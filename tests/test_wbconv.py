"""Tests for core/wbconv.py (shared by both converters).   Run: python -m unittest discover -s tests"""
import io, struct, sys, tempfile, unittest, zipfile, zlib
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
import wbconv as W  # noqa: E402


def strip(frames, fw, h=4, shade=None):
    """RGBA strip; frame i is filled with colour (10*i+10, 0, 0, 255) so crops can be checked."""
    rows = []
    for _ in range(h):
        r = bytearray()
        for i in range(frames):
            r += bytes((10 * i + 10, 0, 0, 255)) * fw
        rows.append(r)
    return W.Image(frames * fw, h, rows)


def put(folder: Path, name: str, frames: int, fw: int = 160):
    W.write_png(folder / name, strip(frames, fw))


def frames_of(path: Path, fw: int = 160):
    img = W.read_png(path)
    assert img.width % fw == 0, (path.name, img.width)
    return img.width // fw


def first_pixel_red(path: Path, frame: int, fw: int = 160):
    return W.read_png(path).rows[0][frame * fw * 4]


def encode_filtered(img, ftype):
    """Independent PNG encoder that applies one filter type to every row (to test the decoder)."""
    bpp, out, prev = 4, bytearray(), bytearray(img.width * 4)
    for row in img.rows:
        line = bytearray(row)
        enc = bytearray(len(line))
        for i, x in enumerate(line):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ftype == 0:
                pred = 0
            elif ftype == 1:
                pred = a
            elif ftype == 2:
                pred = b
            elif ftype == 3:
                pred = (a + b) >> 1
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            enc[i] = (x - pred) & 255
        out += bytes([ftype]) + bytes(enc)
        prev = line
    def chunk(t, body):
        return struct.pack(">I", len(body)) + t + body + struct.pack(">I", zlib.crc32(t + body) & 0xFFFFFFFF)
    return W.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", img.width, img.height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(out))) + chunk(b"IEND", b"")


class PngTests(unittest.TestCase):
    def test_roundtrip_and_all_filters(self):
        img = W.Image(5, 3, [bytearray((x * 7 + y * 13 + k) & 255 for x in range(5) for k in range(4)) for y in range(3)])
        with tempfile.TemporaryDirectory() as tmp:
            for ft in range(5):
                p = Path(tmp) / f"f{ft}.png"
                p.write_bytes(encode_filtered(img, ft))
                got = W.read_png(p)
                self.assertEqual([bytes(r) for r in got.rows], [bytes(r) for r in img.rows], f"filter {ft}")
            W.write_png(Path(tmp) / "w.png", img)
            self.assertEqual([bytes(r) for r in W.read_png(Path(tmp) / "w.png").rows], [bytes(r) for r in img.rows])

    def test_palette_png_with_transparency(self):
        def chunk(t, body):
            return struct.pack(">I", len(body)) + t + body + struct.pack(">I", zlib.crc32(t + body) & 0xFFFFFFFF)
        raw = b"\x00" + bytes([0, 1]) + b"\x00" + bytes([1, 0])
        data = W.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 3, 0, 0, 0)) + chunk(b"PLTE", bytes([255, 0, 0, 0, 255, 0])) \
            + chunk(b"tRNS", bytes([128])) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "pal.png"
            p.write_bytes(data)
            img = W.read_png(p)
        self.assertEqual(bytes(img.rows[0][:8]), bytes([255, 0, 0, 128, 0, 255, 0, 255]))

    def test_pad_and_crop_keep_frames_in_order(self):
        img = strip(4, 160)
        padded = W.pad_width(img, 5 * 160)
        self.assertEqual(padded.width, 800)
        self.assertEqual(padded.rows[0][3 * 160 * 4], 40)       # frame 3 kept
        self.assertEqual(padded.rows[0][4 * 160 * 4 + 3], 0)    # new frame is transparent
        cropped = W.crop_width(img, 3 * 160)
        self.assertEqual(cropped.width, 480)
        self.assertEqual(len(cropped.rows[0]), 480 * 4)

    def test_interlaced_and_garbage_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.png"
            p.write_bytes(b"not a png")
            with self.assertRaises(W.PngError):
                W.read_png(p)


class DescriptorTests(unittest.TestCase):
    SPOUSE = b"[sprite]\r\norigin_x=80\r\n[mating_press]\r\norigin_x=70\r\norigin_y=71\r\n[xray]\r\norigin_x=50\r\norigin_y=51\r\n"
    V15 = b"[info]\nname=\"A\"\n[sprite]\norigin_x=80\nxray_x=60\nxray_y=61\ndeepthroat_origin_y=150\n"

    def test_unchanged_returns_same_object(self):
        data = b"[a]\nx=1\n"
        self.assertIs(W.convert_descriptor_bytes(data, "futa", "futa"), data)

    def test_spouse_to_modroom_wife_and_v15(self):
        ini = W.Ini(W.convert_descriptor_bytes(self.SPOUSE, "spouse", "wife"))
        self.assertEqual(ini.get("sprite", "mating_press_origin_x"), "70")
        ini = W.Ini(W.convert_descriptor_bytes(self.SPOUSE, "spouse", "v15_spouse", "Name"))
        self.assertEqual(ini.get("sprite", "xray_x"), "50")
        self.assertEqual(ini.get("info", "name"), '"Name"')

    def test_v15_to_deeproom_spouse_gets_xray_section(self):
        ini = W.Ini(W.convert_descriptor_bytes(self.V15, "spouse", "spouse"))
        self.assertEqual(ini.get("xray", "origin_x"), "60")
        self.assertEqual(ini.get("deepthroat", "origin_y"), '"80.000000"')  # v1.5 150 - 70
        self.assertEqual(ini.get("sprite", "xray_x"), "60")          # the source key is kept

    def test_existing_keys_never_overwritten(self):
        data = self.SPOUSE + b"[sprite]\r\nmating_press_origin_x=5\r\n"
        self.assertEqual(W.Ini(W.convert_descriptor_bytes(data, "spouse", "wife")).get("sprite", "mating_press_origin_x"), "5")

    def test_v15_partner_to_deeproom_gets_pose_blocks_without_duplicate_sections(self):
        data = b'[info]\nname="A"\n[sprite]\norigin_x="80"\norigin_y="84"\nxray_x="60"\nxray_y="90"\n'
        out = W.convert_descriptor_bytes(data, "spouse", "spouse")
        ini = W.Ini(out)
        for sec, key in (("mating_press", "origin_x"), ("reverse_cowgirl", "origin_y"), ("xray", "origin_x"), ("condom", "condom_y_mpress"), ("gender", "is_male")):
            self.assertIsNotNone(ini.get(sec, key), f"[{sec}] {key}")
        self.assertIsNone(ini.get("deepthroat", "origin_y"))  # absent: the game uses the [sprite] origin (adding 150 drew it 66 px high)
        self.assertEqual(ini.get("sprite", "xray_offset_y"), '"6"')
        self.assertEqual(out.decode().lower().count("[sprite]"), 1)               # no second [sprite] header

    def test_futa_to_modded_adds_xray_offset(self):
        data = b"[sprite]\norigin_x=80\nxray_y=90\n"
        self.assertEqual(W.Ini(W.convert_descriptor_bytes(data, "futa", "futa_modded")).get("sprite", "xray_offset_y"), '"6"')

    def test_strip_that_already_has_the_target_frame_count_is_just_renamed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "P"
            d.mkdir()
            put(d, "custom_wife_xray_0.png", 4)                                    # modern name, 4 frames (like Azure Dogwife)
            put(d, "custom_wife_mating_press_0.png", 5)
            (d / "custom_data.wife").write_bytes(b"[sprite]\norigin_x=80\n")
            r = W.to_v15(d, "wife", "P", approximate=True)
            self.assertEqual(frames_of(d / "custom_xray.png"), 4)
            self.assertTrue(any("already 4 frames" in c for c in r.converted))

    def test_approximate_uses_the_learned_frame_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "P"
            d.mkdir()
            put(d, "custom_futa_mating_press_0.png", 24)
            (d / "custom_data.futa").write_bytes(b"[sprite]\norigin_x=80\n")
            r = W.to_v15(d, "futa", "P", approximate=True)
            out = d / "custom_mating_press.png"
            self.assertEqual(frames_of(out), 9)
            self.assertEqual(first_pixel_red(out, 7), 10 * 7 + 10)      # frame 7 kept
            self.assertEqual(first_pixel_red(out, 8), 10 * 19 + 10)     # last frame is modern frame 19, not frame 8
            self.assertTrue(any("frames 0,1,2,3,4,5,6,7,19 kept" in c for c in r.converted))

    def test_select_frames_order(self):
        img = strip(5, 160)
        out = W.select_frames(img, 160, [4, 0])
        self.assertEqual(out.width, 320)
        self.assertEqual((out.rows[0][0], out.rows[0][160 * 4]), (50, 10))


class PackTests(unittest.TestCase):
    def make(self, tmp, files, descriptor=("custom_data.spouse", b"[sprite]\norigin_x=80\n")):
        d = Path(tmp) / "Pack"
        d.mkdir()
        W.Ini  # keep import used
        for name, frames, *fw in files:
            put(d, name, frames, fw[0] if fw else 160)
        if descriptor:
            (d / descriptor[0]).write_bytes(descriptor[1])
        return d

    def v15_wife(self, tmp, forward=True):
        files = [("custom_portrait.png", 10, 128), ("custom_mating_press.png", 4), ("custom_reverse_cowgirl.png", 5), ("custom_xray.png", 4), ("custom_deepthroat.png", 5)]
        if forward:
            files.append(("custom_forward_cowgirl.png", 6))
        return self.make(tmp, files)

    def test_v15_wife_to_modroom_pads_and_leaves_lossy_strips(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.v15_wife(tmp)
            r = W.from_v15(d, "wife", "modroom", "Pack")
            self.assertEqual(frames_of(d / "custom_wife_mating_press_0.png"), 5)
            self.assertEqual(frames_of(d / "custom_wife_reverse_cowgirl_0.png"), 10)
            self.assertEqual(frames_of(d / "custom_wife_cowgirl_0.png"), 11)
            self.assertEqual(frames_of(d / "custom_wife_xray_0.png"), 4)              # .spouse pack: X-ray renamed, frames untouched
            self.assertEqual(first_pixel_red(d / "custom_wife_mating_press_0.png", 3), 40)
            self.assertTrue((d / "custom_portrait.png").exists())                     # ModRoom reads a 10-frame portrait natively: kept as authored
            self.assertTrue((d / "custom_data.wife").exists())
            self.assertFalse((d / "custom_data.spouse").exists())
            self.assertIn(r.status, ("partial", "padded"))
            self.assertEqual(W.modroom_missing(d, "wife"), [])

    def test_v15_wife_xray_crop_needs_approximate(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.v15_wife(tmp)
            W.from_v15(d, "wife", "modroom", "Pack", approximate=True)
            self.assertEqual(frames_of(d / "custom_wife_xray_0.png"), 4)             # a .spouse pack: X-ray kept as authored, renamed only
            (Path(tmp) / "b").mkdir()
            d = self.v15_wife(str(Path(tmp) / "b"))
            (d / "custom_data.wife").write_bytes(b"[info]\n")
            W.from_v15(d, "wife", "modroom", "Pack", approximate=True)
            self.assertEqual(frames_of(d / "custom_wife_xray_0.png"), 3)
            self.assertEqual(first_pixel_red(d / "custom_wife_xray_0.png", 2), 30)   # first frames kept in order

    def test_modroom_skips_a_partner_without_forward_cowgirl(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.v15_wife(tmp, forward=False)
            r = W.from_v15(d, "wife", "modroom", "Pack")
            self.assertTrue((d / "custom_wife_cowgirl_0.png").exists())               # the missing forward cowgirl is aliased from the reverse one
            self.assertEqual(W.modroom_missing(d, "wife"), [])
            self.assertNotEqual(r.status, "skipped")

    def test_portrait_converted_only_with_approximate(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.v15_wife(tmp)
            W.from_v15(d, "wife", "modroom", "Pack", approximate=True)
            self.assertEqual(frames_of(d / "custom_wife_portrait_0.png", 128), 17)

    def test_deeproom_export_is_one_spouse_descriptor(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.v15_wife(tmp)
            (d / "custom_data.wife").write_bytes(b"[sprite]\norigin_x=1\n")
            r = W.from_v15(d, "wife", "deeproom", "Pack")
            self.assertEqual(r.status, "ok")
            self.assertTrue((d / "custom_data.spouse").exists())
            self.assertFalse((d / "custom_data.wife").exists())
            self.assertTrue((d / "custom_mating_press.png").exists())
            self.assertFalse((d / "custom_wife_mating_press_0.png").exists())

    def test_futa_to_modroom_keeps_standard_names_and_checks_needs(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp, [("custom_portrait.png", 10, 128), ("custom_mating_press.png", 9), ("custom_reverse_cowgirl.png", 5), ("custom_xray.png", 3)],
                          descriptor=("custom_data.futa", b"[sprite]\norigin_x=80\n"))
            r = W.from_v15(d, "futa", "modroom", "Pack")
            self.assertEqual(r.status, "ok")
            self.assertTrue((d / "custom_mating_press.png").exists())
            self.assertFalse((d / "custom_futa_mating_press_0.png").exists())
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp, [("custom_portrait.png", 10, 128), ("custom_mating_press.png", 9)], descriptor=("custom_data.futa", b"[sprite]\n"))
            self.assertEqual(W.from_v15(d, "futa", "modroom", "Pack").status, "skipped")

    def test_modern_wife_to_v15_converts_only_what_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp, [("custom_wife_mating_press_0.png", 5), ("custom_wife_xray_0.png", 3), ("custom_wife_reverse_cowgirl_0.png", 10)],
                          descriptor=("custom_data.wife", b"[sprite]\norigin_x=80\n"))
            r = W.to_v15(d, "wife", "Pack")
            self.assertEqual(r.status, "partial")
            self.assertEqual(frames_of(d / "custom_xray.png"), 4)                    # 3 -> 4 is a pad: allowed
            self.assertFalse((d / "custom_mating_press.png").exists())               # 5 -> 4 drops a frame: needs --approximate
            self.assertFalse((d / "custom_wife_mating_press_0.png").exists())        # unusable leftovers removed
            self.assertTrue((d / "custom_data.spouse").exists())
            self.assertFalse((d / "custom_data.wife").exists())
            self.assertEqual(W.Ini((d / "custom_data.spouse").read_bytes()).get("info", "name"), '"Pack"')

    def test_modern_pack_with_nothing_convertible_is_skipped_then_approximated(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp, [("custom_futa_mating_press_0.png", 24), ("custom_futa_xray_0.png", 18)], descriptor=("custom_data.futa", b"[sprite]\n"))
            self.assertEqual(W.to_v15(d, "futa", "Pack").status, "skipped")
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp, [("custom_futa_mating_press_0.png", 24), ("custom_futa_xray_0.png", 18)], descriptor=("custom_data.futa", b"[sprite]\n"))
            r = W.to_v15(d, "futa", "Pack", approximate=True)
            self.assertEqual(r.status, "approximate")
            self.assertEqual(frames_of(d / "custom_mating_press.png"), 9)
            self.assertEqual(frames_of(d / "custom_xray.png"), 3)

    def test_standard_pack_to_v15_is_untouched_apart_from_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp, [("custom_mating_press.png", 4), ("custom_xray.png", 4)])
            r = W.to_v15(d, "wife", "Pack")
            self.assertEqual(r.status, "ok")
            self.assertEqual(frames_of(d / "custom_mating_press.png"), 4)
            self.assertEqual(W.Ini((d / "custom_data.spouse").read_bytes()).get("info", "name"), '"Pack"')

    def test_odd_width_strip_is_reported_not_converted(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp, [("custom_mating_press.png", 4)])
            W.write_png(d / "custom_mating_press.png", strip(1, 650))                 # 650 px does not divide into 4 frames
            r = W.from_v15(d, "wife", "modroom", "Pack")
            self.assertTrue(any("does not divide into 4 frames" in s for s in r.skipped))


class HelperTests(unittest.TestCase):
    def test_safe_extract_blocks_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../evil.txt", "x")
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            with self.assertRaises(ValueError):
                W.safe_extract(z, tmp)
            self.assertFalse((Path(tmp).parent / "evil.txt").exists())

    def test_safe_extract_normal_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("a/b.txt", "x")
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            self.assertEqual(W.safe_extract(z, tmp), 1)
            self.assertTrue((Path(tmp) / "a" / "b.txt").exists())

    def test_publish_never_overwrites_and_clean_waits_for_packs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dest = tmp / "dest" / "custom_futas"
            (dest / "old").mkdir(parents=True)
            (dest / "old" / "keep.txt").write_text("x")
            staging = tmp / "stage" / "custom_futas"
            staging.mkdir(parents=True)
            self.assertEqual(W.publish_category(staging, dest, clean=True), [])       # nothing converted: destination untouched
            self.assertTrue((dest / "old" / "keep.txt").exists())
            (staging / "old").mkdir()
            (staging / "old" / "new.txt").write_text("y")
            self.assertEqual(W.publish_category(staging, dest, clean=False), ["old_2"])   # no overwrite
            self.assertTrue((dest / "old" / "keep.txt").exists() and (dest / "old_2" / "new.txt").exists())
            (staging / "z").mkdir()
            self.assertEqual(W.publish_category(staging, dest, clean=True), ["z"])         # clean only now
            self.assertFalse((dest / "old").exists())

    def test_report_counts_and_markdown(self):
        rep = W.Report("T")
        rep.add("a", "custom_wives", "modroom", W.Result("padded", ["x"]))
        rep.add("b", "custom_futas", "modroom", W.Result("skipped", notes=["why"]))
        self.assertEqual(rep.counts(), {"padded": 1, "skipped": 1})
        md = rep.to_markdown()
        self.assertIn("| `a` |", md)
        self.assertIn("why", md)


if __name__ == "__main__":
    unittest.main()


class SafeNameTests(unittest.TestCase):
    def test_zalgo_control_and_reserved_names(self):
        zalgo = "M\u0337\u0322\u0322\u0314 W\u0336O\u0336\u0305 my world. "
        self.assertEqual(W.safe_dirname(zalgo), "m_wo_my_world")
        self.assertEqual(W.safe_dirname("\x00bad\u200b"), "bad")
        self.assertEqual(W.safe_dirname("aux"), "_aux")
        self.assertEqual(W.safe_dirname("My World."), "my_world")
        self.assertEqual(W.safe_dirname("Caf\u00e9 Rose (2)"), "caf\u00e9_rose_(2)")
        self.assertEqual(W.safe_dirname("???"), "unnamed_mod")
        self.assertLessEqual(len(W.safe_dirname("x" * 300)), 80)

    def test_make_pack_dir_falls_back_when_the_name_is_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            made = W.make_pack_dir(tmp, "bad\x00name", "My Pack")
            self.assertEqual(made.name, "my_pack")
            self.assertTrue(made.is_dir())


class BadPngTests(unittest.TestCase):
    def test_short_ihdr_raises_pngerror_not_struct_error(self):
        import struct, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "bad.png"
            f.write_bytes(W.PNG_SIG + struct.pack(">I4s", 5, b"IHDR") + b"12345" + b"\x00\x00\x00\x00")
            with self.assertRaises(W.PngError):
                W.read_png(f)


class PackNamingTests(unittest.TestCase):
    def test_repeat_names_keep_their_tag(self):
        used = {"astolfo", "astolfo_futa"}
        self.assertEqual(W.unique_pack_name("astolfo", "Astolfo (naked)", used), "astolfo_(naked)")
        self.assertEqual(W.unique_pack_name("alice", "Alice", {"alice"}), "alice_2")
        self.assertEqual(W.unique_pack_name("fresh", "x", used), "fresh")

    def test_converting_twice_into_the_same_folder_makes_no_copies(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for run in (1, 2):
                stage = Path(tmp) / f"stage{run}" / "pack"
                stage.mkdir(parents=True)
                (stage / "custom_data.futa").write_bytes(b"[info]")
                (stage / "_manifest.txt").write_bytes(b"x" if run == 1 else b"")   # generated index files do not count
                names = W.publish_category(stage.parent, Path(tmp) / "dest", False)
                self.assertEqual(names, ["pack"])
            self.assertEqual(sorted(p.name for p in (Path(tmp) / "dest").iterdir()), ["pack"])
