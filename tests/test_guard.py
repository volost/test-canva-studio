import copy
import dataclasses
import unittest
from pathlib import Path

from app.config import load_config
from app.guard import CANVA_WRITE_TYPES, JOB_TYPES, GuardError, check_job
from app.steps import STEPS

FIXTURE = Path(__file__).parent / "fixtures" / "config.json"
ORIGINAL = "DAHarqlqips"
SKELETON_ID = "DASKEL0001"
COPY_ID = "DACOPY0001"


def make_state(approved=("style", "images", "texts"), copy_id=None, skeleton="ivory-lace"):
    steps = {s: {"status": "approved" if s in approved else "draft", "updated_utc": "2026-11-20T00:00:00Z"} for s in STEPS}
    return {"skeleton": skeleton, "canva_copy_id": copy_id, "chosen": {}, "steps": steps}


def make_job(jtype, target=None, template="rose-1", inputs=None):
    return {
        "id": "20261120T100000Z-" + jtype,
        "type": jtype,
        "template": template,
        "skeleton": "ivory-lace",
        "target_design_id": target,
        "created_utc": "2026-11-20T10:00:00Z",
        "inputs": inputs if inputs is not None else {},
        "limits": [],
    }


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(FIXTURE)
        self.assertIn(ORIGINAL, self.cfg.forbidden_design_ids)  # control: the fixture really forbids it

    def check(self, job, state=None, skeleton_id=SKELETON_ID):
        return check_job(job, self.cfg, skeleton_id, state)

    # ---- the purchased original -------------------------------------------------

    def test_guard_blocks_purchased_original(self):
        for jtype in sorted(JOB_TYPES):
            with self.subTest(jtype=jtype):
                state = make_state(copy_id=COPY_ID)
                with self.assertRaises(GuardError):
                    self.check(make_job(jtype, target=ORIGINAL), state)

    def test_guard_original_variants_refused(self):
        state = make_state(copy_id=COPY_ID)
        for variant in (ORIGINAL.lower(), ORIGINAL.upper(), " " + ORIGINAL, ORIGINAL + "\n"):
            with self.subTest(variant=variant):
                with self.assertRaises(GuardError):
                    self.check(make_job("style_directions", target=variant), state)

    def test_guard_positive_control_valid_jobs_pass(self):
        # if the guard refused everything, the refusal tests above would be meaningless
        state = make_state(copy_id=COPY_ID)
        self.assertIsNone(self.check(make_job("apply_canva", target=COPY_ID), state))
        self.assertIsNone(self.check(make_job("verify", target=COPY_ID), state))
        self.assertIsNone(self.check(make_job("write_texts"), state))
        self.assertIsNone(self.check(make_job("style_directions"), state))
        self.assertIsNone(
            self.check(make_job("map_skeleton", template=None, inputs={"design_id": SKELETON_ID}), None)
        )

    def test_guard_map_skeleton_refuses_original_as_input(self):
        job = make_job("map_skeleton", template=None, inputs={"design_id": ORIGINAL})
        with self.assertRaises(GuardError):
            self.check(job)
        job = make_job("map_skeleton", template=None, inputs={"design_id": ORIGINAL.lower()})
        with self.assertRaises(GuardError):
            self.check(job)
        # control: the skeleton's own id is exactly what map_skeleton must be allowed to read
        self.assertIsNone(self.check(make_job("map_skeleton", template=None, inputs={"design_id": SKELETON_ID})))

    def test_guard_map_skeleton_refuses_original_as_target(self):
        with self.assertRaises(GuardError):
            self.check(make_job("map_skeleton", target=ORIGINAL, template=None, inputs={"design_id": SKELETON_ID}))

    def test_guard_unknown_type_refused(self):
        with self.assertRaises(GuardError):
            self.check(make_job("publish_site"), make_state())

    # ---- the skeleton ------------------------------------------------------------

    def test_guard_blocks_skeleton_id(self):
        for jtype in sorted(CANVA_WRITE_TYPES):
            with self.subTest(jtype=jtype):
                with self.assertRaises(GuardError):
                    self.check(make_job(jtype, target=SKELETON_ID), make_state())
                with self.assertRaises(GuardError):
                    self.check(make_job(jtype, target=SKELETON_ID.lower()), make_state())

    def test_guard_skeleton_id_as_copy_in_state_refused(self):
        # a tainted state whose copy IS the skeleton must not make the skeleton a valid target
        state = make_state(copy_id=SKELETON_ID)
        for jtype in sorted(CANVA_WRITE_TYPES):
            with self.subTest(jtype=jtype):
                with self.assertRaises(GuardError):
                    self.check(make_job(jtype, target=SKELETON_ID), state)
        state = make_state(copy_id=ORIGINAL)
        for jtype in sorted(CANVA_WRITE_TYPES):
            with self.subTest(jtype=jtype, state="original"):
                with self.assertRaises(GuardError):
                    self.check(make_job(jtype, target=ORIGINAL), state)

    def test_guard_skeleton_id_allowed_as_target_for_read_only_types(self):
        # R4: the skeleton id is refused as a target only for the Canva write types
        self.assertIsNone(self.check(make_job("write_texts", target=SKELETON_ID), make_state()))

    def test_guard_write_types_need_a_known_skeleton_id(self):
        for jtype in sorted(CANVA_WRITE_TYPES):
            for bad in (None, "", "  ", 5):
                with self.subTest(jtype=jtype, skeleton_id=bad):
                    with self.assertRaises(GuardError):
                        self.check(make_job(jtype, target=COPY_ID), make_state(copy_id=COPY_ID), skeleton_id=bad)

    # ---- verify ------------------------------------------------------------------

    def test_guard_verify_requires_template_copy(self):
        state = make_state(copy_id=COPY_ID)
        with self.assertRaises(GuardError):
            self.check(make_job("verify", target="DAOTHER001"), state)
        with self.assertRaises(GuardError):
            self.check(make_job("verify", target=None), state)
        with self.assertRaises(GuardError):
            self.check(make_job("verify", target=COPY_ID.lower()), state)  # exact match only
        # no copy recorded yet: nothing to verify
        with self.assertRaises(GuardError):
            self.check(make_job("verify", target=COPY_ID), make_state(copy_id=None))
        with self.assertRaises(GuardError):
            self.check(make_job("verify", target=None), make_state(copy_id=None))
        # control
        self.assertIsNone(self.check(make_job("verify", target=COPY_ID), state))

    # ---- apply_canva -------------------------------------------------------------

    def test_guard_apply_first_run_target_none_ok(self):
        self.assertIsNone(self.check(make_job("apply_canva", target=None), make_state(copy_id=None)))

    def test_guard_apply_first_run_with_a_target_refused(self):
        # no copy recorded, yet a target is named: an unknown design — fail closed
        with self.assertRaises(GuardError):
            self.check(make_job("apply_canva", target="DAOTHER001"), make_state(copy_id=None))

    def test_guard_apply_with_copy_must_target_exactly_that_copy(self):
        state = make_state(copy_id=COPY_ID)
        with self.assertRaises(GuardError):
            self.check(make_job("apply_canva", target=None), state)
        with self.assertRaises(GuardError):
            self.check(make_job("apply_canva", target="DAOTHER001"), state)
        with self.assertRaises(GuardError):
            self.check(make_job("apply_canva", target=COPY_ID.lower()), state)
        self.assertIsNone(self.check(make_job("apply_canva", target=COPY_ID), state))

    def test_guard_apply_stale_texts_refused(self):
        state = make_state(copy_id=None)
        state["steps"]["texts"]["status"] = "stale"
        with self.assertRaises(GuardError):
            self.check(make_job("apply_canva", target=None), state)
        # also once a copy exists
        state["canva_copy_id"] = COPY_ID
        with self.assertRaises(GuardError):
            self.check(make_job("apply_canva", target=COPY_ID), state)
        # control: the same state with texts approved is fine
        state["steps"]["texts"]["status"] = "approved"
        self.assertIsNone(self.check(make_job("apply_canva", target=COPY_ID), state))

    def test_guard_apply_unapproved_earlier_steps_refused(self):
        for missing in ("style", "images", "texts"):
            with self.subTest(missing=missing):
                approved = tuple(s for s in ("style", "images", "texts") if s != missing)
                with self.assertRaises(GuardError):
                    self.check(make_job("apply_canva", target=None), make_state(approved=approved))

    # ---- fail closed on missing / broken input ------------------------------------

    def test_guard_write_types_require_a_template(self):
        for jtype in sorted(CANVA_WRITE_TYPES):
            with self.subTest(jtype=jtype):
                with self.assertRaises(GuardError):
                    self.check(make_job(jtype, target=COPY_ID, template=None), make_state(copy_id=COPY_ID))

    def test_guard_write_types_require_state(self):
        for jtype in sorted(CANVA_WRITE_TYPES):
            with self.subTest(jtype=jtype):
                with self.assertRaises(GuardError):
                    self.check(make_job(jtype, target=COPY_ID), None)

    def test_guard_malformed_state_refused(self):
        good = make_state(copy_id=COPY_ID)
        broken = []
        no_steps = copy.deepcopy(good)
        del no_steps["steps"]
        broken.append(no_steps)
        missing_step = copy.deepcopy(good)
        del missing_step["steps"]["texts"]
        broken.append(missing_step)
        no_status = copy.deepcopy(good)
        no_status["steps"]["style"] = {}
        broken.append(no_status)
        bad_copy = copy.deepcopy(good)
        bad_copy["canva_copy_id"] = 7
        broken.append(bad_copy)
        broken.append([])
        for state in broken:
            with self.subTest(state=state):
                with self.assertRaises(GuardError):
                    self.check(make_job("apply_canva", target=COPY_ID), state)
        self.assertIsNone(self.check(make_job("apply_canva", target=COPY_ID), good))

    def test_guard_bad_target_type_refused(self):
        for bad in ("", "   ", 5, ["x"]):
            with self.subTest(target=bad):
                with self.assertRaises(GuardError):
                    self.check(make_job("style_directions", target=bad), make_state())

    def test_guard_does_not_mutate_inputs(self):
        job = make_job("apply_canva", target=COPY_ID)
        state = make_state(copy_id=COPY_ID)
        before = (copy.deepcopy(job), copy.deepcopy(state))
        self.check(job, state)
        self.assertEqual((job, state), before)

    def test_guard_forbidden_ids_come_from_config(self):
        cfg = dataclasses.replace(self.cfg, forbidden_design_ids=frozenset({"DAEXTRA001"}))
        with self.assertRaises(GuardError):
            check_job(make_job("style_directions", target="DAEXTRA001"), cfg, SKELETON_ID, None)
        # the config, not a hard-coded id, decides
        self.assertIsNone(check_job(make_job("style_directions", target=ORIGINAL), cfg, SKELETON_ID, None))


if __name__ == "__main__":
    unittest.main()
