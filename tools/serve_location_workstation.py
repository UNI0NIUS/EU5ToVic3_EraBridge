"""Loopback-only map workstation with atomic local review persistence."""
import argparse
import base64
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlparse

import numpy as np
from PIL import Image
from build_location_workstation import DEFAULT, packed
from location_reviews import ReviewStore

UI = Path(__file__).resolve().parent / 'location_workstation'


class App:
    def __init__(self, directory):
        self.directory = directory
        self.data = json.loads((directory / 'data.json').read_text(encoding='utf-8'))
        self.store = ReviewStore(directory, self.data)
        self.token = secrets.token_urlsafe(32)
        self.images = {kind: Image.open(directory / f'{kind}-ids.png').convert('RGB') for kind in ('source', 'target')}
        self.ids = {k: packed(im) for k, im in self.images.items()}
        self.source_colors = {r['color']: n for n, r in self.data['sources'].items()}

    @lru_cache(maxsize=96)
    def highlight(self, kind, key):
        color = int(key[1:], 16) if kind == 'target' else int(self.data['sources'][key]['color'], 16)
        yy, xx = np.where(self.ids[kind] == color)
        if not len(xx):
            return {'box': None}  # Tiny source islands remain visible via native-pixel centroid markers.
        x0, x1, y0, y1 = int(xx.min()), int(xx.max())+1, int(yy.min()), int(yy.max())+1
        mask = self.ids[kind][y0:y1, x0:x1] == color
        rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
        rgba[mask] = (255, 196, 75, 180)
        buf = io.BytesIO(); Image.fromarray(rgba).save(buf, format='PNG')
        return {'box': [x0, y0, x1-x0, y1-y0], 'image': 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()}


def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, mime='application/json; charset=utf-8'):
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            elif isinstance(data, str):
                data = data.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers(); self.wfile.write(data)

        def allowed(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.allowed():
                return self.send(403, {'error': 'Local host required'})
            u = urlparse(self.path); q = parse_qs(u.query)
            try:
                if u.path == '/api/session':
                    return self.send(200, {'token': app.token, 'reviews': app.store.doc})
                if u.path == '/api/data':
                    return self.send(200, app.data)
                if u.path == '/api/export':
                    return self.send(200, app.store.doc)
                if u.path == '/api/hit':
                    kind = q['map'][0]; x = int(float(q['x'][0])); y = int(float(q['y'][0]))
                    if kind not in app.ids or not (0 <= x < app.images[kind].width and 0 <= y < app.images[kind].height):
                        raise ValueError('Outside map')
                    color = f'{int(app.ids[kind][y,x]):06X}'
                    key = 'x'+color if kind == 'target' else app.source_colors.get(color)
                    if kind == 'target' and key not in app.data['targets']:
                        key = None
                    return self.send(200, {'key': key})
                if u.path == '/api/highlight':
                    kind, key = q['map'][0], q['key'][0]
                    if kind not in ('source', 'target') or key not in app.data['targets' if kind == 'target' else 'sources']:
                        raise ValueError('Unknown map location')
                    return self.send(200, app.highlight(kind, key))
                assets = {'/': (UI/'index.html', 'text/html; charset=utf-8'),
                          '/app.js': (UI/'app.js', 'text/javascript; charset=utf-8'),
                          '/style.css': (UI/'style.css', 'text/css; charset=utf-8')}
                for kind in ('source', 'target'):
                    assets[f'/{kind}-map.png'] = (app.directory/f'{kind}-map.png', 'image/png')
                if u.path in assets:
                    path, mime = assets[u.path]
                    return self.send(200, path.read_bytes(), mime)
                self.send(404, {'error': 'Not found'})
            except (ValueError, KeyError, IndexError) as e:
                self.send(400, {'error': str(e)})

        def do_POST(self):
            origin = self.headers.get('Origin')
            if not self.allowed() or self.headers.get('X-Review-Token') != app.token or (origin and origin != 'http://'+self.headers['Host']):
                return self.send(403, {'error': 'Invalid local session'})
            if self.path not in ('/api/save', '/api/import'):
                return self.send(404, {'error': 'Not found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2_000_000:
                    raise ValueError('Invalid request length')
                body = json.loads(self.rfile.read(length))
                entries = app.store.validate(body['document']) if self.path == '/api/import' else body['entries']
                self.send(200, app.store.save(body['revision'], entries))
            except RuntimeError as e:
                self.send(409, {'error': str(e)})
            except (ValueError, KeyError, TypeError) as e:
                self.send(400, {'error': str(e)})
            except OSError as e:
                self.send(500, {'error': 'Could not save to disk: '+str(e)})

        def log_message(self, fmt, *args):
            if args and str(args[0]).startswith('POST'):
                super().log_message(fmt, *args)
    return Handler


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--data', type=Path, default=DEFAULT); p.add_argument('--port', type=int, default=8766)
    a = p.parse_args(); app = App(a.data)
    server = ThreadingHTTPServer(('127.0.0.1', a.port), handler(app))
    print(f'Location workstation: http://127.0.0.1:{a.port} | {len(app.data["locations"])} locations', flush=True)
    server.serve_forever()
