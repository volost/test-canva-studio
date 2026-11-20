import dataclasses
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.config import load_config
from app.steps import STEPS
from app.store import (
    CorruptJSON,
    create_template,
    list_templates,
    read_json,
    skeleton_dir,
    template_dir,
    write_json_atomic,
)

FIXTURE = Path(__file__).parent / "fixtures" / "config.json"


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.cfg = dataclasses.replace(load_config(FIXTURE), root=self.tmp)

    def test_atomic_write_roundtrip(self):
        p = self.tmp / "a" / "b" / "x.json"
        data = {"name": "Привіт", "n": [1, 2]}
        write_json_atomic(p, data)
        self.assertEqual(read_json(p), data)
        self.assertIn("Привіт", p.read_text(encoding="utf-8"))
        self.assertEqual([f.name for f in p.parent.iterdir()], ["x.json"])

    def test_atomic_write_failure_keeps_old_file(self):
        p = self.tmp / "x.json"
        write_json_atomic(p, {"ok": 1})
        with self.assertRaises(TypeError):
            write_json_atomic(p, {"bad": object()})
        self.assertEqual(read_json(p), {"ok": 1})
        self.assertEqual([f.name for f in self.tmp.iterdir()], ["x.json"])

    def test_read_corrupt_raises(self):
        p = self.tmp / "bad.json"
        p.write_text('{"a":', encoding="utf-8")
        with self.assertRaises(CorruptJSON) as ctx:
            read_json(p)
        self.assertEqual(ctx.exception.path, p)

    def test_read_missing_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            read_json(self.tmp / "nope.json")

    def test_create_template_writes_state(self):
        d = create_template(self.cfg, "rose-1", "ivory-lace")
        self.assertEqual(d, template_dir(self.cfg, "rose-1"))
        self.assertEqual(d, self.tmp / "templates" / "rose-1")
        state = read_json(d / "state.json")
        self.assertEqual(state["skeleton"], "ivory-lace")
        self.assertIsNone(state["canva_copy_id"])
        self.assertEqual(state["chosen"], {})
        self.assertEqual(list(state["steps"]), list(STEPS))
        for s in STEPS:
            self.assertEqual(state["steps"][s]["status"], "draft")
            self.assertRegex(state["steps"][s]["updated_utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_skeleton_dir(self):
        self.assertEqual(skeleton_dir(self.cfg, "ivory-lace"), self.tmp / "skeletons" / "ivory-lace")

    def test_create_template_rejects_bad_name(self):
        for bad in ("../x", "", "a/b", "A", "a_b", "x" * 41, ".", ".."):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    create_template(self.cfg, bad, "ivory-lace")
        self.assertFalse((self.tmp / "templates").exists())

    def test_create_template_accepts_boundary_names(self):
        for ok in ("a", "0", "a-b-9", "x" * 40):
            with self.subTest(ok=ok):
                create_template(self.cfg, ok, "s")

    def test_create_template_rejects_bad_skeleton(self):
        for bad in ("../x", "", "a/b", "S"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    create_template(self.cfg, "ok", bad)
        self.assertFalse((self.tmp / "templates" / "ok").exists())

    def test_create_template_existing_raises(self):
        create_template(self.cfg, "t1", "s")
        with self.assertRaises(FileExistsError):
            create_template(self.cfg, "t1", "s")

    def test_list_templates(self):
        self.assertEqual(list_templates(self.cfg), [])
        create_template(self.cfg, "b", "s")
        create_template(self.cfg, "a", "s")
        (self.tmp / "templates" / "empty-dir").mkdir()
        (self.tmp / "templates" / "file.txt").write_text("x")
        self.assertEqual(list_templates(self.cfg), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
