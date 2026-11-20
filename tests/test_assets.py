"""Asset pipeline: plan, postprocess, checks with controls, versions, manifest, generate -> process flow.

Everything is synthetic and in temp dirs; generation goes through the real GenQueue with a fake
generate function (no ComfyUI)."""
import copy
import hashlib
import json
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw

from app import assets
from app.genqueue import GenQueue
from app.imaging.core import aspect_error
from app.imaging.envelope import check_envelope
from app.schema import validate_map, validate_style
from app.store import STATE_LOCK, read_json, write_json_atomic

FIX = Path(__file__).parent / "fixtures"
MAP = json.loads((FIX / "map_min.json").read_text(encoding="utf-8"))
STYLE = json.loads((FIX / "style_min.json").read_text(encoding="utf-8"))


def noisy_photo(size=(1024, 1408)):
    rng = np.random.default_rng(1)
    return Image.fromarray(rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8), "RGB")


def on_white(shape="ellipse", size=(900, 900), colour=(190, 90, 120)):
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    box = (size[0] * 0.2, size[1] * 0.25, size[0] * 0.8, size[1] * 0.75)
    d.ellipse(box, fill=colour) if shape == "ellipse" else d.rectangle(box, fill=colour)
    return img


def seal_source():
    img = Image.new("RGB", (800, 800), (255, 255, 255))
    ImageDraw.Draw(img).ellipse((150, 150, 650, 650), fill=(120, 30, 40))
    return img


def linen(size=(1024, 736)):
    return Image.new("RGB", size, (200, 190, 170))


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tdir = self.tmp / "tpl"
        self.out = self.tdir / "assets"
        self.out.mkdir(parents=True)
        write_json_atomic(self.tdir / "state.json", {"skeleton": "mini", "canva_copy_id": None, "chosen": {},
                                                     "steps": {"images": {"status": "draft", "updated_utc": "x"}}})

    def src(self, name, img):
        p = self.tmp / name
        img.save(p)
        return p

    def state(self):
        return read_json(self.tdir / "state.json")


class SizingAndPlanTests(unittest.TestCase):
    def test_gen_size_multiple_of_64_and_close_aspect(self):
        for frame in [(433, 600), (1200, 800), (600, 600), (1366, 964), (200, 200)]:
            w, h = assets.gen_size(frame)
            self.assertEqual((w % 64, h % 64), (0, 0), frame)
            self.assertLess(aspect_error((w, h), frame), 0.03, frame)
            self.assertAlmostEqual(w * h / 1e6, 1.5, delta=0.35, msg=frame)

    def test_gen_size_respects_megapixels(self):
        w, h = assets.gen_size((1, 1), megapixels=0.5)
        self.assertLess(w * h, 0.65e6)
        with self.assertRaises(ValueError):
            assets.gen_size((0, 10))

    def test_fixtures_are_valid(self):
        self.assertEqual(validate_map(MAP), [])
        self.assertEqual(validate_style(STYLE, MAP), [])

    def test_plan_has_every_asset(self):
        plan = assets.plan_generations(MAP, STYLE)
        self.assertEqual({p["asset"] for p in plan}, set(MAP["assets"]))
        for p in plan:
            self.assertEqual(set(p), {"asset", "prompt", "width", "height", "kind"})
            self.assertEqual(p["prompt"], STYLE["image_prompts"][p["asset"]])
            self.assertEqual((p["width"] % 64, p["height"] % 64), (0, 0))
            self.assertEqual(p["kind"], MAP["assets"][p["asset"]]["kind"])

    def test_plan_composed_uses_envelope_section_aspect(self):
        m = copy.deepcopy(MAP)
        m["assets"]["envelope"]["frame"] = [300, 300]          # the asset frame is NOT what is generated
        p = {x["asset"]: x for x in assets.plan_generations(m, STYLE)}["envelope"]
        self.assertLess(aspect_error((p["width"], p["height"]), m["envelope"]["section_px"]), 0.03)

    def test_plan_errors_are_clear(self):
        style = copy.deepcopy(STYLE)
        del style["image_prompts"]["hero"]
        with self.assertRaisesRegex(ValueError, "hero"):
            assets.plan_generations(MAP, style)
        m = copy.deepcopy(MAP)
        m["envelope"] = None
        with self.assertRaisesRegex(ValueError, "envelope"):
            assets.plan_generations(m, STYLE)


class PostprocessTests(TmpCase):
    def test_postprocess_photo_exact_aspect(self):
        for frame in ([1200, 800], [433, 600], [37, 53]):
            m = copy.deepcopy(MAP)
            m["assets"]["hero"]["frame"] = frame
            p = assets.postprocess("hero", self.src("raw.png", noisy_photo()), m, self.out)
            with Image.open(p) as im:
                self.assertLess(aspect_error(im.size, frame), 0.005, frame)
                self.assertEqual(im.mode, "RGB")
                self.assertEqual(im.format, "JPEG")
        self.assertEqual(p.name, "hero__v3.jpg")

    def test_postprocess_photo_is_jpeg_q94_no_subsampling(self):
        p = assets.postprocess("hero", self.src("raw.png", noisy_photo()), MAP, self.out)
        with Image.open(p) as im:
            self.assertEqual(im.format, "JPEG")
            from PIL import JpegImagePlugin
            self.assertEqual(JpegImagePlugin.get_sampling(im), 0)   # 4:4:4

    def test_postprocess_watercolour_transparent(self):
        p = assets.postprocess("florals", self.src("raw.png", on_white()), MAP, self.out)
        self.assertEqual(p.name, "florals__v1.png")
        with Image.open(p) as im:
            self.assertEqual(im.mode, "RGBA")
            self.assertLess(aspect_error(im.size, MAP["assets"]["florals"]["frame"]), 0.005)
            a = np.asarray(im.getchannel("A"))
            self.assertEqual(int(a[0, 0]), 0)
            self.assertGreater(int(a.max()), 200)
        self.assertEqual(assets.check_asset(p, MAP["assets"]["florals"]), [])

    def test_postprocess_solid_transparent(self):
        m = copy.deepcopy(MAP)
        m["assets"]["florals"]["kind"] = "solid"
        p = assets.postprocess("florals", self.src("raw.png", on_white("rect")), m, self.out)
        self.assertEqual(assets.check_asset(p, m["assets"]["florals"]), [])

    def test_postprocess_bad_source_is_a_clear_error(self):
        grey = Image.new("RGB", (400, 400), (120, 120, 120))
        with self.assertRaises(assets.AssetError) as cm:
            assets.postprocess("florals", self.src("grey.png", grey), MAP, self.out)
        self.assertIn("florals", str(cm.exception))
        with self.assertRaises(assets.AssetError):
            assets.postprocess("nope", self.src("x.png", grey), MAP, self.out)
        with self.assertRaises(assets.AssetError):
            assets.postprocess("../evil", self.src("y.png", grey), MAP, self.out)
        self.assertEqual([f.name for f in self.out.iterdir()], [])   # nothing half-written

    def test_postprocess_composed_without_seal(self):
        cover = assets.postprocess("envelope", self.src("t.png", linen()), MAP, self.out)
        self.assertEqual(cover.name, "envelope__cover__v1.jpg")
        flap, body = self.out / "envelope__flap__v1.png", self.out / "envelope__body__v1.png"
        self.assertTrue(flap.is_file() and body.is_file())
        with Image.open(cover) as c, Image.open(flap) as f, Image.open(body) as b:
            self.assertEqual(c.size, (2000, 1400))
            self.assertEqual(c.format, "JPEG")
            c.load(), f.load(), b.load()
            self.assertEqual(check_envelope(c, f, b, MAP["envelope"], seal_expected=False), [])

    def test_postprocess_composed_with_chosen_seal(self):
        seal = assets.postprocess("seal", self.src("s.png", seal_source()), MAP, self.out)
        assets.choose(self.tdir, "seal", seal.name)
        cover = assets.postprocess("envelope", self.src("t.png", linen()), MAP, self.out)
        flap, body = self.out / "envelope__flap__v1.png", self.out / "envelope__body__v1.png"
        with Image.open(cover) as c, Image.open(flap) as f, Image.open(body) as b, Image.open(seal) as s:
            c.load(), f.load(), b.load(), s.load()
            self.assertEqual(check_envelope(c, f, b, MAP["envelope"], seal=s), [])
            # without the seal the checker must notice the layers carry one
            self.assertNotEqual(check_envelope(c, f, b, MAP["envelope"], seal_expected=False), [])

    def test_composed_layers_share_the_version(self):
        for _ in range(2):
            assets.postprocess("envelope", self.src("t.png", linen()), MAP, self.out)
        names = sorted(p.name for p in self.out.iterdir())
        self.assertEqual(names, ["envelope__body__v1.png", "envelope__body__v2.png",
                                 "envelope__cover__v1.jpg", "envelope__cover__v2.jpg",
                                 "envelope__flap__v1.png", "envelope__flap__v2.png"])

    def test_composed_needs_envelope_block(self):
        m = copy.deepcopy(MAP)
        m["envelope"] = None
        with self.assertRaisesRegex(assets.AssetError, "envelope"):
            assets.postprocess("envelope", self.src("t.png", linen()), m, self.out)

    def test_composed_bad_seal_file_is_loud(self):
        (self.out / "seal__v1.png").write_bytes(b"not an image")
        assets.choose(self.tdir, "seal", "seal__v1.png")
        with self.assertRaises(assets.AssetError):
            assets.postprocess("envelope", self.src("t.png", linen()), MAP, self.out)


class VersionTests(TmpCase):
    def test_regenerate_keeps_previous_version(self):
        p1 = assets.postprocess("hero", self.src("a.png", noisy_photo()), MAP, self.out)
        before = p1.read_bytes()
        p2 = assets.postprocess("hero", self.src("b.png", noisy_photo((900, 1200))), MAP, self.out)
        self.assertEqual((p1.name, p2.name), ("hero__v1.jpg", "hero__v2.jpg"))
        self.assertEqual(p1.read_bytes(), before)
        self.assertEqual(assets.list_versions(self.out, "hero"), [(1, "hero__v1.jpg"), (2, "hero__v2.jpg")])

    def test_next_number_is_after_the_highest_and_never_overwrites(self):
        (self.out / "hero__v7.jpg").write_bytes(b"old")
        p = assets.postprocess("hero", self.src("a.png", noisy_photo()), MAP, self.out)
        self.assertEqual(p.name, "hero__v8.jpg")
        self.assertEqual((self.out / "hero__v7.jpg").read_bytes(), b"old")

    def test_exclusive_create_refuses_to_clobber(self):
        # even if the number logic were wrong, a file that exists is never replaced
        (self.out / "hero__v1.jpg").write_bytes(b"old")
        with mock.patch.object(assets, "next_version", return_value=1):
            with self.assertRaises(assets.AssetError):
                assets.postprocess("hero", self.src("a.png", noisy_photo()), MAP, self.out)
        self.assertEqual((self.out / "hero__v1.jpg").read_bytes(), b"old")

    def test_half_written_composed_version_is_not_listed_or_choosable(self):
        assets.postprocess("envelope", self.src("t.png", linen()), MAP, self.out)           # complete v1
        (self.out / "envelope__cover__v2.jpg").write_bytes(b"cover only")                    # v2: cover only
        (self.out / "envelope__cover__v3.jpg").write_bytes(b"x")
        (self.out / "envelope__flap__v3.png").write_bytes(b"x")                              # v3: no body
        self.assertEqual(assets.list_versions(self.out, "envelope"), [(1, "envelope__cover__v1.jpg")])
        for name in ("envelope__cover__v2.jpg", "envelope__cover__v3.jpg"):
            with self.assertRaises(assets.AssetError):
                assets.choose(self.tdir, "envelope", name)
        self.assertEqual(self.state()["chosen"], {})
        assets.choose(self.tdir, "envelope", "envelope__cover__v1.jpg")
        # numbering still goes past the half-written files
        self.assertEqual(assets.next_version(self.out, "envelope"), 4)

    def test_other_assets_do_not_share_numbers(self):
        assets.postprocess("hero", self.src("a.png", noisy_photo()), MAP, self.out)
        p = assets.postprocess("florals", self.src("b.png", on_white()), MAP, self.out)
        self.assertEqual(p.name, "florals__v1.png")


class ChooseTests(TmpCase):
    def test_choose_writes_state_and_keeps_the_rest(self):
        p = assets.postprocess("hero", self.src("a.png", noisy_photo()), MAP, self.out)
        assets.choose(self.tdir, "hero", p.name)
        st = self.state()
        self.assertEqual(st["chosen"], {"hero": "hero__v1.jpg"})
        self.assertEqual(st["steps"], {"images": {"status": "draft", "updated_utc": "x"}})
        self.assertEqual(st["skeleton"], "mini")

    def test_choose_uses_the_public_state_lock(self):
        p = assets.postprocess("hero", self.src("a.png", noisy_photo()), MAP, self.out)
        done = threading.Event()

        def work():
            assets.choose(self.tdir, "hero", p.name)
            done.set()
        with STATE_LOCK:                       # another holder of the lock (e.g. a step change)
            t = threading.Thread(target=work)
            t.start()
            self.assertFalse(done.wait(0.3), "choose wrote state.json while the lock was held elsewhere")
            self.assertEqual(self.state()["chosen"], {})
        self.assertTrue(done.wait(5))
        t.join()
        self.assertEqual(self.state()["chosen"], {"hero": p.name})

    def test_choose_refuses_wrong_or_missing_files(self):
        p = assets.postprocess("hero", self.src("a.png", noisy_photo()), MAP, self.out)
        for asset, name in [("florals", p.name), ("hero", "hero__v9.jpg"), ("hero", "../state.json")]:
            with self.assertRaises(assets.AssetError):
                assets.choose(self.tdir, asset, name)
        self.assertEqual(self.state()["chosen"], {})


class CheckAssetTests(TmpCase):
    def save(self, name, img, **kw):
        p = self.tmp / name
        img.save(p, **kw)
        return p

    def has(self, problems, code):
        self.assertTrue(any(code in x for x in problems), problems)

    def test_good_files_have_no_problems(self):
        spec = MAP["assets"]["hero"]
        self.assertEqual(assets.check_asset(self.save("a.jpg", Image.new("RGB", (600, 400))), spec), [])

    def test_wrong_aspect(self):
        self.has(assets.check_asset(self.save("a.png", Image.new("RGB", (600, 600))), MAP["assets"]["hero"]), "[aspect]")

    def test_unopenable(self):
        p = self.tmp / "a.png"
        p.write_bytes(b"garbage")
        self.has(assets.check_asset(p, MAP["assets"]["hero"]), "[open]")
        self.has(assets.check_asset(self.tmp / "missing.png", MAP["assets"]["hero"]), "[open]")

    def test_transparent_must_be_rgba_with_sane_coverage(self):
        spec = MAP["assets"]["florals"]
        self.has(assets.check_asset(self.save("rgb.png", Image.new("RGB", (600, 600))), spec), "[alpha]")
        self.has(assets.check_asset(self.save("opaque.png", Image.new("RGBA", (600, 600), (1, 2, 3, 255))), spec), "[alpha]")
        self.has(assets.check_asset(self.save("empty.png", Image.new("RGBA", (600, 600), (0, 0, 0, 0))), spec), "[alpha]")
        almost = Image.new("RGBA", (600, 600), (0, 0, 0, 255))
        almost.paste((0, 0, 0, 0), (0, 0, 10, 10))
        self.has(assets.check_asset(self.save("almost.png", almost), spec), "[alpha]")

    def test_opaque_asset_must_not_have_transparency(self):
        img = Image.new("RGBA", (600, 400), (10, 10, 10, 255))
        img.putpixel((3, 3), (10, 10, 10, 0))
        self.has(assets.check_asset(self.save("a.png", img), MAP["assets"]["hero"]), "[opaque]")

    def test_bad_spec_is_a_problem_not_a_crash(self):
        p = self.save("a.png", Image.new("RGB", (60, 40)))
        self.assertTrue(assets.check_asset(p, {"kind": "photo"}))
        self.assertTrue(assets.check_asset(p, {"kind": "photo", "frame": [0, 0]}))


def full_template(case):
    """hero, florals, seal (chosen) and an envelope (chosen) in case.tdir."""
    for name, img in [("hero", noisy_photo()), ("florals", on_white()), ("seal", seal_source())]:
        p = assets.postprocess(name, case.src(name + ".png", img), MAP, case.out)
        assets.choose(case.tdir, name, p.name)
    p = assets.postprocess("envelope", case.src("e.png", linen()), MAP, case.out)
    assets.choose(case.tdir, "envelope", p.name)


class CheckAllTests(TmpCase):
    def test_check_all_controls_reject_bad(self):
        full_template(self)
        res = assets.check_all(self.tdir, MAP)
        self.assertIs(res["controls_ok"], True)
        self.assertEqual(res["problems"], [])
        self.assertEqual(res["hero__v1.jpg"], [])
        for f in ("envelope__cover__v1.jpg", "envelope__flap__v1.png", "envelope__body__v1.png", "seal__v1.png"):
            self.assertIn(f, res)
            self.assertEqual(res[f], [], f)
        self.assertTrue(assets.all_ok(res))

    def test_controls_directly(self):
        ok, detail = assets.run_controls()
        self.assertTrue(ok, detail)
        self.assertGreaterEqual(len(detail), 5)

    def test_sabotaged_check_asset_makes_controls_fail_loudly(self):
        full_template(self)
        with mock.patch.object(assets, "check_asset", lambda *a, **k: []):
            res = assets.check_all(self.tdir, MAP)
        self.assertIs(res["controls_ok"], False)
        self.assertTrue(any("контрол" in x.lower() for x in res["problems"]), res["problems"])
        self.assertFalse(assets.all_ok(res))

    def test_sabotaged_check_envelope_makes_controls_fail(self):
        full_template(self)
        with mock.patch.object(assets, "check_envelope", lambda *a, **k: []):
            res = assets.check_all(self.tdir, MAP)
        self.assertIs(res["controls_ok"], False)
        self.assertFalse(assets.all_ok(res))

    def test_a_check_that_rejects_everything_is_also_broken(self):
        with mock.patch.object(assets, "check_asset", lambda *a, **k: ["[x] always"]):
            ok, _ = assets.run_controls()
        self.assertFalse(ok)

    def test_real_problems_are_reported_per_file_and_unchosen_assets(self):
        full_template(self)
        (self.out / "hero__v1.jpg").write_bytes(b"broken")
        st = self.state()
        del st["chosen"]["florals"]
        write_json_atomic(self.tdir / "state.json", st)
        res = assets.check_all(self.tdir, MAP)
        self.assertTrue(any("[open]" in x for x in res["hero__v1.jpg"]))
        self.assertTrue(any("florals" in x for x in res["problems"]))
        self.assertFalse(assets.all_ok(res))

    def test_stale_envelope_after_seal_change_is_flagged(self):
        full_template(self)
        p = assets.postprocess("seal", self.src("s2.png", on_white(colour=(20, 120, 40))), MAP, self.out)
        assets.choose(self.tdir, "seal", p.name)               # envelope still carries the old seal
        res = assets.check_all(self.tdir, MAP)
        self.assertTrue(any(res[f] for f in res if f.startswith("envelope__")), res)

    def test_controls_leave_no_files_behind(self):
        full_template(self)
        before = sorted(p.name for p in self.out.iterdir())
        assets.check_all(self.tdir, MAP)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), before)


class ManifestTests(TmpCase):
    def test_manifest_has_files_hashes_and_contact_sheet(self):
        full_template(self)
        path = assets.build_manifest(self.tdir, MAP)
        self.assertEqual(path, self.out / "manifest.json")
        man = read_json(path)
        self.assertEqual(set(man["assets"]), set(MAP["assets"]))
        hero = man["assets"]["hero"]
        self.assertEqual((hero["kind"], hero["frame"]), ("photo", [1200, 800]))
        f = hero["files"]["hero__v1.jpg"]
        self.assertEqual(f["sha256"], hashlib.sha256((self.out / "hero__v1.jpg").read_bytes()).hexdigest())
        with Image.open(self.out / "hero__v1.jpg") as im:
            self.assertEqual(f["size"], list(im.size))
        self.assertEqual(set(man["assets"]["envelope"]["files"]),
                         {"envelope__cover__v1.jpg", "envelope__flap__v1.png", "envelope__body__v1.png"})
        sheet = self.out / "contact_sheet.jpg"
        self.assertTrue(sheet.is_file())
        self.assertEqual(man["contact_sheet"], "contact_sheet.jpg")
        with Image.open(sheet) as im:
            self.assertLessEqual(max(im.size), 1568)

    def test_manifest_skips_unchosen_and_fails_on_missing_file(self):
        p = assets.postprocess("hero", self.src("a.png", noisy_photo()), MAP, self.out)
        assets.choose(self.tdir, "hero", p.name)
        man = read_json(assets.build_manifest(self.tdir, MAP))
        self.assertEqual(list(man["assets"]), ["hero"])
        self.assertEqual(sorted(man["unchosen"]), ["envelope", "florals", "seal"])
        p.rename(self.tmp / "moved.jpg")
        with self.assertRaises(assets.AssetError):
            assets.build_manifest(self.tdir, MAP)

    def test_manifest_with_nothing_chosen(self):
        man = read_json(assets.build_manifest(self.tdir, MAP))
        self.assertEqual(man["assets"], {})
        self.assertIsNone(man["contact_sheet"])


def fake_generate(kind_images):
    """generate_fn for GenQueue: writes kind_images[prefix-asset] (PIL image) as PNG into out_dir."""
    calls = []

    def gen(cfg, prompt, width, height, seed, prefix, out_dir):
        calls.append(dict(prompt=prompt, width=width, height=height, seed=seed, prefix=prefix))
        asset = prefix.split("-s")[0]
        img = kind_images[asset]
        if isinstance(img, Exception):
            raise img
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{prefix}_00001_.png"
        img.save(p)
        return [p]
    gen.calls = calls
    return gen


class FlowTests(TmpCase):
    def queue(self, images):
        gen = fake_generate(images)
        q = GenQueue(None, self.tmp / "gen.log", generate_fn=gen)
        return q, gen

    def wait(self, q, n, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            st = q.status()
            if len(st) >= n and all(s["state"] in ("done", "failed") for s in st):
                return
            time.sleep(0.02)
        self.fail("queue did not finish")

    def run_flow(self, q, tickets):
        self.wait(q, len(tickets))
        return assets.process_finished(q, self.tdir, MAP, tickets)

    def test_generate_then_process_end_to_end(self):
        images = {"hero": noisy_photo(), "florals": on_white(), "seal": seal_source(), "envelope": linen()}
        q, gen = self.queue(images)
        tickets = assets.submit_generations(q, self.tdir, MAP, STYLE, only=["hero", "florals", "seal"])
        self.assertEqual([t["asset"] for t in tickets], ["hero", "florals", "seal"])
        self.assertTrue(all(isinstance(t["seed"], int) for t in tickets))
        pending, results = self.run_flow(q, tickets)
        self.assertEqual(pending, [])
        self.assertEqual({r["asset"]: r["status"] for r in results}, {"hero": "done", "florals": "done", "seal": "done"})
        self.assertEqual(self.state()["chosen"], {"hero": "hero__v1.jpg", "florals": "florals__v1.png",
                                                  "seal": "seal__v1.png"})
        raws = sorted(p.name for p in (self.out / "raw").iterdir())
        self.assertEqual(len(raws), 3)
        self.assertEqual({c["seed"] for c in gen.calls}, {t["seed"] for t in tickets})
        # the white-background hint is added to cut-out prompts only
        by = {c["prefix"].split("-s")[0]: c for c in gen.calls}
        self.assertIn("white background", by["florals"]["prompt"])
        self.assertEqual(by["hero"]["prompt"], STYLE["image_prompts"]["hero"])
        # now the envelope: composed, with the chosen seal
        t2 = assets.submit_generations(q, self.tdir, MAP, STYLE, only=["envelope"])
        _, res2 = self.run_flow(q, t2)
        self.assertEqual(res2[0]["files"][0], "envelope__cover__v1.jpg")
        self.assertEqual(self.state()["chosen"]["envelope"], "envelope__cover__v1.jpg")
        self.assertTrue(assets.all_ok(assets.check_all(self.tdir, MAP)))

    def test_generate_all_composes_the_envelope_with_the_seal(self):
        images = {"hero": noisy_photo(), "florals": on_white(), "seal": seal_source(), "envelope": linen()}
        q, gen = self.queue(images)
        tickets = assets.submit_generations(q, self.tdir, MAP, STYLE)            # only=None: every asset
        order = [t["asset"] for t in tickets]
        self.assertEqual(order[-1], "envelope")                                  # composed goes last
        # even if the caller hands the tickets over in map order (envelope before seal), the seal wins
        tickets = sorted(tickets, key=lambda t: list(MAP["assets"]).index(t["asset"]))
        self.assertLess([t["asset"] for t in tickets].index("envelope"), [t["asset"] for t in tickets].index("seal"))
        self.wait(q, 4)
        pending, results = assets.process_finished(q, self.tdir, MAP, tickets)
        self.assertEqual(pending, [])
        self.assertEqual({r["asset"]: r["status"] for r in results}, {a: "done" for a in images})
        self.assertEqual([r["asset"] for r in results].index("seal") < [r["asset"] for r in results].index("envelope"), True)
        res = assets.check_all(self.tdir, MAP)
        self.assertTrue(assets.all_ok(res), res)
        # the flap layer really carries the seal: stacked layers differ from the cover inside the seal box
        with Image.open(self.out / "envelope__flap__v1.png") as f, Image.open(self.out / "envelope__body__v1.png") as b, \
                Image.open(self.out / "envelope__cover__v1.jpg") as c:
            stacked = np.asarray(Image.alpha_composite(b.convert("RGBA"), f.convert("RGBA")).convert("RGB")).astype(int)
            diff = np.abs(stacked - np.asarray(c.convert("RGB")).astype(int)).mean(axis=2)
        cx, cy = (v * 2 for v in MAP["envelope"]["seal_centre"])
        self.assertGreater(diff[cy - 40:cy + 40, cx - 40:cx + 40].mean(), 5.0)

    def test_composed_ticket_waits_while_its_seal_is_unfinished(self):
        class FakeQueue:
            def __init__(self):
                self.st = {"s": {"id": "s", "state": "running", "saved": [], "error": None},
                           "e": {"id": "e", "state": "done", "saved": ["e_00001_.png"], "error": None}}

            def status(self):
                return list(self.st.values())
        (self.out / "raw").mkdir()
        linen().save(self.out / "raw" / "e_00001_.png")
        seal_source().save(self.out / "raw" / "s_00001_.png")
        tickets = [{"job_id": "e", "asset": "envelope", "seed": 1}, {"job_id": "s", "asset": "seal", "seed": 2}]
        q = FakeQueue()
        pending, results = assets.process_finished(q, self.tdir, MAP, tickets)
        self.assertEqual((pending, results), (tickets, []))                      # nothing yet, no seal-less envelope
        self.assertEqual(list((self.out).glob("envelope__*")), [])
        q.st["s"].update(state="done", saved=["s_00001_.png"])
        pending, results = assets.process_finished(q, self.tdir, MAP, pending)
        self.assertEqual([r["asset"] for r in results], ["seal", "envelope"])
        self.assertEqual(pending, [])

    def test_a_failed_seal_does_not_hold_the_envelope(self):
        class FakeQueue:
            def status(self):
                return [{"id": "e2", "state": "done", "saved": ["e2_00001_.png"], "error": None},
                        {"id": "s2", "state": "failed", "saved": [], "error": "boom"}]
        (self.out / "raw").mkdir()
        linen().save(self.out / "raw" / "e2_00001_.png")
        tickets = [{"job_id": "e2", "asset": "envelope", "seed": 1}, {"job_id": "s2", "asset": "seal", "seed": 2}]
        pending, results = assets.process_finished(FakeQueue(), self.tdir, MAP, tickets)
        self.assertEqual(pending, [])
        self.assertEqual({r["asset"]: r["status"] for r in results}, {"seal": "failed", "envelope": "done"})

    def test_concurrent_process_finished_makes_one_version(self):
        q, _ = self.queue({"hero": noisy_photo()})
        t = assets.submit_generations(q, self.tdir, MAP, STYLE, only=["hero"])
        self.wait(q, 1)
        barrier, outs, errs = threading.Barrier(4), [], []

        def work():
            try:
                barrier.wait()
                outs.append(assets.process_finished(q, self.tdir, MAP, t))
            except Exception as e:  # noqa: BLE001
                errs.append(e)
        threads = [threading.Thread(target=work) for _ in range(4)]
        [x.start() for x in threads]
        [x.join(30) for x in threads]
        self.assertEqual(errs, [])
        self.assertEqual(assets.list_versions(self.out, "hero"), [(1, "hero__v1.jpg")])
        self.assertEqual(sum(len(r) for _, r in outs), 1)                        # reported done exactly once
        # once finished, the ticket is dropped for everybody
        self.assertEqual(assets.process_finished(q, self.tdir, MAP, t), ([], []))

    def test_second_generation_adds_a_version_and_keeps_the_choice(self):
        q, _ = self.queue({"hero": noisy_photo()})
        for _ in range(2):
            t = assets.submit_generations(q, self.tdir, MAP, STYLE, only=["hero"])
            self.run_flow(q, t)
        self.assertEqual(assets.list_versions(self.out, "hero"), [(1, "hero__v1.jpg"), (2, "hero__v2.jpg")])
        self.assertEqual(self.state()["chosen"]["hero"], "hero__v1.jpg")   # only the first is auto-chosen
        self.assertEqual(len(list((self.out / "raw").iterdir())), 2)

    def test_prompt_override_and_fixed_seed(self):
        q, gen = self.queue({"hero": noisy_photo()})
        t = assets.submit_generations(q, self.tdir, MAP, STYLE, only=["hero"],
                                      prompts={"hero": "  a red barn  "}, seeds={"hero": 42})
        self.assertEqual(t[0]["seed"], 42)
        self.run_flow(q, t)
        self.assertEqual((gen.calls[0]["prompt"], gen.calls[0]["seed"]), ("a red barn", 42))

    def test_submit_validates_input(self):
        q, _ = self.queue({})
        with self.assertRaises(ValueError):
            assets.submit_generations(q, self.tdir, MAP, STYLE, only=["nope"])
        with self.assertRaises(ValueError):
            assets.submit_generations(q, self.tdir, MAP, STYLE, only=["hero"], prompts={"hero": "  "})
        self.assertEqual(q.status(), [])

    def test_failed_generation_and_bad_image_become_problems_not_crashes(self):
        from app.comfy import ComfyError
        grey = Image.new("RGB", (400, 400), (120, 120, 120))
        q, _ = self.queue({"hero": ComfyError("ComfyUI недоступний"), "florals": grey, "seal": seal_source()})
        t = assets.submit_generations(q, self.tdir, MAP, STYLE, only=["hero", "florals", "seal"])
        pending, results = self.run_flow(q, t)
        by = {r["asset"]: r for r in results}
        self.assertEqual(by["hero"]["status"], "failed")
        self.assertIn("ComfyUI", by["hero"]["problems"][0])
        self.assertEqual(by["florals"]["status"], "failed")
        self.assertTrue(by["florals"]["problems"])
        self.assertEqual(by["seal"]["status"], "done")
        self.assertEqual(self.state()["chosen"], {"seal": "seal__v1.png"})
        self.assertTrue((self.out / "raw").is_dir())
        # the worker is alive: a further job still runs
        q2 = assets.submit_generations(q, self.tdir, MAP, STYLE, only=["seal"])
        self.assertEqual(self.run_flow(q, q2)[1][0]["status"], "done")

    def test_unfinished_jobs_stay_pending(self):
        q, _ = self.queue({"hero": noisy_photo()})
        tickets = [{"job_id": "does-not-exist", "asset": "hero", "seed": 1, "prefix": "hero-s1"}]
        pending, results = assets.process_finished(q, self.tdir, MAP, tickets)
        self.assertEqual((pending, results), (tickets, []))

    def test_a_ticket_is_processed_once(self):
        q, _ = self.queue({"hero": noisy_photo()})
        t = assets.submit_generations(q, self.tdir, MAP, STYLE, only=["hero"])
        self.wait(q, 1)
        pending, r1 = assets.process_finished(q, self.tdir, MAP, t)
        pending, r2 = assets.process_finished(q, self.tdir, MAP, pending)
        self.assertEqual((len(r1), r2, pending), (1, [], []))
        self.assertEqual(len(assets.list_versions(self.out, "hero")), 1)


if __name__ == "__main__":
    unittest.main()
