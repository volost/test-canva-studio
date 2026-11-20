"""Plan connector edit operations from a skeleton map, a style, texts and the design's facts; verify a batch.

Pure functions over JSON: no network, no Canva calls. The session sends the batches with edit-design.

Usage (python -I canva/ops.py ...):
  build  <map.json> <style.json> <texts.json> <facts.json> <out_dir>
      text, text colour, calendar cells and colours -> out_dir/ops_<page id>.json
      ({"page_index", "operations"}) + out_dir/ops_notes.txt (everything skipped, and why).
  images <map.json> <uploads.json> <facts.json> <out_dir>
      update_fill + exact-cover crop_media for every image slot with an upload -> out_dir/images_<page id>.json
      uploads.json = {asset or "asset:layer": {"media_id", "pixel_size": [w, h], "alt_text"}}.
  verify <facts_before.json> <facts_after.json> <batch.json> <report.txt>
      first runs its own control (an untargeted change and a wrong expected value must be caught on this very
      data), then checks each operation against the facts after the edit and lists every change nothing asked
      for (exit 1 when there is a finding or the control fails).

Rules the builders keep (DESIGN 3 and 5.2, PLAYBOOK 4-6): a locator in map["protected"] never gets an operation;
replace_text keeps the font (colour is a separate format_text); after update_fill comes crop_media to the exact
cover box; nothing is regrouped, added or deleted; a section background colour is not set (update_fill takes
images only, recolouring a section is unverified) - it is reported in the notes instead.
"""
import copy
import json
import re
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:  # under `python -I` the script's folder is not on sys.path
    sys.path.insert(0, _ROOT)

from canva.facts import flat  # noqa: E402
from canva.geometry import cover_box  # noqa: E402
from canva.maputil import page_ids, page_index, page_of_locator  # noqa: E402

_HEX = re.compile(r"#[0-9a-fA-F]{6}")
TOL_BOX = 0.05       # px: allowed deviation of an image box from the exact cover box
TOL_POS = 0.02       # px: position / size after position_element / resize_element
_FMT_FIELD = {"color": "color", "font_size": "fontSize", "text_align": "align", "font_style": "style",
              "font_weight": "weight", "line_height": "lh", "decoration": "decoration", "link": "link"}


class OpsError(ValueError):
    """The map, style, texts and facts do not fit together; no operation is safe to emit."""


def _lc(c):
    return c.lower() if isinstance(c, str) else c


def palette_colour(style: dict, role: str):
    """The #rrggbb (lower case) a slot role maps to through style["colour_roles"] and style["palette"], or None."""
    pr = (style.get("colour_roles") or {}).get(role)
    if pr is None:
        return None
    c = (style.get("palette") or {}).get(pr)
    if not (isinstance(c, str) and _HEX.fullmatch(c)):
        raise OpsError(f"colour role {role!r} -> palette {pr!r} is not a #rrggbb colour")
    return c.lower()


def colour_state(rec: dict, target: str) -> list:
    """The colours an element currently shows for the `fill` (recolouring map / solid fill) or `stroke` target."""
    t = rec.get("type")
    if target == "stroke":
        if t in ("line", "rect"):
            s = rec.get("stroke")
            return [s["color"]] if s and s.get("color") else []
        if t == "shape":
            return [p["stroke"]["color"] for p in rec.get("paths", []) if p.get("stroke") and p["stroke"].get("color")]
        raise OpsError(f"a {t} has no stroke to colour")
    if t == "shape":
        paths = rec.get("paths", [])
        if any((p.get("fill") or {}).get("media") for p in paths):
            raise OpsError("an image-filled shape cannot be recoloured (use an image slot)")
        return [p["fill"]["color"] for p in paths if p.get("fill") and p["fill"].get("color")]
    if t == "rect":
        f = rec.get("fill") or {}
        if f.get("recoloring"):
            return list(f["recoloring"].values())
        return [f["color"]] if f.get("color") and not f.get("media") else []
    raise OpsError(f"a {t} cannot be recoloured")


def _page_for(m, loc, facts):
    pid = page_of_locator(m, loc, facts)
    if pid is None or pid not in page_ids(m):
        raise OpsError(f"{loc}: its page {pid!r} is not one of the map's pages {page_ids(m)}")
    return pid


def _rec(facts, loc, kinds, what):
    rec = facts.get(loc)
    if rec is None:
        raise OpsError(f"{loc}: {what} slot has no element in the facts (stale map or wrong design)")
    if rec.get("type") not in kinds:
        raise OpsError(f"{loc}: {what} slot points at a {rec.get('type')!r}, expected {'/'.join(kinds)}")
    return rec


def build_ops(m: dict, style: dict, texts: dict, facts: dict, notes: list = None) -> dict:
    """Operations per page id: replace_text / format_text (colour) for text and calendar-cell slots, and
    recolor_element / update_stroke_properties for colour slots. Only what differs from `facts` is emitted, so a
    second run on the written design is empty. Never an operation on a locator in m["protected"]. `notes` (a list)
    receives one line per skipped item. Raises OpsError when the inputs contradict each other."""
    notes = notes if notes is not None else []
    protected = set(m.get("protected") or [])
    slots = m.get("slots") or []
    slot_locs = {s["locator"] for s in slots}
    out = {}

    def emit(loc, op):
        out.setdefault(_page_for(m, loc, facts), []).append(op)

    for loc in texts:
        if loc not in slot_locs:
            notes.append(f"{loc}: texts entry ignored - " + ("protected, no operation emitted" if loc in protected
                                                              else "no slot with this locator in the map"))
    for s in slots:
        loc, typ = s["locator"], s["type"]
        if typ not in ("text", "table_cell", "colour"):
            continue
        if loc in protected:
            notes.append(f"{loc}: protected, no operation emitted ({typ} slot, role {s.get('role')!r})")
            continue
        if typ == "colour":
            _colour_slot(s, style, facts, emit, notes)
        else:
            _text_slot(s, style, texts, facts, emit, notes)
    for page_ops in out.values():
        for op in page_ops:
            assert op["locator_id"] not in protected, f"protected locator reached the batch: {op}"
    return out


def _text_slot(s, style, texts, facts, emit, notes):
    loc = s["locator"]
    kind = "text" if s["type"] == "text" else "cell"
    colour = palette_colour(style, s.get("role"))
    if loc not in texts and colour is None:
        return
    rec = _rec(facts, loc, (kind,), s["type"])
    replaced = False
    if loc in texts:
        new, cur, orig = texts[loc], rec.get("text", ""), s.get("original")
        if not isinstance(new, str):
            raise OpsError(f"{loc}: text must be a string, got {type(new).__name__}")
        if orig is not None and cur != orig and cur != new:
            raise OpsError(f"{loc}: the design holds {cur!r}, the map expects {orig!r}")
        if s.get("max_len") and len(new) > s["max_len"]:
            notes.append(f"{loc}: WARNING text is {len(new)} characters, max_len is {s['max_len']}")
        if cur != new:
            emit(loc, {"type": "replace_text", "locator_id": loc, "text": new})
            replaced = True
        after = new
    else:
        after = rec.get("text", "")
    if colour and after != "":
        cols = {_lc(r.get("color")) for r in rec.get("regions", [])}
        if cols != {colour}:
            emit(loc, {"type": "format_text", "locator_id": loc, "formatting": {"color": colour}})


def _colour_slot(s, style, facts, emit, notes):
    loc = s["locator"]
    rec = facts.get(loc)
    if rec is None:
        raise OpsError(f"{loc}: colour slot has no element in the facts (stale map or wrong design)")
    t = rec["type"]
    if t == "section":
        notes.append(f"{loc}: section background colour not set - update_fill takes images only and "
                     f"recolouring a section is unverified")
        return
    target = s.get("target") or ("stroke" if t == "line" else "fill")
    if target not in ("fill", "stroke"):
        raise OpsError(f"{loc}: unknown colour target {target!r}")
    if t not in ("rect", "shape", "line") or (t == "line" and target == "fill"):
        raise OpsError(f"{loc}: a {t} cannot take a {target} colour")
    want = palette_colour(style, s.get("role"))
    if want is None:
        raise OpsError(f"{loc}: colour role {s.get('role')!r} has no entry in style colour_roles")
    state = colour_state(rec, target)
    if state and all(_lc(c) == want for c in state):
        return
    emit(loc, {"type": "update_stroke_properties", "locator_id": loc, "color": want} if target == "stroke"
         else {"type": "recolor_element", "locator_id": loc, "color": want})


def _frame_wh(rec):
    return rec["size"] if rec["type"] == "section" else rec["box"][2:4]


def build_image_ops(m: dict, uploads: dict, facts: dict, notes: list = None) -> dict:
    """update_fill for every image slot that has an upload, then crop_media to the exact cover box of the uploaded
    picture in the slot's frame (update_fill alone leaves the box ~11 px too big). Per page id."""
    notes = notes if notes is not None else []
    protected = set(m.get("protected") or [])
    fills, crops = {}, {}
    for s in m.get("slots") or []:
        if s["type"] != "image":
            continue
        loc = s["locator"]
        if loc in protected:
            notes.append(f"{loc}: protected, no operation emitted (image slot)")
            continue
        up = None
        for key in (f"{s['asset']}:{s['layer']}" if s.get("layer") else None, s["asset"]):
            if key and key in uploads:
                up = uploads[key]
                break
        if up is None:
            notes.append(f"{loc}: no upload for asset {s['asset']!r}, slot left as it is")
            continue
        rec = _rec(facts, loc, ("section", "rect", "shape"), "image")
        pid = _page_for(m, loc, facts)
        iw, ih = up["pixel_size"]
        fw, fh = _frame_wh(rec)
        b = cover_box(fw, fh, iw, ih)
        fills.setdefault(pid, []).append({"type": "update_fill", "locator_id": loc, "asset_type": "image",
                                          "asset_id": up["media_id"], "alt_text": str(up.get("alt_text") or s.get("role") or s["asset"])[:250]})
        crops.setdefault(pid, []).append({"type": "crop_media", "locator_id": loc, "top": round(b["top"], 4),
                                          "left": round(b["left"], 4), "width": round(b["width"], 4),
                                          "height": round(b["height"], 4), "rotation": 0})
    return {pid: fills[pid] + crops[pid] for pid in fills}


def to_calls(m: dict, batches: dict) -> dict:
    """{page id: {"page_index", "operations"}} - the shape of one edit-design call per page."""
    return {pid: {"page_index": page_index(m, pid), "operations": ops} for pid, ops in batches.items()}


# ---------------------------------------------------------------- verification

def _media(rec):
    if rec["type"] == "section":
        return rec.get("background") or {}
    if rec["type"] == "rect":
        return rec.get("fill") or {}
    if rec["type"] == "shape":
        return next((p["fill"] for p in rec["paths"] if p.get("fill") and p["fill"].get("media")),
                    (rec["paths"][0].get("fill") if rec["paths"] else {}) or {})
    return {}


def _frame(rec):
    if rec["type"] == "section":
        return {"size": rec["size"], "elements": rec["elements"]}
    return {k: rec.get(k) for k in ("box", "rotation", "opacity", "locked", "parent", "order")}


def _allowed(op, a):
    t, rt = op["type"], a["type"]
    if t == "replace_text":
        # an empty cell has no region to keep, and replacing with "" removes the region
        return ["text", "regions.*.chars", "box"] + (["regions"] if not a.get("regions") or op["text"] == "" else [])
    if t == "format_text":
        p = [f"regions.*.{_FMT_FIELD[k]}" for k in op["formatting"] if k in _FMT_FIELD]
        return p + (["box"] if {"font_size", "line_height"} & set(op["formatting"]) else [])
    if t == "recolor_element":
        return ["fill.recoloring", "fill.color", "paths.*.fill.color", "paths.*.fill.recoloring"]
    if t == "update_stroke_properties":
        sub = ["color"] + (["weight"] if "weight" in op else [])
        return [f"{x}.{y}" for x in ("stroke", "paths.*.stroke") for y in sub]
    if t == "update_fill":
        return ["background", "fill", "paths.*.fill"]
    if t == "crop_media":
        return ["background.imageBox", "fill.imageBox", "paths.*.fill.imageBox"]
    return {"position_element": ["box"], "resize_element": ["box"], "update_opacity": ["opacity"],
            "rotate_element": ["rotation", "box"]}.get(t, [])


def _expect(op, a, b, batch):
    """Problems with one operation's effect (empty list = it did what it said)."""
    t, p = op["type"], []
    if t == "replace_text":
        if b.get("text") != op["text"]:
            p.append(f"text is {b.get('text')!r}, expected {op['text']!r}")
    elif t == "format_text":
        for k, v in op["formatting"].items():
            f = _FMT_FIELD.get(k)
            if f is None:
                p.append(f"no check written for formatting {k!r}")
                continue
            for i, r in enumerate(b.get("regions", [])):
                got = r.get(f)
                ok = abs(got - v) < 0.01 if k == "font_size" and isinstance(got, (int, float)) else _lc(got) == _lc(v)
                if not ok:
                    p.append(f"region {i} {f} is {got!r}, expected {v!r}")
            if not b.get("regions"):
                p.append("no text regions after the edit")
    elif t == "recolor_element":
        st = colour_state(b, "fill")
        if not st or any(_lc(c) != _lc(op["color"]) for c in st):
            p.append(f"fill colours {st}, expected {op['color']}")
    elif t == "update_stroke_properties":
        st = colour_state(b, "stroke")
        if "color" in op and (not st or any(_lc(c) != _lc(op["color"]) for c in st)):
            p.append(f"stroke colours {st}, expected {op['color']}")
        if "weight" in op:
            ws = [x["weight"] for x in ([b["stroke"]] if b["type"] in ("line", "rect") else [q["stroke"] for q in b["paths"]])]
            if any(w != op["weight"] for w in ws):
                p.append(f"stroke weights {ws}, expected {op['weight']}")
    elif t == "update_fill":
        if _media(b).get("media") != op["asset_id"]:
            p.append(f"media is {_media(b).get('media')!r}, expected {op['asset_id']!r}")
        if _frame(a) != _frame(b):
            p.append("the frame (box, rotation, opacity, lock, order) changed")
        if not any(o["type"] == "crop_media" and o["locator_id"] == op["locator_id"] for o in batch):
            p.append("update_fill without a crop_media on the same element in this batch (the box would stay ~11 px too big)")
    elif t == "crop_media":
        ib = _media(b).get("imageBox")
        if not ib:
            p.append("no image box after the edit")
        else:
            want = [op.get("top"), op.get("left"), op.get("width"), op.get("height")]
            dev = max(abs(g - w) for g, w in zip(ib[:4], want) if w is not None)
            if dev > TOL_BOX or abs(ib[4] - op.get("rotation", ib[4])) > 0.01:
                p.append(f"image box {ib}, expected top/left/width/height {want} (deviation {dev:.2f}px)")
        if _frame(a) != _frame(b):
            p.append("the frame (box, rotation, opacity, lock, order) changed")
    elif t == "position_element":
        if abs(b["box"][0] - op["top"]) > TOL_POS or abs(b["box"][1] - op["left"]) > TOL_POS:
            p.append(f"box {b['box']}, expected top {op['top']} left {op['left']}")
    elif t == "resize_element":
        for i, k in ((2, "width"), (3, "height")):
            if k in op and abs(b["box"][i] - op[k]) > TOL_POS:
                p.append(f"box {b['box']}, expected {k} {op[k]}")
    elif t == "update_opacity":
        if abs(b["opacity"] - op["opacity"]) > 1e-6:
            p.append(f"opacity {b['opacity']}, expected {op['opacity']}")
    elif t == "rotate_element":
        if abs(b["rotation"] - op["rotation"]) > 0.05:
            p.append(f"rotation {b['rotation']}, expected {op['rotation']}")
    else:
        p.append("no check written for this operation type")
    return p


def _norm(path):
    return ".".join("*" if seg.isdigit() else seg for seg in path.split("."))


def _short(v):
    return json.dumps(v, ensure_ascii=False)[:120]


def verify_batch(before: dict, after: dict, ops: list) -> list:
    """Findings (strings) after a batch: each operation must show its effect, nothing inside a target may change
    beyond what its operations allow, and no other record may change, appear or vanish. [] = clean."""
    found, targets, allowed = [], set(), {}
    for op in ops:
        if op["type"] in ("update_title", "replace_speaker_notes", "add_page"):
            continue                                  # not an element of the facts
        loc = op.get("locator_id")
        a, b = before.get(loc), after.get(loc)
        if a is None or b is None:
            found.append(f"{op['type']} {loc}: element missing {'before' if a is None else 'after'} the edit")
            continue
        targets.add(loc)
        probs = _expect(op, a, b, ops)
        found.extend(f"{op['type']} {loc}: {x}" for x in probs)
        allowed.setdefault(loc, []).extend(_allowed(op, a))
    for loc in sorted(targets):
        fa, fb = flat(before[loc]), flat(after[loc])
        for path in sorted(k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)):
            n = _norm(path)
            if not any(n == x or n.startswith(x + ".") for x in allowed[loc]):
                found.append(f"unexplained change in {loc}: {path}: {_short(fa.get(path))} -> {_short(fb.get(path))}")
    for k in sorted(set(before) | set(after)):
        if k in targets or before.get(k) == after.get(k):
            continue
        if k not in after:
            found.append(f"untargeted change {k}: element removed")
        elif k not in before:
            found.append(f"untargeted change {k}: element added")
        else:
            fa, fb = flat(before[k]), flat(after[k])
            d = [f"{p}: {_short(fa.get(p))} -> {_short(fb.get(p))}" for p in sorted(set(fa) | set(fb)) if fa.get(p) != fb.get(p)]
            found.append(f"untargeted change {k}: " + "; ".join(d[:3]))
    return found


def verify_control(before: dict, after: dict, ops: list):
    """(ok, detail): verify_batch must catch what it is built to catch, on this very data. (a) an untargeted record
    perturbed by 7 px adds exactly one finding about it; (b) the first operation told to expect a wrong value adds
    findings (skipped when that operation already fails, as then the wrong value cannot be told apart)."""
    base = verify_batch(before, after, ops)
    targets = {o.get("locator_id") for o in ops}
    victim = next((k for k in sorted(after) if k not in targets and before.get(k) == after[k] and after[k].get("box")), None)
    if victim is None:
        return False, "no untouched record with a box to perturb: the untargeted-change detector cannot be shown to work"
    bad = copy.deepcopy(after)
    bad[victim]["box"][0] += 7.0
    hit = verify_batch(before, bad, ops)
    if not (len(hit) == len(base) + 1 and any(victim in f for f in hit)):
        return False, f"an untargeted 7 px move of {victim} was not reported ({len(hit) - len(base)} new findings)"
    detail = f"untargeted 7 px move of {victim} reported"
    for i, op in enumerate(ops):
        wrong = None
        if op["type"] == "replace_text":
            wrong = {**op, "text": op["text"] + "!"}
        elif op["type"] in ("recolor_element", "update_stroke_properties"):
            wrong = {**op, "color": "#010203"}
        elif op["type"] == "format_text" and "color" in op["formatting"]:
            wrong = {**op, "formatting": {**op["formatting"], "color": "#010203"}}
        if wrong is None:
            continue
        if any(op["locator_id"] in f and op["type"] in f for f in base):
            detail += "; wrong-value probe skipped (that operation already fails)"
            break
        hit = verify_batch(before, after, ops[:i] + [wrong] + ops[i + 1:])
        if len(hit) <= len(base):
            return False, f"{detail}; but a wrong expected value for {op['type']} {op['locator_id']} was accepted"
        detail += f"; wrong expected value for {op['type']} on one element rejected"
        break
    return True, detail


# ---------------------------------------------------------------- CLI

def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_batches(prefix, m, batches, out_dir):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    paths = []
    for pid, call in to_calls(m, batches).items():
        p = Path(out_dir) / f"{prefix}_{pid}.json"
        p.write_text(json.dumps(call, ensure_ascii=False, indent=1), encoding="utf-8")
        kinds = {}
        for o in call["operations"]:
            kinds[o["type"]] = kinds.get(o["type"], 0) + 1
        print(f"page {pid} (index {call['page_index']}): {len(call['operations'])} operations {kinds}\n  file: {p}")
        paths.append(p)
    return paths


def main(argv) -> int:
    if not argv or argv[0] not in ("build", "images", "verify"):
        print(__doc__)
        return 2
    cmd, a = argv[0], argv[1:]
    try:
        if cmd == "build" and len(a) == 5:
            m, notes = _load(a[0]), []
            batches = build_ops(m, _load(a[1]), _load(a[2]), _load(a[3]), notes=notes)
            _write_batches("ops", m, batches, a[4])
            nf = Path(a[4]) / "ops_notes.txt"
            nf.write_text("\n".join(notes) if notes else "no notes", encoding="utf-8")
            print(f"{sum(len(v) for v in batches.values())} operations in total; {len(notes)} notes\n  notes: {nf}")
        elif cmd == "images" and len(a) == 4:
            m, notes = _load(a[0]), []
            batches = build_image_ops(m, _load(a[1]), _load(a[2]), notes=notes)
            _write_batches("images", m, batches, a[3])
            nf = Path(a[3]) / "images_notes.txt"
            nf.write_text("\n".join(notes) if notes else "no notes", encoding="utf-8")
            print(f"{len(notes)} notes\n  notes: {nf}")
        elif cmd == "verify" and len(a) == 4:
            batch = _load(a[2])
            before, after = _load(a[0]), _load(a[1])
            ok, cdetail = verify_control(before, after, batch["operations"])
            if not ok:
                print(f"CONTROL FAILED - the verification cannot be trusted: {cdetail}")
                return 1
            found = verify_batch(before, after, batch["operations"])
            Path(a[3]).write_text("\n".join(found + [f"verify: {len(batch['operations'])} operations, findings = {len(found)}"]) + "\n", encoding="utf-8")
            print(f"control ok: {cdetail}\nverify: {len(batch['operations'])} operations, findings = {len(found)}\n  report: {a[3]}")
            return 1 if found else 0
        else:
            print(__doc__)
            return 2
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"error: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
