# style_directions — propose 2-3 visual directions for a template (NO Canva access)

You arrive here from SKILL.md step 1.4: the job is in `jobs/running/`, the precheck printed `"ok": true`; `ROOT`, `CODE`,
`PY`, `ID`, `T` (= the job's `template`), `S` (= its `skeleton`), `BASE` (= `ROOT/templates/T`), `W` (= `BASE/work/ID`) as there.

## Limits

This job does not touch Canva: call no Canva tool, open no design. It writes exactly one file, the result
(`BASE/jobs/ID.result.json`, through the `write_result` snippet), and nothing else: NOT `style.json` (the owner chooses a
direction in the studio, and the studio saves it), NOT the map, NOT any asset. Delete nothing. The job's `limits` say the same.

## What you read first (completely)

1. The job file: `inputs.brief` (the owner's words).
2. `ROOT/skeletons/S/map.json` — the slots and assets the style must cover (a style is valid only against this map).
3. `app/schema.py` `validate_style` (the exact rules) and the shape in DESIGN §5.1 step 1;
   PLAYBOOK §5 Phase 2 "rules for images"; SPEC §1-§3 of the Sage & Linen study
   (`docs/reference/SPEC.md`) as a model of palette roles and image prompts.
4. `BASE/brief.json` if present (same brief) and any earlier result in `BASE/jobs/*.result.json` — do not repeat a rejected look.

## Steps

1. Understand the brief: mood, season, colours the owner named or excluded, anything about fonts or images. Quote the
   constraints you extracted in the notes.
2. Design 2 or 3 clearly different directions (never one, never four). Each is a COMPLETE `style.json` object plus two extra
   keys, exactly:

```json
{"name": "<2-4 words, unique among the directions>", "description": "<2-3 sentences for the owner, Ukrainian>",
 "brief": "<the owner's brief verbatim>",
 "palette": {"<palette role>": "#rrggbb"},
 "colour_roles": {"<slot role of the map>": "<palette role>"},
 "image_prompts": {"<asset name of the map>": "<English prompt>"},
 "fonts": {"heading": "<font>", "body": "<font>", "script": "<font>"},
 "font_map": {"<text slot role of the map>": "heading" | "body" | "script"}}
```

   Rules. `validate_style` (run by `write_result`) enforces ONLY: `palette` is an object whose values are `#rrggbb`; `image_prompts` has a
   non-empty prompt for every asset of the map; `colour_roles` values are palette keys and there is an entry for every role of a colour
   slot of the map; `fonts` has non-empty `heading`, `body`, `script`; `font_map` values are `heading`/`body`/`script`. Everything
   else below is NOT enforced by code: you compute it and report it in the `roles_covered` check (snippet in step 4).
   - `palette`: 5-8 roles (`#rrggbb`, no alpha) with a light colour for text on pictures and a dark ink for text on paper; compute
     the WCAG contrast of any two roles that sit on each other.
   - `colour_roles`: besides the colour-slot roles (enforced), an entry for every text role you want recoloured (a text role without
     an entry keeps the skeleton's colour — say so in the description if intended).
   - `image_prompts`: a prompt for EVERY asset of the map (enforced as non-empty), including the seal and the composed envelope —
     for the envelope write the PAPER/LINEN TEXTURE only: the studio composes flap, body and cover in code. English, plain and
     descriptive. Follow PLAYBOOK §5 Phase 2: no lettering, initials or logos in any picture; subjects in the central third (phones
     show only that); calm mid-dark areas where white text will lie; people only from behind or far away; cut-out assets (kinds
     `watercolour`, `solid`) "on a plain white background"; textures flat and evenly lit.
   - `fonts`: three real font names a buyer can pick in Canva. Fonts are not changed by the connector; the studio gives the owner a
     manual checklist from `fonts`/`font_map`. Availability in Canva's library is unverified: say so in the description.
   - `font_map`: an entry for EVERY text role of the map's text and table-cell slots (not enforced: a missing role shows as "не задано" in the checklist).
3. Write the draft result to `W/result.draft.json`:
   `{"status": "done", "summary": "<Ukrainian>", "outputs": {"directions": [<the 2-3 objects>]}, "checks": [...]}` — the
   UI reads exactly `outputs.directions` (a list of objects with `palette`, `colour_roles`, `image_prompts`, `fonts`,
   `font_map`, `name`, `description`).
4. Checks, each with numbers (compute with a Python call, do not claim):
   - `valid_against_map`: `validate_style` returned `[]` for each direction (`write_result` runs it again and refuses otherwise).
     Control: `validate_style` on a copy of one direction with one prompt removed must return a problem.
   - `roles_covered`: run the snippet below once per direction (save the direction to `$W/direction_<n>.json` first). It prints what
     `validate_style` does not check — palette size 5-8, a light and a dark colour and their contrast, text roles missing from `font_map`,
     text roles without a colour entry — and exits 1 if palette size, light/dark colours or `font_map` coverage fail. Put its printed
     numbers in `detail`; `passed` only if every direction exits 0.
   - `directions_differ` (palettes differ: list each direction's accent colour) and `contrast` (the worst text/background pair per
     direction as a ratio, computed).

```bash
PY=<python path from §0>; CODE=<code folder from §0>; ROOT=<studio root>
$PY -I - "$CODE" "$ROOT/skeletons/$S/map.json" "$W/direction_<n>.json" <<'PYEOF'
# snippet: roles_covered
import json
import sys
from pathlib import Path

m, d = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:4])


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


pal = d["palette"]
ls = sorted(lum(v) for v in pal.values())
light, dark = ls[-1], ls[0]
text_roles = sorted({s["role"] for s in m["slots"] if s["type"] in ("text", "table_cell")})
no_font = [r for r in text_roles if r not in d["font_map"]]
no_colour = [r for r in text_roles if r not in d["colour_roles"]]
problems = []
if not 5 <= len(pal) <= 8:
    problems.append(f"palette has {len(pal)} roles (5-8 wanted)")
if light < 0.6 or dark > 0.2:
    problems.append(f"no light (>=0.6) and dark (<=0.2) pair: lightest {light:.2f}, darkest {dark:.2f}")
if no_font:
    problems.append(f"font_map misses text roles {no_font}")
print(json.dumps({"palette_roles": len(pal), "light_dark_contrast": round((light + 0.05) / (dark + 0.05), 2),
                  "text_roles": len(text_roles), "text_roles_without_font_map": no_font,
                  "text_roles_without_colour_entry": no_colour, "problems": problems}, ensure_ascii=False))
sys.exit(1 if problems else 0)
PYEOF
```

5. `status` `failed` only if the map is missing/invalid (then say so). `summary` (Ukrainian): how many directions, a
   one-line character of each, what is unverified (font availability). Then SKILL §1.5-1.7 (write_result, then file the job).
