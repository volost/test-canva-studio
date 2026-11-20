"""Cover geometry for image fills.

update_fill leaves the image box about 11 px larger than the frame on every side; crop_media must then set the
exact cover box this module computes.

Usage: python -I canva/geometry.py <frame_w> <frame_h> <img_w> <img_h>   (prints the cover box)
"""
import math
import sys


def cover_box(frame_w, frame_h, img_w, img_h) -> dict:
    """The image box (in frame pixels) that covers the frame with the image's aspect, centred.

    `scale = max(frame_w / img_w, frame_h / img_h)`; width/height = image size * scale; left/top centre it."""
    for name, v in (("frame_w", frame_w), ("frame_h", frame_h), ("img_w", img_w), ("img_h", img_h)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError(f"{name} must be a positive finite number, got {v!r}")
    sc = max(frame_w / img_w, frame_h / img_h)
    w, h = img_w * sc, img_h * sc
    return {"left": (frame_w - w) / 2, "top": (frame_h - h) / 2, "width": w, "height": h}


def main(argv) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    try:
        b = cover_box(*[float(x) for x in argv])
    except ValueError as e:
        print(f"error: {e}")
        return 2
    print("cover box: " + " ".join(f"{k}={round(v, 4):g}" for k, v in b.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
