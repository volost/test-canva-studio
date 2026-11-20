"""Cut-outs from a near-white ground (ported from cutout_watercolour.py, cutout_solid.py and
pilot/tools/white_to_alpha.py). Both functions take a PIL image and return a tight-cropped RGBA
image; padding to a frame is ``core.pad_to_frame``. No files, no globals.
"""
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

_BORDER = 8


def _border_colour(rgb):
    b = _BORDER
    border = np.concatenate([rgb[:b].reshape(-1, 3), rgb[-b:].reshape(-1, 3),
                             rgb[:, :b].reshape(-1, 3), rgb[:, -b:].reshape(-1, 3)])
    return border, np.median(border, axis=0)


def _tight_crop(img, threshold=8):
    bbox = img.getchannel("A").point(lambda v: 255 if v > threshold else 0).getbbox()
    if not bbox:
        raise ValueError("nothing left after the cut-out")
    return img.crop(bbox)


def watercolour_to_alpha(img, speck=80, *, opacity=1.05, keep_main_only=False):
    """Watercolour on white -> transparent RGBA.

    The paper white is normalised to pure white, alpha is taken from the distance to white
    (white_to_alpha.py's formula, 0.04 noise floor) and scaled by ``opacity`` x the exact alpha
    (1.0 = flattened on white it looks exactly like the painting). Painted islands smaller than
    ``speck`` px are dropped, the result is cropped tight.
    """
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    _, bg = _border_colour(rgb)
    if bg.min() <= 228:
        raise ValueError(f"background is not near-white: median border colour {bg}")
    # paper white -> pure white, with 2 levels of headroom for paper noise
    norm = np.clip(rgb * (255.0 / (bg - 2.0)), 0, 255).round().astype(np.uint8)

    f = norm.astype(np.float32) / 255.0
    exact = np.clip((1.0 - f.min(axis=2) - 0.04) / 0.96, 0.0, 1.0)
    safe = np.maximum(exact, 1e-6)[..., None]
    colour = np.clip((f - (1.0 - exact[..., None])) / safe, 0.0, 1.0)  # un-mixed from white
    alpha = np.clip(exact * opacity, 0.0, 1.0)

    arr = (np.dstack([colour, alpha]) * 255.0).round().astype(np.uint8)
    ink = arr[..., 3] > 8
    if not ink.any():
        raise ValueError("nothing but white found in the source image")
    lab, n = ndi.label(ink, structure=np.ones((3, 3)))
    sizes = ndi.sum(ink, lab, index=np.arange(1, n + 1))
    if keep_main_only:
        small = [i for i, s in enumerate(sizes, start=1) if s < sizes.max()]
    else:
        small = [i for i, s in enumerate(sizes, start=1) if s < speck]
    if small:
        arr[np.isin(lab, small), 3] = 0
    cut = _tight_crop(Image.fromarray(arr, "RGBA"))
    coverage = float((np.asarray(cut.getchannel("A")) > 8).mean())
    if not 0.01 < coverage < 0.95:
        raise ValueError(f"suspicious ink coverage {coverage:.3f}: background was probably not white")
    return cut


def solid_cutout(img, tol=14, holes=None, erode=2, feather=1.0):
    """Cut a solid object out of a near-white background by flood-filling from the borders.

    Keeps highlights inside the object opaque: only near-background pixels connected to the border
    (and, with ``holes``, enclosed background areas of at least that many px, such as the inside of a
    ring) become transparent. The edge is eroded and feathered and takes its colour from the inside of
    the object, so no white halo remains.
    """
    holes = holes or 0
    rgb = np.asarray(img.convert("RGB")).astype(np.float32)
    _, bg = _border_colour(rgb)
    if bg.min() <= 222:
        raise ValueError(f"background is not near-white: median border colour {bg}")

    # near-background: within tol of the border colour, or brighter than it
    dist = np.abs(rgb - bg).max(axis=2)
    near = (dist < tol) | (rgb.min(axis=2) >= bg.min())
    lab, n = ndi.label(near)
    edge_labels = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    edge_labels = edge_labels[edge_labels != 0]
    bgmask = np.isin(lab, edge_labels)
    if holes > 0:
        sizes = ndi.sum(near, lab, index=np.arange(1, n + 1))
        for i, s in enumerate(sizes, start=1):
            if i in edge_labels or s < holes:
                continue
            bgmask |= lab == i

    obj = ~bgmask
    # keep the main object and anything at least 5 % of its size; drop specks
    olab, on = ndi.label(obj)
    if on < 1:
        raise ValueError("no object found")
    osz = ndi.sum(obj, olab, index=np.arange(1, on + 1))
    keep = [i for i, s in enumerate(osz, start=1) if s >= 0.05 * osz.max()]
    obj = np.isin(olab, keep)

    core = ndi.binary_erosion(obj, iterations=erode) if erode > 0 else obj
    alpha = ndi.gaussian_filter(core.astype(np.float32), feather) if feather > 0 else core.astype(np.float32)
    alpha = np.clip(alpha, 0, 1)

    # edge colour comes from the nearest pixel safely inside the object (removes the white fringe)
    inner = ndi.binary_erosion(obj, iterations=erode + 2)
    if not inner.any():
        raise ValueError("object too thin for the chosen erosion")
    _, (iy, ix) = ndi.distance_transform_edt(~inner, return_indices=True)
    colour = rgb.copy()
    edge_band = ~inner
    colour[edge_band] = rgb[iy[edge_band], ix[edge_band]]

    rgba = np.dstack([colour, alpha * 255.0]).round().astype(np.uint8)
    return _tight_crop(Image.fromarray(rgba, "RGBA"))
