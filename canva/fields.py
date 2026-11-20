"""fields.json and per-page editing checklists, generated from the skeleton map.

Usage: python -I canva/fields.py <map.json> <texts.json> <out_dir> [--style style.json]
  -> out_dir/fields.json (every slot with personal: true) and out_dir/page_notes.json ({page id: note text}).

`build_fields` lists every personal slot with its page, role, sample value (the written text, else the original),
how to edit it and its limits, plus the protected elements ("do not touch"). `page_notes` is the buyer's editing
checklist for each page (English - the template language), at most 5000 characters (the connector's limit for
replace_speaker_notes): the personal fields to edit, the calendar, the fonts to swap by hand (the connector
cannot choose fonts; with a style the font names are listed), and what to leave alone.
"""
import json
import re
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from canva.maputil import page_index, page_of_locator  # noqa: E402

NOTES_LIMIT = 5000
_HOW = {
    "text": "Select the text and type over it; never delete the box (a new box loses the font, size and animation).",
    "table_cell": "Click the cell in the calendar table and type the day number; leave unused cells empty.",
}


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "field"


def _tail(loc):
    """The last segment of a hand-written locator (`p1/text/names` -> `names`, `...-LBxx-D1` -> `D1`)."""
    return loc.rsplit("/", 1)[1] if "/" in loc else loc.rsplit("-", 1)[-1]


def _page(m, loc):
    pid = page_of_locator(m, loc)
    if pid is None:
        raise ValueError(f"{loc}: cannot tell which page of the map this slot is on")
    return pid


def build_fields(m: dict, texts: dict) -> dict:
    fields, seen, per_role = [], set(), {}
    for s in m.get("slots") or []:
        if not s.get("personal"):
            continue
        loc, typ = s["locator"], s["type"]
        pid = _page(m, loc)
        role = s.get("role") or typ
        if typ == "table_cell":
            key, label = f"{_slug(role)}_{_slug(_tail(loc))}", f"{role.title()} cell {_tail(loc)}"
        else:
            per_role[role] = per_role.get(role, 0) + 1
            key, label = f"{_slug(role)}_{per_role[role]}", f"{role.replace('_', ' ').title()} {per_role[role]}"
        while key in seen:
            key += "_x"
        seen.add(key)
        value = texts.get(loc, s.get("original"))
        fields.append({
            "key": key, "label": f"{label} (page {page_index(m, pid)})",
            "kind": "calendar_cell" if typ == "table_cell" else typ, "locator_id": loc, "page": page_index(m, pid),
            "page_id": pid, "role": role, "sample_value": "" if value is None else value,
            "how_to_edit": _HOW.get(typ, "Edit it in the Canva editor."), "max_len": s.get("max_len"),
            "column_px": s.get("column_px")})
    return {"design": {"skeleton": m.get("skeleton"), "id": m.get("design_id")},
            "conventions": {"locator_id": "<page id>-<section id>-<element id> (table cell: + '-' + cell id)"},
            "counts": {"fields": len(fields), "pages": len(m.get("pages") or [])},
            "fields": fields, "do_not_touch": list(m.get("protected") or [])}


def page_notes(m: dict, style: dict = None, texts: dict = None) -> dict:
    """{page id: checklist text}, each at most NOTES_LIMIT characters. With `texts` each field line shows the
    value written into the design (the sample the buyer replaces); without it no value is quoted - a slot's
    `original` is the skeleton's old wording and must never reach a buyer's note."""
    notes = {}
    for pg in m.get("pages") or []:
        pid = pg["id"]
        mine = [s for s in m.get("slots") or [] if _page(m, s["locator"]) == pid]
        fields, cells, per_role = [], 0, {}
        for s in mine:
            if not s.get("personal"):
                continue
            if s["type"] == "table_cell":
                cells += 1
                continue
            if "/" in s["locator"]:
                name = _tail(s["locator"])
            else:
                role = s.get("role") or s["type"]
                per_role[role] = per_role.get(role, 0) + 1
                name = f"{role.replace('_', ' ')} #{per_role[role]}"
            val = ""
            if texts and texts.get(s["locator"]):
                one = " / ".join(texts[s["locator"]].split("\n")).strip()
                val = f' "{one[:40]}{chr(8230) if len(one) > 40 else ""}"'
            cap = f" (max {s['max_len']} characters)" if s.get("max_len") else ""
            fields.append(f"- {name}{(':' + val) if val else ''}{cap}")
        head = [f"EDITING CHECKLIST - {pg.get('title', pid)} (page {pg.get('index')})",
                "Work on a copy of the design. Change a text by selecting it and typing over it; do not delete a box and add a new one."]
        tail = []
        if cells:
            tail.append(f"Calendar: {cells} cells - type each day number of your month; leave unused cells empty.")
        roles = sorted({s["role"] for s in mine if s["type"] == "text" and s.get("role")})
        if style and roles:
            fm, fonts = style.get("font_map") or {}, style.get("fonts") or {}
            pairs = sorted({f"{fm[r]}: {fonts[fm[r]]}" for r in roles if fm.get(r) in fonts})
            if pairs:
                tail.append("Fonts to swap by hand (Canva's connector cannot change fonts) - select the text, pick the font: "
                            + "; ".join(pairs) + ".")
        elif roles:
            tail.append("Fonts: keep the template's font pair; see the template guide for the names.")
        if any(s.get("layer") for s in mine):
            tail.append("Envelope: the envelope pictures and the seal carry the opening animation and the link - replace their "
                        "images only; never regroup, move or delete them.")
        n_prot = sum(1 for p in m.get("protected") or [] if page_of_locator(m, p) == pid)
        if n_prot:
            tail.append(f"Leave alone: {n_prot} protected element(s) on this page (form, embeds, envelope layers).")
        shown = list(fields)
        while True:
            body = ["Edit these fields:"] + shown if shown else []
            if len(shown) < len(fields):
                body.append(f"- ... and {len(fields) - len(shown)} more: see fields.json")
            text = "\n".join(head + body + tail)
            if len(text) <= NOTES_LIMIT or not shown:
                break
            shown.pop()
        if len(text) > NOTES_LIMIT:
            text = text[:NOTES_LIMIT - 3] + "..."
        notes[pid] = text
    return notes


def main(argv) -> int:
    args = list(argv)
    style_path = None
    if "--style" in args:
        i = args.index("--style")
        if i + 1 >= len(args):
            print(__doc__)
            return 2
        style_path = args[i + 1]
        del args[i:i + 2]
    if len(args) != 3:
        print(__doc__)
        return 2
    try:
        m, texts = (json.loads(Path(x).read_text(encoding="utf-8")) for x in args[:2])
        style = json.loads(Path(style_path).read_text(encoding="utf-8")) if style_path else None
        out = Path(args[2])
        out.mkdir(parents=True, exist_ok=True)
        f, n = build_fields(m, texts), page_notes(m, style, texts)
        (out / "fields.json").write_text(json.dumps(f, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "page_notes.json").write_text(json.dumps(n, ensure_ascii=False, indent=1), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"error: {type(e).__name__}: {e}")
        return 1
    print(f"fields: {f['counts']['fields']}; page notes: {len(n)} ({', '.join(str(len(t)) for t in n.values())} characters)\n"
          f"fields file: {out / 'fields.json'}\nnotes file: {out / 'page_notes.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
