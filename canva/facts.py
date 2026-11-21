"""Flatten a Canva page JSON into comparable facts, one record per element (and per table cell).

Usage (python -I canva/facts.py ...):
  dump <read_or_edit.json> <facts_out.json> [<page_id>]
      read-design result: every page (or only <page_id>); edit-design result: its one page.
  merge <facts_base.json> <facts_page.json> <facts_out.json>
      replace in base every record of the pages present in facts_page (an edit result holds one page only).
  diff <facts_a.json> <facts_b.json> <report.txt>
      every field that differs per locator (added / removed / changed); full list in the report file.

Facts kept per element: type, page, section, parent group, order, box (top,left,width,height rounded to 0.01),
rotation, opacity, locked, text + per-region formatting, fill colour / media id / image box / recolouring map,
stroke, line stroke + end points, embed url, shape path digest, table cells.
Nothing is skipped silently: unknown element types keep their raw key list.
A record's key is the element's `locator_id` as the connector reports it.
"""
import hashlib
import json
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:  # under `python -I` the script's folder is not on sys.path
    sys.path.insert(0, _ROOT)


def r2(v):
    return round(float(v), 2)


def fmt_regions(trs):
    out = []
    for tr in trs or []:
        f = tr.get("formatting", {})
        out.append({
            "chars": tr.get("characters", ""),
            "color": f.get("color"), "fontRef": f.get("fontRef"), "fontSize": r2(f.get("fontSize", 0)),
            "weight": f.get("fontWeight"), "style": f.get("fontStyle"), "align": f.get("textAlign"),
            "lh": f.get("lineHeight"), "ls": f.get("letterSpacing"), "link": f.get("link"),
            "decoration": f.get("decoration"),
        })
    return out


def fill_facts(f):
    if not f:
        return None
    m = f.get("media")
    res = {"color": (f.get("color") or {}).get("color") if (f.get("color") or {}).get("type") == "solid" else f.get("color")}
    if m:
        ib = m.get("imageBox", {})
        res["media"] = m.get("mediaId")
        res["mediaType"] = m.get("type")
        res["imageBox"] = [r2(ib.get(k, 0)) for k in ("top", "left", "width", "height", "rotation")]
        res["recoloring"] = m.get("recoloring")
    res["flip"] = [bool(f.get("flipX")), bool(f.get("flipY"))]
    return res


def stroke_facts(s):
    if not s:
        return None
    return {"weight": s.get("weight"), "color": (s.get("color") or {}).get("color")}


def element_facts(e, page_id, section_id, parent, order, out):
    loc = e.get("locator_id") or f"{page_id}-{section_id}-{(parent + '-') if parent else ''}{e['id']}"
    t = e["type"]
    rec = {
        "type": t, "page": page_id, "section": section_id, "parent": parent, "order": order,
        "box": [r2(e.get(k, 0)) for k in ("top", "left", "width", "height")],
        "rotation": r2(e.get("rotation", 0)), "opacity": e.get("opacity", 1), "locked": bool(e.get("isLocked")),
    }
    if t == "text":
        rec["regions"] = fmt_regions(e.get("textRegions"))
        rec["text"] = "".join(x["chars"] for x in rec["regions"])
    elif t == "rect":
        rec["fill"] = fill_facts(e.get("fill"))
        rec["stroke"] = stroke_facts(e.get("stroke"))
    elif t == "shape":
        rec["paths"] = [{
            "d": hashlib.sha1(p.get("d", "").encode()).hexdigest()[:12], "dlen": len(p.get("d", "")),
            "fill": fill_facts(p.get("fill")), "stroke": stroke_facts(p.get("stroke")),
            "round": p.get("cornerRounding"),
        } for p in e.get("paths", [])]
        rec["innerText"] = ["".join(tr.get("characters", "") for tr in tc.get("textRegions", []))
                            for tc in e.get("textContents", [])]
    elif t == "line":
        rec["stroke"] = stroke_facts(e.get("stroke"))
        rec["geometry"] = e.get("geometry")
        rec["ends"] = [[(e.get(k) or {}).get("marker"), r2((e.get(k) or {}).get("top", 0)),
                        r2((e.get(k) or {}).get("left", 0))] for k in ("start", "end")]
    elif t == "embed":
        rec["url"] = e.get("url")
    elif t == "table":
        rec["cells"] = len([c for row in e.get("rows", []) for c in row.get("cells", [])])
        for row in e.get("rows", []):
            for c in row.get("cells", []):
                cl = c.get("locator_id") or f"{loc}-{c['id']}"
                regs = fmt_regions(c.get("textRegions"))
                out[cl] = {"type": "cell", "page": page_id, "section": section_id, "parent": e["id"],
                           "cell": c["id"], "regions": regs, "text": "".join(x["chars"] for x in regs),
                           "span": [c.get("rowSpan"), c.get("colSpan")]}
    elif t == "group":
        rec["children"] = [c["id"] for c in e.get("children", [])]
    else:
        # Unknown element types are kept as a key list instead of being dropped: nothing is skipped silently, and a new
        # connector element type shows up in the diff.
        rec["rawKeys"] = sorted(e.keys())
    # A locator is the key of every later comparison (map, ops, checks); two records under one key would hide a change.
    if loc in out:
        raise ValueError(f"duplicate locator {loc}")
    out[loc] = rec
    for i, ch in enumerate(e.get("children", [])):
        element_facts(ch, page_id, section_id, e["id"], i, out)


def page_facts(pg, out):
    subs = pg.get("pages") or [pg]
    for sp in subs:
        sloc = sp.get("locator_id") or f"{pg['id']}-{sp['id']}"
        dm = sp.get("dimensions", {})
        out[sloc] = {"type": "section", "page": pg["id"], "section": sp["id"],
                     "size": [dm.get("width"), dm.get("height")], "background": fill_facts(sp.get("background")),
                     "elements": [e["id"] for e in sp.get("elements", [])]}
        for i, e in enumerate(sp.get("elements", [])):
            element_facts(e, pg["id"], sp["id"], None, i, out)


def pages_of(raw):
    """The page list of a read-design result (design_content.pages) or an edit-design result (document.page)."""
    if isinstance(raw, dict) and "design_content" in raw:
        return raw["design_content"]["pages"]
    if isinstance(raw, dict) and isinstance(raw.get("document"), dict) and "page" in raw["document"]:
        return [raw["document"]["page"]]
    raise ValueError("not a read-design or edit-design result (no design_content and no document.page)")


def dump_facts(raw, only=None) -> dict:
    out = {}
    for pg in pages_of(raw):
        if only and pg["id"] != only:
            continue
        page_facts(pg, out)
    return out


def merge_facts(base: dict, page: dict) -> dict:
    """base with every record of the pages present in `page` replaced by `page`'s records."""
    pages = {v["page"] for v in page.values()}
    kept = {k: v for k, v in base.items() if v["page"] not in pages}
    kept.update(page)
    return kept


def flat(d, prefix=""):
    res = {}
    if isinstance(d, dict):
        for k, v in d.items():
            res.update(flat(v, f"{prefix}{k}."))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            res.update(flat(v, f"{prefix}{i}."))
    else:
        res[prefix[:-1]] = d
    return res


def diff_lines(a: dict, b: dict) -> list:
    """Every field that differs, per locator. The last line is `records a=.. b=.. differing=N`."""
    lines = []
    n = 0
    for k in sorted(set(a) | set(b)):
        if k not in b:
            lines.append(f"REMOVED {k} ({a[k]['type']})")
            n += 1
        elif k not in a:
            lines.append(f"ADDED   {k} ({b[k]['type']}) {json.dumps(b[k], ensure_ascii=False)[:200]}")
            n += 1
        elif a[k] != b[k]:
            fa, fb = flat(a[k]), flat(b[k])
            for f in sorted(set(fa) | set(fb)):
                if fa.get(f) != fb.get(f):
                    lines.append(f"CHANGED {k} [{b[k]['type']}] {f}: {fa.get(f)!r} -> {fb.get(f)!r}")
            n += 1
    lines.append(f"records a={len(a)} b={len(b)} differing={n}")
    return lines


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def main(argv) -> int:
    if not argv or argv[0] not in ("dump", "merge", "diff"):
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "dump" and len(args) in (2, 3):
            out = dump_facts(_load(args[0]), args[2] if len(args) == 3 else None)
            _save(args[1], out)
            kinds = {}
            for v in out.values():
                kinds[v["type"]] = kinds.get(v["type"], 0) + 1
            print(f"dumped {len(out)} records from {args[0]}: {kinds}\nfacts file: {args[1]}")
        elif cmd == "merge" and len(args) == 3:
            base, page = _load(args[0]), _load(args[1])
            merged = merge_facts(base, page)
            _save(args[2], merged)
            print(f"merge: pages {sorted({v['page'] for v in page.values()})} replaced, total {len(merged)} records\nfacts file: {args[2]}")
        elif cmd == "diff" and len(args) == 3:
            lines = diff_lines(_load(args[0]), _load(args[1]))
            Path(args[2]).write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(lines[-1] + f"\nfull diff: {args[2]}")
        else:
            print(__doc__)
            return 2
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
