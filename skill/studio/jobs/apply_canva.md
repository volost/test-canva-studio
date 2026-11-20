# apply_canva — write one style into a NEW copy of the skeleton

You arrive here from SKILL.md step 1.4: the job is in `jobs/running/`, the precheck printed `"ok": true`, `ROOT`,
`CODE`, `PY`, `BASE` (= `ROOT/templates/<t>`), `ID` (job id), `W` (= `BASE/work/ID`) are as defined there.

## HARD LIMITS (verbatim from SKILL.md; the job's `limits` repeat them)

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
10. One job per `/studio`. One writer per design: never run a second Canva job while another is in `running/`.

The owner approved this write by pressing «Записати в Canva»; that approval covers committing to THE TEMPLATE'S OWN
COPY ONLY. There is nothing else to ask the owner before the risky steps below.

## What you read first (completely)

1. The job file `ROOT/jobs/running/ID.json`: `inputs` = `map_file`, `style_file`, `texts_file`, `manifest_file`
   (paths relative to `ROOT`), `chosen` ({asset: file}), `texts` ({locator: text}); `target_design_id` is null on the
   first run (copy not yet made) or the copy's id on a re-run.
2. The files those paths name, plus `BASE/state.json`.
3. PLAYBOOK §4 (connector behaviour) and §5 Phases 4-6 (`/Users/volost/GitRepos/canva/handoff/PLAYBOOK.md`); SPEC §7
   (`/Users/volost/GitRepos/canva/study/sage-linen/SPEC.md`): configurability rules and the §7.4 stress test.
4. The Python scripts' own `--help` text is their module docstring: run a script with no arguments to print it.

Connector facts that matter here (PLAYBOOK §4): `update_fill` leaves the picture box ~11 px too big, so every fill is
followed by `crop_media` to the cover box (`ops.py images` writes both in one call); results of a big page are saved
to a file, not shown; `replace_text` keeps the font and the box grows downward while neighbours do not move; the
connector cannot choose fonts; pages with sections have no thumbnails (commit, export, slice to look).

## Conventions in this instruction

- Every Bash command starts with the variables (shell state does not persist):
  `ROOT=<studio root>; CODE=/Users/volost/GitRepos/canva/studio; PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python; T=<template>; S=<skeleton>; ID=<job id>; BASE="$ROOT/templates/$T"; W="$BASE/work/$ID"`.
  `$W/...` below always means a file in this job's work folder. `D` is the copy's design id (after step 2).

- A "call" = one `edit-design` call. Operation files `*.json` written by `ops.py` hold
  `{"page_index": n, "operations": [...]}`: send EXACTLY that `page_index` and that `operations` array (copy the file
  content, never retype), with `transaction_id`, `finalize: "keep_open"`, `is_editable: true`, `is_responsive: false`.
- Every call ends with the same four actions (call them **VERIFY-CALL**), BEFORE the next call:
  1. save the edit result to `$W/edit_<nn>.json` (the tool saves big results itself; use that path);
  2. `cd "$CODE" && $PY -I canva/facts.py dump $W/edit_<nn>.json $W/page_<nn>.json` then
     `$PY -I canva/facts.py merge $W/facts_cur.json $W/page_<nn>.json $W/facts_new.json`;
  3. `$PY -I canva/ops.py verify $W/facts_cur.json $W/facts_new.json <the operation file> $W/verify_<nn>.txt`
     — exit 0 required. It runs its own control first; `CONTROL FAILED` = the instrument is broken → stop (SKILL §2).
     Findings = something nothing asked for changed, or an operation did not show its effect;
  4. status check: `$PY -I -c 'import json,sys,collections; r=json.load(open(sys.argv[1])); o=r["edit_operation_results"]; print(len(o), collections.Counter(x.get("status") for x in o))' $W/edit_<nn>.json`
     — the count must equal the number of operations sent and no status may read error / failed / rejected / skipped.
  Then `cp $W/facts_new.json $W/facts_cur.json` (cp over your own work file is fine) and append a note line.
  If a VERIFY-CALL finds anything you cannot explain with a verified mechanism: `edit-design` with
  `finalize: "cancel"` (discards the whole open draft), open a new transaction (step 3), rebuild the operation files
  (`ops.py build` emits only differences, so already-committed work is not repeated) and try once more; the same
  finding twice → stop, `failed/`.
- Commit = `edit-design` with `finalize: "commit"` and no operations. It saves permanently. After a commit open a new
  transaction (`read-design` with `open_transaction: true`) for the next phase. "Open transaction" always means:
  `read-design`, `design_id` = the copy, `open_transaction: true`, `filter: {"fields": ["design_content"]}`; it
  returns the `transaction_id` (save the design content to a file; `facts.py dump` it; if `dump` says the file is not a read-design result, look at the file's top-level keys and tell the owner - never hand-convert).
- A transaction that is not needed any more is ended with `finalize: "cancel"`, never left open.
- Add to the notes after each phase: phase name, call count, operation count, findings.

## Steps

### 1. Validate the inputs (no Canva call yet)

```bash
ROOT=...; CODE=...; PY=...; ID=...; T=<template>; S=<skeleton>
cd "$CODE" && $PY -I -c 'import sys,json; sys.path.insert(0,sys.argv[1]); from app import schema, texts as T; R=sys.argv[2]; t=sys.argv[3]; s=sys.argv[4]; L=lambda p: json.load(open(p,encoding="utf-8")); m=L(f"{R}/skeletons/{s}/map.json"); st=L(f"{R}/templates/{t}/style.json"); tx=L(f"{R}/templates/{t}/texts.json"); mf=L(f"{R}/templates/{t}/assets/manifest.json"); p=[*schema.validate_map(m), *schema.validate_style(st,m), *T.validate_texts(tx,m)]; p+= [f"asset {a} has no manifest entry" for a in m["assets"] if a not in mf["assets"]]; print(len(m["slots"]),"slots,",len(tx),"texts,",len(m["assets"]),"assets;",p); sys.exit(1 if p else 0)' "$CODE" "$ROOT" "$T" "$S"
```

Exit 0 required (the three validators return `[]`, every map asset has a manifest entry). Otherwise `failed/`: the data
the owner approved is not valid. Check the map has a colour slot with role `calendar_marker`
(`grep -c calendar_marker "$ROOT/skeletons/$S/map.json"` ≥ 1); without it step 6 cannot be done honestly → `failed/`
with that reason (the owner adds the role on the skeleton screen).

### 2. The copy (skip `copy-design` when `state.json` already holds `canva_copy_id` or the notes record a copy id)

If the notes record a copy id but `state.json` does not (the earlier run stopped between the two): do NOT copy again;
run the `set_copy_id` snippet with the noted id (item 2 below), then go on with `D` = that id.

1. `copy-design` with `design_id` = the skeleton's design id (`map.json` `design_id`; copy-design leaves the source
   unchanged) and `user_intent`. Do not pass `page_numbers` (copy every page). It returns the new design id.
2. IMMEDIATELY, before anything else: append the id to the notes
   (`echo "$(date -u +%FT%TZ) copy-design returned <id>" >> BASE/jobs/ID.notes.md`), then record it in `state.json`
   with the `set_copy_id` snippet (SKILL.md §3; arguments `"$CODE" "$ROOT" "<template>" "<new design id>"`). It refuses the
   skeleton's id and any protected id. Read the printed `canva_copy_id`.
   Never call `copy-design` a second time for this job: if the snippet fails, retry it once; if it still fails, stop,
   result `failed` with the new design id named in the `summary` (an unrecorded copy is a cost the owner must know).
3. From now on `D` = the copy's id. Every later Canva call uses `D` and nothing else.

### 3. Baseline facts (before any edit)

1. Open a transaction on `D` (see Conventions). `cd "$CODE"`; `$PY -I canva/facts.py dump <design content file> $W/facts_start.json`;
   `$PY -I canva/outline.py <design content file> $W/outline_start.txt`. Copy it: `cp $W/facts_start.json $W/facts_cur.json`.
2. Pages: the design's page ids must equal the map's page ids (`map_check` below does this); otherwise the map is
   for another design → cancel the transaction, `failed/`.
3. Baseline of "what the skeleton looked like": `BASE/facts_orig.json`.
   - first run (the file does not exist): the copy is still unedited, so `facts_start.json` IS the baseline:
     `cp -n $W/facts_start.json "$BASE/facts_orig.json"`. Also compare with the skeleton's own facts from map_skeleton:
     `$PY -I canva/facts.py diff "$ROOT/skeletons/$S/facts.json" $W/facts_start.json $W/diff_skeleton.txt` (if that file exists);
     the last line shows `differing=N`. N > 0 is not fatal (the baseline stays the fresh copy) but is reported as a
     check `copy_matches_skeleton` with the number.
   - re-run (the file exists): use it; do NOT replace it (the copy is already edited).
   - copy already edited and no `facts_orig.json`: fall back to `skeletons/<s>/facts.json`; if that is missing too,
     read the SKELETON once (`read-design` with `open_transaction: true`, dump, then `edit-design` with
     `finalize: "cancel"` and no operations) and use that dump. Hard limit 2: never edit or commit there.
   - `cp -n $W/... $W/facts_orig.json` so the work folder holds the baseline too.
4. Map against the baseline (exit 0 required: every slot exists with the right element type, every text is a slot /
   protected / `keep`, the map's pages are the design's pages):

   the `map_check` snippet (SKILL.md §3), arguments `"$CODE" "$ROOT/skeletons/$S/map.json" "$BASE/facts_orig.json"`.

   Then the protected self-check (its control fails on an unknown protected locator, i.e. a map that does not belong
   to this design):

```bash
cd "$CODE" && $PY -I canva/protected.py "$ROOT/skeletons/$S/map.json" "$BASE/facts_orig.json" "$BASE/facts_orig.json" "$W/protected_selfcheck.txt"
```

### 4. Phase A — colours and texts (PLAYBOOK Phase 4)

1. `cd "$CODE" && $PY -I canva/ops.py build "$ROOT/skeletons/$S/map.json" "$BASE/style.json" "$BASE/texts.json" $W/facts_cur.json $W/ops`
   → `$W/ops/ops_<page id>_<nn>.json` (at most 60 operations and 26 `update_fill` per call; one element's
   operations never split; protected locators never get an operation) and `$W/ops/ops_notes.txt`.
   `OpsError` (stale map, wrong design, role without a colour) → `failed/`, EXCEPT the message `the design holds '<text>', the map
   expects '<original>'`: the design already carries earlier written texts (a re-apply after the owner changed texts) and
   `ops.py` refuses a text that is neither the skeleton's original nor the new one. Workaround, for building only: run the snippet
   below, then run the same `ops.py build` command with `$W/facts_for_build.json` instead of `$W/facts_cur.json`. It emits every
   `replace_text` / colour operation; the verification still uses the real facts.

```bash
PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python; CODE=/Users/volost/GitRepos/canva/studio; ROOT=<studio root>
$PY -I - "$ROOT/skeletons/$S/map.json" "$W/facts_cur.json" "$BASE/facts_orig.json" "$W/facts_for_build.json" <<'PYEOF'
# snippet: reset_texts
import copy
import json
import sys
from pathlib import Path

# usage: reset_texts.py <map.json> <facts_cur.json> <facts_orig.json> <out facts_for_build.json>
m, cur, orig = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:4])
prot = set(m["protected"])
out, n = copy.deepcopy(cur), 0
for s in m["slots"]:
    loc = s["locator"]
    if s["type"] in ("text", "table_cell") and loc not in prot and loc in cur and loc in orig:
        out[loc]["text"], out[loc]["regions"] = orig[loc]["text"], copy.deepcopy(orig[loc]["regions"])
        n += 1
Path(sys.argv[4]).write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print(f"{n} text/cell records reset to the skeleton's wording and formatting (for ops.py build ONLY) -> {sys.argv[4]}")
PYEOF
```

   Read `ops_notes.txt` completely; copy its
   lines about kept colour roles, unmapped texts and skipped section colours into the result `summary`/notes.
2. Send the files in name order (`ls $W/ops/ops_P*.json | sort`), one call each, VERIFY-CALL after each.
3. Commit. Open a new transaction; dump → `$W/facts_cur.json` (a fresh read replaces the merged one).
4. Whole-design check:
   `$PY -I canva/final_check.py "$ROOT/skeletons/$S/map.json" "$BASE/texts.json" "$BASE/facts_orig.json" $W/facts_cur.json $W/final_A.txt --style "$BASE/style.json"`
   Exit 0 required: texts, formatting, colours, protected, coverage, structure, leftovers and its own control. Fix
   what it names (re-run step 4.1 on the fresh facts; it emits only what still differs), then re-check. A `coverage`
   failure is a map defect (a text that is neither slot, protected nor `keep`): `failed/` with the locators.

### 5. Phase B — layout: fit the words to the phone column (PLAYBOOK pass 1b, SPEC §7.3)

1. `$PY -I canva/layout.py "$BASE/facts_orig.json" $W/facts_cur.json $W/layout_A.txt` — it runs its own self-test. Read the
   report: `AXIS` (centre moved), `OVERLAP` (neighbour overlap grew), `COLUMN` (text left its phone column),
   `size` lines (information: box height/width and estimated line count before → after).
2. Single-line personal text fields (map slots: `type` text, `personal` true, `max_len` an integer) whose box is
   centre-aligned (`regions[0].align == "center"`) get a box as wide as the section's phone column (`column_px`
   of the slot), keeping the box's current centre x, except: when that centre is within 6 px of the section's centre (section width / 2; 683
   on a 1366 section, SPEC §7.3) centre it exactly there and list the locator in `outputs.recentred` (the Sage run did this; `layout.py`
   reports such a shift as `AXIS`). Skip boxes already that wide (±0.5 px). Write the batch yourself, one element after the other:
   `{"type": "resize_element", "locator_id": L, "width": column_px}` then
   `{"type": "position_element", "locator_id": L, "top": <current top>, "left": <centre_x - column_px/2>}`
   (text: give only `width`; height is automatic). File `$W/layout_01.json` (same shape as the `ops` files, ≤ 60
   operations per call, one per page; page_index from the map). Send and VERIFY-CALL each. On Sage this was about
   19 boxes.
3. Re-run `layout.py` on the fresh facts. Remaining `OVERLAP` / `COLUMN` lines, and `AXIS` lines you did not cause by the deliberate re-centring of step 2, must be fixed by moving or
   widening ONLY the offending text box (`position_element` / `resize_element`); a text that still does not fit may
   have its size reduced by 1-2 px steps with `format_text` `{"font_size": n}` as the LAST resort (about 5 of the 19 on
   Sage). The words themselves are never changed (the owner approved them). Every size change is "declared": list
   it as `{"locator", "from", "to"}` in `outputs.font_size_changes` and in the notes; step 10.3 judges the rest of the formatting
   with exactly these sizes reset, and fails when any other size moved.
   Anything left that you cannot fix → check `layout` failed with the lines.
4. Commit. Open a new transaction; dump → `$W/facts_cur.json`; `layout.py` once more → `$W/layout_B.txt`. Check `layout` passes iff the
   report has no `OVERLAP`, `COLUMN` or `NEW TEXT` line AND every `AXIS` line names a locator you re-centred on purpose
   (listed in `outputs.recentred`, shift ≤ 6 px). `grep -cE '^(OVERLAP|COLUMN|NEW TEXT) ' $W/layout_B.txt` must print 0 (a grep that
   finds nothing is a claim about the grep: run it once on a line you know is there, e.g. with `'^size '`, and it must print > 0).
   Put the counts in `detail`.

### 6. The calendar marker (heart) onto the new date

The scripts only recolour the marker; moving it is yours. The date: take the newest `BASE/jobs/*-write_texts.result.json`
with `"status": "done"` and read `outputs.calendar_marker_cell` (a table-cell locator) and `outputs.sample_data`.
Missing → check `calendar_marker` failed ("write_texts result has no calendar_marker_cell"), do not guess.
The marker element is the map's colour slot with role `calendar_marker`.

```bash
PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python; CODE=/Users/volost/GitRepos/canva/studio; ROOT=<studio root>
$PY -I - "$CODE" "$ROOT/skeletons/$S/map.json" "$BASE/facts_orig.json" "$W/facts_cur.json" "<marker locator>" "<cell locator>" "$W/marker_01.json" <<'PYEOF'
# snippet: marker
import json
import re
import sys
from pathlib import Path

CODE = sys.argv[1]
sys.path.insert(0, CODE)
from canva.maputil import page_index

# usage: marker.py <map.json> <facts_orig.json> <facts_now.json> <marker locator> <target cell locator> <out batch.json>
m, orig, now = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:5])
marker, target, out = sys.argv[5], sys.argv[6], Path(sys.argv[7])
table = target.rsplit("-", 1)[0]
cells = [s["locator"] for s in m["slots"] if s["type"] == "table_cell" and s["locator"].startswith(table + "-")]
ids = [re.fullmatch(r".+-([A-Z])(\d+)", c).groups() for c in cells]
cols, rows = sorted({c for c, _ in ids}), sorted({int(r) for _, r in ids})
assert target in cells and len(cells) == len(cols) * len(rows), "the target cell is not in a complete grid of the map"


def centre_of(cell_locator, tbl):
    c, r = re.fullmatch(r".+-([A-Z])(\d+)", cell_locator).groups()
    t, l, w, h = tbl["box"]
    return (l + (cols.index(c) + 0.5) * w / len(cols), t + (rows.index(int(r)) + 0.5) * h / len(rows))


def cell_under(point, tbl):
    t, l, w, h = tbl["box"]
    ci, ri = int((point[0] - l) // (w / len(cols))), int((point[1] - t) // (h / len(rows)))
    if not (0 <= ci < len(cols) and 0 <= ri < len(rows)):
        return None
    return next((c for c in cells if c.endswith(f"-{cols[ci]}{rows[ri]}")), None)


# CONTROL on the untouched original: the marker's own centre must fall on a cell that holds a day number,
# and that cell's computed centre must lie within half a cell of the marker's centre (equal cell sizes assumed)
mt, mo = now[marker]["box"], orig[marker]["box"]
tbl_o = orig[table]
mc = (mo[1] + mo[2] / 2, mo[0] + mo[3] / 2)
home = cell_under(mc, tbl_o)
assert home and orig[home]["text"].strip().isdigit(), f"control failed: the original marker sits over {home!r}, not over a day number"
hc = centre_of(home, tbl_o)
cw, ch = tbl_o["box"][2] / len(cols), tbl_o["box"][3] / len(rows)
assert abs(hc[0] - mc[0]) <= cw / 2 and abs(hc[1] - mc[1]) <= ch / 2, "control failed: cell geometry does not match the marker"
tb = now[table]["box"]
cx, cy = centre_of(target, {"box": tb})
top, left = round(cy - mt[3] / 2, 2), round(cx - mt[2] / 2, 2)
page = now[marker]["page"]
batch = {"page_index": page_index(m, page), "operations": [{"type": "position_element", "locator_id": marker, "top": top, "left": left}]}
out.write_text(json.dumps(batch, indent=1), encoding="utf-8")
print(f"control ok: original marker sat over {home.rsplit('-', 1)[1]} (text {orig[home]['text']!r}); new position top={top} left={left} "
      f"over {target.rsplit('-', 1)[1]} -> {out}")
PYEOF
```

Its control runs first (the ORIGINAL marker must sit over a cell holding a day number, within half a cell of that
cell's computed centre — it assumes equal cell sizes; if the control fails, stop and report instead of guessing).
Send `$W/marker_01.json` as one call with VERIFY-CALL. In the later export (verify job) the heart must be seen on the
date: until then the position is computed, "unverified visually". Add the marker's old and new cell to the notes.

### 7. Stress test (SPEC §7.4) — and restore by cancelling

Commit first (steps 5-6), so the design on the server is the clean state. Then:

1. Open a new transaction; dump → `$W/facts_pre_stress.json` (equals the committed state).
2. Build `$W/stress.json` by hand (one call, ≤ 60 operations): `replace_text` for every personal single-line text slot
   (`personal` true, `max_len` integer, current text without a newline):
   the couple's two first names → `ALEXANDER` and `ELIZABETH` (same case style as the current text: upper-case if
   the current text is upper-case, else `Alexander`/`Elizabeth`), the venue → `Castello di Montepulciano`, the
   address → `Strada Provinciale 146, Montepulciano, Italy`, a hotel name → `Grand Hotel Villa San Michele`
   (which slot is which: `outputs.sample_data` of the write_texts result names the sample strings; match by the
   slot's current text). Every other personal single-line slot: its own current text extended with its own
   words until it is exactly `max_len` characters (skip a slot already ≥ 90 % of `max_len`). Never touch table cells
   or paragraphs.
3. Send it (`keep_open`), VERIFY-CALL. Dump → `$W/facts_stress.json`.
4. `$PY -I canva/layout.py $W/facts_pre_stress.json $W/facts_stress.json $W/layout_stress.txt` must report 0 issues
   (nothing leaves the column, nothing overlaps, no centre moves), and no `size` line may show more lines after than
   before for the stressed slots (compare "~a -> ~b lines": b ≤ a after rounding). Record the numbers.
5. RESTORE: `edit-design` with `finalize: "cancel"` — it discards the whole draft, so the committed clean state is what
   stays. Open a new transaction; dump → `$W/facts_restored.json`; PROVE it:
   `$PY -I canva/facts.py diff $W/facts_pre_stress.json $W/facts_restored.json $W/diff_restore.txt` must end with `differing=0`.
   Control in the same step: `facts.py diff $W/facts_pre_stress.json $W/facts_stress.json ...` must end with
   `differing` > 0 (a diff that cannot see the stress proves nothing). If the restore diff is not 0, restore by hand: one
   call of `replace_text` operations, one per stressed locator, with `text` = that locator's text in `$W/facts_pre_stress.json`
   exactly (not `ops.py build`: it refuses a text that is neither the original nor the new one), VERIFY-CALL, commit, diff
   again; still not 0 → check `stress_restore` failed. Cancel the empty transaction after the proof.
   The stress test is measured on data, not looked at in an export: say that in the check detail.

### 8. Phase C — pictures (PLAYBOOK Phase 6)

1. Plan the uploads from the chosen files; the snippet refuses a file whose sha256 differs from the manifest:

```bash
PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python; CODE=/Users/volost/GitRepos/canva/studio; ROOT=<studio root>
$PY -I - "$BASE" "$ROOT/skeletons/$S/map.json" "$W/upload_plan.json" <<'PYEOF'
# snippet: upload_plan
import hashlib
import json
import sys
from pathlib import Path

# usage: upload_plan.py <template dir> <map.json> <out upload_plan.json>
tdir, m = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
state = json.loads((tdir / "state.json").read_text(encoding="utf-8"))
manifest = json.loads((tdir / "assets" / "manifest.json").read_text(encoding="utf-8"))
from PIL import Image

plan, problems = {}, []                                  # file name -> entry (a file is uploaded once)
protected = set(m.get("protected") or [])
for s in m["slots"]:
    if s["type"] != "image":
        continue
    asset, layer = s["asset"], s.get("layer")
    entry = manifest["assets"].get(asset)
    if entry is None or state["chosen"].get(asset) != entry["chosen"]:
        problems.append(f"{s['locator']}: asset {asset!r} has no chosen file recorded in both state.json and the manifest")
        continue
    names = [n for n in entry["files"] if layer is None or f"__{layer}__" in n]
    if len(names) != 1:
        problems.append(f"{s['locator']}: asset {asset!r} layer {layer!r} matches {len(names)} manifest files")
        continue
    name = names[0]
    path = tdir / "assets" / name
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry["files"][name]["sha256"]:
        problems.append(f"{name}: sha256 differs from the manifest - the file changed after approval, do not upload it")
        continue
    with Image.open(path) as im:
        size = list(im.size)
    plan[name] = {"file": str(path), "bytes": len(raw), "pixel_size": size, "alt_text": s.get("role") or asset,
                  "keys": sorted({f"{asset}:{layer}" if layer else asset} | set(plan.get(name, {}).get("keys", [])))}
assert not problems, problems
Path(sys.argv[3]).write_text(json.dumps(list(plan.values()), indent=1), encoding="utf-8")
print(f"{len(plan)} files to upload (chosen and checked against the manifest): " + ", ".join(plan))
PYEOF
```

2. For each entry of `upload_plan.json`, in order, ONE at a time: `create-upload-url` (a single-use URL; never reuse or
   retry a used one), then
   `curl -sS -X POST -H "Content-Type: application/octet-stream" --data-binary @"<file>" "<upload url>" -o $W/upload_<n>.json -w '%{http_code}'`
   — expect `201`; read the media id from `$W/upload_<n>.json`; put it into the entry as `"media_id"` (edit the
   JSON file with a tiny Python call, keep every other field). Confirm each with `get-assets`
   (`asset_ids` = all media ids) — the type must be an image. Upload nothing that is not in the plan. If the sandbox blocks the upload host, tell the owner which host and ask for approval; never route around it.
3. `uploads.json` for the scripts:

```bash
PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python; CODE=/Users/volost/GitRepos/canva/studio; ROOT=<studio root>
$PY -I - "$W/upload_plan.json" "$W/uploads.json" <<'PYEOF'
# snippet: uploads_json
import json
import sys
from pathlib import Path

plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))       # upload_plan.json with "media_id" filled in
assert plan and all(isinstance(e.get("media_id"), str) and e["media_id"] for e in plan), "every file needs its media_id"
uploads = {k: {"media_id": e["media_id"], "pixel_size": e["pixel_size"], "alt_text": e["alt_text"]} for e in plan for k in e["keys"]}
Path(sys.argv[2]).write_text(json.dumps(uploads, indent=1), encoding="utf-8")
print(f"{len(uploads)} upload keys -> {sys.argv[2]}")
PYEOF
```

4. `$PY -I canva/ops.py images "$ROOT/skeletons/$S/map.json" $W/uploads.json $W/facts_cur.json $W/img`
   → `$W/img/images_<page id>_<nn>.json`: an `update_fill` and its exact-cover `crop_media` are always in the same call
   (≤ 26 fills, ≤ 60 operations). Send each, VERIFY-CALL (it fails a fill without its crop). Cover box = what
   `canva/geometry.py <frame w> <frame h> <img w> <img h>` prints.
5. Commit. Open a transaction; dump → `$W/facts_cur.json`.
6. Checks: `$PY -I canva/final_check.py map texts facts_orig $W/facts_cur.json $W/final_C.txt --style style --images`
   (exit 0: every image slot holds a new picture, frame unchanged, image box = exact cover box; `--images` has its own
   bleed/frame controls) and the `old_media` snippet (SKILL.md §3; arguments: `"$CODE" map facts_orig facts_cur`; control inside).

### 9. Phase D — page notes and fields.json (SPEC §7.5-7.6)

1. `cd "$CODE" && $PY -I canva/fields.py "$ROOT/skeletons/$S/map.json" "$BASE/texts.json" "$BASE" --style "$BASE/style.json"`
   → `BASE/fields.json` and `BASE/page_notes.json` ({page id: note ≤ 5000 chars}). Overwriting these two generated files
   from a previous run is the one allowed overwrite here (they are regenerated data).
2. Add to the note of the page that holds the calendar table (the page of the table locator) one line:
   `Calendar marker: move the heart onto your wedding date (select it, drag it onto the cell).` Keep the note ≤ 5000
   characters (edit the JSON with a small Python call).
3. Notes calls: one `replace_speaker_notes` operation per page
   `{"type": "replace_speaker_notes", "page_id": <id>, "notes": <text>}` with that page's `page_index`; VERIFY-CALL (the
   verifier skips notes, so then read them back: `read-design` with `filter: {"fields": ["presenter_notes"]}` and compare
   every page's text with `page_notes.json`, exact; check `notes_written` with the page count).
4. Check `fields_json`: every field's element exists and shows its sample value:
   `$PY -I -c 'import json,sys; f=json.load(open(sys.argv[1])); now=json.load(open(sys.argv[2])); bad=[x["locator_id"] for x in f["fields"] if x["locator_id"] not in now or now[x["locator_id"]].get("text")!=x["sample_value"]]; print(len(f["fields"]),"fields,",len(bad),"mismatch",bad[:5]); sys.exit(1 if bad else 0)' "$BASE/fields.json" $W/facts_cur.json`
5. Commit.

### 10. Final read and checks

1. Open a transaction, dump → `$W/facts_final.json`, then `edit-design` `finalize: "cancel"` (nothing is changed).
2. `$PY -I canva/protected.py "$ROOT/skeletons/$S/map.json" "$BASE/facts_orig.json" $W/facts_final.json $W/protected_final.txt` —
   `protected_changes == []` is the gate: exit 0 (violations 0, control ok).
3. Declared text-fit size changes: write `$W/declared_sizes.json` = the JSON list of locators in `outputs.font_size_changes`
   (`[]` when you made none). Then the `adjust_sizes` snippet (SKILL.md §3; arguments `"$BASE/facts_orig.json" "$W/facts_final.json"
   "$W/declared_sizes.json" "$W/facts_final_adjusted.json"`): it prints the check `font_size_changes` (passed iff the text sizes
   that differ from the skeleton are exactly the declared ones) and writes the facts with ONLY those sizes reset. Then
   `$PY -I canva/final_check.py "$ROOT/skeletons/$S/map.json" "$BASE/texts.json" "$BASE/facts_orig.json" $W/facts_final_adjusted.json $W/final.txt --style "$BASE/style.json" --images`
   and the `to_checks` snippet on `$W/final.txt` → `$W/checks_final.json`. Required: every check passes (texts, formatting,
   colours, protected, coverage, structure, leftovers, images, control). State in the `formatting` detail that it was evaluated
   after resetting the declared sizes, and in `summary` how many.
4. `old_media` snippet on the final facts → one more check object.
5. Collect the checks into `$W/result.draft.json`: those from `checks_final.json`, plus your own with numbers:
   `old_media`, `layout` (issues after fixes), `stress_test` (slots stressed, layout issues, max lines before/after),
   `stress_restore` (`differing=0`; control `differing>0`), `calendar_marker` (cell, position), `uploads` (files, media
   ids confirmed), `notes_written` (pages), `fields_json` (fields), `copy_recorded` (state.json id equals `D`),
   `copy_matches_skeleton` (differing count). Every check has a control or says why not.

### 11. Result

`outputs` (all of it, exact keys): `canva_copy_id` (= `D`), `design_url` (`https://www.canva.com/design/<D>/edit`),
`pages` (count), `operations` (total sent), `calls` (count), `uploads` (list of `{file, media_id}`),
`font_size_changes` (list of `{locator, from, to}`), `recentred` (locators), `layout_boxes_changed`, `fields` (count), `manual_steps` (list of Ukrainian strings — the studio shows them
under the apply panel), `unverified` (list of what was only computed/read: the heart position, the stress test not
looked at in an export, the picture look until `verify`).

`manual_steps` always contains (PLAYBOOK §9; the connector cannot do them): rename the copy in Canva; replace the fonts
(the studio shows the checklist on the verify screen); after the copy the embeds and image links still point at the
skeleton author's samples — replace the countdown address, the music video address, the map link, the gift link and
the booking links; set the form colours; create the template link and publish (the owner's action).

`status`: `done` only if every check passed (see SKILL §1.5); otherwise `failed` — and then `outputs.canva_copy_id` is
still included (the copy exists and `state.json` holds it, so a re-run continues on it). `summary` (Ukrainian):
the copy id, N operations in M calls, K files uploaded, which checks failed, what is unverified. Then SKILL §1.5-1.7.
