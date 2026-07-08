import http.server, socketserver, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()
port = int(os.environ.get('PORT', 8765))
with socketserver.ThreadingTCPServer(("", port), H) as s:
    s.serve_forever()
