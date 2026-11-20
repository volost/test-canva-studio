"""Studio HTTP server: stdlib only, listens on 127.0.0.1."""
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.api import Api
from app.config import Config, load_config

STATIC_DIR = (Path(__file__).parent / "static").resolve()
HOST = "127.0.0.1"
MAX_BODY = 5 * 1024 * 1024


def _content_type(path: Path) -> str:
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
        ctype += "; charset=utf-8"
    return ctype


def _make_handler(cfg: Config, api: Api):
    skeletons, templates = (cfg.root / "skeletons").resolve(), (cfg.root / "templates").resolve()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, "application/json; charset=utf-8", body)

        def _static(self, url_path: str) -> None:
            rel = unquote(url_path).lstrip("/") or "index.html"
            try:
                target = (STATIC_DIR / rel).resolve()
                inside = target.is_relative_to(STATIC_DIR) and target.is_file()
            except (OSError, ValueError):
                inside = False
            if not inside:
                self._json(404, {"ok": False, "error": "not found"})
                return
            self._send(200, _content_type(target), target.read_bytes())

        def _file(self, url_path: str) -> None:
            """/files/<path>: only regular files inside skeletons/ and templates/ (symlinks resolved)."""
            rel = unquote(url_path[len("/files/"):])
            try:
                target = (cfg.root / rel).resolve()
                inside = target.is_file() and (target.is_relative_to(skeletons) or target.is_relative_to(templates))
            except (OSError, ValueError):
                inside = False
            if not inside:
                self._json(404, {"error": "файл не знайдено"})
                return
            self._send(200, _content_type(target), target.read_bytes())

        def _api(self, method: str, path: str) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                self._json(400, {"error": "некоректний Content-Length"})
                return
            # always drain the body (capped) so an early error does not reset the connection
            raw = self.rfile.read(min(length, MAX_BODY + 1)) if length else b""
            status, payload = api.handle(method, path, raw)
            self._json(status, payload)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path.startswith("/api/"):
                self._api("GET", path)
            elif path.startswith("/files/"):
                self._file(path)
            else:
                self._static(path)

        def do_POST(self) -> None:
            self._api("POST", urlsplit(self.path).path)

        def do_PUT(self) -> None:
            self._api("PUT", urlsplit(self.path).path)

        def _not_allowed(self) -> None:
            self._json(405, {"error": "метод не підтримується"})

        do_DELETE = do_PATCH = _not_allowed  # the studio deletes nothing

        def log_message(self, format, *args) -> None:  # noqa: A002
            pass

    return Handler


def make_server(cfg: Config, port: int, generate_fn=None) -> ThreadingHTTPServer:
    """`generate_fn` replaces comfy.generate in the generation queue (tests only)."""
    return ThreadingHTTPServer((HOST, port), _make_handler(cfg, Api(cfg, generate_fn)))


def main() -> None:
    cfg = load_config(Path(__file__).resolve().parent.parent / "config.json")
    server = make_server(cfg, cfg.studio_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
