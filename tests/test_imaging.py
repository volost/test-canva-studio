"""Imaging library: synthetic images only, files only in temp dirs."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app.imaging.core import aspect_error, cover_crop, pad_to_frame, alpha_coverage
from app.imaging.cutout import watercolour_to_alpha, solid_cutout
from app.imaging.sheet import contact_sheet


def white(size, colour=(255, 255, 255)):
    return Image.new("RGB", size, colour)


class CoreTests(unittest.TestCase):
    def test_aspect_error_values(self):
        self.assertAlmostEqual(aspect_error((200, 100), (2, 1)), 0.0)
        # control: a clearly wrong aspect is reported as a large error
        self.assertGreater(aspect_error((100, 100), (2, 1)), 0.4)

    def test_cover_crop_exact_aspect(self):
        img = Image.new("RGB", (1000, 700), (10, 20, 30))
        out = cover_crop(img, (433, 600))
        self.assertLess(aspect_error(out.size, (433, 600)), 0.005)
        self.assertEqual(out.size[1], 700)  # largest crop: full height kept
        # control: the uncropped source is NOT within tolerance
        self.assertGreater(aspect_error(img.size, (433, 600)), 0.005)

    def test_cover_crop_tall_source_and_position(self):
        img = Image.new("RGB", (300, 900))
        ImageDraw.Draw(img).rectangle([0, 0, 299, 299], fill=(255, 0, 0))
        top = cover_crop(img, (3, 1), cx=0.5, cy=0.0)
        self.assertEqual(top.size, (300, 100))
        self.assertEqual(top.getpixel((5, 5)), (255, 0, 0))
        bottom = cover_crop(img, (3, 1), cx=0.5, cy=1.0)
        self.assertNotEqual(bottom.getpixel((5, 5)), (255, 0, 0))

    def test_cover_crop_rejects_bad_frame(self):
        with self.assertRaises(ValueError):
            cover_crop(Image.new("RGB", (10, 10)), (0, 5))

    def test_pad_keeps_alpha(self):
        img = Image.new("RGBA", (40, 20), (200, 30, 30, 255))
        out = pad_to_frame(img, (160, 198), 2.0)
        self.assertEqual(out.mode, "RGBA")
        self.assertEqual(out.size, (320, 396))
        self.assertLess(aspect_error(out.size, (160, 198)), 0.005)
        for corner in [(0, 0), (319, 0), (0, 395), (319, 395)]:
            self.assertEqual(out.getpixel(corner)[3], 0)
        self.assertEqual(out.getpixel((160, 198)), (200, 30, 30, 255))

    def test_pad_margin_and_anchor(self):
        img = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
        out = pad_to_frame(img, (100, 100), 1.0, margin=0.1, anchor=(0.0, 0.0))
        bbox = out.getchannel("A").getbbox()
        self.assertEqual(bbox, (0, 0, 80, 80))

    def test_pad_rejects_non_rgba(self):
        with self.assertRaises(ValueError):
            pad_to_frame(Image.new("RGB", (4, 4)), (10, 10), 1.0)

    def test_alpha_coverage(self):
        a = np.zeros((10, 10, 4), np.uint8)
        a[:5, :, 3] = 255
        self.assertAlmostEqual(alpha_coverage(Image.fromarray(a, "RGBA")), 0.5)
        # control: fully transparent and fully opaque give 0 and 1
        self.assertEqual(alpha_coverage(Image.new("RGBA", (4, 4), (0, 0, 0, 0))), 0.0)
        self.assertEqual(alpha_coverage(Image.new("RGBA", (4, 4), (0, 0, 0, 255))), 1.0)


class WatercolourTests(unittest.TestCase):
    def _painted(self):
        img = white((200, 200))
        d = ImageDraw.Draw(img)
        d.ellipse([60, 60, 140, 140], fill=(40, 120, 60))
        return img

    def test_watercolour_white_becomes_transparent(self):
        img = self._painted()
        # add a speck far from the main blob
        ImageDraw.Draw(img).rectangle([10, 10, 14, 14], fill=(40, 120, 60))
        out = watercolour_to_alpha(img)
        self.assertEqual(out.mode, "RGBA")
        a = np.asarray(out.getchannel("A"))
        self.assertTrue((a > 0).any())
        self.assertGreater(a[a.shape[0] // 2, a.shape[1] // 2], 200)
        # tight crop around the blob only: the 5x5 speck was dropped
        self.assertLess(out.width, 100)
        self.assertEqual(a[0, 0], 0)

    def test_watercolour_speck_kept_when_threshold_small(self):
        img = self._painted()
        ImageDraw.Draw(img).rectangle([10, 10, 14, 14], fill=(40, 120, 60))
        out = watercolour_to_alpha(img, speck=5)
        self.assertGreater(out.width, 120)  # control: speck now widens the crop

    def test_watercolour_rejects_non_white_background(self):
        with self.assertRaises(ValueError):
            watercolour_to_alpha(white((50, 50), (120, 120, 120)))

    def test_watercolour_rejects_blank_page(self):
        with self.assertRaises(ValueError):
            watercolour_to_alpha(white((50, 50)))

    def test_watercolour_tinted_paper_is_normalised(self):
        paper = (246, 242, 232)
        img = white((200, 200), paper)
        ImageDraw.Draw(img).ellipse([60, 60, 140, 140], fill=(40, 120, 60))
        out = watercolour_to_alpha(img)
        a = np.asarray(out.getchannel("A"))
        self.assertEqual(a[0, 0], 0)  # corner of the tight crop outside circle
        self.assertGreater(a[a.shape[0] // 2, a.shape[1] // 2], 200)


class SolidCutoutTests(unittest.TestCase):
    def _ring(self):
        img = white((200, 200))
        d = ImageDraw.Draw(img)
        d.ellipse([40, 40, 160, 160], fill=(60, 50, 40))
        d.ellipse([75, 75, 125, 125], fill=(255, 255, 255))
        return img

    def test_solid_cutout_keeps_highlight_opaque(self):
        out = solid_cutout(self._ring())
        self.assertEqual(out.mode, "RGBA")
        a = np.asarray(out.getchannel("A"))
        cy, cx = a.shape[0] // 2, a.shape[1] // 2
        self.assertEqual(a[cy, cx], 255)  # enclosed white stays opaque
        self.assertEqual(a[0, 0], 0)

    def test_solid_cutout_holes_clears_enclosed_area(self):
        out = solid_cutout(self._ring(), holes=500)
        a = np.asarray(out.getchannel("A"))
        self.assertEqual(a[a.shape[0] // 2, a.shape[1] // 2], 0)  # control for the test above

    def test_solid_cutout_edge_has_no_white_fringe(self):
        out = solid_cutout(self._ring())
        arr = np.asarray(out)
        semi = (arr[..., 3] > 0)
        # colour of every visible pixel on the outer band is the dark object colour, not white
        ys, xs = np.nonzero(semi[:, :])
        edge_pixels = arr[ys[0], xs[ys == ys[0]]]
        self.assertTrue((edge_pixels[:, :3].max(axis=1) < 120).all())

    def test_solid_cutout_rejects_dark_background(self):
        with self.assertRaises(ValueError):
            solid_cutout(white((50, 50), (90, 90, 90)))

    def test_solid_cutout_rejects_empty(self):
        with self.assertRaises(ValueError):
            solid_cutout(white((50, 50)))


class ContactSheetTests(unittest.TestCase):
    def test_contact_sheet_long_edge(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            items = []
            for i in range(20):
                p = td / f"a{i}.png"
                mode = "RGBA" if i % 2 else "RGB"
                Image.new(mode, (300 + i * 10, 200), (10 * i, 80, 120, 128)[:len(mode)]).save(p)
                items.append((f"asset {i}", p))
            out = contact_sheet(items, td / "sheet.jpg", long_edge=1568)
            self.assertEqual(out, td / "sheet.jpg")
            with Image.open(out) as im:
                self.assertLessEqual(max(im.size), 1568)
                self.assertGreater(max(im.size), 400)

    def test_contact_sheet_respects_small_long_edge(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            p = td / "x.png"
            Image.new("RGB", (100, 100)).save(p)
            out = contact_sheet([("x", p)] * 30, td / "s.jpg", long_edge=600)
            with Image.open(out) as im:
                self.assertLessEqual(max(im.size), 600)  # control: limit is a parameter

    def test_contact_sheet_missing_file_is_marked_not_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            good = td / "g.png"
            Image.new("RGB", (50, 50), (0, 200, 0)).save(good)
            out = contact_sheet([("good", good), ("gone", td / "nope.png")], td / "s.jpg")
            self.assertTrue(out.is_file())

    def test_contact_sheet_rejects_empty_and_huge_long_edge(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                contact_sheet([], Path(td) / "s.jpg")
            with self.assertRaises(ValueError):
                contact_sheet([("x", Path(td) / "x.png")], Path(td) / "s.jpg", long_edge=2000)


if __name__ == "__main__":
    unittest.main()
