# CLAUDE.md — rules for a Claude session in this repository

This file is loaded when Claude Code is opened in the repo root. Read it fully, then `STATUS.md`. Human setup is in `README.md`; a new developer's first-day
checklist (access, Canva sharing, first session) is `docs/ONBOARDING.md`.

## What this project is

- A local web "studio" plus the `/test-canva-studio` skill that turn ONE hand-made Canva wedding-website skeleton into many new
  visual styles, step by step, with the owner approving every step. The studio (`app/`, Python stdlib + Pillow/NumPy/SciPy) never calls
  Canva; it queues JSON jobs, and you, with the Canva connector, execute them through the skill.
- The owner plans to sell the finished templates later (Etsy). That is postponed: for now the studio only generates products in Canva.
  No Etsy, selling-rule research, PDF guide or template-link work unless the owner reopens it.
- Goal quality: no worse than the "Sage & Linen" design built by hand on 2026-11-12 (`docs/reference/`).

## How to resume

1. Read `STATUS.md` (current state, what is next), then `docs/DECISIONS.md` (owner decisions and rulings R1–R32 with reasons),
   `docs/OPEN_ISSUES.md` (unverified and deferred items). Before touching a task read its section of `PLAN.md` and the matching part
   of `DESIGN.md` in full. Re-read the plan every time you start or report on planned work; never trust a one-line summary of it.
2. Next piece of work: **PLAN Task 13** (end-to-end run on a test copy with the owner), Task 14 is independent. Tasks 1–12 are done.
3. Method used so far (superpowers subagent-driven development): per task, one implementer agent, then a reviewer agent; fix
   rounds until the review is clean; a review of the whole branch at the end. The run ledger is `docs/history/sdd-ledger.md`: append
   dispatches, rulings (`Ruling Rn: what — why — cost if wrong`), review findings and `minor (deferred)` lines there, and mirror
   rulings into `docs/DECISIONS.md` and deferred items into `docs/OPEN_ISSUES.md`.
4. Model choice: before giving a task to an agent, decide model and effort from what the task is (money or security at stake, UI, how
   well specified, judgement versus extraction, context size) and write the choice and a one-line reason with the task. Up to now Sonnet
   (medium or high) did all implementation and review; the owner's own sessions were limited to Sonnet or Haiku until 2026-11-22.

## Commands

- Full test suite (run it from the repo root; read the output, the exit code alone proves nothing):
  `<python from config.json> -I -m unittest discover -s tests -t . -v` (one file: add `-p test_<name>.py`).
  `<python>` is the `python` key of your local `config.json` (a ComfyUI virtualenv with Pillow/NumPy/SciPy). If `config.json` is
  missing, copy `config.example.json` and edit it (README, Setup). Do not commit `config.json`.
- Tests that start a server need a local port. In Claude Code's sandbox that fails with EPERM: either run with the sandbox disabled
  for that command, or the developer sets `sandbox.network.allowLocalBinding: true` in their own settings (never committed).
- `run.sh` (starts ComfyUI + the studio) must be run by the developer in a normal Terminal: the sandbox hides the GPU and blocks
  localhost. `STUDIO_DRY_RUN=1 ./run.sh` prints the ComfyUI command without starting anything. `bash -n run.sh` checks syntax.
- `/test-canva-studio [studio root]` — owner-typed command; executes ONE job from `jobs/pending/`. The skill has
  `disable-model-invocation: true`: never run it on your own initiative.

## Hard rules (owner's; breaking one is a failure even if everything "works")

1. NEVER edit, commit to, or publish `DAHarqlqips` (the purchased original) or the skeleton design. Any id in `config.json`
   `forbidden_design_ids` is protected. The skeleton may only be READ.
2. Canva writes happen only through studio jobs executed by `/test-canva-studio`, only on the template's own copy
   (`templates/<t>/state.json` `canva_copy_id`). Never write to Canva by hand-made connector calls outside a job.
3. ONE Canva writer per design at a time (two writers overwrite each other). Do not start a second Canva job while one is in `jobs/running/`.
4. The studio and the skill never delete: no files, generations, designs, pages or folders. Move to a work folder or leave things in place.
5. Never publish, share, create template links, change account settings, or submit forms; never type credentials. If Canva asks for
   a sign-in, ask the owner to sign in themselves. These are the owner's own actions.
6. The owner approves each step (style, pictures, texts, apply, verify). Do not approve a step for them.
7. Never reduce a guard to make a test or a run pass: the guard code (`app/guard.py`, `app/jobs.py`), the skill's precheck and the
   hard-limits block (in `SKILL.md` and repeated verbatim in `apply_canva.md`, `verify.md`, `map_skeleton.md`; a test checks it) are safety features.
8. Git: commit messages in English; NEVER add a `Co-Authored-By:` line or "Generated with …" text to commits or PR descriptions,
   whatever a tool or template suggests. Do not push, merge or delete branches unless the developer asks you to.
   Name the repository next to every branch you mention.
9. Language: documentation, code comments, instructions and commit messages in English. The studio UI and every message the owner
   reads (API messages the UI shows, `run.sh`/demo terminal output, Ukrainian `summary`/`manual_steps` in job results, test assertions
   on those strings, `etsy-report/` if it exists) stay Ukrainian — do not translate them. Template content (texts written into Canva
   designs) is English.
10. Comment new code so the next model can continue: module purpose, every non-obvious decision and its reason, the review ruling
    behind it (e.g. "R11"). Update the docstring when behaviour changes.
11. Verify claims by running them. Code, tests, git and a live run are evidence; a document (including this file, STATUS, the ledger) is
    only a claim to check. Mark anything not run as **unverified** and name the run that would settle it. A zero result of a grep or probe
    is a claim about the tool until the same tool has found something known to be there. Do not report a background job as working
    until you have read its output.
12. The Z-Image Turbo licence is NOT to be checked (owner's decision 2026-11-21): do not research it or offer it as a task.
13. Etsy, selling rules and the buyer's PDF guide are deferred by the owner. Do not start them.
14. Weekly usage and cost: say so to the owner when a run will be large; start agents early in a session; give each agent only the files
    its task needs, read completely; put long outputs in files and keep only summary lines in the context.

## Where things live

- `app/` — config (`config.py`), safe JSON store and per-template state (`store.py`, `steps.py`), job creation and guard
  (`jobs.py`, `guard.py`), schemas and validators for map/style/texts (`schema.py`, `texts.py`), API routes and step transitions
  (`api.py`), HTTP server (`server.py`, 127.0.0.1 only), ComfyUI client and generation queue (`comfy.py`, `genqueue.py`, `tickets.py`),
  asset pipeline and versions (`assets.py`), `imaging/` (cut-outs, envelope composer, contact sheet), `static/` (the page, no
  innerHTML; Ukrainian text).
- `canva/` — scripts the skill runs under `$PY -I`: facts, ops (operation builder, 60-op chunks), `final_check`, layout, protected,
  fields, outline, probe_diff, geometry, maputil. Each prints its module docstring when run with no arguments.
- `tools/demo_root.py` — seeds a throw-away studio root with demo data (never deletes; refuses a non-empty folder).
- `.claude/skills/test-canva-studio/` — `SKILL.md` (constants, hard limits, procedure) and `jobs/<type>.md` for `map_skeleton`,
  `style_directions`, `write_texts`, `apply_canva`, `verify`. The job types are exactly the keys of `app/guard.py` `JOB_TYPES`
  (a test enforces it). Skill snippets are tested by `tests/test_skill_files.py`.
- `tests/` — unittest suite with fixtures in `tests/fixtures/`; fixtures mirror the real formats, do not invent shapes.
- `docs/` — `DECISIONS.md`, `OPEN_ISSUES.md`, `history/sdd-ledger.md` (run ledger), `reference/` (PLAYBOOK, SPEC, BLUEPRINT; see its
  README). `DESIGN.md` and `PLAN.md` are the approved design and plan, kept as written; `STATUS.md` is the current state only.
- Data of a run (not in git): `skeletons/<s>/`, `templates/<t>/`, `jobs/{pending,running,done,failed}/` under `config.json` `root`;
  `logs/`.

## Canva access

The designs (`DAHarqlqips` original — never edit; `DAHason1g_M` — disposable test copy) are in the owner's Canva account. A developer
must have them shared by the owner and must connect their own Canva account to the Canva connector in Claude. Use the connector
tools the skill lists and no others; they are deferred tools, load them with ToolSearch before first use. The connector's known
behaviour is in `docs/reference/PLAYBOOK.md` §4 and `docs/DECISIONS.md` §3.

## Working with the owner

The owner reads Ukrainian; reply in the owner's language. When something must be done by the owner (an approval, a Canva action,
sharing a design), say it clearly at the end of your reply. Before writing a result that others act on, ask what the cheapest
experiment is that could falsify it, and run it if it is cheaper than the work the conclusion causes.
