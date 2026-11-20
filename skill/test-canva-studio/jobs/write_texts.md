# write_texts — write the template's English texts (NO Canva access)

You arrive here from SKILL.md step 1.4: the job is in `jobs/running/`, the precheck printed `"ok": true` (style and images
approved, texts waiting); `ROOT`, `CODE`, `PY`, `ID`, `T`, `S`, `BASE` (= `ROOT/templates/T`), `W` (= `BASE/work/ID`) as there.

## Limits

No Canva tool, no design is opened. The only studio files this job writes: `BASE/texts.json` (through the `store_texts`
snippet, which keeps any earlier file as `texts.<UTC>.prev.json` and writes atomically) and the result. Never write
`style.json`, the map, assets or `state.json`. Delete nothing. The job's `limits` say the same.

## What you read first (completely)

1. The job file: `inputs` = `map_file`, `style_file`, `texts_file`, `manifest_file`, `brief` (paths relative to `ROOT`).
2. The map (`app/schema.py` documents its shape): the text slots are the entries with `type` `text` or `table_cell`; each
   has `role`, `personal`, `column_px`, `max_len`, `original`. The style (`name`, `description`, `palette`, `fonts`) and the brief
   set the voice. `app/texts.py` has the exact length rules.
3. SPEC §6-§7 in `/Users/volost/GitRepos/canva/study/sage-linen/SPEC.md` (wording and where personal data may stand) and
   PLAYBOOK §5 Phase 4. The skeleton's own facts `ROOT/skeletons/S/facts.json` (written by map_skeleton) for the calendar.

## Rules (all checked by the snippet or by `app.texts`)

1. Every unprotected text slot gets new English wording — never the seller's sentences. Table cells too (calendar), with `""` in
   unused cells. Slots whose locator is in the map's `protected` list get nothing. Template language is English; the
   brief may be Ukrainian.
2. Length: single-line fields (`max_len` not null): at most `max_len` characters and no line break; every text at most 115 % of its
   `original` (`app.texts.length_warnings` returns the list — aim for 85-105 %, so the layout holds). Paragraphs: similar line count.
3. Personal data ONLY in slots with `personal: true` (SPEC §7.2); paragraphs and non-personal slots carry no names, dates or
   place names. One consistent sample set across the template: couple (two first names, monogram letters = their initials),
   a Saturday wedding date, venue name and address, two hotels, RSVP deadline, timeline times, dress-code line, contact e-mail at
   a reserved domain (`hello@example.com`, never a real address), gift label.
4. Calendar (7 columns Sunday-first): build the cell texts with the snippet below from the real month of the wedding date; it
   first proves its orientation on the ORIGINAL cells (blank, 1..N, blank in reading order) and stops if they do not read that
   way. The month label text slot copies the original label's pattern (same case and separator) for the new month and year.
5. Keep a slot's habit: all-capitals originals stay all-capitals, "&" stays "&" where the design uses it, a time keeps its form.
   Strings are stored exactly as written (curly quotes, accents, `&`, `<`, `>` and line breaks are kept; nothing is escaped).

## Steps

1. Read the map and list the text slots by role and page (a small Python call; print counts).
2. Calendar cells: `year` and `month` of the wedding date you choose, then

```bash
PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python; CODE=/Users/volost/GitRepos/canva/studio; ROOT=<studio root>
$PY -I - "$ROOT/skeletons/$S/map.json" "$ROOT/skeletons/$S/facts.json" <year> <month> > "$W/calendar.json" <<'PYEOF'
# snippet: calendar_cells
import calendar
import json
import re
import sys
from pathlib import Path

# usage: calendar_cells.py <map.json> <facts.json of the skeleton> <year> <month>  -> {cell locator: text} on stdout
m = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
facts = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
year, month = int(sys.argv[3]), int(sys.argv[4])
cells = {}
for s in m["slots"]:
    mt = re.fullmatch(r"(.+)-([A-Z])(\d+)", s["locator"]) if s["type"] == "table_cell" else None
    if mt:
        cells[s["locator"]] = (mt.group(1), mt.group(2), int(mt.group(3)))
assert cells, "the map has no table_cell slots"
tables = {t for t, _, _ in cells.values()}
assert len(tables) == 1, f"several tables in the map: {tables}; run this once per table"
cols = sorted({c for _, c, _ in cells.values()})
rows = sorted({r for _, _, r in cells.values()})
assert len(cols) == 7, f"expected 7 columns (Sunday..Saturday), found {cols}"
order = [(r, c) for r in rows for c in cols]                    # reading order: row by row, left to right
by_pos = {(r, c): loc for loc, (_, c, r) in cells.items()}
assert len(by_pos) == len(order), "the cell grid has holes"


def grid(first_col, ndays):
    out = {}
    for i, pos in enumerate(order):
        d = i - first_col + 1
        out[by_pos[pos]] = str(d) if 1 <= d <= ndays else ""
    return out


# CONTROL: the ORIGINAL calendar must read as a calendar in this orientation (blanks, 1..N, blanks)
orig = [facts[by_pos[p]]["text"] for p in order]
digits = [int(x) for x in orig if x.strip().isdigit()]
first = next(i for i, x in enumerate(orig) if x.strip() == "1")
assert digits == list(range(1, len(digits) + 1)) and all(orig[first + k] == str(k + 1) for k in range(len(digits))), \
    f"the original cells do not read as a calendar in row-major order (A..G across): {orig}"
assert grid(first, len(digits)) == {by_pos[p]: orig[i] for i, p in enumerate(order)}, "control grid differs from the original"
first_col_new = (calendar.weekday(year, month, 1) + 1) % 7      # Sunday-first: Monday=1 ... Sunday=0
out = grid(first_col_new, calendar.monthrange(year, month)[1])
assert max(int(v) for v in out.values() if v) == calendar.monthrange(year, month)[1]
print(json.dumps(out, ensure_ascii=False, indent=1))
print(f"# control ok: original = {len(digits)}-day month starting in column {cols[first]}; "
      f"{calendar.month_name[month]} {year} starts in column {cols[first_col_new]}", file=sys.stderr)
PYEOF
```

   (stdout = `{cell locator: text}` JSON, saved to `W/calendar.json` by the redirect; stderr prints the control line.) A missing
   `facts.json` → `failed/` with "run map_skeleton again (no facts.json)".
3. Write `W/texts.draft.json` (`{locator: text}` for every text/table_cell slot that is not protected; merge in
   `W/calendar.json`) and `W/sample_data.json` (every sample string that stands in personal slots, by kind:
   `{"names": [...], "date": "...", "venue": "...", "address": "...", "hotels": [...], "email": "...", "rsvp": "..."}`), with the Write tool.
4. Store (checks inside: valid against the map, every slot written, no empty text slot, no sample string inside a
   non-personal slot — control: it refuses an incomplete or leaking draft; prints `length_warnings`):

```bash
PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python; CODE=/Users/volost/GitRepos/canva/studio; ROOT=<studio root>
$PY -I - "$CODE" "$ROOT" "$T" "$W/texts.draft.json" "$W/sample_data.json" <<'PYEOF'
# snippet: store_texts
import dataclasses
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CODE, ROOT = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
TEMPLATE, DRAFT, SAMPLE = sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5])    # texts draft, sample_data.json
sys.path.insert(0, str(CODE))
from app import texts as T
from app.config import load_config
from app.store import read_json, skeleton_dir, template_dir, write_json_atomic

cfg = dataclasses.replace(load_config(ROOT / "config.json"), root=ROOT)
tdir = template_dir(cfg, TEMPLATE)
m = read_json(skeleton_dir(cfg, read_json(tdir / "state.json")["skeleton"]) / "map.json")
texts = json.loads(DRAFT.read_text(encoding="utf-8"))
assert T.validate_texts(texts, m) == [], T.validate_texts(texts, m)
json.dumps(texts, ensure_ascii=False).encode("utf-8")                          # lone surrogates fail here, before any write
prot = set(m["protected"])
slots = [s for s in m["slots"] if s["type"] in ("text", "table_cell") and s["locator"] not in prot]
missing = [s["locator"] for s in slots if s["locator"] not in texts]
assert not missing, f"{len(missing)} text slots have no text (the seller's wording would stay): {missing[:5]}"
empty = [s["locator"] for s in slots if s["type"] == "text" and not texts[s["locator"]].strip()]
assert not empty, f"empty text in text slots: {empty[:5]}"
sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
words = [w for v in sample.values() for w in (v if isinstance(v, list) else [v]) if isinstance(w, str) and len(w) >= 4]
assert words, "sample_data.json holds no sample value of 4+ characters: the personal-data rule cannot be checked"
leaks = [(s["locator"], w) for s in slots if s["type"] == "text" and not s["personal"] for w in words
         if w.lower() in texts[s["locator"]].lower()]
assert not leaks, f"sample personal data inside non-personal slots (paragraphs must carry no names, dates or places): {leaks[:5]}"
dest = tdir / "texts.json"
if dest.exists():                                                              # keep the previous version, never overwrite it
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(tdir / f"texts.{stamp}.prev.json", "xb") as out:
        out.write(dest.read_bytes())
write_json_atomic(dest, texts)                                                 # temp file + rename, strings exactly as given
warn = T.length_warnings(texts, m)
print(json.dumps({"stored": str(dest), "texts": len(texts), "personal_leak_words_checked": len(words),
                  "length_warnings": warn}, ensure_ascii=False))
PYEOF
```

   Fix the draft and store again until the printed `length_warnings` is `{}`; a warning you keep must be explained in
   `outputs.length_notes` ({locator: reason}) and in the summary.
5. Result `outputs` (exact keys): `texts` (count), `length_warnings` (the printed dict, ideally `{}`), `length_notes`,
   `sample_data` (the same object as `sample_data.json`), `wedding_date` (`YYYY-MM-DD`), `calendar_marker_cell` (the locator of the
   calendar cell that holds the wedding day — apply_canva moves the heart marker there), `calendar` (month, year, first column).
   Checks: `texts_valid` (`validate_texts` empty, count), `all_slots_written` (n slots / n texts), `length` (warnings 0 or
   explained, numbers), `personal_only` (sample words checked: n, leaks 0), `calendar` (control line, `calendar_marker_cell`
   shows the wedding day number), `voice` (you re-read all texts: tone matches the style `description`, no seller's
   sentence left — say how many you compared with the originals).
   `status` `done` only when all pass. `summary` (Ukrainian). Then SKILL §1.5-1.7.
