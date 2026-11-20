"""JSON API of the studio: routing, error mapping and the handlers that join the store, step states,
job inbox, schemas, generation queue and asset pipeline.

`Api.handle(method, path, raw_body)` returns (status, payload); server.py only does HTTP.
Errors are always {"error": str}: 400 bad input (malformed JSON, ValueError, TypeError, AssetError,
validation messages), 404 unknown template/skeleton/route, 409 refusals (GuardError, step not startable,
Canva busy, stale steps, ComfyUI or the models disk missing), 500 only for the unexpected (the traceback
goes to stderr, never into the body).

Step transitions are owned here (R13): requesting a Claude job sets its step to waiting_claude; reading a
template or the job list reconciles waiting_claude steps with the job results (done -> review,
failed/corrupt -> draft). Every state.json read-modify-write holds store.STATE_LOCK. Nothing is deleted.
"""
import copy
import json
import re
import sys
import traceback
from pathlib import Path

from app import assets, comfy, schema, steps, tickets
from app import texts as texts_mod
from app.config import Config
from app.genqueue import GenQueue
from app.guard import GuardError
from app.jobs import canva_busy, create_job, list_jobs, read_result
from app.steps import STEPS, now_utc
from app.store import (STATE_LOCK, CorruptJSON, create_template, list_templates, read_json, skeleton_dir,
                       template_dir, write_json_atomic)

MAX_BODY = 5 * 1024 * 1024
_DESIGN_ID = re.compile(r"[A-Za-z0-9_-]+")
# job type -> the step it works on
STEP_OF = {"style_directions": "style", "write_texts": "texts", "apply_canva": "apply", "verify": "verify"}
_ACTIVE = ("pending", "running")
BAD_STATE = "пошкоджений state.json"
NO_COPY = "Claude не записав id копії — перевірте /test-canva-studio"
_ROUTES: list = []


class ApiError(Exception):
    def __init__(self, status: int, message: str, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


def route(method: str, pattern: str):
    rx = re.compile(pattern)

    def deco(fn):
        _ROUTES.append((method, rx, fn))
        return fn
    return deco


def _opt(path: Path):
    """(data, None) | (None, None) when the file is absent | (None, message) when it is corrupt."""
    try:
        return read_json(path), None
    except FileNotFoundError:
        return None, None
    except CorruptJSON:
        return None, f"файл {path.name} пошкоджено"
    except OSError as e:
        return None, f"файл {path.name} не читається: {e.strerror or e}"


def _state_ok(state) -> bool:
    """Valid JSON is not enough: the step table every handler indexes must be complete."""
    st = state.get("steps") if isinstance(state, dict) else None
    return (isinstance(st, dict)
            and all(isinstance(st.get(s), dict) and st[s].get("status") in steps.STATUSES for s in STEPS)
            and isinstance(state.get("chosen", {}), dict))


def _text(body: dict, key: str) -> str:
    v = body.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ApiError(400, f"поле {key!r} має бути непорожнім рядком")
    return v


def _result_info(cfg: Config, job: dict) -> dict:
    """What the studio shows about a job's outcome: status None means 'no result yet'."""
    res = read_result(cfg, job)
    if res is not None:
        status = res.get("status") if isinstance(res.get("status"), str) else "corrupt"
        summary = res.get("summary") if isinstance(res.get("summary"), str) else ""
        checks = res.get("checks") if isinstance(res.get("checks"), list) else []
    elif job.get("state") == "failed":
        status, summary, checks = "failed", "Завдання лежить у failed/ без файла результату.", []
    else:
        status, summary, checks = None, None, []
    return {"job_id": job.get("id"), "type": job.get("type"), "folder": job.get("state"),
            "status": status, "summary": summary, "checks": checks}


def _latest(jobs: list, **match) -> dict:
    """{type: newest job} among jobs whose fields equal `match`."""
    out: dict = {}
    for j in jobs:
        if all(j.get(k) == v for k, v in match.items()) and isinstance(j.get("type"), str):
            if j["type"] not in out or (j.get("created_utc", ""), j["id"]) >= (out[j["type"]].get("created_utc", ""), out[j["type"]]["id"]):
                out[j["type"]] = j
    return out


class Api:
    def __init__(self, cfg: Config, generate_fn=None):
        self.cfg = cfg
        # one queue for the whole server; its log is <root>/logs/generations.jsonl
        self.queue = GenQueue(cfg, cfg.root / "logs" / "generations.jsonl", generate_fn)

    # ------------------------------------------------------------------ dispatch
    def handle(self, method: str, path: str, raw_body: bytes = b"") -> tuple[int, dict]:
        try:
            for m, rx, fn in _ROUTES:
                mt = rx.fullmatch(path)
                if mt and m == method:
                    body = self._parse(raw_body) if method in ("POST", "PUT") else {}
                    result = fn(self, body, **mt.groupdict())
                    return 200, result
            raise ApiError(404, "такого маршруту немає")
        except ApiError as e:
            return e.status, {"error": e.message, **e.extra}
        except GuardError as e:
            return 409, {"error": f"завдання відхилено: {e}"}
        except (assets.AssetError, ValueError, TypeError) as e:
            return 400, {"error": str(e)}
        except CorruptJSON as e:
            return self._unexpected(f"файл {e.path.name} пошкоджено")
        except Exception:
            return self._unexpected("внутрішня помилка студії; подробиці в журналі сервера")

    @staticmethod
    def _unexpected(message: str) -> tuple[int, dict]:
        traceback.print_exc(file=sys.stderr)
        return 500, {"error": message}

    @staticmethod
    def _parse(raw: bytes) -> dict:
        if len(raw) > MAX_BODY:
            raise ApiError(400, "тіло запиту завелике")
        if not raw.strip():
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ApiError(400, "тіло запиту не є коректним JSON (UTF-8)") from None
        if not isinstance(body, dict):
            raise ApiError(400, "тіло запиту має бути JSON-об'єктом")
        return body

    # ------------------------------------------------------------------ lookups
    def _tpl(self, name: str) -> Path:
        try:
            d = template_dir(self.cfg, name)
        except ValueError:
            raise ApiError(404, "шаблон не знайдено") from None
        if not (d / "state.json").is_file():
            raise ApiError(404, f"шаблон {name} не знайдено")
        return d

    def _state(self, d: Path) -> dict:
        """state.json, or 409 «пошкоджений state.json» when it is unreadable or lacks the step table."""
        try:
            state = read_json(d / "state.json")
        except (CorruptJSON, OSError):
            raise ApiError(409, BAD_STATE) from None
        if not _state_ok(state):
            raise ApiError(409, BAD_STATE)
        return state

    def _skel(self, name: str) -> Path:
        try:
            d = skeleton_dir(self.cfg, name)
        except ValueError:
            raise ApiError(404, "скелет не знайдено") from None
        if not d.is_dir():
            raise ApiError(404, f"скелет {name} не знайдено")
        return d

    def _map_opt(self, skeleton):
        """(map | None, problems): the map only when it is readable AND valid."""
        try:
            sdir = skeleton_dir(self.cfg, skeleton)
        except ValueError:
            return None, ["немає імені скелета"]
        m, err = _opt(sdir / "map.json")
        if err:
            return None, [err]
        if m is None:
            return None, []
        problems = schema.validate_map(m)
        return (None if problems else m), problems

    def _need_map(self, skeleton) -> dict:
        m, problems = self._map_opt(skeleton)
        if m is None:
            raise ApiError(409, "карти скелета ще немає" if not problems else "карта скелета недійсна: " + "; ".join(problems),
                           problems=problems)
        return m

    def _need_valid(self, d: Path, m: dict, what: str) -> dict:
        """style.json / texts.json as it is ON DISK (Claude's jobs write them without our validators):
        409 with the problems unless it exists and passes the same validator the PUT routes use."""
        data, err = _opt(d / f"{what}.json")
        if data is None:
            raise ApiError(409, err or f"{what}.json ще немає")
        problems = schema.validate_style(data, m) if what == "style" else texts_mod.validate_texts(data, m)
        if problems:
            raise ApiError(409, f"{what}.json недійсний: " + "; ".join(problems), problems=problems)
        return data

    def _mutate(self, d: Path, fn):
        """Locked read-modify-write of state.json; `fn(state)` returns the new state or None (no change)."""
        with STATE_LOCK:
            state = self._state(d)
            new = fn(state)
            if new is None:
                return state
            write_json_atomic(d / "state.json", new)
            return new

    def _set_status(self, d: Path, step: str, status: str):
        return self._mutate(d, lambda s: steps.set_status(s, step, status))

    def _touch(self, d: Path, step: str):
        """The owner changed `step`'s data: an approved step is reopened (later ones go stale), a draft or
        stale one becomes ready for review; one waiting for Claude is left alone."""
        def fn(state):
            status = state["steps"][step]["status"]
            if status == "approved":
                return steps.reopen(state, step)
            if status in ("draft", "stale"):
                return steps.set_status(state, step, "review")
            return None
        return self._mutate(d, fn)

    @staticmethod
    def _rel(*parts) -> str:
        return "/".join(parts)

    # ------------------------------------------------------------------ R13 / R14 reconcile
    def _raw_infos(self, name: str, jobs: list) -> dict:
        return {STEP_OF[t]: _result_info(self.cfg, j) for t, j in _latest(jobs, template=name).items() if t in STEP_OF}

    @staticmethod
    def _effective(infos: dict, state: dict) -> dict:
        """A done apply_canva with no canva_copy_id recorded counts as failed, visibly (R19)."""
        a = infos.get("apply")
        if a and a["status"] == "done" and state.get("canva_copy_id") is None:
            return dict(infos, apply=dict(a, status="failed", summary=NO_COPY, copy_missing=True))
        return infos

    def _reconcile_jobs(self, name: str, jobs: list) -> dict:
        """waiting_claude steps follow their newest job's result. Returns {step: result info} for the payload."""
        raw = self._raw_infos(name, jobs)

        def fn(state):
            new = state
            for step, info in self._effective(raw, state).items():
                if state["steps"][step]["status"] == "waiting_claude" and info["status"] is not None:
                    new = steps.set_status(new, step, "review" if info["status"] == "done" else "draft")
            return None if new is state else new
        return self._effective(raw, self._mutate(template_dir(self.cfg, name), fn))

    def _reconcile_images(self, name: str, m, data: dict) -> None:
        """draft -> review once every asset of the map has a chosen file and none is generating."""
        if not m or not m.get("assets"):
            return
        busy = {t.get("asset") for t in data["pending"]}

        def fn(state):
            chosen = state.get("chosen") or {}
            if (state["steps"]["images"]["status"] == "draft" and all(chosen.get(a) for a in m["assets"])
                    and not busy & set(m["assets"])):
                return steps.set_status(state, "images", "review")
            return None
        self._mutate(template_dir(self.cfg, name), fn)

    def _refresh(self, name: str, jobs=None) -> dict:
        """Process finished generations, then reconcile job and images steps. Returns the tickets data."""
        d = self._tpl(name)
        m, _ = self._map_opt(self._state(d).get("skeleton"))
        data = tickets.sync(self.cfg, self.queue, name, m)  # GEN_LOCK before STATE_LOCK
        self._reconcile_jobs(name, jobs if jobs is not None else list_jobs(self.cfg))
        self._reconcile_images(name, m, data)
        return data

    # ------------------------------------------------------------------ health
    @route("GET", r"/api/health")
    def health(self, body):
        return {"ok": True, "comfy_url": self.cfg.comfy_url, "models_mounted": self.cfg.models_dir.is_dir()}

    # ------------------------------------------------------------------ skeletons
    @route("GET", r"/api/skeletons")
    def list_skeletons(self, body):
        base = self.cfg.root / "skeletons"
        maps = [j for j in list_jobs(self.cfg) if j.get("type") == "map_skeleton"]
        out = []
        for p in sorted(base.iterdir()) if base.is_dir() else []:
            if p.is_dir():
                job = _latest([j for j in maps if j.get("skeleton") == p.name]).get("map_skeleton")
                out.append(self._skeleton_summary(p, job))
        return {"skeletons": out}

    def _skeleton_summary(self, sdir: Path, job) -> dict:
        m, _ = _opt(sdir / "map.json")
        meta, _ = _opt(sdir / "skeleton.json")
        design_id = (m or {}).get("design_id") or (meta or {}).get("design_id")
        return {"name": sdir.name, "design_id": design_id, "has_map": m is not None,
                "job": _result_info(self.cfg, job) if job else None}

    @route("POST", r"/api/skeletons")
    def create_skeleton(self, body):
        name, design_id = body.get("name"), body.get("design_id")
        sdir = skeleton_dir(self.cfg, name)  # ValueError -> 400
        if not isinstance(design_id, str) or not _DESIGN_ID.fullmatch(design_id):
            raise ApiError(400, "design_id має бути ідентифікатором Canva: літери, цифри, - і _")
        with STATE_LOCK:
            if sdir.exists():
                raise ApiError(409, f"скелет {name} уже існує")
            # the guard runs first: a refused (e.g. protected) design id leaves nothing on disk
            job = create_job(self.cfg, "map_skeleton", name, None, {"design_id": design_id}, None)
            write_json_atomic(sdir / "skeleton.json", {"name": name, "design_id": design_id, "created_utc": now_utc()})
        return {"name": name, "job": job}

    @route("GET", r"/api/skeletons/(?P<s>[^/]+)")
    def get_skeleton(self, body, s):
        sdir = self._skel(s)
        m, err = _opt(sdir / "map.json")
        jobs = [j for j in list_jobs(self.cfg) if j.get("type") == "map_skeleton" and j.get("skeleton") == s]
        job = _latest(jobs).get("map_skeleton")
        out = self._skeleton_summary(sdir, job)
        out.update(map=m, map_problems=([err] if err else schema.validate_map(m) if m is not None else []))
        return out

    @route("PUT", r"/api/skeletons/(?P<s>[^/]+)/roles")
    def put_roles(self, body, s):
        sdir = self._skel(s)
        if not body:
            raise ApiError(400, "очікується {locator: роль}")
        with STATE_LOCK:
            m, err = _opt(sdir / "map.json")
            if m is None:
                raise ApiError(409, err or "карти скелета ще немає")
            new = copy.deepcopy(m)
            slots = {x["locator"]: x for x in new.get("slots", []) if isinstance(x, dict) and isinstance(x.get("locator"), str)}
            problems = []
            for loc, role in body.items():
                if loc not in slots:
                    problems.append(f"{loc!r}: такого слота немає в карті")
                elif not isinstance(role, str) or not role.strip():
                    problems.append(f"{loc!r}: роль має бути непорожнім рядком")
                else:
                    slots[loc]["role"] = role
            problems += schema.validate_map(new)
            if problems:
                raise ApiError(400, "; ".join(problems), problems=problems)
            write_json_atomic(sdir / "map.json", new)
        return {"map": new}

    # ------------------------------------------------------------------ templates
    @route("GET", r"/api/templates")
    def list_templates_(self, body):
        out = []
        for name in list_templates(self.cfg):
            state, err = _opt(template_dir(self.cfg, name) / "state.json")
            if state is None or not _state_ok(state):
                out.append({"name": name, "error": err or BAD_STATE})
                continue
            out.append({"name": name, "skeleton": state.get("skeleton"),
                        "steps": {k: v.get("status") for k, v in (state.get("steps") or {}).items()}})
        return {"templates": out}

    @route("POST", r"/api/templates")
    def create_template_(self, body):
        name, skeleton = body.get("name"), body.get("skeleton")
        brief = _text(body, "brief")
        with STATE_LOCK:
            tdir = template_dir(self.cfg, name)  # ValueError -> 400
            sdir = skeleton_dir(self.cfg, skeleton)
            if not sdir.is_dir():
                raise ApiError(404, f"скелет {skeleton} не знайдено")
            if tdir.exists():
                raise ApiError(409, f"шаблон {name} уже існує")
            job = create_job(self.cfg, "style_directions", skeleton, name, {"brief": brief}, None)  # guard first
            create_template(self.cfg, name, skeleton)
            write_json_atomic(tdir / "brief.json", {"brief": brief})
            self._set_status(tdir, "style", "waiting_claude")
        return {"name": name, "job": job}

    @route("GET", r"/api/templates/(?P<t>[^/]+)")
    def get_template(self, body, t):
        d = self._tpl(t)
        all_jobs = list_jobs(self.cfg)
        data = self._refresh(t, all_jobs)
        state = self._state(d)
        skeleton = state.get("skeleton")
        m, map_problems = self._map_opt(skeleton)
        style, style_err = _opt(d / "style.json")
        texts, texts_err = _opt(d / "texts.json")
        brief, _ = _opt(d / "brief.json")
        mine = [j for j in all_jobs if j.get("template") == t]
        job_results = self._effective(self._raw_infos(t, all_jobs), state)
        warnings = texts_mod.length_warnings(texts, m) if texts is not None and m else {}
        return {
            "name": t, "skeleton": skeleton, "state": state, "brief": (brief or {}).get("brief"),
            "style": style, "texts": texts, "length_warnings": warnings,
            "font_checklist": texts_mod.font_checklist(m, style) if m and style else [],
            "problems": [p for p in (style_err, texts_err) if p] + map_problems
                        + (["style.json: " + x for x in schema.validate_style(style, m)] if style is not None and m else [])
                        + (["texts.json: " + x for x in texts_mod.validate_texts(texts, m)] if texts is not None and m else []),
            "map": m, "assets": self._assets_payload(t, d, state, m, style, data),
            "generation": {"pending": tickets.with_queue_state(self.queue, data["pending"]), "recent": data["recent"]},
            "jobs": [dict(_result_info(self.cfg, j), created_utc=j.get("created_utc")) for j in mine],
            "job_results": job_results,
            "can_start": {s: steps.can_start(state, s) for s in STEPS},
        }

    def _assets_payload(self, t, d, state, m, style, data) -> list:
        if not m:
            return []
        queued = {x["job_id"]: x for x in tickets.with_queue_state(self.queue, data["pending"])}
        prompts = (style or {}).get("image_prompts")
        out = []
        for asset, spec in m["assets"].items():
            versions = [{"n": n, "file": f, "url": f"/files/templates/{t}/assets/{f}"}
                        for n, f in assets.list_versions(d / "assets", asset)]
            last = next((r for r in reversed(data["recent"]) if r.get("asset") == asset), None)
            out.append({
                "asset": asset, "kind": spec.get("kind"), "frame": spec.get("frame"), "role": spec.get("role"),
                "transparent": spec.get("transparent"),
                "prompt": prompts.get(asset) if isinstance(prompts, dict) else None,
                "chosen": (state.get("chosen") or {}).get(asset), "versions": versions,
                "generation": {"pending": [x for x in queued.values() if x.get("asset") == asset], "last": last},
            })
        return out

    @route("PUT", r"/api/templates/(?P<t>[^/]+)/style")
    def put_style(self, body, t):
        d = self._tpl(t)
        m = self._need_map(self._state(d).get("skeleton"))
        problems = schema.validate_style(body, m)
        if problems:
            raise ApiError(400, "; ".join(problems), problems=problems)
        with STATE_LOCK:
            write_json_atomic(d / "style.json", body)
            state = self._touch(d, "style")
        return {"ok": True, "state": state}

    @route("PUT", r"/api/templates/(?P<t>[^/]+)/texts")
    def put_texts(self, body, t):
        d = self._tpl(t)
        m = self._need_map(self._state(d).get("skeleton"))
        problems = texts_mod.validate_texts(body, m)
        if problems:
            raise ApiError(400, "; ".join(problems), problems=problems)
        json.dumps(body, ensure_ascii=False).encode("utf-8")  # lone surrogates -> ValueError -> 400, before any write
        with STATE_LOCK:
            write_json_atomic(d / "texts.json", body)  # strings stored exactly as received
            state = self._touch(d, "texts")
        return {"ok": True, "length_warnings": texts_mod.length_warnings(body, m), "state": state}

    # ------------------------------------------------------------------ Claude jobs
    def _paths(self, t, skeleton) -> dict:
        return {"map_file": self._rel("skeletons", skeleton, "map.json"), "style_file": self._rel("templates", t, "style.json"),
                "texts_file": self._rel("templates", t, "texts.json"),
                "manifest_file": self._rel("templates", t, "assets", "manifest.json")}

    def _request(self, t, d, jtype, prepare) -> dict:
        """Create a Claude job and mark its step waiting_claude. Everything runs under STATE_LOCK on a fresh
        state: startable check, `prepare(state) -> (inputs, target)` (its own refusals), the job, and the
        status change. Steps AFTER the requested one that are approved/review/waiting_claude become stale
        (re-running a step outdates what was built on its old result)."""
        step = STEP_OF[jtype]
        with STATE_LOCK:
            state = self._state(d)
            self._require_startable(state, step)
            inputs, target = prepare(state)
            job = create_job(self.cfg, jtype, state["skeleton"], t, inputs, target)
            self._mutate(d, lambda s: steps.set_status(steps.invalidate_after(s, step), step, "waiting_claude"))
        return {"job": job}

    def _require_startable(self, state, step) -> None:
        if not steps.can_start(state, step):
            raise ApiError(409, f"крок {step} ще не можна починати: попередні кроки не затверджено (або застаріли)")

    @route("POST", r"/api/templates/(?P<t>[^/]+)/texts/request")
    def request_texts(self, body, t):
        d = self._tpl(t)
        self._refresh(t)

        def prepare(state):
            self._need_valid(d, self._need_map(state["skeleton"]), "style")
            if any(j.get("template") == t and j.get("type") == "write_texts" and j.get("state") in _ACTIVE
                   for j in list_jobs(self.cfg)):
                raise ApiError(409, "завдання write_texts уже в черзі")
            brief, _ = _opt(d / "brief.json")
            return dict(self._paths(t, state["skeleton"]), brief=(brief or {}).get("brief")), None
        return self._request(t, d, "write_texts", prepare)

    def _canva_request(self, t, jtype):
        d = self._tpl(t)
        self._refresh(t)

        def prepare(state):
            copy_id = state.get("canva_copy_id")
            if jtype == "verify" and copy_id is None:
                raise ApiError(409, "копії в Canva ще немає: спершу запишіть шаблон (apply)")
            if jtype == "apply_canva" and self._effective(self._raw_infos(t, list_jobs(self.cfg)), state).get(
                    "apply", {}).get("copy_missing"):
                raise ApiError(409, NO_COPY)  # re-applying with target null would create a second copy
            if canva_busy(self.cfg):
                raise ApiError(409, "Canva уже зайнята іншим завданням: дочекайтесь його результату")
            inputs = dict(self._paths(t, state["skeleton"]), chosen=state.get("chosen") or {})
            if jtype == "apply_canva":
                m = self._need_map(state["skeleton"])
                self._need_valid(d, m, "style")
                inputs["texts"] = self._need_valid(d, m, "texts")  # the exact strings travel inside the job
            return inputs, copy_id
        return self._request(t, d, jtype, prepare)

    @route("POST", r"/api/templates/(?P<t>[^/]+)/apply")
    def apply(self, body, t):
        return self._canva_request(t, "apply_canva")

    @route("POST", r"/api/templates/(?P<t>[^/]+)/verify")
    def verify(self, body, t):
        return self._canva_request(t, "verify")

    # ------------------------------------------------------------------ approve / reopen
    @staticmethod
    def _step(body) -> str:
        step = body.get("step")
        if not isinstance(step, str) or step not in STEPS:
            raise ApiError(400, f"поле 'step' має бути одним із {list(STEPS)}")
        return step

    def _check_approvable(self, state, step) -> None:
        self._require_startable(state, step)
        status = state["steps"][step]["status"]
        # a stale apply/verify is outdated work to redo, not something to approve as it is
        if status != "review" and not (status == "stale" and step in ("style", "images", "texts")):
            raise ApiError(409, f"крок {step} у стані {status}: затвердити можна лише готовий до перегляду")

    @route("POST", r"/api/templates/(?P<t>[^/]+)/approve")
    def approve(self, body, t):
        d = self._tpl(t)
        step = self._step(body)
        data = self._refresh(t)
        state = self._state(d)
        self._check_approvable(state, step)
        chosen_before = dict(state.get("chosen") or {})
        if step in ("style", "texts"):
            self._need_valid(d, self._need_map(state["skeleton"]), step)
        if step == "images":
            if data["pending"]:
                raise ApiError(409, "генерація ще триває")
            m = self._need_map(state["skeleton"])
            res = assets.check_all(d, m)
            if not assets.all_ok(res):
                problems = list(res["problems"]) + [f"{f}: {p}" for f, v in res.items() if f != "problems" and isinstance(v, list) for p in v]
                raise ApiError(409, "перевірка картинок не пройшла: " + "; ".join(problems), problems=problems)
            assets.build_manifest(d, m)
        with STATE_LOCK:
            state = self._state(d)
            self._check_approvable(state, step)
            if step == "images" and (state.get("chosen") or {}) != chosen_before:
                raise ApiError(409, "вибір картинок змінився під час перевірки: повторіть")
            new = steps.approve(state, step)
            write_json_atomic(d / "state.json", new)
        return {"state": new}

    @route("POST", r"/api/templates/(?P<t>[^/]+)/reopen")
    def reopen(self, body, t):
        d = self._tpl(t)
        step = self._step(body)
        with STATE_LOCK:
            state = self._state(d)
            if state["steps"][step]["status"] != "approved":
                raise ApiError(409, f"крок {step} не затверджено, відкривати нічого")
            new = steps.reopen(state, step)
            write_json_atomic(d / "state.json", new)
        return {"state": new}

    # ------------------------------------------------------------------ images
    @route("POST", r"/api/templates/(?P<t>[^/]+)/images/generate")
    def generate(self, body, t):
        d = self._tpl(t)
        self._refresh(t)
        state = self._state(d)
        self._require_startable(state, "images")
        m = self._need_map(state["skeleton"])
        style = self._need_valid(d, m, "style")
        names, override = body.get("assets"), body.get("prompt_override")
        if names is not None and not (isinstance(names, list) and names and all(isinstance(a, str) for a in names)):
            raise ApiError(400, "'assets' має бути непорожнім списком імен")
        prompts = None
        if isinstance(override, str):
            if not names:
                raise ApiError(400, "'prompt_override'-рядок потребує списку 'assets'")
            prompts = {a: override for a in names}
        elif isinstance(override, dict):
            prompts = override
        elif override is not None:
            raise ApiError(400, "'prompt_override' має бути рядком або {asset: підказка}")
        for a, p in (prompts or {}).items():
            if a not in m["assets"] or not isinstance(p, str) or not p.strip():
                raise ApiError(400, f"підказка для {a!r}: невідомий ассет або порожній текст")
        assets.plan_generations(m, style)  # ValueError (a prompt is missing) -> 400, before any hardware check
        unknown = [a for a in names or [] if a not in m["assets"]]
        if unknown:
            raise ApiError(400, f"невідомі ассети: {unknown}")
        # answer within seconds when the disk or ComfyUI is missing (comfy.ping times out after 3 s)
        if not self.cfg.models_dir.is_dir():
            raise ApiError(409, "диск моделей не змонтовано")
        if not comfy.ping(self.cfg):
            raise ApiError(409, "ComfyUI недоступний — запустіть run.sh")
        with tickets.GEN_LOCK:
            new = assets.submit_generations(self.queue, d, m, style, only=names, prompts=prompts)
            tickets.add(self.cfg, t, new)
        return {"tickets": new}

    @route("POST", r"/api/templates/(?P<t>[^/]+)/images/choose")
    def choose(self, body, t):
        d = self._tpl(t)
        asset, file = body.get("asset"), body.get("file")
        if not isinstance(asset, str) or not isinstance(file, str):
            raise ApiError(400, "потрібні рядкові поля 'asset' і 'file'")
        m = self._need_map(self._state(d).get("skeleton"))
        if asset not in m["assets"]:
            raise ApiError(400, f"ассета {asset!r} немає в карті")
        with STATE_LOCK:
            before = (self._state(d).get("chosen") or {}).get(asset)
            assets.choose(d, asset, file)  # AssetError -> 400
            if before != file:
                self._mutate(d, lambda s: steps.reopen(s, "images") if s["steps"]["images"]["status"] == "approved" else None)
            self._reconcile_images(t, m, tickets.load(self.cfg, t))
            state = self._state(d)
        return {"chosen": state["chosen"], "state": state}

    # ------------------------------------------------------------------ jobs / generations
    @route("GET", r"/api/jobs")
    def jobs(self, body):
        all_jobs = list_jobs(self.cfg)
        bad = {}
        for name in list_templates(self.cfg):
            try:
                self._reconcile_jobs(name, all_jobs)
            except ApiError as e:  # that template's state is unusable; the list must still answer
                bad[name] = e.message
        return {"jobs": [dict(j, result=_result_info(self.cfg, j) if j.get("type") else None) for j in all_jobs],
                "template_errors": bad}

    @route("GET", r"/api/gen")
    def gen(self, body):
        out = {}
        for name in list_templates(self.cfg):
            try:
                data = self._refresh(name)
            except ApiError as e:
                out[name] = {"error": e.message, "pending": [], "recent": []}
                continue
            if data["pending"] or data["recent"]:
                out[name] = {"pending": tickets.with_queue_state(self.queue, data["pending"]), "recent": data["recent"]}
        return {"queue": self.queue.status(), "templates": out}
