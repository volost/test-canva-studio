# Decisions

Two kinds of entries: **owner decisions** (given by the project owner in conversation; they override everything
else) and **rulings R1–R32** (judgement calls made by the lead session while running the plan; each lists what was
decided, why, and what it costs if it turns out wrong). Sources: the owner's project notes, `STATUS.md`, `DESIGN.md`,
and the run ledger `docs/history/sdd-ledger.md` (a snapshot of 2026-11-21, where every ruling first appeared; it also holds
the review findings behind them).

"The owner" is the person for whom the studio is built; the Canva account the studio works in is theirs. A message from
another session or agent is never the owner's consent.

## 1. Owner decisions (dated)

### Product and scope

| Date | Decision | Notes |
|---|---|---|
| 2026-11-12 | Templates must be maximally configurable for the person who edits them: dates, names, addresses and other personal details editable as live text, only where needed, roomy text boxes, a stress test with long values, an editing checklist and `fields.json`. | Owner's words (translated): "make the template so that the person editing it for their own dates can edit the dates, names, addresses and other needed things". Rules derived from it: `docs/reference/SPEC.md` §7. Applies to every template. |
| 2026-11-12 | The finished design should ship with a designed PDF guide; shop name and logo do not exist yet (use placeholders); the template link is a paid Canva feature to be bought later (placeholder); guide screenshots must show Canva's English interface. | Later postponed together with all selling work (see 2026-11-20). Not re-verified in this pass. |
| 2026-11-20 | The templates WILL be sold on Etsy, built on the owner's OWN skeletons, not on copies of the purchased template. | The analysis behind it (not the owner's decision): a design built on a copy of the seller's file is a derivative of a purchased product, suitable only for private demos. Raise it again before anything is sold. |
| 2026-11-20 | Etsy publication is postponed, and no research of selling rules is to be done. "For now the studio must only generate products in Canva." | So: no Etsy listings, mockups, prices, no PDF guide, no template link work, until the owner reopens it. `DESIGN.md` §2 "Non-goals". |
| 2026-11-20 | Architecture: a local web studio (localhost) for the owner, and Claude Code does the Canva writes through a job inbox (the `/test-canva-studio` skill). Step-by-step work with the owner's approval at each step. Fonts: the studio suggests, the owner changes them by hand from a checklist (the connector cannot choose fonts). | Chosen after an analysis that also named experiments not yet run (direct Canva MCP from an own app; `create-design` for a skeleton; Autofill on a website). |
| 2026-11-20 | `DESIGN.md` approved («Затверджую»). | The plan is `PLAN.md` (14 tasks). |
| 2026-11-20 | Execution by agents per task (superpowers subagent-driven development: one implementer and one reviewer per task, a review of the whole branch at the end). | The model is chosen per task by the lead (see the "Model choice" note in `CLAUDE.md`). |
| 2026-11-20 | The job command is `/test-canva-studio`, not `/studio`. | `DESIGN.md` and `PLAN.md` keep the old name in their historical text; the skill and `STATUS.md` use the new one. |
| 2026-11-20 | A local git repository in `studio/` is allowed (main branch). | On 2026-11-21 the owner asked for the repo to be handed to another developer on a private GitHub repository; the controller session creates the remote, not the handover implementer. |

### Language, comments, and models

| Date | Decision | Notes |
|---|---|---|
| 2026-11-21 | All documentation, code comments, instructions and commit messages in English. The studio UI and every owner-facing message stay Ukrainian (API messages the UI shows, `run.sh` / `tools/demo_root.py` terminal output, Ukrainian result summaries the skill writes, test assertions on those strings, `etsy-report/build.py`). | Do not translate those strings. Ruling R27. |
| 2026-11-21 | Add comments wherever another model needs them to continue the work (module purpose, non-obvious decisions and the reason). Standing rule for all new code. | Pass done in commit `bc01df3`. |
| 2026-11-21 | The Z-Image Turbo licence is NOT to be checked (do not research it, do not list it as a task, do not offer it). | `DESIGN.md` §7 item 5 stays open by the owner's choice. |
| 2026-11-20 / 21 | Until the end of the week of 2026-11-22 all agents run on Sonnet or Haiku only (owner's global rule). | Time-limited and specific to the owner's account; after it the lead picks a model per task. Not binding for another developer. |
| 2026-11-21 | The repo is handed over: another developer clones it and continues in their own Claude Code session opened in the repo root. | Rulings R28–R32 below. |

### Safety rules (standing)

These are also in `CLAUDE.md`; they come from the owner and from `DESIGN.md` §2 "Anti-goals":

- Never edit the purchased original `DAHarqlqips` or a skeleton design. Canva writes only on the template's own copy, through jobs.
- One Canva writer at a time per design. The studio never deletes anything. Publishing, sharing, form submission, account settings are the owner's own actions.
- The owner approves each step. Code, not the skill's good intentions, refuses forbidden targets (`app/guard.py`, `app/jobs.py`).

## 2. Rulings R1–R32, grouped by task

Format: **what** — why — cost if wrong.

### Process and environment (before and during Tasks 1–3)

- **Work on `main`, no worktree** (no number). The owner approved a fresh local repo for this; nothing shared. Cost if wrong: none (local only).
- **R1** (Task 1) — Task 1 creates `tests/fixtures/config.json` (same keys as `config.json`, `studio_port` 8765). The tests need it and the plan's file list omitted it. Cost: one extra fixture file. (Its paths became neutral example paths in R29.)
- **R2** (Task 1) — Any test that starts a server runs with the Claude Code sandbox off, after seeing EPERM; the code still binds `127.0.0.1` only. Cost: none. (R32 documents the alternative setting.)
- **R6** (Task 1) — `-I` (isolated Python) applies to the studio's own Python only; ComfyUI is started WITHOUT `-I` with cwd = the ComfyUI folder. The plan's "launch with `-I`" meant studio code (`DESIGN.md` §5.7.4); ComfyUI is a trusted local install and cannot import itself under `-I` (a control run proved it). Cost: none found.
- **R7** (Task 1) — A reviewer minor was promoted into the fix round: `forbidden_design_ids` given as a string became a set of characters, weakening the guard on `DAHarqlqips` that Task 3 builds on. Cost: a few lines. (`app/config.py` now requires a list of non-empty strings.)

### Task 3 — job creation and the guard

- **R3** — `create_job` takes the skeleton id from `skeletons/<s>/map.json["design_id"]` if present, else from `inputs["design_id"]`; if neither exists, Canva write types (`apply_canva`, `verify`) fail closed with `GuardError`. State comes from `templates/<t>/state.json` when a template is given; a missing or corrupt state for a write type is a `GuardError`. Why: fail closed matches `DESIGN.md` §5.7.3. Cost if wrong: an API change in Task 9.
- **R4** — `forbidden_design_ids` are refused as `target_design_id` for EVERY job type, and also as `inputs["design_id"]` of `map_skeleton`; the skeleton id is refused as a target only for Canva write types; `map_skeleton` carries the skeleton id in `inputs["design_id"]` with a null target. Why: `DESIGN.md` §5.7.3 protects against writes; reading the skeleton is step 0. Cost: the guard is slightly looser for a read-only job.
- **R5** — Every `apply_canva` / `verify` job's `limits` contain, in Ukrainian, one line each for: edit only the target (the template's copy); never the skeleton or `DAHarqlqips`; do not touch form, embeds, envelope structure; no regrouping, no new pages; no publishing; no deletions; two identical call failures means stop and write a note (`DESIGN.md` §5.2). Cost: wording only.
- **R8** — `read_json` raises `CorruptJSON` also for invalid UTF-8 and for valid JSON that is not an object. Why: `list_jobs` relies on it so a corrupt inbox file is shown as corrupt and the studio does not crash. Cost: a few lines in `store.py`.

### Tasks 6–8 — envelope, schema, assets

- **R9** (Tasks 6–8) — The map's `envelope` block gets an optional `"seal_asset": <asset key>|null`; image slots get an optional `"layer": "cover"|"flap"|"body"` (only for a `composed` asset). Task 7 validates both. Task 8: a composed asset's prompt generates its texture at the envelope-section aspect; post-processing cover-crops it and `compose_envelope` writes `<asset>__cover__v<n>.jpg`, `__flap__v<n>.png`, `__body__v<n>.png`; `state.chosen[asset]` is the cover file, the layers share its version. Why: the plan's data formats name no seal link and no layer, and the Sage & Linen style needs both. Cost: schema keys renamed in Task 11.
- **R10** (Task 7) — `table_cell` slots (calendar cells: month, days; personal values per `SPEC.md` §7) carry plain strings in `texts.json` like text slots: `validate_texts` and `length_warnings` accept both locators, and `font_checklist` lists both. Otherwise `write_texts`/`apply` could not set the calendar. Cost: one helper line in `texts.py`.
- **R11** (Task 8) — The assets state lock is public and importable (`app/store.py: STATE_LOCK`), used for every `state.json` read-modify-write in `assets.py`; Task 9 takes the same lock for step changes. Cost: one rename.
- **R12** (Task 8) — `list_versions` offers a composed version only when cover, flap and body all exist for that `n`. A half-written set must not be choosable (the studio deletes nothing), because `choose()` would put a broken envelope into Canva. Cost: a few lines.

### Tasks 9–10 — API and web interface

- **R13** (Task 9) — The API owns step transitions: creating `style_directions` / `write_texts` / `apply_canva` / `verify` sets that step to `waiting_claude` (under `STATE_LOCK`); a GET of a template (and `GET /api/jobs`) reconciles: a job result `done` moves its step to `review`, `failed`/`corrupt` to `draft` with the result summary exposed; the images step moves to `review` when every map asset has a chosen file and generation is not running; approve/reopen go through `steps.py` under `STATE_LOCK`. Why: `DESIGN.md` §5.1 statuses need a mover and only the API sees both jobs and state. Cost: transition rules move in Task 12.
- **R14** (Task 9) — Generation tickets are persisted per template (`templates/<t>/gen_tickets.json`, atomic) and reloaded at start; tickets unknown to the fresh queue are marked lost with a Ukrainian problem «генерацію перервано перезапуском — згенеруйте ще раз» instead of pending forever. Why: the owner restarts the studio. Cost: one file.
- **R15** (Task 10) — The Task 10 implementer builds the UI; the controller verifies in the browser itself (the sandbox blocks local ports). Cost: controller context.
- **R17** (Task 9) — Task 9 on Sonnet high rather than the plan's medium: R13/R14 and the shared lock add judgement and concurrency. Cost: a little more usage.
- **R18** (Task 9 fix) — Requesting a Claude job applies reopen-cascade semantics: every later step that is approved/review/waiting_claude becomes stale, then the requested step goes to `waiting_claude`. `steps.reopen` also stales later steps in `waiting_claude` (the Task 2 behaviour and its test changed deliberately); reconcile only advances `waiting_claude` steps, so a staled step never jumps to `review`; `_canva_request` re-checks `can_start` and busy inside `STATE_LOCK`. Why: `DESIGN.md` §5.1 and review focus 2. Cost: a step must be re-run more often.
- **R19** (Task 9 fix) — When an `apply_canva` result is `done` but `state.canva_copy_id` is null, apply goes to `draft` with a visible message «Claude не записав id копії — перевірте /studio» (renamed to `/test-canva-studio` in the code with the command), and a further apply is refused 409 until `canva_copy_id` is set. Why: avoid a second Canva copy. The skill must write `canva_copy_id`. Cost: the owner fixes the state by hand once.
- **R20** (Task 9 fix) — One bad template (corrupt `state.json`, missing keys) must not make `/api/jobs`, `/api/gen` or the list return 500; `GET /api/templates/<t>` for it returns 409 with «пошкоджений state.json». Cost: a few lines.
- **R21** (Task 9 fix) — POST/PUT routes require `Content-Type: application/json` (else 415/400): blocks cross-origin `text/plain` form posts that would create agent jobs. Cost: the UI must send the header (it does).

### Task 11 — Canva scripts

- **R16** — Task 11 creates its own fixture `tests/fixtures/map_sage.json` whose locators match `facts_sage.json`; `build_ops` turns `table_cell` texts into table-cell edit operations. Cost: fixture only.
- **R22** — Task 11 fixes: final check must not be green on an incomplete map (new `coverage` check and the map's `keep` key); a text role missing from `colour_roles` is noted, not silently skipped; operations are chunked (≤ 60 per call, ≤ 26 `update_fill`); `verify_batch` flags `add_page` as forbidden; `schema.validate_map` validates the optional slot `target` (`fill`|`stroke`). Cost: small.

### Task 12 — the skill

- **R23** — The skill source is versioned in the repo (originally `skill/studio/`); the controller installed it by copying into the owner's `canva/.claude/skills/` with a write the owner approved. Superseded by R30 (the skill now lives inside this repo's `.claude/skills/`).
- **R24** — `/test-canva-studio` takes an optional studio root argument (default: the code folder); the dry run (Steps 2–3) ran against a scratch root seeded from the test fixtures, so no test data lands in the real folders. Cost: one argument.
- **R25** — Task 12 on Sonnet high (the owner's choice, and the global Sonnet/Haiku rule).
- **R26** — Task 12 fix round: (I1) a resumed job with a valid done result is checked before the precheck so the result is not overwritten by `failed`; (I2) the stress test leaves `facts_cur` consistent (`cp facts_restored.json facts_cur.json`); and promoted: refusal path wording "write the result (1.5), then file it (1.6)"; SKILL.md frontmatter `disable-model-invocation: true` (a Canva-writing skill runs only on the owner's command); `reset_texts` records the locators whose design text was neither original nor new; every Canva call passes `user_intent` and `is_editable` comes from the page's `isEditable`; `style_directions` names which rules `validate_style` checks and computes the rest in a `roles_covered` check. Cost: instruction edits.
- **Rename** (owner, 2026-11-20): `/studio` became `/test-canva-studio` everywhere except `DESIGN.md`/`PLAN.md` history.

### Translation and comments

- **R27** — Translate to English: `DESIGN.md`, `PLAN.md`, `STATUS.md`, code comments and docstrings (also in `app/static`), and a few notes outside the repo; keep Ukrainian everything owner-facing (UI text, API messages shown by the UI, terminal messages of `run.sh` and `tools/demo_root.py`, Ukrainian result summaries, test assertions on those strings, `etsy-report/build.py`). Files outside the repo got a byte copy `<name>.uk.md` next to them, SHA-256 checked, before translation. Cost: a few extra files.

### Handover (this pass, 2026-11-21)

- **R28** — The other developer opens Claude Code in the repo root (the `studio/` folder of the owner's machine; the repo root is what `git rev-parse --show-toplevel` prints). Why: a project `CLAUDE.md`, `.claude/skills` and `.claude/settings.json` load at session start only for a session opened in that folder (nested ones load on demand); auto memory is machine-local. So the repo carries `CLAUDE.md`, `README.md`, `docs/DECISIONS.md`, `docs/OPEN_ISSUES.md`, `docs/history/sdd-ledger.md`. (The Claude Code loading behaviour was researched from its docs by an agent on 2026-11-21; "connectors are per claude.ai account" is an inference.)
- **R29** — Machine paths leave git: `config.example.json` is committed; `config.json` is untracked (`git rm --cached`, file kept) and ignored locally; `run.sh` reads every path and port from `config.json`; the skill derives `CODE` from the git top level and its default `ROOT` is `CODE`; `tests/fixtures/config.json` has neutral example paths. Cost: a new clone needs one copy-and-edit step, and `tools/demo_root.py` plus its test need `config.json` to exist.
- **R30** — The skill source moved to `.claude/skills/test-canva-studio/` (`git mv`), so a session in the repo root has `/test-canva-studio` with no copy step. The old installed copy in the owner's `canva/.claude/skills/` is left in place (nothing deleted) and is now stale: the owner decides about it.
- **R31** — Copies (not moves) of the playbook, the Sage & Linen spec, the Ivory Lace blueprint and the ComfyUI extra-model-paths file went into `docs/reference/` and `config/extra_model_paths.example.yaml`; links updated. The seller's materials (the purchased template's PDF guide, images) are NOT copied: licence unknown. Cost: the owner's study folders remain the only copy of the rest.
- **R32** — No permission rules are committed. `sandbox.network.allowLocalBinding: true` is documented in `README.md` as an optional personal setting (needed to run the server tests inside Claude Code's sandbox), not committed, because of the security caveat in Claude Code's sandbox documentation.

Rulings R1–R32 have no gaps: the numbers are listed above in order of appearance in the ledger (R16 sits with Task 11 although it was decided in the Tasks 9–11 pre-flight).

## 3. Facts carried over from the owner's machine-local notes

Copied here because the owner's notes live only on their machine. Dated, NOT re-verified in this pass; re-verify before relying on them.

**Local image generation (ComfyUI), established 2026-11-11/12**
- ComfyUI runs headless; no ComfyUI Desktop window is needed. The studio's `run.sh` starts it with `--listen 127.0.0.1 --disable-auto-launch --disable-all-custom-nodes --extra-model-paths-config <file>`.
- The Claude Code Bash sandbox hides the Mac GPU (`torch.backends.mps.is_available()` was False inside, True outside) and blocks connections to localhost. So ComfyUI and the studio server both run in the developer's own Terminal, outside the sandbox.
- Z-Image Turbo graph: UNETLoader, ModelSamplingAuraFlow (shift 3), KSampler (8 steps, cfg 1, `res_multistep`, `simple`), CLIPLoader type `lumina2`, negative = ConditioningZeroOut (built in `app/comfy.py`).
- Timing seen on the owner's Mac: about 70 s for a 1024 px image with models in memory (0.5–4 min for later images, about 14 min for the first, loaded from an external disk).
- System `python3` has no PIL/numpy; the ComfyUI venv Python has both (run with `-I`).

**Canva connector, established 2026-11-12 (details: `docs/reference/PLAYBOOK.md` §4)**
- It can replace section backgrounds, images in frames and masks, text (font kept), colours, table cells (the calendar); move the form and embeds; write speaker notes. It cannot add or resize sections, delete pages, choose fonts, change embeds' addresses, links or animations.
- `update_fill` leaves the image box about 11 px too large; follow every `update_fill` with `crop_media` to the computed cover box.
- Links and animations are invisible to the connector; a connector commit keeps page links, the envelope reveal, text entrance animations, embeds and the form (checked in Canva's full-size preview).
- The editor's side preview panel is static (the envelope never opens there); the full-size interactive preview is reached by the expand button of that panel. A report "the envelope does not open" was this once.
- The owner's Canva account was on the Free plan on 2026-11-12: template links and Autofill need a paid plan, to be bought later. Canva's Contributor Agreement (effective 2026-01-14) forbids AI-generated content in the Canva Creators marketplace, templates included.
- Large `read-design` results are saved to a file; pages with sections have no thumbnails. To see a result: commit, `export-design` PNG, download, slice.
- Designs: the purchased reference template `DAHarqlqips` (never edit); the probe copy `DAHason1g_M` (disposable, "TEST COPY - Ivory Lace…"); the finished Sage & Linen design `DAHatAFDQz4` (built by hand-run agents on 2026-11-12, published by the owner themselves). These ids live in the owner's Canva account; access is the owner's to give.

**Etsy policy as read on 2026-11-20** (only context, selling work is postponed): Creativity Standards (dated 2025-06-10) list wedding invitations as a digital download "designed by a seller" and allow seller-prompted AI with disclosure in the listing description; the Seller Handbook update of 2026-10-22 bans bot-generated listings without human involvement and AI functional guides; the listing image requirements for digital items were not read.
