"""Whole-design check of a written design against the map, the texts and the original facts.

Usage: python -I canva/final_check.py <map.json> <texts.json> <facts_original.json> <facts_now.json> <report.txt>
                                      [--style style.json] [--images]

Checks (each a {name, passed, detail}); a check that examined nothing fails, because it proves nothing:
  texts       every text / calendar-cell slot that has a texts entry now shows exactly that text
  formatting  ... in the font, size, weight, style, alignment, line height and spacing it had in the original
  colours     (with --style) text colours follow style colour_roles, other text colours are unchanged, colour
              slots show their palette colour
  protected   protected_changes() is empty
  structure   no element added or removed; type, page, section, parent and layer order of every record unchanged
  leftovers   no personal slot's original wording (4+ characters) is still anywhere in the design's text
  images      (with --images) every image slot holds a new picture whose image box is its exact cover box
  control     the checks run on the untouched original must FAIL; if they do not, none of the above can be trusted
Exit code 1 when any check fails.
"""
import json
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from canva.geometry import cover_box  # noqa: E402
from canva.ops import colour_state, OpsError, palette_colour  # noqa: E402
from canva.protected import protected_changes, protected_members  # noqa: E402

FONT_FIELDS = ("fontRef", "fontSize", "weight", "style", "align", "lh", "ls")


def _lc(c):
    return c.lower() if isinstance(c, str) else c


def _verdict(name, problems, n, what):
    if n == 0:
        return {"name": name, "passed": False, "detail": f"nothing to check ({what}) - a check that examines nothing proves nothing"}
    head = f"{n} {what} checked, {len(problems)} wrong"
    return {"name": name, "passed": not problems,
            "detail": head + ("" if not problems else ": " + "; ".join(problems[:5]) + (f"; +{len(problems) - 5} more" if len(problems) > 5 else ""))}


def _text_slots(m, texts, only_with_text=True):
    prot = set(m.get("protected") or [])
    return [s for s in m.get("slots") or [] if s["type"] in ("text", "table_cell") and s["locator"] not in prot
            and (s["locator"] in texts or not only_with_text)]


def _font_ref(orig, loc):
    """Formatting reference of a text slot: its first original region, or - for an empty cell - a sibling cell's."""
    rec = orig.get(loc)
    if rec and rec.get("regions"):
        return rec["regions"][0]
    if rec and rec.get("type") == "cell":
        for v in orig.values():
            if v.get("type") == "cell" and v.get("parent") == rec.get("parent") and v.get("page") == rec.get("page") \
                    and v.get("section") == rec.get("section") and v.get("regions"):
                return v["regions"][0]
    return None


def _check_texts(orig, now, m, texts):
    bad, n = [], 0
    for s in _text_slots(m, texts):
        n += 1
        loc = s["locator"]
        want = texts[loc]
        if loc not in now:
            bad.append(f"{loc}: missing")
        elif now[loc].get("text") != want:
            bad.append(f"{loc}: {now[loc].get('text')!r} != {want!r}")
    return _verdict("texts", bad, n, "text slots")


def _check_formatting(orig, now, m, texts):
    bad, n = [], 0
    for s in _text_slots(m, texts):
        loc = s["locator"]
        ref = _font_ref(orig, loc)
        if ref is None or loc not in now or not now[loc].get("regions"):
            continue
        n += 1
        for r in now[loc]["regions"]:
            diff = [f"{f} {ref.get(f)!r} -> {r.get(f)!r}" for f in FONT_FIELDS if r.get(f) != ref.get(f)]
            if diff:
                bad.append(f"{loc}: " + ", ".join(diff))
                break
    return _verdict("formatting", bad, n, "texts with a font reference")


def _check_colours(orig, now, m, texts, style):
    bad, n = [], 0
    for s in _text_slots(m, texts):
        loc = s["locator"]
        if loc not in now or not now[loc].get("text") or not now[loc].get("regions"):
            continue
        want = palette_colour(style, s.get("role"))
        got = {_lc(r.get("color")) for r in now[loc]["regions"]}
        n += 1
        if want is not None:
            if got != {want}:
                bad.append(f"{loc}: text colours {sorted(map(str, got))}, want {want}")
        elif orig.get(loc, {}).get("regions") and got != {_lc(r.get("color")) for r in orig[loc]["regions"]}:
            bad.append(f"{loc}: text colour changed although role {s.get('role')!r} has no colour role")
    prot = set(m.get("protected") or [])
    for s in m.get("slots") or []:
        if s["type"] != "colour" or s["locator"] in prot:
            continue
        loc = s["locator"]
        rec = now.get(loc)
        if rec is None:
            n += 1
            bad.append(f"{loc}: missing")
            continue
        if rec["type"] == "section":
            continue                                     # not settable (see ops.py), not claimed
        target = s.get("target") or ("stroke" if rec["type"] == "line" else "fill")
        n += 1
        try:
            want, got = palette_colour(style, s.get("role")), colour_state(rec, target)
        except OpsError as e:
            bad.append(f"{loc}: {e}")
            continue
        if want is None or not got or any(_lc(c) != want for c in got):
            bad.append(f"{loc}: {target} colours {got}, want {want}")
    return _verdict("colours", bad, n, "text and colour slots")


def _check_structure(orig, now):
    bad = []
    gone, added = sorted(set(orig) - set(now)), sorted(set(now) - set(orig))
    if gone:
        bad.append(f"removed {gone[:3]}")
    if added:
        bad.append(f"added {added[:3]}")
    for k in sorted(set(orig) & set(now)):
        a, b = orig[k], now[k]
        diff = [f for f in ("type", "page", "section", "parent", "order", "children", "elements") if a.get(f) != b.get(f)]
        if diff:
            bad.append(f"{k}: {', '.join(f'{f} {a.get(f)!r} -> {b.get(f)!r}' for f in diff)[:160]}")
    return _verdict("structure", bad, len(orig), "records")


def _check_leftovers(orig, now, m, texts):
    prot = set(protected_members(orig, m))
    words = []
    for s in _text_slots(m, texts):
        o = (s.get("original") or "").strip().lower()
        if s["type"] == "text" and s.get("personal") and len(o) >= 4 and o not in texts[s["locator"]].lower():
            words.append((o, s["locator"]))
    bad = []
    for k, v in now.items():
        if v.get("type") in ("text", "cell") and k not in prot:
            low = v.get("text", "").lower()
            bad += [f"{k}: still has {w!r} (slot {loc})" for w, loc in words if w in low]
    return _verdict("leftovers", bad, len(words), "original wordings searched for")


def _check_images(orig, now, m):
    bad, n = [], 0
    prot = set(m.get("protected") or [])
    for s in m.get("slots") or []:
        if s["type"] != "image" or s["locator"] in prot:
            continue
        loc, a = s["locator"], m["assets"][s["asset"]]
        n += 1
        rec, old = now.get(loc), orig.get(loc)
        if rec is None or old is None:
            bad.append(f"{loc}: missing")
            continue
        med = (rec.get("background") if rec["type"] == "section" else rec.get("fill") if rec["type"] == "rect"
               else next((p["fill"] for p in rec.get("paths", []) if p.get("fill") and p["fill"].get("media")), None)) or {}
        omed = (old.get("background") if old["type"] == "section" else old.get("fill") if old["type"] == "rect"
                else next((p["fill"] for p in old.get("paths", []) if p.get("fill") and p["fill"].get("media")), None)) or {}
        if not med.get("media") or med.get("media") == omed.get("media"):
            bad.append(f"{loc}: picture not replaced (media {med.get('media')!r})")
            continue
        fw, fh = rec["size"] if rec["type"] == "section" else rec["box"][2:4]
        ideal = cover_box(fw, fh, *a["frame"])
        ib = med.get("imageBox") or [None] * 5
        if None in ib:
            bad.append(f"{loc}: no image box")
            continue
        dev = max(abs(ib[0] - ideal["top"]), abs(ib[1] - ideal["left"]), abs(ib[2] - ideal["width"]), abs(ib[3] - ideal["height"]))
        if dev > 0.005 * max(fw, fh) + 0.5 or abs(ib[4]) > 0.01:
            bad.append(f"{loc}: image box {ib} is not the cover box {[round(ideal[k], 2) for k in ('top', 'left', 'width', 'height')]} (off by {dev:.1f}px)")
    return _verdict("images", bad, n, "image slots")


def final_check(orig: dict, now: dict, m: dict, texts: dict, style: dict = None, images: bool = False,
                control: bool = True) -> list:
    """List of {name, passed, detail}. See the module doc for the checks. With control=True the last entry
    ("control") runs the same checks on the untouched original and passes only if they fail there."""
    res = [_check_texts(orig, now, m, texts), _check_formatting(orig, now, m, texts)]
    if style is not None:
        res.append(_check_colours(orig, now, m, texts, style))
    pc = protected_changes(orig, now, m)
    res.append({"name": "protected", "passed": not pc, "detail": f"{len(protected_members(orig, m))} protected records, "
                f"{len(pc)} violations" + ("" if not pc else ": " + "; ".join(pc[:3]))})
    res.append(_check_structure(orig, now))
    res.append(_check_leftovers(orig, now, m, texts))
    if images:
        res.append(_check_images(orig, now, m))
    if control:
        on_orig = final_check(orig, orig, m, texts, style=style, images=images, control=False)
        failed = [r["name"] for r in on_orig if not r["passed"]]
        want_fail = any(s["locator"] in orig and orig[s["locator"]].get("text") != texts[s["locator"]]
                        for s in _text_slots(m, texts))
        ok = want_fail and "texts" in failed
        res.append({"name": "control", "passed": ok,
                    "detail": f"the untouched original fails {len(failed)} check(s): {failed}" if ok else
                    "the texts check does not fail on the untouched original as it must (no text differs from the original, or the check is broken): "
                    f"failed={failed}"})
    return res


def main(argv) -> int:
    args = list(argv)
    style_path = None
    images = False
    if "--images" in args:
        args.remove("--images")
        images = True
    if "--style" in args:
        i = args.index("--style")
        if i + 1 >= len(args):
            print(__doc__)
            return 2
        style_path = args[i + 1]
        del args[i:i + 2]
    if len(args) != 5:
        print(__doc__)
        return 2
    try:
        m, texts, orig, now = (json.loads(Path(x).read_text(encoding="utf-8")) for x in args[:4])
        style = json.loads(Path(style_path).read_text(encoding="utf-8")) if style_path else None
        res = final_check(orig, now, m, texts, style=style, images=images)
        lines = [f"{'PASS' if r['passed'] else 'FAIL'} {r['name']}: {r['detail']}" for r in res]
        Path(args[4]).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"error: {type(e).__name__}: {e}")
        return 1
    failed = [r["name"] for r in res if not r["passed"]]
    ctl = next((r for r in res if r["name"] == "control"), None)
    print(f"checks: {len(res)}; failed: {len(failed)} {failed}\ncontrol: {ctl['detail'] if ctl else 'not run'}\nreport: {args[4]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
