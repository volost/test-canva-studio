"""ComfyUI client against a fake ComfyUI HTTP server on 127.0.0.1 (no real ComfyUI, no GPU)."""
import dataclasses
import json
import socket
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import unittest
from pathlib import Path

from app.comfy import ComfyError, build_graph, generate, ping
from app.config import load_config

FIXTURE = Path(__file__).parent / "fixtures" / "config.json"


def closed_port_cfg():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return dataclasses.replace(load_config(FIXTURE), comfy_url=f"http://127.0.0.1:{port}")


class _Fake(BaseHTTPRequestHandler):
    polls = 0

    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self._send(json.dumps({"prompt_id": "abc", "node_errors": {}}).encode())

    def do_GET(self):
        if self.path.startswith("/history/abc"):
            type(self).polls += 1
            if type(self).polls < 2:
                return self._send(b"{}")
            img = {"filename": "../evil.png", "subfolder": "", "type": "output"}
            return self._send(json.dumps({"abc": {"status": {"status_str": "success"},
                                                  "outputs": {"10": {"images": [img]}}}}).encode())
        if self.path.startswith("/view?"):
            return self._send(b"PNGDATA", "image/png")
        self.send_error(404)


class ComfyTests(unittest.TestCase):
    def nodes(self, graph, cls):
        return [n for n in graph.values() if n["class_type"] == cls]

    def test_build_graph_settings(self):
        g = build_graph("a cat", 1344, 768, 77, "pfx")
        (ks,) = self.nodes(g, "KSampler")
        self.assertEqual(ks["inputs"]["steps"], 8)
        self.assertEqual(ks["inputs"]["cfg"], 1)
        self.assertEqual(ks["inputs"]["sampler_name"], "res_multistep")
        self.assertEqual(ks["inputs"]["scheduler"], "simple")
        self.assertEqual(ks["inputs"]["seed"], 77)
        (ms,) = self.nodes(g, "ModelSamplingAuraFlow")
        self.assertEqual(ms["inputs"]["shift"], 3)
        (clip,) = self.nodes(g, "CLIPLoader")
        self.assertEqual(clip["inputs"]["type"], "lumina2")
        (lat,) = self.nodes(g, "EmptySD3LatentImage")
        self.assertEqual((lat["inputs"]["width"], lat["inputs"]["height"]), (1344, 768))
        (enc,) = self.nodes(g, "CLIPTextEncode")
        self.assertEqual(enc["inputs"]["text"], "a cat")
        (save,) = self.nodes(g, "SaveImage")
        self.assertEqual(save["inputs"]["filename_prefix"], "pfx")
        self.assertEqual(len(self.nodes(g, "ConditioningZeroOut")), 1)

    def test_build_graph_rejects_bad_size(self):
        with self.assertRaises(ValueError):
            build_graph("x", 1000, 768, 1, "p")

    def test_ping_closed_port_fast(self):
        cfg = closed_port_cfg()
        t = time.monotonic()
        self.assertIs(ping(cfg), False)
        self.assertLess(time.monotonic() - t, 5)

    def test_generate_closed_port_message(self):
        cfg = closed_port_cfg()
        t = time.monotonic()
        with self.assertRaises(ComfyError) as cm:
            generate(cfg, "x", 512, 512, 1, "p", Path("."))
        self.assertIn("ComfyUI недоступний", str(cm.exception))
        self.assertLess(time.monotonic() - t, 5)

    def test_generate_happy_path_polls_and_saves_inside_out_dir(self):
        srv = HTTPServer(("127.0.0.1", 0), _Fake)
        _Fake.polls = 0
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        cfg = dataclasses.replace(load_config(FIXTURE), comfy_url=f"http://127.0.0.1:{srv.server_port}")
        with tempfile.TemporaryDirectory() as d:
            out = generate(cfg, "x", 512, 512, 1, "p", Path(d) / "o", poll_interval=0.01)
            self.assertEqual([p.name for p in out], ["evil.png"])
            self.assertEqual(out[0].parent, Path(d) / "o")
            self.assertEqual(out[0].read_bytes(), b"PNGDATA")
        self.assertGreaterEqual(_Fake.polls, 2)


if __name__ == "__main__":
    unittest.main()
