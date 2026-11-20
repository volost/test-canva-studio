import copy
import json
import tempfile
import unittest
from pathlib import Path

from canva.fields import build_fields, page_notes
from canva.final_check import final_check
from canva.protected import protected_changes
from tests import canva_helpers as H


def by_name(res):
    return {r["name"]: r for r in res}


class ProtectedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = H.load("map_sage.json")
        cls.orig, cls.sage = H.load("facts_orig.json"), H.load("facts_sage.json")

    def test_unchanged_is_clean(self):                    # positive control
        self.assertEqual(protected_changes(self.orig, copy.deepcopy(self.orig), self.m), [])

    def test_sage_pass_left_every_protected_element_alone(self):
        self.assertEqual(protected_changes(self.orig, self.sage, self.m), [])

    def test_protected_change_detected(self):             # control: synthetic media-id change
        now = copy.deepcopy(self.orig)
        form_group = self.m["protected"][3]
        child = next(k for k, v in now.items() if k.startswith(form_group + "-") and v["type"] == "rect")
        now[child]["fill"]["media"] = "MAXXXXXXXXX"
        # the child is an image slot (overlay) -> not covered through its protected group
        self.assertEqual(protected_changes(self.orig, now, self.m), [])
        m2 = copy.deepcopy(self.m)
        m2["slots"] = [s for s in m2["slots"] if s["locator"] != child]
        found = protected_changes(self.orig, now, m2)
        self.assertEqual(len(found), 1, found)
        self.assertIn(child, found[0])
        self.assertIn("MAXXXXXXXXX", found[0])

    def test_envelope_layer_inside_protected_group_keeps_its_frame(self):
        # the overlay children are image slots: their picture may change, their frame may not
        group = self.m["protected"][3]
        child = next(k for k, v in self.orig.items() if k.startswith(group + "-") and v["type"] == "rect")
        self.assertIn(child, {s["locator"] for s in self.m["slots"]})
        media_only = copy.deepcopy(self.orig)
        media_only[child]["fill"]["media"] = "MANEW"
        media_only[child]["fill"]["imageBox"] = [1.0, 2.0, 3.0, 4.0, 0.0]
        self.assertEqual(protected_changes(self.orig, media_only, self.m), [])
        for name, mutate in {
            "moved": lambda n: n[child]["box"].__setitem__(0, n[child]["box"][0] + 5.0),
            "resized": lambda n: n[child]["box"].__setitem__(2, n[child]["box"][2] - 5.0),
            "rotated": lambda n: n[child].__setitem__("rotation", 2.0),
            "faded": lambda n: n[child].__setitem__("opacity", 0.5),
            "unlocked": lambda n: n[child].__setitem__("locked", not n[child]["locked"]),
            "reordered": lambda n: n[child].__setitem__("order", 9),
        }.items():
            now = copy.deepcopy(self.orig)
            mutate(now)
            found = protected_changes(self.orig, now, self.m)
            self.assertEqual(len(found), 1, (name, found))
            self.assertIn(child, found[0])
            self.assertIn("frame only", found[0])

    def test_calendar_cells_of_a_protected_table_may_be_written_but_the_table_may_not_move(self):
        table = next(k for k, v in self.orig.items() if v["type"] == "table")
        m = copy.deepcopy(self.m)
        m["protected"].append(table)
        self.assertEqual(protected_changes(self.orig, self.sage, m), [])        # cell texts changed: allowed
        moved = copy.deepcopy(self.sage)
        moved[table]["box"][1] += 4.0
        self.assertEqual(len(protected_changes(self.orig, moved, m)), 1)

    def test_each_kind_of_change_is_found(self):
        mm = H.mini_map()
        mm["protected"] = ["p1/text/footer", "p1/image/hero"]
        orig = H.mini_facts()
        cases = {
            "media": lambda n: n["p1/image/hero"]["fill"].__setitem__("media", "MAZ"),
            "position": lambda n: n["p1/image/hero"]["box"].__setitem__(0, 999.0),
            "size": lambda n: n["p1/image/hero"]["box"].__setitem__(2, 301.0),
            "text": lambda n: n["p1/text/footer"].update(text="Hacked"),
            "layer order": lambda n: n["p1/image/hero"].__setitem__("order", 7),
            "rotation": lambda n: n["p1/image/hero"].__setitem__("rotation", 3.0),
            "removed": lambda n: n.pop("p1/text/footer"),
        }
        for name, mutate in cases.items():
            now = copy.deepcopy(orig)
            mutate(now)
            found = protected_changes(orig, now, mm)
            self.assertEqual(len(found), 1, (name, found))
        self.assertEqual(protected_changes(orig, copy.deepcopy(orig), mm), [])

    def test_section_layer_order_change_found(self):
        mm = H.mini_map()
        mm["protected"] = ["p1/image/hero"]
        orig = H.mini_facts()
        orig["PGmini01-SEC1"] = H.section_rec(elements=["a", "b", "c"])
        now = copy.deepcopy(orig)
        now["PGmini01-SEC1"]["elements"] = ["b", "a", "c"]
        found = protected_changes(orig, now, mm)
        self.assertTrue(any("order" in f.lower() for f in found), found)

    def test_protected_locator_missing_from_original_reported(self):
        mm = H.mini_map()
        mm["protected"] = ["p1/text/ghost"]
        found = protected_changes(H.mini_facts(), H.mini_facts(), mm)
        self.assertTrue(any("p1/text/ghost" in f for f in found), found)

    def test_inputs_not_mutated(self):
        o, n = copy.deepcopy(self.orig), copy.deepcopy(self.sage)
        protected_changes(o, n, self.m)
        self.assertEqual((o, n), (self.orig, self.sage))


class FinalCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m, cls.st, cls.tx = H.load("map_sage.json"), H.load("style_sage.json"), H.load("texts_sage.json")
        cls.orig, cls.sage = H.load("facts_orig.json"), H.load("facts_sage.json")

    def test_result_shape(self):
        res = final_check(self.orig, self.sage, self.m, self.tx, style=self.st)
        for r in res:
            self.assertEqual(set(r), {"name", "passed", "detail"})
            self.assertIsInstance(r["passed"], bool)
            self.assertIsInstance(r["detail"], str)
        self.assertEqual(len({r["name"] for r in res}), len(res))

    def test_final_check_fails_on_original(self):         # the built-in control
        res = by_name(final_check(self.orig, self.orig, self.m, self.tx, style=self.st))
        self.assertFalse(res["texts"]["passed"], res["texts"])
        self.assertFalse(res["colours"]["passed"], res["colours"])
        self.assertFalse(res["leftovers"]["passed"], res["leftovers"])
        self.assertTrue(res["control"]["passed"], res["control"])      # the checker showed it can fail

    def test_final_check_passes_on_the_written_design(self):
        res = final_check(self.orig, self.sage, self.m, self.tx, style=self.st)
        failed = [r for r in res if not r["passed"]]
        self.assertEqual(failed, [], failed)
        self.assertEqual({"texts", "formatting", "colours", "protected", "structure", "leftovers", "coverage", "control"},
                         {r["name"] for r in res})

    def test_without_style_colours_are_not_claimed(self):
        res = by_name(final_check(self.orig, self.sage, self.m, self.tx))
        self.assertNotIn("colours", res)
        self.assertTrue(all(r["passed"] for r in res.values()))

    def test_each_check_fails_on_its_own_bad_input(self):
        def run(mutate):
            now = copy.deepcopy(self.sage)
            mutate(now)
            return by_name(final_check(self.orig, now, self.m, self.tx, style=self.st))
        text_key = next(s["locator"] for s in self.m["slots"] if s["type"] == "text" and s["role"] == "heading")
        cell_key = next(s["locator"] for s in self.m["slots"] if s["type"] == "table_cell")
        r = run(lambda n: n[text_key].update(text="WRONG"))
        self.assertFalse(r["texts"]["passed"])
        self.assertIn(text_key, r["texts"]["detail"])
        r = run(lambda n: n[cell_key].update(text="99"))
        self.assertFalse(r["texts"]["passed"])
        r = run(lambda n: n[text_key]["regions"][0].__setitem__("fontSize", 1.0))
        self.assertFalse(r["formatting"]["passed"])
        r = run(lambda n: n[text_key]["regions"][0].__setitem__("color", "#000000"))
        self.assertFalse(r["colours"]["passed"])
        r = run(lambda n: n.pop(text_key))
        self.assertFalse(r["structure"]["passed"])
        r = run(lambda n: n.__setitem__("EXTRA", copy.deepcopy(n[text_key])))
        self.assertFalse(r["structure"]["passed"])
        prot = self.m["protected"][0]
        r = run(lambda n: n[prot]["box"].__setitem__(0, n[prot]["box"][0] + 10))
        self.assertFalse(r["protected"]["passed"])
        pers = next(s for s in self.m["slots"] if s["type"] == "text" and s["personal"] and len(s["original"].strip()) >= 4)
        r = run(lambda n: n[text_key].update(text="hello " + pers["original"].strip()))
        self.assertFalse(r["leftovers"]["passed"])

    def test_colour_slot_checked_against_palette(self):
        slot = next(s for s in self.m["slots"] if s["type"] == "colour" and self.orig[s["locator"]]["type"] == "shape")
        now = copy.deepcopy(self.sage)
        now[slot["locator"]]["paths"][0]["fill"]["color"] = "#123456"
        res = by_name(final_check(self.orig, now, self.m, self.tx, style=self.st))
        self.assertFalse(res["colours"]["passed"])
        self.assertIn(slot["locator"], res["colours"]["detail"])

    def test_control_fails_when_texts_equal_the_original(self):
        same = {k: self.orig[k]["text"] for k in self.tx}
        res = by_name(final_check(self.orig, self.orig, self.m, same, style=self.st))
        self.assertFalse(res["control"]["passed"])

    def test_images_check_is_opt_in_and_honest(self):
        res = by_name(final_check(self.orig, self.sage, self.m, self.tx, style=self.st, images=True))
        self.assertFalse(res["images"]["passed"])             # sage facts are the pass without images
        self.assertIn("not replaced", res["images"]["detail"])

    def test_images_check_passes_on_a_synthetic_placed_design(self):
        m, facts = H.mini_map(), H.mini_facts()
        now = copy.deepcopy(facts)
        for loc, rec in now.items():
            if "/image/" in loc:
                w, h = rec["box"][2:4]
                rec["fill"]["media"] = "MANEW_" + loc[-4:]
                rec["fill"]["imageBox"] = [0.0, 0.0, w, h, 0.0]
        m["assets"]["hero"]["frame"] = [300, 200]
        m["assets"]["envelope"]["frame"] = [300, 200]
        m["assets"]["florals"]["frame"] = [300, 200]
        m["assets"]["seal"]["frame"] = [200, 200]
        res = by_name(final_check(facts, now, m, H.mini_texts(), images=True, control=False))
        self.assertTrue(res["images"]["passed"], res["images"])
        now["p1/image/hero"]["fill"]["imageBox"][2] += 11.34
        res = by_name(final_check(facts, now, m, H.mini_texts(), images=True, control=False))
        self.assertFalse(res["images"]["passed"])
        self.assertIn("p1/image/hero", res["images"]["detail"])

    def test_incomplete_map_fails_coverage_even_when_everything_else_is_green(self):
        # reviewer's scenario: drop a unique personal slot and put the skeleton's wording back into that element
        m = copy.deepcopy(self.m)
        victim = next(s for s in m["slots"] if s["type"] == "text" and s["personal"] and s["original"] == "Villa Erba")
        m["slots"].remove(victim)
        now = copy.deepcopy(self.sage)
        now[victim["locator"]] = copy.deepcopy(self.orig[victim["locator"]])
        res = by_name(final_check(self.orig, now, m, self.tx, style=self.st))
        self.assertFalse(res["coverage"]["passed"])
        self.assertIn(victim["locator"], res["coverage"]["detail"])
        self.assertFalse(res["leftovers"]["passed"] and res["texts"]["passed"] and res["colours"]["passed"]
                         and res["formatting"]["passed"] and res["structure"]["passed"] and res["protected"]["passed"]
                         and res["coverage"]["passed"])
        # the same map with the element listed in `keep` is complete again (and then its wording may stay)
        m["keep"] = [victim["locator"]]
        res = by_name(final_check(self.orig, self.sage, m, self.tx, style=self.st))
        self.assertTrue(res["coverage"]["passed"], res["coverage"])

    def test_map_sage_is_complete_with_an_empty_keep(self):
        self.assertEqual(self.m["keep"], [])
        res = by_name(final_check(self.orig, self.sage, self.m, self.tx, style=self.st))
        self.assertTrue(res["coverage"]["passed"], res["coverage"])
        self.assertIn("117", res["coverage"]["detail"])

    def test_coverage_accepts_protected_and_keep_and_flags_unknown_keep(self):
        m, facts = H.mini_map(), H.mini_facts()
        facts["p1/text/extra"] = H.text_rec("x")
        res = by_name(final_check(facts, facts, m, H.mini_texts(), control=False))
        self.assertFalse(res["coverage"]["passed"])
        m["keep"] = ["p1/text/extra"]
        res = by_name(final_check(facts, facts, m, H.mini_texts(), control=False))
        self.assertTrue(res["coverage"]["passed"], res["coverage"])          # footer is protected, extra is kept
        m["keep"].append("p1/text/ghost")
        res = by_name(final_check(facts, facts, m, H.mini_texts(), control=False))
        self.assertFalse(res["coverage"]["passed"])
        self.assertIn("ghost", res["coverage"]["detail"])

    def test_colours_detail_lists_the_roles_kept_as_in_the_skeleton(self):
        st = copy.deepcopy(self.st)
        del st["colour_roles"]["script"]
        res = by_name(final_check(self.orig, self.sage, self.m, self.tx, style=st))
        self.assertIn("kept as in the skeleton", res["colours"]["detail"])
        self.assertIn("script (", res["colours"]["detail"])
        full = by_name(final_check(self.orig, self.sage, self.m, self.tx, style=self.st))["colours"]["detail"]
        self.assertIn("heading_on_photo (", full)

    def test_images_frame_must_equal_the_original(self):
        m, facts = H.mini_map(), H.mini_facts()
        for a in ("hero", "envelope", "florals"):
            m["assets"][a]["frame"] = [300, 200]
        m["assets"]["seal"]["frame"] = [200, 200]
        now = copy.deepcopy(facts)
        for loc, rec in now.items():
            if "/image/" in loc:
                rec["fill"]["media"] = "MANEW_" + loc[-4:]
        now["p1/image/hero"]["box"][0] += 5.0
        res = by_name(final_check(facts, now, m, H.mini_texts(), images=True, control=False))
        self.assertFalse(res["images"]["passed"])
        self.assertIn("frame changed", res["images"]["detail"])

    def test_control_runs_a_probe_per_check_and_fails_if_a_check_goes_blind(self):
        from unittest import mock
        import canva.final_check as fc
        res = by_name(final_check(self.orig, self.sage, self.m, self.tx, style=self.st, images=True))
        self.assertIn("9/9 synthetic probes behave", res["control"]["detail"])
        self.assertTrue(res["control"]["passed"])
        blind = {"name": "x", "passed": True, "detail": ""}
        for fn in ("_check_formatting", "_check_structure", "_check_colours", "_check_leftovers", "_check_images",
                   "_check_coverage"):
            with mock.patch.object(fc, fn, return_value=blind):
                res = by_name(final_check(self.orig, self.sage, self.m, self.tx, style=self.st, images=True))
            self.assertFalse(res["control"]["passed"], fn)
        with mock.patch.object(fc, "protected_changes", return_value=[]), \
                mock.patch.object(fc, "run_control", return_value=(False, "blind")):
            res = by_name(final_check(self.orig, self.sage, self.m, self.tx, style=self.st))
        self.assertFalse(res["control"]["passed"])

    def test_inputs_not_mutated(self):
        o, n = copy.deepcopy(self.orig), copy.deepcopy(self.sage)
        final_check(o, n, self.m, self.tx, style=self.st)
        self.assertEqual((o, n), (self.orig, self.sage))


class FieldsTests(unittest.TestCase):
    def test_fields_cover_every_personal_slot(self):
        for m, tx in ((H.load("map_sage.json"), H.load("texts_sage.json")), (H.mini_map(), H.mini_texts())):
            f = build_fields(m, tx)
            want = {s["locator"] for s in m["slots"] if s["personal"]}
            got = [x["locator_id"] for x in f["fields"]]
            self.assertEqual(set(got), want)
            self.assertEqual(len(got), len(set(got)))
            keys = [x["key"] for x in f["fields"]]
            self.assertEqual(len(keys), len(set(keys)))
            self.assertEqual(f["counts"]["fields"], len(want))
            for x in f["fields"]:
                for k in ("key", "label", "kind", "locator_id", "page", "role", "sample_value", "how_to_edit", "max_len"):
                    self.assertIn(k, x)
            json.dumps(f, ensure_ascii=False)

    def test_sample_value_comes_from_texts_else_original(self):
        f = {x["locator_id"]: x for x in build_fields(H.mini_map(), H.mini_texts())["fields"]}
        self.assertEqual(f["p1/text/names"]["sample_value"], "CLARA & DAVID")
        self.assertEqual(f["p1/cell/day"]["sample_value"], "18")
        tx = H.mini_texts()
        del tx["p1/text/names"]
        m = H.mini_map()
        m["slots"][6]["original"] = "OLD NAMES"
        f = {x["locator_id"]: x for x in build_fields(m, tx)["fields"]}
        self.assertEqual(f["p1/text/names"]["sample_value"], "OLD NAMES")

    def test_fields_list_the_protected_elements(self):
        m = H.load("map_sage.json")
        self.assertEqual(build_fields(m, H.load("texts_sage.json"))["do_not_touch"], m["protected"])

    def test_page_notes_one_per_page_english_and_bounded(self):
        m, st = H.load("map_sage.json"), H.load("style_sage.json")
        notes = page_notes(m, style=st)
        self.assertEqual(set(notes), {p["id"] for p in m["pages"]})
        for pid, text in notes.items():
            self.assertIsInstance(text, str)
            self.assertLessEqual(len(text), 5000)
            self.assertTrue(text.strip())
        main = notes["PBw4SHZw3cbPHqdd"]
        self.assertIn("Cormorant Garamond", main)              # fonts to swap by hand
        self.assertIn("Edit", main)
        n_personal = sum(1 for s in m["slots"] if s["personal"] and "PBw4SHZw3cbPHqdd" in s["locator"])
        self.assertGreater(n_personal, 10)
        self.assertIn("calendar", main.lower())

    def test_page_notes_never_quote_the_skeletons_old_wording(self):
        m, st, tx = H.load("map_sage.json"), H.load("style_sage.json"), H.load("texts_sage.json")
        orig_words = {s["original"].strip() for s in m["slots"] if s["personal"] and s["original"]}
        self.assertIn("DAVID", orig_words)
        without = page_notes(m, style=st)["PBw4SHZw3cbPHqdd"]
        for w in orig_words:
            self.assertNotIn(f'"{w}"', without)
        self.assertIn("- heading on photo #1 (max 13 characters)", without)
        self.assertIn("- heading on photo #2 (max 13 characters)", without)              # lines of one role are told apart
        withv = page_notes(m, style=st, texts=tx)["PBw4SHZw3cbPHqdd"]
        self.assertIn('"THEO"', withv)
        self.assertNotIn("DAVID", withv)
        lines = withv.split("\n")
        i = lines.index("Edit these fields:")
        self.assertTrue(all(l.startswith("- ") for l in lines[i + 1:i + 20]), lines[i:i + 20])   # no value splits a line

    def test_page_notes_without_style_and_symbolic_locators(self):
        notes = page_notes(H.mini_map())
        self.assertEqual(list(notes), ["PGmini01"])
        self.assertIn("names", notes["PGmini01"].lower())
        self.assertIn("max 20", notes["PGmini01"].lower())

    def test_page_notes_truncate_instead_of_exceeding_the_limit(self):
        m = H.mini_map()
        for i in range(400):
            m["slots"].append({"locator": f"p1/text/extra{i}", "type": "text", "role": "body", "asset": None,
                               "personal": True, "column_px": 100, "max_len": 30, "original": None})
        text = page_notes(m)["PGmini01"]
        self.assertLessEqual(len(text), 5000)
        self.assertIn("fields.json", text)

    def test_unresolvable_page_raises(self):
        m = H.mini_map()
        m["slots"][6]["locator"] = "zzz/text/names"
        with self.assertRaises(ValueError):
            page_notes(m)
        with self.assertRaises(ValueError):
            build_fields(m, H.mini_texts())


class CliTests(unittest.TestCase):
    def test_final_check_cli_runs_control_and_reports(self):
        with tempfile.TemporaryDirectory() as d:
            rep = Path(d) / "final.txt"
            r = H.run_cli("final_check.py", H.FX / "map_sage.json", H.FX / "texts_sage.json",
                          H.FX / "facts_orig.json", H.FX / "facts_sage.json", rep,
                          "--style", H.FX / "style_sage.json")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("control", r.stdout)
            self.assertIn(str(rep), r.stdout)
            self.assertTrue(rep.exists())
            r = H.run_cli("final_check.py", H.FX / "map_sage.json", H.FX / "texts_sage.json",
                          H.FX / "facts_orig.json", H.FX / "facts_orig.json", rep,
                          "--style", H.FX / "style_sage.json")
            self.assertEqual(r.returncode, 1)                 # the untouched original fails

    def test_protected_cli(self):
        with tempfile.TemporaryDirectory() as d:
            rep = Path(d) / "prot.txt"
            r = H.run_cli("protected.py", H.FX / "map_sage.json", H.FX / "facts_orig.json",
                          H.FX / "facts_sage.json", rep)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("control ok", r.stdout)
            self.assertIn(str(rep), r.stdout)

    def test_fields_cli(self):
        with tempfile.TemporaryDirectory() as d:
            r = H.run_cli("fields.py", H.FX / "map_sage.json", H.FX / "texts_sage.json", d,
                          "--style", H.FX / "style_sage.json")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            f = json.loads((Path(d) / "fields.json").read_text())
            n = json.loads((Path(d) / "page_notes.json").read_text())
            self.assertEqual(f["counts"]["fields"], sum(1 for x in H.load("map_sage.json")["slots"] if x["personal"]))
            self.assertEqual(len(n), 3)


if __name__ == "__main__":
    unittest.main()
