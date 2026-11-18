"""Edge cases found in the pre-release review (PNG colour keys, latin-1 descriptors, cowgirl stand-in strips)."""
import struct, sys, tempfile, unittest, zlib
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import wbconv as W  # noqa: E402


def raw_png(w, h, ctype, pixels, trns=None):
    """8-bit PNG of colour type 0 or 2; pixels = bytes per row, filter 0."""
    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    body = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
    if trns is not None:
        body += chunk(b"tRNS", trns)
    raw = b"".join(b"\x00" + row for row in pixels)
    return W.PNG_SIG + body + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class PngColourKey(unittest.TestCase):
    def _read(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.png"
            p.write_bytes(data)
            return W.read_png(p)

    def test_rgb_colour_key_becomes_transparent(self):
        img = self._read(raw_png(2, 1, 2, [bytes([255, 0, 255, 10, 20, 30])], trns=bytes([0, 255, 0, 0, 0, 255])))
        self.assertEqual(bytes(img.rows[0]), bytes([255, 0, 255, 0, 10, 20, 30, 255]))

    def test_gray_colour_key_becomes_transparent(self):
        img = self._read(raw_png(2, 1, 0, [bytes([7, 8])], trns=bytes([0, 7])))
        self.assertEqual(bytes(img.rows[0]), bytes([7, 7, 7, 0, 8, 8, 8, 255]))

    def test_no_trns_stays_opaque(self):
        img = self._read(raw_png(1, 1, 2, [bytes([1, 2, 3])]))
        self.assertEqual(bytes(img.rows[0]), bytes([1, 2, 3, 255]))


class Latin1Descriptor(unittest.TestCase):
    def test_non_latin_name_does_not_crash_and_keeps_existing_bytes(self):
        data = '[sprite]\norigin_x=80\n; caf\xe9\n'.encode("latin-1")
        out = W.convert_descriptor_bytes(data, "wife", "v15_spouse", "アンカ")
        self.assertTrue(out.startswith(data.rstrip(b"\n")))
        self.assertIn(b'name="???"', out)


class CowgirlStandIn(unittest.TestCase):
    def _strip(self, d, name, frames, fw):
        W.write_png(d / name, W.Image(frames * fw, 2, [bytearray(frames * fw * 4) for _ in range(2)]))
        return d / name

    def test_hi_res_reverse_to_forward_pads_at_own_frame_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = self._strip(d, "rc.png", 10, 320)
            W._alias_strip(src, d / "fc.png", 10, 11)
            self.assertEqual(W.png_size(d / "fc.png")[0], 11 * 320)
            self.assertEqual(W.png_size(src)[0], 10 * 320)  # author's strip untouched

    def test_forward_to_reverse_is_trimmed_to_ten_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = self._strip(d, "fc.png", 11, 160)
            W._alias_strip(src, d / "rc.png", 11, 10)
            self.assertEqual(W.png_size(d / "rc.png")[0], 10 * 160)

    def test_strip_that_does_not_divide_is_copied_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            src = self._strip(d, "rc.png", 1, 1001)
            W._alias_strip(src, d / "fc.png", 10, 11)
            self.assertEqual((d / "fc.png").read_bytes(), src.read_bytes())


if __name__ == "__main__":
    unittest.main()
