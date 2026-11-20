"""Studio configuration: a frozen dataclass loaded from config.json."""
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
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in _REQUIRED:
        if key not in data:
            raise ValueError(f"config missing key: {key}")
    return Config(
        **{k: Path(data[k]) for k in _PATH_KEYS},
        comfy_url=str(data["comfy_url"]),
        studio_port=int(data["studio_port"]),
        forbidden_design_ids=frozenset(data["forbidden_design_ids"]),
    )
