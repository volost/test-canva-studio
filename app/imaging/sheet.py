"""Contact sheet (ported from sage-linen/tools/contact_sheet.py): labelled thumbnails in a grid,
transparent files on a mid-grey checker. Items and output are parameters; the long edge is capped.

Called by assets.build_manifest. A missing file is drawn as "MISSING" rather than raising, so the sheet the owner
looks at shows the gap. The long edge is capped at 1568 px because larger images are downscaled anyway when a
model looks at them."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .core import checker, on_background, resize_rgba

MAX_LONG_EDGE = 1568  # larger images are auto-resized by the API anyway
COLS = 6
_BASE = dict(cell_w=248, thumb_h=214, gap=10)
_MIN_FONT = 8  # FreeType in Pillow fails ("division by zero") below this size
_FONT = "/System/Library/Fonts/Helvetica.ttc"


def _font(size):
    try:
        return ImageFont.truetype(_FONT, size)
    except OSError:
        return ImageFont.load_default(size)


def _dims(k, cols, rows):
    d = {name: max(1, int(v * k)) for name, v in _BASE.items()}
    d["font"] = max(_MIN_FONT, int(12 * k))
    d["label_h"] = 2 * d["font"] + 8  # two text lines
    W = d["gap"] + cols * (d["cell_w"] + d["gap"])
    H = d["gap"] + rows * (d["thumb_h"] + d["label_h"] + d["gap"])
    return d, W, H


def contact_sheet(items, out, long_edge=MAX_LONG_EDGE):
    """items: [(label, path)]. Writes a JPEG to ``out`` (long edge <= long_edge) and returns it."""
    if not items:
        raise ValueError("contact_sheet needs at least one item")
    if not 100 <= long_edge <= MAX_LONG_EDGE:
        raise ValueError(f"long_edge must be between 100 and {MAX_LONG_EDGE}, got {long_edge}")
    out = Path(out)
    cols = min(COLS, len(items))
    rows = (len(items) + cols - 1) // cols
    k = 1.0
    d, W, H = _dims(k, cols, rows)
    while max(W, H) > long_edge:
        k *= 0.97
        d, W, H = _dims(k, cols, rows)
        if k < 0.05:
            raise ValueError("too many items for this long_edge")

    gap, cell_w, thumb_h, label_h = d["gap"], d["cell_w"], d["thumb_h"], d["label_h"]
    sheet = Image.new("RGB", (W, H), (236, 233, 226))
    draw = ImageDraw.Draw(sheet)
    f_bold, f_small = _font(d["font"]), _font(d["font"])
    pad = max(1, int(4 * k))
    for i, (label, path) in enumerate(items):
        cx = gap + (i % cols) * (cell_w + gap)
        cy = gap + (i // cols) * (thumb_h + label_h + gap)
        draw.rectangle([cx, cy, cx + cell_w - 1, cy + thumb_h - 1], fill=(214, 210, 201))
        path = Path(path)
        if not path.is_file():
            draw.text((cx + pad, cy + pad), "MISSING", font=f_bold, fill=(170, 30, 30))
            size_txt = "missing"
        else:
            with Image.open(path) as im:
                im.load()
            size_txt = f"{im.width}x{im.height}"
            s = min((cell_w - 2 * pad) / im.width, (thumb_h - 2 * pad) / im.height)
            tw, th = max(1, round(im.width * s)), max(1, round(im.height * s))
            if im.mode in ("RGBA", "LA", "P") and (im.mode != "P" or "transparency" in im.info):
                thumb = resize_rgba(im.convert("RGBA"), (tw, th))
                thumb = on_background(thumb, checker((tw, th), cell=max(2, int(8 * k))))
            else:
                thumb = im.convert("RGB").resize((tw, th), Image.LANCZOS)
            sheet.paste(thumb, (cx + (cell_w - tw) // 2, cy + (thumb_h - th) // 2))
        draw.text((cx + 2, cy + thumb_h + 2), str(label), font=f_bold, fill=(30, 36, 28))
        draw.text((cx + 2, cy + thumb_h + 2 + f_bold.size + 2), size_txt, font=f_small, fill=(95, 100, 90))

    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    return out
