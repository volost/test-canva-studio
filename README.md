# Wedding-website template studio

A local web application plus a Claude Code skill that together produce new visual styles of a Canva wedding-website
template (pages with sections and an "envelope reveal" opening) from one hand-made "skeleton" design.

The **studio** (Python standard library, a small HTML/JS page on `127.0.0.1:8765`) walks the owner through five steps for each
new template: style direction, pictures (generated locally with ComfyUI and the Z-Image Turbo model), wording, writing it
into Canva, and a check. The owner approves every step. The studio never talks to Canva itself. It puts **jobs** (JSON
files in `jobs/pending/`) into an inbox. The **`/test-canva-studio` skill**, run by Claude Code with the Canva connector, takes
one job, does the Canva work on the template's own copy of the skeleton, checks it, and files a result that the studio shows.

Safety is built into code, not only into instructions: the purchased original design and the skeleton are never
valid targets of a Canva write (`app/guard.py`, `app/jobs.py`, and the skill's precheck), the studio never deletes files,
and publishing, sharing and form submission are always the owner's own actions. Details: `DESIGN.md`.

## Status

Tasks 1–12 of the 14-task plan (`PLAN.md`) are done and reviewed: the studio server, API and web interface, image
pipeline, ComfyUI client, Canva operation scripts, and the skill. **Tasks 13 (the first end-to-end run on a test copy in Canva,
together with the owner) and 14 (the skeleton specification) are left.** Nothing has yet run against a live ComfyUI inside the
studio or against the real Canva connector; see `STATUS.md` (current state) and `docs/OPEN_ISSUES.md` (everything unverified).

## Requirements

- macOS (the owner's setup; the code is not Mac-specific, but ComfyUI was run on Apple Silicon with MPS, and the launch
  and sandbox notes below assume macOS). Python 3 for `run.sh`'s config reading (the system `python3` is enough).
- **A Python with Pillow, NumPy and SciPy**: the virtualenv of a ComfyUI install (verified on the owner's machine:
  Python 3.13, Pillow 12.3.0, NumPy 2.5.2, SciPy 1.18.1; ComfyUI 0.46.0). The studio runs under this interpreter with `-I`.
- **ComfyUI** (headless is enough, no desktop app) and the **Z-Image Turbo** model files, exactly these names (they are
  fixed in `app/comfy.py`, `build_graph`), under one `models` folder:
  - `diffusion_models/z_image_turbo_bf16.safetensors`
  - `text_encoders/qwen_3_4b.safetensors`
  - `vae/ae.safetensors`
- **A Canva account with the Canva connector enabled in Claude** (the skill uses the connector's `read-design`,
  `edit-design`, `copy-design`, `export-design`, `get-export-formats`, `create-upload-url`, `get-assets`, `search-designs`, `help`).
  The Canva connector is per Claude account: connect your own. See "Canva access" below.
- **Claude Code** (the CLI or the desktop app).
- Not required to run the tests: ComfyUI, the models, Canva.

## Setup

1. Clone the repository and `cd` into it. This folder is the **repo root**; open Claude Code here later (see step 7).
2. Create your local config. `config.json` holds the absolute paths of your machine, so it is **not in git**:

   ```bash
   cp config.example.json config.json
   ```

   Edit every value marked `/EXAMPLE/...`:

   | Key | Meaning |
   |---|---|
   | `root` | Absolute path of the studio's data root: where `skeletons/`, `templates/` and `jobs/` are created. Normally the repo root itself. |
   | `python` | The Python of the ComfyUI virtualenv (has Pillow, NumPy, SciPy), e.g. `<ComfyUI>/.venv/bin/python`. Used to run the studio and the skill's scripts (always with `-I`). |
   | `comfy_main` | `<ComfyUI>/main.py`. Its folder is ComfyUI's folder (`run.sh` starts ComfyUI from there). |
   | `models_dir` | The ComfyUI `models` folder that holds the three model files above. `run.sh` and the studio's health check refuse to start generation if it is missing (for example an external disk that is not mounted). |
   | `extra_model_paths` | Absolute path of the ComfyUI "extra model paths" YAML file (step 3). |
   | `comfy_url` | Where the studio reaches ComfyUI. Keep `http://127.0.0.1:8188`; `run.sh` takes ComfyUI's port from it. ComfyUI has no authentication, so it must stay on `127.0.0.1`. |
   | `studio_port` | The studio's port (default 8765). The studio listens on `127.0.0.1` only. |
   | `forbidden_design_ids` | Canva design ids that must never be a target of any job. **Keep `DAHarqlqips`** (the purchased original) and add any other design you must protect. |

   A missing `config.json` is reported by the code and by `run.sh` with a message that says to copy `config.example.json`.
3. Tell ComfyUI where the models are:

   ```bash
   cp config/extra_model_paths.example.yaml config/extra_model_paths.yaml
   ```

   Edit `base_path` in your copy to your `models` folder and point `extra_model_paths` in `config.json` to that file.
4. Make git ignore your local files. A `.gitignore` is deliberately not committed (the original author's global gitignore
   ignores files with that name), so add these lines to `.git/info/exclude` of your clone (this file is local and never committed):

   ```
   /config.json
   /config/extra_model_paths.yaml
   /logs/
   /.superpowers/
   /.claude/launch.json
   /.claude/settings.local.json
   __pycache__/
   *.pyc
   .DS_Store
   ```

   Do not commit `config.json`: it is your machine's paths.
5. Run the tests (about 450 tests; no ComfyUI or Canva needed):

   ```bash
   cd <repo root> && <python from config.json> -I -m unittest discover -s tests -t . -v
   ```

   `-I` isolates the interpreter (so the command is run from the repo root with `-s tests -t .`). Some tests start a local
   HTTP server. Run them in your own Terminal, or, inside Claude Code's sandbox, see "Optional sandbox setting" below.
   `tests/test_demo_root.py` reads your `config.json`, so do step 2 first.
6. Start everything in your own Terminal (not inside the Claude Code sandbox, which hides the GPU and blocks local ports):

   ```bash
   ./run.sh
   ```

   It checks that the models folder exists, starts ComfyUI if nothing answers on its port (log: `logs/comfy.log`, up to about
   90 s to come up), and then starts the studio and prints its address (`http://127.0.0.1:8765`). `STUDIO_DRY_RUN=1 ./run.sh`
   only prints the ComfyUI command that would be run. The terminal messages of `run.sh` are Ukrainian by design (owner-facing).
7. Open Claude Code **in the repo root**. This matters: a project `CLAUDE.md`, `.claude/skills` and `.claude/settings.json` are
   loaded at session start only for a session opened in that folder. You then have the project rules (`CLAUDE.md`) and the
   `/test-canva-studio` command (`.claude/skills/test-canva-studio/`).

## Optional sandbox setting

Claude Code runs shell commands in a sandbox by default. Tests that start a server fail there with `EPERM` because
local port binding is off. Either run the suite in your own Terminal, or add this to **your own** Claude Code settings (it is
not committed to the repo; it opens a local-network capability, so decide for yourself):

```json
{ "sandbox": { "network": { "allowLocalBinding": true } } }
```

It applies without a restart. Running ComfyUI (GPU) and `run.sh` still has to happen outside the sandbox.

## How to resume the work

1. Read `CLAUDE.md` (rules), `STATUS.md` (current state), `docs/DECISIONS.md` (owner decisions and the reasoning behind
   every ruling), and, before touching a task, the matching part of `PLAN.md` and `DESIGN.md`.
2. `docs/OPEN_ISSUES.md` lists what is unverified and what was deferred. `docs/history/sdd-ledger.md` is the full run ledger.
3. **The next piece of work is Task 13** (`PLAN.md`): an end-to-end run on a test copy together with the owner. Task 14, the
   skeleton specification, is independent.

## Canva access

The designs live in the **owner's Canva account**, not in this repository:

- `DAHarqlqips` — the purchased original template. **Never edit it.** It is read-only reference and is listed in `forbidden_design_ids`.
- `DAHason1g_M` — the disposable test copy ("TEST COPY - Ivory Lace…") for experiments.

To work on them you need the owner to **share the designs with your Canva account** (with edit access to the test copy, and
whatever access you need to copy the skeleton), and you must **connect your own Canva account to the Canva connector in
Claude**. A connector connected to the owner's account cannot be used from your machine. The skill copies a skeleton
into a new design for each template (`copy-design`), so your account must be allowed to create designs.

## Where things are

```
app/        the studio: config, store, jobs and guard (safety), steps, API + HTTP server, ComfyUI client, image pipeline
            (app/imaging/), assets, texts, schema (map/style/texts validators), static/ (the web page)
canva/      scripts the skill runs: facts, operations builder (ops.py), final_check, layout, protected, fields, outline
tools/      demo_root.py: seeds a throw-away studio root with demo data for looking at the interface
tests/      unittest suite and fixtures
.claude/skills/test-canva-studio/   the skill: SKILL.md and jobs/<type>.md (one instruction file per job type)
config/     extra_model_paths.example.yaml
docs/       DECISIONS.md, OPEN_ISSUES.md, history/sdd-ledger.md, reference/ (copied reference notes, see its README)
DESIGN.md PLAN.md STATUS.md CLAUDE.md run.sh config.example.json
```

To look at the interface with demo data (needs your `config.json`): `<python> -I tools/demo_root.py <empty folder> --port 8765`.
The script seeds a new folder each time and refuses a non-empty one. In the Claude desktop app a local, git-ignored
`.claude/launch.json` entry (`runtimeExecutable` = your python, `runtimeArgs` = `["-I", "<repo>/tools/demo_root.py", "<empty folder>",
"--port", "8765"]`, `port` 8765) lets the embedded browser start it.

## Language

Documentation, code comments, instructions and commit messages are in English. The studio's web page and every message
the owner reads (API messages shown by the page, terminal messages of `run.sh`, the Ukrainian summaries the skill writes
in job results) are in Ukrainian on purpose; do not translate them, and the tests assert on several of those strings.
