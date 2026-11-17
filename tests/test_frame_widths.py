"""wbconv strip conversion at any frame width (2026-11-17).

The games cut a strip into a fixed NUMBER of frames whatever its width; real packs use 256 px portraits
(cinderace_nude, baiken_clothed: 2560 px = 10 frames) and 220 px mating-press frames (1980 px = 9).
Those used to be skipped as "width is not N frames of 160/128 px"."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
import wbconv as W  # noqa: E402


def png(path, width, height=8):
    W.write_png(path, W.Image(width, height, [bytearray(b"\xff\x00\x00\xff" * width) for _ in range(height)]))


class FrameWidthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_strip_frames_cowgirl_rule(self):
        self.assertEqual(W.strip_frames("futa", "standard", "cowgirl", 800), 5)
        self.assertEqual(W.strip_frames("futa", "standard", "cowgirl", 1120), 7)
        self.assertEqual(W.strip_frames("futa", "standard", "portrait", 2560), 10)
        self.assertEqual(W.frame_width_of(2560, 10), 256)
        self.assertIsNone(W.frame_width_of(1412, 10))

    def test_high_res_strips_are_padded_not_skipped(self):
        # standard -> modern lover: mating press 9 -> 24 frames with 220 px frames
        png(self.d / "custom_mating_press.png", 1980)
        res = W.Result()
        W._convert_strips(self.d, "futa", "standard", "modern", False, res)
        out = self.d / "custom_futa_mating_press_0.png"
        self.assertTrue(out.is_file(), res.skipped)
        self.assertEqual(W.png_size(out)[0], 24 * 220)
        self.assertFalse(any("mating_press" in s for s in res.skipped))

    def test_seven_frame_cowgirl_padded_from_seven(self):
        png(self.d / "custom_reverse_cowgirl.png", 1120)  # 7 x 160
        res = W.Result()
        W._convert_strips(self.d, "futa", "standard", "modern", False, res)
        self.assertEqual(W.png_size(self.d / "custom_futa_cowgirls_0.png")[0], 19 * 160)
        self.assertIn("cowgirl 7 to 19 frames (padded)", res.converted)

    def test_uneven_strip_is_reported_not_guessed(self):
        png(self.d / "custom_xray.png", 1412)
        res = W.Result()
        W._convert_strips(self.d, "futa", "standard", "modern", False, res)
        self.assertTrue(any("does not divide into 3 frames" in s for s in res.skipped), res.skipped)

    def test_pack_notes(self):
        png(self.d / "custom_portrait.png", 1412)
        png(self.d / "custom_xray.png", 640)
        (self.d / "custom_data.spouse").write_text("[mating_press]\norigin_x=110\n[xray]\norigin_x=110\n")
        notes = W.pack_notes(self.d, "wife", "standard")
        self.assertTrue(any("custom_portrait.png is 1412 px" in n for n in notes), notes)
        self.assertTrue(any("[xray] origin_x=110 is the same as the mating-press origin" in n for n in notes), notes)
        (self.d / "custom_data.spouse").write_text("[mating_press]\norigin_x=110\n[xray]\norigin_x=80\n")
        self.assertFalse(any("[xray]" in n for n in W.pack_notes(self.d, "wife", "standard")))


class XrayOriginDefaultTests(unittest.TestCase):
    def test_xray_origin_not_copied_from_sprite_origin(self):
        # a v1.5 partner on a wide canvas: [sprite] origin_x=110, no xray_x -> Deeproom [xray] keeps 80/84
        src = b'[info]\nname="W"\n[sprite]\norigin_x=110\norigin_y=90\n'
        out = W.convert_descriptor_bytes(src, "spouse", "spouse", "W").decode()
        ini = W.Ini(out.encode())
        self.assertEqual(ini.get("xray", "origin_x").strip('"'), "80.000000")
        self.assertEqual(ini.get("xray", "origin_y").strip('"'), "84.000000")
        self.assertEqual(ini.get("mating_press", "origin_x"), "110")  # the body keeps its own origin

    def test_explicit_xray_keys_still_used(self):
        src = b'[sprite]\norigin_x=110\nxray_x=95\nxray_y=88\n'
        ini = W.Ini(W.convert_descriptor_bytes(src, "spouse", "spouse", "W"))
        self.assertEqual((ini.get("xray", "origin_x"), ini.get("xray", "origin_y")), ("95", "88"))


if __name__ == "__main__":
    unittest.main()
