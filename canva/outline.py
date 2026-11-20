"""Compact outline of a Canva design_content JSON (as returned by read-design) or an edit-design result.

Usage: python -I canva/outline.py <design_content.json> <out.txt>
One line per element, children of groups indented, numbers rounded to whole pixels. Ends with totals (element
counts by type, fonts, colours, media ids, unknown keys) so nothing is skipped silently. The outline goes to
<out.txt>; the console gets the totals line and the file path.
"""
import collections
import json
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from canva.facts import pages_of  # noqa: E402

KNOWN = {"id", "top", "left", "width", "height", "rotation", "opacity", "isLocked", "type",
         "locator_id", "textRegions", "fill", "stroke", "children", "viewBox", "paths",
         "textContents", "nineSlice"}


def _r(v):
    return int(round(v))


def _box(e):
    s = f"t{_r(e['top'])} l{_r(e['left'])} w{_r(e['width'])} h{_r(e['height'])}"
    if abs(e.get("rotation", 0)) > 0.05:
        s += f" rot{e['rotation']:.1f}"
    if e.get("opacity", 1) != 1:
        s += f" op{e['opacity']:.2f}"
    if e.get("isLocked"):
        s += " LOCK"
    return s


def build_outline(raw) -> str:
    pages = pages_of(raw)
    lines = []
    types, fonts, colours, media, seen_keys = (collections.Counter() for _ in range(5))

    def fill_desc(f):
        if not f:
            return "nofill"
        parts = []
        m = f.get("media")
        if m:
            media[m["mediaId"]] += 1
            ib = m.get("imageBox", {})
            parts.append(f"{m['type']}:{m['mediaId']} crop(t{_r(ib.get('top', 0))} l{_r(ib.get('left', 0))} "
                         f"w{_r(ib.get('width', 0))} h{_r(ib.get('height', 0))})")
        c = f.get("color")
        if c:
            if c.get("type") == "solid":
                colours[c["color"]] += 1
                parts.append(c["color"])
            else:
                parts.append("colour:" + json.dumps(c)[:160])
        if f.get("flipX") or f.get("flipY"):
            parts.append(f"flip{'X' if f.get('flipX') else ''}{'Y' if f.get('flipY') else ''}")
        if f.get("isMediaReplaceable"):
            parts.append("repl")
        return " ".join(parts) or "empty"

    def regions(trs):
        res = []
        for tr in trs:
            fm = tr.get("formatting", {})
            fonts[fm.get("fontRef")] += 1
            if fm.get("color"):
                colours[fm["color"]] += 1
            extra = ""
            if fm.get("fontWeight", "normal") != "normal":
                extra += " bold"
            if fm.get("fontStyle", "normal") != "normal":
                extra += " ital"
            if fm.get("decoration", "none") != "none":
                extra += " underl"
            if fm.get("link"):
                extra += f" link={fm['link']}"
            if fm.get("listLevel"):
                extra += f" list{fm['listLevel']}"
            res.append(f"{json.dumps(tr.get('characters', ''), ensure_ascii=False)} "
                       f"[{fm.get('fontSize', 0):.1f}px {fm.get('color')} {fm.get('textAlign')} "
                       f"lh{fm.get('lineHeight')} ls{fm.get('letterSpacing')} font={fm.get('fontRef')}{extra}]")
        return " | ".join(res)

    def walk(e, depth):
        pad = "  " * depth
        t = e["type"]
        types[t] += 1
        for k in e:
            if k not in KNOWN:
                seen_keys[f"{t}.{k}"] += 1
        line = f"{pad}{t} {e['id']} {_box(e)}"
        if t == "text":
            line += " :: " + regions(e.get("textRegions", []))
        elif t == "rect":
            line += " :: " + fill_desc(e.get("fill"))
            st = e.get("stroke") or {}
            if st.get("weight"):
                line += f" stroke{st['weight']}:{st.get('color', {}).get('color')}"
        elif t == "shape":
            vb = e.get("viewBox", {})
            ps = []
            for p in e.get("paths", []):
                st = p.get("stroke") or {}
                d = p.get("d", "")
                ps.append(f"path({len(d)}ch {d[:40]!r}) fill={fill_desc(p.get('fill'))}"
                          + (f" stroke{st['weight']}:{st.get('color', {}).get('color')}" if st.get("weight") else "")
                          + (f" round{p['cornerRounding']}" if p.get("cornerRounding") else ""))
            line += f" :: vb{_r(vb.get('width', 0))}x{_r(vb.get('height', 0))} " + " ; ".join(ps)
            inner = [regions(tc.get("textRegions", [])) for tc in e.get("textContents", []) if tc.get("textRegions")]
            if inner:
                line += " TEXT " + " || ".join(inner)
        elif t == "table":
            n = sum(len(row.get("cells", [])) for row in e.get("rows", []))
            line += f" :: {n} cells"
            for row in e.get("rows", []):
                for c in row.get("cells", []):
                    types["cell"] += 1
                    line += f"\n{pad}  cell {c.get('id')} :: " + regions(c.get("textRegions", []))
        elif t != "group":
            line += " :: KEYS " + ",".join(sorted(k for k in e if k not in KNOWN))
        lines.append(line)
        for ch in e.get("children", []):
            walk(ch, depth + 1)

    n_sections = 0
    for pg in pages:
        lines.append(f"PAGE {pg['id']} type={pg.get('type')} title={pg.get('title')!r} notes={pg.get('notes')!r} "
                     f"editable={pg.get('isEditable')}")
        subs = pg.get("pages") or [pg]
        y = 0
        for i, sp in enumerate(subs, 1):
            n_sections += 1
            dm = sp["dimensions"]
            lines.append(f"\n== SECTION {i} {sp['id']} {dm['width']}x{dm['height']} (site y {y}..{y + dm['height']}) "
                         f"bg: {fill_desc(sp.get('background'))} | elements={len(sp.get('elements', []))}")
            y += dm["height"]
            for e in sp.get("elements", []):
                walk(e, 1)
        lines.append(f"\nTOTAL HEIGHT {y}")
    lines.append("\n-- totals --")
    lines.append(f"sections: {n_sections}")
    lines.append(f"element types: {dict(types)}")
    lines.append(f"fonts: {dict(fonts)}")
    lines.append(f"colours: {dict(colours.most_common())}")
    lines.append(f"media ids: {len(media)} {dict(media)}")
    lines.append(f"unknown keys: {dict(seen_keys)}")
    return "\n".join(lines) + "\n"


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        text = build_outline(json.loads(Path(argv[0]).read_text(encoding="utf-8")))
        Path(argv[1]).write_text(text, encoding="utf-8")
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {type(e).__name__}: {e}")
        return 1
    tail = text.rstrip("\n").splitlines()
    print(f"outline: {len(text.splitlines())} lines; {tail[-6]}; {tail[-5]}\noutline file: {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
