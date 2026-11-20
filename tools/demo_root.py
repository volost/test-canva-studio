"""Demo root for the studio's web interface: fresh data on which every screen has something to show.

    python -I tools/demo_root.py <dir> [--port N] [--models-missing]

Creates a NEW root under <dir> (only when <dir> is missing or empty; it never deletes or overwrites
anything), seeds a skeleton and four templates through the real Api object, then serves the studio on
127.0.0.1:<port> (default 8765) with that root. ComfyUI is pointed at a closed port, so pressing
"Згенерувати" shows the ComfyUI-down message; with --models-missing the models disk is absent too and
the «диск моделей не змонтовано» message shows instead. No real ComfyUI or Canva is ever contacted.

Seeded: skeleton `mini` (map from tests/fixtures/map_min.json, a section thumbnail);
templates `demo-sage` (style chosen, images to review, 2 versions of the hero), `demo-texts` (a failed
write_texts job, texts with the unicode string and two length warnings), `demo-done` (all steps through
a verify result with one failing check), `demo-nocopy` (apply done but no Canva copy id recorded),
`demo-broken` (corrupt state.json) and one corrupt job file in jobs/failed/.
"""
import argparse
import dataclasses
import json
import random
import shutil
import sys
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent
if str(STUDIO) not in sys.path:  # under `python -I` the script's folder is not on sys.path
    sys.path.insert(0, str(STUDIO))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from app import assets  # noqa: E402
from app.api import Api  # noqa: E402
from app.config import load_config  # noqa: E402
from app.steps import now_utc  # noqa: E402
from app.store import read_json, write_json_atomic  # noqa: E402

UNICODE = "We’re “so” happy — Café & <b>\nline"
COPY_ID = "DAdemoCopy0001"
CLOSED_COMFY = "http://127.0.0.1:9"


class DemoError(Exception):
    pass


# ------------------------------------------------------------------ root and config
def check_target(root: Path) -> None:
    if root.exists() and not root.is_dir():
        raise DemoError(f"{root} існує і не є текою")
    if root.is_dir() and any(root.iterdir()):
        raise DemoError(f"{root} не порожня: демо-дані створюються лише в новій або порожній теці")


def make_config(root: Path, port: int, models_present: bool = True):
    cfg = dataclasses.replace(
        load_config(STUDIO / "config.json"), root=root, models_dir=root / "models",
        comfy_url=CLOSED_COMFY, studio_port=port)
    if models_present:
        (root / "models").mkdir(exist_ok=True)
    write_json_atomic(root / "config.json", {
        "root": str(root), "python": str(cfg.python), "comfy_main": str(cfg.comfy_main), "models_dir": str(cfg.models_dir),
        "extra_model_paths": str(cfg.extra_model_paths), "comfy_url": cfg.comfy_url, "studio_port": port,
        "forbidden_design_ids": sorted(cfg.forbidden_design_ids)})
    return cfg


# ------------------------------------------------------------------ small helpers
def call(api: Api, method: str, path: str, body=None):
    raw = json.dumps(body if body is not None else {}, ensure_ascii=False).encode("utf-8") if method in ("POST", "PUT") else b""
    status, payload = api.handle(method, path, raw)
    if status != 200:
        raise DemoError(f"{method} {path} -> {status}: {payload}")
    return payload


def finish_job(cfg, job: dict, status: str = "done", summary: str = "ok", outputs=None, checks=None, folder: str = "done") -> None:
    """What the /test-canva-studio skill does: write the result, move the job file out of pending/."""
    base = cfg.root / ("skeletons/" + job["skeleton"] if job["type"] == "map_skeleton" else "templates/" + job["template"])
    write_json_atomic(base / "jobs" / f"{job['id']}.result.json",
                      {"status": status, "summary": summary, "outputs": outputs or {}, "checks": checks or []})
    dest = cfg.root / "jobs" / folder
    dest.mkdir(parents=True, exist_ok=True)
    shutil.move(str(cfg.root / "jobs" / "pending" / f"{job['id']}.json"), str(dest / f"{job['id']}.json"))


def patch_json(path: Path, fn) -> None:
    data = read_json(path)
    fn(data)
    write_json_atomic(path, data)


# ------------------------------------------------------------------ pictures (PIL, no model)
def _raw_image(spec_kind: str, asset: str, size, seed: int) -> Image.Image:
    rnd = random.Random(f"{asset}-{seed}")
    w, h = size
    hue = [(125, 143, 105), (181, 120, 130), (96, 130, 160), (170, 140, 90)][seed % 4]
    if spec_kind in ("watercolour", "solid"):
        im = Image.new("RGB", size, (255, 255, 255))
        d = ImageDraw.Draw(im)
        if asset == "seal":  # the envelope check wants the seal's centroid at the geometry's seal_centre
            r = min(w, h) // 3
            d.ellipse([w // 2 - r, h // 2 - r, w // 2 + r, h // 2 + r], fill=hue)
            return im.filter(ImageFilter.GaussianBlur(2))
        for _ in range(7):
            cx, cy = rnd.randint(w // 4, 3 * w // 4), rnd.randint(h // 4, 3 * h // 4)
            r = rnd.randint(min(w, h) // 10, min(w, h) // 4)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(max(0, c - rnd.randint(0, 50)) for c in hue))
        return im.filter(ImageFilter.GaussianBlur(2))
    im = Image.new("RGB", size, tuple(min(255, c + 70) for c in hue))
    d = ImageDraw.Draw(im)
    for i in range(0, h, 4):
        t = i / h
        d.line([(0, i), (w, i)], fill=tuple(int(c * (1 - 0.35 * t) + 235 * 0.35 * t) for c in hue))
    for _ in range(9):
        x, y, r = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(min(w, h) // 12, min(w, h) // 5)
        d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 255), width=3)
    return im


def make_versions(cfg, tdir: Path, m: dict, style: dict, hero_versions: int = 2) -> None:
    """Postprocess PIL-drawn raws into real versions (seal first, envelope last) and choose the first of each."""
    raw = tdir / "assets" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    plan = sorted(assets.plan_generations(m, style), key=lambda p: p["kind"] == "composed")
    seed = 1
    for p in plan:
        for n in range(hero_versions if p["asset"] == "hero" else 1):
            seed += 1
            src = raw / f"{p['asset']}-s{seed}_00001_.png"
            _raw_image(p["kind"], p["asset"], (p["width"], p["height"]), seed).save(src)
            out = assets.postprocess(p["asset"], src, m, tdir / "assets")
            if n == 0:
                assets.choose(tdir, p["asset"], out.name)


def make_thumbnail(sdir: Path, page: dict) -> None:
    out = sdir / "sections"
    out.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (320, 200), (244, 239, 230))
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 300, 180], outline=(125, 143, 105), width=3)
    d.ellipse([130, 60, 190, 120], fill=(181, 120, 130))
    d.text((24, 24), page["title"], fill=(47, 58, 44))
    im.save(out / f"{page['id']}.png")


# ------------------------------------------------------------------ seeding
def directions(style_min: dict) -> list:
    sage = {"name": "Sage Linen", "description": "Спокійний шавлієвий із льняним фоном і ніжною акварельною ботанікою.",
            **{k: style_min[k] for k in ("palette", "colour_roles", "image_prompts", "fonts", "font_map")}}
    rose = json.loads(json.dumps(sage))
    rose.update(name="Dusty Rose", description="Теплий пудровий рожевий, м’яке вечірнє світло.")
    rose["palette"] = {"background": "#f7ece8", "accent": "#b57882", "ink": "#3a2a2d"}
    rose["image_prompts"] = {"hero": "warm evening light over a blooming garden, film photograph",
                             "florals": "loose watercolour dusty-rose peonies, transparent background",
                             "envelope": "blush linen paper texture, subtle fibres, flat lay",
                             "seal": "wax seal in dusty rose, watercolour illustration"}
    rose["fonts"] = {"heading": "Playfair Display", "body": "Lato", "script": "Allura"}
    return [sage, rose]


def new_template(api: Api, cfg, name: str, brief: str, style_min: dict) -> dict:
    job = call(api, "POST", "/api/templates", {"name": name, "skeleton": "mini", "brief": brief})["job"]
    finish_job(cfg, job, "done", "Складено 2 напрями стилю", outputs={"directions": directions(style_min)})
    tdir = cfg.root / "templates" / name
    style = dict(style_min, brief=brief)
    write_json_atomic(tdir / "style.json", style)
    call(api, "GET", f"/api/templates/{name}")  # reconcile: style waiting_claude -> review
    return style


def approve(api: Api, name: str, step: str) -> None:
    call(api, "POST", f"/api/templates/{name}/approve", {"step": step})


def seed_templates(api: Api, cfg, m: dict, style_min: dict) -> None:
    root = cfg.root
    long_intro = ("Together with their families, they warmly invite you to celebrate their wedding day "
                  "with dinner, music and dancing under the stars.")

    # demo-sage: style chosen, images ready for review, texts not started
    t = "demo-sage"
    style = new_template(api, cfg, t, style_min["brief"], style_min)
    approve(api, t, "style")
    make_versions(cfg, root / "templates" / t, m, style)
    call(api, "GET", f"/api/templates/{t}")  # images draft -> review (all chosen)

    # demo-texts: a failed write_texts job; texts with the unicode string and two length warnings
    t = "demo-texts"
    style = new_template(api, cfg, t, "Dusty rose, warm evening light.", style_min)
    approve(api, t, "style")
    make_versions(cfg, root / "templates" / t, m, style, hero_versions=1)
    call(api, "GET", f"/api/templates/{t}")
    approve(api, t, "images")
    job = call(api, "POST", f"/api/templates/{t}/texts/request")["job"]
    finish_job(cfg, job, "failed", "Claude не зміг написати тексти: конектор повернув порожню відповідь.", folder="failed")
    write_json_atomic(root / "templates" / t / "texts.json",
                      {"p1/text/names": UNICODE, "p1/text/intro": long_intro, "p1/cell/day": "123"})
    call(api, "GET", f"/api/templates/{t}")  # texts waiting_claude -> draft (failed result)

    # demo-done: everything through a verify result with one failing check
    t = "demo-done"
    style = new_template(api, cfg, t, "Calm sage & linen, <i>soft</i> botanicals — “quoted”.", style_min)
    approve(api, t, "style")
    make_versions(cfg, root / "templates" / t, m, style)
    call(api, "GET", f"/api/templates/{t}")
    approve(api, t, "images")
    job = call(api, "POST", f"/api/templates/{t}/texts/request")["job"]
    write_json_atomic(root / "templates" / t / "texts.json",
                      {"p1/text/names": UNICODE, "p1/text/intro": "Together with their families, they invite you to a day of joy.", "p1/cell/day": "14"})
    finish_job(cfg, job, "done", "Тексти написано")
    call(api, "GET", f"/api/templates/{t}")
    approve(api, t, "texts")
    job = call(api, "POST", f"/api/templates/{t}/apply")["job"]
    patch_json(root / "templates" / t / "state.json", lambda s: s.update(canva_copy_id=COPY_ID))
    finish_job(cfg, job, "done", "Копію створено, кольори, тексти й картинки записано.")
    call(api, "GET", f"/api/templates/{t}")
    approve(api, t, "apply")
    job = call(api, "POST", f"/api/templates/{t}/verify")["job"]
    finish_job(cfg, job, "done", "Перевірено 3 пункти: один не пройшов.",
               outputs={"manual_steps": ["Замінити шрифт заголовка на Cormorant Garamond у Canva."]},
               checks=[{"name": "Пропорції картинок у рамках", "passed": True, "detail": "4/4, відхилення до 0,2 %"},
                       {"name": "Контраст тексту на фоні", "passed": True, "detail": "мінімум 7,1:1"},
                       {"name": "Кнопки в повноекранному перегляді", "passed": False, "detail": "8/9: не знайдено кнопку «RSVP» на телефоні"}])
    call(api, "GET", f"/api/templates/{t}")

    # demo-nocopy: apply "done" but the copy id was never recorded
    t = "demo-nocopy"
    style = new_template(api, cfg, t, "Plain demo of the missing-copy-id message.", style_min)
    approve(api, t, "style")
    make_versions(cfg, root / "templates" / t, m, style, hero_versions=1)
    call(api, "GET", f"/api/templates/{t}")
    approve(api, t, "images")
    job = call(api, "POST", f"/api/templates/{t}/texts/request")["job"]
    write_json_atomic(root / "templates" / t / "texts.json", {"p1/text/names": "Anna & Max"})
    finish_job(cfg, job, "done", "Тексти написано")
    call(api, "GET", f"/api/templates/{t}")
    approve(api, t, "texts")
    job = call(api, "POST", f"/api/templates/{t}/apply")["job"]
    finish_job(cfg, job, "done", "Записано.")
    call(api, "GET", f"/api/templates/{t}")  # effective status failed -> apply back to draft


def seed(root, port: int = 8765, models_present: bool = True):
    """Create the demo root. Raises DemoError (touching nothing) when `root` is not missing/empty."""
    root = Path(root).resolve()
    check_target(root)
    root.mkdir(parents=True, exist_ok=True)
    cfg = make_config(root, port, models_present)
    api = Api(cfg)
    fixtures = STUDIO / "tests" / "fixtures"
    m = dict(json.loads((fixtures / "map_min.json").read_text(encoding="utf-8")), skeleton="mini")
    style_min = json.loads((fixtures / "style_min.json").read_text(encoding="utf-8"))

    call(api, "POST", "/api/skeletons", {"name": "mini", "design_id": m["design_id"]})
    write_json_atomic(root / "skeletons" / "mini" / "map.json", m)
    for page in m["pages"]:
        make_thumbnail(root / "skeletons" / "mini", page)
    map_job = next(j for j in (read_json(p) for p in sorted((root / "jobs" / "pending").glob("*.json"))) if j["type"] == "map_skeleton")
    finish_job(cfg, map_job, "done", "Карту складено: 1 сторінка, 4 картинки, 9 слотів.")

    seed_templates(api, cfg, m, style_min)

    (root / "templates" / "demo-broken").mkdir()
    (root / "templates" / "demo-broken" / "state.json").write_text("{oops", encoding="utf-8")
    failed = root / "jobs" / "failed"
    failed.mkdir(parents=True, exist_ok=True)
    (failed / "20261101T090000Z-verify.json").write_text('{"id": "20261101T090000Z-verify", "type": "ver', encoding="utf-8")
    return cfg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Створює демо-дані й запускає студію на них.")
    ap.add_argument("dir", help="нова або порожня тека для демо-даних")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--models-missing", action="store_true", help="не створювати теку моделей (щоб побачити «диск моделей не змонтовано»)")
    args = ap.parse_args(argv)
    try:
        cfg = seed(args.dir, args.port, not args.models_missing)
    except DemoError as e:
        print(f"Відмова: {e}", file=sys.stderr)
        return 2
    from app.server import make_server
    server = make_server(cfg, args.port)
    print(f"Демо-студія: http://127.0.0.1:{args.port}  (дані: {cfg.root}; ComfyUI навмисно недоступний: {cfg.comfy_url})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
