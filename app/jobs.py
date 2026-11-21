"""Job inbox: the studio queues jobs as JSON files under <root>/jobs/{pending,running,done,failed}/.

The studio only ever CREATES job files (in pending/) and reads folders. It never moves, renames or
deletes a job file: moving between folders is the /test-canva-studio skill's work. At most one Canva write job
(apply_canva, verify) may sit in pending/ or running/; anything unreadable there counts as one.
"""
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import Config
from app.guard import CANVA_WRITE_TYPES, JOB_TYPES, GuardError, check_job
from app.store import CorruptJSON, read_json, skeleton_dir, template_dir, write_json_atomic

__all__ = [
    "CANVA_WRITE_TYPES",
    "GuardError",
    "STATE_FOLDERS",
    "canva_busy",
    "create_job",
    "list_jobs",
    "read_result",
]

# Folder = state. A job file lives in exactly one of these; the skill moves it pending -> running -> done|failed.
STATE_FOLDERS = ("pending", "running", "done", "failed")
_ACTIVE_FOLDERS = ("pending", "running")
_JOB_ID_RE = re.compile(r"\d{8}T\d{6}Z-[a-z_]+(?:-\d+)?")
_DESIGN_ID_RE = re.compile(r"[A-Za-z0-9_-]+")

# One create at a time: the server is threaded, and "check busy, then write" must not interleave.
_CREATE_LOCK = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _jobs_dir(cfg: Config) -> Path:
    return cfg.root / "jobs"


def _folder_files(cfg: Config, folder: str) -> list[Path]:
    return sorted(_jobs_dir(cfg).joinpath(folder).glob("*.json"))


# ---------------------------------------------------------------- Canva lock

def canva_busy(cfg: Config) -> bool:
    """True if a Canva write job is in pending/ or running/. Anything we cannot read there counts as
    busy: without reading it we cannot know it is not a Canva write job (fail closed)."""
    for folder in _ACTIVE_FOLDERS:
        try:
            files = _folder_files(cfg, folder)
        except OSError:
            return True
        for path in files:
            try:
                job = read_json(path)
            except (CorruptJSON, OSError):
                return True
            jtype = job.get("type")
            if not isinstance(jtype, str) or jtype not in JOB_TYPES or jtype in CANVA_WRITE_TYPES:
                return True  # a write job, or a type we do not recognise
    return False


# ---------------------------------------------------------------- limits (DESIGN 5.2, PLAYBOOK 6)

def _limits(cfg: Config, jtype: str, skeleton_design_id: str | None, target: str | None) -> list[str]:
    forbidden = ", ".join(sorted(cfg.forbidden_design_ids))
    if jtype in CANVA_WRITE_TYPES:
        if target is not None:
            edit = f"Редагувати лише дизайн {target} (копію цього шаблону); жоден інший дизайн не змінюється."
        else:
            edit = (
                "Редагувати лише дизайн-копію цього шаблону: нову копію скелета, яку це завдання створює; "
                "жоден інший дизайн не змінюється."
            )
        return [
            edit,
            f"Ніколи не редагувати скелет ({skeleton_design_id}) і оригінал: {forbidden}.",
            "Не чіпати форму, вбудовані блоки і структуру конверта.",
            "Без перегрупування елементів і без нових сторінок.",
            "Без публікації.",
            "Без видалень.",
            "Дві однакові невдачі виклику інструмента поспіль — стоп і нотатка.",
        ]
    if jtype == "map_skeleton":
        return [
            f"Лише читання: нічого не редагувати в Canva ні в скелеті, ні в оригіналі ({forbidden}).",
            "Без публікації.",
            "Без видалень.",
            "Дві однакові невдачі виклику інструмента поспіль — стоп і нотатка.",
        ]
    return ["Не звертатися до Canva.", "Без видалень файлів."]


# ---------------------------------------------------------------- create

def _resolve_skeleton_design_id(cfg: Config, skeleton: str, inputs: dict, write: bool) -> str | None:
    """R3: skeletons/<s>/map.json["design_id"] if that file exists, else inputs["design_id"].
    For a write job, an existing but unusable map is a GuardError, never a silent fallback."""
    map_path = skeleton_dir(cfg, skeleton) / "map.json"
    try:
        map_path.stat()
        has_map = True
    except FileNotFoundError:
        has_map = False
    except OSError:
        has_map = True  # cannot tell: treat as present-but-unusable, never as absent
    if has_map:
        try:
            design_id = read_json(map_path).get("design_id")
        except (CorruptJSON, OSError):
            design_id = None
        if isinstance(design_id, str) and design_id.strip():
            return design_id
        if write:
            raise GuardError(f"skeleton map {map_path} is unreadable or has no design_id")
        return None
    design_id = inputs.get("design_id")
    return design_id if isinstance(design_id, str) and design_id.strip() else None


def _read_state(cfg: Config, template: str, write: bool) -> dict | None:
    path = template_dir(cfg, template) / "state.json"
    try:
        return read_json(path)
    except (CorruptJSON, OSError) as e:
        if write:
            raise GuardError(f"template state {path} is missing or corrupt: {e}") from e
        return None


def _new_job_id(cfg: Config, jtype: str, stamp: str) -> str:
    base = f"{stamp}-{jtype}"
    taken = {p.name for folder in STATE_FOLDERS for p in _jobs_dir(cfg).joinpath(folder).glob("*.json")}
    job_id, n = base, 1
    while f"{job_id}.json" in taken:
        n += 1
        job_id = f"{base}-{n}"
    return job_id


def create_job(
    cfg: Config,
    type: str,
    skeleton: str,
    template: str | None,
    inputs: dict,
    target_design_id: str | None,
) -> dict:
    """Validate, run the original-design guard, then write jobs/pending/<id>.json. Returns the job.

    ValueError: malformed arguments. GuardError: the job would be unsafe or a Canva writer is busy.
    Nothing is written unless every check passes."""
    if type not in JOB_TYPES:
        raise ValueError(f"unknown job type {type!r}: use one of {sorted(JOB_TYPES)}")
    skeleton_dir(cfg, skeleton)  # name validation (ValueError)
    if template is not None:
        template_dir(cfg, template)
    if not isinstance(inputs, dict):
        raise ValueError("inputs must be a dict")
    if target_design_id is not None and not (
        isinstance(target_design_id, str) and _DESIGN_ID_RE.fullmatch(target_design_id)
    ):
        raise ValueError(f"invalid target_design_id {target_design_id!r}: use letters, digits, - and _")

    write = type in CANVA_WRITE_TYPES
    # Review ruling: the skeleton id comes from the skeleton's map.json when that file exists, else from
    # inputs["design_id"] (only map_skeleton passes it, before any map exists). For a write job a missing or
    # corrupt map, or a missing/corrupt template state, is a GuardError and never a fallback.
    skeleton_design_id = _resolve_skeleton_design_id(cfg, skeleton, inputs, write)
    state = None
    if template is not None:
        state = _read_state(cfg, template, write)
        if write and state.get("skeleton") != skeleton:
            raise GuardError(f"template {template!r} belongs to skeleton {state.get('skeleton')!r}, not {skeleton!r}")

    now = _utcnow()
    job = {
        "id": "",
        "type": type,
        "template": template,
        "skeleton": skeleton,
        "target_design_id": target_design_id,
        "created_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": inputs,
        "limits": _limits(cfg, type, skeleton_design_id, target_design_id),
    }
    # check_job needs the id-less job only for its fields; the guard runs BEFORE any write
    check_job(job, cfg, skeleton_design_id, state)

    # The busy check and the write must be one atomic step, else two threads could both see "free" and
    # both queue a Canva writer.
    with _CREATE_LOCK:
        if write and canva_busy(cfg):
            raise GuardError("a Canva job is already pending or running: one writer at a time")
        job["id"] = _new_job_id(cfg, type, now.strftime("%Y%m%dT%H%M%SZ"))
        write_json_atomic(_jobs_dir(cfg) / "pending" / f"{job['id']}.json", job)
    return job


# ---------------------------------------------------------------- list

def list_jobs(cfg: Config) -> list[dict]:
    """Every *.json job in the four folders, oldest first. Never raises on a bad file: an unreadable
    one is listed with state "corrupt" and its id taken from the file name."""
    now = time.time()
    rows = []
    for folder in STATE_FOLDERS:
        try:
            paths = _folder_files(cfg, folder)
        except OSError:
            continue
        for path in paths:
            try:
                mtime = path.stat().st_mtime
            except FileNotFoundError:
                continue  # moved by /test-canva-studio between listing and stat
            except OSError:
                mtime = now
            age_s = max(0, int(now - mtime))
            try:
                job = dict(read_json(path))
                job.setdefault("id", path.stem)
                job["state"] = folder
            except FileNotFoundError:
                continue
            except (CorruptJSON, OSError) as e:
                job = {"id": path.stem, "state": "corrupt", "age_s": age_s, "error": str(e)}
            job["age_s"] = age_s
            rows.append((mtime, folder, str(job["id"]), job))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return [r[3] for r in rows]


# ---------------------------------------------------------------- result

def read_result(cfg: Config, job: dict) -> dict | None:
    """The job's result file, or None if it does not exist (or the job names no result location).
    A corrupt result yields {"status": "corrupt", "summary": reason} instead of raising."""
    job_id = job.get("id")
    if not isinstance(job_id, str) or not _JOB_ID_RE.fullmatch(job_id):
        return {"status": "corrupt", "summary": f"job has no valid id: {job_id!r}"}
    try:
        if job.get("type") == "map_skeleton":
            base = skeleton_dir(cfg, job.get("skeleton"))
        elif job.get("template") is not None:
            base = template_dir(cfg, job["template"])
        else:
            return None
    except ValueError as e:
        return {"status": "corrupt", "summary": f"job names an invalid folder: {e}"}
    path = base / "jobs" / f"{job_id}.result.json"
    try:
        return read_json(path)
    except FileNotFoundError:
        return None
    except CorruptJSON:
        return {"status": "corrupt", "summary": f"result file {path.name} is not a valid JSON object"}
    except OSError as e:
        return {"status": "corrupt", "summary": f"result file {path.name} cannot be read: {e.strerror or e}"}
