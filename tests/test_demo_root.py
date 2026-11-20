"""The demo root: seeding (no server, no socket) gives every screen of the web interface something to show."""
import json
import tempfile
import unittest
from pathlib import Path

from app.api import Api
from tools import demo_root
from tools.demo_root import DemoError, UNICODE


class DemoRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "demo"  # missing: seeding creates it
        cls.cfg = demo_root.seed(cls.root, port=8765)
        cls.api = Api(cls.cfg)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def get(self, path):
        status, body = self.api.handle("GET", path)
        self.assertEqual(status, 200, body)
        return body

    def test_api_sees_templates_and_skeleton(self):
        by = {t["name"]: t for t in self.get("/api/templates")["templates"]}
        self.assertEqual({"demo-sage", "demo-texts", "demo-done", "demo-nocopy"}, {n for n, t in by.items() if "error" not in t})
        self.assertIn("error", by["demo-broken"])  # a corrupt state.json is listed as an error row
        sk = self.get("/api/skeletons")["skeletons"]
        self.assertEqual([(s["name"], s["has_map"]) for s in sk], [("mini", True)])

    def test_every_screen_has_data(self):
        sage = self.get("/api/templates/demo-sage")
        self.assertEqual(sage["state"]["steps"]["style"]["status"], "approved")
        self.assertEqual(sage["state"]["steps"]["images"]["status"], "review")
        self.assertEqual({a["asset"] for a in sage["assets"]}, {"hero", "florals", "envelope", "seal"})
        hero = next(a for a in sage["assets"] if a["asset"] == "hero")
        self.assertEqual(len(hero["versions"]), 2)
        self.assertEqual(hero["chosen"], hero["versions"][0]["file"])
        for a in sage["assets"]:
            self.assertTrue(a["chosen"], a["asset"])
            for v in a["versions"]:
                self.assertTrue((self.root / "templates" / "demo-sage" / "assets" / v["file"]).is_file())
        done = self.get("/api/templates/demo-done")
        self.assertEqual(done["state"]["canva_copy_id"], demo_root.COPY_ID)
        self.assertEqual(done["state"]["steps"]["verify"]["status"], "review")
        checks = done["job_results"]["verify"]["checks"]
        self.assertEqual([c["passed"] for c in checks], [True, True, False])
        self.assertTrue((self.root / "templates" / "demo-done" / "assets" / "contact_sheet.jpg").is_file())
        self.assertTrue((self.root / "skeletons" / "mini" / "sections" / "PGmini01.png").is_file())

    def test_unicode_texts_and_warnings_are_stored_exactly(self):
        t = self.get("/api/templates/demo-texts")
        self.assertEqual(t["texts"]["p1/text/names"], UNICODE)
        self.assertEqual(set(t["length_warnings"]), {"p1/text/intro", "p1/cell/day"})
        self.assertEqual(self.get("/api/templates/demo-done")["texts"]["p1/text/names"], UNICODE)
        raw = json.loads((self.root / "templates" / "demo-texts" / "texts.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["p1/text/names"], UNICODE)

    def test_directions_job_result_has_two_directions(self):
        t = self.get("/api/templates/demo-sage")
        res = json.loads((self.root / "templates" / "demo-sage" / "jobs" / f"{t['job_results']['style']['job_id']}.result.json").read_text(encoding="utf-8"))
        self.assertEqual(len(res["outputs"]["directions"]), 2)
        self.assertEqual(res["status"], "done")

    def test_failed_corrupt_and_copy_missing_are_shown_as_such(self):
        texts = self.get("/api/templates/demo-texts")["job_results"]["texts"]
        self.assertEqual(texts["status"], "failed")
        nocopy = self.get("/api/templates/demo-nocopy")
        self.assertEqual(nocopy["job_results"]["apply"]["status"], "failed")
        self.assertTrue(nocopy["job_results"]["apply"]["copy_missing"])
        jobs = self.get("/api/jobs")
        self.assertEqual([j["id"] for j in jobs["jobs"] if j["state"] == "corrupt"], ["20261101T090000Z-verify"])
        self.assertEqual(jobs["template_errors"], {"demo-broken": "пошкоджений state.json"})
        # nothing is left pending or running: the Canva writer is free
        self.assertEqual(list((self.root / "jobs" / "pending").glob("*.json")), [])

    def test_config_points_comfy_to_a_closed_port_and_models_dir_exists(self):
        self.assertEqual(self.cfg.root, self.root.resolve())
        self.assertEqual(self.cfg.comfy_url, demo_root.CLOSED_COMFY)
        self.assertTrue(self.cfg.models_dir.is_dir())
        written = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(written["root"], str(self.root.resolve()))
        self.assertEqual(self.get("/api/health")["models_mounted"], True)

    def test_refuses_a_non_empty_dir_and_leaves_it_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            keep = Path(d) / "keep.txt"
            keep.write_text("mine", encoding="utf-8")
            with self.assertRaises(DemoError):
                demo_root.seed(Path(d))
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["keep.txt"])
            self.assertEqual(keep.read_text(encoding="utf-8"), "mine")
        with self.assertRaises(DemoError):  # seeding twice into the same root is refused too
            demo_root.seed(self.root)
        with tempfile.NamedTemporaryFile() as f:
            with self.assertRaises(DemoError):
                demo_root.seed(Path(f.name))

    def test_empty_existing_dir_is_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = demo_root.seed(Path(d), port=0, models_present=False)
            status, body = Api(cfg).handle("GET", "/api/health")
            self.assertEqual((status, body["models_mounted"]), (200, False))


if __name__ == "__main__":
    unittest.main()
