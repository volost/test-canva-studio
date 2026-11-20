"""Template store on disk: atomic JSON files and template folders. Nothing here deletes anything."""
import json
import os
import re
import tempfile
from pathlib import Path

from app.config import Config
from app.steps import STEPS, now_utc

_NAME_RE = re.compile(r"[a-z0-9-]{1,40}")


class CorruptJSON(Exception):
    """A JSON file exists but cannot be parsed."""

    def __init__(self, path):
        super().__init__(f"corrupt JSON: {path}")
        self.path = Path(path)


def write_json_atomic(path: Path, data) -> None:
    """Write `data` as UTF-8 JSON via a temp file in the same folder, then os.replace."""
    path = Path(path)
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
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except ValueError as e:
        raise CorruptJSON(path) from e


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
