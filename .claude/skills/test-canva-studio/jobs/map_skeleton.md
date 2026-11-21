# map_skeleton — read a skeleton design and write its map (READ-ONLY on Canva)

You arrive here from SKILL.md step 1.4: the job is in `jobs/running/`, the precheck printed `"ok": true`; `ROOT`, `CODE`,
`PY`, `ID`, `S` (= the job's `skeleton`), `BASE` (= `ROOT/skeletons/S`), `W` (= `BASE/work/ID`) are as defined there.
The job: `inputs.design_id` = the skeleton's Canva design id (also in `BASE/skeleton.json`); `template` is null.

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
10. One job per `/test-canva-studio`. One writer per design: never run a second Canva job while another is in `running/`.

THIS JOB IS READ-ONLY ON CANVA: the only `edit-design` call you may ever make is `finalize: "cancel"` with no operations,
to end the read transaction. No `commit`, no `operations`, no `copy-design`, no upload. Reading the skeleton design is
what this job is for; `DAHarqlqips` (the purchased original) is never read here either — the precheck refused it.

## What you read first (completely)

1. The job file and `BASE/skeleton.json`.
2. DESIGN §5.3, §5.6, §5.7.1 (`DESIGN.md` in the code folder) and PLAYBOOK §4 Structure
   (`docs/reference/PLAYBOOK.md`); `app/schema.py` `validate_map` (the exact map shape).
3. SPEC §7.2 (the list of places where personal data may stand) in
   `docs/reference/SPEC.md`.

## Steps

### 1. Read the design (once; keep the files)

`read-design`, `design_id` = `inputs.design_id`, `user_intent`, `open_transaction: true`, `filter: {"fields": ["design_content"]}` — the only
way to get element ids and positions. Save the result to `$W/read.json` (the tool saves big results itself; use that path).
IMMEDIATELY end the transaction: `edit-design` with that `transaction_id` and `finalize: "cancel"`.

```bash
ROOT=...; CODE=...; PY=...; S=<skeleton>; ID=<job id>; BASE="$ROOT/skeletons/$S"; W="$BASE/work/$ID"
cd "$CODE" && $PY -I canva/facts.py dump "$W/read.json" "$W/facts.json" && $PY -I canva/outline.py "$W/read.json" "$W/outline.txt"
test -e "$BASE/facts.json" || cp -n "$W/facts.json" "$BASE/facts.json"
```

`BASE/facts.json` is the skeleton's own facts (baseline for the checks of every copy); an existing one is kept (compare:
`$PY -I canva/facts.py diff "$BASE/facts.json" "$W/facts.json" "$W/diff_facts.txt"`; `differing>0` means the skeleton changed
since the first map — say so in the result). Read the outline completely (it ends with totals: element types, fonts, colours,
media ids, unknown keys — an unknown element type is reported in the result, not ignored).

### 2. Export the pages and make the thumbnails

(Every Canva call passes `user_intent`, see SKILL.md §0.) `get-export-formats`, then `export-design` once per page (`format: {"type": "png", "pages": [i]}`, `design_id` = the
skeleton's id; exporting does not change it). Download only those URLs:
`mkdir -p "$W/export" && curl -sS -o "$W/export/page_<i>.png" "<download url>"`. Make the studio's thumbnail of each page
(the studio shows `skeletons/<s>/sections/<page id>.png`; the snippet never overwrites an existing file — then keep it):

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "$W/export/page_<i>.png" "$BASE/sections/<page id>.png" <<'PYEOF'
# snippet: thumbs
import sys
from pathlib import Path

from PIL import Image

src, dest = Path(sys.argv[1]), Path(sys.argv[2])         # full export of one page -> the studio's thumbnail
assert not dest.exists(), f"{dest} exists: thumbnails are never overwritten"
dest.parent.mkdir(parents=True, exist_ok=True)
im = Image.open(src).convert("RGB")
k = min(360 / im.width, 1400 / im.height, 1.0)
im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS).save(dest)
print(f"{dest}: {im.width}x{im.height} -> {Image.open(dest).size}")
PYEOF
```

Slice every export with the `slice` snippet (SKILL.md §3) into `"$W/slices/page_<i>"` and LOOK at every slice (Read; images ≤ 1568 px a side):
what each section is (cover, hero, story, venue, timeline, ...), where pictures, text, calendar, form, embeds and the envelope are.
(PLAYBOOK §4: pages with sections have no thumbnails from the connector; the export is the only way to see.)

### 3. Draft the map from the facts, then complete it

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "$W/facts.json" "$W/outline.txt" "$S" "<design id>" "$W/map_draft.json" <<'PYEOF'
# snippet: draft_map
import ast
import json
import re
import sys
from pathlib import Path

# usage: draft_map.py <facts.json> <outline.txt> <skeleton name> <design id> <out map_draft.json>
facts = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
outline = Path(sys.argv[2]).read_text(encoding="utf-8")
name, design_id, out = sys.argv[3], sys.argv[4], Path(sys.argv[5])
pages = []
for line in outline.splitlines():
    mt = re.match(r"PAGE (\S+) type=\S* title=(.*?) notes=", line)
    if mt:
        try:
            title = ast.literal_eval(mt.group(2))
        except (ValueError, SyntaxError):
            title = mt.group(2)
        pages.append({"index": len(pages) + 1, "id": mt.group(1), "title": title or f"page {len(pages) + 1}"})
assert pages, "no PAGE line in the outline"
assert {p["id"] for p in pages} == {r["page"] for r in facts.values()}, "outline pages differ from the facts' pages"
columns = {}                                         # (page, section) -> the invisible locked rectangles = phone columns
for r in facts.values():
    if r["type"] == "shape" and r.get("opacity", 1) == 0 and r.get("locked"):
        columns.setdefault((r["page"], r["section"]), []).append(r["box"])


def column_px(rec):
    cx = rec["box"][1] + rec["box"][2] / 2
    for t, l, w, h in columns.get((rec["page"], rec["section"]), []):
        if l - 1 <= cx <= l + w + 1:
            return int(round(w))
    return None


def media(rec):
    if rec["type"] == "section":
        return (rec.get("background") or {}).get("media")
    if rec["type"] == "rect":
        return (rec.get("fill") or {}).get("media")
    if rec["type"] == "shape":
        return next((p["fill"]["media"] for p in rec.get("paths", []) if (p.get("fill") or {}).get("media")), None)
    return None


slots, assets, cands, prot = [], {}, [], []
for loc, rec in facts.items():
    t = rec["type"]
    base = {"locator": loc, "role": "unassigned", "personal": False, "column_px": None, "max_len": None, "original": None}
    if t == "text":
        slots.append({**base, "type": "text", "asset": None, "column_px": column_px(rec), "original": rec["text"]})
    elif t == "cell":
        slots.append({**base, "type": "table_cell", "asset": None, "personal": True})
    elif t in ("section", "rect", "shape") and media(rec):
        size = rec["size"] if t == "section" else rec["box"][2:4]
        frame = [int(round(size[0])), int(round(size[1]))]
        asset = f"asset_{frame[0]}x{frame[1]}"
        assets.setdefault(asset, {"kind": "photo", "frame": frame, "role": "unassigned", "transparent": False})
        slots.append({**base, "type": "image", "asset": asset})
    elif t in ("rect", "shape", "line") and rec.get("opacity", 1) != 0:
        cands.append({"locator": loc, "type": t, "box": rec["box"], "locked": rec.get("locked")})
    if t in ("embed", "unsupported", "group"):
        prot.append({"locator": loc, "type": t, "box": rec["box"], "url": rec.get("url"),
                     "children": rec.get("children")})
draft = {"skeleton": name, "design_id": design_id, "pages": pages, "assets": assets, "slots": slots,
         "envelope": None, "protected": [], "keep": [],
         "_colour_candidates": cands, "_protected_candidates": prot}
out.write_text(json.dumps(draft, ensure_ascii=False, indent=1), encoding="utf-8")
kinds = {}
for s in slots:
    kinds[s["type"]] = kinds.get(s["type"], 0) + 1
print(f"draft: {len(pages)} pages, {kinds}, {len(assets)} asset frames, {len(cands)} colour candidates, "
      f"{len(prot)} protected candidates -> {out}")
PYEOF
```

The draft lists EVERY text, table cell and picture of the design as a slot with `role: "unassigned"`, one asset per
distinct frame size, and puts the possible colour slots and protected elements under the keys `_colour_candidates` and
`_protected_candidates`. Edit `$W/map_draft.json` (Write/Edit on that file; never edit the studio's `map.json` by hand) until
`map_check` and `validate_map` are clean. Rules, in order:

1. **Slots (every text and cell)** — `type` `text` or `table_cell`; `original` = the design's current text exactly; `role`
   by what you see: font size, weight, `fontRef`, colour, position. Suggested vocabulary (any non-empty string is valid, but the
   same role must mean the same look, because colours and fonts are chosen per role): `heading`, `script`, `body`, `label`,
   `caption`, `time`, `calendar`, and `..._on_photo` for light text on a picture (`heading_on_photo`, `body_on_photo`,
   `script_on_photo`, `monogram_on_photo`, `date_on_photo`). Delete from `slots` a draft slot that is not editable content
   (a text inside a protected element goes to `protected`, not `slots`).
2. **`personal`** — true only where SPEC §7.2 says personal data stands: names, monogram letters, the wedding date (short and
   long form), the RSVP deadline, venue name and address, timeline rows (time and title), the dress-code line, hotel names and
   their one-line descriptions, the contact e-mail, the gift button label, the calendar cells and month label, the map
   and booking link texts. Paragraphs are never personal. Table cells: true.
3. **`column_px`** — the phone-column width of the text's section; the draft fills it from the section's invisible locked
   rectangle (opacity 0); null when the section has none. **`max_len`** — only for personal single-line fields: an ESTIMATE
   `floor(column_px / (0.6 * fontSize))` (0.7 for all-capitals or wide fonts), table cells 2, paragraphs and multi-line fields
   null. It is an estimate: the stress test of apply_canva measures it; say "estimated" in the notes.
4. **Assets** — rename `asset_<w>x<h>` to meaningful names (`hero`, `paper`, `florals`, `seal`, ...); `kind`: `photo`
   (pictures of people/places), `texture` (paper, linen backgrounds), `watercolour` (decor cut out of white: florals,
   dividers, icons), `solid` (objects with highlights), `composed` (the envelope, built in code); `role` meaningful and not
   `unassigned`; `transparent` true for `watercolour`, `solid` and the envelope's overlay layers; `frame` = the slot's frame in
   whole pixels. Slots that share an asset must have frames of the same aspect (within 0.5 %); otherwise separate assets. One
   composed asset (`envelope`) serves every envelope slot; each such slot carries `"layer": "cover"|"flap"|"body"`. A
   colour slot may carry `"target": "fill"|"stroke"`.
5. **Colour slots** — promote from `_colour_candidates` only what must follow the palette: dividers, rules, frames, button
   frames, cards, swatches, accent shapes; role per kind; never an invisible column rectangle (opacity 0); a section
   background colour cannot be set by the connector (ops.py reports it), so do not rely on it. The calendar's heart marker
   (the small shape lying over a day cell) gets the colour slot role `calendar_marker` — apply_canva moves it onto the wedding
   date and needs to find it by this role.
6. **`protected`** — locators of what must stay exactly as it is: the form (type `unsupported`), every embed, and the envelope's
   overlay groups (promote them from `_protected_candidates`; a protected group's picture children stay image slots with a
   `layer`, because their pictures ARE replaced). **`keep`** — texts intentionally left as they are (a lone "&", "•",
   a numeral); default empty; every one named with its reason in the notes. Every text of the design must end up a slot,
   protected, or in `keep` (the coverage rule).
7. **`envelope`** — null when the skeleton has no opening animation; otherwise
   `{"section_px": [w, h], "tip": [x, y], "left_top": [x, y], "right_top": [x, y], "seal_centre": [x, y], "seal_size": [w, h],
   "seal_rot_canva": r, "seal_asset": "<seal asset>"}` in the envelope section's own coordinates. `section_px` = that
   section's size; `seal_*` = the seal picture's own record (box centre, box width/height, `rotation` as Canva reports it).
   `tip` (the flap's lowest point where its two edges meet), `left_top` and `right_top` (where the edges reach x = 0 and
   x = section width) are pixels of the exported closed envelope, not data: measure them on the export of that section
   (crop and enlarge with Pillow, read the pixel, divide by the export's scale = export width / section width), draw the
   three lines on a copy of the slice and look until they follow the flap edges. Say "envelope geometry measured on an
   export, unverified by the studio's composer" in the result.
8. `pages` (from the outline, 1-based `index`), `skeleton`, `design_id` stay as drafted; delete the two `_...` keys when done.

### 4. Validate (every check must pass; each has its own control)

```bash
cd "$CODE" && $PY -I canva/protected.py "$W/map_draft.json" "$BASE/facts.json" "$BASE/facts.json" "$W/protected_selfcheck.txt"
```

Exit 0 (its control fails when a protected locator does not exist in the design). And:

The `map_check` snippet (SKILL.md §3), arguments `"$CODE" "$W/map_draft.json" "$BASE/facts.json"`:

Exit 0 required: `validate_map` clean, every slot exists in the design with the right element type, `original` equals the
design's text, no role still `unassigned`, no draft key left, every text is a slot / protected / `keep` (`uncovered` 0), the map's
pages are the design's pages. Control: the same snippet on the unedited `map_draft.json` must fail (it has `unassigned`
roles) — run it once on the draft BEFORE editing and note that it failed.

### 5. Store the map

An existing `map.json` (the owner may already have corrected roles in the studio) is kept as `map.<UTC>.prev.json`; the
snippet validates and writes atomically:

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "$CODE" "$ROOT" "$S" "$W/map_draft.json" <<'PYEOF'
# snippet: store_map
import dataclasses
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CODE, ROOT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
SKELETON, DRAFT = sys.argv[3], Path(sys.argv[4])
sys.path.insert(0, str(CODE))
from app import schema
from app.config import load_config
from app.store import read_json, skeleton_dir, write_json_atomic

cfg = dataclasses.replace(load_config(ROOT / "config.json"), root=ROOT)
sdir = skeleton_dir(cfg, SKELETON)
draft = json.loads(DRAFT.read_text(encoding="utf-8"))
assert schema.validate_map(draft) == [], schema.validate_map(draft)
assert draft["skeleton"] == SKELETON and not [k for k in draft if k.startswith("_")], "wrong skeleton name or leftover draft keys"
skeleton_id = read_json(sdir / "skeleton.json")["design_id"]
assert draft["design_id"] == skeleton_id, f"map design_id {draft['design_id']!r} differs from skeleton.json {skeleton_id!r}"
dest = sdir / "map.json"
if dest.exists():                                    # the owner may have corrected roles in the studio: keep that version
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(sdir / f"map.{stamp}.prev.json", "xb") as out:
        out.write(dest.read_bytes())
write_json_atomic(dest, draft)                       # temp file + rename
print(f"stored {dest}: {len(draft['slots'])} slots, {len(draft['assets'])} assets, {len(draft['protected'])} protected, keep {len(draft.get('keep', []))}")
PYEOF
```

### 6. Result

`outputs`: `design_id`, `pages` (count), `slots` (`{"text": n, "table_cell": n, "image": n, "colour": n}`), `assets` (count),
`protected` (count), `keep` (count), `envelope` (true/false), `thumbnails` (list of the files written or kept),
`uncovered_texts` (0), `unknown_element_types` (from the outline totals), `facts_file` (`skeletons/<s>/facts.json`),
`manual_steps` (Ukrainian strings: «Перегляньте ролі слотів на екрані скелета й виправте помилки» — the role-correction
screen is mandatory, DESIGN §5.7.1 —, and what you could not decide). Checks: `read_only` (the number of `edit-design`
calls you made, all `cancel`, zero operations), `map_valid`, `map_check` (slots, uncovered), `protected_selfcheck`,
`thumbnails` (files = pages), `envelope_geometry` (passed only if you looked at the three lines on the slice; else
failed with "not measured"). `status` `done` only if all pass. `summary` (Ukrainian): slots by type, assets, what is
estimated (max_len, envelope) and unverified. Then SKILL §1.5-1.7.
