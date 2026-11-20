"""Minimal ComfyUI HTTP client (stdlib only): Z-Image Turbo text-to-image.

Talks only to cfg.comfy_url: POST /prompt, GET /history/<id>, GET /view.
The node graph reproduces pilot/tools/comfy_generate.py.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CLIENT_ID = "canva-studio"
_DOWN = "ComfyUI недоступний за адресою {url}: запустіть ComfyUI і повторіть."


class ComfyError(Exception):
    pass


def build_graph(prompt: str, width: int, height: int, seed: int, prefix: str) -> dict:
    if width % 16 or height % 16 or width <= 0 or height <= 0:
        raise ValueError("width and height must be positive multiples of 16")
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
        "7": {"class_type": "EmptySD3LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0],
                         "latent_image": ["7", 0], "seed": seed, "steps": 8, "cfg": 1,
                         "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
    }


def _base(cfg) -> str:
    return cfg.comfy_url.rstrip("/")


def _open(cfg, path, payload=None, timeout=30):
    """Return response bytes; ComfyError on any failure (down => 'ComfyUI недоступний')."""
    url = _base(cfg) + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise ComfyError(f"ComfyUI відповів помилкою HTTP {e.code} на {path}: {body}") from e
    except (urllib.error.URLError, OSError) as e:
        raise ComfyError(_DOWN.format(url=_base(cfg))) from e


def _json(cfg, path, payload=None, timeout=30):
    raw = _open(cfg, path, payload, timeout)
    try:
        return json.loads(raw)
    except ValueError as e:
        raise ComfyError(f"ComfyUI повернув неочікувану відповідь на {path}") from e


def ping(cfg, timeout: float = 3.0) -> bool:
    try:
        urllib.request.urlopen(_base(cfg) + "/system_stats", timeout=timeout).close()
        return True
    except Exception:
        return False


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    n = 1
    while True:
        cand = path.with_name(f"{path.stem}-{n}{path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def generate(cfg, prompt, width, height, seed, prefix, out_dir: Path, timeout=1500,
             poll_interval: float = 1.0) -> list[Path]:
    started = time.monotonic()
    graph = build_graph(prompt, width, height, seed, prefix)
    resp = _json(cfg, "/prompt", {"prompt": graph, "client_id": CLIENT_ID}, timeout=60)
    pid = resp.get("prompt_id") if isinstance(resp, dict) else None
    if not pid:
        raise ComfyError(f"ComfyUI не повернув prompt_id: {str(resp)[:300]}")
    if resp.get("node_errors"):
        raise ComfyError(f"ComfyUI відхилив граф: {json.dumps(resp['node_errors'], ensure_ascii=False)[:500]}")
    quoted = urllib.parse.quote(str(pid), safe="")
    while True:
        if time.monotonic() - started > timeout:
            raise ComfyError(f"Час очікування вичерпано ({timeout} с) для завдання {pid}")
        hist = _json(cfg, f"/history/{quoted}", timeout=30)
        if isinstance(hist, dict) and pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") != "success":
                raise ComfyError(f"ComfyUI не зміг згенерувати: {json.dumps(status, ensure_ascii=False)[:500]}")
            images = [i for o in entry.get("outputs", {}).values() for i in o.get("images", [])]
            if not images:
                raise ComfyError("ComfyUI завершив завдання без жодного зображення")
            break
        time.sleep(poll_interval)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for img in images:
        name = Path(str(img["filename"])).name  # never trust a path from the server
        q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                    "type": img.get("type", "output")})
        data = _open(cfg, "/view?" + q, timeout=60)
        dest = _unique(out_dir / name)
        dest.write_bytes(data)
        saved.append(dest)
    return saved
