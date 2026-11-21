"""Job inbox: create_job (guard + one-writer rule), canva_busy, list_jobs and read_result, including corrupt files."""
import dataclasses
import json
import os
import re
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from app import jobs as jobs_mod
from app.config import load_config
from app.guard import CANVA_WRITE_TYPES, GuardError
from app.jobs import canva_busy, create_job, list_jobs, read_result
from app.steps import STEPS
from app.store import create_template, read_json, write_json_atomic

FIXTURE = Path(__file__).parent / "fixtures" / "config.json"
ORIGINAL = "DAHarqlqips"
SKELETON_ID = "DASKEL0001"
COPY_ID = "DACOPY0001"
STATES = ("pending", "running", "done", "failed")


class JobsTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.cfg = dataclasses.replace(load_config(FIXTURE), root=self.tmp)
        self.jobs = self.tmp / "jobs"

    # -- fixtures --
    def make_skeleton(self, name="ivory-lace", design_id=SKELETON_ID):
        write_json_atomic(self.tmp / "skeletons" / name / "map.json", {"skeleton": name, "design_id": design_id})

    def make_template(self, name="rose-1", skeleton="ivory-lace", approved=("style", "images", "texts"), copy_id=None):
        d = create_template(self.cfg, name, skeleton)
        state = read_json(d / "state.json")
        for s in approved:
            state["steps"][s]["status"] = "approved"
        state["canva_copy_id"] = copy_id
        write_json_atomic(d / "state.json", state)
        return d

    def files(self, state):
        d = self.jobs / state
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def all_job_files(self):
        return {s: self.files(s) for s in STATES}

    def put_raw(self, state, name, data: bytes):
        d = self.jobs / state
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(data)
        return d / name

    def move(self, job_id, src, dst):
        # test-only helper standing in for the /test-canva-studio skill; the studio code itself never moves files
        (self.jobs / dst).mkdir(parents=True, exist_ok=True)
        os.rename(self.jobs / src / f"{job_id}.json", self.jobs / dst / f"{job_id}.json")


class CreateJobTests(JobsTestBase):
    def test_create_apply_first_run_writes_pending_file(self):
        self.make_skeleton()
        self.make_template()
        job = create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {"note": "x"}, None)
        self.assertEqual(self.files("pending"), [job["id"] + ".json"])
        on_disk = read_json(self.jobs / "pending" / (job["id"] + ".json"))
        self.assertEqual(on_disk, job)
        self.assertEqual(
            sorted(job),
            ["created_utc", "id", "inputs", "limits", "skeleton", "target_design_id", "template", "type"],
        )
        self.assertEqual(job["type"], "apply_canva")
        self.assertEqual(job["template"], "rose-1")
        self.assertEqual(job["skeleton"], "ivory-lace")
        self.assertIsNone(job["target_design_id"])
        self.assertEqual(job["inputs"], {"note": "x"})
        self.assertRegex(job["created_utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertRegex(job["id"], r"^\d{8}T\d{6}Z-apply_canva$")

    def test_create_apply_with_existing_copy_targets_it(self):
        self.make_skeleton()
        self.make_template(copy_id=COPY_ID)
        job = create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, COPY_ID)
        self.assertEqual(job["target_design_id"], COPY_ID)

    def test_create_verify_on_copy(self):
        self.make_skeleton()
        self.make_template(copy_id=COPY_ID)
        job = create_job(self.cfg, "verify", "ivory-lace", "rose-1", {}, COPY_ID)
        self.assertEqual(job["type"], "verify")

    def test_create_refuses_forbidden_target_for_every_type(self):
        self.make_skeleton()
        self.make_template(copy_id=COPY_ID)
        for jtype in ("map_skeleton", "style_directions", "write_texts", "apply_canva", "verify"):
            with self.subTest(jtype=jtype):
                with self.assertRaises(GuardError):
                    create_job(self.cfg, jtype, "ivory-lace", "rose-1", {}, ORIGINAL)
        self.assertEqual(self.all_job_files(), {s: [] for s in STATES})
        self.assertFalse(self.jobs.exists())

    def test_create_refuses_skeleton_id_as_write_target(self):
        self.make_skeleton()
        self.make_template(copy_id=COPY_ID)
        for jtype in sorted(CANVA_WRITE_TYPES):
            with self.subTest(jtype=jtype):
                with self.assertRaises(GuardError):
                    create_job(self.cfg, jtype, "ivory-lace", "rose-1", {}, SKELETON_ID)
        self.assertFalse(self.jobs.exists())

    def test_create_map_skeleton_carries_id_in_inputs(self):
        # R4 positive control: map_skeleton on the skeleton's own id is allowed (read-only), target None
        job = create_job(self.cfg, "map_skeleton", "ivory-lace", None, {"design_id": SKELETON_ID}, None)
        self.assertEqual(job["inputs"]["design_id"], SKELETON_ID)
        self.assertIsNone(job["target_design_id"])
        self.assertIsNone(job["template"])
        self.assertEqual(self.files("pending"), [job["id"] + ".json"])

    def test_create_map_skeleton_refuses_original_in_inputs(self):
        with self.assertRaises(GuardError):
            create_job(self.cfg, "map_skeleton", "ivory-lace", None, {"design_id": ORIGINAL}, None)
        self.assertFalse(self.jobs.exists())

    def test_create_map_skeleton_does_not_take_the_canva_lock(self):
        self.make_skeleton()
        self.make_template()
        create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        # read-only: allowed while a write job is pending
        create_job(self.cfg, "map_skeleton", "ivory-lace", None, {"design_id": SKELETON_ID}, None)
        self.assertEqual(len(self.files("pending")), 2)

    def test_create_read_only_types_never_blocked_by_busy(self):
        self.make_skeleton()
        self.make_template()
        create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        create_job(self.cfg, "style_directions", "ivory-lace", "rose-1", {}, None)
        create_job(self.cfg, "write_texts", "ivory-lace", "rose-1", {}, None)
        self.assertEqual(len(self.files("pending")), 3)

    # ---- R3: where the skeleton id comes from, fail closed ----

    def test_create_skeleton_id_from_map_json(self):
        self.make_skeleton(design_id="DAFROMMAP1")
        self.make_template(copy_id="DAFROMMAP1")  # state is consistent, so only the skeleton rule can refuse
        # inputs claim a different id; the map wins, so the map's id is the protected one
        with self.assertRaises(GuardError):
            create_job(self.cfg, "verify", "ivory-lace", "rose-1", {"design_id": "DAINPUT001"}, "DAFROMMAP1")
        self.assertFalse(self.jobs.exists())

    def test_create_skeleton_id_falls_back_to_inputs_when_no_map(self):
        self.make_template(copy_id="DAINPUT002")
        # no map.json: inputs["design_id"] is the skeleton id and is refused as target of a write job
        with self.assertRaises(GuardError):
            create_job(self.cfg, "verify", "ivory-lace", "rose-1", {"design_id": "DAINPUT002"}, "DAINPUT002")
        # control: same call with a different copy id works
        self.make_template("rose-2", copy_id=COPY_ID)
        job = create_job(self.cfg, "verify", "ivory-lace", "rose-2", {"design_id": "DAINPUT002"}, COPY_ID)
        self.assertEqual(job["target_design_id"], COPY_ID)

    def test_create_write_without_any_skeleton_id_fails_closed(self):
        self.make_template(copy_id=COPY_ID)
        for jtype, target in (("apply_canva", COPY_ID), ("verify", COPY_ID)):
            with self.subTest(jtype=jtype):
                with self.assertRaises(GuardError):
                    create_job(self.cfg, jtype, "ivory-lace", "rose-1", {}, target)
        self.assertFalse(self.jobs.exists())

    def test_create_write_with_corrupt_or_idless_map_fails_closed(self):
        self.make_template(copy_id=COPY_ID)
        map_path = self.tmp / "skeletons" / "ivory-lace" / "map.json"
        map_path.parent.mkdir(parents=True)
        for content in (b'{"design_id":', b"\xff\xfe", b"[]", b'{"skeleton": "x"}', b'{"design_id": ""}', b'{"design_id": 5}'):
            with self.subTest(content=content):
                map_path.write_bytes(content)
                with self.assertRaises(GuardError):
                    # inputs carry a plausible id, but an existing broken map must not be silently bypassed
                    create_job(self.cfg, "verify", "ivory-lace", "rose-1", {"design_id": "DAINPUT003"}, COPY_ID)
        self.assertFalse(self.jobs.exists())

    def test_create_read_only_job_survives_corrupt_map(self):
        self.make_template()
        map_path = self.tmp / "skeletons" / "ivory-lace" / "map.json"
        map_path.parent.mkdir(parents=True)
        map_path.write_bytes(b"{")
        job = create_job(self.cfg, "write_texts", "ivory-lace", "rose-1", {}, None)
        self.assertEqual(job["type"], "write_texts")

    def test_create_write_with_missing_state_fails_closed(self):
        self.make_skeleton()
        with self.assertRaises(GuardError):
            create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        self.assertFalse(self.jobs.exists())

    def test_create_write_with_corrupt_state_fails_closed(self):
        self.make_skeleton()
        d = self.make_template()
        for content in (b'{"steps":', b"\xff\xfe", b"[]"):
            with self.subTest(content=content):
                (d / "state.json").write_bytes(content)
                with self.assertRaises(GuardError):
                    create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        self.assertFalse(self.jobs.exists())

    def test_create_write_without_template_fails_closed(self):
        self.make_skeleton()
        for jtype in sorted(CANVA_WRITE_TYPES):
            with self.subTest(jtype=jtype):
                with self.assertRaises(GuardError):
                    create_job(self.cfg, jtype, "ivory-lace", None, {}, COPY_ID)
        self.assertFalse(self.jobs.exists())

    def test_create_write_refuses_template_of_another_skeleton(self):
        self.make_skeleton("ivory-lace", SKELETON_ID)
        self.make_skeleton("other", "DAOTHERSK1")
        self.make_template(skeleton="other")
        with self.assertRaises(GuardError):
            create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        self.assertFalse(self.jobs.exists())
        # control: the matching skeleton works
        job = create_job(self.cfg, "apply_canva", "other", "rose-1", {}, None)
        self.assertEqual(job["skeleton"], "other")

    def test_create_apply_stale_state_refused_and_nothing_written(self):
        self.make_skeleton()
        d = self.make_template()
        state = read_json(d / "state.json")
        state["steps"]["texts"]["status"] = "stale"
        write_json_atomic(d / "state.json", state)
        with self.assertRaises(GuardError):
            create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        self.assertFalse(self.jobs.exists())

    def test_create_read_only_job_without_state_is_fine(self):
        self.make_skeleton()
        job = create_job(self.cfg, "style_directions", "ivory-lace", "rose-1", {}, None)
        self.assertEqual(job["template"], "rose-1")

    # ---- input validation (ValueError, distinct from GuardError) ----

    def test_create_bad_arguments_raise_valueerror(self):
        self.make_skeleton()
        self.make_template()
        cases = [
            dict(type="publish_site", skeleton="ivory-lace", template="rose-1", inputs={}, target=None),
            dict(type="", skeleton="ivory-lace", template="rose-1", inputs={}, target=None),
            dict(type="write_texts", skeleton="../x", template="rose-1", inputs={}, target=None),
            dict(type="write_texts", skeleton="Ivory", template="rose-1", inputs={}, target=None),
            dict(type="write_texts", skeleton="ivory-lace", template="../x", inputs={}, target=None),
            dict(type="write_texts", skeleton="ivory-lace", template="a/b", inputs={}, target=None),
            dict(type="write_texts", skeleton="ivory-lace", template="rose-1", inputs=[], target=None),
            dict(type="write_texts", skeleton="ivory-lace", template="rose-1", inputs={}, target=5),
            dict(type="write_texts", skeleton="ivory-lace", template="rose-1", inputs={}, target="a b"),
            dict(type="write_texts", skeleton="ivory-lace", template="rose-1", inputs={}, target=""),
        ]
        for c in cases:
            with self.subTest(case=c):
                with self.assertRaises(ValueError) as ctx:
                    create_job(self.cfg, c["type"], c["skeleton"], c["template"], c["inputs"], c["target"])
                self.assertNotIsInstance(ctx.exception, GuardError)
        self.assertFalse(self.jobs.exists())

    def test_guard_error_is_not_a_value_error(self):
        self.assertFalse(issubclass(GuardError, ValueError))

    def test_create_unserialisable_inputs_write_nothing(self):
        self.make_skeleton()
        with self.assertRaises(TypeError):
            create_job(self.cfg, "style_directions", "ivory-lace", "rose-1", {"x": object()}, None)
        self.assertEqual(self.all_job_files(), {s: [] for s in STATES})

    # ---- ids ----

    def test_job_id_format_and_same_second_collision(self):
        self.make_skeleton()
        fixed = datetime(2026, 11, 20, 10, 11, 12, tzinfo=timezone.utc)
        with mock.patch.object(jobs_mod, "_utcnow", return_value=fixed):
            a = create_job(self.cfg, "style_directions", "ivory-lace", "rose-1", {"n": 1}, None)
            b = create_job(self.cfg, "style_directions", "ivory-lace", "rose-1", {"n": 2}, None)
            c = create_job(self.cfg, "style_directions", "ivory-lace", "rose-1", {"n": 3}, None)
        self.assertEqual(a["id"], "20261120T101112Z-style_directions")
        self.assertEqual(b["id"], "20261120T101112Z-style_directions-2")
        self.assertEqual(c["id"], "20261120T101112Z-style_directions-3")
        self.assertEqual(a["created_utc"], "2026-11-20T10:11:12Z")
        self.assertEqual(len(self.files("pending")), 3)
        # nothing was overwritten
        for job in (a, b, c):
            self.assertEqual(read_json(self.jobs / "pending" / (job["id"] + ".json")), job)

    def test_job_id_collision_with_a_file_in_another_state_folder(self):
        self.make_skeleton()
        fixed = datetime(2026, 11, 20, 10, 11, 12, tzinfo=timezone.utc)
        for state in ("running", "done", "failed"):
            with self.subTest(state=state):
                name = "20261120T101112Z-write_texts"
                (self.jobs / state).mkdir(parents=True, exist_ok=True)
                (self.jobs / state / f"{name}.json").write_text('{"id": "old"}', encoding="utf-8")
                with mock.patch.object(jobs_mod, "_utcnow", return_value=fixed):
                    job = create_job(self.cfg, "write_texts", "ivory-lace", "rose-1", {}, None)
                self.assertNotEqual(job["id"], name)
                self.assertTrue(job["id"].startswith(name + "-"))
                self.assertEqual(
                    json.loads((self.jobs / state / f"{name}.json").read_text(encoding="utf-8")), {"id": "old"}
                )
                self.move(job["id"], "pending", "done")  # tidy for the next iteration (test helper)

    def test_job_id_collides_only_by_exact_name(self):
        self.make_skeleton()
        fixed = datetime(2026, 11, 20, 10, 11, 12, tzinfo=timezone.utc)
        (self.jobs / "done").mkdir(parents=True)
        (self.jobs / "done" / "20261120T101112Z-verify.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(jobs_mod, "_utcnow", return_value=fixed):
            job = create_job(self.cfg, "write_texts", "ivory-lace", "rose-1", {}, None)
        self.assertEqual(job["id"], "20261120T101112Z-write_texts")  # different type: no suffix

    # ---- limits (R5) ----

    def test_job_limits_present(self):
        self.make_skeleton()
        self.make_template(copy_id=COPY_ID)
        needles = [
            "Редагувати лише дизайн",
            "Ніколи не редагувати скелет",
            "Не чіпати форму",
            "Без перегрупування",
            "Без публікації",
            "Без видалень",
            "Дві однакові невдачі",
        ]
        apply_job = create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, COPY_ID)
        self.move(apply_job["id"], "pending", "done")  # test helper: free the Canva lock
        verify_job = create_job(self.cfg, "verify", "ivory-lace", "rose-1", {}, COPY_ID)
        for job in (apply_job, verify_job):
            with self.subTest(type=job["type"]):
                limits = job["limits"]
                self.assertEqual(len(limits), 7)
                for needle in needles:
                    hits = [line for line in limits if needle in line]
                    self.assertEqual(len(hits), 1, f"{needle!r} must appear in exactly one line: {limits}")
                self.assertIn(COPY_ID, [l for l in limits if "Редагувати лише дизайн" in l][0])
                forbidden_line = [l for l in limits if "Ніколи не редагувати скелет" in l][0]
                self.assertIn(ORIGINAL, forbidden_line)
                self.assertIn(SKELETON_ID, forbidden_line)
        # the stored files carry the same limits
        self.assertEqual(read_json(self.jobs / "done" / (apply_job["id"] + ".json"))["limits"], apply_job["limits"])
        self.assertEqual(read_json(self.jobs / "pending" / (verify_job["id"] + ".json"))["limits"], verify_job["limits"])

    def test_job_limits_first_run_has_no_target(self):
        self.make_skeleton()
        self.make_template()
        job = create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        line = [l for l in job["limits"] if "Редагувати лише дизайн" in l]
        self.assertEqual(len(line), 1)
        self.assertNotIn("None", line[0])
        self.assertEqual(len(job["limits"]), 7)

    def test_job_limits_name_every_forbidden_id(self):
        cfg = dataclasses.replace(self.cfg, forbidden_design_ids=frozenset({"DAFIRST001", "DASECOND02"}))
        self.make_skeleton()
        self.make_template()
        job = create_job(cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        line = [l for l in job["limits"] if "Ніколи не редагувати скелет" in l][0]
        self.assertIn("DAFIRST001", line)
        self.assertIn("DASECOND02", line)

    def test_map_skeleton_limits_say_read_only(self):
        job = create_job(self.cfg, "map_skeleton", "ivory-lace", None, {"design_id": SKELETON_ID}, None)
        self.assertTrue(job["limits"])
        self.assertIn(ORIGINAL, "\n".join(job["limits"]))
        self.assertTrue(any("лише читання" in l.lower() for l in job["limits"]))


class BusyTests(JobsTestBase):
    def setUp(self):
        super().setUp()
        self.make_skeleton()
        self.make_template()

    def test_canva_busy_false_when_no_jobs_folder(self):
        self.assertFalse(canva_busy(self.cfg))

    def test_second_canva_job_refused(self):
        first = create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        self.assertTrue(canva_busy(self.cfg))
        with self.assertRaises(GuardError):
            create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        self.assertEqual(self.files("pending"), [first["id"] + ".json"])

    def test_any_write_type_blocks_any_other_write_type(self):
        d = self.tmp / "templates" / "rose-1"
        state = read_json(d / "state.json")
        state["canva_copy_id"] = COPY_ID
        write_json_atomic(d / "state.json", state)
        create_job(self.cfg, "verify", "ivory-lace", "rose-1", {}, COPY_ID)
        with self.assertRaises(GuardError):
            create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, COPY_ID)
        with self.assertRaises(GuardError):
            create_job(self.cfg, "verify", "ivory-lace", "rose-1", {}, COPY_ID)
        self.assertEqual(len(self.files("pending")), 1)

    def test_running_write_job_blocks(self):
        first = create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        self.move(first["id"], "pending", "running")
        self.assertTrue(canva_busy(self.cfg))
        with self.assertRaises(GuardError):
            create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        self.assertEqual(self.files("pending"), [])

    def test_done_or_failed_write_job_does_not_block(self):
        for final in ("done", "failed"):
            with self.subTest(final=final):
                first = create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
                self.assertTrue(canva_busy(self.cfg))
                self.move(first["id"], "pending", final)
                self.assertFalse(canva_busy(self.cfg))
        second = create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        self.assertEqual(self.files("pending"), [second["id"] + ".json"])

    def test_read_only_job_does_not_make_canva_busy(self):
        create_job(self.cfg, "map_skeleton", "ivory-lace", None, {"design_id": SKELETON_ID}, None)
        create_job(self.cfg, "style_directions", "ivory-lace", "rose-1", {}, None)
        create_job(self.cfg, "write_texts", "ivory-lace", "rose-1", {}, None)
        self.assertFalse(canva_busy(self.cfg))

    def test_corrupt_file_in_pending_or_running_is_busy(self):
        samples = {
            "garbage": b"not json at all",
            "truncated": b'{"id": "x", "type": "style_dir',
            "bad utf8": b'{"type": "\xff\xfe"}',
            "non-object": b"[1, 2]",
            "no type": b'{"id": "x"}',
            "unknown type": b'{"id": "x", "type": "mystery"}',
            "non-string type": b'{"id": "x", "type": 5}',
            "empty": b"",
        }
        for state in ("pending", "running"):
            for label, content in samples.items():
                with self.subTest(state=state, sample=label):
                    p = self.put_raw(state, "x.json", content)
                    self.assertTrue(canva_busy(self.cfg))
                    with self.assertRaises(GuardError):
                        create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
                    p.unlink()  # test cleanup
                    self.assertFalse(canva_busy(self.cfg))  # control: clean again after the garbage is gone

    def test_corrupt_file_in_done_or_failed_is_not_busy(self):
        for state in ("done", "failed"):
            self.put_raw(state, "x.json", b"garbage")
        self.assertFalse(canva_busy(self.cfg))

    def test_corrupt_file_does_not_block_read_only_types(self):
        self.put_raw("pending", "x.json", b"garbage")
        job = create_job(self.cfg, "map_skeleton", "ivory-lace", None, {"design_id": SKELETON_ID}, None)
        self.assertEqual(job["type"], "map_skeleton")

    def test_directory_named_like_a_job_is_busy(self):
        (self.jobs / "pending" / "weird.json").mkdir(parents=True)
        self.assertTrue(canva_busy(self.cfg))

    def test_non_json_files_are_ignored(self):
        self.put_raw("pending", "notes.txt", b"hello")
        self.put_raw("pending", ".x.json.abc.tmp", b"half")
        self.assertFalse(canva_busy(self.cfg))

    def test_busy_is_false_for_valid_read_only_job_files(self):
        self.put_raw("pending", "a.json", json.dumps({"id": "a", "type": "write_texts"}).encode())
        self.assertFalse(canva_busy(self.cfg))
        self.put_raw("running", "b.json", json.dumps({"id": "b", "type": "verify"}).encode())
        self.assertTrue(canva_busy(self.cfg))


class ListJobsTests(JobsTestBase):
    def test_empty(self):
        self.assertEqual(list_jobs(self.cfg), [])

    def test_corrupt_job_listed_not_raised(self):
        good = {"id": "20261120T100000Z-write_texts", "type": "write_texts"}
        self.put_raw("pending", "20261120T100000Z-write_texts.json", json.dumps(good).encode())
        self.put_raw("pending", "x.json", b"%%% garbage")
        self.put_raw("running", "badutf.json", b'{"a": "\xff"}')
        self.put_raw("done", "arr.json", b"[1]")
        listed = list_jobs(self.cfg)  # must not raise
        by_id = {j["id"]: j for j in listed}
        self.assertEqual(set(by_id), {"20261120T100000Z-write_texts", "x", "badutf", "arr"})
        self.assertEqual(by_id["x"]["state"], "corrupt")
        self.assertEqual(by_id["badutf"]["state"], "corrupt")
        self.assertEqual(by_id["arr"]["state"], "corrupt")
        # control: the good file is not mislabelled corrupt
        self.assertEqual(by_id["20261120T100000Z-write_texts"]["state"], "pending")
        self.assertEqual(by_id["20261120T100000Z-write_texts"]["type"], "write_texts")

    def test_state_and_age(self):
        now = time.time()
        for state in STATES:
            p = self.put_raw(state, f"j-{state}.json", json.dumps({"id": f"j-{state}", "type": "write_texts"}).encode())
            os.utime(p, (now - 100, now - 100))
        listed = list_jobs(self.cfg)
        self.assertEqual({j["state"] for j in listed}, set(STATES))
        for j in listed:
            self.assertIsInstance(j["age_s"], int)
            self.assertTrue(100 <= j["age_s"] < 160, j)

    def test_state_key_comes_from_the_folder_not_the_file(self):
        self.put_raw("done", "a.json", json.dumps({"id": "a", "type": "write_texts", "state": "pending"}).encode())
        self.assertEqual(list_jobs(self.cfg)[0]["state"], "done")

    def test_sorted_oldest_first(self):
        now = time.time()
        for name, age in (("c", 10), ("a", 300), ("b", 100)):
            p = self.put_raw("pending", f"{name}.json", json.dumps({"id": name, "type": "write_texts"}).encode())
            os.utime(p, (now - age, now - age))
        p = self.put_raw("done", "old.json", b"garbage")
        os.utime(p, (now - 1000, now - 1000))
        self.assertEqual([j["id"] for j in list_jobs(self.cfg)], ["old", "a", "b", "c"])

    def test_listing_changes_nothing_on_disk(self):
        self.put_raw("pending", "x.json", b"garbage")
        self.put_raw("running", "y.json", b'{"id": "y", "type": "verify"}')
        before = self.all_job_files()
        content = (self.jobs / "pending" / "x.json").read_bytes()
        list_jobs(self.cfg)
        canva_busy(self.cfg)
        self.assertEqual(self.all_job_files(), before)
        self.assertEqual((self.jobs / "pending" / "x.json").read_bytes(), content)

    def test_other_files_ignored(self):
        self.put_raw("pending", "notes.txt", b"hi")
        self.assertEqual(list_jobs(self.cfg), [])

    def test_created_jobs_are_listed(self):
        self.make_skeleton()
        job = create_job(self.cfg, "style_directions", "ivory-lace", "rose-1", {}, None)
        listed = list_jobs(self.cfg)
        self.assertEqual([j["id"] for j in listed], [job["id"]])
        self.assertEqual(listed[0]["state"], "pending")


class ReadResultTests(JobsTestBase):
    def setUp(self):
        super().setUp()
        self.job = {"id": "20261120T100000Z-write_texts", "type": "write_texts", "template": "rose-1", "skeleton": "ivory-lace"}
        self.map_job = {
            "id": "20261120T100000Z-map_skeleton",
            "type": "map_skeleton",
            "template": None,
            "skeleton": "ivory-lace",
        }

    def test_missing_is_none(self):
        self.assertIsNone(read_result(self.cfg, self.job))
        self.assertIsNone(read_result(self.cfg, self.map_job))

    def test_template_result(self):
        result = {"status": "done", "summary": "ok", "outputs": {}, "checks": []}
        write_json_atomic(self.tmp / "templates" / "rose-1" / "jobs" / (self.job["id"] + ".result.json"), result)
        self.assertEqual(read_result(self.cfg, self.job), result)
        # the map_skeleton path is a different place
        self.assertIsNone(read_result(self.cfg, self.map_job))

    def test_map_skeleton_result_lives_under_skeleton(self):
        result = {"status": "failed", "summary": "no", "outputs": {}, "checks": []}
        write_json_atomic(self.tmp / "skeletons" / "ivory-lace" / "jobs" / (self.map_job["id"] + ".result.json"), result)
        self.assertEqual(read_result(self.cfg, self.map_job), result)

    def test_corrupt_result_returns_corrupt_status(self):
        for content in (b"{", b"\xff\xfe", b"[]", b""):
            with self.subTest(content=content):
                p = self.tmp / "templates" / "rose-1" / "jobs" / (self.job["id"] + ".result.json")
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(content)
                res = read_result(self.cfg, self.job)
                self.assertEqual(res["status"], "corrupt")
                self.assertIsInstance(res["summary"], str)
                self.assertTrue(res["summary"])

    def test_hostile_job_fields_do_not_escape_the_folder(self):
        secret = self.tmp / "secret.result.json"
        secret.write_text(json.dumps({"status": "done", "summary": "leak"}), encoding="utf-8")
        for bad_id in ("../../secret", "..", "a/b", "", None, 5):
            with self.subTest(job_id=bad_id):
                res = read_result(self.cfg, dict(self.job, id=bad_id))
                self.assertTrue(res is None or res["status"] == "corrupt")
                self.assertNotEqual((res or {}).get("summary"), "leak")
        for bad in ("../x", "A", 5):
            with self.subTest(template=bad):
                res = read_result(self.cfg, dict(self.job, template=bad))
                self.assertTrue(res is None or res["status"] == "corrupt")

    def test_job_without_type_gives_none_or_corrupt(self):
        res = read_result(self.cfg, {"id": "x"})
        self.assertTrue(res is None or res["status"] == "corrupt")

    def test_read_result_does_not_create_folders(self):
        read_result(self.cfg, self.job)
        read_result(self.cfg, self.map_job)
        self.assertFalse((self.tmp / "templates").exists())
        self.assertFalse((self.tmp / "skeletons").exists())


class NoDeletionTests(JobsTestBase):
    def test_studio_leaves_every_existing_file_alone(self):
        self.make_skeleton()
        self.make_template()
        old = self.put_raw("done", "old.json", b'{"id": "old", "type": "verify"}')
        failed = self.put_raw("failed", "bad.json", b"garbage")
        snapshot = {p: p.read_bytes() for p in (old, failed)}
        create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        with self.assertRaises(GuardError):
            create_job(self.cfg, "apply_canva", "ivory-lace", "rose-1", {}, None)
        list_jobs(self.cfg)
        canva_busy(self.cfg)
        for p, content in snapshot.items():
            self.assertEqual(p.read_bytes(), content)
        self.assertEqual(len(self.files("pending")), 1)

    def test_no_stray_temp_files_after_create(self):
        self.make_skeleton()
        create_job(self.cfg, "style_directions", "ivory-lace", "rose-1", {}, None)
        self.assertTrue(all(re.fullmatch(r"[\w-]+\.json", n) for n in self.files("pending")))


if __name__ == "__main__":
    unittest.main()
