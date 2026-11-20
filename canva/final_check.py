"""Whole-design check of a written design against the map, the texts and the original facts.

Usage: python -I canva/final_check.py <map.json> <texts.json> <facts_original.json> <facts_now.json> <report.txt>
                                      [--style style.json] [--images]

Checks (each a {name, passed, detail}); a check that examined nothing fails, because it proves nothing:
  texts       every text / calendar-cell slot that has a texts entry now shows exactly that text
  formatting  ... in the font, size, weight, style, alignment, line height and spacing it had in the original
  colours     (with --style) text colours follow style colour_roles, other text colours are unchanged (the roles
              kept as they are are listed in the detail), colour slots show their palette colour
  protected   protected_changes() is empty
  coverage    every text / calendar-cell record of the original is a slot, protected, or listed in the map's `keep`
              (an unmapped text is never checked by the others: an incomplete map must not give a green result);
              a `keep` locator that is not in the original is reported
  structure   no element added or removed; type, page, section, parent and layer order of every record unchanged
  leftovers   no personal slot's original wording (4+ characters) is still anywhere in the design's text
  images      (with --images) every image slot holds a new picture, its frame (box, rotation, opacity, lock, order)
              is the original's, and its image box is the exact cover box
  control     every check must reject a deliberately bad input in the same run: texts on the untouched original,
              the others on synthetic mutations (a font size, a protected record, a removed record, a wrong colour,
              a leftover word, an image box with the update_fill bleed or a moved frame), each next to a good input
              that passes; if any stays green, none of the checks can be trusted
Exit code 1 when any check fails.
"""
import copy
import json
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from canva.geometry import cover_box  # noqa: E402
from canva.ops import _frame as frame_of, colour_state, kept_colour_roles, OpsError, palette_colour, uncovered_texts  # noqa: E402
from canva.protected import protected_changes, protected_members, run_control  # noqa: E402

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
    res = _verdict("colours", bad, n, "text and colour slots")
    kept = kept_colour_roles(m, style)
    if kept:
        res["detail"] += "; roles kept as in the skeleton (no colour_roles entry): " + ", ".join(
            f"{r} ({c})" for r, c in sorted(kept.items(), key=lambda kv: str(kv[0])))
    return res


def _check_coverage(orig, m):
    miss = uncovered_texts(orig, m)
    bad = [f"{k}: text element not in the map (no slot, not protected, not in keep)" for k in miss]
    bad += [f"keep {k}: not in the original facts (stale map?)" for k in m.get("keep") or [] if k not in orig]
    n = sum(1 for v in orig.values() if v.get("type") in ("text", "cell"))
    return _verdict("coverage", bad, n, "text and cell records")


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


def _leftover_words(m, texts):
    words = []
    for s in _text_slots(m, texts):
        o = (s.get("original") or "").strip().lower()
        if s["type"] == "text" and s.get("personal") and len(o) >= 4 and o not in texts[s["locator"]].lower():
            words.append((o, s["locator"]))
    return words


def _check_leftovers(orig, now, m, texts):
    prot = set(protected_members(orig, m))
    words = _leftover_words(m, texts)
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
        if frame_of(old) != frame_of(rec):
            bad.append(f"{loc}: the frame changed (box, rotation, opacity, lock or order)")
            continue
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


def _sub(m, slot):
    return {**m, "slots": [slot], "protected": [], "keep": []}


def _probe(name, good, bad):
    """(ok, detail): `good` ({passed}) must pass and `bad` must fail - a check shown to tell them apart."""
    ok = good["passed"] and not bad["passed"]
    return name, ok, (f"{name}: good input {'passes' if good['passed'] else 'FAILS'}, bad input "
                      f"{'rejected' if not bad['passed'] else 'ACCEPTED'}")


def _controls(orig, m, texts, style, images):
    """Probes of every check but `texts` on synthetic inputs built from the original. None of them depends on
    the design under test, so a green result there is a green result of the checker itself."""
    out = []
    cp = copy.deepcopy
    ts = [s for s in _text_slots(m, texts) if _font_ref(orig, s["locator"]) and orig[s["locator"]].get("regions")
          and orig[s["locator"]].get("text")]
    if ts:
        loc = ts[0]["locator"]
        bad = cp(orig)
        bad[loc]["regions"][0]["fontSize"] += 1.0
        out.append(_probe("formatting", _check_formatting(orig, cp(orig), _sub(m, ts[0]), {loc: orig[loc]["text"]}),
                          _check_formatting(orig, bad, _sub(m, ts[0]), {loc: orig[loc]["text"]})))
    ok, detail = run_control(orig, m)
    out.append(("protected", ok, "protected: " + detail))
    cs0 = next((s for s in _text_slots(m, texts, only_with_text=False) if s["locator"] in orig), None)
    if cs0 is not None:
        o1 = {cs0["locator"]: cp(orig[cs0["locator"]])}
        stray = cp(o1)
        stray["COVERAGE-PROBE"] = cp(o1[cs0["locator"]])
        out.append(_probe("coverage", _check_coverage(o1, _sub(m, cs0)), _check_coverage(stray, _sub(m, cs0))))
    if orig:
        gone, added = cp(orig), cp(orig)
        k0 = sorted(orig)[0]
        del gone[k0]
        added["NEW-PROBE"] = cp(orig[k0])
        out.append(_probe("structure", _check_structure(orig, cp(orig)), _check_structure(orig, gone)))
        out.append(_probe("structure+", _check_structure(orig, cp(orig)), _check_structure(orig, added)))
    if style is not None:
        cs = [s for s in ts if palette_colour(style, s.get("role"))]
        if cs:
            loc, want = cs[0]["locator"], palette_colour(style, cs[0].get("role"))
            good, bad = cp(orig), cp(orig)
            for r in good[loc]["regions"]:
                r["color"] = want
            for r in bad[loc]["regions"]:
                r["color"] = "#010203" if want != "#010203" else "#020304"
            out.append(_probe("colours", _check_colours(orig, good, _sub(m, cs[0]), {loc: good[loc]["text"]}, style),
                              _check_colours(orig, bad, _sub(m, cs[0]), {loc: bad[loc]["text"]}, style)))
    ws = _leftover_words(m, texts)
    if ws:
        word, loc = ws[0]
        slot = next(s for s in m["slots"] if s["locator"] == loc)
        tx = {loc: "something else entirely"}
        o1 = {loc: cp(orig[loc])}                  # one record: other texts of the design may legitimately hold the word
        good, bad = cp(o1), cp(o1)
        good[loc]["text"] = "something else entirely"
        bad[loc]["text"] = "prefix " + word
        out.append(_probe("leftovers", _check_leftovers(o1, good, _sub(m, slot), tx),
                          _check_leftovers(o1, bad, _sub(m, slot), tx)))
    if images:
        im = next((s for s in m.get("slots") or [] if s["type"] == "image" and s["locator"] in orig
                   and s["locator"] not in (m.get("protected") or []) and orig[s["locator"]]["type"] != "section"), None)
        if im is not None:
            loc = im["locator"]
            rec = orig[loc]
            fw, fh = rec["box"][2:4]
            ideal = cover_box(fw, fh, *m["assets"][im["asset"]]["frame"])

            def placed(box=None, move=False):
                n = cp(orig)
                tgt = n[loc]["fill"] if rec["type"] == "rect" else next(p["fill"] for p in n[loc]["paths"] if p["fill"].get("media"))
                tgt["media"] = "MAPROBE0001"
                tgt["imageBox"] = box or [ideal["top"], ideal["left"], ideal["width"], ideal["height"], 0.0]
                if move:
                    n[loc]["box"][0] += 5.0
                return n
            sm = _sub(m, im)
            good = _check_images(orig, placed(), sm)
            bleed = [ideal["top"] - 11.34, ideal["left"] - 11.34, ideal["width"] + 22.68, ideal["height"] + 22.68, 0.0]
            out.append(_probe("images (bleed)", good, _check_images(orig, placed(box=bleed), sm)))
            out.append(_probe("images (frame)", good, _check_images(orig, placed(move=True), sm)))
    return out


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
    res.append(_check_coverage(orig, m))
    res.append(_check_structure(orig, now))
    res.append(_check_leftovers(orig, now, m, texts))
    if images:
        res.append(_check_images(orig, now, m))
    if control:
        on_orig = final_check(orig, orig, m, texts, style=style, images=images, control=False)
        failed = [r["name"] for r in on_orig if not r["passed"]]
        want_fail = any(s["locator"] in orig and orig[s["locator"]].get("text") != texts[s["locator"]]
                        for s in _text_slots(m, texts))
        probes = _controls(orig, m, texts, style, images)
        slack = [d for _, ok, d in probes if not ok]
        ok = want_fail and "texts" in failed and not slack
        res.append({"name": "control", "passed": ok, "detail":
                    f"texts fails on the untouched original ({'yes' if 'texts' in failed else 'NO'}; it fails {len(failed)} "
                    f"check(s): {failed}); {len(probes) - len(slack)}/{len(probes)} synthetic probes behave"
                    + ("" if not slack else ": " + "; ".join(slack))
                    + ("" if want_fail else "; no text differs from the original, so texts cannot be shown to fail")})
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
