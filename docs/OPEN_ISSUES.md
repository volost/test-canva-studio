# Open issues

Everything known to be unfinished, unverified, or deliberately deferred, as of 2026-11-21. Nothing here was re-checked
in the handover pass except where a line says so. Rule of the project: a claim without a run is "unverified" until a run
settles it. When you settle an item, move it to `docs/history/` or delete the line and say so in the commit message.

Z-Image Turbo licence: NOT an open item. The owner decided on 2026-11-21 not to check it (`docs/DECISIONS.md`).

## 1. Not verified by a run (from `STATUS.md`)

- Image generation with a live ComfyUI has never run end to end in the studio (the ComfyUI HTTP shapes were tested only against a fake server; `/view` parameters unverified; the studio's own run of `run.sh` on 2026-11-20 only confirmed that ComfyUI starts and answers on `/system_stats`).
- The Canva connector has never been called by the skill. The Task 11 scripts were checked only against the files saved by the 2026-11-12 manual run; the skill instructions only by tests of code fragments (`tests/test_skill_files.py`) and one dry run (2026-11-20) that never reached Canva (a verify job on the protected original was refused; `write_texts` ran on demo data).
- The `create-design` test for a skeleton (it would create a design in the owner's Canva account) — only with the owner's permission.
- Results of the skill's instruction text on a real model run: none for `apply_canva`, `verify`, `map_skeleton`, `style_directions` (only `write_texts` was run, on demo data).
- Not yet seen on screen by the project (from the 2026-11-12 study): the publish dialog; the sound of the music element; form submission; the template's licence terms; font names (shown only in the editor toolbar).

## 2. Task 13 carry-forward (first live run with the owner)

From the reviews of Tasks 9–12 and `STATUS.md`:

- The first live run must determine the steps for entering Canva's fullscreen view (they are not in `verify.md`; without them the view check is "not performed" every time) and check the assumptions: transactions and "cancel discards the draft", the shape of the upload response, the format of the design link (`https://www.canva.com/design/<id>/edit` is an unverified guess in the UI).
- `apply_canva`: at most 60 operations per call (at most 26 `update_fill`); after the texts run `canva/layout.py` and fit the words to the phone width by hand (text fit: 19 boxes with fixed width and five font sizes in the reference run is not generalised).
- The calendar's heart marker is only recoloured by the scripts; it must be MOVED onto the new date cell (`position_element`) and the buyer's notes must say so. The map role `calendar_marker` is added by the owner on the map screen, with a colour for it in the style.
- Slots inside protected groups (table cells, overlay images) are written deliberately; confirm each on the map screen.
- `final_check` has a `coverage` check: every skeleton text must be a slot, protected, or listed in the map's `keep`.
- `SKILL.md` is about 12k tokens on every run; the Canva-only snippets should move into the per-type instruction files.
- Task 14 (the skeleton specification, `SKELETON_SPEC.md`) is independent; after Task 13 comes the final review of the whole branch.

## 3. Deferred small items ("minor (deferred)" and carry lines of the run ledger), by task

Copied verbatim from `docs/history/sdd-ledger.md`. "Task N" is the task in which the reviewer found it. A line may already be fixed by later work; check the code before acting on it.

Resolved by the handover pass of 2026-11-21 (kept for the record): Task 1 "run.sh echo hardcodes 8765" — `run.sh` now prints the port from `config.json`.


### Task 1

- **minor (deferred)**: no JSON for HEAD/POST (501 HTML) — Task 9 adds routes; read_bytes race after is_file; models_mounted branches untested; traversal guard not mutation-tested; malformed config raises raw JSONDecodeError; run.sh echo hardcodes 8765.
- **minor (deferred)**: comfy.log appended not truncated; dead ComfyUI waits full ~90 s

### Task 2

- **minor (deferred)**: reopen of a step in waiting_claude resets it to review (undefined by spec); state shape unchecked (KeyError); mkstemp mode 0600; empty template folder left if state write fails; no parent-dir fsync.

### Task 3

- **minor (deferred → Task 9 must handle)**: create_job raises ValueError (not GuardError) for whitespace variants of protected ids; TypeError for unserialisable inputs — server must treat ValueError/GuardError/TypeError all as refusals; state read→write window outside lock — serialize state mutation (reopen/approve) under the same lock in Task 9 or rely on skill re-check (DESIGN §5.7.3).
- **minor (deferred)**: verify does not require can_start(state,"verify") (unpinned by test); RecursionError on pathological deep JSON escapes read_json; no threaded test for _CREATE_LOCK; map_skeleton does not enforce target None; write types reachable before skeleton is mapped (inputs design_id only).

### Task 4

- **minor (deferred)**: cover_crop/pad_to_frame raise ValueError in ~1.6 % / ~2 % of random small/odd cases (loud, never silent) — T8 must resize to an exact frame multiple or handle it; no-fringe test checks one row only; no regression test vs original pipeline; no test for the aspect-raise path; contact_sheet bold font = small font, long labels not clipped.

### Task 5

- **minor (deferred → T9/T10)**: disk-not-mounted with ComfyUI up gives HTTP 400 "відхилив граф" not a clear message — UI should check /api/health models_mounted + ping first and hint "перевірте диск моделей"; hung (not refused) ComfyUI blocks /prompt up to 60 s.
- **minor (deferred)**: log-write failure leaves state done with error; job missing a key fails without a jsonl line (validate in submit); read timeout mid-poll reported as «недоступний»; test helper imported across test modules.

### Task 6

- **carry → T8**: when composing with seal=None, call check_envelope(..., seal_expected=False); with a seal, pass seal=<image>. Default seal_expected=True fails loudly otherwise.
- **minor (deferred)**: duplicated seal validation (_seal_layer dead checks); (f) centroid check assumes symmetric seal; RGBA conversion inconsistency in (g).

### Task 7

- **minor (deferred)**: slot fields personal/max_len/original and asset role/transparent types unchecked; protected-need-not-be-slots undocumented by a test.
- **minor (deferred)**: table_cell slot with non-null asset not rejected (schema.py:102)

### Task 8

- **minor (deferred → T9)**: tickets in memory only — after a studio restart, finished-but-unpolled generations stay as orphan raw files and their tickets pend forever; T9 should persist tickets or expire unknown ones; seed/prompt not in manifest; stale-envelope message is a metric string, not «печатку змінено — перегенеруйте конверт»; run_controls lacks a seal-expected control; CorruptJSON from state.json propagates raw in check_all; assets.py 452 lines.
- **carry → T9**: take store.STATE_LOCK for step changes; _load_seal read not under lock (read-only); _CLAIMS grows unbounded (negligible); unknown tickets after restart (see earlier minor)

### Task 9

- **minor (deferred)**: GEN_LOCK held across process_finished image work stalls polling routes and can exceed 5 s for generate during postprocess; stale style/images/texts approvable without re-run; no route to re-request style_directions after failure; template creatable without skeleton map; job written before template/skeleton.json (orphan risk); /files read_bytes OSError uncaught.
- **minor (deferred)**: state.json with steps but no "skeleton" → 500 on POST texts/request and /apply (add to _state_ok); chosen:null treated corrupt; staled waiting_claude job not cancelled — its output still lands; 415 verified by reading only
- **carry → T10**: every POST/PUT must send Content-Type application/json (incl. bodiless); show job_results summaries and copy_missing message; carry → T12: /studio skill must write state.canva_copy_id after copy-design

### Task 10

- **minor (deferred)**: poll fetch has no timeout (a hung request stops polling); copy-missing text says re-apply disabled but button not disabled (server 409s anyway); no /files/ prefix check on version url; panel re-render drops focus in prompt textarea during generation; skeleton screen lacks stale-response guard; hideBanner on every poll; ComfyUI status not pinged in health (only on generate); thumbnails path convention skeletons/<s>/sections/<page>.png; result outputs.directions contract → T12; Canva link form https://www.canva.com/design/<id>/edit unverified.

### Task 11

- **carry → T12/T13 (manual work in apply_canva instructions)**: (I4) text fit to the phone column (pass 1b: 19 boxes fixed-width, 5 font sizes) not generalised — run layout.py after the text pass, fix with resize_element/position_element; (I5) calendar heart marker only recoloured — must be moved onto the new date cell (position_element) and the buyer's notes must say so; (I6) slots under a protected group (table cells, overlay images) are written by design — map review must confirm.
- **minor (deferred)**: replace_text/format_text allow any box change; structure check ignores box/rotation/opacity/lock of non-slot records; colours detail omits skipped section slots; images tolerance 0.5 %+0.5 px; texts keys without slot ignored by final_check; leftovers passes on empty now; update_title/alt/notes/duplicate strokes unchecked; ops.py 480 lines.
- **minor (deferred)**: chunk_ops raises plain ValueError for >60 ops on one element (CLI may traceback); chunking reorders ops across elements (within-element order kept); ops.py 566 lines

### Task 12

- **minor (deferred → T13 first live run)**: expanded preview entry steps undefined (verify may always fail that check until defined); facts_orig baseline first-run ambiguity; set_copy_id lost-update recovery step; SKILL.md ~12k tokens per run (move Canva-only snippets to per-type files); .prev.json 1 s stamp collision; store_map replaces owner-corrected map (kept as .prev).
- **minor (deferred)**: hand-planted valid result for a forbidden-target job is filed without precheck (no Canva call); STATUS/DESIGN still say /studio (controller updates STATUS)
- **minor (deferred)**: tools/demo_root.py seeds no skeletons/<s>/facts.json and no calendar grid, so write_texts fails on fresh demo data.

(Generated from 24 ledger lines: 20 `minor (deferred...)` lines and 4 `carry` lines.)

