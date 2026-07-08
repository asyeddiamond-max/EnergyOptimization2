import http.server, socketserver, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
class H(http.server.SimpleHTTPRequestHandler):
    # HTTP/1.0 (one connection per request, no keep-alive) avoids the
    # intermittent net::ERR_CONNECTION_RESET seen under ThreadingTCPServer's
    # default keep-alive handling on Windows when the browser fires several
    # rapid/overlapping requests (e.g. page reload + many data-file fetches).
    protocol_version = "HTTP/1.0"
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()
class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
port = int(os.environ.get('PORT', 8765))
with Server(("", port), H) as s:
    s.serve_forever()
