"""Hard-limit check: nothing the map marks as protected has changed.

Usage: python -I canva/protected.py <map.json> <facts_original.json> <facts_now.json> <report.txt>

Protected = every locator in map["protected"] (the form, embeds, envelope overlay groups, ...) plus everything
below it (a group's children, a table's cells) EXCEPT descendants that the map lists as slots of their own (the
two envelope layers inside a protected overlay group are image slots: the images are replaced, the group stays).
For each protected record the whole record must be identical: media id, image box, position, size, rotation,
opacity, lock, layer order, text, children list, url. For every section that holds a protected record the order
of its elements must be identical too. A protected locator that is not in the original facts is reported.
Control (run by the CLI): a synthetic change to one protected record must be reported, an identical copy must be clean.
Exit code 1 on any violation or a failed control.
"""
import copy
import json
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from canva.facts import flat  # noqa: E402


def protected_members(orig: dict, m: dict) -> list:
    """Locators in `orig` that the protection covers (sorted)."""
    prot = set(m.get("protected") or [])
    own_slots = {s["locator"] for s in m.get("slots") or []} - prot
    members = set()
    for p in prot:
        if p in orig:
            members.add(p)
        for k in orig:
            if k.startswith(p + "-") and k not in own_slots:
                members.add(k)
    return sorted(members)


def _short(v):
    return json.dumps(v, ensure_ascii=False)[:100]


def protected_changes(orig: dict, now: dict, m: dict) -> list:
    """Findings (strings) for protected elements that changed, vanished or were re-ordered; [] = untouched."""
    found = []
    for p in m.get("protected") or []:
        if p not in orig:
            found.append(f"UNKNOWN protected locator {p}: not in the original facts (stale map?)")
    sections = set()
    for k in protected_members(orig, m):
        v = orig[k]
        if k not in now:
            found.append(f"MISSING protected {k}")
            continue
        if v != now[k]:
            fa, fb = flat(v), flat(now[k])
            d = [f"{p}: {_short(fa.get(p))} -> {_short(fb.get(p))}" for p in sorted(set(fa) | set(fb)) if fa.get(p) != fb.get(p)]
            found.append(f"CHANGED protected {k}: " + "; ".join(d[:4]) + (f" (+{len(d) - 4} more)" if len(d) > 4 else ""))
        if v.get("page") is not None and v.get("section") is not None:
            sections.add(f"{v['page']}-{v['section']}")
    for sk in sorted(sections):
        if sk in orig and sk in now and orig[sk].get("elements") != now[sk].get("elements"):
            found.append(f"LAYER ORDER of section {sk} changed: {orig[sk].get('elements')} -> {now[sk].get('elements')}")
    return found


def run_control(orig: dict, m: dict):
    """(ok, detail): a synthetic change to one protected record is reported, an identical copy is clean."""
    members = protected_members(orig, m)
    if not members:
        return False, "no protected record in the original facts to test with"
    k = members[0]
    bad = copy.deepcopy(orig)
    med = bad[k].get("fill") if bad[k]["type"] == "rect" else None
    if med and med.get("media"):
        med["media"] = "MAXXXXXXXXX"
    elif "box" in bad[k]:
        bad[k]["box"][0] += 1.0
    else:                                   # a section: change the element order
        bad[k]["elements"] = list(reversed(bad[k].get("elements", []))) + ["XX"]
    hit = protected_changes(orig, bad, m)
    clean = protected_changes(orig, copy.deepcopy(orig), m)
    ok = len(hit) >= 1 and any(k in h for h in hit) and clean == []
    return ok, f"changed record {k}: {len(hit)} finding(s); identical copy: {len(clean)} finding(s)"


def main(argv) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    try:
        m, a, b = (json.loads(Path(x).read_text(encoding="utf-8")) for x in argv[:3])
        ok, detail = run_control(a, m)
        if not ok:
            print(f"CONTROL FAILED - the check cannot be trusted: {detail}")
            return 1
        found = protected_changes(a, b, m)
        n = len(protected_members(a, m))
        Path(argv[3]).write_text("\n".join(found + [f"protected records checked: {n}; violations: {len(found)}"]) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"error: {type(e).__name__}: {e}")
        return 1
    print(f"control ok: {detail}\nprotected records checked: {n}; violations: {len(found)}\nreport: {argv[3]}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
