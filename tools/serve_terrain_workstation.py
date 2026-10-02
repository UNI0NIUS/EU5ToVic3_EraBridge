"""Separate loopback server: 1337 terrain queue and reusable review records."""
import argparse
import json
from pathlib import Path
import secrets
import base64
import io
from functools import lru_cache
from urllib.parse import urlparse,parse_qs
from http.server import ThreadingHTTPServer
import numpy as np
from PIL import Image
import serve_location_workstation as base
from build_location_workstation import packed
from build_terrain_workstation import DEFAULT
from terrain_reviews import TerrainReviewStore


class App(base.App):
    def __init__(self,directory):
        self.directory=directory
        self.data=json.loads((directory/'data.json').read_text(encoding='utf-8'))
        self.store=TerrainReviewStore(directory,self.data)
        self.data_stamp=(directory/'data.json').stat().st_mtime_ns
        self.token=secrets.token_urlsafe(32)
        self.images={k:Image.open(directory/f'{k}-ids.png').convert('RGB') for k in ('source','target')}
        self.ids={k:packed(im) for k,im in self.images.items()}
        self.source_colors={r['color']:n for n,r in self.data['sources'].items()}

    @lru_cache(maxsize=50)
    def component(self,key):
        group=next(c for c in self.data['components'] if c['component']==key)
        colors=np.array([int(p[1:],16) for p in group['provinces']],dtype=np.uint32)
        mask=np.isin(self.ids['target'],colors);yy,xx=np.where(mask)
        x0,x1,y0,y1=int(xx.min()),int(xx.max())+1,int(yy.min()),int(yy.max())+1
        rgba=np.zeros((y1-y0,x1-x0,4),dtype=np.uint8);rgba[mask[y0:y1,x0:x1]]=(255,181,74,195)
        buf=io.BytesIO();Image.fromarray(rgba).save(buf,format='PNG')
        return dict(box=[x0,y0,x1-x0,y1-y0],image='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode())


def handler(app):
    class Handler(base.handler(app)):
        def do_GET(self):
            stamp=(app.directory/'data.json').stat().st_mtime_ns
            if stamp!=app.data_stamp:
                app.data=json.loads((app.directory/'data.json').read_text(encoding='utf-8-sig'));app.data_stamp=stamp
                app.store.targets={p for c in app.data['components'] for p in c['provinces']};app.component.cache_clear()
            u=urlparse(self.path)
            if u.path=='/api/adjudications':
                if not self.allowed():return self.send(403,{'error':'Local host required'})
                path=app.directory/'adjudications.json'
                return self.send(200,json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {})
            if u.path!='/api/component': return super().do_GET()
            if not self.allowed(): return self.send(403,{'error':'Local host required'})
            try: return self.send(200,app.component(parse_qs(u.query)['id'][0]))
            except (KeyError,StopIteration): return self.send(400,{'error':'Unknown component'})
    return Handler


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=DEFAULT);p.add_argument('--port',type=int,default=8768)
    a=p.parse_args();base.UI=Path(__file__).resolve().parent/'terrain_workstation'
    app=App(a.data);server=ThreadingHTTPServer(('127.0.0.1',a.port),handler(app))
    print(f'1337 terrain workstation: http://127.0.0.1:{a.port}',flush=True);server.serve_forever()
