"""The /studio skill files (studio/skill/studio): structure checks on the markdown, and a run of the shipped
snippets (the precheck that refuses the purchased original, the result writer, the copy-id writer, the map and
media checks) against temporary data. Standard library only; no network; no Canva."""
import dataclasses
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.config import load_config
from app.guard import JOB_TYPES
from app.store import create_template, read_json, write_json_atomic

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "studio"
FX = Path(__file__).parent / "fixtures"
ORIGINAL = "DAHarqlqips"
FILES = ["SKILL.md"] + [f"jobs/{t}.md" for t in ("map_skeleton", "style_directions", "write_texts", "apply_canva", "verify")]
PATH_RE = re.compile(r"(?<![\w/.])((?:canva|app)/[\w./-]+\.(?:py|js))")
SNIPPET_RE = re.compile(r"\$PY -I - (.*?) <<'PYEOF'\n(.*?)\nPYEOF", re.S)


def read(rel: str) -> str:
    return (SKILL / rel).read_text(encoding="utf-8")


def missing_paths(text: str, root: Path) -> tuple[list, int]:
    """(mentioned canva/... or app/... source paths that do not exist under root, number of mentions)."""
    found = sorted(set(PATH_RE.findall(text)))
    return [p for p in found if not (root / p).is_file()], len(found)


def has_all(text: str, *patterns: str) -> bool:
    return all(re.search(p, text, re.I) for p in patterns)


def placeholders(text: str) -> list:
    return re.findall(r"\b(?:TODO|TBD)\b", text)


def frontmatter(text: str) -> dict:
    mt = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not mt:
        return {}
    return dict(line.split(": ", 1) for line in mt.group(1).splitlines() if ": " in line)


def snippets() -> dict:
    """{name: code} of every `$PY -I - ... <<'PYEOF'` block in the six files (the name is the code's first line)."""
    out = {}
    for rel in FILES:
        for _, code in SNIPPET_RE.findall(read(rel)):
            name = re.match(r"# snippet: (\w+)\n", code).group(1)
            assert name not in out, f"snippet {name} appears twice"
            out[name] = code
    return out


class StructureTests(unittest.TestCase):
    def test_all_six_files_exist(self):
        for rel in FILES:
            self.assertTrue((SKILL / rel).is_file(), rel)

    def test_job_instruction_files_match_job_types_exactly(self):
        stems = {p.stem for p in (SKILL / "jobs").glob("*.md")}
        self.assertEqual(stems, set(JOB_TYPES))

    def test_frontmatter(self):
        fm = frontmatter(read("SKILL.md"))
        self.assertEqual(fm.get("name"), "studio")
        self.assertTrue(fm.get("description", "").strip())
        self.assertEqual(frontmatter("no front matter here"), {})                     # control

    def test_mentioned_source_paths_exist(self):
        total = 0
        for rel in FILES:
            bad, n = missing_paths(read(rel), ROOT)
            total += n
            self.assertEqual(bad, [], f"{rel} mentions files that do not exist")
        self.assertGreaterEqual(total, 10, "the path check examined almost nothing")

    def test_path_check_control(self):
        """The same function must detect a fake path and accept a real one."""
        bad, n = missing_paths("run `python -I canva/definitely_not_here.py` and `app/store.py`", ROOT)
        self.assertEqual(bad, ["canva/definitely_not_here.py"])
        self.assertEqual(n, 2)
        self.assertEqual(missing_paths("`python -I canva/ops.py build`", ROOT), ([], 1))
        self.assertEqual(missing_paths("the folder /Users/x/GitRepos/canva/studio is not a path of a script", ROOT)[1], 0)

    def test_protected_id_and_publish_rule_in_the_canva_instructions(self):
        for rel in ("SKILL.md", "jobs/apply_canva.md", "jobs/verify.md"):
            text = read(rel)
            self.assertIn(ORIGINAL, text, rel)
            self.assertTrue(has_all(text, r"never publish"), rel)
        self.assertFalse(has_all("nothing about it", ORIGINAL), "control: the id check must be able to fail")
        self.assertFalse(has_all("we publish everything", r"never publish"))

    def test_limits_block_is_verbatim_in_every_canva_instruction(self):
        skill = read("SKILL.md")
        block = skill[skill.index("1. Edit ONLY"):skill.index("## 1. Procedure")].rstrip()
        for rel in ("jobs/apply_canva.md", "jobs/verify.md", "jobs/map_skeleton.md"):
            self.assertIn(block, read(rel), rel)
        self.assertNotIn(block, read("jobs/write_texts.md"))                           # control: the check can say no

    def test_no_placeholders(self):
        for rel in FILES:
            self.assertEqual(placeholders(read(rel)), [], rel)
        self.assertEqual(placeholders("a TODO item"), ["TODO"])                        # control
        self.assertEqual(placeholders("a TBD item and TODOS"), ["TBD"])

    def test_every_snippet_is_present_once_and_no_marker_is_left(self):
        found = snippets()
        self.assertGreaterEqual(len(found), 16)
        for name in ("precheck", "write_result", "set_copy_id", "map_check", "old_media", "marker", "calendar_cells",
                     "adjust_sizes", "reset_texts"):
            self.assertIn(name, found)
        for rel in FILES:
            self.assertNotIn("@@", read(rel), rel)


class SnippetTests(unittest.TestCase):
    """The shipped code, run the way the instructions run it: `python -I - <args>` with the code on stdin."""

    @classmethod
    def setUpClass(cls):
        cls.code = snippets()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        shutil.copy(FX / "config.json", self.root / "config.json")
        self.cfg = dataclasses.replace(load_config(self.root / "config.json"), root=self.root)
        (self.root / "skeletons" / "sk").mkdir(parents=True)
        write_json_atomic(self.root / "skeletons" / "sk" / "map.json", {"skeleton": "sk", "design_id": "DASKEL0001"})
        self.tdir = create_template(self.cfg, "tpl", "sk")
        write_json_atomic(self.tdir / "texts.json", {"a": "b"})

    def run_snippet(self, name, *args):
        return subprocess.run([sys.executable, "-I", "-", *map(str, args)], input=self.code[name], text=True,
                              capture_output=True, cwd="/")

    def set_state(self, approved=("style", "images", "texts"), waiting=None, copy_id=None):
        st = read_json(self.tdir / "state.json")
        for s in st["steps"]:
            st["steps"][s]["status"] = "approved" if s in approved else "draft"
        if waiting:
            st["steps"][waiting]["status"] = "waiting_claude"
        st["canva_copy_id"] = copy_id
        write_json_atomic(self.tdir / "state.json", st)

    def job(self, jtype, target, jid, **kw):
        job = {"id": jid, "type": jtype, "template": "tpl", "skeleton": "sk", "target_design_id": target,
               "created_utc": "2026-11-20T00:00:00Z", "inputs": {}, "limits": ["Без публікації."]}
        job.update(kw)
        path = self.root / "jobs" / "running" / f"{jid}.json"
        write_json_atomic(path, job)
        return path

    def precheck(self, path):
        r = self.run_snippet("precheck", ROOT, self.root, path)
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        return r.returncode, out

    # ---- the protected original is refused with zero Canva work ------------------------------------------
    def test_verify_of_the_purchased_original_is_refused(self):
        self.set_state(approved=("style", "images", "texts", "apply"), waiting="verify", copy_id="DACOPY0001")
        good = self.job("verify", "DACOPY0001", "20261120T000001Z-verify")
        code, out = self.precheck(good)                                                # control: the good job passes
        self.assertEqual((code, out["ok"], out["reasons"]), (0, True, []))
        for target in (ORIGINAL, f"  {ORIGINAL.lower()} ", "DASKEL0001", "DAOTHER0001"):
            code, out = self.precheck(self.job("verify", target, "20261120T000002Z-verify"))
            self.assertEqual(code, 1, target)
            self.assertFalse(out["ok"], target)
        code, out = self.precheck(self.job("verify", ORIGINAL, "20261120T000003Z-verify"))
        self.assertIn("protected original", " ".join(out["reasons"]))

    def test_precheck_refuses_outdated_or_malformed_jobs(self):
        self.set_state(waiting="apply")
        ok = {"texts": {"a": "b"}, "chosen": {}}
        self.assertEqual(self.precheck(self.job("apply_canva", None, "20261120T000004Z-apply_canva", inputs=ok))[0], 0)
        cases = [
            self.job("apply_canva", None, "20261120T000005Z-apply_canva", inputs={"texts": {"a": "other"}, "chosen": {}}),
            self.job("apply_canva", ORIGINAL, "20261120T000006Z-apply_canva", inputs=ok),
            self.job("apply_canva", None, "20261120T000007Z-apply_canva", inputs=ok, limits=[]),
            self.job("apply_canva", None, "20261120T000008Z-apply_canva", inputs=ok, id="another-id"),
        ]
        for path in cases:
            self.assertEqual(self.precheck(path)[0], 1, path.name)
        self.set_state(approved=("style", "images"), waiting="apply")                  # texts reopened by the owner
        self.assertEqual(self.precheck(self.job("apply_canva", None, "20261120T000009Z-apply_canva", inputs=ok))[0], 1)
        corrupt = self.root / "jobs" / "running" / "20261120T000010Z-verify.json"
        corrupt.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.precheck(corrupt)[0], 1)

    def test_map_skeleton_may_not_read_the_original(self):
        write_json_atomic(self.root / "skeletons" / "sk" / "skeleton.json", {"name": "sk", "design_id": "DASKEL0001"})
        base = dict(template=None)
        self.assertEqual(self.precheck(self.job("map_skeleton", None, "20261120T000011Z-map_skeleton",
                                                inputs={"design_id": "DASKEL0001"}, **base))[0], 0)
        self.assertEqual(self.precheck(self.job("map_skeleton", None, "20261120T000012Z-map_skeleton",
                                                inputs={"design_id": ORIGINAL}, **base))[0], 1)


    def test_interrupted_first_apply_fails_the_precheck_by_design(self):
        """target null + a copy id already in state.json: check_job demands target == copy id, so the job is filed as
        failed and the owner re-requests it (SKILL.md 1.1). A copy id only in the notes (state null) passes."""
        ok = {"texts": {"a": "b"}, "chosen": {}}
        self.set_state(waiting="apply", copy_id="DANEWCOPY1")
        code, out = self.precheck(self.job("apply_canva", None, "20261120T000014Z-apply_canva", inputs=ok))
        self.assertEqual(code, 1)
        self.assertIn("own copy", " ".join(out["reasons"]))
        code, out = self.precheck(self.job("apply_canva", "DANEWCOPY1", "20261120T000015Z-apply_canva", inputs=ok))
        self.assertEqual((code, out["ok"]), (0, True))                                 # the re-requested job targets the copy
        self.set_state(waiting="apply")
        self.assertEqual(self.precheck(self.job("apply_canva", None, "20261120T000016Z-apply_canva", inputs=ok))[0], 0)

    def test_adjust_sizes_resets_only_declared_changes(self):
        orig = json.loads((FX / "facts_orig.json").read_text(encoding="utf-8"))
        loc = next(k for k, v in orig.items() if v["type"] == "text" and v["regions"])
        changed = json.loads(json.dumps(orig))
        changed[loc]["regions"][0]["fontSize"] += 2
        (self.root / "changed.json").write_text(json.dumps(changed), encoding="utf-8")
        (self.root / "declared.json").write_text(json.dumps([loc]), encoding="utf-8")
        (self.root / "none.json").write_text("[]", encoding="utf-8")
        out = self.root / "adjusted.json"
        r = self.run_snippet("adjust_sizes", FX / "facts_orig.json", self.root / "changed.json", self.root / "declared.json", out)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))[loc]["regions"][0]["fontSize"],
                         orig[loc]["regions"][0]["fontSize"])
        r = self.run_snippet("adjust_sizes", FX / "facts_orig.json", self.root / "changed.json", self.root / "none.json", out)
        self.assertEqual(r.returncode, 1, "control: an undeclared size change must fail")
        self.assertIn(loc, r.stdout)

    def test_reset_texts_lets_ops_build_pass_on_a_design_with_earlier_texts(self):
        m = json.loads((FX / "map_sage.json").read_text(encoding="utf-8"))
        facts = json.loads((FX / "facts_orig.json").read_text(encoding="utf-8"))
        loc = next(s["locator"] for s in m["slots"] if s["type"] == "text" and s.get("original"))
        facts[loc]["text"] = "SOMETHING WRITTEN EARLIER"
        facts[loc]["regions"][0]["chars"] = "SOMETHING WRITTEN EARLIER"
        (self.root / "cur.json").write_text(json.dumps(facts), encoding="utf-8")
        args = [FX / "map_sage.json", FX / "style_sage.json", FX / "texts_sage.json"]

        def build(facts_file, out):
            return subprocess.run([sys.executable, "-I", "canva/ops.py", "build", *map(str, args), str(facts_file), str(out)],
                                  capture_output=True, text=True, cwd=ROOT)
        bad = build(self.root / "cur.json", self.root / "o1")
        self.assertNotEqual(bad.returncode, 0)                                         # the limitation the workaround exists for
        self.assertIn("the design holds", bad.stdout)
        r = self.run_snippet("reset_texts", FX / "map_sage.json", self.root / "cur.json", FX / "facts_orig.json", self.root / "fb.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        good = build(self.root / "fb.json", self.root / "o2")
        self.assertEqual(good.returncode, 0, good.stdout)
        ops = [op for f in (self.root / "o2").glob("ops_P*.json") for op in json.loads(f.read_text(encoding="utf-8"))["operations"]]
        self.assertTrue(any(o["type"] == "replace_text" and o["locator_id"] == loc for o in ops))

    # ---- result writer and copy id ------------------------------------------------------------------------
    def draft(self, **kw):
        d = {"status": "done", "summary": "Готово", "outputs": {"canva_copy_id": "DANEWCOPY1"},
             "checks": [{"name": "x", "passed": True, "detail": "ok"}]}
        d.update(kw)
        path = self.root / "draft.json"
        path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return path

    def test_write_result_enforces_the_copy_id_rule(self):
        self.set_state(waiting="apply")
        job = self.job("apply_canva", None, "20261120T000013Z-apply_canva", inputs={})
        r = self.run_snippet("write_result", ROOT, self.root, job, self.draft())
        self.assertNotEqual(r.returncode, 0, "done without a recorded copy id must be refused (R19)")
        self.assertIn("canva_copy_id", r.stderr)
        self.set_state(waiting="apply", copy_id="DANEWCOPY1")
        for bad in (self.draft(outputs={"canva_copy_id": "DAWRONG"}), self.draft(checks=[{"name": "x", "passed": False, "detail": "bad"}]),
                    self.draft(extra=1), self.draft(summary="  ")):
            self.assertNotEqual(self.run_snippet("write_result", ROOT, self.root, job, bad).returncode, 0)
        r = self.run_snippet("write_result", ROOT, self.root, job, self.draft())
        self.assertEqual(r.returncode, 0, r.stderr)
        stored = read_json(self.tdir / "jobs" / "20261120T000013Z-apply_canva.result.json")
        self.assertEqual(stored["status"], "done")
        self.assertEqual(stored["summary"], "Готово")

    def test_set_copy_id_refuses_originals_and_a_second_id(self):
        self.set_state(waiting="apply")
        for protected in (ORIGINAL, ORIGINAL.upper(), "DASKEL0001"):
            self.assertNotEqual(self.run_snippet("set_copy_id", ROOT, self.root, "tpl", protected).returncode, 0, protected)
        self.assertIsNone(read_json(self.tdir / "state.json")["canva_copy_id"])
        self.assertEqual(self.run_snippet("set_copy_id", ROOT, self.root, "tpl", "DANEWCOPY1").returncode, 0)
        self.assertEqual(self.run_snippet("set_copy_id", ROOT, self.root, "tpl", "DANEWCOPY1").returncode, 0)  # same id: fine
        self.assertNotEqual(self.run_snippet("set_copy_id", ROOT, self.root, "tpl", "DAOTHER0002").returncode, 0)
        st = read_json(self.tdir / "state.json")
        self.assertEqual(st["canva_copy_id"], "DANEWCOPY1")
        self.assertEqual(st["steps"]["apply"]["status"], "waiting_claude")             # no step status is touched

    # ---- checks run on the shipped fixtures ---------------------------------------------------------------
    def test_map_check_accepts_a_good_map_and_rejects_the_unassigned_draft(self):
        good = self.run_snippet("map_check", ROOT, FX / "map_sage.json", FX / "facts_orig.json")
        self.assertEqual(good.returncode, 0, good.stdout)
        self.assertEqual(json.loads(good.stdout)["uncovered"], 0)
        outline = self.root / "outline.txt"
        outline.write_text("PAGE PBXlqtRQwJ1yRgrZ type=x title='A' notes=''\nPAGE PBw4SHZw3cbPHqdd type=x title='B' notes=''\n"
                           "PAGE PBk5WNyktq95LJP9 type=x title='C' notes=''\n", encoding="utf-8")
        draft = self.root / "draft_map.json"
        r = self.run_snippet("draft_map", FX / "facts_orig.json", outline, "sk", "DAXXXXXXXXX", draft)
        self.assertEqual(r.returncode, 0, r.stderr)
        bad = self.run_snippet("map_check", ROOT, draft, FX / "facts_orig.json")
        self.assertEqual(bad.returncode, 1, "control: a draft with unassigned roles must fail the same check")
        self.assertIn("unassigned", bad.stdout)

    def test_calendar_cells_september_2027(self):
        r = self.run_snippet("calendar_cells", FX / "map_sage.json", FX / "facts_orig.json", 2027, 9)
        self.assertEqual(r.returncode, 0, r.stderr)
        cells = json.loads(r.stdout)
        by = {k.rsplit("-", 1)[1]: v for k, v in cells.items()}
        self.assertEqual((by["D1"], by["G3"], by["E5"], by["F5"], by["A6"]), ("1", "18", "30", "", ""))
        self.assertEqual(sum(1 for v in cells.values() if v), 30)

    def test_old_media_search_has_a_working_control(self):
        r = self.run_snippet("old_media", ROOT, FX / "map_sage.json", FX / "facts_orig.json", FX / "facts_orig.json")
        out = json.loads(r.stdout)
        self.assertEqual(r.returncode, 1)                                              # the untouched original still shows old media
        self.assertIn("control on the untouched original found", out["detail"])
        self.assertNotIn("CONTROL FAILED", out["detail"])

    def test_marker_position_and_its_control(self):
        facts = json.loads((FX / "facts_orig.json").read_text(encoding="utf-8"))
        marker = "PBw4SHZw3cbPHqdd-PBb0Thf13p3S4fmP-LBdkLjZVv73Kb0vD"
        table = "PBw4SHZw3cbPHqdd-PBb0Thf13p3S4fmP-LBxhfzk8VVsmFczv"
        out = self.root / "marker.json"
        r = self.run_snippet("marker", ROOT, FX / "map_sage.json", FX / "facts_orig.json", FX / "facts_orig.json",
                             marker, f"{table}-G3", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        op = json.loads(out.read_text(encoding="utf-8"))["operations"][0]
        t, l, w, h = facts[table]["box"]
        mt, ml, mw, mh = facts[marker]["box"]
        self.assertAlmostEqual(op["left"] + mw / 2, l + 6.5 * w / 7, delta=0.01)       # column G
        self.assertAlmostEqual(op["top"] + mh / 2, t + 2.5 * h / 6, delta=0.01)        # row 3
        bad = json.loads(json.dumps(facts))
        bad[marker]["box"][0] -= 300                                                    # marker not over any cell: control must fail
        (self.root / "facts_bad.json").write_text(json.dumps(bad), encoding="utf-8")
        r = self.run_snippet("marker", ROOT, FX / "map_sage.json", self.root / "facts_bad.json", FX / "facts_orig.json",
                             marker, f"{table}-G3", out)
        self.assertNotEqual(r.returncode, 0)

    def test_to_checks_parses_a_final_check_report(self):
        report = self.root / "report.txt"
        report.write_text("PASS texts: 3 text slots checked, 0 wrong\nFAIL colours: 1 wrong: a: b\nnoise\n", encoding="utf-8")
        out = self.root / "checks.json"
        self.assertEqual(self.run_snippet("to_checks", report, out).returncode, 0)
        self.assertEqual([(c["name"], c["passed"]) for c in json.loads(out.read_text(encoding="utf-8"))],
                         [("texts", True), ("colours", False)])
        empty = self.root / "empty.txt"
        empty.write_text("nothing here\n", encoding="utf-8")
        self.assertNotEqual(self.run_snippet("to_checks", empty, out).returncode, 0)   # a parser that found nothing fails


if __name__ == "__main__":
    unittest.main()
