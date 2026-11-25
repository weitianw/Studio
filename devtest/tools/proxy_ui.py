"""预览用的小转发：localhost:<端口，默认 7871> → 测试 Studio（默认 127.0.0.1:7865 = run.py 的 dev；STUDIO_PROXY_TARGET 改）（只给浏览器预览看页面用）
用法：python proxy_ui.py [监听端口] [目标端口]"""
import http.server, os, socketserver, sys, urllib.request, urllib.error

T = 'http://127.0.0.1:' + (sys.argv[2] if len(sys.argv) > 2 else os.environ.get('STUDIO_PROXY_TARGET', '7865'))


class H(http.server.BaseHTTPRequestHandler):
    def _go(self, method):
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n) if n else None
        hd = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'connection', 'accept-encoding', 'origin', 'referer')}
        r = urllib.request.Request(T + self.path, body, hd, method=method)
        try:
            x = urllib.request.urlopen(r, timeout=600)
            code = x.status
        except urllib.error.HTTPError as e:
            x, code = e, e.code
        data = x.read()
        self.send_response(code)
        for k, v in x.headers.items():
            if k.lower() not in ('transfer-encoding', 'connection', 'content-length'):
                self.send_header(k, v)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self): self._go('GET')
    def do_POST(self): self._go('POST')
    def do_DELETE(self): self._go('DELETE')
    def log_message(self, *a): pass


class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


S(('127.0.0.1', int(sys.argv[1]) if len(sys.argv) > 1 else 7871), H).serve_forever()
