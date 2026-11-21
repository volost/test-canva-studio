# Studio — resume point

Updated: 2026-11-21. Current state only; history is in `docs/history/sdd-ledger.md` (the run ledger) and in `git log`.
Decisions and rulings: `docs/DECISIONS.md`. Everything unfinished or unverified: `docs/OPEN_ISSUES.md`.
How to set up and run: `README.md`. Rules for a Claude session: `CLAUDE.md`.

## State

- Design `DESIGN.md` — approved by the owner on 2026-11-20. Plan `PLAN.md` — 14 tasks; the method of
  execution is agents per task (superpowers:subagent-driven-development: one implementer per task, a reviewer after
  each, and at the end a review of the whole branch).
- **The repository is prepared for handover (2026-11-21).** Another developer clones it and continues in their own
  Claude Code session opened in the repo root. Machine paths are no longer in git: `config.example.json` is committed,
  `config.json` is local (git-ignored, copied from the example); `run.sh` reads every path and port from it. The
  reference notes the skill needs are in `docs/reference/`; the machine-local project notes of the owner were folded into
  `docs/DECISIONS.md`. The remote repository is created by the owner's controller session, not recorded here.
- Repository: git, branch `main`, no `Co-Authored-By` lines. A `.gitignore` is NOT committed (the owner's global
  gitignore ignores files named `.gitignore`); the README lists the lines every clone should add to `.git/info/exclude`.
- **Done: Tasks 1–12** (`af9c9c2..f566570`), each passed review; the full suite — **457/457** when last counted on
  2026-11-20 (the number is higher now: the handover pass added tests; run the suite for the current count). What exactly
  and with which caveats — the ledger, the `Task N: complete` lines.
- **The command is called `/test-canva-studio`** (owner's decision 2026-11-20; historically `/studio` in DESIGN/PLAN).
  **The skill now lives in `.claude/skills/test-canva-studio/` inside this repo** (moved with `git mv` on 2026-11-21), so a
  Claude Code session opened in the repo root has the command with no copy step. The old copy at
  `/Users/volost/GitRepos/canva/.claude/skills/test-canva-studio` on the owner's machine is **stale** (it was a copy of the
  pre-move text); the owner decides what to do with it. Nothing was deleted.
- **The Task 12 dry run was done on 2026-11-20** in a test folder on the owner's machine: the `verify` job on `DAHarqlqips`
  was rejected before any call to Canva; `write_texts` → `done/` (45 texts, 6 checks with controls), the studio shows the
  texts, the step is "ready for review". The first `write_texts` failed because the demo skeleton had no `facts.json` and no
  calendar grid (a gap in `tools/demo_root.py`, still open: see `docs/OPEN_ISSUES.md`).
- **`run.sh` verified on 2026-11-20** on the owner's Mac: the studio at 127.0.0.1:8765 (`/api/health` ok, the models
  disk mounted), ComfyUI 0.46.0 at 127.0.0.1:8188 (MPS; arguments = the command from run.sh, without `-I`). On 2026-11-21 `run.sh`
  was changed to read its paths from `config.json`; only `bash -n` and `STUDIO_DRY_RUN=1` (the printed command is identical)
  were checked after that change, not a real launch.
- **Not verified by a run:** generation with a live ComfyUI; no call to the Canva connector at all
  (the Task 11 scripts were checked only against the files of the 12.11 run; the skill instructions only by tests of code fragments).
- **Next:** Task 13 (an end-to-end run on a test copy together with the owner).
  Task 14 (the skeleton specification) is independent. After Task 13 — the final review of the whole branch.

## What to pass on to Task 13 (from the reviews, details in `docs/OPEN_ISSUES.md` section 2)

- The first live run must determine the steps for entering Canva's fullscreen view (they are not in `verify.md` — without
  them the view check will be "not performed" every time) and check the assumptions: transactions and "cancel discards the
  draft", the shape of the upload response, the format of the design link.
- `apply_canva`: calls ≤ 60 operations (≤ 26 `update_fill`); after the texts — `canva/layout.py` and a manual fit
  to the phone width; the calendar's heart marker is moved (the map role `calendar_marker` — the owner adds it on the
  map screen, and the style — a colour for it); slots inside protected groups are written deliberately — confirm on the map.
- `final_check` has a `coverage` check: every skeleton text is a slot, protected, or in the map's `keep`.
- `SKILL.md` is ~12k tokens on every run — the Canva-only fragments should be moved into the per-type instructions.
- Deferred small items for the final review — `docs/OPEN_ISSUES.md` section 3.

## Working notes

- Tests with a server open a port: in the Claude Code sandbox that is EPERM. Run the full suite outside the sandbox, or
  turn on `sandbox.network.allowLocalBinding: true` in your own Claude Code settings (not committed; see README).
- A demo for checking the interface: `python -I tools/demo_root.py <empty folder> --port 8765`. The script seeds the
  folder anew each time and refuses a non-empty one, so before every launch a new empty folder is needed. (The owner used a
  local, git-ignored `.claude/launch.json` entry for the embedded browser; an example is in the README.)
  `tools/demo_root.py` reads the repo's `config.json` for its paths, so copy `config.example.json` first.

## Language and comments (owner's rules, 2026-11-21)

- Documentation, code comments, instructions and commit messages: English. The studio UI and every
  owner-facing message (API messages the UI shows, run.sh/demo terminal output, Ukrainian result summaries,
  the owner's report in `etsy-report/` on the owner's machine) stay Ukrainian.
- Add comments wherever another model needs them to continue: module purpose, non-obvious decisions and the
  reason. Handover comments were added on 2026-11-21 (`bc01df3`); keep doing it for all new code.
- The Z-Image Turbo licence is not to be checked (owner, 2026-11-21).

## Before starting a new session

1. Read in full: `CLAUDE.md`, this file, `docs/DECISIONS.md`; and `DESIGN.md` and `PLAN.md` before touching a task
   (`docs/history/sdd-ledger.md` and `docs/OPEN_ISSUES.md` for the details behind a task).
2. Until the end of the week of 2026-11-22 the owner's agents are Sonnet or Haiku only (the owner's own rule; after the reset
   the lead chooses a model per task).
3. Every agent's name ends with " · <Model> <version> <effort>".

## Open questions for the owner

- The `create-design` test for the skeleton — only with the owner's permission (it will create a design in their account).
- What to do with the stale old skill copy in the owner's `canva/.claude/skills/test-canva-studio` (decision of the owner; nothing was deleted).
- The developer who takes over needs the owner to share the Canva designs (see README "Canva access").
