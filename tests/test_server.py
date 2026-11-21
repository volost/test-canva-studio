"""HTTP layer: binds a real port on 127.0.0.1, so it needs the sandbox off (EPERM otherwise); checks health, the static index, path traversal refusal and that a static file is served."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from app.config import load_config
from app.server import make_server

FIXTURE = Path(__file__).parent / "fixtures" / "config.json"


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(FIXTURE)
        self.server = make_server(self.cfg, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def get(self, path):
        return urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5)

    def test_health_endpoint(self):
        with self.get("/api/health") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers["Content-Type"], "application/json; charset=utf-8")
            body = json.loads(r.read().decode("utf-8"))
        self.assertIs(body["ok"], True)
        self.assertEqual(body["comfy_url"], self.cfg.comfy_url)
        self.assertIsInstance(body["models_mounted"], bool)

    def test_server_binds_localhost_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_index_served(self):
        with self.get("/") as r:
            self.assertEqual(r.status, 200)
            self.assertIn("text/html", r.headers["Content-Type"])
            self.assertIn("Студія шаблонів", r.read().decode("utf-8"))

    def test_static_rejects_path_traversal(self):
        for path in ("/../config.json", "/%2e%2e/config.json", "/..%2fconfig.json", "/static/../../config.json"):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    self.get(path)
                self.assertEqual(ctx.exception.code, 404)

    def test_control_existing_static_file_is_served(self):
        # control for the traversal test: the same code path must serve a legit file
        with self.get("/index.html") as r:
            self.assertEqual(r.status, 200)


if __name__ == "__main__":
    unittest.main()
