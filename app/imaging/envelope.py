"""Envelope layers composed from skeleton geometry, and the checker that measures them again.

Ported from ``study/sage-linen/tools/compose_envelope.py`` (composer) and
``tools/check_assets.py:check_envelope`` (checker). The algorithm and the look constants are the same;
every position and size comes from ``geom`` (the ``envelope`` block of the skeleton's ``map.json``):

    {"section_px": [w, h], "tip": [x, y], "left_top": [x, y], "right_top": [x, y],
     "seal_centre": [x, y], "seal_size": [w, h], "seal_rot_canva": float}

Nothing here reads or writes files: images in, images (or a list of problems) out.

Layer order: the flap layer (flap + its soft shadow + the seal, if any) lies ABOVE the body layer. The
cover is the two layers flattened without the seal, so the three images agree by construction; the
checker measures that independently from the finished layers. The body layer reaches ``OVERLAP`` px
under the flap, so the two layers together have no transparent pixel.

Differences from the Sage & Linen scripts:
- the fold apex (where the body's two seams meet, hidden under the flap tip) was a constant
  (683, 585) = the tip shifted 25 px up; it is now ``(tip.x, tip.y - FOLD_APEX_RISE)``;
- the body seams start at the bottom corners of ``section_px`` (they were (0, 964) and (1366, 964));
- the texture is cover-cropped to a square-or-taller area before it is scaled to the frame width
  (identical for the square linen of the source, no distortion for other aspects);
- the seal is an argument (``None`` = no seal drawn, and ``check_envelope(..., seal_expected=False)``
  does not look for one);
- the checker also measures the flap and body edge positions against ``geom`` ((h), new).
"""
import math

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from .core import aspect_error, cover_crop

# ---- look constants (unchanged from the source; none of them is a position in the section) ------
TIP_RADIUS = 10.0              # canva px, the flap tip is slightly rounded
FOLD_APEX_RISE = 25.0          # canva px, apex = tip shifted up by this much (source: 610 -> 585)
BODY_GAIN = 0.99               # body about 4 % darker than the flap
FLAP_GAIN = 1.03
OVERLAP = 3.0                  # canva px, the body layer reaches this far under the flap
SHADOW = {"sigma_px": 12.0, "dy_px": 5.0, "alpha": 0.35, "rgb": (26, 22, 14)}

# ---- checker constants ---------------------------------------------------------------------------
MAD_LIMIT = 2.0                # (d) mean abs difference of the flattened layers vs the cover, of 255
SEAL_PRESENT_MIN = 5.0         # (d-control) mean abs difference inside the seal box when a seal is expected
STRONG_DIFF = 25               # pixels differing more than this are "the seal"
STRONG_FRACTION = 0.0005       # with no seal expected, at most this share of pixels may differ that much
CENTROID_TOL = 6.0             # canva px, (f)
BOX_PAD = 2.0                  # canva px added around the rotated seal's bounding box (source: 4 px at 2x)
EDGE_TOL = 1.5                 # canva px, (h) flap/body edge measured vs the geometry
EDGE_SAMPLES = (0.25, 0.5, 0.75)   # fractions along each diagonal where (h) measures
EDGE_ALPHA = 192               # shadow alpha stays below 0.5 (128), so >= 192 is the flap/body proper

_REQUIRED = ("section_px", "tip", "left_top", "right_top")
_SEAL_KEYS = ("seal_centre", "seal_size", "seal_rot_canva")


def _pair(geom, key):
    try:
        a, b = geom[key]
        return float(a), float(b)
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"envelope geometry needs {key!r} as [x, y]; got {geom.get(key)!r}") from None


def _geometry(geom, need_seal):
    """Validated, numeric copy of the geometry (section coordinates)."""
    if not isinstance(geom, dict):
        raise ValueError(f"envelope geometry must be a dict, got {type(geom).__name__}")
    keys = _REQUIRED + (_SEAL_KEYS if need_seal else ())
    for k in keys:
        if geom.get(k) is None:
            raise ValueError(f"envelope geometry is missing {k!r}")
    g = {k: _pair(geom, k) for k in _REQUIRED}
    w, h = g["section_px"]
    if w <= 0 or h <= 0:
        raise ValueError(f"bad section_px {g['section_px']}")
    tx, ty = g["tip"]
    (lx, ly), (rx, ry) = g["left_top"], g["right_top"]
    if not (0 <= lx < tx < rx <= w):
        raise ValueError(f"need 0 <= left_top.x < tip.x < right_top.x <= width; got {lx}, {tx}, {rx}, width {w}")
    if not (0 <= ly < ty < h and 0 <= ry < ty):
        raise ValueError(f"the tip must lie below both top corners and inside the section: "
                         f"left_top.y {ly}, right_top.y {ry}, tip.y {ty}, height {h}")
    if need_seal:
        g["seal_centre"] = _pair(geom, "seal_centre")
        g["seal_size"] = _pair(geom, "seal_size")
        if g["seal_size"][0] <= 0 or g["seal_size"][1] <= 0:
            raise ValueError(f"bad seal_size {g['seal_size']}")
        try:
            g["seal_rot_canva"] = float(geom["seal_rot_canva"])
        except (TypeError, ValueError):
            raise ValueError(f"bad seal_rot_canva {geom['seal_rot_canva']!r}") from None
    return g


def _scale(scale):
    if not isinstance(scale, (int, float)) or isinstance(scale, bool) or not scale > 0:
        raise ValueError(f"scale must be a positive number, got {scale!r}")
    return float(scale)


def _frame_px(g, S):
    return int(round(g["section_px"][0] * S)), int(round(g["section_px"][1] * S))


def _half_plane(x, y, p0, p1, inside_pt):
    """Signed distance (section px) to the line p0-p1, positive on the side of inside_pt."""
    d = np.array([p1[0] - p0[0], p1[1] - p0[1]], np.float32)
    n = np.array([-d[1], d[0]], np.float32)
    n /= np.linalg.norm(n)
    if (inside_pt[0] - p0[0]) * n[0] + (inside_pt[1] - p0[1]) * n[1] < 0:
        n = -n
    return (x - p0[0]) * n[0] + (y - p0[1]) * n[1]


def _to_img(rgb, a):
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.clip(a, 0, 1) * 255]).round().astype(np.uint8), "RGBA")


def _seal_layer(seal, g, S, size):
    """The seal scaled to seal_size, turned by seal_rot_canva (clockwise in Canva) and placed at the centre."""
    sw, sh = int(round(g["seal_size"][0] * S)), int(round(g["seal_size"][1] * S))
    if not isinstance(seal, Image.Image):
        raise ValueError(f"seal must be a PIL image or None, got {type(seal).__name__}")
    if aspect_error(seal.size, g["seal_size"]) >= 0.005:
        raise ValueError(f"seal {seal.size} does not have the aspect of seal_size {tuple(g['seal_size'])} within 0.5 %")
    seal = seal.convert("RGBA")
    seal2 = seal.convert("RGBa").resize((sw, sh), Image.LANCZOS).convert("RGBA")
    # Canva degrees are clockwise; PIL's are counter-clockwise
    seal_rot = seal2.convert("RGBa").rotate(-g["seal_rot_canva"], resample=Image.BICUBIC, expand=True).convert("RGBA")
    px = int(round(g["seal_centre"][0] * S - seal_rot.width / 2))
    py = int(round(g["seal_centre"][1] * S - seal_rot.height / 2))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.paste(seal_rot, (px, py))
    return layer


def compose_envelope(texture, geom, scale=2, seal=None):
    """Compose the envelope for ``geom``. Returns ``(cover, flap, body)``.

    cover: RGB, the two layers flattened (no seal); flap: RGBA, flap + shadow + seal, lies above
    body: RGBA, the part below the flap line, reaching OVERLAP px under it. All are
    ``round(section_px * scale)`` pixels. ``texture`` is any RGB image (the linen); ``seal`` is an RGBA
    image with the aspect of ``seal_size`` or None for an envelope without a seal.
    """
    S = _scale(scale)
    g = _geometry(geom, need_seal=seal is not None)
    if not isinstance(texture, Image.Image):
        raise ValueError(f"texture must be a PIL image, got {type(texture).__name__}")
    if seal is not None:                                     # refuse a bad seal before the heavy work
        if not isinstance(seal, Image.Image):
            raise ValueError(f"seal must be a PIL image or None, got {type(seal).__name__}")
        if aspect_error(seal.size, g["seal_size"]) >= 0.005:
            raise ValueError(f"seal {seal.size} does not have the aspect of seal_size {tuple(g['seal_size'])} within 0.5 %")
    W, H = _frame_px(g, S)
    FW, FH = g["section_px"]
    tip, left_top, right_top = g["tip"], g["left_top"], g["right_top"]
    fold_apex = (tip[0], tip[1] - FOLD_APEX_RISE)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    x = (xx + 0.5) / S
    y = (yy + 0.5) / S

    # flap: above both diagonals, with a slightly rounded tip
    inside = (tip[0], 0.0)
    a_l = _half_plane(x, y, left_top, tip, inside)
    a_r = _half_plane(x, y, right_top, tip, inside)
    r = TIP_RADIUS
    qa, qb = np.maximum(r - a_l, 0), np.maximum(r - a_r, 0)
    sd_flap = -(np.hypot(qa, qb) + np.minimum(np.maximum(r - a_l, r - a_r), 0) - r)   # positive inside
    flap_a = np.clip(sd_flap * S + 0.5, 0, 1)

    # texture: scaled to the frame width, at least square; body takes the lower part, flap the same part turned
    Hb = max(W, H)
    tex = texture.convert("RGB")
    tex = cover_crop(tex, (W, Hb)).resize((W, Hb), Image.LANCZOS)
    body_tex = np.asarray(tex.crop((0, Hb - H, W, Hb))).astype(np.float32)
    flap_tex = np.asarray(tex.rotate(180).crop((0, 0, W, H))).astype(np.float32)

    # body: two faint seams from the bottom corners to the apex
    b_l = _half_plane(x, y, (0, FH), fold_apex, (FW / 2, FH))
    b_r = _half_plane(x, y, (FW, FH), fold_apex, (FW / 2, FH))
    sd_bot = np.minimum(b_l, b_r)                                   # positive inside the bottom flap
    body = body_tex * BODY_GAIN
    body *= np.where(sd_bot > 0, 1.010, 1.0)[..., None]             # bottom flap lies on top: a touch lighter
    seam_line = np.exp(-(sd_bot / 0.9) ** 2) * 0.11
    seam_shadow = np.where(sd_bot < 0, np.exp(np.minimum(sd_bot, 0) / 5.0), 0) * 0.07
    seam_light = np.where(sd_bot > 0, np.exp(-np.maximum(sd_bot, 0) / 1.6), 0) * 0.05
    body = body * (1 - np.clip(seam_line + seam_shadow, 0, 1)[..., None])
    body = body + (255 - body) * seam_light[..., None]
    body = np.clip(body, 0, 255)
    body_a = 1.0 - np.clip((sd_flap - OVERLAP) * S + 0.5, 0, 1)

    # flap: lighter linen, hairline dark edge, faint inner highlight
    flap = flap_tex * FLAP_GAIN
    edge_dark = np.clip(1.0 - sd_flap / 1.1, 0, 1) * (sd_flap > 0) * 0.16
    edge_light = np.exp(-((sd_flap - 3.0) / 2.0) ** 2) * (sd_flap > 0) * 0.035
    flap = flap * (1 - edge_dark[..., None])
    flap = flap + (255 - flap) * edge_light[..., None]
    flap = np.clip(flap, 0, 255)

    # shadow carried by the flap layer
    hard = (sd_flap > 0).astype(np.float32)
    sh = ndi.gaussian_filter(hard, SHADOW["sigma_px"] * S)
    sh = ndi.shift(sh, (SHADOW["dy_px"] * S, 0), order=1, mode="nearest")
    contact = ndi.shift(ndi.gaussian_filter(hard, 2.0 * S), (1.5 * S, 0), order=1, mode="nearest") * 0.16
    sh_a = np.clip(sh * SHADOW["alpha"] + contact * (1 - sh * SHADOW["alpha"]), 0, 1)
    SH = np.array(SHADOW["rgb"], np.float32)

    flap_layer_a = flap_a + sh_a * (1 - flap_a)
    safe = np.maximum(flap_layer_a, 1e-6)[..., None]
    flap_layer_rgb = (flap * flap_a[..., None] + SH * (sh_a * (1 - flap_a))[..., None]) / safe

    body_img = _to_img(body, body_a)
    flap_img = _to_img(flap_layer_rgb, flap_layer_a)

    # cover = flap layer (no seal) over body layer, flattened over black to expose any hole
    base = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    cover = Image.alpha_composite(Image.alpha_composite(base, body_img), flap_img).convert("RGB")

    if seal is not None:
        flap_img = Image.alpha_composite(flap_img, _seal_layer(seal, g, S, (W, H)))
    return cover, flap_img, body_img


# ---------------------------------------------------------------- checker
def _seal_box(g, S, W, H):
    """Bounding box (px, clipped to the image) of the rotated seal, padded by BOX_PAD canva px."""
    rot = math.radians(abs(g["seal_rot_canva"]))
    sw, sh = g["seal_size"][0] * S, g["seal_size"][1] * S
    bw = sw * math.cos(rot) + sh * math.sin(rot)
    bh = sw * math.sin(rot) + sh * math.cos(rot)
    cx, cy = g["seal_centre"][0] * S, g["seal_centre"][1] * S
    pad = int(round(BOX_PAD * S))
    x0, y0 = int(cx - bw / 2) - pad, int(cy - bh / 2) - pad
    x1, y1 = int(math.ceil(cx + bw / 2)) + pad, int(math.ceil(cy + bh / 2)) + pad
    return max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)


def _measure_edges(flap_a, body_a, g, S, box):
    """(h) Where the flap's lower edge and the body's upper edge really are, against the geometry.

    Measured on columns along both diagonals (outside the seal box): the last row of the flap layer whose
    alpha is flap-like, the first such row of the body layer. Independent of how the layers were made.
    """
    problems = []
    tip = g["tip"]
    H = flap_a.shape[0]
    for name, top in (("left", g["left_top"]), ("right", g["right_top"])):
        dx, dy = tip[0] - top[0], tip[1] - top[1]
        length = math.hypot(dx, dy)
        for t in EDGE_SAMPLES:
            col = int((top[0] + t * dx) * S)
            xc = (col + 0.5) / S
            if box is not None and box[0] <= col < box[2]:
                continue                                    # the seal hides the flap edge here
            line_y = top[1] + (xc - top[0]) * dy / dx       # the diagonal's y at this column (section px)
            rows_f = np.nonzero(flap_a[:, col] >= EDGE_ALPHA)[0]
            rows_b = np.nonzero(body_a[:, col] >= EDGE_ALPHA)[0]
            if rows_f.size == 0 or rows_b.size == 0:
                problems.append(f"(h) {name} diagonal, column {col}: flap or body layer has no solid pixel there")
                continue
            flap_edge = (rows_f.max() + 1) / S
            body_edge = rows_b.min() / S
            want_body = line_y - OVERLAP * length / abs(dx)   # OVERLAP is perpendicular; convert to vertical
            if abs(flap_edge - line_y) > EDGE_TOL:
                problems.append(f"(h) {name} diagonal at x={xc:.0f}: flap edge at y={flap_edge:.1f}, "
                                f"geometry says {line_y:.1f} (tolerance {EDGE_TOL})")
            if abs(body_edge - want_body) > EDGE_TOL:
                problems.append(f"(h) {name} diagonal at x={xc:.0f}: body starts at y={body_edge:.1f}, "
                                f"geometry says {want_body:.1f} (tolerance {EDGE_TOL})")
    return problems


def check_envelope(cover, flap, body, geom, scale=2, *, seal=None, seal_expected=True):
    """Measure finished layers against ``geom``. Returns a list of problems (empty = good).

    Checks: (d) sizes/modes, flap over body reproduces the cover outside the seal box (mean abs
    difference < 2 of 255); (e) the two layers stacked leave no transparent pixel; (h) the flap's and the
    body's edges lie where the geometry says; (d-control) a seal is really found inside the seal box, and
    (f) its centroid is at ``seal_centre`` (+-6 px); (g) when ``seal`` (the seal image) is given, cover +
    seal placed per geometry equals the layers inside the box.
    With ``seal_expected=False`` no seal is looked for: the layers must reproduce the cover everywhere.
    """
    S = _scale(scale)
    if seal is not None and not seal_expected:
        raise ValueError("a seal image was given but seal_expected is False")
    g = _geometry(geom, need_seal=seal_expected)
    W, H = _frame_px(g, S)
    for label, im in (("cover", cover), ("flap", flap), ("body", body)):
        if not isinstance(im, Image.Image):
            return [f"(d) {label} is not an image"]
    if not (cover.size == flap.size == body.size):
        return [f"(d) sizes differ: cover {cover.size}, flap {flap.size}, body {body.size}"]
    if cover.size != (W, H):
        return [f"(d) layers are {cover.size} but the geometry at scale {S:g} needs {(W, H)}"]
    if flap.mode != "RGBA" or body.mode != "RGBA":
        return [f"(d) overlays must be RGBA: flap {flap.mode}, body {body.mode}"]
    cover = cover.convert("RGB")

    problems = []
    both = Image.alpha_composite(body, flap)                      # flap above body, on nothing
    a = np.asarray(both.getchannel("A"))
    if a.min() < 255:
        problems.append(f"(e) {int((a < 255).sum())} pixel(s) not fully opaque when the two layers are stacked "
                        f"(min alpha {a.min()})")
    comp = np.asarray(both.convert("RGB")).astype(np.float64)
    diff = np.abs(comp - np.asarray(cover).astype(np.float64)).mean(axis=2)

    box = _seal_box(g, S, W, H) if seal_expected else None
    if box is None:
        mad_out = float(diff.mean())
        if mad_out >= MAD_LIMIT:
            problems.append(f"(d) flap over body differs from the cover: mean abs {mad_out:.2f} >= {MAD_LIMIT:g} "
                            f"(no seal is expected, so nothing may differ)")
        strong = float((diff > STRONG_DIFF).mean())
        if strong > STRONG_FRACTION:
            problems.append(f"(d) {strong * 100:.2f} % of the pixels differ from the cover by more than {STRONG_DIFF} "
                            f"although no seal is expected (a seal baked into the flap layer?)")
    else:
        x0, y0, x1, y1 = box
        outside = np.ones(diff.shape, bool)
        outside[y0:y1, x0:x1] = False
        mad_out = float(diff[outside].mean()) if outside.any() else 0.0
        mad_in = float(diff[y0:y1, x0:x1].mean())
        if mad_out >= MAD_LIMIT:
            problems.append(f"(d) flap over body differs from the cover outside the seal box: "
                            f"mean abs {mad_out:.2f} >= {MAD_LIMIT:g}")
        # the comparison must be able to see a difference: the seal is in the overlays and not in the cover
        if mad_in < SEAL_PRESENT_MIN:
            problems.append(f"(d-control) no seal found inside the seal box (mean abs diff {mad_in:.2f} < "
                            f"{SEAL_PRESENT_MIN:g}): either the seal is missing from the flap layer or the cover has one")
        else:
            ys, xs = np.nonzero(diff > STRONG_DIFF)
            if xs.size == 0:
                problems.append("(f) no pixel differs strongly between the layers and the cover: no seal to locate")
            else:
                cx, cy = float(xs.mean()) / S, float(ys.mean()) / S
                sx, sy = g["seal_centre"]
                if abs(cx - sx) > CENTROID_TOL or abs(cy - sy) > CENTROID_TOL:
                    problems.append(f"(f) seal centroid {cx:.1f},{cy:.1f} is not at {sx:g},{sy:g} (+-{CENTROID_TOL:g} px)")
        if seal is not None:
            # the seal placed over the cover per the geometry must give what the layers show inside the box
            # (written out again, not shared with the composer, so a shared mistake cannot hide itself)
            sw, sh = int(round(g["seal_size"][0] * S)), int(round(g["seal_size"][1] * S))
            s2 = seal.convert("RGBa").resize((sw, sh), Image.LANCZOS)
            s2 = s2.rotate(-g["seal_rot_canva"], resample=Image.BICUBIC, expand=True).convert("RGBA")
            page1 = cover.convert("RGBA")
            page1.alpha_composite(s2, (int(round(g["seal_centre"][0] * S - s2.width / 2)),
                                       int(round(g["seal_centre"][1] * S - s2.height / 2))))
            d2 = np.abs(np.asarray(page1.convert("RGB")).astype(np.float64) - comp).mean(axis=2)
            m = float(d2[y0:y1, x0:x1].mean())
            if m >= MAD_LIMIT:
                problems.append(f"(g) cover + seal placed per geometry differs from the layers inside the seal "
                                f"box: mean abs {m:.2f} >= {MAD_LIMIT:g}")

    problems += _measure_edges(np.asarray(flap.getchannel("A")), np.asarray(body.getchannel("A")), g, S, box)
    return problems
