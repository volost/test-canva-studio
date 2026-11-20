import json
import tempfile
import unittest
from pathlib import Path

from app.store import read_json, write_json_atomic
from app.texts import font_checklist, length_warnings, validate_texts

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


class TextTests(unittest.TestCase):
    def setUp(self):
        self.m = load("map_min.json")
        self.s = load("style_min.json")

    def test_texts_valid_positive_control(self):
        self.assertEqual(validate_texts({"p1/text/names": "Anna & Tom", "p1/text/intro": "Hi"}, self.m), [])
        self.assertEqual(validate_texts({}, self.m), [])

    def test_texts_unknown_locator_rejected(self):
        r = validate_texts({"p1/text/nope": "x"}, self.m)
        self.assertTrue(any("p1/text/nope" in x for x in r))

    def test_texts_non_text_locator_rejected(self):
        for loc in ("p1/image/hero", "p1/colour/background"):
            r = validate_texts({loc: "x"}, self.m)
            self.assertTrue(any(loc in x for x in r), loc)

    def test_texts_values_must_be_str(self):
        r = validate_texts({"p1/text/names": 5}, self.m)
        self.assertTrue(any("p1/text/names" in x for x in r))
        self.assertTrue(validate_texts([], self.m))

    def test_unicode_text_preserved(self):
        s = "We’re “so” happy — Café & <b>\nline"
        texts = {"p1/text/intro": s}
        self.assertEqual(validate_texts(texts, self.m), [])
        self.assertEqual(texts["p1/text/intro"], s)
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "texts.json"
            write_json_atomic(p, texts)
            self.assertEqual(read_json(p), texts)
            self.assertIn("We’re “so” happy — Café & <b>".encode("utf-8"), p.read_bytes())  # raw UTF-8, not \\u-escaped

    def test_length_warning_one_line(self):
        v = "x" * 25
        w = length_warnings({"p1/text/names": v}, self.m)
        self.assertEqual(list(w), ["p1/text/names"])
        self.assertIn("25", w["p1/text/names"])
        self.assertIn("20", w["p1/text/names"])

    def test_length_ok_no_warning(self):
        self.assertEqual(length_warnings({"p1/text/names": "x" * 20}, self.m), {})

    def test_multiline_not_checked_against_max_len(self):
        self.assertEqual(length_warnings({"p1/text/names": "x" * 15 + "\n" + "y" * 15}, self.m), {})

    def test_paragraph_115_percent(self):
        orig = self.m["slots"][-2]["original"]
        limit = (115 * len(orig)) // 100
        self.assertEqual(length_warnings({"p1/text/intro": "z" * limit}, self.m), {})
        w = length_warnings({"p1/text/intro": "z" * (limit + 1)}, self.m)
        self.assertEqual(list(w), ["p1/text/intro"])
        self.assertIn(str(len(orig)), w["p1/text/intro"])
        self.assertIn(str(limit + 1), w["p1/text/intro"])

    def test_paragraph_exact_integer_limit(self):
        for s in self.m["slots"]:
            if s["locator"] == "p1/text/intro":
                s["original"] = "o" * 100
        self.assertEqual(length_warnings({"p1/text/intro": "z" * 115}, self.m), {})
        w = length_warnings({"p1/text/intro": "z" * 116}, self.m)
        self.assertEqual(list(w), ["p1/text/intro"])
        self.assertIn("115", w["p1/text/intro"])
        self.assertNotIn("114", w["p1/text/intro"])

    def test_table_cell_is_a_text(self):
        self.assertEqual(validate_texts({"p1/cell/day": "12"}, self.m), [])
        w = length_warnings({"p1/cell/day": "123"}, self.m)
        self.assertEqual(list(w), ["p1/cell/day"])
        self.assertEqual(length_warnings({"p1/cell/day": "12"}, self.m), {})
        self.assertIn("p1/cell/day", [e["locator"] for e in font_checklist(self.m, self.s)])
        for loc in ("p1/image/hero", "p1/colour/background"):
            self.assertTrue(validate_texts({loc: "x"}, self.m))

    def test_length_ignores_unknown_and_nonstr(self):
        self.assertEqual(length_warnings({"zzz": "x" * 99, "p1/text/names": 5}, self.m), {})

    def test_font_checklist_lists_every_text_role(self):
        r = font_checklist(self.m, self.s)
        self.assertEqual([e["locator"] for e in r], ["p1/text/names", "p1/text/intro", "p1/cell/day"])
        self.assertEqual(r[0], {"locator": "p1/text/names", "role": "heading", "font": "Cormorant Garamond"})
        self.assertEqual(r[1]["font"], "Lato")

    def test_font_checklist_unmapped_role(self):
        del self.s["font_map"]["body"]
        r = font_checklist(self.m, self.s)
        self.assertIn("не задано", r[1]["font"])
        self.assertEqual(r[0]["font"], "Cormorant Garamond")


if __name__ == "__main__":
    unittest.main()
