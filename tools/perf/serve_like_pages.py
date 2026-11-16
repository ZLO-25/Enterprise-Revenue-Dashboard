# 模擬 GitHub Pages：gzip、Cache-Control: max-age=600、ETag/304
import http.server, gzip, hashlib, os, sys, mimetypes, socketserver
ROOT=sys.argv[1]; PORT=int(sys.argv[2])
cache={}
class H(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*a): pass
    def do_GET(self):
        p=self.path.split('?')[0].lstrip('/')
        fp=os.path.join(ROOT,p)
        if os.path.isdir(fp): fp=os.path.join(fp,'index.html')
        if not os.path.isfile(fp):
            self.send_response(404); self.send_header('Content-Length','0'); self.end_headers(); return
        if fp not in cache:
            raw=open(fp,'rb').read(); ct=mimetypes.guess_type(fp)[0] or 'application/octet-stream'
            gz=gzip.compress(raw,6) if ct.startswith(('text','application/j','image/svg')) else None
            cache[fp]=(raw,gz,'"'+hashlib.md5(raw).hexdigest()+'"',ct)
        raw,gz,etag,ct=cache[fp]
        if self.headers.get('If-None-Match')==etag:
            self.send_response(304); self.send_header('ETag',etag); self.send_header('Cache-Control','max-age=600'); self.send_header('Content-Length','0'); self.end_headers(); return
        body=gz if gz and 'gzip' in (self.headers.get('Accept-Encoding') or '') else raw
        self.send_response(200); self.send_header('Content-Type',ct+('; charset=utf-8' if ct.startswith('text') or 'javascript' in ct else ''))
        if body is gz: self.send_header('Content-Encoding','gzip')
        self.send_header('ETag',etag); self.send_header('Cache-Control','max-age=600'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
class S(socketserver.ThreadingMixIn,http.server.HTTPServer): daemon_threads=True
S(('127.0.0.1',PORT),H).serve_forever()
