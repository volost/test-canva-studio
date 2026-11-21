"""Original-design guard. Pure checks, no I/O: a job that could write to the purchased original,
to a skeleton, or to an unknown design is refused here, before anything is written to the inbox.

Every doubt resolves to GuardError (fail closed): a missing or malformed state, a missing skeleton
id, a target that is not exactly the template's recorded copy.

Called only from jobs.create_job, BEFORE the job file is written (and before the one-writer check there).
This module must never be loosened to "allow" a doubtful case: it is the last line of defence between the
studio and the purchased original design (cfg.forbidden_design_ids) and the skeleton design. What it
refuses: any job whose target is a forbidden id; a Canva write job (apply_canva, verify) targeting the
skeleton; a write job whose target is not exactly state["canva_copy_id"]; apply_canva before the earlier
steps are approved. map_skeleton is read-only, so it may read the skeleton but never a forbidden id.
"""
from app.config import Config
from app.steps import can_start

JOB_TYPES = frozenset({"map_skeleton", "style_directions", "write_texts", "apply_canva", "verify"})
# Review ruling: forbidden_design_ids are refused as target for EVERY job type, but the skeleton id is
# refused as a target only for write types, because reading the skeleton is step 0 (map_skeleton).
# Types that WRITE to a Canva design. map_skeleton only reads, so it is not here.
CANVA_WRITE_TYPES = frozenset({"apply_canva", "verify"})


class GuardError(Exception):
    """A job was refused to protect an original design or the one-writer rule."""


def _norm(design_id) -> str | None:
    # Canva ids are case-sensitive, but refusing a case/whitespace variant of a protected id costs nothing.
    return design_id.strip().casefold() if isinstance(design_id, str) else None


def _is_id(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_job(job: dict, cfg: Config, skeleton_design_id: str, state: dict | None) -> None:
    """Raise GuardError unless `job` is safe to queue; return None when it is."""
    jtype = job.get("type")
    if jtype not in JOB_TYPES:
        raise GuardError(f"unknown job type: {jtype!r}")

    forbidden = {_norm(i) for i in cfg.forbidden_design_ids}
    target = job.get("target_design_id")
    if target is not None:
        if not _is_id(target):
            raise GuardError("target_design_id must be a non-empty string or null")
        if _norm(target) in forbidden:
            raise GuardError(f"target {target!r} is a protected original design")

    inputs = job.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}

    if jtype == "map_skeleton":
        read_id = inputs.get("design_id")
        if read_id is not None and (not _is_id(read_id) or _norm(read_id) in forbidden):
            raise GuardError(f"map_skeleton may not read the protected design {read_id!r}")

    if jtype not in CANVA_WRITE_TYPES:
        return

    # ---- Canva write types: apply_canva, verify ----
    if not _is_id(job.get("template")):
        raise GuardError(f"{jtype} needs a template")
    if not _is_id(skeleton_design_id):
        raise GuardError(f"{jtype}: the skeleton's design id is unknown, cannot prove the target is not the skeleton")
    skeleton_key = _norm(skeleton_design_id)
    if target is not None and _norm(target) == skeleton_key:
        raise GuardError(f"target {target!r} is the skeleton design")
    if not isinstance(state, dict):
        raise GuardError(f"{jtype}: template state is missing or malformed")

    copy_id = state.get("canva_copy_id")
    if copy_id is not None:
        if not _is_id(copy_id):
            raise GuardError("state canva_copy_id is malformed")
        if _norm(copy_id) in forbidden or _norm(copy_id) == skeleton_key:
            raise GuardError("state canva_copy_id points at an original design or the skeleton")

    # verify and apply_canva differ on purpose: verify needs an existing copy and must hit exactly it; apply_canva
    # may run with NO copy yet (target must then be null, and Claude creates the copy from the skeleton).
    if jtype == "verify":
        if copy_id is None:
            raise GuardError("verify: the template has no Canva copy yet")
        if target != copy_id:
            raise GuardError("verify must target exactly the template's own copy")
        return

    # apply_canva
    try:
        startable = can_start(state, "apply")
    except (KeyError, TypeError, AttributeError) as e:
        raise GuardError(f"apply_canva: state steps are malformed ({e!r})") from e
    if not startable:
        raise GuardError("apply_canva: earlier steps are not approved (texts may be stale)")
    if copy_id is None:
        if target is not None:
            raise GuardError("apply_canva: no copy is recorded, so a target cannot be named; Claude creates the copy")
    elif target != copy_id:
        raise GuardError("apply_canva must target exactly the template's own copy")
