"""JSON API: real HTTP against a server on port 0, temp root, fake ComfyUI (no network but 127.0.0.1)."""
import dataclasses
import http.client
import json
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from PIL import Image

from app.config import load_config
from app.server import make_server

FIX = Path(__file__).parent / "fixtures"
UNICODE = "We’re “so” happy — Café & <b>\nline"
TEXTS_ALL = "  ’ “ ” é & < >\nsecond line \n"  # leading/trailing whitespace must survive too


def photo_map():
    """The fixture map reduced to one photo asset (hero): enough for the generate/choose/approve flow."""
    m = json.loads((FIX / "map_min.json").read_text(encoding="utf-8"))
    m["assets"] = {"hero": m["assets"]["hero"]}
    m["slots"] = [s for s in m["slots"] if s["asset"] in (None, "hero")]
    m["envelope"] = None
    return m


def fake_generate(gate=None):
    def gen(cfg, prompt, width, height, seed, prefix, out_dir):
        if gate is not None:
            gate.wait(30)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{prefix}_00001_.png"
        Image.new("RGB", (width, height), (120, 140, 100)).save(p)
        return [p]
    return gen


class ApiBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "models").mkdir()
        (self.root / "config.json").write_text('{"secret": "do-not-leak"}', encoding="utf-8")
        self.cfg = dataclasses.replace(
            load_config(FIX / "config.json"), root=self.root, models_dir=self.root / "models",
            comfy_url="http://127.0.0.1:9",  # nothing listens: refused at once
        )
        self.start()

    def start(self, generate_fn=None):
        server = make_server(self.cfg, 0, generate_fn=generate_fn)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
        thread.start()
        self.port = server.server_address[1]

        def stop():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.addCleanup(stop)
        return server

    def call(self, method, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data is not None else {})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                status, payload = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, payload = e.code, e.read()
        return status, json.loads(payload.decode("utf-8"))

    def get(self, p):
        return self.call("GET", p)

    def post(self, p, b=None):
        return self.call("POST", p, {} if b is None else b)

    def put(self, p, b):
        return self.call("PUT", p, b)

    # ---- fixtures on disk (what Claude / the owner's session would write) ----
    def make_skeleton(self, name="mini", map_=None):
        st, body = self.post("/api/skeletons", {"name": name, "design_id": "DAXXXXXXXXX"})
        self.assertEqual(st, 200, body)
        m = map_ if map_ is not None else json.loads((FIX / "map_min.json").read_text(encoding="utf-8"))
        m = dict(m, skeleton=name)
        (self.root / "skeletons" / name / "map.json").write_text(json.dumps(m), encoding="utf-8")
        return body

    def make_template(self, name="t1", skeleton="mini"):
        st, body = self.post("/api/templates", {"name": name, "skeleton": skeleton, "brief": "calm sage"})
        self.assertEqual(st, 200, body)
        return body["job"]

    def tdir(self, name="t1"):
        return self.root / "templates" / name

    def write_style(self, name="t1"):
        shutil.copy(FIX / "style_min.json", self.tdir(name) / "style.json")

    def read_state(self, name="t1"):
        return json.loads((self.tdir(name) / "state.json").read_text(encoding="utf-8"))

    def set_state(self, name="t1", statuses=None, **extra):
        st = self.read_state(name)
        for step, s in (statuses or {}).items():
            st["steps"][step]["status"] = s
        st.update(extra)
        (self.tdir(name) / "state.json").write_text(json.dumps(st), encoding="utf-8")

    def finish_job(self, job, status="done", summary="ok", corrupt=False, folder="done"):
        base = self.root / ("skeletons/" + job["skeleton"] if job["type"] == "map_skeleton" else "templates/" + job["template"])
        res = base / "jobs" / f"{job['id']}.result.json"
        res.parent.mkdir(parents=True, exist_ok=True)
        res.write_text("{broken" if corrupt else json.dumps({"status": status, "summary": summary, "outputs": {}, "checks": []}),
                       encoding="utf-8")
        dest = self.root / "jobs" / folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(self.root / "jobs" / "pending" / f"{job['id']}.json", dest / f"{job['id']}.json")

    def pending(self, type_=None):
        files = sorted((self.root / "jobs" / "pending").glob("*.json"))
        jobs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
        return [j for j in jobs if type_ in (None, j["type"])]

    def apply_ready(self):
        """Skeleton + template with style/images/texts approved and texts.json written."""
        self.make_skeleton()
        self.make_template()
        self.write_style()
        (self.tdir() / "texts.json").write_text(json.dumps({"p1/text/names": "A & B"}), encoding="utf-8")
        self.set_state(statuses={"style": "approved", "images": "approved", "texts": "approved"})

    def wait_for(self, fn, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            v = fn()
            if v:
                return v
            time.sleep(0.05)
        self.fail("timed out")


class SpecTests(ApiBase):
    """The tests the brief lists."""

    def test_create_template_flow(self):
        self.make_skeleton()
        job = self.make_template()
        pending = self.pending()
        self.assertEqual([j["type"] for j in pending], ["map_skeleton", "style_directions"])
        self.assertEqual(pending[1]["id"], job["id"])
        self.assertEqual(pending[1]["template"], "t1")
        self.assertEqual(pending[1]["inputs"]["brief"], "calm sage")
        st, t = self.get("/api/templates/t1")
        self.assertEqual(st, 200)
        self.assertEqual(t["state"]["steps"]["style"]["status"], "waiting_claude")
        self.assertEqual(self.get("/api/templates")[1]["templates"][0]["name"], "t1")

    def test_apply_twice_conflict(self):
        self.apply_ready()
        st, body = self.post("/api/templates/t1/apply")
        self.assertEqual(st, 200, body)
        job = self.pending("apply_canva")[0]
        self.assertIsNone(job["target_design_id"])
        self.assertEqual(self.read_state()["steps"]["apply"]["status"], "waiting_claude")
        st, body = self.post("/api/templates/t1/apply")
        self.assertEqual(st, 409)
        self.assertIn("error", body)
        self.assertEqual(len(self.pending("apply_canva")), 1)

    def test_apply_refused_when_texts_stale(self):
        self.apply_ready()
        self.set_state(statuses={"texts": "stale"})
        st, body = self.post("/api/templates/t1/apply")
        self.assertEqual(st, 409)
        self.assertIn("error", body)
        self.assertEqual(self.pending("apply_canva"), [])

    def test_apply_refused_when_images_stale(self):
        self.apply_ready()
        self.set_state(statuses={"images": "stale"})
        self.assertEqual(self.post("/api/templates/t1/apply")[0], 409)
        self.assertEqual(self.pending("apply_canva"), [])

    def test_files_path_traversal_blocked(self):
        self.make_skeleton()
        self.make_template()
        # control: a legitimate file under templates/ is served with the right type
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/files/templates/t1/state.json", timeout=5) as r:
            self.assertEqual(r.status, 200)
            self.assertIn("application/json", r.headers["Content-Type"])
            self.assertIn("skeleton", json.loads(r.read().decode("utf-8")))
        for path in ("/files/../config.json", "/files/%2e%2e/config.json", "/files/..%2fconfig.json",
                     "/files/skeletons/../config.json", "/files/templates/%2e%2e/%2e%2e/config.json",
                     "/files/config.json", "/files/", "/files/templates", "/files/templates/%00"):
            with self.subTest(path=path):
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
                conn.request("GET", path)
                resp = conn.getresponse()
                body = resp.read()
                conn.close()
                self.assertEqual(resp.status, 404)
                self.assertNotIn(b"do-not-leak", body)

    def test_files_serves_image_with_content_type(self):
        self.make_skeleton()
        self.make_template()
        (self.tdir() / "assets").mkdir()
        Image.new("RGB", (4, 4)).save(self.tdir() / "assets" / "x.png")
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/files/templates/t1/assets/x.png", timeout=5) as r:
            self.assertEqual(r.headers["Content-Type"], "image/png")
            self.assertTrue(r.read().startswith(b"\x89PNG"))

    def test_bad_json_body_400(self):
        for raw in (b"{not json", b"[1, 2]", b'"str"', b"\xff\xfe\x00bad"):
            with self.subTest(raw=raw):
                st, body = self.call("POST", "/api/templates", raw=raw)
                self.assertEqual(st, 400)
                self.assertIsInstance(body["error"], str)
        self.assertEqual(self.call("PUT", "/api/templates/t1/texts", raw=b"{")[0], 400)

    def test_unicode_texts_roundtrip(self):
        self.make_skeleton()
        self.make_template()
        texts = {"p1/text/intro": UNICODE, "p1/text/names": TEXTS_ALL}
        st, body = self.put("/api/templates/t1/texts", texts)
        self.assertEqual(st, 200, body)
        st, t = self.get("/api/templates/t1")
        self.assertEqual(t["texts"], texts)
        on_disk = json.loads((self.tdir() / "texts.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk, texts)
        self.assertIn("We’re “so” happy — Café & <b>".encode("utf-8"), (self.tdir() / "texts.json").read_bytes())

    def test_texts_travel_to_the_apply_job_unchanged(self):
        self.apply_ready()
        texts = {"p1/text/intro": UNICODE, "p1/text/names": TEXTS_ALL}
        self.assertEqual(self.put("/api/templates/t1/texts", texts)[0], 200)
        self.set_state(statuses={"texts": "approved"})
        self.assertEqual(self.post("/api/templates/t1/apply")[0], 200)
        self.assertEqual(self.pending("apply_canva")[0]["inputs"]["texts"], texts)


class ErrorTests(ApiBase):
    def test_unknown_routes_and_names_are_404_json(self):
        for method, path in (("GET", "/api/nope"), ("GET", "/api/templates/nope"), ("GET", "/api/skeletons/nope"),
                             ("GET", "/api/templates/BAD%20NAME"), ("POST", "/api/templates/nope/apply"),
                             ("PUT", "/api/templates/nope/texts"), ("DELETE", "/api/templates/x")):
            with self.subTest(path=path):
                st, body = self.call(method, path, {} if method != "GET" else None)
                self.assertIn(st, (404, 405))
                self.assertIsInstance(body["error"], str)

    def test_unexpected_error_is_500_without_traceback(self):
        with mock.patch("app.api.list_templates", side_effect=RuntimeError("boom-secret")), \
                mock.patch("sys.stderr"):
            st, body = self.get("/api/templates")
        self.assertEqual(st, 500)
        self.assertEqual(list(body), ["error"])
        self.assertNotIn("Traceback", body["error"])
        self.assertNotIn("boom-secret", body["error"])

    def test_health_still_works(self):
        st, body = self.get("/api/health")
        self.assertEqual((st, body["ok"], body["models_mounted"]), (200, True, True))


class SkeletonTests(ApiBase):
    def test_create_and_read(self):
        st, body = self.post("/api/skeletons", {"name": "mini", "design_id": "DAXXXXXXXXX"})
        self.assertEqual(st, 200, body)
        self.assertEqual(body["job"]["type"], "map_skeleton")
        self.assertEqual(body["job"]["inputs"]["design_id"], "DAXXXXXXXXX")
        sk = json.loads((self.root / "skeletons" / "mini" / "skeleton.json").read_text(encoding="utf-8"))
        self.assertEqual(sk["design_id"], "DAXXXXXXXXX")
        st, listing = self.get("/api/skeletons")
        self.assertEqual([(s["name"], s["design_id"], s["has_map"]) for s in listing["skeletons"]],
                         [("mini", "DAXXXXXXXXX", False)])
        st, one = self.get("/api/skeletons/mini")
        self.assertEqual((st, one["design_id"], one["map"]), (200, "DAXXXXXXXXX", None))

    def test_map_job_result_is_exposed(self):
        job = self.make_skeleton()["job"]
        self.finish_job(job, summary="mapped 9 slots")
        one = self.get("/api/skeletons/mini")[1]
        self.assertEqual(one["job"]["status"], "done")
        self.assertEqual(one["job"]["summary"], "mapped 9 slots")
        self.assertTrue(one["map"]["slots"])
        self.assertEqual(one["map_problems"], [])

    def test_protected_design_refused_and_nothing_created(self):
        st, body = self.post("/api/skeletons", {"name": "orig", "design_id": "DAHarqlqips"})
        self.assertEqual(st, 409)
        self.assertIn("error", body)
        self.assertFalse((self.root / "skeletons" / "orig").exists())
        self.assertEqual(self.pending(), [])

    def test_bad_input_and_duplicates(self):
        self.assertEqual(self.post("/api/skeletons", {"name": "Bad Name", "design_id": "DAX"})[0], 400)
        self.assertEqual(self.post("/api/skeletons", {"name": "ok", "design_id": ""})[0], 400)
        self.assertEqual(self.post("/api/skeletons", {"name": "ok", "design_id": "bad id!"})[0], 400)
        self.assertEqual(self.post("/api/skeletons", {"name": "ok"})[0], 400)
        self.assertEqual(self.post("/api/skeletons", {"name": "ok", "design_id": "DAX"})[0], 200)
        self.assertEqual(self.post("/api/skeletons", {"name": "ok", "design_id": "DAY"})[0], 409)
        self.assertEqual(len(self.pending("map_skeleton")), 1)

    def test_roles_put_updates_map(self):
        self.make_skeleton()
        st, body = self.put("/api/skeletons/mini/roles", {"p1/text/names": "couple-names", "p1/text/intro": "lead"})
        self.assertEqual(st, 200, body)
        slots = {s["locator"]: s for s in json.loads((self.root / "skeletons/mini/map.json").read_text(encoding="utf-8"))["slots"]}
        self.assertEqual(slots["p1/text/names"]["role"], "couple-names")
        self.assertEqual(slots["p1/text/intro"]["role"], "lead")
        self.assertEqual(slots["p1/image/hero"]["role"], "hero")  # untouched

    def test_roles_put_validation_writes_nothing(self):
        self.make_skeleton()
        path = self.root / "skeletons/mini/map.json"
        before = path.read_bytes()
        for bad in ({"p1/text/nope": "x"}, {"p1/text/names": ""}, {"p1/text/names": 5}, {}, {"p1/text/names": None}):
            with self.subTest(bad=bad):
                st, body = self.put("/api/skeletons/mini/roles", bad)
                self.assertEqual(st, 400)
                self.assertIsInstance(body["error"], str)
                self.assertEqual(path.read_bytes(), before)
        # a map that is already invalid is re-validated and refused, not rewritten
        m = json.loads(before)
        m["assets"]["hero"]["kind"] = "nonsense"
        path.write_text(json.dumps(m), encoding="utf-8")
        before = path.read_bytes()
        st, body = self.put("/api/skeletons/mini/roles", {"p1/text/names": "x"})
        self.assertEqual(st, 400)
        self.assertTrue(body["problems"])
        self.assertEqual(path.read_bytes(), before)

    def test_roles_without_map_is_409(self):
        self.post("/api/skeletons", {"name": "bare", "design_id": "DAX"})
        self.assertEqual(self.put("/api/skeletons/bare/roles", {"a": "b"})[0], 409)


class TemplateTests(ApiBase):
    def test_create_validation(self):
        self.make_skeleton()
        self.assertEqual(self.post("/api/templates", {"name": "t1", "skeleton": "nope", "brief": "x"})[0], 404)
        self.assertEqual(self.post("/api/templates", {"name": "Bad Name", "skeleton": "mini", "brief": "x"})[0], 400)
        self.assertEqual(self.post("/api/templates", {"name": "t1", "skeleton": "mini"})[0], 400)
        self.assertEqual(self.post("/api/templates", {"name": "t1", "skeleton": "mini", "brief": 5})[0], 400)
        self.assertFalse((self.root / "templates").exists() and list((self.root / "templates").iterdir()))
        self.make_template()
        self.assertEqual(self.post("/api/templates", {"name": "t1", "skeleton": "mini", "brief": "x"})[0], 409)
        self.assertEqual(len(self.pending("style_directions")), 1)

    def test_get_template_payload(self):
        self.make_skeleton()
        self.make_template()
        self.write_style()
        self.put("/api/templates/t1/texts", {"p1/text/intro": "x" * 200})
        t = self.get("/api/templates/t1")[1]
        for key in ("state", "style", "texts", "length_warnings", "assets", "jobs", "job_results", "map", "brief", "can_start"):
            self.assertIn(key, t)
        self.assertEqual(t["style"]["name"], "Sage Linen")
        self.assertIn("p1/text/intro", t["length_warnings"])
        self.assertEqual({a["asset"] for a in t["assets"]}, {"hero", "florals", "envelope", "seal"})
        self.assertEqual(t["jobs"][0]["type"], "style_directions")

    def test_put_style_validates(self):
        self.make_skeleton()
        self.make_template()
        style = json.loads((FIX / "style_min.json").read_text(encoding="utf-8"))
        self.assertEqual(self.put("/api/templates/t1/style", style)[0], 200)
        self.assertEqual(self.get("/api/templates/t1")[1]["style"], style)
        before = (self.tdir() / "style.json").read_bytes()
        bad = dict(style, palette={"background": "red"})
        st, body = self.put("/api/templates/t1/style", bad)
        self.assertEqual(st, 400)
        self.assertTrue(body["problems"])
        self.assertEqual((self.tdir() / "style.json").read_bytes(), before)

    def test_put_texts_validates_and_warns(self):
        self.make_skeleton()
        self.make_template()
        before_exists = (self.tdir() / "texts.json").exists()
        st, body = self.put("/api/templates/t1/texts", {"p1/image/hero": "x"})
        self.assertEqual(st, 400)
        self.assertEqual(before_exists, (self.tdir() / "texts.json").exists())
        self.assertEqual(self.put("/api/templates/t1/texts", {"p1/text/names": 5})[0], 400)
        st, body = self.put("/api/templates/t1/texts", {"p1/text/names": "Much too long a line for names"})
        self.assertEqual(st, 200)
        self.assertIn("p1/text/names", body["length_warnings"])

    def test_texts_request_creates_job_and_waits(self):
        self.make_skeleton()
        self.make_template()
        self.assertEqual(self.post("/api/templates/t1/texts/request")[0], 409)  # style not approved
        self.write_style()
        self.set_state(statuses={"style": "approved", "images": "approved"})
        st, body = self.post("/api/templates/t1/texts/request")
        self.assertEqual(st, 200, body)
        self.assertEqual(self.pending("write_texts")[0]["template"], "t1")
        self.assertEqual(self.read_state()["steps"]["texts"]["status"], "waiting_claude")
        self.assertEqual(self.post("/api/templates/t1/texts/request")[0], 409)  # one at a time
        self.assertEqual(len(self.pending("write_texts")), 1)

    def test_verify_needs_copy_and_approved_apply(self):
        self.apply_ready()
        self.assertEqual(self.post("/api/templates/t1/verify")[0], 409)  # no copy yet
        self.set_state(statuses={"apply": "approved"}, canva_copy_id="DACOPY1")
        st, body = self.post("/api/templates/t1/verify")
        self.assertEqual(st, 200, body)
        self.assertEqual(self.pending("verify")[0]["target_design_id"], "DACOPY1")
        self.assertEqual(self.read_state()["steps"]["verify"]["status"], "waiting_claude")
        self.assertEqual(self.post("/api/templates/t1/verify")[0], 409)  # Canva busy

    def test_apply_targets_recorded_copy_and_respects_busy(self):
        self.apply_ready()
        self.set_state(canva_copy_id="DACOPY1")
        self.assertEqual(self.post("/api/templates/t1/apply")[0], 200)
        self.assertEqual(self.pending("apply_canva")[0]["target_design_id"], "DACOPY1")

    def test_apply_refused_when_a_canva_job_is_running(self):
        self.apply_ready()
        (self.root / "jobs" / "running").mkdir(parents=True)
        (self.root / "jobs" / "running" / "20260101T000000Z-verify.json").write_text(
            json.dumps({"id": "20260101T000000Z-verify", "type": "verify"}), encoding="utf-8")
        st, body = self.post("/api/templates/t1/apply")
        self.assertEqual(st, 409)
        self.assertEqual(self.pending("apply_canva"), [])

    def test_apply_without_design_id_in_map_is_409_not_500(self):
        self.apply_ready()
        mp = self.root / "skeletons/mini/map.json"
        m = json.loads(mp.read_text(encoding="utf-8"))
        m["design_id"] = ""
        mp.write_text(json.dumps(m), encoding="utf-8")
        self.assertEqual(self.post("/api/templates/t1/apply")[0], 409)


class StepFlowTests(ApiBase):
    def test_job_created_then_done_then_review(self):  # R13
        self.make_skeleton()
        job = self.make_template()
        self.assertEqual(self.read_state()["steps"]["style"]["status"], "waiting_claude")
        # still waiting while the job has no result
        self.assertEqual(self.get("/api/templates/t1")[1]["state"]["steps"]["style"]["status"], "waiting_claude")
        self.finish_job(job, "done", "3 directions")
        t = self.get("/api/templates/t1")[1]
        self.assertEqual(t["state"]["steps"]["style"]["status"], "review")
        self.assertEqual(t["job_results"]["style"]["summary"], "3 directions")
        self.assertEqual(self.read_state()["steps"]["style"]["status"], "review")  # persisted
        # an old done result never moves an approved step back
        self.set_state(statuses={"style": "approved"})
        self.assertEqual(self.get("/api/templates/t1")[1]["state"]["steps"]["style"]["status"], "approved")

    def test_failed_result_goes_back_to_draft_with_summary(self):
        self.make_skeleton()
        job = self.make_template()
        self.finish_job(job, "failed", "Canva mcp недоступний", folder="failed")
        t = self.get("/api/templates/t1")[1]
        self.assertEqual(t["state"]["steps"]["style"]["status"], "draft")
        self.assertEqual(t["job_results"]["style"]["status"], "failed")
        self.assertEqual(t["job_results"]["style"]["summary"], "Canva mcp недоступний")

    def test_corrupt_result_goes_back_to_draft_and_is_shown(self):  # Review Focus 5
        self.make_skeleton()
        job = self.make_template()
        self.finish_job(job, corrupt=True)
        t = self.get("/api/templates/t1")[1]
        self.assertEqual(t["state"]["steps"]["style"]["status"], "draft")
        self.assertEqual(t["job_results"]["style"]["status"], "corrupt")
        self.assertTrue(t["job_results"]["style"]["summary"])

    def test_job_in_failed_folder_without_result_goes_to_draft(self):
        self.make_skeleton()
        job = self.make_template()
        dest = self.root / "jobs" / "failed"
        dest.mkdir(parents=True)
        shutil.move(self.root / "jobs" / "pending" / f"{job['id']}.json", dest / f"{job['id']}.json")
        t = self.get("/api/templates/t1")[1]
        self.assertEqual(t["state"]["steps"]["style"]["status"], "draft")

    def test_get_jobs_reconciles_and_lists_corrupt_job_files(self):
        self.make_skeleton()
        job = self.make_template()
        self.finish_job(job, "done", "ok")
        (self.root / "jobs" / "pending" / "garbage.json").write_text("{x", encoding="utf-8")
        st, body = self.get("/api/jobs")
        self.assertEqual(st, 200)
        by_id = {j["id"]: j for j in body["jobs"]}
        self.assertEqual(by_id[job["id"]]["result"]["status"], "done")
        self.assertEqual(by_id["garbage"]["state"], "corrupt")
        self.assertEqual(self.read_state()["steps"]["style"]["status"], "review")

    def test_approve_requires_previous_step_approved(self):
        self.make_skeleton()
        self.make_template()
        self.set_state(statuses={"images": "review"})
        st, body = self.post("/api/templates/t1/approve", {"step": "images"})
        self.assertEqual(st, 409)
        self.assertIn("error", body)
        self.assertEqual(self.read_state()["steps"]["images"]["status"], "review")
        self.assertEqual(self.post("/api/templates/t1/approve", {"step": "bogus"})[0], 400)
        self.assertEqual(self.post("/api/templates/t1/approve", {})[0], 400)

    def test_approve_refused_unless_ready_for_review(self):
        self.make_skeleton()
        self.make_template()  # style is waiting_claude
        self.assertEqual(self.post("/api/templates/t1/approve", {"step": "style"})[0], 409)
        self.set_state(statuses={"style": "review"})
        self.assertEqual(self.post("/api/templates/t1/approve", {"step": "style"})[0], 200)
        self.assertEqual(self.read_state()["steps"]["style"]["status"], "approved")

    def test_reopen_marks_later_steps_stale(self):  # Review Focus 2
        self.apply_ready()
        st, _ = self.post("/api/templates/t1/reopen", {"step": "style"})
        self.assertEqual(st, 200)
        steps = {k: v["status"] for k, v in self.read_state()["steps"].items()}
        self.assertEqual(steps["style"], "review")
        self.assertEqual((steps["images"], steps["texts"]), ("stale", "stale"))
        self.assertEqual(self.post("/api/templates/t1/apply")[0], 409)
        self.assertEqual(self.post("/api/templates/t1/reopen", {"step": "apply"})[0], 409)  # not approved

    def test_editing_an_approved_style_or_texts_makes_later_steps_stale(self):
        self.apply_ready()
        style = json.loads((FIX / "style_min.json").read_text(encoding="utf-8"))
        self.assertEqual(self.put("/api/templates/t1/style", style)[0], 200)
        steps = {k: v["status"] for k, v in self.read_state()["steps"].items()}
        self.assertEqual((steps["style"], steps["images"], steps["texts"]), ("review", "stale", "stale"))
        self.assertEqual(self.post("/api/templates/t1/apply")[0], 409)
        self.set_state(statuses={"style": "approved", "images": "approved", "texts": "approved", "apply": "approved"})
        self.assertEqual(self.put("/api/templates/t1/texts", {"p1/text/names": "Z"})[0], 200)
        steps = {k: v["status"] for k, v in self.read_state()["steps"].items()}
        self.assertEqual((steps["texts"], steps["apply"]), ("review", "stale"))
        self.assertEqual(steps["images"], "approved")


class ImageTests(ApiBase):
    def setup_photo_template(self):
        self.make_skeleton(map_=photo_map())
        self.make_template()
        self.write_style()
        self.set_state(statuses={"style": "approved"})

    def add_version(self, n, size=(1200, 800)):
        (self.tdir() / "assets").mkdir(exist_ok=True)
        Image.new("RGB", size, (90, 100, 80)).save(self.tdir() / "assets" / f"hero__v{n}.jpg")
        return f"hero__v{n}.jpg"

    def test_generate_refused_when_models_disk_missing(self):
        self.setup_photo_template()
        shutil.rmtree(self.root / "models")
        t0 = time.monotonic()
        st, body = self.post("/api/templates/t1/images/generate")
        self.assertEqual(st, 409)
        self.assertEqual(body["error"], "диск моделей не змонтовано")
        self.assertLess(time.monotonic() - t0, 5)
        self.assertFalse((self.tdir() / "gen_tickets.json").exists())

    def test_generate_refused_when_comfy_down_within_5s(self):
        self.setup_photo_template()
        t0 = time.monotonic()
        st, body = self.post("/api/templates/t1/images/generate")
        self.assertEqual(st, 409)
        self.assertEqual(body["error"], "ComfyUI недоступний — запустіть run.sh")
        self.assertLess(time.monotonic() - t0, 5)
        self.assertFalse((self.tdir() / "gen_tickets.json").exists())

    def test_generate_needs_approved_style_map_and_valid_assets(self):
        self.make_skeleton(map_=photo_map())
        self.make_template()
        self.write_style()
        with mock.patch("app.comfy.ping", return_value=True):
            self.assertEqual(self.post("/api/templates/t1/images/generate")[0], 409)  # style not approved
            self.set_state(statuses={"style": "approved"})
            self.assertEqual(self.post("/api/templates/t1/images/generate", {"assets": ["nope"]})[0], 400)
            self.assertEqual(self.post("/api/templates/t1/images/generate", {"assets": "hero"})[0], 400)
            self.assertEqual(self.post("/api/templates/t1/images/generate", {"prompt_override": "x"})[0], 400)
            self.assertEqual(self.post("/api/templates/t1/images/generate", {"assets": ["hero"], "prompt_override": ""})[0], 400)
        self.assertFalse((self.tdir() / "gen_tickets.json").exists())

    def test_generate_end_to_end_with_fake_comfy(self):  # R14 happy path
        self.cfg_start = self.start(generate_fn=fake_generate())
        self.setup_photo_template()
        with mock.patch("app.comfy.ping", return_value=True):
            st, body = self.post("/api/templates/t1/images/generate", {"assets": ["hero"], "prompt_override": "a custom prompt"})
        self.assertEqual(st, 200, body)
        ticket = body["tickets"][0]
        self.assertEqual(ticket["asset"], "hero")
        self.assertIn("a custom prompt", ticket["prompt"])
        saved = json.loads((self.tdir() / "gen_tickets.json").read_text(encoding="utf-8"))
        self.assertEqual([t["job_id"] for t in saved["pending"]], [ticket["job_id"]])

        def done():
            t = self.get("/api/templates/t1")[1]
            return t if t["state"]["chosen"].get("hero") else None
        t = self.wait_for(done)
        self.assertEqual(t["state"]["chosen"]["hero"], "hero__v1.jpg")
        asset = next(a for a in t["assets"] if a["asset"] == "hero")
        self.assertEqual([v["file"] for v in asset["versions"]], ["hero__v1.jpg"])
        self.assertEqual(asset["versions"][0]["url"], "/files/templates/t1/assets/hero__v1.jpg")
        self.assertEqual(asset["generation"]["pending"], [])
        self.assertEqual(t["state"]["steps"]["images"]["status"], "review")  # every asset chosen, nothing pending
        saved = json.loads((self.tdir() / "gen_tickets.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["pending"], [])
        self.assertEqual(saved["recent"][-1]["status"], "done")
        gen = self.get("/api/gen")[1]
        self.assertIn("queue", gen)
        self.assertEqual(gen["templates"]["t1"]["pending"], [])

    def test_pending_ticket_is_lost_after_restart(self):  # R14
        gate = threading.Event()
        self.addCleanup(gate.set)
        self.start(generate_fn=fake_generate(gate))  # server A: the generation never finishes
        self.setup_photo_template()
        with mock.patch("app.comfy.ping", return_value=True):
            st, body = self.post("/api/templates/t1/images/generate")
        self.assertEqual(st, 200, body)
        a = next(x for x in self.get("/api/templates/t1")[1]["assets"] if x["asset"] == "hero")
        self.assertEqual(len(a["generation"]["pending"]), 1)  # still pending in the same process
        saved = json.loads((self.tdir() / "gen_tickets.json").read_text(encoding="utf-8"))
        self.assertEqual(len(saved["pending"]), 1)
        self.start()  # server B on the same root: fresh queue, nobody knows the ticket
        t = self.get("/api/templates/t1")[1]
        a = next(x for x in t["assets"] if x["asset"] == "hero")
        self.assertEqual(a["generation"]["pending"], [])
        self.assertEqual(a["generation"]["last"]["status"], "lost")
        self.assertIn("генерацію перервано перезапуском — згенеруйте ще раз", a["generation"]["last"]["problems"][0])
        saved = json.loads((self.tdir() / "gen_tickets.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["pending"], [])
        self.assertEqual(saved["recent"][-1]["status"], "lost")
        self.assertEqual(t["state"]["steps"]["images"]["status"], "draft")  # nothing chosen: not "ready"

    def test_gen_endpoint_marks_lost_too(self):
        self.setup_photo_template()
        (self.tdir() / "gen_tickets.json").write_text(json.dumps({"pending": [
            {"job_id": "deadbeef0000", "asset": "hero", "seed": 1, "prefix": "hero-s1", "width": 64, "height": 64,
             "prompt": "p", "kind": "photo"}], "recent": []}), encoding="utf-8")
        gen = self.get("/api/gen")[1]
        self.assertEqual(gen["templates"]["t1"]["pending"], [])
        self.assertEqual(gen["templates"]["t1"]["recent"][-1]["status"], "lost")

    def test_choose_updates_state_and_validates(self):
        self.setup_photo_template()
        v1, v2 = self.add_version(1), self.add_version(2)
        st, body = self.post("/api/templates/t1/images/choose", {"asset": "hero", "file": v2})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.read_state()["chosen"], {"hero": v2})
        for bad in ({"asset": "hero", "file": "../state.json"}, {"asset": "hero", "file": "hero__v9.jpg"},
                    {"asset": "nope", "file": v1}, {"asset": "hero"}, {"file": v1}):
            with self.subTest(bad=bad):
                self.assertEqual(self.post("/api/templates/t1/images/choose", bad)[0], 400)
        self.assertEqual(self.read_state()["chosen"], {"hero": v2})
        # every asset chosen and nothing generating -> the images step is ready for review
        self.assertEqual(self.read_state()["steps"]["images"]["status"], "review")

    def test_choosing_after_approval_reopens_images(self):
        self.apply_ready()
        mp = self.root / "skeletons/mini/map.json"
        mp.write_text(json.dumps(dict(photo_map(), skeleton="mini")), encoding="utf-8")
        v1, v2 = self.add_version(1), self.add_version(2)
        self.set_state(chosen={"hero": v1})
        self.assertEqual(self.post("/api/templates/t1/images/choose", {"asset": "hero", "file": v2})[0], 200)
        steps = {k: v["status"] for k, v in self.read_state()["steps"].items()}
        self.assertEqual((steps["images"], steps["texts"]), ("review", "stale"))

    def test_approve_images_runs_checks_and_writes_manifest(self):
        self.setup_photo_template()
        bad = self.add_version(1, size=(300, 300))  # wrong aspect for a 1200x800 frame
        self.post("/api/templates/t1/images/choose", {"asset": "hero", "file": bad})
        st, body = self.post("/api/templates/t1/approve", {"step": "images"})
        self.assertEqual(st, 409)
        self.assertTrue(body["problems"])
        self.assertEqual(self.read_state()["steps"]["images"]["status"], "review")
        self.assertFalse((self.tdir() / "assets" / "manifest.json").exists())
        good = self.add_version(2)
        self.post("/api/templates/t1/images/choose", {"asset": "hero", "file": good})
        st, body = self.post("/api/templates/t1/approve", {"step": "images"})
        self.assertEqual(st, 200, body)
        self.assertEqual(self.read_state()["steps"]["images"]["status"], "approved")
        manifest = json.loads((self.tdir() / "assets" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["assets"]["hero"]["chosen"], good)


if __name__ == "__main__":
    unittest.main()
