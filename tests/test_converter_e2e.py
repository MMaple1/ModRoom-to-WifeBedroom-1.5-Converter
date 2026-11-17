"""End-to-end tests for Modded_to_WB_1.5.py on synthetic packs.   Run: python -m unittest discover -s tests"""
import importlib.util, io, sys, tempfile, unittest, zipfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
import wbconv as W  # noqa: E402

spec = importlib.util.spec_from_file_location("modded_to_15", ROOT / "Modded_to_WB_1.5.py")
CONV = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CONV)


def strip(frames, fw, h=4):
    row = b"".join(bytes((10 * i + 10, 0, 0, 255)) * fw for i in range(frames))
    return W.Image(frames * fw, h, [bytearray(row) for _ in range(h)])


def png(folder, name, frames, fw=160):
    W.write_png(folder / name, strip(frames, fw))


def std_wife(root, name):
    d = Path(root) / "custom_wives" / name
    d.mkdir(parents=True)
    for n, f, fw in (("custom_portrait.png", 10, 128), ("custom_mating_press.png", 4, 160), ("custom_xray.png", 4, 160)):
        png(d, n, f, fw)
    (d / "custom_data.spouse").write_bytes(b"[sprite]\norigin_x=80\norigin_y=84\n[mating_press]\norigin_x=70\n")
    return d


def modern_wife(root, name):
    d = Path(root) / "custom_wives" / name
    d.mkdir(parents=True)
    png(d, "custom_wife_mating_press_0.png", 5)
    png(d, "custom_wife_xray_0.png", 3)
    (d / "custom_data.wife").write_bytes(b"[sprite]\norigin_x=80\norigin_y=84\n")
    return d


class ModdedTo15(unittest.TestCase):
    def run_conv(self, src, dest, **kw):
        kw.setdefault("verbose", False)
        kw.setdefault("quarantine_duplicates", False)
        return CONV.convert_modroom_to_15([Path(src)], Path(dest), **kw)

    def test_standard_partner_is_converted_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            std_wife(src, "Lisa")
            st = self.run_conv(src, dest)
            out = dest / "custom" / "lisa"
            self.assertEqual(st["partners_converted"], 1)
            self.assertEqual(W.png_size(out / "custom_mating_press.png")[0], 4 * 160)
            ini = W.Ini((out / "custom_data.spouse").read_bytes())
            self.assertEqual(ini.get("info", "name"), '"Lisa"')
            self.assertEqual(ini.get("mating_press", "origin_x"), "70")       # existing keys untouched
            self.assertTrue((dest / "custom" / "_manifest.txt").exists())
            self.assertEqual(st["report"].counts(), {"ok": 1})

    def test_modern_partner_converts_only_what_is_safe_and_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            modern_wife(src, "Mod")
            st = self.run_conv(src, dest)
            out = dest / "custom" / "mod"
            self.assertEqual(W.png_size(out / "custom_xray.png")[0], 4 * 160)    # 3 -> 4 frames is a pad
            self.assertFalse((out / "custom_mating_press.png").exists())         # 5 -> 4 drops a frame: needs --approximate
            self.assertFalse(any(p.name.endswith("_0.png") for p in out.iterdir()))
            self.assertFalse((out / "custom_data.wife").exists())
            self.assertEqual(st["report"].counts(), {"partial": 1})

    def test_approximate_converts_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            modern_wife(src, "Mod")
            self.run_conv(src, dest, approximate=True)
            self.assertEqual(W.png_size(dest / "custom" / "mod" / "custom_mating_press.png")[0], 4 * 160)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            std_wife(src, "Lisa")
            self.run_conv(src, dest, dry_run=True)
            self.assertFalse(dest.exists())

    def test_clean_never_empties_the_destination_when_nothing_converts(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            (src / "custom_wives").mkdir(parents=True)                           # no packs at all
            keep = dest / "custom" / "existing"
            keep.mkdir(parents=True)
            (keep / "custom_data.spouse").write_text("x")
            self.run_conv(src, dest, clean_dest=True)
            self.assertTrue((keep / "custom_data.spouse").exists())

    def test_merge_never_overwrites_an_existing_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            std_wife(src, "Lisa")
            self.run_conv(src, dest)
            (dest / "custom" / "lisa" / "mine.txt").write_text("keep me")
            self.run_conv(src, dest)
            self.assertTrue((dest / "custom" / "lisa" / "mine.txt").exists())
            self.assertTrue((dest / "custom" / "lisa_2").is_dir())

    def test_unsafe_zip_is_skipped_not_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            z = tmp / "bad.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("../evil.txt", "x")
            CONV.convert_modroom_to_15([z], tmp / "dest", verbose=False, quarantine_duplicates=False)
            self.assertFalse((tmp / "evil.txt").exists())

    def test_duplicates_are_reported_not_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "src", Path(tmp) / "dest"
            std_wife(src, "Lisa")
            std_wife(src, "Lisa - Copy")
            st = CONV.convert_modroom_to_15([src], dest, verbose=False, quarantine_duplicates=True)
            self.assertFalse((dest / "!duplicates").exists())
            self.assertEqual(len([p for p in (dest / "custom").iterdir() if p.is_dir()]), 1)
            self.assertTrue(any("duplicate" in " ".join(r.notes) for *_, r in st["report"].rows))


class ConsoleEncoding(unittest.TestCase):
    def test_printing_an_unencodable_pack_name_does_not_crash(self):
        import os, subprocess
        code = ("import importlib.util, sys; "
                "sys.path.insert(0, r'%s'); "
                "spec = importlib.util.spec_from_file_location('conv', r'%s'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                "print('pack \\u221e name')" % (str(ROOT / "core"), str(ROOT / 'Modded_to_WB_1.5.py')))
        env = dict(os.environ, PYTHONIOENCODING="cp1252:strict")
        r = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
