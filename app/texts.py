"""Texts: validation against the map's text slots, length warnings, and the manual font checklist.
Strings are never altered here (no strip, no normalisation, no escaping)."""
NOT_SET = "не задано"
PARAGRAPH_PERCENT = 115


def _text_slots(m) -> list:
    slots = m.get("slots") if isinstance(m, dict) else None
    if not isinstance(slots, list):
        return []
    return [s for s in slots if isinstance(s, dict) and s.get("type") in ("text", "table_cell")
            and isinstance(s.get("locator"), str)]


def validate_texts(d, m) -> list:
    if not isinstance(d, dict):
        return ["texts: not an object"]
    allowed = {s["locator"] for s in _text_slots(m)}
    out = []
    for loc, v in d.items():
        if loc not in allowed:
            out.append(f"{loc!r}: not a locator of a text slot")
        elif not isinstance(v, str):
            out.append(f"{loc!r}: value must be a string")
    return out


def length_warnings(texts, m) -> dict:
    if not isinstance(texts, dict):
        return {}
    out = {}
    for s in _text_slots(m):
        loc = s["locator"]
        v = texts.get(loc)
        if not isinstance(v, str):
            continue
        mx, orig = s.get("max_len"), s.get("original")
        if isinstance(mx, int) and not isinstance(mx, bool) and "\n" not in v and len(v) > mx:
            out[loc] = f"Задовгий рядок: {len(v)} символів, дозволено до {mx}."
        elif isinstance(orig, str) and orig and len(v) * 100 > PARAGRAPH_PERCENT * len(orig):
            out[loc] = (f"Абзац задовгий: {len(v)} символів, в оригіналі {len(orig)} "
                        f"(дозволено до 115 %, тобто {(PARAGRAPH_PERCENT * len(orig)) // 100}).")
    return out


def font_checklist(m, style) -> list:
    style = style if isinstance(style, dict) else {}
    fonts = style.get("fonts") if isinstance(style.get("fonts"), dict) else {}
    fmap = style.get("font_map") if isinstance(style.get("font_map"), dict) else {}
    out = []
    for s in _text_slots(m):
        role = s.get("role")
        key = fmap.get(role) if isinstance(role, str) else None
        font = fonts.get(key) if isinstance(key, str) else None
        out.append({"locator": s["locator"], "role": role, "font": font if font else NOT_SET})
    return out
