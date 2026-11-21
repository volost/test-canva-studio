# Studio — resume point

Updated: 2026-11-20. Current state only; history is in the log `.superpowers/sdd/PLAN/progress.md` and in `git log`.

## State

- Design `studio/DESIGN.md` — approved by the owner on 2026-11-20. Plan `studio/PLAN.md` — 14 tasks; the method of
  execution is agents per task (superpowers:subagent-driven-development: one implementer per task, a reviewer after
  each, and at the end a review of the whole branch).
- Repository: local git in `studio/`, branch `main`, no push and no remote repository, no
  `Co-Authored-By`. Its own `.gitignore` stays local (the global `~/.gitignore_global` ignores `.gitignore`).
- **Done: Tasks 1–12** (`af9c9c2..f566570`), each passed review; the full suite — **457/457** (run
  2026-11-20, outside the sandbox). What exactly and with which caveats — the log, the `Task N: complete` lines.
- **The command is called `/test-canva-studio`** (owner's decision 2026-11-20; historically `/studio` in DESIGN/PLAN).
  The skill source is `studio/skill/test-canva-studio/` (under git); installed 2026-11-20 as a byte-for-byte copy in
  `/Users/volost/GitRepos/canva/.claude/skills/test-canva-studio/`. After every skill change in the repository,
  copy it again (the sandbox blocks writes to `.claude/skills` → the owner's permission window).
- **The Task 12 dry run was done on 2026-11-20** in the test folder `/Users/volost/GitRepos/canva/studio-dryrun`:
  the `verify` job on `DAHarqlqips` was rejected before any call to Canva; `write_texts` → `done/`
  (45 texts, 6 checks with controls), the studio shows the texts, the step is "ready for review". The first
  `write_texts` failed because the demo skeleton had no `facts.json` and no calendar grid (a gap in `tools/demo_root.py`).
- **`run.sh` verified on 2026-11-20** on the owner's Mac: the studio at 127.0.0.1:8765 (`/api/health` ok, the models
  disk mounted), ComfyUI 0.46.0 at 127.0.0.1:8188 (MPS; arguments = the command from run.sh, without `-I`).
- **Not verified by a run:** generation with a live ComfyUI; no call to the Canva connector at all
  (the Task 11 scripts were checked only against the files of the 12.11 run; the skill instructions only by tests of code fragments).
- **Next:** Task 13 (an end-to-end run on a test copy together with the owner).
  Task 14 (the skeleton specification) is independent. After Task 13 — the final review of the whole branch.

## What to pass on to Task 13 (from the reviews, details in the log)

- The first live run must determine the steps for entering Canva's fullscreen view (they are not in `verify.md` — without
  them the view check will be "not performed" every time) and check the assumptions: transactions and "cancel discards the
  draft", the shape of the upload response, the format of the design link.
- `apply_canva`: calls ≤ 60 operations (≤ 26 `update_fill`); after the texts — `canva/layout.py` and a manual fit
  to the phone width; the calendar's heart marker is moved (the map role `calendar_marker` — the owner adds it on the
  map screen, and the style — a colour for it); slots inside protected groups are written deliberately — confirm on the map.
- `final_check` has a `coverage` check: every skeleton text is a slot, protected, or in the map's `keep`.
- `SKILL.md` is ~12k tokens on every run — the Canva-only fragments should be moved into the per-type instructions.
- Deferred small items for the final review — in the log, the `minor (deferred)` lines.

## Working notes

- Tests with a server open a port: in the Claude Code sandbox that is EPERM. Run the full suite outside the sandbox, or
  the owner turns on `sandbox.network.allowLocalBinding: true`.
- A demo for checking the interface: `python -I tools/demo_root.py <empty folder> --port 8765`; the config of the embedded
  browser `studio-demo` is in `/Users/volost/GitRepos/canva/.claude/launch.json`. The script seeds the folder
  anew each time and refuses a non-empty one, so **before every launch** a new empty folder must be set in `launch.json`
  (the old `scratchpad/demo1` is already seeded).

## Before starting a new session

1. Read in full: `studio/DESIGN.md`, `studio/PLAN.md`, this file, the log `.superpowers/sdd/PLAN/progress.md`.
2. `get_usage`: tell the owner the figure. Until the end of the week of 2026-11-22 all agents are Sonnet or Haiku only.
3. Every agent's name ends with " · <Model> <version> <effort>".

## Open questions for the owner

- The `create-design` test for the skeleton — only with the owner's permission (it will create a design in their account).
