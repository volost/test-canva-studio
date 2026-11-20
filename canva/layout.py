"""Layout check from the data (no images): compare two facts files.

Usage: python -I canva/layout.py <facts_before.json> <facts_after.json> <report.txt>

For every text element:
  1. centre axis: for centre-aligned text the box centre x must not move (tolerance 1 px); for
     start-aligned text the left edge must not move.
  2. size: reports every text whose box height or width changed, with the line count estimate
     (height / (font size * line height)).
  3. overlap: vertical overlap of the text box with every other visible element of the same section
     whose x range intersects it, before and after. Reports pairs whose overlap grew by more than 2 px
     or that are new. Invisible elements (opacity 0), groups, section records and table cells are
     skipped; pairs that already overlapped by the same amount are not reported.
  4. column: every text must stay inside its section's invisible column rectangle (opacity-0 locked
     shape) when it was inside before; reports texts that now stick out.
Control: the script first checks itself on a synthetic pair (a text that grows into its neighbour).
Exit code 1 when issues are found (AXIS / OVERLAP / COLUMN / NEW TEXT); `size` lines are information only.
"""
import json
import sys
from pathlib import Path


def boxes(facts, section_key):
    res = {}
    for k, v in facts.items():
        if v["type"] in ("section", "cell", "group") or (v["page"], v["section"]) != section_key:
            continue
        if v.get("opacity", 1) == 0:
            continue
        t, l, w, h = v["box"]
        res[k] = (t, l, t + h, l + w, v)
    return res


def v_overlap(a, b):
    """vertical overlap in px of boxes a, b (0 when their x ranges do not intersect)."""
    if min(a[3], b[3]) - max(a[1], b[1]) <= 0:
        return 0.0
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))


def check(fa, fb, out=print):
    """Compare two facts dicts; every finding goes to `out(line)`; returns the number of issues."""
    issues = 0
    sections = sorted({(v["page"], v["section"]) for v in fb.values()})
    for sk in sections:
        ba, bb = boxes(fa, sk), boxes(fb, sk)
        cols = [v["box"] for k, v in fb.items() if (v["page"], v["section"]) == sk and v["type"] == "shape"
                and v.get("opacity", 1) == 0 and v.get("locked")]
        for k, (t, l, btm, r, v) in sorted(bb.items(), key=lambda kv: kv[1][0]):
            if v["type"] != "text":
                continue
            name = k.split("-")[-1]
            if k not in ba:
                out(f"NEW TEXT {sk[1]} {name}")
                issues += 1
                continue
            t0, l0, b0, r0, v0 = ba[k]
            reg = v["regions"][0] if v["regions"] else {}
            align = reg.get("align")
            moved = []
            if align == "center":
                if abs((l + r) / 2 - (l0 + r0) / 2) > 1:
                    moved.append(f"centre x {(l0 + r0) / 2:.1f} -> {(l + r) / 2:.1f}")
            elif abs(l - l0) > 1:
                moved.append(f"left {l0:.1f} -> {l:.1f}")
            size = ""
            if abs((btm - t) - (b0 - t0)) > 1 or abs((r - l) - (r0 - l0)) > 1 or abs(t - t0) > 1:
                lh = (reg.get("fontSize") or 1) * (reg.get("lh") or 1)
                size = (f"box t{t0:.0f} l{l0:.0f} w{r0 - l0:.0f} h{b0 - t0:.0f} -> t{t:.0f} l{l:.0f} w{r - l:.0f} h{btm - t:.0f}"
                        f" (~{(b0 - t0) / lh:.1f} -> ~{(btm - t) / lh:.1f} lines)")
            if moved:
                out(f"AXIS  {sk[1]} {name} {v['text'][:30]!r}: {'; '.join(moved)}")
                issues += 1
            if size:
                out(f"size  {sk[1]} {name} {v['text'][:30]!r}: {size}")
            for k2, b2 in bb.items():
                if k2 == k or (b2[4]["type"] == "text" and k2 < k):     # each text-text pair once
                    continue
                ov = v_overlap((t, l, btm, r), b2)
                ov0 = v_overlap((t0, l0, b0, r0), ba[k2]) if k2 in ba else 0.0
                if ov > ov0 + 2:
                    out(f"OVERLAP {sk[1]} {name} {v['text'][:24]!r} with {b2[4]['type']} {k2.split('-')[-1]}"
                        f"{(' ' + repr(b2[4].get('text', '')[:20])) if b2[4]['type'] == 'text' else ''}: {ov0:.0f} -> {ov:.0f} px")
                    issues += 1
            for c in cols:
                ct, cl, cw, ch = c
                inside0 = l0 >= cl - 1 and r0 <= cl + cw + 1
                inside = l >= cl - 1 and r <= cl + cw + 1
                if inside0 and not inside:
                    out(f"COLUMN {sk[1]} {name} {v['text'][:24]!r}: x {l:.0f}..{r:.0f} leaves column {cl:.0f}..{cl + cw:.0f}")
                    issues += 1
    return issues


def self_test():
    def txt(t, l, w, h):
        return {"type": "text", "page": "P", "section": "S", "box": [t, l, w, h], "opacity": 1, "text": "x",
                "regions": [{"align": "center", "fontSize": 10, "lh": 1.5}]}
    a = {"P-S-A": txt(0, 0, 100, 20), "P-S-B": txt(30, 0, 100, 20)}
    b = {"P-S-A": txt(0, 10, 100, 45), "P-S-B": txt(30, 0, 100, 20)}
    lines = []
    n = check(a, b, lines.append)
    assert n == 2 and any(x.startswith("AXIS") for x in lines) and any(x.startswith("OVERLAP") for x in lines), lines
    assert check(a, a, lines.append) == 0
    return "self-test ok (synthetic axis shift and overlap both detected, identical pair clean)"


def main(argv) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    try:
        msg = self_test()
        fa = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
        fb = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        lines = []
        n = check(fa, fb, lines.append)
        Path(argv[2]).write_text("\n".join(lines + [f"layout issues: {n}"]) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {type(e).__name__}: {e}")
        return 1
    print(f"{msg}\nlayout issues: {n}\nreport: {argv[2]}")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
