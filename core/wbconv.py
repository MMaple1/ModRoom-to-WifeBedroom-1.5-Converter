"""wbconv - shared conversion core for the Wife's Bedroom mod converters (standard library only).

Used by Modded_to_WB_1.5.py and WB_1.5_to_Modded.py and the WB Mobile Patcher (wbp/wbconv.py). All three carry an
identical copy; the canonical one is Modded_to_WB_1.5_Converter_v1.1/core/wbconv.py. After editing it run the
patcher's `python tools/sync_wbconv.py` (copies it to the others; `--check` only reports).

What it knows (checked against the engines' own code, see the WB Mobile Patcher's ENGINE_ARCHITECTURE_REPORT.md):
  * Two pack formats share file names but not frame counts or descriptor keys:
      standard (Wife's Bedroom v1.5, Deeproom spouse packs): custom_data.futa / .spouse, custom_portrait.png ...
      modern   (ModRoom V3.3, Deeproom modern wife):         custom_data.futa / .wife,   custom_wife_*_0.png ...
  * A strip renamed between the formats keeps its pixels but not its frame count, so it is cut wrongly
    unless it is padded or cropped. This module pads and crops PNG strips with no third-party library.
  * Padding keeps every frame and is allowed. Cropping drops frames, so it is only done where the dropped
    frame is known to be unused; every crop, and every portrait change, needs approximate=True. The partner
    X-ray crop (4 to 3) used to count as safe because the draw code never shows a 4th frame, but hybrid packs
    (2026-11 library scan) show the standard 4th frame equal to the modern 3rd, so it is treated as lossy.
  * ModRoom lists a pack only when it has the sprites it draws (admission rules below); others crash it.
  * One descriptor per pack, in the target's format. Descriptor conversion only adds keys, never changes values.
"""
import hashlib
import os
import re
import shutil
import struct
import sys
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = ["PngError", "Image", "read_png", "write_png", "pad_width", "crop_width", "sha256_file",
           "safe_extract", "unique_name", "png_size", "select_frames", "FRAME_MAPS", "Ini", "convert_descriptor_bytes", "Result", "Report",
           "to_v15", "from_v15", "modroom_missing", "detect_format", "FRAMES", "NAMES", "publish_category",
           "progress", "say", "Spinner", "strip_frames", "frame_width_of", "pack_notes",
           "repair_deepthroat_bytes", "repair_deepthroat_folder", "repair_deepthroat_main"]



# --------------------------------------------------------------------------- console progress
# Shared by the converters (and available to the patcher and the Studio, which carry identical copies).
_BAR = {"line": "", "shown": {}}
_SPIN = "|/-\\"


def _isatty():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def progress(current, total, prefix="Working", bar_length=28):
    """One-line progress bar, redrawn only when the whole percentage changes (so thousands of small steps
    do not slow the console); always drawn at the start and the end, and finished with a newline."""
    percent = float(current) / max(1, total)
    shown = int(percent * 100)
    if 1 < current < total and _BAR["shown"].get(prefix) == shown:
        return
    _BAR["shown"][prefix] = shown
    arrow = "=" * max(0, int(round(percent * bar_length)) - 1) + ">" if percent > 0 else ""
    line = f"[*] {prefix}: [{arrow}{' ' * (bar_length - len(arrow))}] {shown}% ({current}/{total})"
    pad = " " * max(0, len(_BAR["line"]) - len(line))
    sys.stdout.write("\r" + line + pad)
    if current >= total:
        sys.stdout.write("\n")
        _BAR["line"] = ""
    else:
        _BAR["line"] = line
    sys.stdout.flush()


def say(msg):
    """Print a message while a progress bar is on screen: the bar line is cleared first and redrawn below."""
    if _BAR["line"]:
        sys.stdout.write("\r" + " " * len(_BAR["line"]) + "\r")
    print(msg)
    if _BAR["line"]:
        sys.stdout.write(_BAR["line"])
        sys.stdout.flush()


class Spinner:
    """Animated "working" line for steps whose progress cannot be measured (unpacking, publishing):

        with Spinner("Unpacking mods.zip"):
            ...

    Shows a moving bar and the elapsed seconds; prints one final line with the duration."""

    def __init__(self, label, width=24):
        self.label, self.width = label, width

    def __enter__(self):
        import threading
        import time
        self._t0 = time.time()
        self._stop = threading.Event()
        interactive = _isatty()

        def run():
            i = 0
            while not self._stop.wait(0.15):
                if not interactive:
                    continue
                pos = i % (2 * self.width - 2)
                pos = pos if pos < self.width else 2 * self.width - 2 - pos
                bar = (" " * pos + "###").ljust(self.width + 2)[:self.width + 2]
                sys.stdout.write(f"\r[{_SPIN[i % 4]}] {self.label}: [{bar}] {time.time() - self._t0:5.0f}s ")
                sys.stdout.flush()
                i += 1

        if not interactive:
            print(f"[*] {self.label} ...")
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        import time
        self._stop.set()
        self._thread.join(timeout=1)
        if _isatty():
            sys.stdout.write("\r" + " " * (len(self.label) + self.width + 24) + "\r")
        print(f"[*] {self.label}: {'failed' if exc_type else 'done'} in {time.time() - self._t0:.0f}s")
        return False

# --------------------------------------------------------------------------- PNG (8-bit, non-interlaced)
class PngError(Exception):
    pass


PNG_SIG = b"\x89PNG\r\n\x1a\n"


@dataclass
class Image:
    width: int
    height: int
    rows: List[bytearray]  # RGBA8, one bytearray per row


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(path) -> Image:
    data = Path(path).read_bytes()
    if data[:8] != PNG_SIG:
        raise PngError("not a PNG file")
    pos, ihdr, plte, trns, idat = 8, None, None, None, bytearray()
    while pos + 8 <= len(data):
        length, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if typ == b"IHDR":
            if len(body) != 13:
                raise PngError("bad IHDR chunk")
            ihdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
    if not ihdr:
        raise PngError("missing IHDR")
    w, h, bit_depth, ctype, _, _, interlace = ihdr
    if interlace:
        raise PngError("interlaced PNG is not supported")
    if bit_depth != 8 or ctype not in (0, 2, 3, 4, 6):
        raise PngError(f"unsupported PNG type (bit depth {bit_depth}, colour type {ctype})")
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    stride = w * bpp
    raw = zlib.decompress(bytes(idat))
    if len(raw) < h * (stride + 1):
        raise PngError("truncated image data")
    rows, prev, p = [], bytearray(stride), 0
    for _ in range(h):
        ft = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += stride + 1
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                ul = prev[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, prev[i], ul)) & 255
        elif ft != 0:
            raise PngError(f"bad filter type {ft}")
        prev = line
        rows.append(_to_rgba(line, w, ctype, plte, trns))
    return Image(w, h, rows)


def _to_rgba(line, w, ctype, plte, trns):
    if ctype == 6:
        return line
    out = bytearray(w * 4)
    if ctype == 2:
        out[0::4], out[1::4], out[2::4], out[3::4] = line[0::3], line[1::3], line[2::3], b"\xff" * w
        if trns and len(trns) >= 6:  # colour key: 16-bit samples, low byte at 8-bit depth
            key = bytes((trns[1], trns[3], trns[5]))
            for i in range(w):
                if line[i * 3:i * 3 + 3] == key:
                    out[i * 4 + 3] = 0
    elif ctype == 0:
        out[0::4] = out[1::4] = out[2::4] = line
        out[3::4] = b"\xff" * w
        if trns and len(trns) >= 2:
            out[3::4] = line.translate(bytes(0 if v == trns[1] else 255 for v in range(256)))
    elif ctype == 4:
        out[0::4] = out[1::4] = out[2::4] = line[0::2]
        out[3::4] = line[1::2]
    else:  # palette
        pal = plte or b""
        r = bytes(pal[i * 3] if i * 3 + 2 < len(pal) else 0 for i in range(256))
        g = bytes(pal[i * 3 + 1] if i * 3 + 2 < len(pal) else 0 for i in range(256))
        b = bytes(pal[i * 3 + 2] if i * 3 + 2 < len(pal) else 0 for i in range(256))
        a = bytes((trns[i] if trns and i < len(trns) else 255) for i in range(256))
        out[0::4], out[1::4], out[2::4], out[3::4] = line.translate(r), line.translate(g), line.translate(b), line.translate(a)
    return out


def _chunk(typ: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + typ + body + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF)


def write_png(path, img: Image):
    raw = b"".join(b"\x00" + bytes(row) for row in img.rows)
    out = PNG_SIG + _chunk(b"IHDR", struct.pack(">IIBBBBB", img.width, img.height, 8, 6, 0, 0, 0)) \
        + _chunk(b"IDAT", zlib.compress(raw, 6)) + _chunk(b"IEND", b"")
    Path(path).write_bytes(out)


def png_size(path):
    """(width, height) from the IHDR chunk without decoding the image; None if unreadable."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] != PNG_SIG or head[12:16] != b"IHDR":
            return None
        return struct.unpack(">II", head[16:24])
    except OSError:
        return None


def select_frames(img: Image, frame_w: int, indices) -> Image:
    """New strip made of the listed frames (0-based) of `img`, in that order."""
    rows = []
    for r in img.rows:
        out = bytearray()
        for i in indices:
            out += r[i * frame_w * 4:(i + 1) * frame_w * 4]
        rows.append(out)
    return Image(len(indices) * frame_w, img.height, rows)


def pad_width(img: Image, new_w: int) -> Image:
    extra = bytes((new_w - img.width) * 4)
    return Image(new_w, img.height, [bytearray(r) + extra for r in img.rows])


def crop_width(img: Image, new_w: int) -> Image:
    return Image(new_w, img.height, [bytearray(r[:new_w * 4]) for r in img.rows])


def _alias_strip(src, dst, src_frames, dst_frames):
    """Copy a cowgirl strip to stand in for the missing one, with the frame count the other pose is cut into, at the
    source's own frame width (high-res packs too). The copy is a generated stand-in, so trimming it loses nothing of the
    author's file. A strip that does not divide into src_frames is copied unchanged."""
    shutil.copyfile(str(src), str(dst))
    try:
        img = read_png(dst)
        fw = frame_width_of(img.width, src_frames)
        if fw:
            want = dst_frames * fw
            if img.width < want:
                write_png(dst, pad_width(img, want))
            elif img.width > want:
                write_png(dst, crop_width(img, want))
    except (PngError, OSError, zlib.error):
        pass


# --------------------------------------------------------------------------- small safe helpers
def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_extract(zf, dest) -> int:
    """Extract a zip without letting a crafted member name write outside `dest`. Returns the member count."""
    root = Path(dest).resolve()
    for m in zf.infolist():
        target = (root / m.filename).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"unsafe path in archive: {m.filename}")
    zf.extractall(str(root))
    return len(zf.infolist())


_FS_BAD = re.compile(r'[\/:*?"<>|]')
_DEVICE_NAMES = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}


def safe_dirname(name, limit=80) -> str:
    """A lower-case folder / manifest name that every filesystem accepts.

    Control and invisible characters go, so does a pile of combining marks ("zalgo" text, which makes the name
    unreadable and its folder hard to create); characters Windows forbids become `_`, spaces become `_`, trailing
    dots and spaces go, Windows device names (con, aux, nul ...) get a prefix, and the length is capped."""
    s = unicodedata.normalize("NFC", str(name))
    if sum(unicodedata.category(c) in ("Mn", "Me") for c in s) > 2:
        s = "".join(c for c in s if unicodedata.category(c) not in ("Mn", "Me"))
    s = "".join(c for c in s if unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co", "Cn"))
    s = _FS_BAD.sub("_", s).strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_. ")[:limit].rstrip("_. ")
    if s.split(".")[0] in _DEVICE_NAMES:
        s = "_" + s
    return s or "unnamed_mod"


def make_pack_dir(parent, name, fallback) -> Path:
    """Create parent/name; when the OS refuses the name, use a name made from `fallback` (the pack's folder name), then a hash."""
    parent = Path(parent)
    for candidate in (name, safe_dirname(fallback), "pack_" + hashlib.sha256(str(fallback).encode("utf-8", "replace")).hexdigest()[:8]):
        try:
            (parent / candidate).mkdir(parents=True, exist_ok=True)
            return parent / candidate
        except (OSError, ValueError):
            continue
    raise OSError(f"cannot create a folder for pack '{fallback}' in {parent}")


def unique_name(parent: Path, name: str) -> str:
    """`name`, or name_2, name_3 ... when a folder of that name already exists in `parent`."""
    if not (Path(parent) / name).exists():
        return name
    n = 2
    while (Path(parent) / f"{name}_{n}").exists():
        n += 1
    return f"{name}_{n}"


def unique_pack_name(clean, folder, used) -> str:
    """A name for a pack whose display name `clean` may already be taken in `used`.

    A repeat keeps the tag that makes it different: the part of the pack's folder name that does not repeat the
    display name ("astolfo" + folder "Astolfo (naked)" gives "astolfo_(naked)"), and a number only as a last resort."""
    if clean not in used:
        return clean
    shown, tokens = clean.split("_"), safe_dirname(folder).split("_")
    i = 0
    while i < len(shown) and i < len(tokens) and shown[i] == tokens[i]:
        i += 1
    rest = "_".join(tokens[i:])
    cand = f"{clean}_{rest}" if rest else clean
    base, n = cand, 2
    while cand in used:
        cand = f"{base}_{n}"
        n += 1
    return cand


def tree_signature(root) -> list:
    """(relative path, size, sha256) of every file under `root`, sorted: equal signatures mean equal packs.

    The generated `_manifest.txt` index files are ignored: they are written after a pack is published."""
    root = Path(root)
    return [(f.relative_to(root).as_posix().lower(), f.stat().st_size, sha256_file(f)) for f in sorted(root.rglob("*")) if f.is_file() and f.name != "_manifest.txt"]


def find_identical(dest_parent, name, src):
    """The folder `name`, `name_2`, `name_3` ... in `dest_parent` whose content equals the pack `src`, else None.

    Converting into a destination that already holds a pack must not leave a second copy under a new number."""
    base, sig = Path(dest_parent), None
    for cand in [name] + [f"{name}_{n}" for n in range(2, 100)]:
        existing = base / cand
        if not existing.is_dir():
            continue
        if sig is None:
            sig = tree_signature(src)
        if tree_signature(existing) == sig:
            return cand
    return None


def publish_category(staging_cat: Path, dest_cat: Path, clean: bool) -> List[str]:
    """Move finished packs from a staging category folder into the destination without overwriting anything.

    The destination is only touched after a conversion produced at least one pack (with clean=True its old
    contents are removed at that point, not before). Returns the final names."""
    Path(dest_cat).mkdir(parents=True, exist_ok=True)
    packs = [p for p in sorted(Path(staging_cat).iterdir()) if p.is_dir()] if Path(staging_cat).is_dir() else []
    if not packs:
        return []

    def _force_rm(path):
        import stat
        p = Path(path)
        if not p.exists(): return
        def _err(fn, pt, exc):
            try:
                os.chmod(pt, stat.S_IWRITE)
                fn(pt)
            except Exception: pass
        try: shutil.rmtree(p, onerror=_err)
        except Exception: pass

    if clean and Path(dest_cat).exists():
        _force_rm(dest_cat)
        import time
        time.sleep(0.05)
        Path(dest_cat).mkdir(parents=True, exist_ok=True)

    names = []
    for p in packs:
        same = find_identical(dest_cat, p.name, p)
        if same:
            names.append(same)  # already in the destination, unchanged: keep that one, make no copy
            continue
        final = unique_name(dest_cat, p.name)
        target_p = Path(dest_cat) / final
        if target_p.exists():
            _force_rm(target_p)
        try:
            shutil.move(str(p), str(target_p))
        except Exception:
            try:
                shutil.copytree(str(p), str(target_p), dirs_exist_ok=True)
                _force_rm(p)
            except Exception:
                continue  # not published (locked file, permissions): do not report it as written
        names.append(final)
    return names


# --------------------------------------------------------------------------- INI (line-preserving)
_SECTION = re.compile(r"^\s*\[([^\]]*)\]\s*(?:[;#].*)?$")
_KEYVAL = re.compile(r"^\s*([^=;#\[\]][^=]*?)\s*=\s*(.*?)\s*$")


class Ini:
    """Edits add lines and never rewrite existing ones; line endings, BOM and unknown lines are preserved."""

    def __init__(self, data: bytes):
        self.bom = data.startswith(b"\xef\xbb\xbf")
        raw = data[3:] if self.bom else data
        try:
            self.text, self.enc = raw.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            self.text, self.enc = raw.decode("latin-1"), "latin-1"
        self.eol = "\r\n" if "\r\n" in self.text else "\n"
        self.lines = self.text.replace("\r\n", "\n").split("\n")
        self.changed = False

    def _scan(self):
        sec = ""
        for i, line in enumerate(self.lines):
            m = _SECTION.match(line)
            if m:
                sec = m.group(1).strip().lower()
                continue
            m = _KEYVAL.match(line)
            if m:
                yield i, sec, m.group(1).strip().lower(), m.group(2)

    def get(self, section, key):
        s, k = section.lower(), key.lower()
        for _, sec, key_, val in self._scan():
            if sec == s and key_ == k:
                return val
        return None

    def add(self, section, key, value):
        if self.get(section, key) is not None:
            return False
        s, last, in_sec = section.lower(), None, False
        for i, line in enumerate(self.lines):
            m = _SECTION.match(line)
            if m:
                in_sec = m.group(1).strip().lower() == s
                if in_sec:
                    last = i
                continue
            if in_sec and _KEYVAL.match(line):
                last = i
        new = f"{key}={value}"
        if last is None:
            while self.lines and self.lines[-1] == "":
                self.lines.pop()
            self.lines += ["", f"[{section}]", new, ""]
        else:
            self.lines.insert(last + 1, new)
        self.changed = True
        return True

    def to_bytes(self):
        # A latin-1 file keeps its encoding (existing bytes must not change); an added value it cannot hold,
        # such as a Japanese pack name, gets "?" for those characters instead of crashing the conversion.
        out = self.eol.join(self.lines).encode(self.enc, errors="replace")
        return (b"\xef\xbb\xbf" + out) if self.bom else out


_POSE_MAP = [(("mating_press", "origin_x"), ("sprite", "mating_press_origin_x")), (("mating_press", "origin_y"), ("sprite", "mating_press_origin_y")),
             (("deepthroat", "origin_x"), ("sprite", "deepthroat_origin_x")), (("deepthroat", "origin_y"), ("sprite", "deepthroat_origin_y")),
             (("reverse_cowgirl", "origin_x"), ("sprite", "cowgirl_origin_x")), (("reverse_cowgirl", "origin_y"), ("sprite", "cowgirl_origin_y"))]
_V15_MAP = [(("xray", "origin_x"), ("sprite", "xray_x")), (("xray", "origin_y"), ("sprite", "xray_y"))]

# v1.5 draws a partner's deepthroat strip where the vanilla sWifeDeepthroat goes (origin y 150 in both games);
# Deeproom's spouse loader draws it 70 px higher (legacy_dt_y_offset = -70). Measured 2026-11-17 from both games' code.
DT_V15_TO_DEEPROOM = -70


def _derive(ini, pairs, forward=True):
    for left, right in pairs:
        src, dst = (left, right) if forward else (right, left)
        val = ini.get(*src)
        if val is not None:
            ini.add(dst[0], dst[1], val)


def _num(value):
    try:
        return float(str(value).strip().strip('"'))
    except (TypeError, ValueError):
        return None


def _xray_offset(ini):
    """[sprite] xray_offset_y (what ModRoom/Deeproom futas read) from v1.5's [sprite] xray_y."""
    y = _num(ini.get("sprite", "xray_y"))
    if y is not None:
        ini.add("sprite", "xray_offset_y", f'"{round(y - 84)}"')


def _fmt(v):
    return f'"{v:.6f}"'


def _dt_to_deeproom(ini):
    """[deepthroat] origin_y from a v1.5 partner's [sprite] deepthroat_origin_y (minus 70). Without that key nothing is
    added: Deeproom then uses the [sprite] origin, as for its own packs (adding v1.5's default 150 drew them 66 px high)."""
    v = _num(ini.get("sprite", "deepthroat_origin_y"))
    if v is not None:
        ini.add("deepthroat", "origin_y", _fmt(v + DT_V15_TO_DEEPROOM))


def _dt_to_v15(ini):
    """[sprite] deepthroat_origin_y for v1.5 from Deeproom's [deepthroat] origin_y (plus 70)."""
    if ini.get("sprite", "deepthroat_origin_y") is not None:
        return
    v = _num(ini.get("deepthroat", "origin_y"))
    if v is None:
        return  # no Deeproom deepthroat block: v1.5 uses its own default (150), within 4 px of Deeproom's
    ini.add("sprite", "deepthroat_origin_y", _fmt(v - DT_V15_TO_DEEPROOM))


_OLD_DT_DEFAULT = '"150.000000"'


def repair_deepthroat_bytes(data: bytes) -> bytes:
    """Undo the [deepthroat] block converters before 2026-11-17 wrote into Deeproom partner descriptors.

    Those versions added origin_x (copied from [sprite] origin_x) and origin_y, which was either v1.5's default
    "150.000000" (Deeproom then drew the sprite 66 px high) or a 1:1 copy of [sprite] deepthroat_origin_y (70 px high).
    Only a single block in exactly that shape is touched; anything hand-made (other keys, comments, other values)
    is left alone. Invented block -> removed (the game uses the [sprite] origin, as for native packs); copied
    value -> that value minus 70. Returns the same bytes object when nothing matches. Safe to run twice."""
    ini = Ini(data)
    starts = [i for i, line in enumerate(ini.lines)
              if (m := _SECTION.match(line)) and m.group(1).strip().lower() == "deepthroat"]
    if len(starts) != 1:
        return data
    start = starts[0]
    end = next((i for i in range(start + 1, len(ini.lines)) if _SECTION.match(ini.lines[i])), len(ini.lines))
    keys = {}
    for i in range(start + 1, end):
        line = ini.lines[i]
        if not line.strip():
            continue
        m = _KEYVAL.match(line)
        k = m.group(1).strip().lower() if m else None
        if k is None or k in keys:
            return data  # comment, stray text or a repeated key: not what the old converter wrote
        keys[k] = (i, m.group(2))
    if set(keys) != {"origin_x", "origin_y"} or keys["origin_x"][1] != ini.get("sprite", "origin_x"):
        return data
    dt_line, dt = keys["origin_y"]
    v15 = ini.get("sprite", "deepthroat_origin_y")
    if v15 is not None and dt == v15:
        v = _num(v15)
        if v is None:
            return data
        ini.lines[dt_line] = f"origin_y={_fmt(v + DT_V15_TO_DEEPROOM)}"
    elif v15 is None and dt == _OLD_DT_DEFAULT:
        while end > start + 1 and not ini.lines[end - 1].strip():
            end -= 1  # keep the blank line(s) that separate the next section
        del ini.lines[start:end]
        if 0 < start < len(ini.lines) and not ini.lines[start - 1].strip() and not ini.lines[start].strip():
            del ini.lines[start]  # no double blank line where the block was
    else:
        return data
    return ini.to_bytes()


def repair_deepthroat_folder(root, apply=False, backup=None):
    """Run repair_deepthroat_bytes over every custom_data.spouse under `root`.
    Returns the descriptor paths that need (or, with apply=True, got) the repair. With apply=True every original is
    first stored in the `backup` zip (required, must not exist yet) under its path relative to `root`."""
    root = Path(root)
    real_root = root.resolve()
    todo = []
    for p in sorted(root.rglob("custom_data.spouse")):
        if p.is_symlink() or not p.is_file() or real_root not in p.resolve().parents:  # 3.8: no is_relative_to
            continue  # never write through a link or outside the folder
        data = p.read_bytes()
        new = repair_deepthroat_bytes(data)
        if new is not data:
            todo.append((p, data, new))
    if apply and todo:
        if backup is None:
            raise ValueError("apply=True needs a backup zip path")
        backup = Path(backup)
        if backup.exists():
            raise FileExistsError(f"backup already exists: {backup}")
        with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as z:
            for p, data, _ in todo:
                z.writestr(p.relative_to(root).as_posix(), data)
        for p, _, new in todo:  # each file is replaced whole, so a failure never leaves a half-written descriptor
            tmp = p.with_name(p.name + ".repair_tmp")
            try:
                tmp.write_bytes(new)
                os.replace(tmp, p)
            finally:
                if tmp.exists():
                    tmp.unlink()
    return [p for p, _, _ in todo]


def repair_deepthroat_main(argv=None):
    """Command line for repair_deepthroat_folder: `<folder> [--apply]`. Dry run unless --apply."""
    import argparse
    import time
    ap = argparse.ArgumentParser(description="Fix Deeproom partners whose deepthroat sprite sits too high after "
                                             "conversion with a converter older than 2026-11-17.")
    ap.add_argument("folder", help="a custom_wives folder (or any folder above the partner packs)")
    ap.add_argument("--apply", action="store_true", help="write the fixes (default: only list them)")
    a = ap.parse_args(argv)
    root = Path(a.folder)
    if not root.is_dir():
        ap.error(f"not a folder: {root}")
    backup = root.parent / f"{root.name}_deepthroat_backup_{time.strftime('%Y%m%d_%H%M%S')}.zip" if a.apply else None
    try:
        found = repair_deepthroat_folder(root, apply=a.apply, backup=backup)
    except OSError as e:  # includes FileExistsError for the backup; files already replaced stay fixed (re-run is safe)
        print(f"Stopped: {e}")
        if backup is not None and backup.exists():
            print(f"Originals of every file it was going to change are in {backup}")
        return 1
    for p in found:
        print(f"  {p.relative_to(root)}")
    if not found:
        print("Nothing to fix.")
    elif a.apply:
        print(f"Fixed {len(found)} partner(s). Originals saved in {backup}")
    else:
        print(f"{len(found)} partner(s) need the fix. Run again with --apply to fix them (originals are backed up).")
    return 0


def _deeproom_extras(ini):
    """Per-pose blocks Deeproom's spouse loader reads, built from a v1.5 partner's [sprite] keys (added only when absent)."""
    def val(sec, key, default):
        v = ini.get(sec, key)
        return v if v is not None else f'"{default}"'
    ox, oy = val("sprite", "origin_x", "80.000000"), val("sprite", "origin_y", "84.000000")
    # The X-ray keeps its OWN origin: v1.5 draws an X-ray without xray_x/xray_y at (80, 84). Falling back to
    # the body's [sprite] origin (100-120 on wide mating-press canvases) drew the X-ray 20-40 px off-centre.
    xx = ini.get("sprite", "xray_x") or '"80.000000"'
    xy = ini.get("sprite", "xray_y") or '"84.000000"'
    for sec in ("mating_press", "reverse_cowgirl"):
        ini.add(sec, "origin_x", ox)
        ini.add(sec, "origin_y", oy)
    ini.add("xray", "origin_x", xx)
    ini.add("xray", "origin_y", xy)
    ini.add("condom", "condom_y_mpress", val("sprite", "condom_y", "78.000000"))
    ini.add("condom", "condom_y_cowgirls", val("sprite", "standing_condom_y", "0.000000"))
    ini.add("gender", "is_male", '"0"')
    _xray_offset(ini)


def convert_descriptor_bytes(data: bytes, source: str, target: str, name: str = "") -> bytes:
    """source: 'futa' | 'spouse' | 'wife'.  target: 'wife' (ModRoom), 'spouse' (Deeproom), 'v15_spouse', 'v15_futa'.
    Keys are only added. Returns the same bytes object when nothing changes."""
    ini = Ini(data)
    if target == "wife" and source == "spouse":
        _derive(ini, _POSE_MAP, forward=True)
    elif target == "spouse":                      # Deeproom reads per-pose sections; v1.5 files carry [sprite] xray_x/y
        if source == "wife":
            _derive(ini, _POSE_MAP, forward=False)
        _derive(ini, _V15_MAP, forward=False)
        if source == "spouse":
            _dt_to_deeproom(ini)
            _deeproom_extras(ini)
    elif target == "futa_modded":                 # ModRoom / Deeproom lover: xray offset from v1.5's xray_y
        _xray_offset(ini)
    elif target == "v15_spouse":
        if source == "wife":
            _derive(ini, _POSE_MAP, forward=False)
        _derive(ini, _V15_MAP, forward=True)
        if source == "spouse":
            _dt_to_v15(ini)
    if target.startswith("v15") and name and ini.get("info", "name") is None:
        ini.add("info", "name", '"' + name.replace('"', "'") + '"')
    return ini.to_bytes() if ini.changed else data


# --------------------------------------------------------------------------- format tables
FRAME_W = 160
PORTRAIT_FRAME_W = 128

NAMES: Dict[Tuple[str, str], Dict[str, str]] = {
    ("futa", "standard"): {"portrait": "custom_portrait.png", "mating_press": "custom_mating_press.png",
                           "cowgirl": "custom_reverse_cowgirl.png", "xray": "custom_xray.png"},
    ("futa", "modern"): {"portrait": "custom_futa_portrait_0.png", "mating_press": "custom_futa_mating_press_0.png",
                         "cowgirl": "custom_futa_cowgirls_0.png", "xray": "custom_futa_xray_0.png"},
    ("wife", "standard"): {"portrait": "custom_portrait.png", "mating_press": "custom_mating_press.png",
                           "reverse_cowgirl": "custom_reverse_cowgirl.png", "forward_cowgirl": "custom_forward_cowgirl.png",
                           "deepthroat": "custom_deepthroat.png", "xray": "custom_xray.png"},
    ("wife", "modern"): {"portrait": "custom_wife_portrait_0.png", "mating_press": "custom_wife_mating_press_0.png",
                         "forward_cowgirl": "custom_wife_cowgirl_0.png", "reverse_cowgirl": "custom_wife_reverse_cowgirl_0.png",
                         "deepthroat": "custom_wife_deepthroat_0.png", "xray": "custom_wife_xray_0.png"},
}
ALIASES = {("futa", "standard", "cowgirl"): ["custom_cowgirl.png"],
           ("wife", "standard", "forward_cowgirl"): ["custom_cowgirl.png", "custom_reverse_cowgirl.png"],
           ("wife", "standard", "reverse_cowgirl"): ["custom_cowgirl.png", "custom_forward_cowgirl.png"]}
# frames per strip (measured over thousands of packs; see the engine report)
FRAMES: Dict[Tuple[str, str], Dict[str, int]] = {
    ("futa", "standard"): {"portrait": 10, "mating_press": 9, "cowgirl": 5, "xray": 3},
    ("futa", "modern"): {"portrait": 17, "mating_press": 24, "cowgirl": 19, "xray": 18},
    ("wife", "standard"): {"portrait": 10, "mating_press": 4, "reverse_cowgirl": 5, "forward_cowgirl": 6, "deepthroat": 5, "xray": 4},
    ("wife", "modern"): {"portrait": 17, "mating_press": 5, "forward_cowgirl": 11, "reverse_cowgirl": 10, "deepthroat": 5, "xray": 3},
}

# Which frames of a modern strip make up the standard strip (kind, strip) -> modern frame indices, in standard order.
# Learned by comparing the frames of packs that ship BOTH formats for the same character (lover mating press and
# cowgirl: 4 packs, every frame agreed; partner mating press: 10 packs, frames 0-3 matched and the 5th is the extra
# one). Used only with approximate=True: the samples are small, so the result is reported as approximate.
# Portraits are layered face strips and do not map frame for frame; they are never mapped.
FRAME_MAPS = {
    ("futa", "mating_press"): [0, 1, 2, 3, 4, 5, 6, 7, 19],
    ("futa", "cowgirl"): [0, 1, 2, 14, 17],
    ("wife", "mating_press"): [0, 1, 2, 3],
}

# What ModRoom V3.3 needs before it lists a pack (its own scan); names the patched checks also accept
MODROOM_NEEDS = {
    "futa": [("portrait", ("custom_futa_portrait_0.png", "custom_portrait.png", "custom_futa_portrait.png")),
             ("mating press", ("custom_futa_mating_press_0.png", "custom_mating_press.png", "custom_futa_mating_press.png")),
             ("cowgirl", ("custom_futa_cowgirls_0.png", "custom_reverse_cowgirl.png", "custom_cowgirl.png")),
             ("X-ray", ("custom_futa_xray_0.png", "custom_xray.png", "custom_futa_xray.png"))],
    "wife": [("mating press", ("custom_wife_mating_press_0.png", "custom_mating_press.png", "custom_wife_mating_press.png")),
             ("forward cowgirl", ("custom_wife_cowgirl_0.png", "custom_cowgirl.png", "custom_wife_cowgirl.png", "custom_forward_cowgirl.png", "custom_reverse_cowgirl.png", "custom_wife_reverse_cowgirl_0.png")),
             ("reverse cowgirl", ("custom_wife_reverse_cowgirl_0.png", "custom_reverse_cowgirl.png", "custom_wife_reverse_cowgirl.png", "custom_cowgirl.png", "custom_wife_cowgirl_0.png"))],
}


def modroom_missing(pack_dir, kind) -> List[str]:
    needs = MODROOM_NEEDS.get(kind)
    if not needs:
        return []
    present = {p.name.lower() for p in Path(pack_dir).iterdir()}
    return [label for label, names in needs if not any(n in present for n in names)]


def detect_format(kind, names) -> str:
    """'standard', 'modern', 'hybrid' (both) or 'none', from the lower-case file names of a pack."""
    names = {n.lower() for n in names}
    std = any(n in names for n in NAMES[(kind, "standard")].values()) or any(a in names for (k, f, _), al in ALIASES.items() if k == kind for a in al)
    mod = any(n in names for n in NAMES[(kind, "modern")].values())
    return "hybrid" if std and mod else "modern" if mod else "standard" if std else "none"


# --------------------------------------------------------------------------- results and report
@dataclass
class Result:
    status: str = "ok"           # ok | padded | approximate | partial | skipped
    converted: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class Report:
    def __init__(self, title="Conversion report"):
        self.title, self.rows = title, []

    def add(self, pack, category, target, result: Result):
        self.rows.append((pack, category, target, result))

    def counts(self):
        out = {}
        for *_, r in self.rows:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", "", "Counts: " + (", ".join(f"{v} {k}" for k, v in sorted(self.counts().items())) or "none"), "",
                 "| Pack | Kind | Target | Status | Details |", "|---|---|---|---|---|"]
        for pack, cat, target, r in self.rows:
            detail = "; ".join(r.converted + [f"not converted: {s}" for s in r.skipped] + r.notes)
            lines.append(f"| `{pack}` | {cat} | {target} | {r.status} | {detail.replace('|', '/')} |")
        lines += ["", "**ok**: exact. **padded**: transparent frames were appended to reach the target frame count (nothing dropped). "
                      "**approximate**: frames were dropped to reach the target count (`--approximate`). **partial**: some strips could not be converted. "
                      "**skipped**: the pack was not written."]
        return "\n".join(lines) + "\n"

    def write(self, path):
        Path(path).write_text(self.to_markdown(), encoding="utf-8")


# --------------------------------------------------------------------------- strip and pack conversion
def _frame_w(strip):
    """The usual frame width of a strip. Only a hint: the games cut a strip into a fixed NUMBER of frames
    whatever its width (high-res packs use 256 px portraits, many mating presses 220 px frames)."""
    return PORTRAIT_FRAME_W if strip == "portrait" else FRAME_W


def strip_frames(kind, fmt, strip, width):
    """Frames the engine cuts this strip into. The lover's standard cowgirl strip is 7 frames when it is a
    whole number of 7 usual-width frames (the v1.5 rule: 7 when wider than origin_x * 10), otherwise 5."""
    n = FRAMES.get((kind, fmt), {}).get(strip)
    if (kind, fmt, strip) == ("futa", "standard", "cowgirl") and width and width % (7 * FRAME_W) == 0 and width // FRAME_W == 7:
        return 7
    return n


def frame_width_of(width, frames):
    """Width of one frame when `width` divides evenly into `frames`, else None."""
    return width // frames if frames and width and width % frames == 0 else None


def pack_notes(pack_dir, kind, fmt) -> List[str]:
    """Problems the games will show for this pack as authored (report notes; nothing is changed):
    strips whose width does not divide into the frame count the engine uses (frames are cut off-centre),
    and an X-ray origin copied from the mating-press origin (draws the X-ray 10-40 px off-centre)."""
    pack_dir = Path(pack_dir)
    notes = []
    for strip, name in NAMES.get((kind, fmt), {}).items():
        f = pack_dir / name
        size = png_size(f) if f.is_file() else None
        if not size:
            continue
        n = strip_frames(kind, fmt, strip, size[0])
        if n and size[0] % n:
            notes.append(f"{name} is {size[0]} px; the game cuts it into {n} frames ({size[0] / n:.1f} px each)")
    if kind == "wife":
        for desc in ("custom_data.spouse", "custom_data.wife"):
            if not (pack_dir / desc).is_file():
                continue
            ini = Ini((pack_dir / desc).read_bytes())
            xo = _num(ini.get("xray", "origin_x"))
            body = _num(ini.get("mating_press", "origin_x")) or _num(ini.get("sprite", "mating_press_origin_x")) or _num(ini.get("sprite", "origin_x"))
            xr = pack_dir / NAMES[(kind, fmt)].get("xray", "")
            size = png_size(xr) if xr.is_file() else None
            if xo and body and xo == body and xo != 80 and size and size[0] % FRAME_W == 0:
                notes.append(f"{desc}: [xray] origin_x={xo:g} is the same as the mating-press origin, but the X-ray strip uses "
                             f"standard {FRAME_W} px frames, so the X-ray will be drawn {abs(xo - 80):g} px off-centre (80 is usual)")
            break
    return notes


def _policy(kind, strip, src_frames, dst_frames):
    if dst_frames == src_frames:
        return "copy"
    if dst_frames > src_frames:
        return "approximate" if strip == "portrait" else "pad"
    return "approximate"


def _find_source(pack_dir: Path, kind, fmt, strip) -> Optional[Path]:
    for name in [NAMES[(kind, fmt)].get(strip, "")] + ALIASES.get((kind, fmt, strip), []):
        if name and (pack_dir / name).exists():
            return pack_dir / name
    return None


def _convert_strips(pack_dir: Path, kind, src_fmt, dst_fmt, approximate, res: Result):
    used_pad = used_approx = False
    for strip, dst_name in NAMES[(kind, dst_fmt)].items():
        src = _find_source(pack_dir, kind, src_fmt, strip)
        if src is None:
            continue
        src_n, dst_n = FRAMES[(kind, src_fmt)].get(strip), FRAMES[(kind, dst_fmt)].get(strip)
        if src_n is None or dst_n is None:
            continue
        size = png_size(src)
        width = size[0] if size else 0
        src_n = strip_frames(kind, src_fmt, strip, width) or src_n
        dst_n = strip_frames(kind, dst_fmt, strip, width) if (kind, dst_fmt, strip) != ("futa", "standard", "cowgirl") else dst_n
        # trust the real width over the format table: a pack may already hold a strip with the target frame count
        # (it divides into the target count with a usual-width frame but not into the source count)
        fw = _frame_w(strip)
        if width and src_n != dst_n and width % fw == 0 and width // fw == dst_n and width % src_n != 0:
            dst = pack_dir / dst_name
            if src != dst:
                shutil.move(str(src), str(dst))
            res.converted.append(f"{strip} already {dst_n} frames, renamed")
            continue
        policy = _policy(kind, strip, src_n, dst_n)
        if kind == "wife" and strip == "xray" and dst_n < src_n and not (pack_dir / "custom_data.wife").exists():
            # a pack without custom_data.wife (a v1.5 .spouse pack): keep the strip as authored, only renamed
            dst = pack_dir / dst_name
            if src != dst:
                shutil.move(str(src), str(dst))
            res.converted.append(f"{strip} renamed, frames unchanged (the X-ray crop is only done for packs with a custom_data.wife)")
            continue
        if policy == "approximate" and not approximate:
            res.skipped.append(f"{strip} {src_n} to {dst_n} frames (use --approximate)")
            continue
        dst = pack_dir / dst_name
        if policy == "copy":
            if src != dst:
                shutil.move(str(src), str(dst))
            res.converted.append(f"{strip} renamed")
            continue
        try:
            img = read_png(src)
        except (PngError, OSError, zlib.error) as exc:
            res.skipped.append(f"{strip}: cannot read PNG ({exc})")
            continue
        fw = frame_width_of(img.width, src_n)  # any frame width: the games cut by frame count
        if fw is None:
            res.skipped.append(f"{strip}: width {img.width}px does not divide into {src_n} frames")
            continue
        picked = FRAME_MAPS.get((kind, strip)) if (src_fmt == "modern" and dst_fmt == "standard") else None
        if picked and len(picked) == dst_n and max(picked) < src_n and policy == "approximate":
            out = select_frames(img, fw, picked)
            how = "frames " + ",".join(str(i) for i in picked) + " kept"
        else:
            out = pad_width(img, dst_n * fw) if dst_n > src_n else crop_width(img, dst_n * fw)
            how = "padded" if dst_n > src_n else "first frames kept"
        write_png(dst, out)
        if src != dst:
            src.unlink()
        res.converted.append(f"{strip} {src_n} to {dst_n} frames ({how})")
        if policy == "approximate":
            used_approx = True
        elif policy == "pad":
            used_pad = True
    if used_approx:
        res.status = "approximate"
    elif used_pad:
        res.status = "padded"


_DESC_BY_KIND = {"futa": ("custom_data.futa",), "wife": ("custom_data.wife", "custom_data.spouse")}


def _write_descriptor(pack_dir: Path, kind, target, name, res: Result):
    """One descriptor per pack, in the target's name: futa -> .futa; wife -> .wife (modroom) / .spouse (deeproom, v15)."""
    target_file = "custom_data.futa" if kind == "futa" else ("custom_data.wife" if target == "modroom" else "custom_data.spouse")
    sources = [pack_dir / n for n in _DESC_BY_KIND[kind] if (pack_dir / n).exists()]
    if kind == "futa":
        source_kind = "futa"
    else:
        # prefer the descriptor that already is in the target's name, else the other one
        sources.sort(key=lambda p: p.name != target_file)
        source_kind = "wife" if sources and sources[0].name == "custom_data.wife" else "spouse"
    conv_target = {"modroom": "wife", "deeproom": "spouse", "v15": "v15_futa" if kind == "futa" else "v15_spouse"}[target]
    if kind == "futa" and target != "v15":
        conv_target = "futa_modded"
    data = sources[0].read_bytes() if sources else (b'[info]\nname="' + name.encode("utf-8", "replace") + b'"\n' if target == "v15" else b"[sprite]\norigin_x=80\norigin_y=84\n")
    new = convert_descriptor_bytes(data, source_kind, conv_target, name)
    (pack_dir / target_file).write_bytes(new)
    for s in sources:
        if s.name != target_file and s.exists():
            s.unlink()
    if not sources:
        res.notes.append("no descriptor found; a minimal one was written")


def to_v15(pack_dir, kind, name, approximate=False) -> Result:
    """Convert a copied ModRoom / FutasRoom / Deeproom pack folder (in place) to the Wife's Bedroom v1.5 format."""
    pack_dir, res = Path(pack_dir), Result()
    if kind in ("futa", "wife"):
        names = [p.name for p in pack_dir.iterdir()]
        fmt = detect_format(kind, names)
        if fmt == "modern":
            _convert_strips(pack_dir, kind, "modern", "standard", approximate, res)
            if not res.converted:
                res.status = "skipped"
                res.notes.append("modern-format strips cannot be used by v1.5 without --approximate (frame counts differ)")
                return res
            if res.skipped:
                res.status = "partial"
            for n in NAMES[(kind, "modern")].values():          # whatever was not converted is unusable in v1.5
                if (pack_dir / n).exists():
                    (pack_dir / n).unlink()
        elif fmt == "hybrid":
            for strip, n in NAMES[(kind, "modern")].items():   # v1.5 ignores the _0 strips; drop the duplicates
                if (pack_dir / n).exists():
                    (pack_dir / n).unlink()
            res.notes.append("had both naming sets; kept the standard strips")
        _write_descriptor(pack_dir, kind, "v15", name, res)
        res.notes.extend(pack_notes(pack_dir, kind, "standard"))  # what v1.5 will load
    return res


def from_v15(pack_dir, kind, target, name, approximate=False) -> Result:
    """Convert a copied v1.5 pack folder (in place) for 'deeproom' or 'modroom'."""
    pack_dir, res = Path(pack_dir), Result()
    if kind not in ("futa", "wife"):
        return res
    if target == "modroom" and kind == "wife":
        _convert_strips(pack_dir, kind, "standard", "modern", approximate, res)
        for strip in list(NAMES[(kind, "standard")]):
            if any(item.startswith(strip + " ") or item.startswith(strip + ":") for item in res.skipped):
                if strip == "portrait":
                    # ModRoom v3.3 natively supports 10-frame portraits via legacy_custom_portrait; keep intact
                    continue
                leftover = _find_source(pack_dir, kind, "standard", strip)
                if leftover is not None:
                    leftover.unlink()
                    res.notes.append(f"{strip} omitted (ModRoom would cut the {FRAMES[(kind, 'standard')][strip]}-frame strip as {FRAMES[(kind, 'modern')][strip]} frames)")

        # Ensure ModRoom has both forward and reverse cowgirl by aliasing if author only provided one
        rc_file = pack_dir / "custom_wife_reverse_cowgirl_0.png"
        fc_file = pack_dir / "custom_wife_cowgirl_0.png"
        if rc_file.exists() and not fc_file.exists():
            _alias_strip(rc_file, fc_file, 10, 11)
        elif fc_file.exists() and not rc_file.exists():
            _alias_strip(fc_file, rc_file, 11, 10)

        # Ensure portrait alias exists for ModRoom
        p_std = pack_dir / "custom_portrait.png"
        p_mod = pack_dir / "custom_wife_portrait_0.png"
        if p_std.exists() and not p_mod.exists():
            shutil.copyfile(str(p_std), str(p_mod))
        if res.skipped and not res.converted:
            res.status = "skipped"
            return res
        if res.skipped:
            res.status = "partial"
    _write_descriptor(pack_dir, kind, target, name, res)
    if target == "modroom":
        missing = modroom_missing(pack_dir, kind)
        if missing:
            res.status = "skipped"
            res.notes.append("ModRoom V3.3 needs the " + ", ".join(m for m, _ in MODROOM_NEEDS[kind]) + " sprites; missing: " + ", ".join(missing))
    if kind in ("futa", "wife"):
        res.notes.extend(pack_notes(pack_dir, kind, "modern"))  # what ModRoom / Deeproom modern will load
    return res
