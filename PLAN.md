# Студія шаблонів — план будування

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** локальна веб-студія, яка покроково (стиль → картинки → тексти → запис у Canva → перевірка) робить
новий стиль весільного сайту на копії скелета в Canva; запис у Canva виконує сесія Claude Code через
скриньку завдань.

**Architecture:** один Python-процес (стандартна бібліотека, `http.server`) віддає HTML/JS-інтерфейс і JSON API
на `127.0.0.1`; стан — файли в `studio/skeletons/`, `studio/templates/`, `studio/jobs/`. Картинки студія
генерує сама через HTTP API ComfyUI. Кроки, що потребують Claude (карта скелета, напрями стилю, тексти,
запис у Canva, перевірка), студія кладе завданнями в `jobs/pending/`; skill `/studio` у сесії Claude Code їх
виконує скриптами з `studio/canva/`.

**Tech Stack:** Python 3.13 із середовища ComfyUI (PIL 12.3, numpy 2.5, scipy — є; pytest — немає, тому
`unittest`); HTML + vanilla JS без збірки; ComfyUI + Z-Image Turbo; конектор Canva (MCP) у Claude Code.

**Spec:** `studio/DESIGN.md` (затверджено 2026-11-20). Виконавці читають обидва файли.

**Команда тестів (усі задачі):**
`cd /Users/volost/GitRepos/canva/studio && /Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python -I -m unittest discover -s tests -t . -v`
(далі — `RUN_TESTS`; для одного файлу додати `-p test_<name>.py`).

**Git:** проєкт не є репозиторієм. Кроки «Commit» виконуються лише якщо власник дозволив `git init` у
`studio/` (локально, без push, без `Co-Authored-By`); інакше крок пропускається.

## Global Constraints

- Ніколи не редагувати `DAHarqlqips` (куплений Ivory Lace) і дизайн скелета; Canva-завдання дозволені лише
  на копію, створену для цього шаблону (DESIGN §5.7.3).
- Один записувач на дизайн: не більше одного Canva-завдання (`apply_canva`, `verify`) у `running/` або
  `pending/` одночасно (DESIGN §5.2, §5.7.5).
- Студія нічого не видаляє: «ще раз» додає нову генерацію, старі файли лишаються; відхилені — позначка в
  стані, не видалення. Ніякої публікації сайту, надсилання форми, зміни налаштувань акаунта.
- Сервер слухає лише `127.0.0.1`; лише стандартна бібліотека + PIL/numpy/scipy середовища ComfyUI; нічого не
  встановлювати.
- Python: `/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python`, запуск з `-I`.
- Моделі: `/Volumes/WoofData/ComfyUI/models`; ComfyUI: `/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/main.py`,
  `--listen 127.0.0.1 --port 8188 --disable-auto-launch --disable-all-custom-nodes --extra-model-paths-config
  /Users/volost/GitRepos/canva/pilot/comfy/extra_model_paths.yaml`.
- Граф Z-Image Turbo: KSampler 8 кроків, cfg 1, `res_multistep`, `simple`; ModelSamplingAuraFlow shift 3;
  CLIPLoader type `lumina2`; негатив — ConditioningZeroOut (як у `pilot/tools/comfy_generate.py`).
- Кожна фінальна картинка має пропорцію своєї рамки з точністю 0,5 %; прозорий декор — доповнений
  (padded), фото — обрізані по центру.
- Після кожного `update_fill` — `crop_media` до точного cover-кадру.
- Кожна перевірка має контроль: навмисно поганий вхід мусить бути відхилений тією ж функцією; інакше
  перевірка вважається зламаною і прогін падає.
- Мова шаблонів — англійська. Шрифти не змінюються конектором: студія видає чекліст ручної заміни.
- Персональні дані — лише живий текст і лише в слотах з `personal: true`; правила `SPEC.md` §7.
- Інтерфейс студії — українською.

## Review Focus

1. ComfyUI не запущено або диск `WoofData` не змонтовано, а власник тисне «Генерувати» → зрозуміле
   повідомлення в інтерфейсі за ≤ 5 с, без зависання (тест у Task 5).
2. Власник повертається і змінює вже затверджений крок → усі наступні кроки стають `stale`, і завдання
   `apply_canva` з застарілими даними не створюється (тест у Task 2 і Task 3).
3. Подвійне натискання «Записати в Canva» → друге Canva-завдання відхилено (тест у Task 3).
4. Тексти з `’ “ ” é & < >` і переносом рядка → зберігаються й передаються в завдання без змін, інтерфейс
   показує їх без HTML-ін'єкції (тест у Task 9 і Task 10).
5. Пошкоджений або напівзаписаний JSON у скриньці чи в результаті завдання → студія показує завдання як
   «пошкоджене», не падає (тест у Task 3).

---

## Структура файлів

```
studio/
  DESIGN.md  PLAN.md
  config.json                  шляхи, порти, заборонені id
  run.sh                       запуск для власника (ComfyUI + студія)
  app/
    config.py                  Config, load_config
    store.py                   шаблони/скелети на диску, атомарний запис JSON
    steps.py                   стани кроків, затвердження, stale
    guard.py                   захист оригіналів
    jobs.py                    скринька завдань, замок Canva, зависання
    schema.py                  перевірка map.json / style.json / texts.json
    texts.py                   попередження про довжину
    comfy.py                   клієнт ComfyUI
    genqueue.py                послідовна черга генерацій у фоні
    imaging/
      core.py                  aspect_error, cover_crop, pad_to_frame, alpha_coverage, checker, on_background
      cutout.py                watercolour_to_alpha, solid_cutout
      envelope.py              compose_envelope, check_envelope (геометрія з map.json)
      sheet.py                 contact_sheet
    assets.py                  план генерацій по ассетах, постобробка, перевірка, маніфест
    server.py                  HTTP: статика + JSON API
    static/ index.html app.js style.css
  canva/                       скрипти для Claude-сесії (узагальнені з Sage & Linen)
    facts.py outline.py probe_diff.py layout.py   (копії, без жорстких id)
    ops.py                     операції з map + style + texts
    protected.py final_check.py fields.py geometry.py
  tests/  test_*.py, fixtures/
  skeletons/<skeleton>/  templates/<template>/  jobs/{pending,running,done,failed}/
/Users/volost/GitRepos/canva/.claude/skills/studio/SKILL.md + jobs/*.md
```

## Формати даних (спільні для всіх задач)

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
  кроки `STEPS = ("style", "images", "texts", "apply", "verify")`; статуси `draft`, `waiting_claude`, `review`, `approved`, `stale`.
- Завдання `jobs/<state>/<id>.json`: `{"id", "type", "template"|null, "skeleton", "target_design_id"|null,
  "created_utc", "inputs": {...}, "limits": [str]}`; типи `map_skeleton`, `style_directions`, `write_texts`,
  `apply_canva`, `verify`; Canva-типи — `apply_canva`, `verify` (і `map_skeleton`, що лише читає).
- Результат `templates/<t>/jobs/<id>.result.json` (для `map_skeleton` — `skeletons/<s>/jobs/`):
  `{"status": "done"|"failed", "summary": str, "outputs": {...}, "checks": [{"name": str, "passed": bool, "detail": str}]}`.

---

### Task 1: Каркас, конфіг і запуск

**Who:** Sonnet, medium — чітко описаний каркас, мало суджень.

**Files:** Create `studio/config.json`, `studio/app/__init__.py`, `studio/app/config.py`, `studio/app/server.py`,
`studio/app/static/index.html`, `studio/run.sh`, `studio/tests/__init__.py`, `studio/tests/test_config.py`, `studio/tests/test_server.py`.

**Interfaces:**
- Produces: `Config` (frozen dataclass: `root: Path`, `python: Path`, `comfy_main: Path`, `models_dir: Path`,
  `extra_model_paths: Path`, `comfy_url: str`, `studio_port: int`, `forbidden_design_ids: frozenset[str]`);
  `load_config(path: Path) -> Config`; `make_server(cfg: Config, port: int) -> ThreadingHTTPServer`;
  `GET /api/health -> {"ok": true, "comfy_url": str, "models_mounted": bool}`.

- [ ] **Step 1: Write the failing tests** — `test_load_config_reads_values` (з `tests/fixtures/config.json`:
  `forbidden_design_ids == {"DAHarqlqips"}`, `studio_port == 8765`); `test_load_config_rejects_missing_key`
  (`ValueError` з назвою ключа); `test_health_endpoint` (сервер на порту 0 у потоці, `GET /api/health` →
  200, `ok is True`, `models_mounted` — bool); `test_server_binds_localhost_only` (`server_address[0] == "127.0.0.1"`).
- [ ] **Step 2:** `RUN_TESTS -p "test_c*.py"` і `-p "test_server.py"` → FAIL (модулів немає).
- [ ] **Step 3:** Реалізувати `load_config`, `make_server` (обробник на `BaseHTTPRequestHandler`, статика з
  `app/static`, JSON-відповіді з `Content-Type: application/json; charset=utf-8`). `config.json` — значення з
  Global Constraints, `studio_port` 8765, `forbidden_design_ids` `["DAHarqlqips"]`.
- [ ] **Step 4:** `run.sh`: перевіряє, що `/Volumes/WoofData/ComfyUI/models` існує (інакше повідомлення і
  вихід 1); якщо `curl -s 127.0.0.1:8188` не відповідає — стартує ComfyUI у фоні з лог-файлом
  `studio/logs/comfy.log`; стартує студію; друкує `Студія: http://127.0.0.1:8765` і `ComfyUI: http://127.0.0.1:8188`.
- [ ] **Step 5:** `RUN_TESTS` → PASS. Ручна перевірка не потрібна (сервер поза пісочницею запускає власник).
- [ ] **Step 6: Commit** `feat(studio): skeleton, config, launcher`.

### Task 2: Сховище і стани кроків

**Who:** Sonnet, medium — логіка стану, чіткі правила.

**Files:** Create `app/store.py`, `app/steps.py`, `tests/test_store.py`, `tests/test_steps.py`.

**Interfaces:**
- Consumes: `Config` (Task 1).
- Produces: `write_json_atomic(path: Path, data) -> None` (тимчасовий файл + `os.replace`);
  `read_json(path: Path) -> dict` (кидає `CorruptJSON(path)` на поганий JSON);
  `create_template(cfg, name: str, skeleton: str) -> Path`; `list_templates(cfg) -> list[str]`;
  `template_dir(cfg, name) -> Path`; `skeleton_dir(cfg, name) -> Path`;
  `STEPS`, `set_status(state: dict, step: str, status: str) -> dict`; `approve(state, step) -> dict`;
  `reopen(state, step) -> dict` (крок → `review`, усі наступні `approved`/`review` → `stale`);
  `can_start(state, step) -> bool` (усі попередні `approved`).

- [ ] **Step 1: Write the failing tests** — `test_atomic_write_roundtrip`; `test_read_corrupt_raises`
  (файл `{"a":` → `CorruptJSON`); `test_create_template_rejects_bad_name` (`"../x"`, `""`, `"a/b"` → `ValueError`;
  дозволено `[a-z0-9-]{1,40}`); `test_create_template_existing_raises`; `test_reopen_marks_later_stale`
  (усі approved, `reopen(state,"images")` → images `review`, texts/apply/verify `stale`, style `approved`);
  `test_can_start_requires_previous_approved` (`can_start(s,"apply")` False, поки texts `stale`).
- [ ] **Step 2:** `RUN_TESTS -p "test_st*.py"` → FAIL.
- [ ] **Step 3:** Реалізувати; `updated_utc` — `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.
- [ ] **Step 4:** `RUN_TESTS` → PASS.
- [ ] **Step 5: Commit** `feat(studio): template store and step states`.

### Task 3: Скринька завдань і захист оригіналів

**Who:** Sonnet, high — тут живуть анти-цілі (запис в оригінал, два записувачі); помилка дорога.

**Files:** Create `app/guard.py`, `app/jobs.py`, `tests/test_guard.py`, `tests/test_jobs.py`.

**Interfaces:**
- Consumes: `Config`, `store.*`, `steps.can_start` (Tasks 1–2).
- Produces: `GuardError(Exception)`; `check_job(job: dict, cfg: Config, skeleton_design_id: str, state: dict|None) -> None`;
  `CANVA_WRITE_TYPES = {"apply_canva", "verify"}`; `create_job(cfg, type: str, skeleton: str, template: str|None,
  inputs: dict, target_design_id: str|None) -> dict`; `list_jobs(cfg) -> list[dict]` (кожен з `state` ∈
  `pending|running|done|failed|corrupt`, `age_s`); `canva_busy(cfg) -> bool`; `read_result(cfg, job) -> dict|None`.

- [ ] **Step 1: Write the failing tests** — `test_guard_blocks_purchased_original` (`target_design_id="DAHarqlqips"` → `GuardError`);
  `test_guard_blocks_skeleton_id`; `test_guard_verify_requires_template_copy` (verify з target ≠
  `state["canva_copy_id"]` → `GuardError`); `test_guard_apply_first_run_target_none_ok` (apply з `target None`
  і `canva_copy_id None` — дозволено: копію створить Claude); `test_guard_apply_stale_texts_refused`
  (`can_start(state,"apply")` False → `GuardError`); `test_second_canva_job_refused` (два `create_job("apply_canva")`
  поспіль → другий `GuardError`, у `pending/` один файл); `test_corrupt_job_listed_not_raised` (сміття в
  `pending/x.json` → `list_jobs` повертає `state == "corrupt"`); `test_job_limits_present` (кожне Canva-завдання
  має в `limits` рядки з DESIGN §5.2).
- [ ] **Step 2:** `RUN_TESTS -p "test_guard.py"`, `-p "test_jobs.py"` → FAIL.
- [ ] **Step 3:** Реалізувати; id завдання `YYYYmmddTHHMMSSZ-<type>`; `canva_busy` — є Canva-завдання в
  `pending/` або `running/`; `create_job` викликає `check_job` до запису; запис — `write_json_atomic`.
- [ ] **Step 4:** `RUN_TESTS` → PASS.
- [ ] **Step 5: Commit** `feat(studio): job inbox with original-design guard`.

### Task 4: Бібліотека обробки картинок

**Who:** Sonnet, medium — перенесення перевіреного коду з тестами.

**Files:** Create `app/imaging/__init__.py`, `core.py`, `cutout.py`, `sheet.py`, `tests/test_imaging.py`.
Джерела: `study/sage-linen/tools/lib.py` (функції з тими ж назвами), `cutout_watercolour.py`,
`cutout_solid.py`, `contact_sheet.py`, `pilot/tools/white_to_alpha.py`.

**Interfaces:**
- Produces: `aspect_error(size: tuple[int,int], frame: tuple[int,int]) -> float`;
  `cover_crop(img, frame, cx=0.5, cy=0.5) -> Image`; `pad_to_frame(img, frame, scale, margin=0.0, anchor=(0.5,0.5)) -> Image`;
  `alpha_coverage(img) -> float`; `watercolour_to_alpha(img, speck=80) -> Image`;
  `solid_cutout(img, tol=14, holes=None, erode=2, feather=1.0) -> Image`;
  `contact_sheet(items: list[tuple[str, Path]], out: Path, long_edge=1568) -> Path`.
  Без глобальних шляхів (`ROOT`, `ASSETS`) — усе через параметри.

- [ ] **Step 1: Write the failing tests** — `test_cover_crop_exact_aspect` (1000×700 у рамку 433×600 →
  `aspect_error < 0.005`); `test_pad_keeps_alpha` (результат RGBA, кути прозорі); `test_watercolour_white_becomes_transparent`
  (біле тло → alpha 0, пляма кольору → alpha > 0); `test_solid_cutout_keeps_highlight_opaque` (біле коло
  всередині темного кільця не прозоре без `holes`); `test_contact_sheet_long_edge` (≤ 1568).
- [ ] **Step 2:** FAIL. **Step 3:** перенести функції. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): imaging library`.

### Task 5: Клієнт ComfyUI і черга генерацій

**Who:** Sonnet, medium.

**Files:** Create `app/comfy.py`, `app/genqueue.py`, `tests/test_comfy.py`, `tests/test_genqueue.py`.
Джерело графа: `pilot/tools/comfy_generate.py`.

**Interfaces:**
- Consumes: `Config`.
- Produces: `ComfyError(Exception)`; `build_graph(prompt: str, width: int, height: int, seed: int, prefix: str) -> dict`;
  `ping(cfg, timeout=3.0) -> bool`; `generate(cfg, prompt, width, height, seed, prefix, out_dir: Path, timeout=1500) -> list[Path]`;
  `GenQueue(cfg, log_path: Path)` з `submit(job: dict) -> str`, `status() -> list[dict]` (`queued|running|done|failed`,
  `error`, `seconds`), один робочий потік; кожен запуск — рядок у `generations.jsonl`
  (`utc, prefix, seed, width, height, exit, saved, seconds, prompt`).

- [ ] **Step 1: Write the failing tests** — `test_build_graph_settings` (у графі steps 8, cfg 1, sampler
  `res_multistep`, scheduler `simple`, shift 3, CLIP type `lumina2`, розміри й seed передані);
  `test_ping_closed_port_fast` (URL на вільний порт → `False` менш ніж за 5 с);
  `test_queue_reports_comfy_down` (черга з недоступним ComfyUI → завдання `failed`, `error` містить
  «ComfyUI недоступний», рядок у jsonl з `exit != 0`); `test_queue_sequential` (підмінений `generate`
  фіксує, що два завдання не перетинаються в часі).
- [ ] **Step 2:** FAIL. **Step 3:** реалізувати (`urllib.request`; `/prompt`, `/history/<id>`, `/view`).
- [ ] **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): ComfyUI client and generation queue`.

### Task 6: Конверт за геометрією з карти

**Who:** Sonnet, high — геометрія, яку модель не вгадає; є готова перевірка.

**Files:** Create `app/imaging/envelope.py`, `tests/test_envelope.py`. Джерела: `study/sage-linen/tools/compose_envelope.py`,
`check_assets.py:check_envelope`.

**Interfaces:**
- Consumes: `imaging.core`; блок `envelope` з `map.json`.
- Produces: `compose_envelope(texture: Image, geom: dict, scale=2, seal: Image|None=None) -> tuple[Image, Image, Image]`
  (cover, flap, body); `check_envelope(cover, flap, body, geom, scale=2) -> list[str]` (порожній = добре).
  Константи `TIP`, `SEAL_CENTRE` тощо — з `geom`, не з коду.

- [ ] **Step 1: Write the failing tests** — `test_envelope_layers_reproduce_cover` (геометрія Sage & Linen:
  section 1366×964, tip (683,610), left_top (0,60), right_top (1366,60), seal_centre (683,623),
  seal_size (160,198), seal_rot_canva −3.4; рівномірна текстура → `check_envelope == []`);
  `test_envelope_no_transparent_pixel` (flap над body — альфа 255 скрізь);
  `test_check_rejects_shifted_flap` (зсув flap на 6 px → непорожній список — контроль).
- [ ] **Step 2:** FAIL. **Step 3:** перенести, параметризувати геометрією. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): envelope from skeleton geometry`.

### Task 7: Схеми даних і тексти

**Who:** Sonnet, medium.

**Files:** Create `app/schema.py`, `app/texts.py`, `tests/test_schema.py`, `tests/test_texts.py`,
`tests/fixtures/map_min.json`, `tests/fixtures/style_min.json`.

**Interfaces:**
- Produces: `validate_map(d: dict) -> list[str]`; `validate_style(d: dict, m: dict) -> list[str]`
  (кожен ассет із `m["assets"]` має промпт; кожна роль кольору є в палітрі; кольори `#rrggbb`);
  `validate_texts(d: dict, m: dict) -> list[str]` (лише локатори текстових слотів);
  `length_warnings(texts: dict, m: dict) -> dict[str, str]` (одиничний рядок довший за `max_len`;
  абзац довший за 115 % `original`); `font_checklist(m: dict, style: dict) -> list[dict]`
  (`locator, role, font`).

- [ ] **Step 1: Write the failing tests** — `test_map_min_valid`; `test_map_rejects_slot_without_locator`;
  `test_map_rejects_image_slot_with_unknown_asset`; `test_style_requires_prompt_per_asset`;
  `test_texts_unknown_locator_rejected`; `test_length_warning_one_line` (`max_len` 20, 25 символів → попередження);
  `test_unicode_text_preserved` (`"We’re “so” happy — Café & <b>\nline"` проходить `validate_texts` і
  записується/читається через `store` байт у байт); `test_font_checklist_lists_every_text_role`.
- [ ] **Step 2:** FAIL. **Step 3:** реалізувати. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): data schemas, length warnings, font checklist`.

### Task 8: Конвеєр ассетів

**Who:** Sonnet, high — з'єднує карту, генерацію, обробку і перевірки; від нього залежить якість картинок.

**Files:** Create `app/assets.py`, `tests/test_assets.py`.

**Interfaces:**
- Consumes: `comfy`, `genqueue`, `imaging.*`, `schema` (Tasks 4–7).
- Produces: `gen_size(frame: tuple[int,int], megapixels=1.5) -> tuple[int,int]` (кратні 64, пропорція рамки
  ±3 % — точну дає постобробка); `plan_generations(m: dict, style: dict) -> list[dict]` (на ассет:
  `asset, prompt, width, height, kind`; `composed` → генерується лише текстура, решта — `compose_envelope`);
  `postprocess(asset: str, src: Path, m: dict, out_dir: Path) -> Path` (photo/texture → `cover_crop`;
  watercolour → `watercolour_to_alpha` + `pad_to_frame`; solid → `solid_cutout` + `pad_to_frame`);
  `check_asset(path: Path, spec: dict) -> list[str]`; `check_all(template_dir: Path, m: dict) -> dict`
  (на файл — список проблем, плюс `controls_ok: bool` з навмисно поганих файлів);
  `build_manifest(template_dir: Path, m: dict) -> Path`. Файли версіонуються: `assets/<asset>__v<n>.<ext>`,
  обраний — у `state.json` (`"chosen": {<asset>: <file>}`); попередні версії не видаляються.

- [ ] **Step 1: Write the failing tests** — `test_gen_size_multiple_of_64_and_close_aspect`
  (рамка 433×600); `test_plan_has_every_asset`; `test_postprocess_photo_exact_aspect`;
  `test_postprocess_watercolour_transparent`; `test_check_all_controls_reject_bad`
  (неправильна пропорція, непрозорий «прозорий» файл, файл, що не відкривається → кожен відхилено;
  `controls_ok True`); `test_regenerate_keeps_previous_version` (v1 лишається після v2).
- [ ] **Step 2:** FAIL. **Step 3:** реалізувати. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): asset pipeline with checks and versions`.

### Task 9: JSON API студії

**Who:** Sonnet, medium.

**Files:** Modify `app/server.py`; Create `tests/test_api.py`.

**Interfaces:**
- Consumes: усе з Tasks 2–8.
- Produces (усі відповіді JSON; помилки — `{"error": str}` з 400/409/500, без трасування):
  `GET /api/skeletons`, `POST /api/skeletons {name, design_id}` → створює завдання `map_skeleton`;
  `GET /api/skeletons/<s>`, `PUT /api/skeletons/<s>/roles {locator: role}`;
  `GET /api/templates`, `POST /api/templates {name, skeleton, brief}` → завдання `style_directions`;
  `GET /api/templates/<t>` (state, style, texts, warnings, assets, jobs);
  `PUT /api/templates/<t>/style`, `POST /api/templates/<t>/images/generate {assets?: [..], prompt_override?}`,
  `POST /api/templates/<t>/images/choose {asset, file}`, `POST /api/templates/<t>/texts/request` → `write_texts`,
  `PUT /api/templates/<t>/texts`, `POST /api/templates/<t>/approve {step}`, `POST /api/templates/<t>/reopen {step}`,
  `POST /api/templates/<t>/apply` → `apply_canva`, `POST /api/templates/<t>/verify` → `verify`;
  `GET /api/jobs`, `GET /api/gen`; `GET /files/<path>` — лише всередині `skeletons/` і `templates/`.

- [ ] **Step 1: Write the failing tests** — `test_create_template_flow` (POST template → 200, у `pending/` завдання
  `style_directions`); `test_apply_twice_conflict` (друге `apply` → 409); `test_apply_refused_when_texts_stale` → 409;
  `test_files_path_traversal_blocked` (`/files/../config.json` і `/files/%2e%2e/config.json` → 404);
  `test_bad_json_body_400`; `test_unicode_texts_roundtrip` (рядок з Task 7 через PUT/GET без змін).
- [ ] **Step 2:** FAIL. **Step 3:** реалізувати маршрути. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): JSON API`.

### Task 10: Інтерфейс

**Who:** Sonnet, high — UI; перевіряється у браузері вимірюванням, не на око.

**Files:** Create/Modify `app/static/index.html`, `app/static/app.js`, `app/static/style.css`.

**Interfaces:** Consumes the API of Task 9. Екрани (DESIGN §5.1): список шаблонів і скелетів; карта скелета з
мініатюрами і редагуванням ролей; бриф і вибір напряму стилю; галерея картинок (прийняти / ще раз / своя
підказка; аркуш-огляд; статус черги й ComfyUI); тексти з попередженнями; «Записати в Canva» з поясненням
«виконайте `/studio` у сесії Claude Code»; результат перевірки (сторінки, таблиця перевірок, посилання на
дизайн, чекліст шрифтів і ручних кроків). Смуга кроків угорі зі статусами. Стан завдань оновлюється
опитуванням `GET /api/jobs` кожні 3 с. Увесь текст користувача вставляється через `textContent`, не `innerHTML`.

- [ ] **Step 1:** Запустити студію з тестовими даними (`tests/fixtures/`) поза пісочницею; відкрити у
  вбудованому браузері `http://127.0.0.1:8765`.
- [ ] **Step 2: Перевірка списком елементів** — для кожного екрана з переліку вище: елемент є в DOM
  (`read_page`), видимий, кнопки досяжні (`getBoundingClientRect` у межах вікна при 1440×900 і 768×1024),
  немає горизонтальної прокрутки.
- [ ] **Step 3: Перевірка ін'єкції** — текст `<img src=x onerror=alert(1)>` у полі тексту показується як текст
  (`document.querySelectorAll('img[src="x"]').length === 0`).
- [ ] **Step 4:** Помилка ComfyUI (Review Focus 1) показується повідомленням на екрані картинок.
- [ ] **Step 5: Commit** `feat(studio): web interface`.

### Task 11: Скрипти для Canva-сесії

**Who:** Sonnet, high — узагальнення скриптів, що захищали дизайн 12.11; помилка = зіпсований дизайн.

**Files:** Create `studio/canva/{facts,outline,probe_diff,layout}.py` (копії з `study/sage-linen/canva/` і
`handoff/tools/`, без жорстких id), `studio/canva/ops.py`, `protected.py`, `final_check.py`, `fields.py`,
`geometry.py`, `tests/test_canva_ops.py`, `tests/test_canva_checks.py`, `tests/fixtures/facts_sage.json`
(копія `study/sage-linen/canva/facts_final.json`), `tests/fixtures/facts_orig.json` (копія `facts0.json`).

**Interfaces:**
- Produces: `cover_box(frame_w, frame_h, img_w, img_h) -> dict(left, top, width, height)` (точний cover, центр);
  `build_ops(m: dict, style: dict, texts: dict, facts: dict) -> dict[str, list[dict]]` (пакети по сторінках:
  `replace_text`, `format_text` колір, `recolor_element`/`update_fill` для кольорів; ніколи не торкається
  `m["protected"]`); `verify_batch(before: dict, after: dict, ops: list) -> list[str]` (неціловані зміни
  мусять бути відсутні); `protected_changes(orig: dict, now: dict, m: dict) -> list[str]`;
  `final_check(orig: dict, now: dict, m: dict, texts: dict) -> list[dict]` (на кожну перевірку `name, passed, detail`,
  плюс контроль: на `orig` перевірки мусять падати); `build_fields(m: dict, texts: dict) -> dict` і
  `page_notes(m: dict) -> dict[str, str]`.
  CLI кожного скрипта: `python -I <script>.py <args>` друкує підсумок, повний вивід — у файл.

- [ ] **Step 1: Write the failing tests** — `test_cover_box_centred_exact` (рамка 433×600, картинка 866×1300 →
  ширина 433, висота 650, top −25); `test_build_ops_never_touches_protected`; `test_build_ops_text_uses_replace_text`;
  `test_verify_batch_flags_untargeted_change`; `test_protected_change_detected` (синтетична зміна media id →
  знайдено — контроль); `test_final_check_fails_on_original` (на `facts_orig` перевірки падають);
  `test_fields_cover_every_personal_slot`.
- [ ] **Step 2:** FAIL. **Step 3:** реалізувати/перенести. **Step 4:** PASS.
- [ ] **Step 5: Commit** `feat(studio): Canva-side scripts`.

### Task 12: Skill `/studio` та інструкції завдань

**Who:** Opus, high після оновлення ліміту (до 22.11 — Sonnet, high) — суджень багато: правила конектора,
межі, що робити при невдачі; помилка псує дизайн або витрачає ліміт.

**Files:** Create `/Users/volost/GitRepos/canva/.claude/skills/studio/SKILL.md`, `.../jobs/map_skeleton.md`,
`style_directions.md`, `write_texts.md`, `apply_canva.md`, `verify.md`. Запис у `.claude/skills` пісочниця
блокує — потрібен дозвіл власника на цей запис.

**Interfaces:**
- Consumes: формати даних (вище), скрипти Task 11, `PLAYBOOK.md` §4–7, `SPEC.md` §7.
- Produces: SKILL.md: (1) спершу `jobs/running/` (DESIGN §5.7.5); (2) найстаріше `pending/` → `running/`;
  (3) перевірка цілі: id ≠ `DAHarqlqips`, ≠ id скелета, для verify = `canva_copy_id`; (4) інструкція типу
  з `jobs/<type>.md`; (5) результат у `<id>.result.json` за форматом; (6) `done/` або `failed/`.
  Кожна інструкція: що прочитати, кроки, жорсткі межі DESIGN §5.2, формат `outputs` і `checks`.
  `apply_canva`: `copy-design` скелета → записати `canva_copy_id` у `state.json` → кольори і тексти пакетами з
  `verify_batch` після кожного → завантаження картинок (`create-upload-url` + `curl`) → `update_fill` +
  `crop_media(cover_box)` → стрес-тест довгими значеннями з `SPEC.md` §7.4 і відновлення з diff →
  нотатки сторінок → `fields.json` → `protected_changes == []`. `verify`: експорт PNG, нарізка, контраст під
  білим текстом, перегляд у повноекранному прев'ю (телефон і 1440×810), аудит кнопок 9/9 (JS з PLAYBOOK §5
  Phase 7), чекліст шрифтів і ручних кроків.

- [ ] **Step 1:** Написати SKILL.md та п'ять інструкцій.
- [ ] **Step 2: Сухий прогін** — завдання `write_texts` для тестового шаблону з `tests/fixtures/`: `/studio`
  бере його, пише `texts.json` і результат, переносить у `done/`; студія показує тексти.
- [ ] **Step 3: Перевірка захисту** — підкласти в `pending/` вручну зроблене завдання `verify` з
  `target_design_id: "DAHarqlqips"` → skill відмовляє, завдання в `failed/` з причиною, жодного виклику Canva.
- [ ] **Step 4: Commit** `feat(studio): /studio skill and job instructions`.

### Task 13: Наскрізний прогін на тестовій копії

**Who:** провідна сесія (Opus після оновлення ліміту) разом із власником — потрібні Canva, браузер, рішення власника.

**Files:** `studio/skeletons/probe/`, `studio/templates/<перший-стиль>/`, звіт `studio/templates/<t>/RUN_NOTES.md`.

- [ ] **Step 1:** Власник запускає `studio/run.sh`; студія і ComfyUI відповідають (адреси в звіті).
- [ ] **Step 2:** Скелет `probe` = `DAHason1g_M`; `/studio` виконує `map_skeleton`; власник виправляє ролі.
- [ ] **Step 3:** Шаблон: бриф → `style_directions` → вибір → картинки (усі прийняті) → `write_texts` → правки → затвердження.
- [ ] **Step 4:** «Записати» → `/studio` виконує `apply_canva` на новій копії; `protected_changes == []`.
- [ ] **Step 5:** «Перевірити» → `/studio` виконує `verify`; усі перевірки пройдені з числами; аудит кнопок 9/9.
- [ ] **Step 6:** Записати в звіт: час кожного кроку, витрату ліміту (`get_usage` до і після), що не вдалося.

### Task 14: Специфікація власного скелета для власника

**Who:** провідна сесія, Sonnet medium до 22.11 — документ на основі `study/ivory-lace/BLUEPRINT.md` і вимог DESIGN §5.6.
Незалежна від Tasks 1–13, можна робити будь-коли.

**Files:** Create `studio/SKELETON_SPEC.md`.

- [ ] **Step 1:** Описати для власника, українською, покроково в редакторі Canva: сторінки і секції, ширина
  колонки для телефона, рамки під картинки з розмірами, текстові поля (окреме поле на кожне персональне
  значення), конверт із двох шарів, кнопки з посиланням на верхньому елементі, форма, вбудовані блоки,
  без тексту в картинках.
- [ ] **Step 2:** Перевірити кожну назву меню в редакторі Canva (англійський інтерфейс власника) через
  вбудований браузер; що не перевірено — позначити.
- [ ] **Step 3:** Віддати власнику на читання.

Не входить у план (DESIGN §4): кнопка фонового запуску `claude -p` — окремо, після тесту.
