# Playbook: generating Canva wedding website templates with Claude Code

For a Claude Code session that works for another person. It describes a pipeline that was run end to end
once (November 2026): one new visual design of a multi-section Canva wedding website with an "envelope reveal"
opening, built from a skeleton design, with locally generated images, checked in Canva's preview on phone and
desktop, plus a buyer's editing guide. Everything below is what that run established; what it did **not**
establish is listed in section 11 — do not present those points as known.

Read this file in full before starting. Reply to your user in their language. Where this file and your user's
own instructions disagree, your user's instructions win.

---

## 1. What you can and cannot automate

**Automated by you:** studying a skeleton design, writing a style spec, generating and composing every image,
replacing every image, text and colour in a copy of the skeleton, making the copy easy to personalise,
measuring the result, checking it in Canva's preview, drafting and verifying the buyer's guide.

**Always manual, in the Canva editor, by the human:** fonts for newly added text, the address inside an embed
(music video, countdown), links that sit on images, the colours of Canva's form, adding sections, animations,
creating the template link buyers receive (a paid Canva feature), publishing.

**Consequence:** you do not build a website from nothing. You copy a **skeleton** — a Canva website design that
already has the pages, sections, styled text boxes, form, embeds, links and animations — and replace its content.

**Before any work, settle the skeleton's origin with your user.** A design built on a copy of someone else's
purchased template is a derivative of that product: fine as a private exercise, not something to sell unless the
template's licence allows it. For templates meant for sale the user needs their own skeleton (built by hand
once) or a licence that permits resale of modified versions. Never hand anyone a copy of a purchased template.

## 2. Ground rules (they are why the run worked)

1. **A source tells you what something is; only a run tells you what it does.** "The link works", "the envelope
   opens", "it fits on a phone" are claims about behaviour: check them in the full-size preview, not in the data.
2. **Every instrument needs a known-answer control in the same run.** A search that finds nothing must first
   find something you know is there; a checker must be shown to fail on a deliberately bad input.
3. **Measure, do not eyeball.** Aspect ratios, overlaps, contrast, click areas: compute them. In the run a hero
   photo that looked too bright measured 6.7:1 contrast and was fine; a button that looked fine was clickable
   on only 6 of 9 points.
4. **A subagent's report is a claim.** Spot-check the load-bearing statements yourself (open two or three
   exported slices, re-read the saved design, re-run one check).
5. **One design, one writer.** Never let two agents edit the same Canva design at the same time; the later save
   overwrites the earlier one. Images (local) and texts (Canva) can run in parallel; two Canva passes cannot.
6. **Never touch the original.** Work on copies. Keep one disposable "probe copy" for experiments that may break
   things. Do not open an editing transaction on the original; reading it needs a transaction, so cancel it.
7. **Never publish, never submit the form, never type credentials, never change account settings.** If a
   sign-in page appears, ask the human to sign in themselves in the browser pane.
8. **Deleting is the human's decision.** Rejected generations and old exports stay on disk.
9. **Report honestly.** State what was verified, how, and what was not. Keep "unverified" visible in summaries.

## 3. What you need

| Need | Notes from the run |
|---|---|
| Claude Code with the **Canva connector** (MCP) | Tools used: search-designs, read-design, edit-design, copy-design, export-design, get-export-formats, create-upload-url, get-assets, help. They are deferred tools: load them with ToolSearch. |
| A **browser Claude can drive** (built-in browser pane or the Chrome extension), signed in to Canva by the human | Needed for the full-size preview. The sign-in is lost when the computer restarts — ask again. |
| **Local image generation** | Used: ComfyUI started headless with the Z-Image Turbo model (8 steps, cfg 1, sampler `res_multistep`, scheduler `simple`, AuraFlow shift 3, text encoder type `lumina2`), driven over its HTTP API (`/prompt`, `/history/<id>`). Any model that follows plain descriptive prompts will do. |
| **Python with PIL and numpy** | The system Python may have neither; ComfyUI's own virtual environment has both. Run scripts with `python -I`. |
| A **Canva account** | The free plan is enough to build and preview. The template link for buyers and Autofill need a paid plan. |
| A **skeleton design** in that account | See section 1. |
| **Usage budget** | Measured on one account: about 8 % of a weekly limit on the largest subscription tier for one template, about 7 % more for verifying the buyer's guide; wall time about 2 h 15 min for the template. On smaller tiers this may not fit in a week. Use a fresh session per phase and subagents with their own context; a single long conversation is the expensive way. |

Environment facts worth checking first on macOS: a sandboxed shell may hide the GPU and block connections to
`localhost`, so the ComfyUI server and its client must run outside the sandbox (the human approves each such
command). If models live on an external disk, confirm it is mounted before starting. The first image after a
server start took about 14 minutes (model loading); later ones 0.5–4 minutes.

## 4. How Canva websites and the connector behave (verified)

**Structure**
- A website design has several website pages. A page made of stacked sections is reported as type
  `concatenated_fixed` with sub-pages, each 1366 px wide. An element's locator is
  `<page id>-<section id>-<element id>` (with the group id in between for a group's child).
- Copies keep every element id of the source, so a slot table written for a skeleton works on all its copies.
- A design made for phones puts content in a narrow central column and marks it with an invisible, locked
  rectangle per section. In phone preview that column fills the screen; body text sizes in the editor differ
  between sections precisely because columns of different width are scaled to one screen.

**The connector can**
- replace a section background, an image in a frame (also a locked one) and a photo inside a shape mask
  (`update_fill`);
- replace text keeping its font (`replace_text`); the box grows downward and neighbours do not move;
- set text colour, size, alignment and links on text (`format_text`), resize and move elements;
- recolour shapes, lines and single-colour vector library elements;
- edit table cells (a calendar), including empty ones, keeping the table's font;
- move a form (reported as type `unsupported`) and an embed;
- insert Canva library elements by their id, insert shapes, add text;
- change stacking order (`layer_element` front/back);
- write page notes (`replace_speaker_notes`) — works on website pages.

**The connector cannot**
- add a section to an existing page (`add_page` creates a new website page), resize a section, delete a page;
- choose a font (`add_text` gives Canva's default font — so reuse existing styled text boxes instead);
- add or edit forms, embeds, animations, or links that sit on images;
- recolour raster library icons, the second colour of a two-colour vector, the form, the countdown widget;
- show you links on elements or animations at all.

**Gotchas that cost time**
- **`update_fill` is not an exact cover crop.** It leaves the image box about 11 px larger than the frame on
  every side (a seal came out 14 % enlarged and cut). Follow every `update_fill` with `crop_media` to the
  computed cover box, then read back and compare.
- Results for a big page (about 120k characters) are not shown; they are saved to a file. Parse that file
  (see `tools/outline.py`, `tools/probe_diff.py`). Never trust an "applied" status without the diff.
- Pages with sections return **no thumbnails**. To see a result: commit → `export-design` PNG → download →
  slice (`tools/slice_page.py`) → look at slices no larger than about 1500 px.
- The PNG export hides whatever is under an overlay (the hero under the envelope) and renders pictures about
  1 px softer and shifted; judge pixel-exact alignment in the preview, not in the export.
- `get-assets` refuses images uploaded by another account and returns library elements — a quick way to tell
  whose an image is.
- Uploading a local file: `create-upload-url`, then one `curl -X POST -H "Content-Type: application/octet-stream"
  --data-binary @file "<url>"`; expect HTTP 201 and a media id. One URL per file.
- Canva's Help Center answers (the connector's `help` tool) were wrong about embeds twice. Where the editor and
  the Help Center disagree, the editor wins.

**Behaviour found in the preview and the editor**
- The small preview panel beside the editor is static: the envelope stays closed and nothing reacts to clicks.
  Only the **expanded, full-size preview** behaves like the site. Humans mistake the panel for a broken site.
- The opening is an on-load animation of two full-section images lying over the first section (flap on top,
  body below). Replace only their image fills; never regroup, delete or reorder them.
- All texts of the first section lie under that overlay. A buyer edits them through Position → Layers: click
  the text in the list, click the page once, click the text in the list again, press Enter.
- A link lives on one element of a button (in the skeleton used: on the frame image for some buttons). An
  element lying above it swallows clicks even where it is transparent. The linked element must be on top.
- Changing an embed's address through its "Edit link" field works, but Canva resets the embed's size and
  transparency and may move it to the front; the buyer's guide must give the values to restore.
- In phone preview only links near the visible area exist in the page; audit links in desktop preview.

## 5. The pipeline

Keep one folder per style, e.g. `<project>/<style>/` with `SPEC.md`, `assets/`, `gen/`, `tools/`, `canva/`
(notes and exports of each pass). Each agent leaves a notes file for the next one.

### Phase 0 — check the environment (lead, 10 minutes)
Connector tools load; the reference design is found by `search-designs`; the image server starts and produces
one test image; Python has PIL; the browser shows the Canva editor, not a sign-in page. Tell the user plainly
what is missing instead of working around it.

### Phase 1 — study the skeleton (once per skeleton)
1. `read-design` with an editing transaction (the only way to get positions and ids), page by page; save the
   results; **cancel the transaction**. Produce a one-line-per-element outline with `tools/outline.py`.
2. Export every page to PNG, slice, look at every section.
3. If the template came with a PDF guide, extract its text and links (`tools/pdf_dump.swift` on macOS) — it
   explains the interactive parts. Treat its steps as claims.
4. Make a **probe copy** and test on it each connector operation you plan to use; commit; open the full-size
   preview and confirm that links, the opening animation, embeds and the form survived a connector save.
5. Find out which overlay child is the flap and which the body (hide one with `update_opacity 0` on the probe
   copy, export, look; restore).
6. Write the result down: structure, layout principles, type roles, image roles with frame sizes, interactive
   parts, what the connector can do, what is unverified. `examples/BLUEPRINT_EXAMPLE.md` shows the form.

### Phase 2 — write the style spec (lead)
One file, `SPEC.md`; `examples/SPEC_EXAMPLE.md` is the model. It must contain:
- the look in three sentences and a palette with roles;
- rules for every image (below);
- an asset table: file → frame size → how it is made → what it shows;
- exact geometry of composed pieces (the envelope) in section coordinates;
- the slot table: element id → file or colour;
- sample data used consistently (names, date, venue, hotels, contact) and the calendar layout for that month;
- the configurability rules (Phase 5).

Rules for images: every final file has exactly its frame's aspect ratio (photos centre-cropped, transparent
decor **padded**); subjects sit in the central third, because phones show only that; areas under white text are
mid-dark and calm; people from behind or far away; no lettering or initials in any image; watercolour pieces on
white become transparent by un-mixing from white, solid objects with highlights by flood-filling the
background from the borders (un-mixing would make highlights see-through).

### Phase 3 — images (one agent; runs in parallel with Phase 4)
Generate textures first, then cut-out objects, then decor, then photos. Compose geometry-critical pieces
(envelope cover, its two overlay layers, cards) **in code** from generated textures — a model will not place a
flap tip on an exact pixel. Write one check script that asserts, for every file: it opens, its aspect matches
the frame within 0.5 %, transparent files really have alpha, the two overlay layers stacked reproduce the cover
and leave no transparent pixel — and include deliberately bad inputs to show the checker can fail. Deliver a
manifest (prompt, seed, processing per file) and a labelled contact sheet. The lead looks at the contact sheet
and at the closed envelope before anything goes to Canva.

### Phase 4 — wording and colours (one agent, on a fresh copy of the skeleton)
Copy the skeleton, rename the copy. Replace every sentence with new wording of similar length; set text
colours; recolour dividers, frames, lines, cards, swatches; rebuild the calendar and move its marker. After
each batch run the diff; after the pass commit, export, slice, look at every section. No images in this pass.

### Phase 5 — configurability (one agent, same copy, after Phase 4)
The person who buys the template must be able to change names, dates, addresses and the rest without
redesigning. Rules that worked:
1. Every personal detail is live text, never part of an image.
2. Personal details appear only where the design needs them; paragraphs carry no names, dates or place names.
3. Single-line fields of varying length get a text box as wide as the section's phone column, centred, so a
   longer value does not wrap.
4. A stress test with long values (long names, a long venue, a long address, a long hotel name): nothing wraps
   unexpectedly, overlaps or leaves the column; then restore the samples and prove the restore with a diff.
5. Each website page carries a short editing checklist in its notes.
6. Every button reacts over its whole area (link audit in Phase 7).
7. Deliver `fields.json` (every editable field: where, element ids, sample value, how it is edited, maximum
   length) and a text guide for the buyer.

### Phase 6 — placing the images (one agent, same copy, after Phases 3 and 5)
Upload the files, checking each against the manifest; `update_fill` + `crop_media` per slot; then measure:
- **no old image left** — search the final read for every media id of the skeleton's own images, with the same
  search on the pre-pass read as the control;
- **envelope continuity** — the exported closed overlay equals the cover page plus the seal;
- **cards and frames** — text lies inside its card with margins;
- **white text on photos** — contrast under the letters, mean and worst tenth.
Fix and repeat until clean.

### Phase 7 — the lead's own check in the full-size preview
Phone view: cover, a real click on the linked element, the opening, every section, the form, the last button
back to the cover. Desktop view (set the viewport to about 1440 × 810): cover, opening, and the link audit:

```js
// run in the expanded desktop preview on the main page
const sleep = ms => new Promise(r => setTimeout(r, ms));
let sc = null, best = 0;
for (const el of document.querySelectorAll('*')) {
  const s = el.scrollHeight - el.clientHeight;
  if (s > best && /auto|scroll/.test(getComputedStyle(el).overflowY)) { best = s; sc = el; }
}
const res = {}, step = Math.round(sc.clientHeight * 0.55);
for (let y = 0; y <= sc.scrollHeight; y += step) {
  sc.scrollTop = y; await sleep(300);
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.getAttribute('href') || '';
    if (href === '#' || href.startsWith('/') || href.includes('canva.com') || href.includes('navigator')) continue;
    const r = a.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.top < 70 || r.bottom > innerHeight - 10) continue;
    const key = href.slice(0, 30) + '@' + Math.round((r.y + sc.scrollTop) / 30);
    if (res[key]) continue;
    let hit = 0;
    for (let i = 1; i <= 3; i++) for (let j = 1; j <= 3; j++) {
      const el = document.elementFromPoint(r.x + r.width * i / 4, r.y + r.height * j / 4);
      if (el && el.closest('a') === a) hit++;
    }
    res[key] = {href: href.slice(0, 40), w: Math.round(r.width), h: Math.round(r.height), hit: hit + '/9'};
  }
}
sc.scrollTop = 0;
Object.values(res)
```

Every link must score 9/9. A lower score means an element lies above the linked one: bring the linked element
to the front with `layer_element`, commit, reload the editor, re-run. A button that does not appear in the list
has no working link at all — say so.

### Phase 8 — the buyer's guide
Draft it from `fields.json`, then verify every step: menu names against the editor in the buyer's language
(switching the interface language is an account setting — the human does it), mechanics by test edits on the
probe copy. Mark what you could not run. Only then lay it out as a PDF with screenshots.

### Phase 9 — hand the human the manual list
After a copy, the embeds and image links still point to the skeleton author's samples. The human replaces: the
countdown address, the music video address, the map link, the gift link, the booking links; sets form colours;
changes fonts if the style needs others; creates the template link; publishes. Give exact steps for each.

## 6. Orchestration

- Phases 3 and 4 run in parallel; 5 follows 4; 6 follows 3 and 5; 7 is the lead's.
- Give each agent a fresh context and a brief that contains: what to read first (files, not retyped content),
  facts already established ("do not re-derive"), tools and how to load them, numbered steps, hard limits,
  and the report format. Ask for honesty per item: good / acceptable / weak and why.
- Hard limits that belong in every Canva brief: which design to edit; never the original; no form, embed or
  overlay-structure changes; no regrouping, no new pages; never publish; no other agents; no deletions;
  "if a connector call fails twice the same way, stop retrying it, note it, move on".
- If the machine restarts mid-run: check what is on disk and in Canva, restart the image server, and resume
  each agent with a message stating exactly what you verified (files present, design state, lost transactions).
- Read the usage figure before starting each agent and respect the user's reserve.

## 7. Deliverables per template

- the Canva design (a copy of the skeleton with every image, sentence and colour replaced);
- `SPEC.md`, the image set with manifest and contact sheet, the generation scripts;
- `fields.json` and the buyer's guide (text, then PDF);
- exported page images and the list of checks with their numbers;
- the manual list for the human, and the list of what is unverified.

## 8. Pitfalls met in the run

| Symptom | Cause | What to do |
|---|---|---|
| "The envelope does not open" | The human looked at the static side preview panel | Use the expanded preview; say so in the guide |
| Image enlarged or cut after replacement | `update_fill` leaves a bleed | `crop_media` to the exact cover box |
| Clicking a button's label does nothing | Label lies above the linked frame | `layer_element` front on the linked element; audit 9/9 |
| A button has no link at all | Skeleton shipped it that way, or the link sits on text under a frame | Tell the human to put the link on the top element |
| Countdown shows zeros | It is the skeleton author's sample timer | Human creates their own timer and pastes its address |
| Embed changed size or became visible after its address was edited | Canva resets size, transparency, layer | Restore width, transparency, "To back"; put the values in the guide |
| Text overlaps after rewording | Box grew downward, neighbours stay | Keep lengths close; check heights in the returned data |
| Long name wraps | Narrow text box | Widen boxes to the phone column; state the maximum length |
| Search finds no designs / no links | Tool limits, lazy rendering | Run a control that must find something |
| Generation "works" but nothing appears | Server not reachable from the sandbox, models not mounted | Read the server log and the output folder, not the exit code |
| Sign-in page instead of the editor | Session lost (restart) | Ask the human to sign in in the browser pane |
| Menu names in the guide do not match | Taken from another seller's PDF or the Help Center | Read them on screen in the buyer's interface language |

## 9. Files in this package

- `tools/outline.py` — one line per element from a read-design or edit-design result.
- `tools/probe_diff.py` — what an edit really changed, with each operation's status.
- `tools/slice_page.py` — cut a tall exported page into viewable slices.
- `tools/pdf_dump.swift` — text, links and page images of a PDF with macOS PDFKit.
- `tools/comfy_generate.py`, `tools/white_to_alpha.py` — image generation client and watercolour cut-out.
- `tools/assets/` — the scripts one run used to compose the envelope, the card and the textures, to cut out
  solid objects, to build the manifest, the contact sheet and the checks. They are examples written for one
  style; read them before reuse. Paths inside are placeholders.
- `examples/` — the style spec, the skeleton study, the field list and the buyer's guide from that run.
  Element ids in them belong to one specific skeleton and are meaningless for another.

## 10. Numbers from the run (one template, one account, one day)

- 21 image files in 36 frames; 18 generations, 29 minutes of generation after a 14-minute model load.
- 55 of 75 texts reworded, 19 text boxes widened, 52 editable fields listed.
- Wall time about 2 h 15 min including a 16-minute interruption; four agent passes plus the lead's check.
- The buyer's guide: 18 doubtful steps found, all settled or removed in two further passes.

## 11. Not established — do not claim

- A second template has not been built: the 1.5–2 hour estimate for the next one is an estimate.
- No own skeleton was built from scratch; only a copy of a purchased template was restyled.
- The designed PDF guide with screenshots was not produced.
- Whether the remaining Canva library elements (icons, frames) are free or need a paid Canva plan was not checked.
- Marketplace rules for AI-generated images were not checked beyond Canva's own creator programme, which forbids them.
- Sound of the music embed, form submission, and the publish dialog were not exercised.
- Autofill labels were accepted in a draft but never saved or used.
