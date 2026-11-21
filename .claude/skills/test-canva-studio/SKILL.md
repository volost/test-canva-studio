---
name: test-canva-studio
disable-model-invocation: true
description: Run the next job of the wedding-template studio. The owner types /test-canva-studio (optionally followed by the studio root folder) after pressing a button in the studio page; Claude takes the oldest job from jobs/pending/, executes it (map a skeleton, propose styles, write texts, write a template into Canva, verify it) and files the result.
---

# /test-canva-studio — execute ONE studio job

The studio (a local web page) puts jobs as JSON files into `jobs/pending/`. You are the "Claude half" of the
product: you execute exactly ONE job per `/test-canva-studio`, write its result file, and move the job file to `done/` or
`failed/`. A wrong step here damages a real Canva design or wastes the weekly limit, so every rule below is
binding and every "check" must be run, not assumed.

Language: this file and the job instructions are English. Everything the owner reads (result `summary`, check
`detail` strings you write yourself, `manual_steps`, your closing message) is Ukrainian. Template content
(texts written into designs) is English.

## 0. Constants

Argument of this invocation (may be empty): `$ARGUMENTS`

- `CODE` = the repository root — where `app/`, `canva/` and `docs/` (the scripts and the reference notes) live.
  This skill lives at `<repo>/.claude/skills/test-canva-studio/`, so it is loaded only by a session opened in the
  repository root, whose working directory is therefore the repository. Find `CODE` ONCE, first thing, with
  `git rev-parse --show-toplevel` (equivalently `git -C "<SKILL_DIR>" rev-parse --show-toplevel`; use the second form if
  the working directory is somewhere else), and check that `CODE/app/guard.py` and `CODE/.claude/skills/test-canva-studio/SKILL.md`
  exist; otherwise tell the owner and stop. Nothing in this skill hard-codes a machine path: the same files work on every machine.
  Relative paths in the job instructions (`docs/reference/PLAYBOOK.md`, `DESIGN.md`, `app/...`, `canva/...`) are relative to `CODE`.
- `ROOT` = the studio root (the folder with `jobs/`, `templates/`, `skeletons/` and its own `config.json`) = the argument
  if it is not empty, else `CODE`.
  Every data path below (`jobs/`, `templates/`, `skeletons/`, `config.json`) is relative to `ROOT`.
  Before anything else check that `ROOT/config.json` and `ROOT/jobs/pending` exist; otherwise tell the owner
  and stop (touch nothing). (`ROOT/config.json` is the machine-local file a developer creates from `config.example.json`.)
- `PY` = the `python` key of `ROOT/config.json` (the ComfyUI virtualenv's Python, which has PIL and numpy). Read it once with
  the system Python (stdlib only): `python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["python"])' "$ROOT/config.json"`,
  and check that the file it names exists and is executable. Always run Python as `$PY -I`.
  Shell state does not persist between Bash calls: put `ROOT=...; CODE=...; PY=...` (the literal values found above)
  at the start of every Bash command that uses them. Scripts are run from `CODE`
  (`cd "$CODE" && $PY -I canva/ops.py ...`); data files are given by absolute path under `ROOT`.
- `SKILL_DIR` = the folder of this SKILL.md; the job instructions are `SKILL_DIR/jobs/<type>.md`.
- `BASE` = `ROOT/templates/<template>` for template jobs, `ROOT/skeletons/<skeleton>` for `map_skeleton`.
  Result: `BASE/jobs/<job id>.result.json`. Notes: `BASE/jobs/<job id>.notes.md`. Work folder (facts, operation
  files, exports; never deleted): `BASE/work/<job id>/`.
- The Canva connector tools are deferred tools: load them with ToolSearch before first use. Their names (PLAYBOOK §3):
  `read-design`, `edit-design`, `copy-design`, `export-design`, `get-export-formats`, `create-upload-url`,
  `get-assets`, `search-designs`, `help`. Use no other Canva tool.
  Every Canva call (`read-design`, `edit-design` including `cancel` and `commit`, `copy-design`, `export-design`, `get-export-formats`,
  `create-upload-url`, `get-assets`) passes `user_intent` (mandatory in the connector's schema): one concise sentence, at most 255
  characters, e.g. `Studio job <id>: reading the copy to measure it`.

## HARD LIMITS (every Canva job; repeated at the top of apply_canva.md, verify.md and map_skeleton.md)

1. Edit ONLY the design whose id is the job's `target_design_id` — the template's own copy (`canva_copy_id` in
   `templates/<t>/state.json`). Nothing else is ever edited.
2. NEVER edit or commit to `DAHarqlqips` (the purchased original), any id in `config.json` `forbidden_design_ids`,
   or the skeleton design (`skeletons/<s>/map.json` `design_id`). The skeleton may only be READ (map_skeleton; or, as
   a last resort, the baseline of apply_canva): open a read transaction and END it with `finalize: "cancel"`.
3. Never touch the form (element type `unsupported`), the embeds, or the envelope structure (overlay groups: no
   move, regroup, reorder or delete; only their image fills are replaced).
4. No regrouping, no new pages, no deletions (pages, elements, files, designs, folders).
5. NEVER PUBLISH. No publishing, sharing or template links; no account settings; no form submission; never type
   credentials. If a sign-in page appears, ask the owner to sign in themselves.
6. Upload nothing except the template's chosen asset files (`state.json` `chosen`, hash-checked against
   `assets/manifest.json`).
7. `edit-design` operation types allowed, exactly: `replace_text`, `format_text` (only `color`; `font_size` only for a
   declared text-fit fix; never `link`), `recolor_element`, `update_stroke_properties`, `update_fill`, `crop_media`,
   `position_element`, `resize_element`, `replace_speaker_notes`. Everything else is forbidden (`add_page`,
   `delete_*`, `group_elements`, `ungroup_elements`, `insert_*`, `add_text`, `replace_shape`, `reorder_page`,
   `layer_element`, `update_opacity`, `rotate_element`, `flip_media`, `update_text_anchoring`, `update_line_properties`,
   `update_autofill_field`, `update_title`).
8. Two identical failures of the same connector call in a row: stop retrying, write a note, move the job to `failed/`.
9. On disk: delete nothing and overwrite no existing data file of the studio (jobs, results, `style.json`, `texts.json`,
   `state.json`, maps, assets) except through the snippets below (temp file + rename). Only the working files you
   created yourself in this job's work folder may be replaced. Move job files with `mv -n` only. `rm`, `git clean`,
   `git reset` are never used.
10. One job per `/test-canva-studio`. One writer per design: never run a second Canva job while another is in `running/`.

## 1. Procedure

### 1.1 Look in `jobs/running/` first (DESIGN §5.7.5, PLAYBOOK §6 restart rule)

`mkdir -p ROOT/jobs/{pending,running,done,failed}`. List `ROOT/jobs/running/*.json`. If there is one (several: take the
oldest by file name, tell the owner about the others), it is an interrupted job:

1. FIRST, before any precheck: if `BASE/jobs/<id>.result.json` already exists (the earlier run stopped between the result and the move;
   the studio may meanwhile have moved the step on to `review`, so the precheck would now refuse a job that is in fact finished), check
   it with the `write_result` snippet (1.5), giving the EXISTING result file as the draft argument and `--validate-only` as a fifth argument.
   Valid (exit 0) → no precheck, no Canva call, no instruction file: just file the job by that result's `status` (1.6) and tell the
   owner (1.7). Invalid → never overwrite it: write `BASE/jobs/<id>.refused.note.txt` (Ukrainian: what is wrong) and file the job as failed (1.6).
2. Otherwise run the precheck (1.3). If it fails: write the result (1.5), then file the job (1.6).
3. Read `BASE/jobs/<id>.notes.md` and the instruction file for the type.
   - `style_directions`, `write_texts`: no Canva involved and idempotent — restart the instruction from its top.
   - `map_skeleton`: restart from its top (reads only; existing thumbnails are kept, never overwritten).
   - `apply_canva`, `verify`: (an interrupted FIRST apply, whose job still has `target_design_id` null although `state.json` already
     holds the new copy id, fails the precheck by design — `check_job` demands target = copy id once a copy exists. File it as
     failed with the copy id in the summary; the owner presses «Записати ще раз» and the new job targets that copy and continues.
     A copy id only in the notes, not in `state.json`, passes the precheck: apply step 2 records it.) Read the CURRENT state of the design first (`read-design` with a transaction,
     then cancel it) and compare with the notes. Continue only if the notes say which phase finished AND the
     design's facts agree with that phase (the instruction file says how). `ops.py build` emits only differences,
     so re-running a finished phase is harmless; never repeat `copy-design` when the notes or `state.json`
     already hold a copy id. If you cannot establish the state with certainty, move the job to `failed/` with the
     reason (the owner re-requests it; apply then continues on the same copy).

### 1.2 Take the oldest pending job

List `ROOT/jobs/pending/*.json` sorted by file name (names start with the UTC time stamp, so this is oldest first).
A file that is not valid JSON, or has no usable `id`/`type` (Read it to see), is NEVER executed and never moved to
`running/`: move it straight to `failed/` (`mv -n pending/<file> failed/<file>` with the same two `test`s as below), write
`ROOT/jobs/failed/<file name>.note.txt` (Ukrainian: what is wrong), then look at the next file. For the first usable file run
the move below. If `pending/` is empty (and `running/` was empty) say so in one line and stop.

```bash
ROOT=...; ID=<job id>
cd "$ROOT/jobs" && mv -n "pending/$ID.json" "running/$ID.json" && test -e "running/$ID.json" && test ! -e "pending/$ID.json" && echo moved
```

`mv -n` never overwrites; if the last two tests do not both hold, stop and tell the owner. Move = rename. Never
copy-and-remove, never delete a job file.

### 1.3 Precheck — BEFORE any Canva call (zero Canva calls on a failure)

Run the snippet on the running job file. It stops on every mismatch: unreadable job, job id different from the file name,
no `limits` list, `target_design_id` (any case, any spaces) among `DAHarqlqips` / `forbidden_design_ids`, the skeleton's own
design id, `verify` whose target is not exactly `canva_copy_id`, `apply_canva` whose target is neither null
(first run, `canva_copy_id` null) nor exactly `canva_copy_id`, `map_skeleton` reading a design that is not the
skeleton's recorded id, earlier template steps not all `approved`, the job's own step not `waiting_claude`
(the owner changed something after queueing: the job is outdated), `apply_canva` whose `inputs.texts` /
`inputs.chosen` differ from `texts.json` / `state.json`. It reuses the studio's own `app.guard.check_job`.

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "$CODE" "$ROOT" "$ROOT/jobs/running/$ID.json" <<'PYEOF'
# snippet: precheck
import dataclasses
import json
import sys
from pathlib import Path

CODE, ROOT, JOB = (Path(a).resolve() for a in sys.argv[1:4])   # code folder, data root, job file
sys.path.insert(0, str(CODE))
from app.config import load_config
from app.guard import CANVA_WRITE_TYPES, JOB_TYPES, GuardError, check_job
from app.steps import STEPS
from app.store import CorruptJSON, read_json, skeleton_dir, template_dir

PROTECTED_ALWAYS = {"daharqlqips"}          # the purchased original, even if config.json is unreadable
STEP_OF = {"write_texts": "texts", "apply_canva": "apply", "verify": "verify"}
bad = []


def fail(msg):
    bad.append(msg)


def done(job=None, **extra):
    out = {"ok": not bad, "reasons": bad}
    if job:
        out.update(type=job.get("type"), template=job.get("template"), skeleton=job.get("skeleton"),
                   target=job.get("target_design_id"), **extra)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(1 if bad else 0)


try:
    job = read_json(JOB)
except (CorruptJSON, OSError) as e:
    fail(f"job file unreadable or not a JSON object: {e}")
    done()

jtype, target, inputs = job.get("type"), job.get("target_design_id"), job.get("inputs")
if jtype not in JOB_TYPES:
    fail(f"unknown job type {jtype!r}")
if job.get("id") != JOB.stem:
    fail(f"job id {job.get('id')!r} does not match the file name {JOB.stem!r}")
limits = job.get("limits")
if not (isinstance(limits, list) and limits and all(isinstance(x, str) and x.strip() for x in limits)):
    fail("the job has no limits list (a job without limits is never executed)")
if not isinstance(inputs, dict):
    fail("inputs is not an object")
    inputs = {}

cfg = None
try:
    # data folders come from the root given, not from the root written inside config.json
    cfg = dataclasses.replace(load_config(ROOT / "config.json"), root=ROOT)
except (OSError, ValueError) as e:
    fail(f"config.json unreadable: {e}")
forbidden = {i.strip().casefold() for i in (cfg.forbidden_design_ids if cfg else ())} | PROTECTED_ALWAYS
if isinstance(target, str) and target.strip().casefold() in forbidden:
    fail(f"target {target!r} is a protected original design")

skeleton_id = state = None
if cfg:
    try:
        sdir = skeleton_dir(cfg, job.get("skeleton"))
        for name in ("map.json", "skeleton.json"):
            if skeleton_id is None and (sdir / name).is_file():
                try:
                    v = read_json(sdir / name).get("design_id")
                except CorruptJSON:
                    v = None
                skeleton_id = v if isinstance(v, str) and v.strip() else None
        if skeleton_id is None:
            v = inputs.get("design_id")
            skeleton_id = v if isinstance(v, str) and v.strip() else None
        if job.get("template") is not None:
            state = read_json(template_dir(cfg, job["template"]) / "state.json")
    except (ValueError, TypeError, OSError, CorruptJSON) as e:
        fail(f"skeleton or template folder unusable: {e}")
if skeleton_id and skeleton_id.strip().casefold() in forbidden:
    fail(f"the skeleton's design id {skeleton_id!r} is a protected original")

if jtype == "map_skeleton":
    rid = inputs.get("design_id")
    if target is not None:
        fail("map_skeleton must have target_design_id null")
    if not (isinstance(rid, str) and rid.strip()):
        fail("map_skeleton has no inputs.design_id to read")
    elif rid.strip().casefold() in forbidden:
        fail(f"map_skeleton would read the protected design {rid!r}")
    elif skeleton_id and rid != skeleton_id:
        fail(f"inputs.design_id {rid!r} differs from the skeleton's recorded id {skeleton_id!r}")

if jtype in CANVA_WRITE_TYPES and cfg and not bad:
    try:
        check_job(job, cfg, skeleton_id, state)      # the studio's own guard, run again
    except GuardError as e:
        fail(f"guard: {e}")
if jtype in STEP_OF and cfg:
    if not (isinstance(state, dict) and isinstance(state.get("steps"), dict)):
        fail("template state.json missing or without a steps table")
    else:
        st = {s: (state["steps"].get(s) or {}).get("status") for s in STEPS}
        step = STEP_OF[jtype]
        before = STEPS[:STEPS.index(step)]
        if any(st[s] != "approved" for s in before):
            fail(f"earlier steps are not all approved: { {s: st[s] for s in before} }")
        if st[step] != "waiting_claude":
            fail(f"step {step} is {st[step]!r}, not waiting_claude: the job is outdated or was never requested")
if jtype == "apply_canva" and cfg and isinstance(state, dict):
    try:
        if inputs.get("texts") != read_json(template_dir(cfg, job["template"]) / "texts.json"):
            fail("inputs.texts differs from texts.json: the texts changed after the job was queued")
    except (CorruptJSON, OSError):
        fail("texts.json unreadable")
    if (inputs.get("chosen") or {}) != (state.get("chosen") or {}):
        fail("inputs.chosen differs from state.json chosen: the picture choice changed after the job was queued")
if jtype in ("style_directions", "write_texts") and state is None and job.get("template") is not None:
    fail("template state unreadable")
done(job, skeleton_design_id=skeleton_id)
PYEOF
```

Read its JSON output. `"ok": true` → continue. `"ok": false` → do NOT open the instruction file's Canva steps, do not
call any Canva tool; write the result (1.5), then file the job (1.6): status `failed`, `summary` = the reasons in Ukrainian,
`outputs` = `{"refused": true, "reasons": [<the reasons verbatim>]}` and one check
`{"name": "target_check", "passed": false, "detail": "<reasons>"}`. (A precheck that printed no JSON, or crashed, is also a
failure: the job is not executed; if the job file itself is unreadable, write `ROOT/jobs/failed/<job id>.note.txt` and file
the job as failed. If a result already exists, `write_result` refuses to overwrite it: write `BASE/jobs/<job id>.refused.note.txt` with the reasons instead.) After an `"ok": true`: create the work folder and the notes file
(`mkdir -p BASE/work/ID BASE/jobs`; first line `<UTC time> started`, then the `target` and `skeleton_design_id` it compared).
After every finished phase append one line to the notes:
`echo "$(date -u +%FT%TZ) <phase>: <ids, counts, file names>" >> BASE/jobs/ID.notes.md`. A "target check" that approves is also a claim: print the two ids it compared
(`target`, `skeleton_design_id`) in your reply to the owner.

### 1.4 Follow the instruction for the type

Read `SKILL_DIR/jobs/<type>.md` completely, then execute it step by step (`map_skeleton`, `style_directions`,
`write_texts`, `apply_canva`, `verify`). Also read, completely, the files it names. The job's `limits` strings (Ukrainian)
repeat the hard limits above; if a `limits` entry forbids something the instruction asks for, the stricter wins.

### 1.5 Write the result

Result format (exact; `write_result` rejects anything else):

```json
{"status": "done" | "failed",
 "summary": "<Ukrainian, 1-4 sentences: what was done and what is not verified>",
 "outputs": {},
 "checks": [{"name": "<short id>", "passed": true, "detail": "<numbers, ids, what was compared>"}]}
```

Write the draft with the Write tool to `BASE/work/ID/result.draft.json`, then validate and store it
atomically (temp file + rename) with the snippet. It also enforces per type: `apply_canva` done needs
`outputs.canva_copy_id` equal to the one in `state.json` AND every check passed (the studio treats a done apply
without a recorded copy id as failed, R19); `style_directions` done needs 2-3 directions, each valid against the map;
`write_texts` done needs a valid `texts.json`; `map_skeleton` done needs a valid `map.json`. If it asserts,
fix the draft; if you cannot, set `status` to `failed` and say why. If the result folder does not exist (unknown
template), write `ROOT/jobs/failed/<job id>.note.txt` instead. The snippet NEVER overwrites an existing result file (it exits non-zero
with a clear message): then write `BASE/jobs/<job id>.refused.note.txt` (Ukrainian, what you would have written) and file the job by the
existing result's `status`.

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "$CODE" "$ROOT" "$ROOT/jobs/running/$ID.json" "$BASE/work/$ID/result.draft.json" <<'PYEOF'
# snippet: write_result
import dataclasses
import json
import sys
from pathlib import Path

CODE, ROOT, JOB, DRAFT = (Path(a).resolve() for a in sys.argv[1:5])   # code folder, data root, job file, draft result
sys.path.insert(0, str(CODE))
from app import schema, texts
from app.config import load_config
from app.store import read_json, skeleton_dir, template_dir, write_json_atomic

cfg = dataclasses.replace(load_config(ROOT / "config.json"), root=ROOT)
job, draft = read_json(JOB), json.loads(DRAFT.read_text(encoding="utf-8"))
assert set(draft) == {"status", "summary", "outputs", "checks"}, f"keys must be exactly status, summary, outputs, checks: {sorted(draft)}"
assert draft["status"] in ("done", "failed"), "status must be done or failed"
assert isinstance(draft["summary"], str) and draft["summary"].strip(), "summary must be a non-empty string (Ukrainian)"
assert isinstance(draft["outputs"], dict), "outputs must be an object"
assert isinstance(draft["checks"], list) and all(
    isinstance(c, dict) and set(c) == {"name", "passed", "detail"} and isinstance(c["name"], str) and c["name"]
    and isinstance(c["passed"], bool) and isinstance(c["detail"], str) for c in draft["checks"]), "bad checks entry"
jtype, ok = job["type"], draft["status"] == "done"
sdir = skeleton_dir(cfg, job["skeleton"])
tdir = template_dir(cfg, job["template"]) if job.get("template") else None
base = sdir if jtype == "map_skeleton" else tdir
assert base is not None and base.is_dir(), f"folder for the result does not exist: {base}"
if ok and jtype == "apply_canva":                     # a done apply without a recorded copy id counts as failed (R19)
    state = read_json(tdir / "state.json")
    assert state.get("canva_copy_id") and draft["outputs"].get("canva_copy_id") == state["canva_copy_id"], \
        "done apply_canva needs outputs.canva_copy_id equal to state.json canva_copy_id"
    assert draft["checks"] and all(c["passed"] for c in draft["checks"]), "done apply_canva needs every check passed"
if ok and jtype == "style_directions":
    m, dirs = read_json(sdir / "map.json"), draft["outputs"].get("directions")
    assert isinstance(dirs, list) and 2 <= len(dirs) <= 3, "outputs.directions must hold 2-3 directions"
    for d in dirs:
        assert isinstance(d.get("name"), str) and d["name"].strip() and isinstance(d.get("description"), str) and d["description"].strip(), "direction needs name and description"
        assert schema.validate_style(d, m) == [], f"direction {d.get('name')!r}: {schema.validate_style(d, m)}"
if ok and jtype == "write_texts":
    m, written = read_json(sdir / "map.json"), read_json(tdir / "texts.json")
    assert texts.validate_texts(written, m) == [], texts.validate_texts(written, m)
if ok and jtype == "map_skeleton":
    problems = schema.validate_map(read_json(sdir / "map.json"))
    assert problems == [], problems
dest = base / "jobs" / f"{job['id']}.result.json"
if "--validate-only" in sys.argv[5:]:                  # the draft IS an existing result file: validate it, write nothing
    print(f"valid: {draft['status']}, {len(draft['checks'])} checks")
    sys.exit(0)
assert not dest.exists(), f"{dest} already exists: a result is never overwritten (write <id>.refused.note.txt and file the job by that result)"
write_json_atomic(dest, draft)                        # temp file + rename
print(f"wrote {dest}: status {draft['status']}, {len(draft['checks'])} checks, {sum(not c['passed'] for c in draft['checks'])} failed")
PYEOF
```

Honesty rules for `summary`, `detail`, notes: say what was verified and how; keep the word "unverified" for anything
that was only read, not run; never write "done" for something whose check did not run. A check that examined nothing
is a failed check. Numbers are recomputed, not remembered.

### 1.6 File the job

`done` iff the result's `status` is `done`, else `failed`:

```bash
ROOT=...; ID=<job id>; TO=done   # or failed
cd "$ROOT/jobs" && mv -n "running/$ID.json" "$TO/$ID.json" && test -e "$TO/$ID.json" && test ! -e "running/$ID.json" && echo filed
```

Never touch the step statuses in `state.json`: the studio derives them from the result files. `state.json` is written
by you in exactly one place: `canva_copy_id` (apply_canva, snippet below).

### 1.7 Tell the owner

Ukrainian, short: job id, type, status, the summary, the failed checks with numbers, the design link
`https://www.canva.com/design/<canva_copy_id>/edit` for Canva jobs, and the `target` / `skeleton_design_id` pair the
precheck compared. Remind the owner to refresh the studio page. Everything the owner must do (manual steps, answers)
goes in one closing block at the very end of the reply, in this exact form (omit it when nothing is needed):

```
> 👉 **Від вас потрібно**
> **Зараз** — робота чекає на це:
> 1. <verb first: what to do and where> — <why>.
> **Коли зручно:**
> 2. <what to do and where> — <why>.
```

## 2. Failure handling

- Two identical failures of one connector call → stop, note, `failed/` (hard limit 8). A different call may be tried.
- A connector result that is saved to a file instead of shown: use that path. A result shown inline that a script
  needs: save it to `BASE/work/ID/` byte for byte with the Write tool (never retype or summarise JSON).
- A check script reports a control failure (`CONTROL FAILED`) → the instrument is broken, not the design: stop, note,
  `failed/`; never report its green/red as a result.
- Sign-in page, missing browser, lost connector: stop and ask the owner in chat; if the owner cannot help now, `failed/`
  with that reason (a failed job costs nothing; a guess can destroy a design).
- Anything you did not run is "unverified" in the result, never a pass.

## 3. Snippets used by the job instructions

Run each exactly as written, replacing only the angle-bracket arguments. Do not edit the code.

**Record the Canva copy id (apply_canva, right after `copy-design`)** — one short call, read-modify-write of
`state.json` under the studio's lock (`app.store.STATE_LOCK`; note: the lock is per process, so keep the call short and
never combine it with other work). It changes only `canva_copy_id`, and refuses a protected or skeleton id.

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "$CODE" "$ROOT" "<template>" "<new design id>" <<'PYEOF'
# snippet: set_copy_id
import dataclasses
import sys
from pathlib import Path

CODE, ROOT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
TEMPLATE, COPY_ID = sys.argv[3], sys.argv[4]
sys.path.insert(0, str(CODE))
from app.config import load_config
from app.store import STATE_LOCK, read_json, skeleton_dir, template_dir, write_json_atomic

cfg = dataclasses.replace(load_config(ROOT / "config.json"), root=ROOT)
with STATE_LOCK:
    path = template_dir(cfg, TEMPLATE) / "state.json"
    state = read_json(path)                                  # read fresh, change one key, write back at once
    skeleton_id = read_json(skeleton_dir(cfg, state["skeleton"]) / "map.json").get("design_id") \
        if (skeleton_dir(cfg, state["skeleton"]) / "map.json").is_file() \
        else read_json(skeleton_dir(cfg, state["skeleton"]) / "skeleton.json")["design_id"]
    protected = {i.casefold() for i in cfg.forbidden_design_ids} | {"daharqlqips", skeleton_id.casefold()}
    assert COPY_ID.casefold() not in protected, f"{COPY_ID} is the skeleton or a protected original: never record it"
    assert state.get("canva_copy_id") in (None, COPY_ID), f"state already holds {state.get('canva_copy_id')}"
    state["canva_copy_id"] = COPY_ID
    write_json_atomic(path, state)                           # temp file + rename
print("canva_copy_id =", read_json(path)["canva_copy_id"])
PYEOF
```

**Turn a `final_check.py` / similar report into result checks** (`PASS name: detail` lines → checks JSON):

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "<report.txt>" "<checks.json>" <<'PYEOF'
# snippet: to_checks
import json
import re
import sys
from pathlib import Path

checks = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    mt = re.match(r"(PASS|FAIL) ([^:]+): (.*)$", line)
    if mt:
        checks.append({"name": mt.group(2), "passed": mt.group(1) == "PASS", "detail": mt.group(3)})
assert checks, "no PASS/FAIL lines found in the report"
Path(sys.argv[2]).write_text(json.dumps(checks, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(checks)} checks, {sum(not c['passed'] for c in checks)} failed -> {sys.argv[2]}")
PYEOF
```

**No old picture left** (search the written design for every media id of the skeleton, control = the same search on the
untouched original; protected elements may keep theirs):

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "$CODE" "<map.json>" "<facts_orig.json>" "<facts_now.json>" <<'PYEOF'
# snippet: old_media
import json
import sys
from pathlib import Path

CODE = sys.argv[1]
sys.path.insert(0, CODE)
from canva.protected import protected_members

m, orig, now = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:5])


def media_of(rec):
    out = []
    if (rec.get("background") or {}).get("media"):
        out.append(rec["background"]["media"])
    if (rec.get("fill") or {}).get("media"):
        out.append(rec["fill"]["media"])
    out += [p["fill"]["media"] for p in rec.get("paths", []) if (p.get("fill") or {}).get("media")]
    return out


old = {mid for rec in orig.values() for mid in media_of(rec)}
prot = set(protected_members(orig, m))          # protected pictures may legitimately keep the old media


def leftovers(design, skip):
    return sorted(f"{loc} still shows {mid}" for loc, rec in design.items() if loc not in skip
                  for mid in media_of(rec) if mid in old)


found = leftovers(now, prot)
control = leftovers(orig, set())                # the untouched original MUST be reported: proves the search can find
ok_control = bool(old) and bool(control)
check = {"name": "old_media", "passed": ok_control and not found,
         "detail": (f"{len(old)} media ids of the skeleton searched; {len(found)} left outside protected elements"
                    + ("" if not found else ": " + "; ".join(found[:5]))
                    + f"; control on the untouched original found {len(control)}"
                    + ("" if ok_control else " - CONTROL FAILED, the search proves nothing"))}
print(json.dumps(check, ensure_ascii=False))
sys.exit(0 if check["passed"] else 1)
PYEOF
```

**Cut an exported page into slices** (at most 1400 px high and 1568 px wide, safe to look at):

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "<page.png>" "<out folder>" <<'PYEOF'
# snippet: slice
import sys
from pathlib import Path

from PIL import Image

src, out = Path(sys.argv[1]), Path(sys.argv[2])          # one exported page png -> slices of at most 1400 px high
out.mkdir(parents=True, exist_ok=True)
im = Image.open(src).convert("RGB")
if im.width > 1568:                                       # never show an image wider than 1568 px
    im = im.resize((1568, round(im.height * 1568 / im.width)), Image.LANCZOS)
names = []
for n, y in enumerate(range(0, im.height, 1400)):
    names.append(out / f"{src.stem}_{n:02d}.png")
    im.crop((0, y, im.width, min(y + 1400, im.height))).save(names[-1])
print(f"{src.name}: {im.width}x{im.height} -> {len(names)} slices in {out}")
PYEOF
```

**Check a skeleton map against the design's facts** (map_skeleton, apply_canva; exit 0 required): `validate_map` clean, every
slot exists with the right element type, `original` equals the design's text, no role still `unassigned`, no draft key left,
every text is a slot / protected / `keep`, the map's pages are the design's pages:

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "$CODE" "<map.json>" "<facts.json>" <<'PYEOF'
# snippet: map_check
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from app.schema import validate_map
from canva.ops import uncovered_texts

m, facts = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:4])
problems = [f"map: {p}" for p in validate_map(m)]
KINDS = {"text": {"text"}, "table_cell": {"cell"}, "colour": {"rect", "shape", "line", "section"},
         "image": {"section", "rect", "shape"}}
for s in m["slots"]:
    rec = facts.get(s["locator"])
    if rec is None:
        problems.append(f"slot {s['locator']}: no such element in the facts")
    elif rec["type"] not in KINDS[s["type"]]:
        problems.append(f"slot {s['locator']}: a {s['type']} slot points at a {rec['type']}")
    elif s["type"] in ("text", "table_cell") and s.get("original") not in (None, rec.get("text")):
        problems.append(f"slot {s['locator']}: original {s.get('original')!r} differs from the design's text {rec.get('text')!r}")
    if s["type"] == "text" and s.get("max_len") is not None and not isinstance(s["max_len"], int):
        problems.append(f"slot {s['locator']}: max_len must be an integer or null")
problems += [f"slot {s['locator']}: role is still 'unassigned'" for s in m["slots"] if s.get("role") in (None, "", "unassigned")]
problems += [f"asset {a}: role is still 'unassigned'" for a, v in m["assets"].items() if v.get("role") in (None, "", "unassigned")]
problems += [f"leftover draft key {k}" for k in m if k.startswith("_")]
for p in m["protected"] + m.get("keep", []):
    if p not in facts:
        problems.append(f"protected/keep {p}: no such element in the facts")
unc = uncovered_texts(facts, m)
problems += [f"uncovered text {k}: not a slot, not protected, not in keep" for k in unc]
pages = {r["page"] for r in facts.values()}
if pages != {p["id"] for p in m["pages"]}:
    problems.append(f"map pages {sorted(p['id'] for p in m['pages'])} differ from the design's pages {sorted(pages)}")
n_text = sum(1 for r in facts.values() if r["type"] in ("text", "cell"))
print(json.dumps({"slots": len(m["slots"]), "text_records": n_text, "uncovered": len(unc), "problems": problems[:20],
                  "n_problems": len(problems)}, ensure_ascii=False))
sys.exit(1 if problems else 0)
PYEOF
```

**Judge the formatting with the declared text-fit size changes reset** (apply_canva step 10.3, verify step 2): writes the facts with
ONLY the declared sizes reset and prints the check `font_size_changes` (passed iff the sizes that differ from the skeleton are
exactly the declared locators; control: with an empty declared list any changed size fails):

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "<facts_orig.json>" "<facts_final.json>" "<declared.json>" "<facts_adjusted.json>" <<'PYEOF'
# snippet: adjust_sizes
import copy
import json
import sys
from pathlib import Path

# usage: adjust_sizes.py <facts_orig> <facts_final> <declared.json = list of locators> <out adjusted facts>
orig, final = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:3])
declared = set(json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")))


def sizes(rec):
    return sorted({r.get("fontSize") for r in rec.get("regions", [])}, key=str)


changed = {loc for loc, rec in final.items() if rec.get("type") in ("text", "cell") and loc in orig and sizes(rec) != sizes(orig[loc])}
undeclared, unused = sorted(changed - declared), sorted(declared - changed)
adjusted = copy.deepcopy(final)
for loc in changed & declared:                       # reset ONLY the declared size changes, so final_check can judge the rest
    first = orig[loc]["regions"][0]["fontSize"]
    for r in adjusted[loc]["regions"]:
        r["fontSize"] = first
Path(sys.argv[4]).write_text(json.dumps(adjusted, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
check = {"name": "font_size_changes", "passed": not undeclared and not unused,
         "detail": f"{len(changed)} text sizes differ from the skeleton, {len(declared)} declared; undeclared {undeclared[:5]}; "
                   f"declared but unchanged {unused[:5]}; final_check was run on the facts with the declared sizes reset"}
print(json.dumps(check, ensure_ascii=False))
sys.exit(0 if check["passed"] else 1)
PYEOF
```
