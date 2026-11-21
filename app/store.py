"""Template store on disk: atomic JSON files and template folders. Nothing here deletes anything.

Callers: every other app/ module reads and writes JSON through read_json / write_json_atomic, and gets
paths from template_dir / skeleton_dir. Those two validate the name against _NAME_RE, which is also what
keeps a name from ever containing "/" or ".." (path traversal), so never build a templates/ or skeletons/
path by hand from user input.

STATE_LOCK (below) is shared across modules: assets.py and api.py (and tickets.py when it saves) take the
SAME lock for every state.json read-modify-write. Do not introduce a second lock for state.json.
"""
import json
import os
import re
import tempfile
import threading
from pathlib import Path

from app.config import Config
from app.steps import STEPS, now_utc

# One process-wide lock for every read-modify-write of a template's state.json (chosen files in
# assets.py, step statuses elsewhere). Re-entrant; hold it across the whole read -> change -> write.
# Why one global RLock rather than one per template: the server is threaded and there are only a few
# templates, so contention is irrelevant while a missed lock would silently lose a step change or a chosen
# file (two handlers reading the same old state, last writer wins). RLock because a handler that already
# holds it calls helpers that take it again.
# Lock order across the app: tickets.GEN_LOCK is always taken BEFORE STATE_LOCK, never the other way round
# (taking them in opposite orders in two threads would deadlock).
STATE_LOCK = threading.RLock()

_NAME_RE = re.compile(r"[a-z0-9-]{1,40}")


class CorruptJSON(Exception):
    """A JSON file exists but cannot be parsed."""

    def __init__(self, path):
        super().__init__(f"corrupt JSON: {path}")
        self.path = Path(path)


def write_json_atomic(path: Path, data) -> None:
    """Write `data` as UTF-8 JSON via a temp file in the same folder, then os.replace."""
    path = Path(path)
    # Temp file in the SAME folder, because os.replace is only atomic within one filesystem. A reader
    # (the studio UI polling, or the /test-canva-studio skill) therefore sees either the old or the new file,
    # never a half-written one. fsync before replace so a crash cannot leave an empty target.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        # remove only our own temp file; the target is never touched before os.replace
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def read_json(path: Path) -> dict:
    """Read a JSON object. Invalid UTF-8, invalid JSON, or JSON that is not an object -> CorruptJSON."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:  # JSONDecodeError and UnicodeDecodeError are both ValueError
        raise CorruptJSON(path) from e
    if not isinstance(data, dict):
        raise CorruptJSON(path)
    return data


def _check_name(kind: str, name: str) -> str:
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid {kind} name {name!r}: use [a-z0-9-], 1-40 characters")
    return name


def template_dir(cfg: Config, name: str) -> Path:
    return cfg.root / "templates" / _check_name("template", name)


def skeleton_dir(cfg: Config, name: str) -> Path:
    return cfg.root / "skeletons" / _check_name("skeleton", name)


def create_template(cfg: Config, name: str, skeleton: str) -> Path:
    """Create templates/<name>/ with a fresh state.json; FileExistsError if it exists."""
    _check_name("skeleton", skeleton)
    d = template_dir(cfg, name)
    d.mkdir(parents=True, exist_ok=False)
    now = now_utc()
    state = {
        "skeleton": skeleton,
        "canva_copy_id": None,
        "chosen": {},
        "steps": {s: {"status": "draft", "updated_utc": now} for s in STEPS},
    }
    write_json_atomic(d / "state.json", state)
    return d


def list_templates(cfg: Config) -> list[str]:
    base = cfg.root / "templates"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and (p / "state.json").is_file())
