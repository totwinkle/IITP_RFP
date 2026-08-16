from __future__ import annotations

import io
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iitp_app.server import IITPApplication  # noqa: E402


application = IITPApplication(Path(os.environ.get("IITP_DATA_DIR", "/tmp/iitp-data")))


class handler(BaseHTTPRequestHandler):
    """Minimal WSGI-to-Vercel adapter with no third-party runtime dependency."""

    def _dispatch(self):
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length) if length else b""
        environ = {
            "REQUEST_METHOD": self.command,
            "PATH_INFO": self.path.split("?", 1)[0],
            "QUERY_STRING": self.path.split("?", 1)[1] if "?" in self.path else "",
            "SERVER_NAME": self.headers.get("host", "localhost").split(":", 1)[0],
            "SERVER_PORT": self.headers.get("host", "").rsplit(":", 1)[-1] if ":" in self.headers.get("host", "") else "443",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.url_scheme": "https",
            "wsgi.version": (1, 0),
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": sys.stderr,
        }
        for key, value in self.headers.items():
            environ["HTTP_" + key.upper().replace("-", "_")] = value
        if "content-type" in self.headers:
            environ["CONTENT_TYPE"] = self.headers["content-type"]
        if "content-length" in self.headers:
            environ["CONTENT_LENGTH"] = self.headers["content-length"]

        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = headers

        result = application(environ, start_response)
        status_code = int(captured.get("status", "500").split(" ", 1)[0])
        self.send_response(status_code)
        for key, value in captured.get("headers", []):
            self.send_header(key, value)
        chunks = list(result)
        if not any(key.lower() == "content-length" for key, _ in captured.get("headers", [])):
            self.send_header("Content-Length", str(sum(len(chunk) for chunk in chunks)))
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(chunk)
        close = getattr(result, "close", None)
        if close:
            close()

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_PATCH(self):
        self._dispatch()

    def do_OPTIONS(self):
        self._dispatch()
