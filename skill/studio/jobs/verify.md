# verify — measure the written copy and test it in the full-size preview

You arrive here from SKILL.md step 1.4: the job is in `jobs/running/`, the precheck printed `"ok": true` (so
`target_design_id` equals `canva_copy_id`), `ROOT`, `CODE`, `PY`, `BASE` (= `ROOT/templates/<t>`), `ID`, `W`
(= `BASE/work/ID`) are as defined there. `D` = `target_design_id`.

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

THIS JOB MAKES NO EDITS. It is classified as a Canva write job only so that two Canva jobs never overlap. Open a
transaction only to read, end it with `finalize: "cancel"`, never `commit`, never send `operations`. Publishing is the
owner's action — never publish, share, or create a template link. A defect you find (a button below 9/9, a picture that
looks wrong) goes into the result and `manual_steps`; fixing it is a new apply job or the owner's hand, not this job.

## What you read first (completely)

1. The job file: `inputs` = `map_file`, `style_file`, `texts_file`, `manifest_file`, `chosen` (paths relative to `ROOT`).
2. `BASE/state.json`, `BASE/facts_orig.json` (baseline written by apply; if missing: `skeletons/<s>/facts.json`; if that
   is missing too, the baseline checks fail with that reason — do not re-read the skeleton here).
3. PLAYBOOK §4 ("Behaviour found in the preview and the editor"), §5 Phases 6-7 and §8 pitfalls
   (`/Users/volost/GitRepos/canva/handoff/PLAYBOOK.md`).

## Steps

### 1. Read the copy (read only)

`read-design`, `design_id` = `D`, `user_intent`, `open_transaction: true`, `filter: {"fields": ["design_content"]}`; save the content to
`$W/read.json`; end the transaction at once: `edit-design` with that `transaction_id` and `finalize: "cancel"` (no operations).
Then:

```bash
ROOT=...; CODE=...; PY=...; ID=...; T=<template>; S=<skeleton>; W="$ROOT/templates/$T/work/$ID"; BASE="$ROOT/templates/$T"
cd "$CODE" && $PY -I canva/facts.py dump "$W/read.json" "$W/facts_now.json" && $PY -I canva/outline.py "$W/read.json" "$W/outline_now.txt"
```

### 2. Structural checks on the data (numbers)

1. Declared text-fit size changes: write `"$W/declared_sizes.json"` = the JSON list of locators in `outputs.font_size_changes` of the
   newest `done`/`failed` `BASE/jobs/*-apply_canva.result.json` (`[]` when none). Run the `adjust_sizes` snippet (SKILL.md §3;
   arguments `"$BASE/facts_orig.json" "$W/facts_now.json" "$W/declared_sizes.json" "$W/facts_adjusted.json"`) → one check
   `font_size_changes` (its JSON line goes into the result). Then
   `$PY -I canva/final_check.py "$ROOT/skeletons/$S/map.json" "$BASE/texts.json" "$BASE/facts_orig.json" "$W/facts_adjusted.json" "$W/final.txt" --style "$BASE/style.json" --images`
   and the `to_checks` snippet (SKILL.md §3) → `$W/checks_final.json`. These are checks: texts, formatting, colours,
   protected, coverage, structure, leftovers, images, control (formatting is judged with the declared sizes reset: say so).
2. `old_media` snippet (SKILL.md §3) with the baseline and `$W/facts_now.json` → one check.
3. `$PY -I canva/layout.py "$BASE/facts_orig.json" "$W/facts_now.json" "$W/layout.txt"` → check `layout`: passed iff no `OVERLAP`,
   `COLUMN` or `NEW TEXT` line (`grep -cE '^(OVERLAP|COLUMN|NEW TEXT) ' "$W/layout.txt"` prints 0) and every `AXIS` line names a locator in the apply
   result's `outputs.recentred` (a box deliberately re-centred on the section centre, shift ≤ 6 px).
4. Protected elements: `$PY -I canva/protected.py "$ROOT/skeletons/$S/map.json" "$BASE/facts_orig.json" "$W/facts_now.json" "$W/protected.txt"`
   → check `protected_changes` (violations 0; the form, embeds and envelope groups are untouched).

### 3. Export every page, slice, look

1. (Every Canva call passes `user_intent`, see SKILL.md §0.) `get-export-formats` for `D`; confirm `png` is available and which page numbers.
2. `export-design` for each page number `i` of the map (`pages` in the map, field `index`): `design_id` = `D`,
   `format: {"type": "png", "pages": [i]}` → a download URL. Download only these URLs, only for `D`:
   `mkdir -p "$W/export" && curl -sS -o "$W/export/page_<i>.png" "<download url>"`. Check each file opens
   (PIL) and is not empty. (Note: the PNG export hides what lies under an overlay, renders pictures ~1 px softer and
   shifted: pixel-exact alignment is judged in the preview, not here — PLAYBOOK §4.)
3. Slice each page: for every export run the `slice` snippet (SKILL.md §3) into `"$W/slices/page_<i>"`, then look at
   EVERY slice with Read (no image larger than 1568 px on a side). Judge: text overlapping text or a picture, text cut
   off, text leaving its card, an old picture of the skeleton still visible, an envelope seam between flap and body, the
   heart marker on the wedding date. Record one check `visual_review` with `detail` = the number of slices looked at
   and every defect found (page, slice, what). `passed` only if you saw no defect. Do not say "looks fine" without the number.

### 4. Contrast under light text (PLAYBOOK Phase 6; measured, not eyeballed)

For every page `i` run the snippet below (its control — white on white must read ≈1, white on black ≈21 — runs inside;
it measures light-coloured text boxes against the exported pixels: mean contrast and the worst tenth).
Check `contrast_light_text`: passed iff every page printed a `worst_tenth` ≥ 3.0 (WCAG AA for large text; the playbook gives
no threshold, this is this skill's choice). Put the worst 3 `{locator, text, mean, worst_tenth}` and the minimum in `detail`.
A page with `light_texts` 0 counts as "nothing measured" there, not as a pass; if all pages are 0 the check is failed.

```bash
PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python; CODE=/Users/volost/GitRepos/canva/studio; ROOT=<studio root>
$PY -I - "$W/export/page_<i>.png" "$W/facts_now.json" "$W/outline_now.txt" "<page id>" <<'PYEOF'
# snippet: contrast
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# usage: contrast.py <exported page png> <facts_now.json> <outline.txt> <page id>
png, facts_p, outline_p, page = sys.argv[1:5]
facts = json.loads(Path(facts_p).read_text(encoding="utf-8"))
sections, cur = {}, None                      # section id -> (site y offset, width) for this page, from the outline file
for line in Path(outline_p).read_text(encoding="utf-8").splitlines():
    mp = re.match(r"PAGE (\S+) ", line)
    if mp:
        cur = mp.group(1)
    ms = re.match(r"== SECTION \d+ (\S+) (\d+)x(\d+) \(site y (\d+)\.\.(\d+)\)", line)
    if ms and cur == page:
        sections[ms.group(1)] = (int(ms.group(4)), int(ms.group(2)))
assert sections, f"page {page} not found in the outline"
img = np.asarray(Image.open(png).convert("RGB"), dtype=np.float64) / 255.0
width = next(iter(sections.values()))[1]
scale = img.shape[1] / width


def lum(rgb):
    c = np.where(rgb <= 0.03928, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return c @ np.array([0.2126, 0.7152, 0.0722])


def ratio(l1, l2):
    hi, lo = np.maximum(l1, l2), np.minimum(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def measure(box_px, text_rgb):
    x0, y0, x1, y1 = box_px
    patch = img[max(0, y0):y1, max(0, x0):x1]
    r = ratio(lum(patch.reshape(-1, 3)), float(lum(np.array(text_rgb))))
    return float(r.mean()), float(np.sort(r)[: max(1, len(r) // 10)].mean())      # mean, worst tenth


# CONTROL: the same function must call white-on-white unreadable and white-on-black readable
img_backup = img
img = np.ones((40, 40, 3)); white_on_white = measure((0, 0, 40, 40), (1, 1, 1))
img = np.zeros((40, 40, 3)); white_on_black = measure((0, 0, 40, 40), (1, 1, 1))
img = img_backup
assert white_on_white[0] < 1.1 and white_on_black[0] > 20, (white_on_white, white_on_black)

rows = []
for loc, rec in facts.items():
    if rec.get("type") != "text" or rec.get("page") != page or rec.get("section") not in sections or not rec.get("text", "").strip():
        continue
    col = (rec["regions"][0].get("color") or "") if rec.get("regions") else ""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", col):
        continue
    rgb = tuple(int(col[i:i + 2], 16) / 255 for i in (1, 3, 5))
    if float(lum(np.array(rgb))) < 0.6:           # only light text (white-ish letters on photos / dark paper)
        continue
    off, _ = sections[rec["section"]]
    t, l, w, h = rec["box"]
    box = tuple(int(round(v * scale)) for v in (l, off + t, l + w, off + t + h))
    if box[2] <= box[0] or box[3] <= box[1] or box[3] > img.shape[0]:
        continue
    mean, worst = measure(box, rgb)
    rows.append((worst, mean, loc, rec["text"][:30]))
rows.sort()
print(json.dumps({"page": page, "light_texts": len(rows),
                  "worst": [{"locator": r[2], "text": r[3], "mean": round(r[1], 2), "worst_tenth": round(r[0], 2)} for r in rows[:5]],
                  "control": {"white_on_white": round(white_on_white[0], 2), "white_on_black": round(white_on_black[0], 2)}},
                 ensure_ascii=False))
PYEOF
```

### 5. Full-size preview (PLAYBOOK §4 and Phase 7) — behaviour needs a run

Preconditions: a browser the session can drive (the browser pane tools, or the Chrome extension), signed in to Canva by the
owner. If a sign-in page appears: stop and ask the owner in chat to sign in themselves; never type credentials; if the
owner cannot now, record every preview check below as `passed: false`, `detail: "not run: <reason>"` and finish the job
(then the job's status is `failed` — see step 7 — with every check measured so far in the result, and "run the preview check" in `manual_steps`).
Open the editor `https://www.canva.com/design/<D>/edit` and enter the EXPANDED full-size preview (the small panel beside
the editor is static: the envelope stays closed there — PLAYBOOK §4). If you cannot reach the expanded preview, the
preview checks are "not run", never passed. Take screenshots no larger than 1568 px on a side; prefer reading the page
(accessibility tree / text) over screenshots. Never submit the form (look at it, do not fill or send it).

1. Phone view (emulate a phone viewport, e.g. 375x812, reload after switching): cover; a REAL click on the linked
   element; the opening animation (envelope opens); scroll through every section; the form is present (not submitted);
   the last button returns to the cover. One check each: `preview_phone_cover`, `preview_phone_click`,
   `preview_phone_opening`, `preview_phone_sections` (sections seen / sections in the map), `preview_phone_form`,
   `preview_phone_back`, with what you saw.
2. Desktop view: set the viewport to 1440x810 and reload. Cover, the opening
   (`preview_desktop_cover`, `preview_desktop_opening`), then the button audit: run this JavaScript verbatim in the
   expanded desktop preview on the main page (PLAYBOOK §5 Phase 7):

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

   Check `button_audit_9of9`: save the returned list to `$W/audit.json`. Passed iff the list is not empty AND every entry reads
   `9/9`. Zero entries is a claim about the script first: the control is the links the data says exist — list them with
   `$PY -I -c 'import json,sys; f=json.load(open(sys.argv[1])); print([(k, r["link"]) for k,v in f.items() if v.get("type")=="text" for r in v.get("regions",[]) if r.get("link")])' "$W/facts_now.json"`
   — every text link printed must appear among the audit's `href` values (first 40 characters); links on images are not
   visible to the connector, so they are not part of the control. If the printed list is empty the control proves
   nothing: say so in `detail` and judge the audit from the button labels in `$W/slices` instead. A button missing from the list has no working link:
   say so. Detail = `"N links, M at 9/9; below 9/9: <href@position hit>..."`. A button below 9/9 means an element lies
   above the linked one; the fix (`layer_element` front on the linked element, commit, reload, re-run) is NOT done here:
   write it to `manual_steps`.
3. Everything in the preview that only the owner can judge or do goes to `manual_steps` (never "unverified" as pass).

### 6. Fonts and the manual list

1. Fonts in the design (the connector cannot change them) against the style:
   `$PY -I -c 'import json,sys; f=json.load(open(sys.argv[1])); s=json.load(open(sys.argv[2])); refs=sorted({r.get("fontRef") for v in f.values() if v.get("type") in ("text","cell") for r in v.get("regions",[]) if r.get("fontRef")}); print(len(refs),"font refs in the design:",refs,"| style wants:",s["fonts"])' "$W/facts_now.json" "$BASE/style.json"`
   → check `font_checklist`: passed = the list was produced; detail = the font refs found, the style's three fonts, and the
   number of text slots to replace by hand (`cd "$CODE" && $PY -I -c 'import sys,json; sys.path.insert(0,"."); from app.texts import font_checklist; L=lambda p: json.load(open(p)); print(len(font_checklist(L(sys.argv[1]),L(sys.argv[2]))))' "$ROOT/skeletons/$S/map.json" "$BASE/style.json"`).
   The font checklist table itself is shown by the studio.
2. `manual_steps` (Ukrainian strings, all that apply): replace the fonts by hand per the checklist; replace the countdown
   address, music video address, map link, gift link and the booking links (they still point to the skeleton author's
   samples); set the form colours; every button below 9/9 or not in the audit list (name it); anything in step 5 not run;
   create the template link and publish yourself (never done by Claude).

### 7. Result

Checks (names exactly as above, plus those of `checks_final.json`, `old_media`, `layout`, `protected_changes`,
`visual_review`, `contrast_light_text`, the preview checks, `button_audit_9of9`, `font_checklist`), every `detail` with
numbers. `outputs`: `canva_copy_id` (= `D`), `design_url`, `pages_exported`, `slices`, `contrast` (the printed JSON per page),
`audit` (the list), `manual_steps`, `unverified` (what was not run). `status`: `done` when every check was RUN (a red row
with numbers is a valid result: the owner sees pass/fail); `failed` when any check could not be run (preview not reachable or
not signed in, export failed twice, copy unreadable, a control failed) — the measured checks are still in the result. `summary` (Ukrainian): `N of M checks passed`, the failed ones by name with numbers, what is
unverified. Then SKILL §1.5-1.7. Never publish.
