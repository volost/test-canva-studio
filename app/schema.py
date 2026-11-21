"""Validators for skeleton map.json and template style.json. Each returns a list of short messages
(empty = valid); none raises on malformed input.

map.json is written by Claude (map_skeleton job) and edited by the owner's role assignments; style.json comes from the
owner's chosen direction. Both are untrusted input, which is why every access here is type-checked first, and why the
same validators run on PUT (api.py) AND again on the file as it is on disk before a job is requested or a step is
approved (Claude's jobs write these files without going through the PUT routes).
"""
import re

# Keys every map must carry. "keep" (texts intentionally left as they are) is optional and, like "protected", is read by
# canva/final_check.py's coverage check, so a map that forgets a text cannot pass.
TOP_KEYS = ("skeleton", "design_id", "pages", "assets", "slots", "envelope", "protected")
SLOT_TYPES = ("image", "text", "colour", "table_cell")
ASSET_KINDS = ("photo", "texture", "watercolour", "solid", "composed")
LAYERS = ("cover", "flap", "body")
TARGETS = ("fill", "stroke")
ENVELOPE_PAIRS = ("section_px", "tip", "left_top", "right_top", "seal_centre", "seal_size")
FONT_ROLES = ("heading", "body", "script")
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pair(v, pred) -> bool:
    return isinstance(v, (list, tuple)) and len(v) == 2 and all(pred(x) for x in v)


def _str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def validate_map(d) -> list:
    if not isinstance(d, dict):
        return ["map: not an object"]
    out = []
    for k in TOP_KEYS:
        if k not in d:
            out.append(f"map: missing key {k!r}")
    assets = d.get("assets")
    if "assets" in d:
        if not isinstance(assets, dict):
            out.append("assets: not an object")
            assets = {}
    else:
        assets = {}
    if "pages" in d and not isinstance(d["pages"], list):
        out.append("pages: not a list")
    for name, a in assets.items():
        if not isinstance(a, dict):
            out.append(f"asset {name!r}: not an object")
            continue
        if a.get("kind") not in ASSET_KINDS:
            out.append(f"asset {name!r}: bad kind {a.get('kind')!r}")
        fr = a.get("frame")
        if not _pair(fr, lambda x: _int(x) and x > 0):
            out.append(f"asset {name!r}: frame must be two positive integers")

    slots = d.get("slots")
    if "slots" in d and not isinstance(slots, list):
        out.append("slots: not a list")
        slots = []
    seen = set()
    for i, s in enumerate(slots or []):
        if not isinstance(s, dict):
            out.append(f"slot #{i}: not an object")
            continue
        loc = s.get("locator")
        if not _str(loc):
            out.append(f"slot #{i}: missing or empty locator")
            tag = f"slot #{i}"
        else:
            tag = f"slot {loc!r}"
            if loc in seen:
                out.append(f"{tag}: duplicate locator")
            seen.add(loc)
        t = s.get("type")
        if t not in SLOT_TYPES:
            out.append(f"{tag}: bad type {t!r}")
        asset = s.get("asset")
        if t == "image":
            if not isinstance(asset, str) or asset not in assets:
                out.append(f"{tag}: image slot references unknown asset {asset!r}")
        elif t in ("text", "colour") and asset is not None:
            out.append(f"{tag}: {t} slot must have asset null")
        # A "layer" (cover/flap/body) names which of a composed asset's three generated pictures fills this slot; it is
        # meaningless for any other asset kind, so it is refused there rather than ignored.
        if "layer" in s:
            layer = s["layer"]
            if layer not in LAYERS:
                out.append(f"{tag}: bad layer {layer!r}")
            elif t != "image" or not (isinstance(asset, str) and isinstance(assets.get(asset), dict)
                                         and assets[asset].get("kind") == "composed"):
                out.append(f"{tag}: layer allowed only on an image slot with a composed asset")

        if "target" in s:
            target = s["target"]
            if target not in TARGETS:
                out.append(f"{tag}: bad target {target!r} (fill or stroke)")
            elif t != "colour":
                out.append(f"{tag}: target allowed only on a colour slot")

    if "keep" in d:
        k = d["keep"]
        if not (isinstance(k, list) and all(isinstance(x, str) for x in k)):
            out.append("keep: must be a list of strings (locators of texts intentionally left as they are)")

    if "protected" in d:
        p = d["protected"]
        if not (isinstance(p, list) and all(isinstance(x, str) for x in p)):
            out.append("protected: must be a list of strings")

    env = d.get("envelope")
    if env is not None and "envelope" in d:
        if not isinstance(env, dict):
            out.append("envelope: must be null or an object")
        else:
            for k in ENVELOPE_PAIRS:
                if k not in env:
                    out.append(f"envelope: missing key {k!r}")
                elif not _pair(env[k], _num):
                    out.append(f"envelope: {k} must be a pair of numbers")
            if "seal_rot_canva" not in env:
                out.append("envelope: missing key 'seal_rot_canva'")
            elif not _num(env["seal_rot_canva"]):
                out.append("envelope: seal_rot_canva must be a number")
            # The seal is another asset of the map (a picture chosen first); composed envelopes read it by this key.
            sa = env.get("seal_asset")
            if sa is not None and (not isinstance(sa, str) or sa not in assets):
                out.append(f"envelope: seal_asset {sa!r} is not a known asset")
    return out


def validate_style(d, m) -> list:
    if not isinstance(d, dict):
        return ["style: not an object"]
    if not isinstance(m, dict):
        return ["style: map is not an object"]
    out = []
    pal = d.get("palette")
    if not isinstance(pal, dict):
        out.append("palette: not an object")
        pal = {}
    for role, c in pal.items():
        if not (isinstance(c, str) and _HEX.fullmatch(c)):
            out.append(f"palette {role!r}: {c!r} is not #rrggbb")
    prompts = d.get("image_prompts")
    if not isinstance(prompts, dict):
        out.append("image_prompts: not an object")
        prompts = {}
    assets = m.get("assets") if isinstance(m.get("assets"), dict) else {}
    for name in assets:
        if not _str(prompts.get(name)):
            out.append(f"image_prompts: asset {name!r} has no prompt")
    roles = d.get("colour_roles")
    if not isinstance(roles, dict):
        out.append("colour_roles: not an object")
        roles = {}
    for r, pr in roles.items():
        if not isinstance(pr, str) or pr not in pal:
            out.append(f"colour_roles {r!r}: {pr!r} is not a palette role")
    slots = m.get("slots") if isinstance(m.get("slots"), list) else []
    for s in slots:
        # Every colour slot's role must be mapped to a palette entry; otherwise apply_canva would refuse the run later
        # (canva/ops.py raises OpsError for a colour slot with no colour_roles entry), so it is caught here, at the style step.
        if (isinstance(s, dict) and s.get("type") == "colour"
                and (not isinstance(s.get("role"), str) or s.get("role") not in roles)):
            out.append(f"colour_roles: no entry for colour slot role {s.get('role')!r}")
    fonts = d.get("fonts")
    if not isinstance(fonts, dict):
        out.append("fonts: not an object")
        fonts = {}
    for k in FONT_ROLES:
        if not _str(fonts.get(k)):
            out.append(f"fonts: missing {k!r}")
    fm = d.get("font_map")
    if not isinstance(fm, dict):
        out.append("font_map: not an object")
        fm = {}
    for r, v in fm.items():
        if v not in FONT_ROLES:
            out.append(f"font_map {r!r}: {v!r} is not heading|body|script")
    return out
