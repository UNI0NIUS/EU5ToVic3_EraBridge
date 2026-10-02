"""Loopback desktop workbench. Every project and export is an independent directory."""
import argparse
from copy import deepcopy
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import traceback
from urllib.parse import urlparse, parse_qs
import uuid
import webbrowser
import numpy as np
from PIL import Image
from converter_project import DEFAULTS, read, write, settings
from converter_world import Candidate
from converter_export import export_candidate
from converter_project import resolve_merges

ROOT=Path(__file__).resolve().parents[1]
UI=Path(__file__).with_name('converter_ui')

from converter_controller import App

def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def send(self,status,data,mime='application/json; charset=utf-8'):
            if isinstance(data,(dict,list)):data=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
            elif isinstance(data,str):data=data.encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data)
        def allowed(self):return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.allowed():return self.send(403,dict(error='仅允许本机访问'))
            u=urlparse(self.path);q=parse_qs(u.query)
            try:
                with app.lock:
                    if u.path=='/api/session':return self.send(200,dict(token=app.token,defaults=app.defaults(),**app.snapshot()))
                    if u.path=='/api/status':return self.send(200,dict(job=app.job,revision=app.project['revision'] if app.project else None,project_id=app.project['id'] if app.project else None))
                    if u.path=='/api/project':return self.send(200,app.snapshot())
                    if u.path=='/api/map':return self.send(200,app.image(q.get('view',['country'])[0]),'image/png')
                    if u.path=='/api/hit':return self.send(200,app.hit(int(float(q['x'][0])),int(float(q['y'][0]))))
                    if u.path=='/api/region':return self.send(200,app.region(q['id'][0]))
                    if u.path=='/api/export-project':return self.send(200,app.project or {})
                assets={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
                if u.path in assets:
                    name,mime=assets[u.path];return self.send(200,(UI/name).read_bytes(),mime)
                self.send(404,dict(error='不存在'))
            except (ValueError,KeyError,TypeError) as e:self.send(400,dict(error=str(e)))
            except Exception as e:self.send(500,dict(error=str(e)))
        def do_POST(self):
            origin=self.headers.get('Origin')
            if not self.allowed() or self.headers.get('X-Converter-Token')!=app.token or (origin and origin!='http://'+self.headers['Host']):
                try:
                    self.connection.settimeout(2)
                    length=int(self.headers.get('Content-Length','0'))
                    if 0<length<=2_000_000:self.rfile.read(length)
                except (OSError,ValueError):pass
                return self.send(403,dict(error='本机会话无效'))
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=2_000_000:raise ValueError('请求过大或为空')
                body=json.loads(self.rfile.read(length))
                route=self.path.removeprefix('/api/')
                if route=='load':result=app.load(body)
                elif route in ('settings','merge','undo','restore'):result=app.mutate(route,body)
                elif route=='export':
                    with app.lock:
                        app.check_revision(body);project=deepcopy(app.project);world=app.world
                        out=app.workspace/'exports'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
                        result=app.background('导出并校验候选包',lambda:export_candidate(world,project,out))
                elif route=='convert':
                    from converter_pipeline import run_conversion
                    def progress(message):
                        with app.lock:
                            if app.job['status']=='running':app.job['message']='转换中 · '+message
                    result=app.background('运行通用转换流水线',lambda:run_conversion(ROOT,app.workspace,body,progress))
                elif route=='pick':
                    # Separate process owns the native dialog event loop.
                    result=subprocess.run([sys.executable,str(Path(__file__).with_name('converter_picker.py')),body.get('kind','file')],capture_output=True,text=True,encoding='utf-8',check=True)
                    result=dict(path=result.stdout.strip())
                elif route=='shutdown':
                    if app.job['status']=='running':raise RuntimeError('任务仍在运行，请完成后退出')
                    self.send(200,dict(status='closed'))
                    threading.Thread(target=self.server.shutdown,daemon=True).start();return
                else:return self.send(404,dict(error='未知操作'))
                self.send(200,result)
            except RuntimeError as e:self.send(409,dict(error=str(e)))
            except (ValueError,KeyError,TypeError) as e:self.send(400,dict(error=str(e)))
            except Exception as e:self.send(500,dict(error=str(e)))
        def log_message(self,*args):pass
    return Handler

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,default=ROOT/'.local/converter');p.add_argument('--port',type=int,default=0);p.add_argument('--no-browser',action='store_true')
    a=p.parse_args()
    if not a.no_browser and (a.workspace/'session.json').exists():
        from urllib.request import urlopen
        try:
            old=read(a.workspace/'session.json')['url']
            u=urlparse(old)
            if u.scheme=='http' and u.hostname=='127.0.0.1':
                with urlopen(old+'/api/status',timeout=2) as response:
                    if response.status==200:webbrowser.open(old);return
        except (OSError,ValueError,KeyError):pass
    app=App(a.workspace);server=ThreadingHTTPServer(('127.0.0.1',a.port),handler(app))
    url=f'http://127.0.0.1:{server.server_port}'
    write(a.workspace/'session.json',dict(url=url,pid=os.getpid()))
    print(url,flush=True)
    if not a.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
