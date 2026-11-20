"""Asset pipeline: generation plan, post-processing, checks (with controls), versions, manifest.

Flow: ``submit_generations`` puts one GenQueue job per asset (raw ComfyUI files go to assets/raw/);
the caller polls ``process_finished`` (in its own thread, so the queue stays single-worker), which
runs ``postprocess`` on every finished job and writes a new version ``assets/<asset>__v<n>.<ext>``.
Versions are never overwritten or deleted. The first version of an asset is chosen automatically,
later ones only through ``choose``. Every state.json read-modify-write here (choose, auto-choose) holds
``app.store.STATE_LOCK``; other code that changes state.json (step statuses) must take the same lock.
Messages shown to the user are Ukrainian; every problem string
starts with a stable [code].
"""
import hashlib
import os
import random
import re
import tempfile
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from app.imaging.core import aspect_error, cover_crop, pad_to_frame
from app.imaging.cutout import solid_cutout, watercolour_to_alpha
from app.imaging.envelope import check_envelope, compose_envelope
from app.imaging.sheet import contact_sheet
from app.steps import now_utc
from app.store import STATE_LOCK, read_json, write_json_atomic

OPAQUE_KINDS = ("photo", "texture")
CUTOUT_KINDS = ("watercolour", "solid")
TOLERANCE = 0.005          # 0.5 % frame aspect
GEN_TOLERANCE = 0.03       # generation sizes are multiples of 64; postprocess makes the aspect exact
PAD_MARGIN = 0.02          # share of the canvas kept free around a padded cut-out
COVERAGE = (0.005, 0.98)   # sensible alpha coverage of a transparent asset
WHITE_HINT = ", isolated on a plain pure white background, soft even light, no shadow, no border"
_NAME = re.compile(r"(?!.*__)[A-Za-z0-9_-]+")
_AUTO = object()           # "use the chosen seal from state.json"
_LOCK = threading.RLock()  # version numbers, ticket claims
_CLAIMS = {}               # job_id -> "running" | "done": a ticket is postprocessed at most once per process


class AssetError(Exception):
    """A clear, user-showable reason why an asset could not be processed."""


# ---- plan --------------------------------------------------------------------------------------
def gen_size(frame, megapixels=1.5):
    """(w, h), multiples of 64, about `megapixels`, aspect within 3 % of the frame's."""
    fw, fh = frame
    if not (fw > 0 and fh > 0 and megapixels > 0):
        raise ValueError(f"bad frame or megapixels: {frame!r}, {megapixels!r}")
    a, best = fw / fh, None
    for w in range(64, 2049, 64):
        h = max(64, round(w / a / 64) * 64)
        if h > 2048:
            continue
        err = abs(w / h / a - 1)
        key = (False, abs(w * h - megapixels * 1e6)) if err <= GEN_TOLERANCE else (True, err)
        if best is None or key < best[0]:
            best = (key, (w, h))
    if best is None:
        raise ValueError(f"frame aspect {frame!r} is too extreme to generate")
    return best[1]


def plan_generations(m, style):
    """One entry per asset: asset, prompt (as in the style), width, height, kind.

    A composed asset generates only its texture, at the envelope section's aspect."""
    prompts = style.get("image_prompts") or {}
    out = []
    for asset, spec in m["assets"].items():
        prompt, kind = prompts.get(asset), spec.get("kind")
        if not (isinstance(prompt, str) and prompt.strip()):
            raise ValueError(f"image_prompts: asset {asset!r} has no prompt")
        if kind == "composed":
            frame = (m.get("envelope") or {}).get("section_px")
            if not frame:
                raise ValueError(f"asset {asset!r} is composed but the map has no envelope block")
        elif kind in OPAQUE_KINDS + CUTOUT_KINDS:
            frame = spec["frame"]
        else:
            raise ValueError(f"asset {asset!r}: unknown kind {kind!r}")
        w, h = gen_size(frame)
        out.append({"asset": asset, "prompt": prompt, "width": w, "height": h, "kind": kind})
    return out


def final_prompt(kind, prompt):
    """Cut-outs need a near-white ground; the hint is added when the prompt does not say so."""
    if kind in CUTOUT_KINDS and "white background" not in prompt.lower():
        return prompt.rstrip(" .,") + WHITE_HINT
    return prompt


# ---- versions ----------------------------------------------------------------------------------
def _scan(out_dir, asset):
    """[(n, name, layer)] of every version file of `asset` in out_dir (layer None|cover|flap|body)."""
    rx = re.compile(rf"{re.escape(asset)}__(?:(cover|flap|body)__)?v(\d+)\.(?:jpg|png)")
    found = []
    for p in Path(out_dir).iterdir() if Path(out_dir).is_dir() else []:
        mt = rx.fullmatch(p.name)
        if mt:
            found.append((int(mt.group(2)), p.name, mt.group(1)))
    return sorted(found)


def list_versions(out_dir, asset):
    """[(n, file)] sorted by n; a composed version is listed (as its cover) only when cover, flap and
    body all exist for that n, so a half-written set can never be chosen."""
    found = _scan(out_dir, asset)
    layers = {}
    for n, _, layer in found:
        layers.setdefault(n, set()).add(layer)
    return [(n, name) for n, name, layer in found
            if layer is None or (layer == "cover" and {"cover", "flap", "body"} <= layers[n])]


def next_version(out_dir, asset):
    return 1 + max((n for n, _, _ in _scan(out_dir, asset)), default=0)


def _save_new(img, dest, fmt):
    """Write via a temp file and hard-link it into place: an existing file is never replaced."""
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    os.close(fd)
    try:
        if fmt == "JPEG":
            img.convert("RGB").save(tmp, format="JPEG", quality=94, subsampling=0)
        else:
            img.save(tmp, format="PNG")
        try:
            os.link(tmp, dest)
        except FileExistsError:
            raise AssetError(f"{dest.name} уже існує; перезапис заборонено") from None
    finally:
        os.unlink(tmp)  # our own temp file


def _chosen(tdir):
    p = Path(tdir) / "state.json"
    return (read_json(p).get("chosen") or {}) if p.is_file() else {}


def choose(template_dir, asset, file):
    """Set state["chosen"][asset] = file (an existing version of that asset). Steps are not touched."""
    tdir = Path(template_dir)
    if file not in {name for _, name in list_versions(tdir / "assets", asset)}:
        raise AssetError(f"{file!r} не є версією ассета {asset!r}")
    with STATE_LOCK:
        st = read_json(tdir / "state.json")
        st.setdefault("chosen", {})[asset] = file
        write_json_atomic(tdir / "state.json", st)


# ---- postprocess -------------------------------------------------------------------------------
def _exact_size(frame, k):
    """(W, H, scale) near k x frame whose aspect is within 0.5 % of the frame's (tiny frames need a bump)."""
    for i in range(60):
        s = k * (1 + 0.02 * i)
        W, H = max(1, round(frame[0] * s)), max(1, round(frame[1] * s))
        if aspect_error((W, H), frame) < TOLERANCE:
            return W, H, s
    raise AssetError(f"рамку {tuple(frame)} не можна відтворити з точністю 0,5 %")


def _fit(img, size):
    out = cover_crop(img, size)
    return out if out.size == tuple(size) else out.resize(tuple(size), Image.LANCZOS)


def _load_seal(m, out_dir, seal):
    if seal is _AUTO:
        name = (m.get("envelope") or {}).get("seal_asset")
        f = _chosen(out_dir.parent).get(name) if name else None
        seal = out_dir / f if f else None
    if seal is None:
        return None
    try:
        with Image.open(seal) as im:
            im.load()
            return im.convert("RGBA")
    except Exception as e:
        raise AssetError(f"обраний штамп {Path(seal).name} не відкривається: {e}") from e


def _render(asset, img, spec, m, out_dir, seal):
    """[(layer, image, format)] for one new version."""
    kind, frame = spec.get("kind"), spec.get("frame")
    if kind in OPAQUE_KINDS:
        W, H, _ = _exact_size(frame, min(img.width / frame[0], img.height / frame[1]))
        return [(None, _fit(img, (W, H)), "JPEG")]
    if kind in CUTOUT_KINDS:
        cut = watercolour_to_alpha(img) if kind == "watercolour" else solid_cutout(img)
        _, _, s = _exact_size(frame, max(1.0, max(img.size) / max(frame)))
        return [(None, pad_to_frame(cut, frame, s, margin=PAD_MARGIN), "PNG")]
    if kind == "composed":
        geom = m.get("envelope")
        if not geom:
            raise AssetError("у карті немає блоку envelope")
        size = tuple(round(v * 2) for v in geom["section_px"])
        cover, flap, body = compose_envelope(_fit(img, size), geom, scale=2, seal=_load_seal(m, out_dir, seal))
        return [("cover", cover, "JPEG"), ("flap", flap, "PNG"), ("body", body, "PNG")]
    raise AssetError(f"невідомий тип ассета {kind!r}")


def postprocess(asset, src, m, out_dir, *, seal=_AUTO):
    """Process the raw image `src` into a NEW version in out_dir; returns its path (a composed
    asset: the cover; flap and body share the number). `seal`: a path or None to override the
    chosen seal. Every failure is an AssetError with a clear message; nothing is half-written."""
    out_dir = Path(out_dir)
    try:
        if not _NAME.fullmatch(asset):
            raise AssetError("недійсне ім'я ассета")
        spec = (m.get("assets") or {}).get(asset)
        if spec is None:
            raise AssetError("такого ассета немає в карті")
        with Image.open(src) as im:
            im.load()
            img = im.convert("RGB")
        layers = _render(asset, img, spec, m, out_dir, seal)
        out_dir.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            n = next_version(out_dir, asset)
            paths = []
            for layer, im, fmt in layers:
                mid = f"__{layer}" if layer else ""
                p = out_dir / f"{asset}{mid}__v{n}.{'jpg' if fmt == 'JPEG' else 'png'}"
                _save_new(im, p, fmt)
                paths.append(p)
        return paths[0]
    except AssetError as e:
        raise AssetError(f"{asset}: {e}") from e
    except Exception as e:  # ValueError from the imaging layer, unreadable file, ... -> one clear error
        raise AssetError(f"{asset}: {type(e).__name__}: {e}") from e


# ---- checks ------------------------------------------------------------------------------------
def _open(path):
    with Image.open(path) as im:
        im.load()
        return im.copy()


def check_asset(path, spec):
    """Problems of one finished file against its map entry (empty = good)."""
    try:
        im = _open(path)
    except Exception as e:
        return [f"[open] не відкривається: {type(e).__name__}: {e}"]
    out = []
    try:
        err = aspect_error(im.size, spec["frame"])
        if err > TOLERANCE:
            out.append(f"[aspect] пропорція {im.width}x{im.height} відхиляється від рамки {spec['frame']} на {err * 100:.2f} % (> 0.5 %)")
    except (KeyError, TypeError, ValueError):
        out.append(f"[spec] немає придатної рамки в {spec!r}")
    has_alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
    a = np.asarray(im.convert("RGBA").getchannel("A")) if has_alpha else None
    transparent = spec.get("transparent", spec.get("kind") in CUTOUT_KINDS)
    if transparent and im.mode != "RGBA":
        out.append(f"[alpha] прозорий ассет має бути RGBA, а не {im.mode}")
    elif transparent:
        cov = float((a > 8).mean())
        if a.min() >= 250 or cov > COVERAGE[1]:
            out.append(f"[alpha] майже непрозорий (покриття {cov:.3f}, мін. альфа {a.min()})")
        elif cov < COVERAGE[0]:
            out.append(f"[alpha] майже порожній (покриття {cov:.4f})")
    elif a is not None and a.min() < 255:
        out.append("[opaque] непрозорий ассет має прозорі пікселі")
    return out


def _check_env_files(cover, flap, body, geom, seal_path):
    try:
        seal = _open(seal_path).convert("RGBA") if seal_path else None
        return check_envelope(_open(cover), _open(flap), _open(body), geom, seal=seal, seal_expected=seal is not None)
    except Exception as e:
        return [f"[open] конверт не перевірено: {type(e).__name__}: {e}"]


def _env_problems(asset, f, m, out, chosen):
    """Check the three envelope layers of the chosen cover `f`: {file: [problems]}."""
    mt, geom = re.fullmatch(rf"{re.escape(asset)}__cover__v(\d+)\.jpg", f), m.get("envelope")
    if not mt or not geom:
        return {f: ["[envelope] обраний файл не є обкладинкою конверта або немає блоку envelope"]}
    flap, body = f"{asset}__flap__v{mt.group(1)}.png", f"{asset}__body__v{mt.group(1)}.png"
    sealf = chosen.get(geom.get("seal_asset") or "")
    probs = check_asset(out / f, {"kind": "composed", "frame": geom.get("section_px"), "transparent": False})
    probs += ["[envelope] " + p for p in _check_env_files(out / f, out / flap, out / body, geom, out / sealf if sealf else None)]
    rest = {n: ([] if (out / n).is_file() else ["[open] файла немає"]) for n in (flap, body)}
    return {f: probs, **rest}


def run_controls():
    """Run the SAME check functions on deliberately bad (and good) synthetic files.

    Returns (ok, detail). ok only if every bad file was rejected AND every good one accepted."""
    detail, ok = [], True
    geom = {"section_px": [400, 300], "tip": [200, 170], "left_top": [0, 20], "right_top": [400, 20]}
    clear, solid = Image.new("RGBA", (100, 100), (0, 0, 0, 0)), Image.new("RGBA", (100, 100), (9, 9, 9, 255))
    dot = clear.copy()
    dot.paste((200, 50, 50, 255), (30, 30, 70, 70))
    holed = Image.new("RGBA", (100, 100), (9, 9, 9, 255))
    holed.putpixel((1, 1), (9, 9, 9, 0))
    photo, tr = {"kind": "photo", "frame": [100, 100]}, {"kind": "watercolour", "frame": [100, 100], "transparent": True}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        files = {"wrong aspect": (Image.new("RGB", (300, 100)), photo, True),
                 "opaque 'transparent'": (solid, tr, True),
                 "empty 'transparent'": (clear, tr, True),
                 "transparent photo": (holed, photo, True),
                 "good photo": (Image.new("RGB", (100, 100)), photo, False),
                 "good transparent": (dot, tr, False)}
        cases = []
        for name, (img, spec, should_reject) in files.items():
            p = td / (name.replace(" ", "_").replace("'", "") + ".png")
            img.save(p)
            cases.append((name, check_asset(p, spec), should_reject))
        bad = td / "unopenable.png"
        bad.write_bytes(b"not an image")
        cases.append(("unopenable file", check_asset(bad, photo), True))
        cover, flap, body = compose_envelope(Image.new("RGB", (800, 600), (200, 190, 170)), geom, scale=2)
        paths = {}
        for tag, im in {"cover": cover, "flap": flap, "body": body, "bad_flap": _shift(flap, 0, 12)}.items():
            paths[tag] = td / f"{tag}.png"
            im.save(paths[tag])
        cases.append(("good envelope", _check_env_files(paths["cover"], paths["flap"], paths["body"], geom, None), False))
        cases.append(("shifted envelope flap", _check_env_files(paths["cover"], paths["bad_flap"], paths["body"], geom, None), True))
    for name, problems, should_reject in cases:
        good = bool(problems) == should_reject
        ok &= good
        detail.append(f"{name}: {'ok' if good else 'ПОМИЛКА ПЕРЕВІРКИ — ' + ('прийнято' if should_reject else 'відхилено') + ' неправильно'}")
    return ok, detail


def _shift(img, dx, dy):
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img.convert("RGBA"), (dx, dy))
    return out


def check_all(template_dir, m):
    """{file: [problems]} for every chosen file, "problems" (template-level list), "controls_ok"."""
    tdir = Path(template_dir)
    out, chosen = tdir / "assets", _chosen(tdir)
    ok, detail = run_controls()
    res = {"problems": []}
    if not ok:
        res["problems"].append("КОНТРОЛІ ПЕРЕВІРКИ НЕ ПРОЙШЛИ — перевірку вважати зламаною, результатам не вірити: "
                               + "; ".join(d for d in detail if "ПОМИЛКА" in d))
    for asset, spec in m["assets"].items():
        f = chosen.get(asset)
        if not f:
            res["problems"].append(f"{asset}: нічого не обрано")
        elif spec.get("kind") == "composed":
            res.update(_env_problems(asset, f, m, out, chosen))
        else:
            res[f] = check_asset(out / f, spec)
    res["problems"] += [f"{a}: обрано файл для ассета, якого немає в карті" for a in chosen if a not in m["assets"]]
    res["controls_ok"] = ok
    return res


def all_ok(res):
    return bool(res["controls_ok"]) and all(not v for v in res.values() if isinstance(v, list))


# ---- manifest ----------------------------------------------------------------------------------
def _file_info(p):
    if not p.is_file():
        raise AssetError(f"обраного файла немає: {p.name}")
    with Image.open(p) as im:
        size, mode = list(im.size), im.mode
    return {"size": size, "mode": mode, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def build_manifest(template_dir, m):
    """Write assets/manifest.json and assets/contact_sheet.jpg (the sheet is made here, too)."""
    tdir = Path(template_dir)
    out, chosen = tdir / "assets", _chosen(tdir)
    entries, items, unchosen = {}, [], []
    for asset, spec in m["assets"].items():
        f = chosen.get(asset)
        if not f:
            unchosen.append(asset)
            continue
        names = [f]
        if spec.get("kind") == "composed":
            names = [f, f.replace("__cover__", "__flap__").replace(".jpg", ".png"),
                     f.replace("__cover__", "__body__").replace(".jpg", ".png")]
        entries[asset] = {"kind": spec.get("kind"), "frame": spec.get("frame"), "role": spec.get("role"),
                          "transparent": spec.get("transparent"), "chosen": f,
                          "files": {n: _file_info(out / n) for n in names}}
        items += [(n.split("__v")[0] if len(names) == 1 else n.rsplit(".", 1)[0], out / n) for n in names]
    sheet = contact_sheet(items, out / "contact_sheet.jpg").name if items else None
    path = out / "manifest.json"
    write_json_atomic(path, {"template": tdir.name, "written_utc": now_utc(), "assets": entries,
                             "unchosen": unchosen, "contact_sheet": sheet})
    return path


# ---- generate -> process -----------------------------------------------------------------------
def submit_generations(queue, template_dir, m, style, only=None, prompts=None, seeds=None):
    """Queue one job per asset (all, or `only`); `prompts`/`seeds` override per asset. Returns tickets
    for ``process_finished``. Seeds are random unless given; the seed is in the ticket (and GenQueue's log)."""
    by = {p["asset"]: p for p in plan_generations(m, style)}
    names = list(by) if only is None else list(only)
    names.sort(key=lambda a: by.get(a, {}).get("kind") == "composed")  # composed last: it needs the seal chosen first
    unknown = [a for a in names if a not in by]
    if unknown:
        raise ValueError(f"unknown asset(s): {unknown}")
    prompts, seeds, jobs = prompts or {}, seeds or {}, []
    for a in names:
        prompt = prompts.get(a, by[a]["prompt"])
        if not (isinstance(prompt, str) and prompt.strip()):
            raise ValueError(f"empty prompt for asset {a!r}")
        seed = seeds.get(a)
        seed = random.SystemRandom().randrange(2**32) if seed is None else int(seed)
        jobs.append(dict(asset=a, seed=seed, prefix=f"{a}-s{seed}", width=by[a]["width"], height=by[a]["height"],
                         prompt=final_prompt(by[a]["kind"], prompt.strip())))
    raw = Path(template_dir) / "assets" / "raw"
    tickets = []
    for j in jobs:
        jid = queue.submit({k: j[k] for k in ("prompt", "width", "height", "seed", "prefix")} | {"out_dir": raw})
        tickets.append({"job_id": jid, **j})
    return tickets


def _finish(t, st, tdir, m):
    res = {"asset": t["asset"], "job_id": t["job_id"], "seed": t.get("seed"), "status": "failed", "files": [], "problems": []}
    if st["state"] == "failed" or not st["saved"]:
        res["problems"].append(st.get("error") or "ComfyUI не повернув жодного файла")
        return res
    try:
        p = postprocess(t["asset"], tdir / "assets" / "raw" / st["saved"][0], m, tdir / "assets")
        res.update(status="done", files=[p.name], raw=st["saved"][0])
    except AssetError as e:
        res["problems"].append(str(e))
        return res
    try:
        with STATE_LOCK:
            if not _chosen(tdir).get(t["asset"]):
                choose(tdir, t["asset"], p.name)
    except Exception as e:
        res["problems"].append(f"{t['asset']}: версію створено, але не обрано: {e}")
    return res


def _claim(job_id, state):
    """Under _LOCK: "claimed" -> this caller may process; otherwise why not."""
    with _LOCK:
        if job_id in _CLAIMS:
            return _CLAIMS[job_id]
        if state is None or state["state"] not in ("done", "failed"):
            return "unfinished"
        _CLAIMS[job_id] = "running"
        return "claimed"


def process_finished(queue, template_dir, m, tickets):
    """Postprocess every ticket whose job has finished, each at most once per process. Returns
    (still_pending_tickets, results); a result is {asset, job_id, seed, status: done|failed, files,
    problems}. Never raises for a bad image. A ticket another call is processing right now stays pending
    (it is neither redone nor reported twice); one already processed is dropped. A composed ticket waits
    while the seal's ticket from the same list is unsettled, so the seal is chosen before it is composed."""
    state = {s["id"]: s for s in queue.status()}
    tickets = list(tickets)
    seal = (m.get("envelope") or {}).get("seal_asset")
    kinds = {a: (spec or {}).get("kind") for a, spec in (m.get("assets") or {}).items()}
    comp = lambda t: kinds.get(t["asset"]) == "composed"  # noqa: E731
    waiting, results = set(), []
    for t in [t for t in tickets if not comp(t)] + [t for t in tickets if comp(t)]:
        jid = t["job_id"]
        if comp(t) and any(o["asset"] == seal and o["job_id"] in waiting for o in tickets):
            waiting.add(jid)
            continue
        why = _claim(jid, state.get(jid))
        if why in ("unfinished", "running"):
            waiting.add(jid)
        elif why == "claimed":
            try:
                res = _finish(t, state[jid], Path(template_dir), m)
            except Exception as e:  # never leave a ticket "running" forever
                res = {"asset": t["asset"], "job_id": jid, "seed": t.get("seed"), "status": "failed",
                       "files": [], "problems": [f"{t['asset']}: {type(e).__name__}: {e}"]}
            with _LOCK:
                _CLAIMS[jid] = "done"
            results.append(res)
    return [t for t in tickets if t["job_id"] in waiting], results
