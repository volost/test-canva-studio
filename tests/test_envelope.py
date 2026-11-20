"""Envelope from skeleton geometry: synthetic textures and seals, everything in memory."""
import unittest

import numpy as np
from PIL import Image, ImageDraw

from app.imaging.core import aspect_error
from app.imaging.envelope import check_envelope, compose_envelope

# Sage & Linen geometry (section coordinates), exactly as in the skeleton map's envelope block.
SL = {"section_px": [1366, 964], "tip": [683, 610], "left_top": [0, 60], "right_top": [1366, 60],
      "seal_centre": [683, 623], "seal_size": [160, 198], "seal_rot_canva": -3.4}

# a second, deliberately different geometry (not symmetric, other section size and aspect)
ODD = {"section_px": [1000, 800], "tip": [430, 470], "left_top": [0, 30], "right_top": [1000, 110],
       "seal_centre": [430, 480], "seal_size": [100, 120], "seal_rot_canva": 5.0}


def texture(size=(300, 300), colour=(176, 170, 156)):
    return Image.new("RGB", size, colour)


def make_seal(size=(640, 792)):
    """A dark red ellipse with a light bar: clearly different from the linen, same aspect as 160x198."""
    seal = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(seal)
    d.ellipse((4, 4, size[0] - 5, size[1] - 5), fill=(120, 30, 40, 255))
    d.rectangle((size[0] * 0.3, size[1] * 0.45, size[0] * 0.7, size[1] * 0.55), fill=(230, 200, 190, 255))
    return seal


def shifted(layer, dx, dy):
    """The layer moved by (dx, dy) px; what moves out is lost, what moves in is transparent."""
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.paste(layer, (dx, dy))
    return out


class EnvelopeBase(unittest.TestCase):
    """The Sage & Linen envelope composed once at the default scale 2, shared by the tests."""

    @classmethod
    def setUpClass(cls):
        cls.seal = make_seal()
        cls.cover, cls.flap, cls.body = compose_envelope(texture(), SL, seal=cls.seal)


class LayersTests(EnvelopeBase):
    def test_envelope_layers_reproduce_cover(self):
        self.assertEqual(self.cover.size, (2732, 1928))
        self.assertEqual(self.flap.size, (2732, 1928))
        self.assertEqual(self.body.size, (2732, 1928))
        self.assertEqual((self.cover.mode, self.flap.mode, self.body.mode), ("RGB", "RGBA", "RGBA"))
        self.assertEqual(check_envelope(self.cover, self.flap, self.body, SL, seal=self.seal), [])
        # the same without the seal argument to the checker (seal still expected from the geometry)
        self.assertEqual(check_envelope(self.cover, self.flap, self.body, SL), [])

    def test_envelope_no_transparent_pixel(self):
        stacked = Image.alpha_composite(self.body, self.flap)
        self.assertEqual(int(np.asarray(stacked.getchannel("A")).min()), 255)
        # control: neither layer alone covers the section, so the property is not trivial
        self.assertEqual(int(np.asarray(self.flap.getchannel("A")).min()), 0)
        self.assertEqual(int(np.asarray(self.body.getchannel("A")).min()), 0)

    def test_seal_is_in_the_flap_layer_only(self):
        a = np.asarray(self.flap.convert("RGB")).astype(int)
        c = np.asarray(self.cover).astype(int)
        cx, cy = 683 * 2, 623 * 2
        # at the seal centre the flap layer shows the seal's bar/body, the cover shows linen
        self.assertGreater(np.abs(a[cy - 40:cy + 40, cx - 40:cx + 40] - c[cy - 40:cy + 40, cx - 40:cx + 40]).mean(), 20)

    def test_cover_is_flap_over_body_without_seal(self):
        cover1, flap1, body1 = compose_envelope(texture(), SL, scale=1, seal=None)
        flat = Image.alpha_composite(Image.alpha_composite(Image.new("RGBA", cover1.size, (0, 0, 0, 255)), body1), flap1)
        d = np.abs(np.asarray(flat.convert("RGB")).astype(int) - np.asarray(cover1).astype(int))
        self.assertLessEqual(int(d.max()), 1)  # only the RGBA -> RGB rounding


class ControlTests(EnvelopeBase):
    """Known-bad inputs the checker must reject (if one passes, the checker is broken)."""

    def check(self, cover=None, flap=None, body=None, **kw):
        return check_envelope(cover or self.cover, flap or self.flap, body or self.body, SL, **kw)

    def test_check_rejects_shifted_flap(self):
        for dx, dy in ((0, 12), (0, -12), (12, 0), (-12, 0)):  # 6 canva px at scale 2, every direction
            with self.subTest(dx=dx, dy=dy):
                problems = self.check(flap=shifted(self.flap, dx, dy))
                self.assertTrue(problems, f"flap shifted by {(dx, dy)} was accepted")

    def test_check_rejects_shifted_flap_without_seal(self):
        """No seal to betray the shift: only the union alpha and the edge measurement can catch it."""
        cover, flap, body = compose_envelope(texture(), SL, scale=1, seal=None)
        self.assertEqual(check_envelope(cover, flap, body, SL, scale=1, seal_expected=False), [])  # positive control
        for dx, dy in ((0, 6), (0, -6), (6, 0), (-6, 0)):
            with self.subTest(dx=dx, dy=dy):
                problems = check_envelope(cover, shifted(flap, dx, dy), body, SL, scale=1, seal_expected=False)
                self.assertTrue(problems, f"flap shifted by {(dx, dy)} was accepted")

    def test_flap_position_is_measured_independently_of_the_union_alpha(self):
        """A flap moved by 6 px AND a body repaired to hide the union hole is still caught by (h)."""
        bad_flap = shifted(self.flap, 0, 12)
        # repair: make the body opaque everywhere, so the union has no transparent pixel
        body = self.body.copy()
        body.putalpha(255)
        problems = self.check(flap=bad_flap, body=body)
        self.assertTrue(any("(h)" in p for p in problems), problems)

    def test_check_rejects_hole_in_body(self):
        arr = np.asarray(self.body).copy()
        arr[1700:1712, 300:312, 3] = 0
        problems = self.check(body=Image.fromarray(arr, "RGBA"))
        self.assertTrue(any("(e)" in p for p in problems), problems)

    def test_check_rejects_brightened_cover(self):
        c = np.asarray(self.cover).astype(np.int16)
        bad = Image.fromarray(np.clip(c + 6, 0, 255).astype(np.uint8), "RGB")
        problems = self.check(cover=bad)
        self.assertTrue(any("(d)" in p for p in problems), problems)

    def test_check_rejects_missing_seal_and_misplaced_seal(self):
        cover, flap_noseal, body = compose_envelope(texture(), SL, seal=None)
        problems = check_envelope(cover, flap_noseal, body, SL)  # seal expected by default
        self.assertTrue(any("(d-control)" in p for p in problems), problems)
        # seal 30 canva px too low: build it by composing the seal at a displaced centre
        low = dict(SL, seal_centre=[683, 653])
        _, flap_low, _ = compose_envelope(texture(), low, seal=self.seal)
        problems = check_envelope(self.cover, flap_low, self.body, SL, seal=self.seal)
        self.assertTrue(any("(f)" in p for p in problems), problems)
        self.assertTrue(any("(g)" in p for p in problems), problems)

    def test_check_rejects_wrong_sizes_and_modes(self):
        self.assertTrue(self.check(cover=self.cover.resize((1366, 964))))
        self.assertTrue(self.check(flap=self.flap.convert("RGB")))
        self.assertTrue(self.check(body=self.body.crop((0, 0, 2000, 1928))))

    def test_no_seal_mode_does_not_expect_a_seal(self):
        cover, flap, body = compose_envelope(texture(), SL, seal=None)
        self.assertEqual(check_envelope(cover, flap, body, SL, seal_expected=False), [])
        # control: the same flap with a seal baked in is rejected when no seal is expected
        problems = check_envelope(self.cover, self.flap, self.body, SL, seal_expected=False)
        self.assertTrue(problems)
        with self.assertRaises(ValueError):
            check_envelope(cover, flap, body, SL, seal=self.seal, seal_expected=False)


class GeometryComesFromGeomTests(unittest.TestCase):
    def test_other_geometry_composes_and_checks_clean(self):
        seal = make_seal((500, 600))
        cover, flap, body = compose_envelope(texture(), ODD, scale=1, seal=seal)
        self.assertEqual(cover.size, (1000, 800))
        self.assertEqual(check_envelope(cover, flap, body, ODD, scale=1, seal=seal), [])

    def test_layers_of_one_geometry_fail_the_check_of_another(self):
        seal = make_seal((500, 600))
        cover, flap, body = compose_envelope(texture(), ODD, scale=1, seal=seal)
        moved = dict(ODD, tip=[430, 520])
        self.assertTrue(check_envelope(cover, flap, body, moved, scale=1, seal=seal))
        moved = dict(ODD, right_top=[1000, 60])
        self.assertTrue(check_envelope(cover, flap, body, moved, scale=1, seal=seal))

    def test_tip_position_moves_the_flap(self):
        def lowest_opaque_row(tip_y):
            _, flap, _ = compose_envelope(texture(), dict(ODD, tip=[430, tip_y]), scale=1, seal=None)
            a = np.asarray(flap.getchannel("A"))[:, 430]
            return int(np.nonzero(a >= 192)[0].max())
        # the flap tip follows geom["tip"] (the rounded tip sits a few px above it)
        low, high = lowest_opaque_row(520), lowest_opaque_row(470)
        self.assertEqual(low - high, 50)
        self.assertLess(abs(high - 470), 12)

    def test_scale_changes_pixel_size_not_layout(self):
        cover, flap, body = compose_envelope(texture(), SL, scale=1, seal=make_seal())
        self.assertEqual(cover.size, (1366, 964))
        self.assertEqual(check_envelope(cover, flap, body, SL, scale=1), [])

    def test_bad_geometry_is_refused(self):
        with self.assertRaises(ValueError):
            compose_envelope(texture(), {k: v for k, v in SL.items() if k != "tip"}, scale=1)
        with self.assertRaises(ValueError):
            compose_envelope(texture(), dict(SL, tip=[683, 20]), scale=1)  # tip above the top corners
        with self.assertRaises(ValueError):
            compose_envelope(texture(), dict(SL, tip=[683, 2000]), scale=1)  # tip outside the section
        with self.assertRaises(ValueError):
            compose_envelope(texture(), SL, scale=0)
        with self.assertRaises(ValueError):  # seal with the wrong aspect for seal_size
            compose_envelope(texture(), SL, scale=1, seal=Image.new("RGBA", (200, 200)))
        with self.assertRaises(ValueError):  # a seal that is not RGBA-convertible must not pass silently
            compose_envelope(texture(), SL, scale=1, seal="seal.png")
        self.assertGreater(aspect_error((200, 200), (160, 198)), 0.005)  # the control for the case above


if __name__ == "__main__":
    unittest.main()
