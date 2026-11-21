# Wedding-website template studio — design

Note: The command was renamed to /test-canva-studio on 2026-11-20 (owner's decision).

Status: approved by the owner on 2026-11-20 («Затверджую», "I approve").
Basis: conversation with the owner on 2026-11-20; verified facts — `handoff/PLAYBOOK.md` §4–5 (the 12.11 run),
`study/sage-linen/SPEC.md` §7, the project memory.

## 1. Why

The owner will make wedding-website templates in Canva on **their own skeletons**, in order to sell them on Etsy later.
For now the studio must **only generate products in Canva**: from one skeleton it makes new visual styles of a
quality no worse than "Sage & Linen" (12.11), step by step, with the owner's approval at every step.

A skeleton is a site in Canva that the owner assembles by hand once: pages, sections, styled text fields,
frames for pictures, a form, embedded blocks, the envelope animation. A style is a new set of pictures, colours and
texts on top of a copy of the skeleton.

## 2. Goals, non-goals, anti-goals

**Goals**
- One skeleton → any number of styles; each style is a separate copy of the skeleton in Canva.
- Step by step: style → pictures → texts → write to Canva → check; the owner approves every step in the studio.
- The template is configurable for the buyer under the rules of `SPEC.md` §7 (personal data — live text only, and only
  where needed; wide fields; a stress test with long values; `fields.json`; checklists in the page notes).
- Repeatability: what was done by hand by agents on 12.11 now follows one and the same order.

**Non-goals for now** (postponed by the owner on 2026-11-20, or my decision — marked)
- Etsy: listings, mockups, prices, selling rules (owner: postpone, do not research).
- The buyer's PDF guide and the link to the template (my decision: this is part of selling, so it is postponed too;
  `fields.json` and the checklists in the page notes stay, because they are part of the template itself).
- Automatic skeleton building; changing fonts; addresses in embedded blocks; links on pictures;
  publishing — the connector cannot do this (12.11), it is manual work for the owner.
- Cloud, several users, password login: the studio is local, for a single owner.

**Anti-goals** (a failure even if it "works")
- Any write to the skeleton original or to the purchased template `DAHarqlqips`.
- Two writes to one design at the same time (the later save overwrites the earlier one).
- "Done" without a check: the status "applied" without comparing what was read against the plan.
- A style that reached Canva without the owner's approval.
- The studio deleting files, generations or designs; publishing a site; submitting a form.

## 3. Constraints (verified 11–12.11 unless stated otherwise)

- The Canva connector **can**: replace a section's background, a picture in a frame, a photo in a mask (`update_fill`); replace
  text while keeping the font (`replace_text`); text colour/size/alignment; recolour shapes,
  lines, single-colour vector elements; edit table cells (the calendar); move the form and
  embedded blocks; change the layer order; write page notes.
- The connector **cannot**: add a section, resize a section, delete a page, choose a font, change the
  form/embedded blocks/animations/links on pictures, show a link.
- After `update_fill`, `crop_media` to the exact cover frame is mandatory (otherwise the picture is ~11 px larger).
- Copies keep the skeleton's element ids — the skeleton map is valid for all its copies.
- Large `read-design` results are saved to a file; pages with sections have no thumbnails — to see
  the result: commit → `export-design` PNG → download → slice.
- ComfyUI needs the GPU and `localhost`, which the Claude Code sandbox hides. So the studio server and ComfyUI are started
  by the owner in their own Terminal (outside the sandbox).
- Canva's free plan is enough to make and view a design.
- The templates' language is English (my decision; Ivory Lace and Sage & Linen are made that way).
- Fonts are the skeleton's fonts. The studio recommends a font pair for the style and, after writing, gives a checklist for
  the manual swap (owner's decision 2026-11-20).
- Cost: on 12.11 one template took ~8 % of the weekly limit (with research and fixes); a new estimate
  will come after the first run.

## 4. Approaches

| Approach | What it is | Pros | Cons | Decision |
|---|---|---|---|---|
| A. Writing through Claude Code | The studio prepares a job, a Claude Code session executes it through the Canva connector | The path was verified on 12.11; no new accounts; Claude writes the texts too | The steps involving Claude need a Claude Code session | **Chosen by the owner** |
| B. The studio writes to Canva itself | A dedicated app in the Canva Developer Portal + OAuth + MCP tools | The studio is independent | Not verified; needs a developer app; texts — a separate API | Not chosen |

How the studio hands work to Claude Code:
- **Job inbox** (now): the studio puts the job in a file, the owner types one command in the session (`/studio`),
  the session executes the job and puts the result back. **Chosen by the owner.**
- **Button** (later): the studio itself launches Claude Code in the background (`claude -p`). The switch happens only after a test
  shows that a background launch sees the Canva connector. The command-line program currently exists only inside the desktop
  app (`~/Library/Application Support/Claude/claude-code-vm/2.1.328/claude`), not on PATH. **Not
  verified.** The job format is the same for both ways.
- Rejected: a session that checks the inbox continuously — it burns the limit while idle.

## 5. How (decided)

### 5.1 The flow of one template

| Step | Who does it | What the owner sees and approves |
|---|---|---|
| 0. Skeleton (once per skeleton) | Claude: the `map_skeleton` job — reads the design, exports the pages, builds the map | The map: a list of frames and texts with roles, section thumbnails; corrects the roles |
| 1. Style | The owner writes a brief; Claude: the `style_directions` job — 2–3 directions (a palette with roles, a description, picture prompts, a font pair) | Chooses a direction, edits the palette and the prompts |
| 2. Pictures | The studio itself: generates in ComfyUI for each frame (exact aspect ratio), cuts out the background, assembles the envelope in code, runs the checks | The gallery: «прийняти» ("accept") / «ще раз» ("again") / own prompt for each picture; an overview sheet of all of them together |
| 3. Texts | Claude: the `write_texts` job — wording to fit the style, close in length to the skeleton's; personal data only in the fields from the list | Edits each text in the studio; sees the length warnings |
| 4. Write to Canva | Claude: the `apply_canva` job — a copy of the skeleton, colours, texts, pictures (`update_fill` + `crop_media`), configurability, stress test and restoration, page notes, `fields.json` | Presses «Записати» ("Write"); then sees the report |
| 5. Check | Claude: the `verify` job — page export, measurements, a check in Canva's fullscreen view (phone and computer, button audit 9/9) | The pages, a table of checks (passed/failed with numbers), a link to the design, a checklist of fonts and manual steps |

Each step has a status: draft → waiting for Claude → ready for review → approved. The next step
opens only after the previous one is approved. Going back is possible; the following steps are then
marked as stale.

### 5.2 The job inbox

- The studio writes the job to `studio/jobs/pending/<id>.json`: type, template, input files, constraints.
- The `/studio` command in a Claude Code session (a project skill) takes the oldest job, moves it to
  `running/`, executes it, writes the result and notes to the template folder, and moves the job to `done/` or
  `failed/` with a reason. One job at a time; for work with Canva — always one.
- The studio shows the state of the jobs by re-reading the folder.
- Every job for Canva carries the hard limits from PLAYBOOK §6: which design may be edited; never the
  original; do not touch the form, embedded blocks, or the envelope structure; no regrouping and no new pages;
  no publishing; no deletions; two identical call failures — stop and leave a note.

### 5.3 Data

- `studio/skeletons/<skeleton>/` — the skeleton's design id, the map (`map.json`: for each slot — locator,
  type picture/text/colour/table, role, frame size, column width for the phone, whether it is a personal field),
  section exports.
- `studio/templates/<template>/` — the brief, the chosen direction (`style.json`), `assets/` + manifest + overview sheet,
  `texts.json`, the id of the copy in Canva, step results, `fields.json`, notes of each job.
  The layout follows the model of `study/sage-linen/`.
- The skeleton map is the only place where element ids live; the rest of the code does not depend on a specific skeleton.

### 5.4 Technical

- The language is Python; the interface is a page in the browser on `127.0.0.1`. My decision: the Python
  standard library for the server and plain HTML/JS without a build, so that nothing has to be installed; image processing —
  Python from the ComfyUI environment (it has PIL and numpy).
- Launch — one script that the owner runs in the Terminal: it starts ComfyUI (if not running) with the
  project's model paths, and the studio server; it prints the studio address and the ComfyUI address for watching.
- Reuse and generalise the Sage & Linen scripts: `study/sage-linen/tools/*` (generation, cut-out,
  envelope, manifest, overview sheet, picture checks) and `study/sage-linen/canva/{facts,plan,final_check}.py`
  (design facts, the edit plan, the post-write check); remove the hard-coded ids and paths from them.
- Every check has a control: before believing "zero findings", it must find something deliberately present;
  the picture check must reject deliberately bad files.

### 5.5 A skeleton for development

While there is no own skeleton yet, the studio is built and debugged on the test copy `DAHason1g_M` (a copy of
Ivory Lace for experiments; not for sale). The original `DAHarqlqips` is never edited. When the owner
assembles their skeleton, the first real run goes on it.

### 5.6 Requirements for the own skeleton (so that the studio can read it)

My proposal; the owner will get a separate skeleton specification before assembling it:
- every picture is in a frame or a section background, not embedded in a group with text;
- every personal text is a separate text field;
- the envelope is two layers over the first section (flap and body), as in Ivory Lace;
- the button's link is on the button's top element;
- no text embedded in pictures.

### 5.7 Clarifications after review (my decisions, the owner may change them)

1. **The skeleton map is general, not tied to Ivory Lace.** The `map.json` schema describes any skeleton (slots with a
   locator, type, role, size); Claude builds the map by reading the design, so it does not depend on the
   structure. The first check is on the test copy `DAHason1g_M`; the role-correction screen is mandatory.
2. **Claude's part is half of the product and is part of the deliverable:** the `/studio` skill in the project and the instructions for
   each job type (`map_skeleton`, `style_directions`, `write_texts`, `apply_canva`, `verify`) with
   hard limits and the result format. Writing to the project's `.claude/skills` is blocked by the Bash sandbox —
   creating the skill needs the owner's permission during the build.
3. **Protection of the originals — in code.** For each style `apply_canva` makes a new copy of the skeleton and writes its id into the
   template; all later Canva jobs are allowed only on that id. The studio refuses to create a job if the
   target is the skeleton's id or `DAHarqlqips`; the skill checks the same once more before opening a transaction.
   A test copy for experiments — only if needed, one per skeleton.
4. **One process under the ComfyUI Python** (`/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python`,
   verified 2026-11-20: PIL 12.3.0, numpy 2.5.2). The paths (ComfyUI, models at `/Volumes/WoofData/ComfyUI/models`,
   port) are in one studio config file. The launch script checks that the disk is mounted.
5. **A job stuck in `running/`.** The studio shows the start time; while a Canva job is in `running/`,
   a new Canva job is not created. At start, `/studio` first looks in `running/`: reads the notes and the
   current state of the design, continues or marks `failed` with a reason — as in PLAYBOOK §6 on restarts.
6. **Where the checks run.** The picture checks (aspect ratio, transparency, envelope, deliberately bad files) are
   in the studio. The checks that need Canva reads and a browser (`facts`/`final_check`, contrast on the export,
   the button audit 9/9) are run by Claude in the session with the same Python scripts; the studio shows their result.
7. **`fields.json` and the page notes** are generated by a script from the map (the "personal field" marks) and the
   written texts during `apply_canva`; Claude checks them against the design as read.

## 6. Left to the builder

The server port; the look of the interface; the exact JSON schema of the jobs and the map; how often the studio re-reads the inbox;
how to split the generalised scripts into modules; the look of the overview sheet; the wording of the `/studio` command.

## 7. Not verified — verify, do not promise

1. A background `claude -p` launch sees the Canva connector (a precondition for the button).
2. An automatic skeleton map for a skeleton that does not exist yet: the slot roles on a new skeleton may need
   to be refined by hand — that is why step 0 has a role-correction screen.
3. How much of the limit and time one template takes through the studio.
4. The Canva tool `create-design` as a source of the skeleton — only with the owner's permission (the test will create a design in
   their account).
5. The licence of the Z-Image Turbo model for commercial use — not to be checked: the owner's decision of
   2026-11-21 («не перевіряй ліцензію Z-Image Turbo», "do not check the Z-Image Turbo licence"). Do not research it
   or offer it as a task.
