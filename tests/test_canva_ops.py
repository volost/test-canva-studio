import copy
import json
import re
import tempfile
import unittest
from pathlib import Path

from app.schema import validate_map, validate_style
from canva import facts as F
from canva import layout, outline, probe_diff
from canva.geometry import cover_box
from canva.ops import OpsError, build_image_ops, build_ops, to_calls, verify_batch
from tests import canva_helpers as H


def ops_of(batches):
    return [op for page_ops in batches.values() for op in page_ops]


class CoverBoxTests(unittest.TestCase):
    def test_cover_box_centred_exact(self):
        b = cover_box(433, 600, 866, 1300)
        self.assertAlmostEqual(b["width"], 433)
        self.assertAlmostEqual(b["height"], 650)
        self.assertAlmostEqual(b["top"], -25)
        self.assertAlmostEqual(b["left"], 0)
        self.assertEqual(set(b), {"left", "top", "width", "height"})

    def test_cover_box_wide_image_overflows_sideways(self):
        b = cover_box(400, 400, 2000, 1000)
        self.assertAlmostEqual(b["height"], 400)
        self.assertAlmostEqual(b["width"], 800)
        self.assertAlmostEqual(b["left"], -200)
        self.assertAlmostEqual(b["top"], 0)

    def test_cover_box_same_aspect_is_the_frame(self):
        b = cover_box(1366, 964, 2732, 1928)
        self.assertEqual((round(b["left"], 6), round(b["top"], 6), round(b["width"], 6), round(b["height"], 6)),
                         (0.0, 0.0, 1366.0, 964.0))

    def test_cover_box_rejects_nonsense(self):
        for args in ((0, 10, 5, 5), (10, 10, 0, 5), (-1, 10, 5, 5), (10, 10, 5, float("nan"))):
            with self.assertRaises(ValueError):
                cover_box(*args)


class FixtureTests(unittest.TestCase):
    def test_map_sage_validates_and_matches_both_facts(self):
        m, st = H.load("map_sage.json"), H.load("style_sage.json")
        self.assertEqual(validate_map(m), [])
        self.assertEqual(validate_style(st, m), [])
        orig, sage = H.load("facts_orig.json"), H.load("facts_sage.json")
        want = {"text": "text", "table_cell": "cell"}
        for s in m["slots"]:
            for facts in (orig, sage):
                self.assertIn(s["locator"], facts, s["locator"])
                if s["type"] in want:
                    self.assertEqual(facts[s["locator"]]["type"], want[s["type"]], s["locator"])
        for p in m["protected"]:
            self.assertIn(p, orig)
        self.assertEqual(set(H.load("texts_sage.json")),
                         {s["locator"] for s in m["slots"] if s["type"] in ("text", "table_cell")})


class BuildOpsMiniTests(unittest.TestCase):
    def setUp(self):
        self.m, self.st, self.tx, self.facts = H.mini_map(), H.mini_style(), H.mini_texts(), H.mini_facts()

    def test_build_ops_text_uses_replace_text(self):
        b = build_ops(self.m, self.st, self.tx, self.facts)
        self.assertEqual(list(b), ["PGmini01"])
        ops = b["PGmini01"]
        rep = [o for o in ops if o["type"] == "replace_text"]
        self.assertEqual({o["locator_id"]: o["text"] for o in rep},
                         {"p1/text/names": "CLARA & DAVID", "p1/cell/day": "18"})   # intro is unchanged: no op
        # names text is black and role heading maps to ink: colour op; cell colour only when it has text
        cols = {o["locator_id"]: o["formatting"] for o in ops if o["type"] == "format_text"}
        self.assertEqual(cols["p1/text/names"], {"color": "#2f3a2c"})
        for o in ops:      # only operation types the connector accepts for these slots
            self.assertIn(o["type"], {"replace_text", "format_text", "recolor_element", "update_stroke_properties"})
        # shape background: colour slot -> recolor_element
        self.assertIn({"type": "recolor_element", "locator_id": "p1/colour/background", "color": "#f4efe6"}, ops)

    def test_text_op_order_replace_before_colour(self):
        ops = build_ops(self.m, self.st, self.tx, self.facts)["PGmini01"]
        idx = {(o["type"], o["locator_id"]): i for i, o in enumerate(ops)}
        self.assertLess(idx[("replace_text", "p1/text/names")], idx[("format_text", "p1/text/names")])

    def test_build_ops_never_touches_protected(self):
        self.m["protected"] = ["p1/text/names", "p1/colour/background"]
        notes = []
        b = build_ops(self.m, self.st, self.tx, self.facts, notes=notes)
        locs = {o["locator_id"] for o in ops_of(b)}
        self.assertFalse(locs & set(self.m["protected"]), locs)
        self.assertIn("p1/cell/day", locs)                       # others still written
        for p in self.m["protected"]:
            self.assertTrue(any(p in n and "protected" in n for n in notes), (p, notes))

    def test_protected_footer_in_texts_is_noted_not_written(self):
        self.tx["p1/text/footer"] = "Changed"
        notes = []
        b = build_ops(self.m, self.st, self.tx, self.facts, notes=notes)
        self.assertNotIn("p1/text/footer", {o["locator_id"] for o in ops_of(b)})
        self.assertTrue(any("p1/text/footer" in n and "protected" in n for n in notes), notes)

    def test_idempotent_second_run_is_empty(self):
        facts = copy.deepcopy(self.facts)
        facts["p1/text/names"] = H.text_rec("CLARA & DAVID", "#2f3a2c")
        facts["p1/cell/day"] = H.cell_rec("18")
        facts["p1/cell/day"]["regions"][0]["color"] = "#2f3a2c"
        facts["p1/colour/background"] = H.shape_rec("#f4efe6")
        self.assertEqual(build_ops(self.m, self.st, self.tx, facts), {})

    def test_unknown_locator_and_wrong_type_raise(self):
        facts = copy.deepcopy(self.facts)
        del facts["p1/text/names"]
        with self.assertRaises(OpsError):
            build_ops(self.m, self.st, self.tx, facts)
        facts = copy.deepcopy(self.facts)
        facts["p1/text/names"] = H.rect_rec("MA1")
        with self.assertRaises(OpsError):
            build_ops(self.m, self.st, self.tx, facts)

    def test_original_mismatch_raises(self):
        facts = copy.deepcopy(self.facts)
        facts["p1/text/intro"] = H.text_rec("Somebody edited this by hand")
        self.tx["p1/text/intro"] = "A new intro"
        with self.assertRaises(OpsError) as cm:
            build_ops(self.m, self.st, self.tx, facts)
        self.assertIn("p1/text/intro", str(cm.exception))

    def test_texts_for_unknown_slot_noted(self):
        self.tx["p1/text/ghost"] = "x"
        notes = []
        build_ops(self.m, self.st, self.tx, self.facts, notes=notes)
        self.assertTrue(any("p1/text/ghost" in n for n in notes), notes)

    def test_non_string_text_raises(self):
        self.tx["p1/text/names"] = 5
        with self.assertRaises(OpsError):
            build_ops(self.m, self.st, self.tx, self.facts)

    def test_max_len_is_a_note_not_an_op_change(self):
        self.tx["p1/text/names"] = "X" * 40
        notes = []
        b = build_ops(self.m, self.st, self.tx, self.facts, notes=notes)
        self.assertIn("X" * 40, [o.get("text") for o in ops_of(b)])
        self.assertTrue(any("p1/text/names" in n and "max_len" in n for n in notes), notes)

    def test_line_colour_is_stroke_and_stroke_target(self):
        m = copy.deepcopy(self.m)
        m["slots"] += [
            {"locator": "p1/line/rule", "type": "colour", "role": "background", "asset": None, "personal": False,
             "column_px": None, "max_len": None, "original": None},
            {"locator": "p1/shape/frame", "type": "colour", "role": "background", "asset": None, "personal": False,
             "column_px": None, "max_len": None, "original": None, "target": "stroke"},
        ]
        facts = copy.deepcopy(self.facts)
        facts["p1/line/rule"] = H.line_rec("#292514")
        facts["p1/shape/frame"] = H.shape_rec("#ffffff", stroke="#cabfa9")
        ops = build_ops(m, self.st, self.tx, facts)["PGmini01"]
        self.assertIn({"type": "update_stroke_properties", "locator_id": "p1/line/rule", "color": "#f4efe6"}, ops)
        self.assertIn({"type": "update_stroke_properties", "locator_id": "p1/shape/frame", "color": "#f4efe6"}, ops)

    def test_section_background_colour_is_noted_not_written(self):
        facts = copy.deepcopy(self.facts)
        facts["p1/colour/background"] = H.section_rec()
        notes = []
        b = build_ops(self.m, self.st, self.tx, facts, notes=notes)
        self.assertNotIn("p1/colour/background", {o["locator_id"] for o in ops_of(b)})
        self.assertTrue(any("p1/colour/background" in n and "section" in n for n in notes), notes)

    def test_colour_slot_on_group_raises(self):
        facts = copy.deepcopy(self.facts)
        facts["p1/colour/background"] = {"type": "group", "page": "PGmini01", "section": "SEC1", "parent": None,
                                         "order": 0, "box": [0, 0, 1, 1], "children": []}
        with self.assertRaises(OpsError):
            build_ops(self.m, self.st, self.tx, facts)

    def test_page_missing_from_map_raises(self):
        facts = copy.deepcopy(self.facts)
        facts["p1/text/names"]["page"] = "PGother"
        with self.assertRaises(OpsError):
            build_ops(self.m, self.st, self.tx, facts)

    def test_to_calls_has_page_index(self):
        calls = to_calls(self.m, build_ops(self.m, self.st, self.tx, self.facts))
        self.assertEqual(calls["PGmini01"]["page_index"], 1)
        self.assertTrue(calls["PGmini01"]["operations"])

    def test_inputs_not_mutated(self):
        before = copy.deepcopy((self.m, self.st, self.tx, self.facts))
        build_ops(self.m, self.st, self.tx, self.facts)
        self.assertEqual((self.m, self.st, self.tx, self.facts), before)


class BuildOpsSageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.st, cls.tx = H.load("map_sage.json"), H.load("style_sage.json"), H.load("texts_sage.json")
        cls.orig, cls.sage = H.load("facts_orig.json"), H.load("facts_sage.json")
        cls.notes = []
        cls.batches = build_ops(cls.m, cls.st, cls.tx, cls.orig, notes=cls.notes)
        cls.ops = ops_of(cls.batches)

    def test_replace_text_count_matches_independent_count(self):
        want = sum(1 for s in self.m["slots"] if s["type"] in ("text", "table_cell")
                   and self.orig[s["locator"]]["text"] != self.tx[s["locator"]])
        got = sum(1 for o in self.ops if o["type"] == "replace_text")
        self.assertEqual(got, want)
        self.assertGreater(want, 60)

    def test_every_op_targets_a_slot_and_never_a_protected_one(self):
        slots = {s["locator"] for s in self.m["slots"]}
        locs = {o["locator_id"] for o in self.ops}
        self.assertTrue(locs <= slots)
        self.assertFalse(locs & set(self.m["protected"]))

    def test_only_known_operation_types_and_pages(self):
        self.assertTrue({o["type"] for o in self.ops} <=
                        {"replace_text", "format_text", "recolor_element", "update_stroke_properties"})
        self.assertEqual(set(self.batches), {self.m["pages"][0]["id"], self.m["pages"][1]["id"]})

    def test_second_run_on_the_written_design_is_empty(self):
        self.assertEqual(build_ops(self.m, self.st, self.tx, self.sage), {})

    def test_protected_locator_also_targeted_gets_no_op_and_a_note(self):
        m = copy.deepcopy(self.m)
        target = next(s["locator"] for s in m["slots"] if s["type"] == "text" and s["locator"] in self.tx
                      and self.orig[s["locator"]]["text"] != self.tx[s["locator"]])
        m["protected"].append(target)
        notes = []
        b = build_ops(m, self.st, self.tx, self.orig, notes=notes)
        self.assertNotIn(target, {o["locator_id"] for o in ops_of(b)})
        self.assertTrue(any(target in n and "protected" in n for n in notes), notes)
        self.assertEqual(len(ops_of(b)), len(self.ops) - sum(1 for o in self.ops if o["locator_id"] == target))

    def test_calendar_cells_become_replace_text_on_the_cell_locator(self):
        cell = next(s["locator"] for s in self.m["slots"] if s["type"] == "table_cell"
                    and self.orig[s["locator"]]["text"] != self.tx[s["locator"]])
        self.assertIn({"type": "replace_text", "locator_id": cell, "text": self.tx[cell]}, self.ops)


class ImageOpsTests(unittest.TestCase):
    def setUp(self):
        self.m, self.facts = H.mini_map(), H.mini_facts()
        self.up = {a: {"media_id": f"MA_{a}", "pixel_size": [v["frame"][0] * 2, v["frame"][1] * 2],
                       "alt_text": f"{a} picture"} for a, v in self.m["assets"].items()}

    def test_every_update_fill_is_followed_by_exact_cover_crop(self):
        ops = build_image_ops(self.m, self.up, self.facts)["PGmini01"]
        fills = [o for o in ops if o["type"] == "update_fill"]
        crops = {o["locator_id"]: o for o in ops if o["type"] == "crop_media"}
        self.assertEqual(len(fills), 5)
        self.assertEqual({f["locator_id"] for f in fills}, set(crops))
        last_fill = max(i for i, o in enumerate(ops) if o["type"] == "update_fill")
        first_crop = min(i for i, o in enumerate(ops) if o["type"] == "crop_media")
        self.assertLess(last_fill, first_crop)
        f = next(o for o in fills if o["locator_id"] == "p1/image/hero")
        self.assertEqual((f["asset_type"], f["asset_id"], f["alt_text"]), ("image", "MA_hero", "hero picture"))
        c = crops["p1/image/hero"]          # frame 300x200 (aspect 1.5), asset 2400x1600 (aspect 1.5): the frame
        self.assertEqual((c["left"], c["top"], c["width"], c["height"], c["rotation"]), (0.0, 0.0, 300.0, 200.0, 0))
        s = crops["p1/image/seal"]          # frame 200x200, asset 400x400
        self.assertEqual((s["width"], s["height"]), (200.0, 200.0))

    def test_cover_crop_when_asset_aspect_differs(self):
        self.up["hero"]["pixel_size"] = [3000, 1000]       # frame 300x200: scale 0.2 -> 600x200, left -150
        c = next(o for o in build_image_ops(self.m, self.up, self.facts)["PGmini01"]
                 if o["type"] == "crop_media" and o["locator_id"] == "p1/image/hero")
        self.assertEqual((c["left"], c["top"], c["width"], c["height"]), (-150.0, 0.0, 600.0, 200.0))

    def test_layered_upload_key_and_missing_upload_note(self):
        self.up["envelope:flap"] = {"media_id": "MA_flap", "pixel_size": [2000, 1400], "alt_text": "flap"}
        del self.up["florals"]
        notes = []
        ops = build_image_ops(self.m, self.up, self.facts, notes=notes)["PGmini01"]
        ids = {o["locator_id"]: o["asset_id"] for o in ops if o["type"] == "update_fill"}
        self.assertEqual(ids["p1/image/env-flap"], "MA_flap")
        self.assertEqual(ids["p1/image/env-cover"], "MA_envelope")
        self.assertNotIn("p1/image/florals", ids)
        self.assertTrue(any("p1/image/florals" in n for n in notes), notes)

    def test_protected_image_slot_untouched(self):
        self.m["protected"] = ["p1/image/seal"]
        notes = []
        ops = build_image_ops(self.m, self.up, self.facts, notes=notes)["PGmini01"]
        self.assertNotIn("p1/image/seal", {o["locator_id"] for o in ops})
        self.assertTrue(any("p1/image/seal" in n and "protected" in n for n in notes))

    def test_sage_has_36_fills_and_36_crops(self):
        m, orig = H.load("map_sage.json"), H.load("facts_orig.json")
        up = {a: {"media_id": f"MA_{a}", "pixel_size": [v["frame"][0] * 2, v["frame"][1] * 2], "alt_text": a}
              for a, v in m["assets"].items()}
        ops = [o for p in build_image_ops(m, up, orig).values() for o in p]
        self.assertEqual(sum(o["type"] == "update_fill" for o in ops), 36)
        self.assertEqual(sum(o["type"] == "crop_media" for o in ops), 36)
        for o in ops:
            if o["type"] == "crop_media":      # every crop covers its frame
                rec = orig[o["locator_id"]]
                fw, fh = rec["size"] if rec["type"] == "section" else rec["box"][2:4]
                self.assertLessEqual(o["left"], 1e-3)
                self.assertLessEqual(o["top"], 1e-3)
                self.assertGreaterEqual(o["left"] + o["width"], fw - 1e-3)
                self.assertGreaterEqual(o["top"] + o["height"], fh - 1e-3)


class VerifyBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.st, cls.tx = H.load("map_sage.json"), H.load("style_sage.json"), H.load("texts_sage.json")
        cls.orig, cls.sage = H.load("facts_orig.json"), H.load("facts_sage.json")
        cls.ops = ops_of(build_ops(cls.m, cls.st, cls.tx, cls.orig))

    def after_for(self, ops):
        """orig with the sage record put in for every locator the ops target: a design where the batch worked."""
        after = copy.deepcopy(self.orig)
        for o in ops:
            after[o["locator_id"]] = copy.deepcopy(self.sage[o["locator_id"]])
        return after

    def subset(self, n):
        locs = []
        for o in self.ops:
            if o["locator_id"] not in locs:
                locs.append(o["locator_id"])
        keep = set(locs[:n])
        return [o for o in self.ops if o["locator_id"] in keep]

    def test_clean_batch_has_no_findings(self):          # positive control
        for n in (1, 5, 40):
            ops = self.subset(n)
            self.assertGreater(len(ops), 0)
            self.assertEqual(verify_batch(self.orig, self.after_for(ops), ops), [], n)

    def test_verify_batch_flags_untargeted_change(self):  # control
        ops = self.subset(5)
        after = self.after_for(ops)
        stranger = next(k for k, v in self.orig.items() if v["type"] == "text" and k not in {o["locator_id"] for o in ops})
        after[stranger]["box"][1] += 7
        found = verify_batch(self.orig, after, ops)
        self.assertEqual(len(found), 1, found)
        self.assertIn(stranger, found[0])
        self.assertIn("untargeted", found[0].lower())

    def test_untargeted_added_and_removed_records_flagged(self):
        ops = self.subset(3)
        after = self.after_for(ops)
        after["NEW-ELEMENT"] = copy.deepcopy(next(iter(self.orig.values())))
        victim = next(k for k in self.orig if k not in {o["locator_id"] for o in ops})
        del after[victim]
        found = verify_batch(self.orig, after, ops)
        self.assertTrue(any("NEW-ELEMENT" in f for f in found) and any(victim in f for f in found), found)

    def test_op_not_applied_is_flagged(self):
        ops = self.subset(2)
        found = verify_batch(self.orig, copy.deepcopy(self.orig), ops)
        self.assertTrue(found and any("replace_text" in f or "format_text" in f or "recolor" in f for f in found), found)

    def test_text_format_change_inside_target_flagged(self):
        op = next(o for o in self.ops if o["type"] == "replace_text" and o["locator_id"].count("-") == 2)
        ops = [x for x in self.ops if x["locator_id"] == op["locator_id"]]
        after = self.after_for(ops)
        after[op["locator_id"]]["regions"][0]["fontSize"] += 3
        found = verify_batch(self.orig, after, ops)
        self.assertTrue(any(op["locator_id"] in f for f in found), found)

    def test_unexplained_field_inside_a_target_flagged(self):
        ops = [o for o in self.ops if o["type"] == "recolor_element"][:1]
        after = self.after_for(ops)
        after[ops[0]["locator_id"]]["box"][0] += 5
        self.assertTrue(verify_batch(self.orig, after, ops))

    def test_unsupported_operation_type_fails_closed(self):
        op = {"type": "delete_element", "locator_id": next(iter(self.orig))}
        self.assertTrue(any("delete_element" in f for f in verify_batch(self.orig, copy.deepcopy(self.orig), [op])))

    def test_real_whole_pass_leaves_exactly_the_known_unmapped_changes(self):
        # orig -> sage was done by hand-written plan.py. It also moved the calendar heart and recoloured two swatch
        # rims and the album frame stroke - things the map has no operation for - and verify_batch must say so,
        # and say nothing else (the ~100 other changes are all explained by operations).
        found = verify_batch(self.orig, self.sage, self.ops)
        keys = {re.search(r"change (?:in )?(\S+?):", f).group(1).rsplit("-", 1)[1] for f in found}
        self.assertEqual(keys, {"LBdkLjZVv73Kb0vD", "LBXhXCyn5qK3ScDL", "LBwgQKSyFLpvMjZx", "LBCb5dhKGGjfrwcJ"}, found)

    def test_fill_and_crop_checks(self):
        m, facts = H.mini_map(), H.mini_facts()
        up = {a: {"media_id": f"MA_{a}", "pixel_size": [v["frame"][0] * 2, v["frame"][1] * 2], "alt_text": a}
              for a, v in m["assets"].items()}
        ops = build_image_ops(m, up, facts)["PGmini01"]
        after = copy.deepcopy(facts)
        for o in ops:
            if o["type"] == "update_fill":
                after[o["locator_id"]]["fill"]["media"] = o["asset_id"]
            else:
                after[o["locator_id"]]["fill"]["imageBox"] = [o["top"], o["left"], o["width"], o["height"], 0.0]
        self.assertEqual(verify_batch(facts, after, ops), [])
        after["p1/image/hero"]["fill"]["imageBox"][2] += 11.34        # the bleed update_fill leaves behind
        self.assertTrue(any("p1/image/hero" in f for f in verify_batch(facts, after, ops)))
        after["p1/image/hero"]["fill"]["imageBox"][2] -= 11.34
        after["p1/image/hero"]["fill"]["media"] = "MA_wrong"
        self.assertTrue(any("p1/image/hero" in f for f in verify_batch(facts, after, ops)))


class PortedToolsTests(unittest.TestCase):
    def raw(self):
        return {"design_content": {"pages": [{
            "id": "PG1", "type": "concatenated_fixed", "title": "MAIN", "isEditable": True, "pages": [{
                "id": "S1", "locator_id": "PG1-S1", "dimensions": {"width": 1366, "height": 900},
                "background": {"color": {"type": "solid", "color": "#ffffff"}}, "elements": [
                    {"id": "T1", "locator_id": "PG1-S1-T1", "type": "text", "top": 10, "left": 20, "width": 300,
                     "height": 40, "textRegions": [{"characters": "Hello", "formatting": {
                         "color": "#000000", "fontRef": "F", "fontSize": 20, "textAlign": "center"}}]},
                    {"id": "R1", "locator_id": "PG1-S1-R1", "type": "rect", "top": 0, "left": 0, "width": 50,
                     "height": 50, "fill": {"media": {"mediaId": "MA1", "type": "image",
                                                      "imageBox": {"top": 0, "left": 0, "width": 50, "height": 50}}}},
                    {"id": "TB", "locator_id": "PG1-S1-TB", "type": "table", "top": 200, "left": 0, "width": 70,
                     "height": 60, "rows": [{"cells": [{"id": "A1", "locator_id": "PG1-S1-TB-A1",
                                                         "textRegions": [{"characters": "3", "formatting": {}}]}]}]},
                ]}]}]}}

    def test_facts_dump_records_every_element_and_cell(self):
        facts = F.dump_facts(self.raw())
        self.assertEqual(set(facts), {"PG1-S1", "PG1-S1-T1", "PG1-S1-R1", "PG1-S1-TB", "PG1-S1-TB-A1"})
        self.assertEqual(facts["PG1-S1-T1"]["text"], "Hello")
        self.assertEqual(facts["PG1-S1-R1"]["fill"]["media"], "MA1")
        self.assertEqual(facts["PG1-S1-TB-A1"]["type"], "cell")

    def test_facts_dump_edit_result_and_page_filter(self):
        one = {"document": {"page": self.raw()["design_content"]["pages"][0]}}
        self.assertEqual(set(F.dump_facts(one)), set(F.dump_facts(self.raw())))
        self.assertEqual(F.dump_facts(self.raw(), only="PGnone"), {})

    def test_facts_merge_and_diff(self):
        a = F.dump_facts(self.raw())
        raw2 = self.raw()
        raw2["design_content"]["pages"][0]["pages"][0]["elements"][0]["textRegions"][0]["characters"] = "Bye"
        b = F.dump_facts(raw2)
        lines = F.diff_lines(a, b)
        self.assertTrue(any("PG1-S1-T1" in l and "Hello" in l and "Bye" in l for l in lines), lines)
        self.assertEqual(F.diff_lines(a, a)[-1].split("differing=")[1], "0")
        self.assertEqual(F.merge_facts(a, b)["PG1-S1-T1"]["text"], "Bye")

    def test_facts_rejects_unknown_shape(self):
        with self.assertRaises(ValueError):
            F.dump_facts({"nothing": 1})

    def test_outline_lists_every_element_and_totals(self):
        text = outline.build_outline(self.raw())
        for needle in ("PAGE PG1", "SECTION 1 S1", "text T1", '"Hello"', "rect R1", "MA1", "table TB", "-- totals --"):
            self.assertIn(needle, text)

    def test_probe_diff_reports_changed_lines_and_requires_operations(self):
        raw = self.raw()
        prev = outline.build_outline(raw)
        res = {"status": "ok", "page_index": 1, "edit_operation_results": [
            {"status": "applied", "operation_info": {"type": "replace_text"}}], "document": {"page": copy.deepcopy(
                raw["design_content"]["pages"][0])}}
        res["document"]["page"]["pages"][0]["elements"][0]["textRegions"][0]["characters"] = "Bye"
        lines = probe_diff.probe_diff(prev, res)
        self.assertTrue(any("op1 replace_text: applied" in l for l in lines), lines)
        self.assertTrue(any('"Bye"' in l for l in lines), lines)
        self.assertTrue(any("changed=" in l for l in lines))
        with self.assertRaises(ValueError):
            probe_diff.probe_diff(prev, {"status": "ok"})

    def test_layout_self_test_and_check(self):
        layout.self_test()
        def txt(t, l, w, h):
            return {"type": "text", "page": "P", "section": "S", "box": [t, l, w, h], "opacity": 1, "text": "x",
                    "regions": [{"align": "center", "fontSize": 10, "lh": 1.5}]}
        a = {"P-S-A": txt(0, 0, 100, 20), "P-S-B": txt(30, 0, 100, 20)}
        b = {"P-S-A": txt(0, 10, 100, 45), "P-S-B": txt(30, 0, 100, 20)}
        out = []
        self.assertEqual(layout.check(a, b, out.append), 2)
        self.assertEqual(layout.check(a, a, out.append), 0)


class CliTests(unittest.TestCase):
    def test_geometry_cli(self):
        r = H.run_cli("geometry.py", 433, 600, 866, 1300)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("650", r.stdout)

    def test_ops_cli_build_and_verify(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            args = [H.FX / "map_sage.json", H.FX / "style_sage.json", H.FX / "texts_sage.json",
                    H.FX / "facts_orig.json", d]
            r = H.run_cli("ops.py", "build", *args)
            self.assertEqual(r.returncode, 0, r.stderr)
            files = sorted(d.glob("ops_*.json"))
            self.assertEqual(len(files), 2, r.stdout)
            self.assertTrue((d / "ops_notes.txt").exists())
            self.assertIn(str(d), r.stdout)
            batch = json.loads(files[0].read_text())
            self.assertIn("page_index", batch)
            self.assertTrue(batch["operations"])
            # verify: before == after -> the batch was not applied -> findings -> exit 1, report file printed
            rep = d / "verify.txt"
            r = H.run_cli("ops.py", "verify", H.FX / "facts_orig.json", H.FX / "facts_orig.json", files[0], rep)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertTrue(rep.exists())
            self.assertIn(str(rep), r.stdout)

    def test_cli_usage_error_is_clean(self):
        r = H.run_cli("ops.py")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
