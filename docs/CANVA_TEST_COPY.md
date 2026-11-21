# Getting your own Canva test copy (instructions for Claude)

A Canva design is not a file: it lives in a Canva account and cannot be stored in this repository. The connector can
export the test copy only as PDF/JPG/PNG (all pages) and PPTX/GIF/MP4 (page 4 only) — checked with `get-export-formats`
on 2026-11-21 — and none of these round-trips back into an editable website with sections, the envelope animation, the
RSVP form, embeds and button links. `import-design-from-url` also needs a public URL, and a private design must not be
put on public hosting. The design is also a copy of a purchased template, so its content is not redistributed.

So the test copy travels through Canva itself: the owner shares it, and your Claude session makes **your own** copy with
the connector, checks that its structure matches the snapshot in this repository, and registers it in the studio as the
development skeleton (PLAN Task 13).

## What the repository already has

- `tests/fixtures/facts_orig.json` — a structural snapshot (one record per element and table cell, keyed by the
  connector's `locator_id`) of an untouched copy of the Ivory Lace template, taken on 2026-11-12.
- `docs/reference/BLUEPRINT.md` — the analysis of the template's structure.

Copies keep the element ids of their source (verified on 11–12 November 2026, `DESIGN.md` §3), so the locators of a fresh
copy are expected to match the snapshot. That expectation is **unverified for your copy** until step 5 runs.

## Rules for this procedure

- `DAHarqlqips` (the purchased original) is never read for editing, copied or written. It is in `forbidden_design_ids`.
- The owner's `DAHason1g_M` is only **read** and **copied** here — never edited. Your copy is yours to experiment on.
- `copy-design` creates a new design in the Canva account of the connector that runs it (yours). Ask the developer
  before calling it.
- The only `edit-design` call allowed in this procedure is `finalize: "cancel"` with no operations (to close the read
  transaction). Nothing is deleted.
- Load the Canva tools with ToolSearch before first use (they are deferred tools). Every call passes `user_intent`.

## Steps

### 1. Preconditions

- The owner has shared `DAHason1g_M` with the developer's Canva account (Share → e-mail → Can edit).
- The developer's own Canva connector is connected in Claude (docs/ONBOARDING.md §1).
- `config.json` exists (README, Setup) and its `forbidden_design_ids` still contains `DAHarqlqips`.

### 2. Confirm access (read-only)

`read-design` with `design_id: "DAHason1g_M"`, `filter: {"fields": ["design_metadata", "page_metadata"]}` (no
transaction). Expected: the title starts with "TEST COPY - Ivory Lace" and the design is a website with 3 pages.
If the call fails with no access, stop and tell the developer to ask the owner to share it.

### 3. Make your copy (creates a design — ask first)

After the developer agrees: `copy-design` with `design_id: "DAHason1g_M"` (all pages: omit `page_numbers`).
Write down the returned id (`D…`, 11 characters) — below it is `<COPY>`. Tell the developer the id and the title.

### 4. Read the copy's structure and dump facts

`read-design` with `design_id: "<COPY>"`, `open_transaction: true`, `filter: {"fields": ["design_content"]}` — the only
way to get element ids and positions. The tool saves a big result to a file itself; note that path (`<READ_JSON>`).
**Immediately** close the transaction: `edit-design` with that `transaction_id` and `finalize: "cancel"`, no operations.

Then, from the repo root (`$PY` is the `python` key of `config.json`; keep the work files outside git, e.g. under the
studio's data root):

```bash
PY=$(python3 -c "import json;print(json.load(open('config.json'))['python'])")
W="$(python3 -c "import json;print(json.load(open('config.json'))['root'])")/work/test-copy"; mkdir -p "$W"
cp -n "<READ_JSON>" "$W/read.json"
$PY -I canva/facts.py dump "$W/read.json" "$W/facts.json"
$PY -I canva/outline.py "$W/read.json" "$W/outline.txt"
```

### 5. Compare with the snapshot (with a control)

```bash
$PY -I - "$W/facts.json" tests/fixtures/facts_orig.json <<'PY'
import json, sys
copy = set(json.load(open(sys.argv[1]))); snap = set(json.load(open(sys.argv[2])))
def diff(a, b):
    return sorted(a - b), sorted(b - a)
# control: the same comparison must notice one missing locator
probe = set(snap); probe.discard(next(iter(snap)))
assert diff(probe, snap) == ([], [next(iter(snap - probe))]), "comparison is blind"
only_copy, only_snap = diff(copy, snap)
print(f"copy={len(copy)} snapshot={len(snap)} only_in_copy={len(only_copy)} only_in_snapshot={len(only_snap)}")
for k in only_copy[:20]: print("  + copy  ", k)
for k in only_snap[:20]: print("  - snap  ", k)
PY
```

Expected: `only_in_copy=0 only_in_snapshot=0`. Values (texts, boxes) may differ slightly, because the owner's test copy
had probe edits on 12 November that were restored — compare values only if a later step needs them
(`canva/facts.py diff "$W/facts.json" tests/fixtures/facts_orig.json "$W/diff.txt"`).
If locators differ, **do not** edit the fixture to make them match: report the counts and the first lines to the
developer and the owner. A differing structure means this copy is not the skeleton the studio was built on.

### 6. Register the copy as the development skeleton

Start the studio (`./run.sh` in the developer's own Terminal), then:

```bash
curl -s -X POST http://127.0.0.1:8765/api/skeletons \
  -H 'Content-Type: application/json' \
  -d '{"name": "probe", "design_id": "<COPY>"}'
```

The studio answers with a `map_skeleton` job in `jobs/pending/`. The developer types `/test-canva-studio` to run it
(the job only reads the design). From then on `<COPY>` is a skeleton: the guard refuses it as a write target, and every
template gets its own fresh copy of it (PLAN Task 13).

### 7. Report

Tell the developer: the copy's id and title, the step 5 counts, and that the skeleton `probe` is registered. Do not put
the copy's id in committed files unless the owner asks; it lives in `skeletons/probe/skeleton.json` (not in git).
