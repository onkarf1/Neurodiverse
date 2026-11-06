"""Temporary local host: backend API + built frontend with /api proxy."""
from __future__ import annotations

import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "frontend" / "dist"
API = "http://127.0.0.1:8001"
PYTHON = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def do_GET(self):
        if self.path.startswith("/api"):
            return self.proxy()
        return self.serve_spa()

    def do_POST(self):
        return self.proxy() if self.path.startswith("/api") else self.send_error(405)

    def do_PUT(self):
        return self.proxy() if self.path.startswith("/api") else self.send_error(405)

    def do_PATCH(self):
        return self.proxy() if self.path.startswith("/api") else self.send_error(405)

    def do_DELETE(self):
        return self.proxy() if self.path.startswith("/api") else self.send_error(405)

    def serve_spa(self):
        path = self.path.split("?", 1)[0]
        candidate = DIST / path.lstrip("/")
        if path == "/" or not candidate.is_file():
            self.path = "/index.html"
        return SimpleHTTPRequestHandler.do_GET(self)

    def proxy(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "content-length"}}
        req = Request(f"{API}{self.path}", data=body, headers=headers, method=self.command)
        try:
            with urlopen(req, timeout=60) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() not in {"transfer-encoding", "connection", "content-encoding"}:
                        self.send_header(key, value)
                self.end_headers()
                self.wfile.write(payload)
        except HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except URLError as exc:
            msg = f'{{"detail":"Backend unavailable: {exc.reason}"}}'.encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))
        sys.stdout.flush()


def main():
    if not DIST.exists():
        raise SystemExit(f"Missing frontend build at {DIST}")
    if not PYTHON.exists():
        raise SystemExit(f"Missing backend venv at {PYTHON}")

    backend = subprocess.Popen(
        [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"],
        cwd=str(ROOT / "backend"),
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPYCACHEPREFIX": str(ROOT / ".cache" / "pycache")},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 5173), Handler)
    print("StriveTrack is ready. Open http://127.0.0.1:5173")
    print("API docs: http://127.0.0.1:8001/docs")
    print("Ctrl+C stops both servers.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        backend.terminate()
        try:
            backend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()


if __name__ == "__main__":
    main()
