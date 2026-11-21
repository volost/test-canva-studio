# SDD ledger — plan: /Users/volost/GitRepos/canva/studio/PLAN.md

Spec: /Users/volost/GitRepos/canva/studio/DESIGN.md (approved 2026-11-20).
Scope of this run (owner, 2026-11-20): Tasks 1–3 only; weekly usage 89 % at start; stop near 95 %.
Repo: local git in studio/ (owner approved 2026-11-20), branch main, no push, no Co-Authored-By (owner's global rule overrides the session attribution reminder). First commit af9c9c2.

Environment facts (checked 2026-11-20 in this session):
- Sandboxed commits work; `git init` needed the sandbox off (.git/config write blocked).
- Binding a local port inside the sandbox fails with EPERM → server tests must run with the sandbox off.
- ~/.gitignore_global ignores `.gitignore` itself, so studio/.gitignore stays local, uncommitted.

Ruling: work on main, no worktree — the owner approved a fresh local repo for this; nothing shared — cost if wrong: none (local only).

## Pre-flight scan (Tasks 1–3 in depth; later tasks only for interfaces 1–3 produce)

| Pair / task | Produces → consumes | Finding |
|---|---|---|
| T1 self | tests use tests/fixtures/config.json, Files list omits it | gap → Ruling R1 |
| T1 self | test_health_endpoint binds a port | sandbox EPERM → R2 |
| T1 → T2 | Config.root → store paths | consistent |
| T2 self | tests vs interface | consistent; state.json shape from "Формати даних" |
| T2 → T3 | can_start, read_json/CorruptJSON, write_json_atomic | consistent |
| T1 → T3 | Config.forbidden_design_ids | consistent |
| T3 self | create_job has no skeleton_design_id/state params but must call check_job(job,cfg,skeleton_design_id,state) | gap → R3 |
| T3 self | map_skeleton targets the skeleton (read-only); guard "blocks skeleton id" | conflict → R4 |
| T3 self | "limits з DESIGN §5.2" not enumerated in plan | R5 |
| T3 → T9 | POST /api/skeletons {name, design_id} creates map_skeleton before map.json exists | covered by R3 |

Ruling R1: T1 creates tests/fixtures/config.json (same keys as config.json, studio_port 8765) — tests need it — cost if wrong: one extra fixture file.
Ruling R2: implementers run any test that starts a server with the sandbox off (dangerouslyDisableSandbox) after seeing EPERM; the code still binds 127.0.0.1 only — cost if wrong: none.
Ruling R3: create_job resolves skeleton_design_id from skeletons/<s>/map.json["design_id"] if present, else inputs["design_id"]; if neither, Canva write types (apply_canva, verify) fail closed with GuardError; state = templates/<t>/state.json when template is given (missing/corrupt state for a write type → GuardError) — fail-closed matches DESIGN §5.7.3 — cost if wrong: an API change in T9.
Ruling R4: forbidden_design_ids are refused as target_design_id for EVERY job type, and also refused as inputs["design_id"] of map_skeleton; the skeleton id is refused as target only for CANVA_WRITE_TYPES; map_skeleton carries the skeleton id in inputs["design_id"] with target None — DESIGN §5.7.3 protects against writes; reading the skeleton is step 0 — cost if wrong: guard slightly looser for a read-only job.
Ruling R5: every apply_canva/verify job's limits contain, in Ukrainian, one line each for: edit only target design / the template's copy; never the skeleton or DAHarqlqips; do not touch form, embeds, envelope structure; no regrouping, no new pages; no publishing; no deletions; two identical call failures → stop and write a note (DESIGN §5.2) — cost if wrong: wording only.

## Progress
Task 1: dispatched implementer (Sonnet medium), BASE af9c9c2
Task 1: implementer DONE_WITH_CONCERNS (minor: traversal test not mutation-tested, run.sh only syntax-checked, 3 extra server tests) commit f9292ab; reviewer dispatched (Sonnet medium)
Task 1: review — spec ❌ (plan-mandated): run.sh starts ComfyUI with `python -I` → ModuleNotFoundError comfy (controller confirmed with control run: same cmd without -I prints usage); Important: no check that ComfyUI came up.
Ruling R6: `-I` applies to the studio's own Python only; ComfyUI is started without `-I`, with cwd = ComfyUI dir — Global Constraint "запуск з -I" meant studio code (DESIGN §5.7.4); ComfyUI is the owner's trusted local install and cannot import itself under -I — cost if wrong: none found.
Ruling R7: promote reviewer Minor "forbidden_design_ids string → frozenset of characters" into fix round 1 — it weakens the DAHarqlqips guard that Task 3 builds on (anti-goal, DESIGN §2) — cost if wrong: a few lines.
Task 1: minor (deferred): no JSON for HEAD/POST (501 HTML) — Task 9 adds routes; read_bytes race after is_file; models_mounted branches untested; traversal guard not mutation-tested; malformed config raises raw JSONDecodeError; run.sh echo hardcodes 8765.
Task 1: fix round 1 implementer DONE commit 23827c1 (adds STUDIO_DRY_RUN hook); scoped re-review dispatched (Sonnet medium)
Task 1: fix round 1/5 (3 addressed, 0 open; commits f9292ab..23827c1)
Task 1: minor (deferred): comfy.log appended not truncated; dead ComfyUI waits full ~90 s
Task 1: complete (commits af9c9c2..23827c1, review clean); controller re-ran suite: see evidence-task1-tests.txt
Task 2: dispatched implementer (Sonnet medium), BASE 23827c1
Task 2: implementer DONE commit 2b6bbf2 (30 tests); reviewer dispatched (Sonnet medium)
Task 2: review ✅ Approved, no Critical/Important.
Task 2: minor (deferred): reopen of a step in waiting_claude resets it to review (undefined by spec); state shape unchecked (KeyError); mkstemp mode 0600; empty template folder left if state write fails; no parent-dir fsync.
Ruling R8: read_json must raise CorruptJSON also for invalid UTF-8 (UnicodeDecodeError) and for valid JSON that is not an object — fixed inside Task 3, because Task 3's list_jobs relies on it for Review Focus 5 (corrupt inbox file shown as corrupt, studio does not crash) — cost if wrong: a few lines in store.py.
Task 2: complete (commits 23827c1..2b6bbf2, review clean)
Task 3: dispatched implementer (Sonnet high), BASE 2b6bbf2
Task 3: implementer DONE commit a2579b3 (114 tests; concerns: apply with copy None + target refused; state.skeleton must match; ids strip+casefold, target charset check; verify no can_start; in-process lock only); reviewer dispatched (Sonnet high)
Task 3: review ✅ Approved, no Critical/Important; controller checked: commit bodies clean, config.json forbids DAHarqlqips, full suite 114/114 (evidence-task3-tests.txt).
Task 3: minor (deferred → Task 9 must handle): create_job raises ValueError (not GuardError) for whitespace variants of protected ids; TypeError for unserialisable inputs — server must treat ValueError/GuardError/TypeError all as refusals; state read→write window outside lock — serialize state mutation (reopen/approve) under the same lock in Task 9 or rely on skill re-check (DESIGN §5.7.3).
Task 3: minor (deferred): verify does not require can_start(state,"verify") (unpinned by test); RecursionError on pathological deep JSON escapes read_json; no threaded test for _CREATE_LOCK; map_skeleton does not enforce target None; write types reachable before skeleton is mapped (inputs design_id only).
Task 3: complete (commits 2b6bbf2..a2579b3, review clean)
Run scope (Tasks 1–3) done; final whole-branch review deferred until all tasks are done.

## Run 2 (owner 2026-11-20: «Продовжуй зараз») — Tasks 4–8; usage 90 % at start

### Pre-flight scan Tasks 4–8
| Pair / task | Produces → consumes | Finding |
|---|---|---|
| T4 self | sources exist (lib.py 147, cutout_watercolour 98, cutout_solid 191, contact_sheet 57, white_to_alpha 33 lines) | ok |
| T5 self | test_ping_closed_port_fast needs a free port (bind) | sandbox EPERM → run outside sandbox (as R2) |
| T5 self | test_queue_reports_comfy_down must not depend on a live ComfyUI | use a closed port URL |
| T4 → T6 | imaging.core → envelope | consistent |
| T6 self | source compose_envelope.py reads linen texture + seal.png from global ASSETS | parametrise: texture/seal passed in (brief already says so) |
| T6 ↔ T7 ↔ T8 | `composed` asset: plan says "генерується лише текстура, решта — compose_envelope", but the seal is a separate asset and map has no link to it; slots have no way to say which envelope layer they take | gap → R9 |
| T7 → T8 | validate_style/validate_map used by plan_generations | consistent |
| T8 self | tests must not reach ComfyUI | substitute generate (as T5 test_queue_sequential) |
| T7 self | test_unicode_text_preserved uses store write/read (Task 2) | consistent (ensure_ascii=False) |

Ruling R9: map `envelope` block gets optional `"seal_asset": <asset key>|null`; image slots get optional `"layer": "cover"|"flap"|"body"` (only for a `composed` asset). T7 validates both (seal_asset must be a key of assets; layer only on slots whose asset is composed). T8: a composed asset's prompt generates its texture at the envelope section aspect; postprocess cover_crops it to section_px×2; compose_envelope(texture, geom, seal=chosen seal or None) writes `<asset>__cover__v<n>.jpg`, `<asset>__flap__v<n>.png`, `<asset>__body__v<n>.png`; state "chosen"[asset] = the cover file, the layers share its version — the plan's data formats name no seal link and no layer, and Sage & Linen needs both — cost if wrong: schema keys renamed in T11.
Task 4: dispatched implementer (Sonnet medium), BASE 15760cd
Task 4: implementer DONE commit 5ea7aa5 (136 tests; watercolour_to_alpha not bit-identical on low-alpha edges, up to 31 colour diff at alpha 10-18); reviewer dispatched (Sonnet medium)
Task 4: review ✅ Approved; reviewer ran port-fidelity check on 4 real watercolour gens: RGB identical, alpha ≤1 level (float32 vs float64 rounding); implementer's "RGB up to 31" not reproduced.
Task 4: minor (deferred): cover_crop/pad_to_frame raise ValueError in ~1.6 % / ~2 % of random small/odd cases (loud, never silent) — T8 must resize to an exact frame multiple or handle it; no-fringe test checks one row only; no regression test vs original pipeline; no test for the aspect-raise path; contact_sheet bold font = small font, long labels not clipped.
Task 4: complete (commits 15760cd..5ea7aa5, review clean)
Task 5: dispatched implementer (Sonnet medium), BASE 5ea7aa5
Task 5: implementer DONE commit 624a566 (145 tests; live ComfyUI never run — HTTP shapes vs fake server only; ping uses /system_stats); reviewer dispatched (Sonnet medium)
Task 5: review ✅ Approved; graph identical to pilot node by node; /history parse matches pilot; /system_stats is a real route (server.py:774, control /prompt matched); /view params unverified by run; live ComfyUI never run.
Task 5: minor (deferred → T9/T10): disk-not-mounted with ComfyUI up gives HTTP 400 "відхилив граф" not a clear message — UI should check /api/health models_mounted + ping first and hint "перевірте диск моделей"; hung (not refused) ComfyUI blocks /prompt up to 60 s.
Task 5: minor (deferred): log-write failure leaves state done with error; job missing a key fails without a jsonl line (validate in submit); read timeout mid-poll reported as «недоступний»; test helper imported across test modules.
Task 5: complete (commits 5ea7aa5..624a566, review clean)
Task 6: dispatched implementer (Sonnet high), BASE 624a566
Task 6: implementer DONE commit 18cee6a (flap/body bit-identical to real S&L files; cover identical after JPEG q94; check_envelope gained seal_expected kw + seal image; new check (h)); controller re-ran full suite 162 OK (evidence-task6-tests.txt); reviewer dispatched (Sonnet medium)
Task 6: review ✅ Approved; reviewer grep: no S&L geometry literals (comments only); non-Sage geometry (1200×900) passes with and without seal at scales 1 and 2; controls would catch an always-[] checker.
Task 6: carry → T8: when composing with seal=None, call check_envelope(..., seal_expected=False); with a seal, pass seal=<image>. Default seal_expected=True fails loudly otherwise.
Task 6: minor (deferred): duplicated seal validation (_seal_layer dead checks); (f) centroid check assumes symmetric seal; RGBA conversion inconsistency in (g).
Task 6: complete (commits 624a566..18cee6a, review clean)
Task 7: dispatched implementer (Sonnet medium), BASE 18cee6a
Task 7: implementer DONE commit b79bdc4 (196 tests; table_cell excluded from texts; paragraph limit int(1.15*len); fixture protected locator not in slots); reviewer dispatched (Sonnet medium)
Task 7: review — Needs fixes: (I1) validators raise TypeError on unhashable asset/colour_roles value/colour-slot role (schema.py:100,108,162,166) — breaks "never raises"; (I2) 115 % limit float rounding: int(1.15*100)=114 (controller confirmed; 97 of n≤5000 differ) → false warning at exact limit.
Ruling R10: table_cell slots (calendar cells: month, days — personal values per SPEC §7) carry plain strings in texts.json like text slots: validate_texts and length_warnings accept both "text" and "table_cell" locators; font_checklist lists both — otherwise write_texts/apply cannot set the calendar and validate_texts would reject it; DESIGN §3 lists table-cell editing as a connector ability — cost if wrong: one helper line in texts.py.
Task 7: minor (deferred): slot fields personal/max_len/original and asset role/transparent types unchecked; protected-need-not-be-slots undocumented by a test.
Task 7: fix round 1 implementer DONE commit 3c1861f (200 tests); scoped re-review dispatched (Sonnet medium)
Task 7: fix round 1/5 (3 addressed, 0 open; commits b79bdc4..3c1861f)
Task 7: minor (deferred): table_cell slot with non-null asset not rejected (schema.py:102)
Task 7: complete (commits 18cee6a..3c1861f, review clean)
Task 8: dispatched implementer (Sonnet high), BASE 3c1861f
Task 8: implementer DONE_WITH_CONCERNS commit a7b2573 (246 tests; assets.py 452 lines; process_finished twice → duplicate versions; unknown tickets pending forever; no recompose-from-raw; provenance not in manifest; white-bg hint added at submit); reviewer dispatched (Sonnet high)
Task 8: review — Needs fixes (reviewer reproduced both by run): (I1) generate-all with map order hero,florals,envelope,seal bakes the envelope before the seal is chosen → all_ok False, (d-control)/(g) flagged; (I2) 4 concurrent process_finished calls on one ticket → hero__v1..v4 duplicates (never deleted). Aspect verified: worst 0.296 % over odd frames; controls real.
Ruling R11: expose the assets state lock as a public, importable lock (e.g. `app/store.py: STATE_LOCK` or `assets.STATE_LOCK`) used for every state.json read-modify-write in assets.py, so Task 9 takes the same lock for step changes — Task 3 review deferred the same need — cost if wrong: one rename.
Ruling R12: list_versions offers a composed version only when cover, flap and body all exist for that n (a half-written set must not be choosable; studio deletes nothing) — promoted from reviewer Minor 3 because choose() would put a broken envelope into Canva — cost if wrong: a few lines.
Task 8: minor (deferred → T9): tickets in memory only — after a studio restart, finished-but-unpolled generations stay as orphan raw files and their tickets pend forever; T9 should persist tickets or expire unknown ones; seed/prompt not in manifest; stale-envelope message is a metric string, not «печатку змінено — перегенеруйте конверт»; run_controls lacks a seal-expected control; CorruptJSON from state.json propagates raw in check_all; assets.py 452 lines.
Task 8: fix round 1 implementer DONE_WITH_CONCERNS commit bf72b71 (252 tests; assets.py 491 lines; unknown seal ticket after restart holds envelope; claims per process); scoped re-review dispatched (Sonnet medium)
Task 8: fix round 1/5 (4 addressed, 0 open; commits a7b2573..bf72b71)
Task 8: carry → T9: take store.STATE_LOCK for step changes; _load_seal read not under lock (read-only); _CLAIMS grows unbounded (negligible); unknown tickets after restart (see earlier minor)
Task 8: complete (commits 3c1861f..bf72b71, review clean); controller re-ran suite: evidence-task8-tests.txt
Run 2 scope (Tasks 4–8) done.

## Run 3 (owner 2026-11-20: «Продовжуй») — Tasks 9–11; usage 91 % at start

### Pre-flight scan Tasks 9–11
| Pair / task | Produces → consumes | Finding |
|---|---|---|
| T9 self | routes create jobs and approve/reopen steps, but nothing in the plan moves a step to waiting_claude / review when a job is created / finished | gap → R13 |
| T9 self | POST /api/skeletons {name, design_id} before map.json exists | R3 already covers (inputs.design_id) |
| T8 → T9 | GenQueue tickets in memory; studio restarts | gap → R14 |
| T3/T8 → T9 | create_job raises GuardError/ValueError/TypeError; STATE_LOCK for state writes | carried (STATUS) |
| T5 → T9/T10 | disk unmounted + ComfyUI up → HTTP 400 | carried: health first |
| T9 → T10 | API consumed by UI | consistent once T9 lands |
| T10 self | Step 1 needs the server running outside the sandbox + in-app browser | R15 |
| T7 → T11 | map_min fixture locators don't match facts_sage.json | R16 |
| T7(R10) → T11 | table_cell texts must become table-cell edit ops | R16 |
| T11 self | sources exist: facts.py 195, final_check.py 117, layout.py 112, plan.py 385, protected.py 94, outline.py 149, probe_diff.py 29 lines; facts0.json, facts_final.json present | ok |

Ruling R13: the API owns step transitions: creating style_directions/write_texts/apply_canva/verify sets that step to waiting_claude (under STATE_LOCK); GET of a template (and GET /api/jobs) reconciles: a job result "done" → its step review, "failed"/"corrupt" → draft with the result summary exposed; images step → review when every map asset has a chosen file and generation for it is not running; approve/reopen via steps.py under STATE_LOCK — DESIGN §5.1 statuses need a mover and only the API sees both jobs and state — cost if wrong: transition rules move in T12.
Ruling R14: GenQueue tickets are persisted per template (templates/<t>/gen_tickets.json, atomic) and reloaded at start; tickets unknown to the fresh queue are marked lost with a Ukrainian problem «генерацію перервано перезапуском — згенеруйте ще раз» instead of pending forever — owner restarts the studio — cost if wrong: one file.
Ruling R15: T10 implementer builds the UI; the controller does the browser verification (Steps 1–4) itself via the in-app browser with a launch config, because the sandbox blocks local ports — cost if wrong: controller context.
Ruling R16: T11 creates its own fixture map_sage.json whose locators match tests/fixtures/facts_sage.json; build_ops turns table_cell texts into table-cell edit ops — cost if wrong: fixture only.
Ruling R17: T9 runs on Sonnet high, not medium as the plan's Who line says — R13/R14 and the shared lock add judgement and concurrency — cost: a little more usage.
Task 9: dispatched implementer (Sonnet high), BASE b27ed92
Task 9: implementer DONE_WITH_CONCERNS commits e00926f 949ef2b (301 tests; api.py 622, tickets.py 77, server.py 119; canva_copy_id never written by API → T12 skill; stale step approvable directly; lost-marking at first GET; texts/request needs style+images approved; images approve runs check_all+manifest); reviewer dispatched (Sonnet high)
Task 9: review — Needs fixes (3 Important, reproduced in-process exp A–C): (I1) re-requesting a Claude job on an approved step does not stale later steps (all approved again with old texts in Canva); (I2) reopen does not stale a later step in waiting_claude → old job finishes → review → approvable on old data; also _canva_request checks state outside the lock; (I3) apply done with canva_copy_id null → apply review, second apply with target null → second Canva copy.
Ruling R18: (I1) _request applies reopen-cascade semantics: every later step that is approved/review/waiting_claude becomes stale, then the requested step → waiting_claude. (I2) steps.reopen also stales later steps in waiting_claude (Task 2 behaviour and its test change deliberately); reconcile only advances waiting_claude steps, so a staled step never jumps to review; _canva_request re-checks can_start and busy inside STATE_LOCK — DESIGN §5.1 "наступні кроки позначаються як застарілі", Review Focus 2 — cost if wrong: a step must be re-run more often.
Ruling R19: (I3) when an apply_canva result is done but state.canva_copy_id is null, apply goes to draft with a visible message «Claude не записав id копії — перевірте /studio» and a further apply is refused 409 until canva_copy_id is set — avoids a second Canva copy; the /studio skill (T12) must write canva_copy_id — cost if wrong: owner must fix state by hand once.
Ruling R20 (promoted Minor 2): one bad template (state.json corrupt or missing keys) must not 500 /api/jobs, /api/gen or the list; GET /api/templates/<t> for it returns 409 with «пошкоджений state.json» — Review Focus 5 — cost: a few lines.
Ruling R21 (promoted Minor 5): POST/PUT routes require Content-Type application/json (else 415/400) — blocks cross-origin text/plain form posts that would create agent jobs — cost: UI must send the header (it will).
Task 9: minor (deferred): GEN_LOCK held across process_finished image work stalls polling routes and can exceed 5 s for generate during postprocess; stale style/images/texts approvable without re-run; no route to re-request style_directions after failure; template creatable without skeleton map; job written before template/skeleton.json (orphan risk); /files read_bytes OSError uncaught.
Task 9: fix round 1 implementer DONE commit d8dee53 (310 tests; steps.invalidate_after added; reopen stales waiting_claude); scoped re-review dispatched (Sonnet medium)
Task 9: fix round 1/5 (5 addressed, 0 open; commits 949ef2b..d8dee53)
Task 9: minor (deferred): state.json with steps but no "skeleton" → 500 on POST texts/request and /apply (add to _state_ok); chosen:null treated corrupt; staled waiting_claude job not cancelled — its output still lands; 415 verified by reading only
Task 9: carry → T10: every POST/PUT must send Content-Type application/json (incl. bodiless); show job_results summaries and copy_missing message; carry → T12: /studio skill must write state.canva_copy_id after copy-design
Task 9: complete (commits b27ed92..d8dee53, review clean)
Task 10: dispatched implementer (Sonnet high), BASE d8dee53
Task 10: implementer DONE_WITH_CONCERNS commit adbf552 (318 tests; no innerHTML; style screen reads result file outputs.directions — T12 contract; thumbnails skeletons/<s>/sections/<page>.png convention; Canva link form unverified; layout unmeasured); reviewer dispatched (Sonnet medium); controller browser check next
Task 10: code review ✅ Approved (no HTML sinks, Canva href regex-validated, all 12 writes via api() with JSON header, routes match api.py, polling chained, demo_root never deletes).
Task 10: controller browser check (R15), demo via /Users/volost/GitRepos/canva/.claude/launch.json "studio-demo", root in scratchpad/demo1, ComfyUI url closed port:
- inventory 1440×900: home (lists, both forms, jobs panel, template_errors, attention), skeleton (thumbs, slots, roles save, assets), style (directions, choose, editor, palette, font map, save), images (gallery, versions, choose, regen, own prompt, contact sheet, queue status), texts (fields, warnings, request, save), apply (explain, apply button, copy-missing alert), verify (Canva link, checks table, pages, font checklist, manual steps); step bar with 5 statuses on every template screen; scrollWidth 1425 ≤ 1440; no control outside x except the skip link (left −9999 by design; .skip:focus rule verified by reading only — Tab test reached another element).
- 768×1024: all 7 screens scrollWidth = clientWidth 753, zero controls outside x; small (<20 px) targets only inline text links and checklist checkboxes.
- injection: text-0 saved as "<img src=x onerror=alert(1)>", reloaded: stored verbatim in API, shown as text, img[src="x"] count 0.
- Review Focus 1: «ComfyUI недоступний — запустіть run.sh» on images screen ~0.1 s after Generate.
Task 10: minor (deferred): poll fetch has no timeout (a hung request stops polling); copy-missing text says re-apply disabled but button not disabled (server 409s anyway); no /files/ prefix check on version url; panel re-render drops focus in prompt textarea during generation; skeleton screen lacks stale-response guard; hideBanner on every poll; ComfyUI status not pinged in health (only on generate); thumbnails path convention skeletons/<s>/sections/<page>.png; result outputs.directions contract → T12; Canva link form https://www.canva.com/design/<id>/edit unverified.
Task 10: complete (commits d8dee53..adbf552, review clean + browser check)
Task 11: dispatched implementer (Sonnet high), BASE adbf552
Task 11: implementer DONE_WITH_CONCERNS commits f4b1ac4 a2f8349 (414 tests; final_check sage 7/7, orig fails texts/colours/leftovers; ops.py 480; heart-marker/title/duplicate strokes/timeline icons not generalised; section bg colour not settable; no real connector run); reviewer dispatched (Sonnet high)
Task 11: review — Needs fixes. Verified by reviewer runs: ops port matches plan.py (88 replace_text, 86 format_text) and all 72 fill/crop pairs match 2026-11-12 ground truth; controls real. Important: (I1) final_check green on an incomplete map (text element not in map keeps skeleton wording — all 7 pass); (I2) text role missing in colour_roles silently keeps skeleton colour, no note; (I3) no chunking — page 2 = 187 ops in one call, largest ever run 65.
Ruling R22: fix I1–I3 in Task 11; also verify_batch flags add_page as forbidden; schema.validate_map validates optional slot `target` (fill|stroke) — cheap safety — cost: small.
Task 11: carry → T12/T13 (manual work in apply_canva instructions): (I4) text fit to the phone column (pass 1b: 19 boxes fixed-width, 5 font sizes) not generalised — run layout.py after the text pass, fix with resize_element/position_element; (I5) calendar heart marker only recoloured — must be moved onto the new date cell (position_element) and the buyer's notes must say so; (I6) slots under a protected group (table cells, overlay images) are written by design — map review must confirm.
Task 11: minor (deferred): replace_text/format_text allow any box change; structure check ignores box/rotation/opacity/lock of non-slot records; colours detail omits skipped section slots; images tolerance 0.5 %+0.5 px; texts keys without slot ignored by final_check; leftovers passes on empty now; update_title/alt/notes/duplicate strokes unchecked; ops.py 480 lines.
Task 11: fix round 1 implementer DONE_WITH_CONCERNS commit d18e1aa (431 tests; coverage check + keep key; 60-op/26-fill chunks; sage 8/8, orig fails texts/colours/leftovers); scoped re-review dispatched (Sonnet medium)
Task 11: fix round 1/5 (5 addressed, 0 open; commits a2f8349..d18e1aa)
Task 11: minor (deferred): chunk_ops raises plain ValueError for >60 ops on one element (CLI may traceback); chunking reorders ops across elements (within-element order kept); ops.py 566 lines
Task 11: complete (commits adbf552..d18e1aa, review clean); controller re-ran suite: evidence-task11-tests.txt
Run 3 scope (Tasks 9–11) done.

## Run 4 (owner 2026-11-20: «Зараз на Sonnet high») — Task 12; usage 93 % at start
Ruling R23: the implementer writes the skill into the repo at studio/skill/studio/{SKILL.md,jobs/*.md} (versioned); the controller installs it by copying into /Users/volost/GitRepos/canva/.claude/skills/studio/ with the Write tool so the owner approves that write in the permission prompt (plan: "потрібен дозвіл власника на цей запис") — a background agent cannot surface the prompt — cost if wrong: one copy step; the repo copy is the source of truth.
Ruling R24: /studio takes an optional studio root argument (default /Users/volost/GitRepos/canva/studio); Steps 2–3 (dry run, guard check) run by the controller against a scratch root seeded from tests/fixtures, so no test data lands in the real studio folders — cost if wrong: one argument.
Ruling R25: Task 12 on Sonnet high (owner's choice 2026-11-20 and the global Sonnet/Haiku rule until 2026-11-22).
Task 12: dispatched implementer (Sonnet high), BASE 2749a95
Task 12: implementer DONE_WITH_CONCERNS commit 2865f1f (453 tests; SKILL.md 586 lines, apply_canva 442; no Canva call run; ops.py build raises on re-apply after owner text edits — reset_texts workaround; layer_element forbidden so 9/9 fix manual; calendar_marker new role; CODE fixed path vs ROOT); reviewer dispatched (Sonnet high)
Task 12: review — Needs fixes. No path to a forbidden Canva write or a Canva call before the target check (walkthroughs a–e). Important: (I1, reproduced) resumed running/ job with a valid done result + step reconciled to review → precheck refuses → write_result overwrites the done result with failed; (I2, by reading code) stress test leaves facts_cur stressed → first image batch VERIFY-CALL reports false untargeted changes → apply stalls.
Ruling R26: fix I1, I2 and promote: (#4) refusal path wording "write the result (1.5), then file (1.6)"; (#10) SKILL.md frontmatter `disable-model-invocation: true` — a Canva-writing skill must run only on the owner's /studio; (#6) reset_texts records the locators whose design text was neither original nor new into notes/outputs and the Ukrainian summary; (#9) every Canva tool call passes `user_intent`, and is_editable comes from the page's isEditable; (#3) style_directions wording: name which rules validate_style checks and compute the rest in a roles_covered check — cost: instruction edits.
Task 12: minor (deferred → T13 first live run): expanded preview entry steps undefined (verify may always fail that check until defined); facts_orig baseline first-run ambiguity; set_copy_id lost-update recovery step; SKILL.md ~12k tokens per run (move Canva-only snippets to per-type files); .prev.json 1 s stamp collision; store_map replaces owner-corrected map (kept as .prev).
Owner decision 2026-11-20: the skill/command is named /test-canva-studio (not /studio). Rename after Task 12 fix round 1: frontmatter name, folder skill/test-canva-studio/, install path .claude/skills/test-canva-studio/, tests, UI hint (app.js), API messages mentioning /studio, STATUS.md. DESIGN/PLAN historical text stays; STATUS records the rename.
Task 12: fix round 1 commit 2dc510a + rename commit f566570 (457 tests); scoped re-review dispatched (Sonnet medium)
Task 12: fix round 1/5 (7 addressed + rename, 0 open; commits 2865f1f..f566570)
Task 12: minor (deferred): hand-planted valid result for a forbidden-target job is filed without precheck (no Canva call); STATUS/DESIGN still say /studio (controller updates STATUS)
Task 12: complete (commits 2749a95..f566570, review clean); install + dry run next
Task 12: installed (diff -r identical) into /Users/volost/GitRepos/canva/.claude/skills/test-canva-studio/; dry-run root /Users/volost/GitRepos/canva/studio-dryrun prepared (write_texts-2 pending, verify→DAHarqlqips pending); steps 2–3 await the owner running the command (model invocation disabled)
run.sh verified 2026-11-20 by owner screenshot + controller browser read: /api/health ok models_mounted true; ComfyUI 0.46.0 /system_stats argv matches run.sh (no -I), device mps. Browser cross-port fetch failed (CORS) — not a defect, studio pings server-side.
Task 12 steps 2–3 (dry run) done 2026-11-20 in another session (likely the owner's), checked by the controller 2026-11-21 from files: verify→DAHarqlqips refused before any Canva call (failed/, reasons: protected original + step not waiting_claude); write_texts-2 failed honestly (demo skeleton lacked facts.json and a calendar grid — demo_root fixture gap); after that session added skeletons/mini/facts.json, calendar grid in map.json and FIXTURE_NOTE.md, job 20261120T211712Z-write_texts → done, 45 texts, 6 checks with controls; Api GET reconciles texts → review, 45 texts, warnings {}. Child session studio-dryrun (Sonnet high) found an empty queue and changed nothing.
Task 12: minor (deferred): tools/demo_root.py seeds no skeletons/<s>/facts.json and no calendar grid, so write_texts fails on fresh demo data.

## Translation pass (owner 2026-11-21: «вся документація, коментарі в коді, інструкції, та інше крім UI — англійською»)
Ruling R27: translate to English: studio DESIGN.md, PLAN.md, STATUS.md; code comments and docstrings (app/static app.js/index.html/style.css comments, any Ukrainian comment/docstring in Python/shell); outside the repo study/ivory-lace/BLUEPRINT.md, handoff/examples/BLUEPRINT_EXAMPLE.md, study/sage-linen/canva/guide_check/LOG.md, the one Ukrainian line in study/sage-linen/SPEC.md and handoff/examples/SPEC_EXAMPLE.md. Keep Ukrainian (owner-facing = UI): studio UI text, API error/status messages the UI shows, terminal messages of run.sh and tools/demo_root.py, Ukrainian result summaries the skill writes for the owner, test assertions on those strings, etsy-report/build.py (renders the owner's Ukrainian report). Non-repo files get a byte copy <name>.uk.md next to them, checked by SHA-256, before translation — cost if wrong: a few extra files.
Translation: agents dispatched in parallel (studio repo; outside files), Sonnet medium.
Owner decision 2026-11-21: «не перевіряй ліцензію Z-Image Turbo» — the Z-Image Turbo licence is not to be checked; remove it from open items in STATUS after the translation lands.
Owner 2026-11-21: «додавай коментарі там де це потрібно щоб інша модель могла продовжувати роботу над проектом» — commenting pass after the translation lands (same files): module docstrings, non-obvious logic and the reason for each review ruling, English, no behaviour change; standing rule for all new code.
Translation: studio b6239d8 (457 OK, node --check OK), outside 5 files translated with .uk.md backups (SHA-256 matched), controller spot-checked; DESIGN §7.5 updated with the licence decision.
Commenting pass: dispatched (Sonnet medium), BASE a7e3b17
Comments pass: bc01df3 (35 files, +264 lines); controller AST check: 33 py files equal sans docstrings, control detects a 1-char change; suite OK (evidence-comments-tests.txt). STATUS updated with language/comment rules.

## Handover pass (owner 2026-11-21: «зроби так щоб інший розробник в своїй сесії міг продовжити роботу»; private GitHub; now)
Research (claude-code-guide agent, docs URLs in its report): project CLAUDE.md, .claude/skills and .claude/settings.json load at start only for a session opened in the repo root; nested ones load on demand; auto memory is machine-local; connectors are per claude.ai account (inference).
Ruling R28: the other developer opens Claude Code in studio/ (repo root). Commit studio/CLAUDE.md (project rules), README.md (human setup), docs/DECISIONS.md (owner decisions + rulings R1–R27 with reasons), docs/OPEN_ISSUES.md (deferred minors + unverified), docs/history/sdd-ledger.md (copy of the ledger).
Ruling R29: machine paths move out of git: config.example.json committed, config.json git-ignored local (untracked with git rm --cached, file kept); run.sh reads paths from config.json; skill derives CODE = git toplevel of its own folder and default ROOT = CODE; tests/fixtures/config.json uses neutral example paths.
Ruling R30: skill source moves to studio/.claude/skills/test-canva-studio (git mv) so a session in studio/ gets /test-canva-studio with no copy step; the old installed copy in canva/.claude/skills stays (no deletion) and is now stale — owner decides.
Ruling R31: copies (not moves) of handoff/PLAYBOOK.md, study/sage-linen/SPEC.md, study/ivory-lace/BLUEPRINT.md and pilot/comfy/extra_model_paths.yaml into studio/docs/reference/ (+ config/extra_model_paths.example.yaml); links updated; seller materials (purchased template PDF, images) are NOT copied — licence unknown.
Ruling R32: no permission rules committed; sandbox.network.allowLocalBinding documented in README as an optional personal setting, not committed (security caveat in the sandbox docs).
Handover implementer dispatched (Sonnet high), BASE 26be6c9.
