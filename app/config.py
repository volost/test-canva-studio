"""Studio configuration: a frozen dataclass loaded from config.json.

forbidden_design_ids is the list of protected original Canva designs; guard.py and jobs.py refuse to
target them. Keep it a frozenset of whole strings: a bare string would silently become a set of
characters (an earlier bug fixed in review), which is why load_config insists on a list of non-empty strings.

config.json holds this machine's absolute paths, so it is NOT in git (see README "Setup"): a new developer copies the
committed config.example.json to config.json and edits the paths. load_config therefore fails with a message that
says so when the file is missing (the most likely first-run mistake).
"""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    root: Path
    python: Path
    comfy_main: Path
    models_dir: Path
    extra_model_paths: Path
    comfy_url: str
    studio_port: int
    forbidden_design_ids: frozenset[str]


_PATH_KEYS = ("root", "python", "comfy_main", "models_dir", "extra_model_paths")
_REQUIRED = _PATH_KEYS + ("comfy_url", "studio_port", "forbidden_design_ids")


def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.is_file():
        # Developer-facing (English) on purpose: it is a setup error of a fresh clone, not a message of the studio UI.
        raise FileNotFoundError(
            f"{path} not found. config.json is local to each machine and is not in git: "
            f"copy config.example.json to config.json and edit the paths (see README.md, section Setup).")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in _REQUIRED:
        if key not in data:
            raise ValueError(f"config missing key: {key}")
    ids = data["forbidden_design_ids"]
    if not isinstance(ids, list) or not all(isinstance(i, str) and i for i in ids):
        raise ValueError("config key forbidden_design_ids must be a list of non-empty strings")
    return Config(
        **{k: Path(data[k]) for k in _PATH_KEYS},
        comfy_url=str(data["comfy_url"]),
        studio_port=int(data["studio_port"]),
        forbidden_design_ids=frozenset(ids),
    )
