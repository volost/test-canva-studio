"""Small helpers shared by the Canva-side scripts: which page a locator belongs to, and its index."""
import re

_SYMBOLIC = re.compile(r"^p(\d+)[/-]")


def page_ids(m: dict) -> list:
    return [p["id"] for p in m.get("pages", []) if isinstance(p, dict) and "id" in p]


def page_index(m: dict, page_id: str) -> int:
    """One-based index of the page in the map (what edit-design calls page_index)."""
    for p in m.get("pages", []):
        if isinstance(p, dict) and p.get("id") == page_id:
            return int(p["index"])
    raise ValueError(f"page {page_id!r} is not in the map's pages")


def page_of_locator(m: dict, locator: str, facts: dict = None):
    """Page id of a locator: from the facts record when there is one, else from the locator's own text
    (`<page id>-...` as Canva writes it, or `p<index>/...` / `p<index>-...` as a hand-written map may). None if unknown."""
    if facts is not None and locator in facts and isinstance(facts[locator], dict) and facts[locator].get("page"):
        return facts[locator]["page"]
    for p in m.get("pages", []):
        pid = p.get("id")
        if pid and (locator == pid or locator.startswith(pid + "-") or locator.startswith(pid + "/")):
            return pid
    mo = _SYMBOLIC.match(locator)
    if mo:
        for p in m.get("pages", []):
            if p.get("index") == int(mo.group(1)):
                return p["id"]
    return None
