"""Step states of a template. All functions are pure: they return a modified deep copy of `state`.

STEPS run in order style -> images -> texts -> apply -> verify; a step can start only when every earlier
step is approved (can_start). Persisting the result is the caller's job (api.py, under store.STATE_LOCK).

The "stale cascade": when an earlier step changes (reopen) or is re-requested (api._request ->
invalidate_after), every LATER step that is approved/review/waiting_claude becomes `stale`, so work built
on the old result can no longer be approved or applied to Canva by accident. A stale step must be redone.
"""
import copy
from datetime import datetime, timezone

STEPS = ("style", "images", "texts", "apply", "verify")
STATUSES = ("draft", "waiting_claude", "review", "approved", "stale")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_step(step: str) -> None:
    if step not in STEPS:
        raise ValueError(f"unknown step: {step!r}")


def _stamp(state: dict, step: str, status: str) -> None:
    state["steps"][step] = {"status": status, "updated_utc": now_utc()}


def set_status(state: dict, step: str, status: str) -> dict:
    """Return a copy of `state` with `step` set to `status` and `updated_utc` stamped."""
    _check_step(step)
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status!r}")
    out = copy.deepcopy(state)
    _stamp(out, step, status)
    return out


def can_start(state: dict, step: str) -> bool:
    """True when every step before `step` is approved."""
    _check_step(step)
    before = STEPS[: STEPS.index(step)]
    return all(state["steps"][s]["status"] == "approved" for s in before)


def approve(state: dict, step: str) -> dict:
    """Return a copy with `step` approved; ValueError unless `can_start(state, step)`."""
    if not can_start(state, step):
        raise ValueError(f"cannot approve {step!r}: earlier steps are not approved")
    return set_status(state, step, "approved")


def invalidate_after(state: dict, step: str) -> dict:
    """Return a copy with every step after `step` that is approved, review or waiting_claude marked `stale`.
    A step waiting for Claude is stale too: its result will be built on data that has changed."""
    _check_step(step)
    out = copy.deepcopy(state)
    # waiting_claude is included on purpose (review finding: an old job finishing could otherwise move a step
    # that was built on outdated data to `review` and get it approved). api._reconcile_jobs only advances
    # waiting_claude steps, so a step marked stale here never jumps back to review when the old job ends.
    for later in STEPS[STEPS.index(step) + 1 :]:
        if out["steps"][later]["status"] in ("approved", "review", "waiting_claude"):
            _stamp(out, later, "stale")
    return out


def reopen(state: dict, step: str) -> dict:
    """Return a copy with `step` back in `review` and every later approved/review/waiting_claude step marked
    `stale` (changed in fix round 1: a later step waiting for Claude used to be left alone, so its result
    could be approved on top of old data)."""
    return invalidate_after(set_status(state, step, "review"), step)
