"""Step states of a template. All functions are pure: they return a modified deep copy of `state`."""
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


def reopen(state: dict, step: str) -> dict:
    """Return a copy with `step` back in `review` and later approved/review steps marked `stale`."""
    _check_step(step)
    out = set_status(state, step, "review")
    for later in STEPS[STEPS.index(step) + 1 :]:
        if out["steps"][later]["status"] in ("approved", "review"):
            _stamp(out, later, "stale")
    return out
