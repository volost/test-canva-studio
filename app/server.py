"""Studio HTTP server: stdlib only, listens on 127.0.0.1."""
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.config import Config, load_config

STATIC_DIR = (Path(__file__).parent / "static").resolve()
HOST = "127.0.0.1"


def _make_handler(cfg: Config):
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
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self._send(200, ctype, target.read_bytes())

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/health":
                self._json(200, {
                    "ok": True,
                    "comfy_url": cfg.comfy_url,
                    "models_mounted": cfg.models_dir.is_dir(),
                })
            else:
                self._static(path)

        def log_message(self, format, *args) -> None:  # noqa: A002
            pass

    return Handler


def make_server(cfg: Config, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), _make_handler(cfg))


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
