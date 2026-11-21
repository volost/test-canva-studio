"""Geometry and alpha helpers (ported from study/sage-linen/tools/lib.py, without global paths).

Differences from the source: ``cover_crop`` and ``pad_to_frame`` return just the image (the source
also returned a box / info dict), ``alpha_coverage`` returns the single float ``coverage_gt8``
(the source returned a dict; ``alpha_stats`` keeps that dict), asserts became ``ValueError``.

Used by assets.py (cover_crop, pad_to_frame, aspect_error), contact sheets (checker, on_background) and the
envelope composer. ASPECT_TOLERANCE is the project-wide 0.5 % frame tolerance; every function that makes an image
for a frame re-checks it and raises rather than return a picture of the wrong proportions.
"""
import numpy as np
from PIL import Image

ASPECT_TOLERANCE = 0.005  # 0.5 %, the project's frame-aspect tolerance


def _check_frame(frame):
    if len(frame) != 2 or frame[0] <= 0 or frame[1] <= 0:
        raise ValueError(f"bad frame {frame!r}")


def aspect_error(size, frame):
    """Relative difference between an image's aspect and a frame's aspect (0.005 = 0.5 %)."""
    _check_frame(size)
    _check_frame(frame)
    return abs((size[0] / size[1]) / (frame[0] / frame[1]) - 1.0)


def cover_crop(img, frame, cx=0.5, cy=0.5):
    """Largest crop of img with the frame's aspect. cx, cy in 0..1 place the crop window."""
    _check_frame(frame)
    w, h = img.size
    fa = frame[0] / frame[1]
    if w / h > fa:
        cw, ch = int(round(h * fa)), h
    else:
        cw, ch = w, int(round(w / fa))
    x0 = int(round((w - cw) * cx))
    y0 = int(round((h - ch) * cy))
    out = img.crop((x0, y0, x0 + cw, y0 + ch))
    if aspect_error(out.size, frame) >= ASPECT_TOLERANCE:
        raise ValueError(f"cannot crop {img.size} to the aspect of {tuple(frame)} within 0.5 % (got {out.size})")
    return out


def resize_rgba(img, size, resample=Image.LANCZOS):
    """Resize an RGBA image with premultiplied alpha, so edges get no dark or white fringe.

    LANCZOS rings where a hard edge meets a semi-transparent area: pass Image.BOX or Image.HAMMING there.
    """
    return img.convert("RGBa").resize(size, resample).convert("RGBA")


def pad_to_frame(img, frame, scale, margin=0.0, anchor=(0.5, 0.5), resample=Image.LANCZOS):
    """Fit a tight RGBA cut-out inside a transparent canvas of exactly scale x frame. Never crops.

    margin is the fraction of the canvas kept free on every side.
    """
    if img.mode != "RGBA":
        raise ValueError(f"pad_to_frame needs an RGBA image, got {img.mode}")
    _check_frame(frame)
    W, H = int(round(frame[0] * scale)), int(round(frame[1] * scale))
    aw, ah = W * (1 - 2 * margin), H * (1 - 2 * margin)
    if aw <= 0 or ah <= 0:
        raise ValueError("margin leaves no room for the image")
    k = min(aw / img.width, ah / img.height)
    nw, nh = max(1, int(round(img.width * k))), max(1, int(round(img.height * k)))
    small = resize_rgba(img, (nw, nh), resample) if (nw, nh) != img.size else img
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = int(round((W - nw) * anchor[0]))
    y = int(round((H - nh) * anchor[1]))
    canvas.paste(small, (x, y))
    if aspect_error(canvas.size, frame) >= ASPECT_TOLERANCE:
        raise ValueError(f"canvas {canvas.size} does not match the aspect of {tuple(frame)}")
    return canvas


def alpha_stats(img):
    a = np.asarray(img.getchannel("A"))
    return {"coverage_gt8": round(float((a > 8).mean()), 4),
            "opaque_gt250": round(float((a > 250).mean()), 4),
            "min_alpha": int(a.min()), "max_alpha": int(a.max())}


def alpha_coverage(img):
    """Fraction of pixels whose alpha is above 8 (the source's ``coverage_gt8``)."""
    return alpha_stats(img)["coverage_gt8"]


def checker(size, cell=16, a=(128, 128, 128), b=(160, 160, 160)):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((xx // cell + yy // cell) % 2).astype(bool)
    arr = np.empty((h, w, 3), np.uint8)
    arr[~m] = a
    arr[m] = b
    return Image.fromarray(arr, "RGB")


def on_background(img, bg):
    """Flatten an RGBA image over a solid colour or over another RGB image of the same size."""
    base = Image.new("RGB", img.size, bg) if isinstance(bg, tuple) else bg.copy()
    base.paste(img, (0, 0), img)
    return base
