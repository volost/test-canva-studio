import json
import tempfile
import unittest
from pathlib import Path

from app.config import Config, load_config

FIXTURE = Path(__file__).parent / "fixtures" / "config.json"


class ConfigTests(unittest.TestCase):
    def test_load_config_reads_values(self):
        cfg = load_config(FIXTURE)
        self.assertIsInstance(cfg, Config)
        self.assertEqual(cfg.forbidden_design_ids, frozenset({"DAHarqlqips"}))
        self.assertEqual(cfg.studio_port, 8765)
        self.assertIsInstance(cfg.root, Path)
        self.assertEqual(cfg.comfy_url, "http://127.0.0.1:8188")

    def test_load_config_rejects_missing_key(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        del data["comfy_url"]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_config(p)
        self.assertIn("comfy_url", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
