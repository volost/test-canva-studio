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
   (`/Users/volost/GitRepos/canva/study/sage-linen/SPEC.md`) as a model of palette roles and image prompts.
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

   Rules (each is checked by `validate_style`, so they are not optional):
   - `palette`: 5-8 roles with `#rrggbb` values (6 hex digits, no alpha). It must contain a light colour for text on
     pictures and a dark ink for text on paper; check contrast numerically if two roles sit on each other (WCAG ratio, compute it).
   - `colour_roles`: an entry for EVERY role that occurs in a colour slot of the map, and for every text role you want
     recoloured (text roles without an entry keep the skeleton's colour — say so in the description if intended). Every value is a
     key of `palette`.
   - `image_prompts`: a prompt for EVERY asset of the map (`map.assets` keys, including the seal and the composed envelope —
     for the envelope write the PAPER/LINEN TEXTURE only: the studio composes flap, body and cover in code). English, plain
     and descriptive. Follow PLAYBOOK §5 Phase 2: no lettering, initials or logos in any picture; subjects in the central
     third (phones show only that); calm mid-dark areas where white text will lie; people only from behind or far away;
     cut-out assets (kinds `watercolour`, `solid`) "on a plain white background"; textures flat and evenly lit.
   - `fonts`: three real font names a buyer can pick in Canva. Fonts are not changed by the connector; the studio gives the
     owner a manual checklist from `fonts`/`font_map`. Availability in Canva's library is unverified: say so in the description.
   - `font_map`: an entry for EVERY text role of the map's text and table-cell slots.
3. Write the draft result to `W/result.draft.json`:
   `{"status": "done", "summary": "<Ukrainian>", "outputs": {"directions": [<the 2-3 objects>]}, "checks": [...]}` — the
   UI reads exactly `outputs.directions` (a list of objects with `palette`, `colour_roles`, `image_prompts`, `fonts`,
   `font_map`, `name`, `description`).
4. Checks, each with numbers (compute with a Python call, do not claim): `valid_against_map` (`validate_style` returned `[]` for
   each direction — `write_result` runs it again and refuses otherwise), `roles_covered` (colour slot roles / text roles /
   assets covered, counts), `directions_differ` (palettes differ: list each direction's accent colour), `contrast`
   (the worst text/background pair per direction as a ratio). Control for `valid_against_map`: run `validate_style` on a copy of
   one direction with one prompt removed — it must return a problem.
5. `status` `failed` only if the map is missing/invalid (then say so). `summary` (Ukrainian): how many directions, a
   one-line character of each, what is unverified (font availability). Then SKILL §1.5-1.7 (write_result, then file the job).
