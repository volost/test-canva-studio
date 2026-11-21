# Template Studio — build plan

Note: The command was renamed to /test-canva-studio on 2026-11-20 (owner's decision).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a local web studio that step by step (style → pictures → texts → write to Canva → check) makes a
new wedding-website style on a copy of the skeleton in Canva; the write to Canva is performed by a Claude Code session through
the job inbox.

**Architecture:** one Python process (standard library, `http.server`) serves the HTML/JS interface and the JSON API
on `127.0.0.1`; state is files in `studio/skeletons/`, `studio/templates/`, `studio/jobs/`. The studio
generates pictures itself through the ComfyUI HTTP API. The steps that need Claude (skeleton map, style directions, texts,
write to Canva, check) are put by the studio as jobs into `jobs/pending/`; the `/studio` skill in a Claude Code session
executes them with the scripts from `studio/canva/`.

**Tech Stack:** Python 3.13 from the ComfyUI environment (PIL 12.3, numpy 2.5, scipy — present; pytest — absent, so
`unittest`); HTML + vanilla JS with no build; ComfyUI + Z-Image Turbo; the Canva connector (MCP) in Claude Code.

**Spec:** `studio/DESIGN.md` (approved 2026-11-20). Implementers read both files.

**Test command (all tasks):**
`cd /Users/volost/GitRepos/canva/studio && /Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python -I -m unittest discover -s tests -t . -v`
(hereafter `RUN_TESTS`; for a single file add `-p test_<name>.py`).

**Git:** the project is not a repository. The "Commit" steps are performed only if the owner allowed `git init` in
`studio/` (local, no push, no `Co-Authored-By`); otherwise the step is skipped.

## Global Constraints

- Never edit `DAHarqlqips` (the purchased Ivory Lace) or the skeleton design; Canva jobs are allowed only
  on the copy created for this template (DESIGN §5.7.3).
- One writer per design: no more than one Canva job (`apply_canva`, `verify`) in `running/` or
  `pending/` at a time (DESIGN §5.2, §5.7.5).
- The studio deletes nothing: «ще раз» ("again") adds a new generation, the old files stay; rejected ones are a mark in the
  state, not a deletion. No publishing of the site, submitting a form, or changing account settings.
- The server listens only on `127.0.0.1`; only the standard library + PIL/numpy/scipy of the ComfyUI environment; nothing is
  installed.
- Python: `/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python`, launched with `-I`.
- Models: `/Volumes/WoofData/ComfyUI/models`; ComfyUI: `/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/main.py`,
  `--listen 127.0.0.1 --port 8188 --disable-auto-launch --disable-all-custom-nodes --extra-model-paths-config
  /Users/volost/GitRepos/canva/pilot/comfy/extra_model_paths.yaml`.
- The Z-Image Turbo graph: KSampler 8 steps, cfg 1, `res_multistep`, `simple`; ModelSamplingAuraFlow shift 3;
  CLIPLoader type `lumina2`; negative — ConditioningZeroOut (as in `pilot/tools/comfy_generate.py`).
- Every final picture has the aspect ratio of its frame within 0.5 %; transparent decor is padded,
  photos are cropped around the centre.
- After every `update_fill` — `crop_media` to the exact cover frame.
- Every check has a control: a deliberately bad input must be rejected by the same function; otherwise the
  check is considered broken and the run fails.
- The templates' language is English. Fonts are not changed by the connector: the studio issues a checklist for the manual swap.
- Personal data — live text only and only in slots with `personal: true`; the rules of `SPEC.md` §7.
- The studio interface is in Ukrainian.

## Review Focus

1. ComfyUI is not running or the `WoofData` disk is not mounted, and the owner presses «Генерувати» ("Generate") → a clear
   message in the interface within ≤ 5 s, no hang (test in Task 5).
2. The owner comes back and changes an already approved step → all following steps become `stale`, and an `apply_canva`
   job with stale data is not created (test in Task 2 and Task 3).
3. Double press of «Записати в Canva» ("Write to Canva") → the second Canva job is rejected (test in Task 3).
4. Texts with `’ “ ” é & < >` and a line break → stored and passed into the job unchanged, the interface
   shows them without HTML injection (test in Task 9 and Task 10).
5. Corrupted or half-written JSON in the inbox or in a job result → the studio shows the job as
   "corrupt" and does not crash (test in Task 3).

---

## File structure

```
studio/
  DESIGN.md  PLAN.md
  config.json                  paths, ports, forbidden ids
  run.sh                       launcher for the owner (ComfyUI + studio)
  app/
    config.py                  Config, load_config
    store.py                   templates/skeletons on disk, atomic JSON write
    steps.py                   step states, approval, stale
    guard.py                   protection of the originals
    jobs.py                    job inbox, Canva lock, stuck jobs
    schema.py                  validation of map.json / style.json / texts.json
    texts.py                   length warnings
    comfy.py                   ComfyUI client
    genqueue.py                sequential background generation queue
    imaging/
      core.py                  aspect_error, cover_crop, pad_to_frame, alpha_coverage, checker, on_background
      cutout.py                watercolour_to_alpha, solid_cutout
      envelope.py              compose_envelope, check_envelope (geometry from map.json)
      sheet.py                 contact_sheet
    assets.py                  generation plan per asset, post-processing, checking, manifest
    server.py                  HTTP: static files + JSON API
    static/ index.html app.js style.css
  canva/                       scripts for the Claude session (generalised from Sage & Linen)
    facts.py outline.py probe_diff.py layout.py   (copies, no hard-coded ids)
    ops.py                     operations from map + style + texts
    protected.py final_check.py fields.py geometry.py
  tests/  test_*.py, fixtures/
  skeletons/<skeleton>/  templates/<template>/  jobs/{pending,running,done,failed}/
/Users/volost/GitRepos/canva/.claude/skills/studio/SKILL.md + jobs/*.md
```

## Data formats (shared by all tasks)

- `skeletons/<s>/map.json`:
  `{"skeleton": str, "design_id": str, "pages": [{"index": int, "id": str, "title": str}],
  "assets": {<asset>: {"kind": "photo"|"texture"|"watercolour"|"solid"|"composed", "frame": [w, h], "role": str, "transparent": bool}},
  "slots": [{"locator": str, "type": "image"|"text"|"colour"|"table_cell", "role": str, "asset": str|null,
  "personal": bool, "column_px": int|null, "max_len": int|null, "original": str|null}],
  "envelope": {"section_px": [w, h], "tip": [x, y], "left_top": [x, y], "right_top": [x, y],
  "seal_centre": [x, y], "seal_size": [w, h], "seal_rot_canva": float} | null,
  "protected": [locator, ...]}`
- `templates/<t>/style.json`: `{"name", "brief", "palette": {<role>: "#rrggbb"}, "colour_roles": {<slot role>: <palette role>},
  "image_prompts": {<asset>: str}, "fonts": {"heading": str, "body": str, "script": str}, "font_map": {<text role>: "heading"|"body"|"script"}}`
- `templates/<t>/texts.json`: `{<locator>: str}`.
- `templates/<t>/state.json`: `{"skeleton": str, "canva_copy_id": str|null, "chosen": {<asset>: <file>}, "steps": {<step>: {"status": str, "updated_utc": str}}}`;
  steps `STEPS = ("style", "images", "texts", "apply", "verify")`; statuses `draft`, `waiting_claude`, `review`, `approved`, `stale`.
- Job `jobs/<state>/<id>.json`: `{"id", "type", "template"|null, "skeleton", "target_design_id"|null,
  "created_utc", "inputs": {...}, "limits": [str]}`; types `map_skeleton`, `style_directions`, `write_texts`,
  `apply_canva`, `verify`; Canva types — `apply_canva`, `verify` (and `map_skeleton`, which only reads).
- Result `templates/<t>/jobs/<id>.result.json` (for `map_skeleton` — `skeletons/<s>/jobs/`):
  `{"status": "done"|"failed", "summary": str, "outputs": {...}, "checks": [{"name": str, "passed": bool, "detail": str}]}`.

---

### Task 1: Skeleton, config and launcher

**Who:** Sonnet, medium — a clearly described skeleton, little judgement.

**Files:** Create `studio/config.json`, `studio/app/__init__.py`, `studio/app/config.py`, `studio/app/server.py`,
`studio/app/static/index.html`, `studio/run.sh`, `studio/tests/__init__.py`, `studio/tests/test_config.py`, `studio/tests/test_server.py`.

**Interfaces:**
- Produces: `Config` (frozen dataclass: `root: Path`, `python: Path`, `comfy_main: Path`, `models_dir: Path`,
  `extra_model_paths: Path`, `comfy_url: str`, `studio_port: int`, `forbidden_design_ids: frozenset[str]`);
  `load_config(path: Path) -> Config`; `make_server(cfg: Config, port: int) -> ThreadingHTTPServer`;
  `GET /api/health -> {"ok": true, "comfy_url": str, "models_mounted": bool}`.

- [ ] **Step 1: Write the failing tests** — `test_load_config_reads_values` (from `tests/fixtures/config.json`:
  `forbidden_design_ids == {"DAHarqlqips"}`, `studio_port == 8765`); `test_load_config_rejects_missing_key`
  (`ValueError` naming the key); `test_health_endpoint` (a server on port 0 in a thread, `GET /api/health` →
  200, `ok is True`, `models_mounted` is a bool); `test_server_binds_localhost_only` (`server_address[0] == "127.0.0.1"`).
- [ ] **Step 2:** `RUN_TESTS -p "test_c*.py"` and `-p "test_server.py"` → FAIL (no modules).
- [ ] **Step 3:** Implement `load_config`, `make_server` (a handler on `BaseHTTPRequestHandler`, static files from
  `app/static`, JSON responses with `Content-Type: application/json; charset=utf-8`). `config.json` — the values from
  Global Constraints, `studio_port` 8765, `forbidden_design_ids` `["DAHarqlqips"]`.
- [ ] **Step 4:** `run.sh`: checks that `/Volumes/WoofData/ComfyUI/models` exists (otherwise a message and
  exit 1); if `curl -s 127.0.0.1:8188` does not answer — starts ComfyUI in the background with the log file
  `studio/logs/comfy.log`; starts the studio; prints `Студія: http://127.0.0.1:8765` ("Studio: ...") and `ComfyUI: http://127.0.0.1:8188`.
- [ ] **Step 5:** `RUN_TESTS` → PASS. No manual check needed (the owner starts the server outside the sandbox).
- [ ] **Step 6: Commit** `feat(studio): skeleton, config, launcher`.

### Task 2: Store and step states

**Who:** Sonnet, medium — state logic, clear rules.

**Files:** Create `app/store.py`, `app/steps.py`, `tests/test_store.py`, `tests/test_steps.py`.

**Interfaces:**
- Consumes: `Config` (Task 1).
- Produces: `write_json_atomic(path: Path, data) -> None` (a temporary file + `os.replace`);
  `read_json(path: Path) -> dict` (raises `CorruptJSON(path)` on bad JSON);
  `create_template(cfg, name: str, skeleton: str) -> Path`; `list_templates(cfg) -> list[str]`;
  `template_dir(cfg, name) -> Path`; `skeleton_dir(cfg, name) -> Path`;
  `STEPS`, `set_status(state: dict, step: str, status: str) -> dict`; `approve(state, step) -> dict`;
  `reopen(state, step) -> dict` (the step → `review`, all following `approved`/`review` → `stale`);
  `can_start(state, step) -> bool` (all previous are `approved`).

- [ ] **Step 1: Write the failing tests** — `test_atomic_write_roundtrip`; `test_read_corrupt_raises`
  (the file `{"a":` → `CorruptJSON`); `test_create_template_rejects_bad_name` (`"../x"`, `""`, `"a/b"` → `ValueError`;
  allowed `[a-z0-9-]{1,40}`); `test_create_template_existing_raises`; `test_reopen_marks_later_stale`
  (all approved, `reopen(state,"images")` → images `review`, texts/apply/verify `stale`, style `approved`);
  `test_can_start_requires_previous_approved` (`can_start(s,"apply")` False while texts is `stale`).
- [ ] **Step 2:** `RUN_TESTS -p "test_st*.py"` → FAIL.
- [ ] **Step 3:** Implement; `updated_utc` — `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.
- [ ] **Step 4:** `RUN_TESTS` → PASS.
- [ ] **Step 5: Commit** `feat(studio): template store and step states`.

### Task 3: Job inbox and protection of the originals

**Who:** Sonnet, high — the anti-goals live here (a write to the original, two writers); a mistake is costly.

**Files:** Create `app/guard.py`, `app/jobs.py`, `tests/test_guard.py`, `tests/test_jobs.py`.

**Interfaces:**
- Consumes: `Config`, `store.*`, `steps.can_start` (Tasks 1–2).
- Produces: `GuardError(Exception)`; `check_job(job: dict, cfg: Config, skeleton_design_id: str, state: dict|None) -> None`;
  `CANVA_WRITE_TYPES = {"apply_canva", "verify"}`; `create_job(cfg, type: str, skeleton: str, template: str|None,
  inputs: dict, target_design_id: str|None) -> dict`; `list_jobs(cfg) -> list[dict]` (each with `state` ∈
  `pending|running|done|failed|corrupt`, `age_s`); `canva_busy(cfg) -> bool`; `read_result(cfg, job) -> dict|None`.

- [ ] **Step 1: Write the failing tests** — `test_guard_blocks_purchased_original` (`target_design_id="DAHarqlqips"` → `GuardError`);
  `test_guard_blocks_skeleton_id`; `test_guard_verify_requires_template_copy` (verify with target ≠
  `state["canva_copy_id"]` → `GuardError`); `test_guard_apply_first_run_target_none_ok` (apply with `target None`
  and `canva_copy_id None` — allowed: Claude will create the copy); `test_guard_apply_stale_texts_refused`
  (`can_start(state,"apply")` False → `GuardError`); `test_second_canva_job_refused` (two `create_job("apply_canva")`
  in a row → the second `GuardError`, one file in `pending/`); `test_corrupt_job_listed_not_raised` (garbage in
  `pending/x.json` → `list_jobs` returns `state == "corrupt"`); `test_job_limits_present` (every Canva job
  has strings in `limits` from DESIGN §5.2).
- [ ] **Step 2:** `RUN_TESTS -p "test_guard.py"`, `-p "test_jobs.py"` → FAIL.
- [ ] **Step 3:** Implement; job id `YYYYmmddTHHMMSSZ-<type>`; `canva_busy` — there is a Canva job in
  `pending/` or `running/`; `create_job` calls `check_job` before writing; the write is `write_json_atomic`.
- [ ] **Step 4:** `RUN_TESTS` → PASS.
- [ ] **Step 5: Commit** `feat(studio): job inbox with original-design guard`.

### Task 4: Image-processing library

**Who:** Sonnet, medium — porting verified code with tests.

**Files:** Create `app/imaging/__init__.py`, `core.py`, `cutout.py`, `sheet.py`, `tests/test_imaging.py`.
Sources: `study/sage-linen/tools/lib.py` (functions with the same names), `cutout_watercolour.py`,
`cutout_solid.py`, `contact_sheet.py`, `pilot/tools/white_to_alpha.py`.

**Interfaces:**
- Produces: `aspect_error(size: tuple[int,int], frame: tuple[int,int]) -> float`;
  `cover_crop(img, frame, cx=0.5, cy=0.5) -> Image`; `pad_to_frame(img, frame, scale, margin=0.0, anchor=(0.5,0.5)) -> Image`;
  `alpha_coverage(img) -> float`; `watercolour_to_alpha(img, speck=80) -> Image`;
  `solid_cutout(img, tol=14, holes=None, erode=2, feather=1.0) -> Image`;
  `contact_sheet(items: list[tuple[str, Path]], out: Path, long_edge=1568) -> Path`.
  No global paths (`ROOT`, `ASSETS`) — everything through parameters.

- [ ] **Step 1: Write the failing tests** — `test_cover_crop_exact_aspect` (1000×700 into a 433×600 frame →
  `aspect_error < 0.005`); `test_pad_keeps_alpha` (the result is RGBA, corners transparent); `test_watercolour_white_becomes_transparent`
  (white background → alpha 0, a colour blot → alpha > 0); `test_solid_cutout_keeps_highlight_opaque` (a white circle
  inside a dark ring is not transparent without `holes`); `test_contact_sheet_long_edge` (≤ 1568).
- [ ] **Step 2:** FAIL. **Step 3:** port the functions. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): imaging library`.

### Task 5: ComfyUI client and generation queue

**Who:** Sonnet, medium.

**Files:** Create `app/comfy.py`, `app/genqueue.py`, `tests/test_comfy.py`, `tests/test_genqueue.py`.
Graph source: `pilot/tools/comfy_generate.py`.

**Interfaces:**
- Consumes: `Config`.
- Produces: `ComfyError(Exception)`; `build_graph(prompt: str, width: int, height: int, seed: int, prefix: str) -> dict`;
  `ping(cfg, timeout=3.0) -> bool`; `generate(cfg, prompt, width, height, seed, prefix, out_dir: Path, timeout=1500) -> list[Path]`;
  `GenQueue(cfg, log_path: Path)` with `submit(job: dict) -> str`, `status() -> list[dict]` (`queued|running|done|failed`,
  `error`, `seconds`), one worker thread; every run is a line in `generations.jsonl`
  (`utc, prefix, seed, width, height, exit, saved, seconds, prompt`).

- [ ] **Step 1: Write the failing tests** — `test_build_graph_settings` (the graph has steps 8, cfg 1, sampler
  `res_multistep`, scheduler `simple`, shift 3, CLIP type `lumina2`, sizes and seed passed through);
  `test_ping_closed_port_fast` (a URL on a free port → `False` in under 5 s);
  `test_queue_reports_comfy_down` (a queue with an unavailable ComfyUI → the job `failed`, `error` contains
  «ComfyUI недоступний» ("ComfyUI unavailable"), a line in jsonl with `exit != 0`); `test_queue_sequential` (a substituted `generate`
  records that two jobs do not overlap in time).
- [ ] **Step 2:** FAIL. **Step 3:** implement (`urllib.request`; `/prompt`, `/history/<id>`, `/view`).
- [ ] **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): ComfyUI client and generation queue`.

### Task 6: Envelope from the map's geometry

**Who:** Sonnet, high — geometry the model will not guess; a ready-made check exists.

**Files:** Create `app/imaging/envelope.py`, `tests/test_envelope.py`. Sources: `study/sage-linen/tools/compose_envelope.py`,
`check_assets.py:check_envelope`.

**Interfaces:**
- Consumes: `imaging.core`; the `envelope` block from `map.json`.
- Produces: `compose_envelope(texture: Image, geom: dict, scale=2, seal: Image|None=None) -> tuple[Image, Image, Image]`
  (cover, flap, body); `check_envelope(cover, flap, body, geom, scale=2) -> list[str]` (empty = good).
  Constants `TIP`, `SEAL_CENTRE` etc. — from `geom`, not from code.

- [ ] **Step 1: Write the failing tests** — `test_envelope_layers_reproduce_cover` (Sage & Linen geometry:
  section 1366×964, tip (683,610), left_top (0,60), right_top (1366,60), seal_centre (683,623),
  seal_size (160,198), seal_rot_canva −3.4; a uniform texture → `check_envelope == []`);
  `test_envelope_no_transparent_pixel` (flap over body — alpha 255 everywhere);
  `test_check_rejects_shifted_flap` (shifting the flap by 6 px → a non-empty list — the control).
- [ ] **Step 2:** FAIL. **Step 3:** port, parameterise with the geometry. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): envelope from skeleton geometry`.

### Task 7: Data schemas and texts

**Who:** Sonnet, medium.

**Files:** Create `app/schema.py`, `app/texts.py`, `tests/test_schema.py`, `tests/test_texts.py`,
`tests/fixtures/map_min.json`, `tests/fixtures/style_min.json`.

**Interfaces:**
- Produces: `validate_map(d: dict) -> list[str]`; `validate_style(d: dict, m: dict) -> list[str]`
  (every asset from `m["assets"]` has a prompt; every colour role is in the palette; colours are `#rrggbb`);
  `validate_texts(d: dict, m: dict) -> list[str]` (only the locators of text slots);
  `length_warnings(texts: dict, m: dict) -> dict[str, str]` (a single line longer than `max_len`;
  a paragraph longer than 115 % of `original`); `font_checklist(m: dict, style: dict) -> list[dict]`
  (`locator, role, font`).

- [ ] **Step 1: Write the failing tests** — `test_map_min_valid`; `test_map_rejects_slot_without_locator`;
  `test_map_rejects_image_slot_with_unknown_asset`; `test_style_requires_prompt_per_asset`;
  `test_texts_unknown_locator_rejected`; `test_length_warning_one_line` (`max_len` 20, 25 characters → a warning);
  `test_unicode_text_preserved` (`"We’re “so” happy — Café & <b>\nline"` passes `validate_texts` and
  is written/read through `store` byte for byte); `test_font_checklist_lists_every_text_role`.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): data schemas, length warnings, font checklist`.

### Task 8: Asset pipeline

**Who:** Sonnet, high — joins the map, generation, processing and checks; the quality of the pictures depends on it.

**Files:** Create `app/assets.py`, `tests/test_assets.py`.

**Interfaces:**
- Consumes: `comfy`, `genqueue`, `imaging.*`, `schema` (Tasks 4–7).
- Produces: `gen_size(frame: tuple[int,int], megapixels=1.5) -> tuple[int,int]` (multiples of 64, the frame's aspect
  ±3 % — the exact one comes from post-processing); `plan_generations(m: dict, style: dict) -> list[dict]` (per asset:
  `asset, prompt, width, height, kind`; `composed` → only the texture is generated, the rest is `compose_envelope`);
  `postprocess(asset: str, src: Path, m: dict, out_dir: Path) -> Path` (photo/texture → `cover_crop`;
  watercolour → `watercolour_to_alpha` + `pad_to_frame`; solid → `solid_cutout` + `pad_to_frame`);
  `check_asset(path: Path, spec: dict) -> list[str]`; `check_all(template_dir: Path, m: dict) -> dict`
  (per file a list of problems, plus `controls_ok: bool` from deliberately bad files);
  `build_manifest(template_dir: Path, m: dict) -> Path`. Files are versioned: `assets/<asset>__v<n>.<ext>`,
  the chosen one is in `state.json` (`"chosen": {<asset>: <file>}`); previous versions are not deleted.

- [ ] **Step 1: Write the failing tests** — `test_gen_size_multiple_of_64_and_close_aspect`
  (a 433×600 frame); `test_plan_has_every_asset`; `test_postprocess_photo_exact_aspect`;
  `test_postprocess_watercolour_transparent`; `test_check_all_controls_reject_bad`
  (a wrong aspect ratio, an opaque "transparent" file, a file that does not open → each rejected;
  `controls_ok True`); `test_regenerate_keeps_previous_version` (v1 stays after v2).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): asset pipeline with checks and versions`.

### Task 9: The studio's JSON API

**Who:** Sonnet, medium.

**Files:** Modify `app/server.py`; Create `tests/test_api.py`.

**Interfaces:**
- Consumes: everything from Tasks 2–8.
- Produces (all responses JSON; errors — `{"error": str}` with 400/409/500, no traceback):
  `GET /api/skeletons`, `POST /api/skeletons {name, design_id}` → creates a `map_skeleton` job;
  `GET /api/skeletons/<s>`, `PUT /api/skeletons/<s>/roles {locator: role}`;
  `GET /api/templates`, `POST /api/templates {name, skeleton, brief}` → a `style_directions` job;
  `GET /api/templates/<t>` (state, style, texts, warnings, assets, jobs);
  `PUT /api/templates/<t>/style`, `POST /api/templates/<t>/images/generate {assets?: [..], prompt_override?}`,
  `POST /api/templates/<t>/images/choose {asset, file}`, `POST /api/templates/<t>/texts/request` → `write_texts`,
  `PUT /api/templates/<t>/texts`, `POST /api/templates/<t>/approve {step}`, `POST /api/templates/<t>/reopen {step}`,
  `POST /api/templates/<t>/apply` → `apply_canva`, `POST /api/templates/<t>/verify` → `verify`;
  `GET /api/jobs`, `GET /api/gen`; `GET /files/<path>` — only inside `skeletons/` and `templates/`.

- [ ] **Step 1: Write the failing tests** — `test_create_template_flow` (POST template → 200, a `style_directions`
  job in `pending/`); `test_apply_twice_conflict` (the second `apply` → 409); `test_apply_refused_when_texts_stale` → 409;
  `test_files_path_traversal_blocked` (`/files/../config.json` and `/files/%2e%2e/config.json` → 404);
  `test_bad_json_body_400`; `test_unicode_texts_roundtrip` (the string from Task 7 through PUT/GET unchanged).
- [ ] **Step 2:** FAIL. **Step 3:** implement the routes. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): JSON API`.

### Task 10: Interface

**Who:** Sonnet, high — UI; verified in the browser by measurement, not by eye.

**Files:** Create/Modify `app/static/index.html`, `app/static/app.js`, `app/static/style.css`.

**Interfaces:** Consumes the API of Task 9. Screens (DESIGN §5.1): a list of templates and skeletons; the skeleton map with
thumbnails and role editing; the brief and the choice of a style direction; the picture gallery (accept / again / own
prompt; overview sheet; queue and ComfyUI status); texts with warnings; «Записати в Canva» ("Write to Canva") with the explanation
"run `/studio` in the Claude Code session"; the check result (pages, a table of checks, a link to the
design, a checklist of fonts and manual steps). A step strip on top with statuses. The job state is refreshed
by polling `GET /api/jobs` every 3 s. All user text is inserted through `textContent`, not `innerHTML`.

- [ ] **Step 1:** Start the studio with test data (`tests/fixtures/`) outside the sandbox; open in the
  embedded browser `http://127.0.0.1:8765`.
- [ ] **Step 2: Check by element list** — for each screen in the list above: the element is in the DOM
  (`read_page`), visible, the buttons are reachable (`getBoundingClientRect` within the window at 1440×900 and 768×1024),
  no horizontal scrolling.
- [ ] **Step 3: Injection check** — the text `<img src=x onerror=alert(1)>` in a text field is shown as text
  (`document.querySelectorAll('img[src="x"]').length === 0`).
- [ ] **Step 4:** A ComfyUI error (Review Focus 1) is shown as a message on the pictures screen.
- [ ] **Step 5: Commit** `feat(studio): web interface`.

### Task 11: Scripts for the Canva session

**Who:** Sonnet, high — generalising the scripts that protected the design on 12.11; a mistake = a damaged design.

**Files:** Create `studio/canva/{facts,outline,probe_diff,layout}.py` (copies from `study/sage-linen/canva/` and
`handoff/tools/`, with no hard-coded ids), `studio/canva/ops.py`, `protected.py`, `final_check.py`, `fields.py`,
`geometry.py`, `tests/test_canva_ops.py`, `tests/test_canva_checks.py`, `tests/fixtures/facts_sage.json`
(a copy of `study/sage-linen/canva/facts_final.json`), `tests/fixtures/facts_orig.json` (a copy of `facts0.json`).

**Interfaces:**
- Produces: `cover_box(frame_w, frame_h, img_w, img_h) -> dict(left, top, width, height)` (exact cover, centred);
  `build_ops(m: dict, style: dict, texts: dict, facts: dict) -> dict[str, list[dict]]` (batches per page:
  `replace_text`, `format_text` colour, `recolor_element`/`update_fill` for colours; never touches
  `m["protected"]`); `verify_batch(before: dict, after: dict, ops: list) -> list[str]` (untargeted changes
  must be absent); `protected_changes(orig: dict, now: dict, m: dict) -> list[str]`;
  `final_check(orig: dict, now: dict, m: dict, texts: dict) -> list[dict]` (per check `name, passed, detail`,
  plus a control: on `orig` the checks must fail); `build_fields(m: dict, texts: dict) -> dict` and
  `page_notes(m: dict) -> dict[str, str]`.
  The CLI of each script: `python -I <script>.py <args>` prints a summary, the full output goes to a file.

- [ ] **Step 1: Write the failing tests** — `test_cover_box_centred_exact` (a 433×600 frame, a 866×1300 picture →
  width 433, height 650, top −25); `test_build_ops_never_touches_protected`; `test_build_ops_text_uses_replace_text`;
  `test_verify_batch_flags_untargeted_change`; `test_protected_change_detected` (a synthetic change of a media id →
  found — the control); `test_final_check_fails_on_original` (on `facts_orig` the checks fail);
  `test_fields_cover_every_personal_slot`.
- [ ] **Step 2:** FAIL. **Step 3:** implement/port. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): Canva-side scripts`.

### Task 12: The `/studio` skill and the job instructions

**Who:** Opus, high after the limit refresh (until 22.11 — Sonnet, high) — much judgement: the connector's rules,
limits, what to do on failure; a mistake damages the design or burns the limit.

**Files:** Create `/Users/volost/GitRepos/canva/.claude/skills/studio/SKILL.md`, `.../jobs/map_skeleton.md`,
`style_directions.md`, `write_texts.md`, `apply_canva.md`, `verify.md`. Writing to `.claude/skills` is blocked by the sandbox —
the owner's permission is needed for this write.

**Interfaces:**
- Consumes: the data formats (above), the Task 11 scripts, `PLAYBOOK.md` §4–7, `SPEC.md` §7.
- Produces: SKILL.md: (1) first `jobs/running/` (DESIGN §5.7.5); (2) the oldest `pending/` → `running/`;
  (3) target check: id ≠ `DAHarqlqips`, ≠ the skeleton's id, for verify = `canva_copy_id`; (4) the type's instruction
  from `jobs/<type>.md`; (5) the result in `<id>.result.json` in the format; (6) `done/` or `failed/`.
  Each instruction: what to read, steps, the hard limits of DESIGN §5.2, the format of `outputs` and `checks`.
  `apply_canva`: `copy-design` of the skeleton → write `canva_copy_id` into `state.json` → colours and texts in batches with
  `verify_batch` after each → upload the pictures (`create-upload-url` + `curl`) → `update_fill` +
  `crop_media(cover_box)` → a stress test with the long values of `SPEC.md` §7.4 and restoration from the diff →
  page notes → `fields.json` → `protected_changes == []`. `verify`: PNG export, slicing, contrast under
  white text, a view in the fullscreen preview (phone and 1440×810), the button audit 9/9 (the JS from PLAYBOOK §5
  Phase 7), the checklist of fonts and manual steps.

- [ ] **Step 1:** Write SKILL.md and the five instructions.
- [ ] **Step 2: Dry run** — a `write_texts` job for a test template from `tests/fixtures/`: `/studio`
  takes it, writes `texts.json` and the result, moves it to `done/`; the studio shows the texts.
- [ ] **Step 3: Protection check** — put into `pending/` a hand-made `verify` job with
  `target_design_id: "DAHarqlqips"` → the skill refuses, the job goes to `failed/` with a reason, not a single Canva call.
- [ ] **Step 4: Commit** `feat(studio): /studio skill and job instructions`.

### Task 13: End-to-end run on a test copy

**Who:** the lead session (Opus after the limit refresh) together with the owner — Canva, the browser, the owner's decisions are needed.

**Files:** `studio/skeletons/probe/`, `studio/templates/<first-style>/`, the report `studio/templates/<t>/RUN_NOTES.md`.

- [ ] **Step 1:** The owner runs `studio/run.sh`; the studio and ComfyUI respond (the addresses go in the report).
- [ ] **Step 2:** The skeleton `probe` = `DAHason1g_M`; `/studio` executes `map_skeleton`; the owner corrects the roles.
- [ ] **Step 3:** Template: brief → `style_directions` → choice → pictures (all accepted) → `write_texts` → edits → approval.
- [ ] **Step 4:** «Записати» ("Write") → `/studio` executes `apply_canva` on a new copy; `protected_changes == []`.
- [ ] **Step 5:** «Перевірити» ("Check") → `/studio` executes `verify`; all checks passed with numbers; the button audit 9/9.
- [ ] **Step 6:** Record in the report: the time of each step, the limit spent (`get_usage` before and after), what failed.

### Task 14: Specification of the own skeleton for the owner

**Who:** the lead session, Sonnet medium until 22.11 — a document based on `study/ivory-lace/BLUEPRINT.md` and the requirements of DESIGN §5.6.
Independent of Tasks 1–13, can be done at any time.

**Files:** Create `studio/SKELETON_SPEC.md`.

- [ ] **Step 1:** Describe for the owner, in Ukrainian, step by step in the Canva editor: pages and sections, the
  column width for the phone, frames for pictures with sizes, text fields (a separate field for each personal
  value), the two-layer envelope, buttons with the link on the top element, the form, embedded blocks,
  no text in pictures.
- [ ] **Step 2:** Verify every menu name in the Canva editor (the owner's English interface) through the
  embedded browser; mark whatever is not verified.
- [ ] **Step 3:** Give it to the owner to read.

Not part of the plan (DESIGN §4): the background-launch button `claude -p` — separately, after the test.
