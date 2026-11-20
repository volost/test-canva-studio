import copy
import json
import unittest
from pathlib import Path

from app.schema import validate_map, validate_style

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def has(msgs, needle):
    return any(needle in m for m in msgs)


class MapTests(unittest.TestCase):
    def setUp(self):
        self.m = load("map_min.json")

    def test_map_min_valid(self):
        self.assertEqual(validate_map(self.m), [])

    def test_map_rejects_slot_without_locator(self):
        del self.m["slots"][0]["locator"]
        self.assertTrue(has(validate_map(self.m), "locator"))
        self.m["slots"][0]["locator"] = ""
        self.assertTrue(has(validate_map(self.m), "locator"))

    def test_map_rejects_image_slot_with_unknown_asset(self):
        self.m["slots"][0]["asset"] = "nope"
        self.assertTrue(has(validate_map(self.m), "nope"))
        self.m["slots"][0]["asset"] = None
        self.assertTrue(validate_map(self.m))

    def test_duplicate_locator(self):
        self.m["slots"][1]["locator"] = self.m["slots"][0]["locator"]
        self.assertTrue(has(validate_map(self.m), "duplicate"))

    def test_missing_top_key(self):
        del self.m["protected"]
        self.assertTrue(has(validate_map(self.m), "protected"))

    def test_bad_slot_type_and_asset_kind(self):
        self.m["slots"][0]["type"] = "video"
        self.m["assets"]["hero"]["kind"] = "gif"
        r = validate_map(self.m)
        self.assertTrue(has(r, "video"))
        self.assertTrue(has(r, "gif"))

    def test_bad_frame(self):
        self.m["assets"]["hero"]["frame"] = [0, 800]
        self.assertTrue(has(validate_map(self.m), "frame"))
        self.m["assets"]["hero"]["frame"] = [1200.5, 800]
        self.assertTrue(has(validate_map(self.m), "frame"))
        self.m["assets"]["hero"]["frame"] = [True, 800]
        self.assertTrue(has(validate_map(self.m), "frame"))

    def test_text_and_colour_slot_with_asset_rejected(self):
        self.m["slots"][-2]["asset"] = "hero"
        self.assertTrue(validate_map(self.m))

    def test_protected_must_be_strings(self):
        self.m["protected"] = ["a", 3]
        self.assertTrue(has(validate_map(self.m), "protected"))
        self.m["protected"] = "a"
        self.assertTrue(has(validate_map(self.m), "protected"))

    def test_envelope_null_ok_and_bad_envelope(self):
        self.m["envelope"] = None
        self.assertEqual(validate_map(self.m), [])
        self.m = load("map_min.json")
        del self.m["envelope"]["tip"]
        self.assertTrue(has(validate_map(self.m), "tip"))
        self.m = load("map_min.json")
        self.m["envelope"]["tip"] = ["a", 1]
        self.assertTrue(has(validate_map(self.m), "tip"))

    def test_envelope_seal_asset(self):
        self.m["envelope"]["seal_asset"] = None
        self.assertEqual(validate_map(self.m), [])
        del self.m["envelope"]["seal_asset"]
        self.assertEqual(validate_map(self.m), [])
        self.m["envelope"]["seal_asset"] = "ghost"
        self.assertTrue(has(validate_map(self.m), "ghost"))

    def test_slot_layer(self):
        # valid on composed image slots: fixture already has cover + flap (positive control)
        self.assertEqual(validate_map(self.m), [])
        by = {s["locator"]: s for s in self.m["slots"]}
        by["p1/image/env-cover"]["layer"] = "body"
        self.assertEqual(validate_map(self.m), [])
        by["p1/image/env-cover"]["layer"] = "roof"
        self.assertTrue(has(validate_map(self.m), "roof"))
        by["p1/image/env-cover"]["layer"] = "cover"
        by["p1/image/hero"]["layer"] = "cover"  # photo asset, not composed
        self.assertTrue(has(validate_map(self.m), "layer"))
        del by["p1/image/hero"]["layer"]
        by["p1/text/names"]["layer"] = "cover"  # not an image slot
        self.assertTrue(has(validate_map(self.m), "layer"))

    def test_unhashable_values_return_messages(self):
        self.m["slots"][0]["asset"] = ["hero"]
        self.assertTrue(has(validate_map(self.m), "asset"))
        self.m = load("map_min.json")
        by = {s["locator"]: s for s in self.m["slots"]}
        by["p1/image/env-cover"]["asset"] = {"a": 1}
        by["p1/image/env-cover"]["layer"] = "cover"
        self.assertTrue(validate_map(self.m))
        self.m = load("map_min.json")
        self.m["envelope"]["seal_asset"] = ["seal"]
        self.assertTrue(has(validate_map(self.m), "seal_asset"))

    def test_slot_target_validated(self):
        by = {s["locator"]: s for s in self.m["slots"]}
        by["p1/colour/background"]["target"] = "stroke"
        self.assertEqual(validate_map(self.m), [])
        by["p1/colour/background"]["target"] = "fill"
        self.assertEqual(validate_map(self.m), [])
        by["p1/colour/background"]["target"] = "strok"          # a typo must fail at map time
        self.assertTrue(has(validate_map(self.m), "strok"))
        by["p1/colour/background"]["target"] = ["stroke"]
        self.assertTrue(has(validate_map(self.m), "target"))
        by["p1/colour/background"]["target"] = "fill"
        by["p1/text/names"]["target"] = "fill"                  # not a colour slot
        self.assertTrue(has(validate_map(self.m), "colour slot"))

    def test_keep_is_an_optional_list_of_strings(self):
        self.assertEqual(validate_map(self.m), [])               # absent: fine
        self.m["keep"] = ["p1/text/footer"]
        self.assertEqual(validate_map(self.m), [])
        self.m["keep"] = []
        self.assertEqual(validate_map(self.m), [])
        for bad in ("p1/text/footer", [1], None, {"a": 1}, [["x"]]):
            self.m["keep"] = bad
            self.assertTrue(has(validate_map(self.m), "keep"), bad)

    def test_non_dict_inputs(self):
        for bad in (None, [], "x", 3):
            r = validate_map(bad)
            self.assertTrue(r and all(isinstance(x, str) for x in r))

    def test_garbage_shapes_do_not_crash(self):
        self.m["slots"] = [1, None]
        self.m["assets"] = []
        self.m["pages"] = "x"
        self.assertTrue(validate_map(self.m))


class StyleTests(unittest.TestCase):
    def setUp(self):
        self.m = load("map_min.json")
        self.s = load("style_min.json")

    def test_style_min_valid(self):
        self.assertEqual(validate_style(self.s, self.m), [])

    def test_style_requires_prompt_per_asset(self):
        del self.s["image_prompts"]["hero"]
        self.assertTrue(has(validate_style(self.s, self.m), "hero"))
        self.s["image_prompts"]["hero"] = "   "
        self.assertTrue(has(validate_style(self.s, self.m), "hero"))

    def test_composed_asset_needs_prompt_too(self):
        del self.s["image_prompts"]["envelope"]
        self.assertTrue(has(validate_style(self.s, self.m), "envelope"))

    def test_palette_hex(self):
        self.s["palette"]["accent"] = "#7d8f6"
        self.assertTrue(has(validate_style(self.s, self.m), "accent"))
        self.s["palette"]["accent"] = "7d8f69"
        self.assertTrue(has(validate_style(self.s, self.m), "accent"))
        self.s["palette"]["accent"] = "#7D8F69"
        self.assertEqual(validate_style(self.s, self.m), [])
        self.s["palette"]["accent"] = "#7d8f69ff"
        self.assertTrue(validate_style(self.s, self.m))

    def test_colour_role_value_must_be_palette_role(self):
        self.s["colour_roles"]["background"] = "missing"
        self.assertTrue(has(validate_style(self.s, self.m), "missing"))

    def test_colour_slot_role_needs_entry(self):
        self.s["colour_roles"] = {}
        self.assertTrue(has(validate_style(self.s, self.m), "background"))

    def test_fonts_and_font_map(self):
        del self.s["fonts"]["script"]
        self.assertTrue(has(validate_style(self.s, self.m), "script"))
        self.s = load("style_min.json")
        self.s["font_map"]["body"] = "display"
        self.assertTrue(has(validate_style(self.s, self.m), "display"))

    def test_unhashable_values_return_messages(self):
        self.s["colour_roles"]["background"] = ["background"]
        self.assertTrue(has(validate_style(self.s, self.m), "background"))
        self.s = load("style_min.json")
        for s in self.m["slots"]:
            if s["type"] == "colour":
                s["role"] = ["background"]
        self.assertTrue(has(validate_style(self.s, self.m), "colour"))

    def test_non_dict(self):
        self.assertTrue(validate_style(None, self.m))
        self.assertTrue(validate_style(self.s, None))


if __name__ == "__main__":
    unittest.main()
