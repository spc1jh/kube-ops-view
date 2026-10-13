import json
import threading
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

import pytest


class FakeApiServer:
    """Minimal HTTP server answering GET requests with canned JSON responses."""

    def __init__(self):
        self.responses = {}
        self.requests = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                server.requests.append(
                    (path, {k.lower(): v for k, v in self.headers.items()})
                )
                status, body = server.responses.get(
                    path, (404, {"kind": "Status", "message": "not found"})
                )
                data = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:{}".format(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def set_items(self, path, items, status=200):
        self.responses[path] = (status, {"items": items})

    def stop(self):
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def fake_api():
    server = FakeApiServer()
    yield server
    server.stop()
