import copy
import unittest

from app.steps import STATUSES, STEPS, approve, can_start, reopen, set_status


def make_state(status="draft"):
    return {
        "skeleton": "s",
        "canva_copy_id": None,
        "chosen": {},
        "steps": {s: {"status": status, "updated_utc": "2000-01-01T00:00:00Z"} for s in STEPS},
    }


def statuses(state):
    return {s: state["steps"][s]["status"] for s in STEPS}


class StepsTests(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(STEPS, ("style", "images", "texts", "apply", "verify"))
        self.assertEqual(set(STATUSES), {"draft", "waiting_claude", "review", "approved", "stale"})

    def test_set_status_stamps_time(self):
        s = set_status(make_state(), "style", "review")
        self.assertEqual(s["steps"]["style"]["status"], "review")
        self.assertNotEqual(s["steps"]["style"]["updated_utc"], "2000-01-01T00:00:00Z")
        self.assertEqual(s["steps"]["images"]["updated_utc"], "2000-01-01T00:00:00Z")

    def test_set_status_rejects_bad_input(self):
        for step, status in (("nope", "review"), ("style", "nope"), ("", "draft")):
            with self.subTest(step=step, status=status):
                with self.assertRaises(ValueError):
                    set_status(make_state(), step, status)

    def test_set_status_does_not_mutate_input(self):
        orig = make_state()
        before = copy.deepcopy(orig)
        out = set_status(orig, "style", "review")
        self.assertEqual(orig, before)
        self.assertIsNot(out, orig)

    def test_can_start_first_step_always(self):
        self.assertTrue(can_start(make_state(), "style"))

    def test_can_start_requires_previous_approved(self):
        s = make_state("approved")
        self.assertTrue(can_start(s, "apply"))
        s["steps"]["texts"]["status"] = "stale"
        self.assertFalse(can_start(s, "apply"))
        s2 = make_state("approved")
        s2["steps"]["style"]["status"] = "review"
        self.assertFalse(can_start(s2, "verify"))

    def test_can_start_unknown_step(self):
        with self.assertRaises(ValueError):
            can_start(make_state(), "nope")

    def test_approve_requires_can_start(self):
        s = make_state()
        with self.assertRaises(ValueError):
            approve(s, "images")
        s = approve(s, "style")
        self.assertEqual(s["steps"]["style"]["status"], "approved")
        s = approve(s, "images")
        self.assertEqual(s["steps"]["images"]["status"], "approved")

    def test_reopen_marks_later_stale(self):
        s = reopen(make_state("approved"), "images")
        self.assertEqual(
            statuses(s),
            {"style": "approved", "images": "review", "texts": "stale", "apply": "stale", "verify": "stale"},
        )

    def test_reopen_leaves_other_later_statuses(self):
        s = make_state("draft")
        s["steps"]["texts"]["status"] = "review"
        s["steps"]["apply"]["status"] = "waiting_claude"
        s = reopen(s, "style")
        self.assertEqual(
            statuses(s),
            {"style": "review", "images": "draft", "texts": "stale", "apply": "waiting_claude", "verify": "draft"},
        )

    def test_reopen_rejects_unknown_step_and_does_not_mutate(self):
        orig = make_state("approved")
        before = copy.deepcopy(orig)
        with self.assertRaises(ValueError):
            reopen(orig, "nope")
        reopen(orig, "images")
        self.assertEqual(orig, before)


if __name__ == "__main__":
    unittest.main()
