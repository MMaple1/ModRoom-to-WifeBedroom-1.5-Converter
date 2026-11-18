# Modded to WB 1.5 Mod Converter v1.2 — Technical Details

Converts **FutasRoom / ModRoom v3.3 / Deeproom 4.0.3 Kiwami / Vanilla v1.2** custom mods (from `custom_stuff/`, `custom_futas/`, `custom_wives/`, `custom_bedrooms/`, or loose folders) into the unified **Wife's Bedroom v1.5** `custom/` layout:

- `custom/<name>/custom_data.futa` (lovers)
- `custom/<name>/custom_data.spouse` (partners)
- `custom/<name>/custom_data.bedroom` (bedrooms)

Standard library only (Python 3.8 or newer). No Pillow.

---

## What Converts and How Exactly

The two pack formats do not only differ in file names: a strip is cut into a different number of frames.

### Frame Count Comparison Table

| Strip | v1.5 / standard names | ModRoom / `_0.png` names |
|---|---|---|
| Lover portrait | 10 frames | 17 |
| Lover mating press | 9 | 24 |
| Lover cowgirl | 5 | 19 |
| Lover X-ray | 3 | 18 |
| Partner portrait | 10 | 17 |
| Partner mating press | 4 | 5 |
| Partner reverse cowgirl | 5 | 10 |
| Partner forward cowgirl | 6 | 11 |
| Partner X-ray | 4 | 3 |

Frames are usually 160 px wide and portrait frames 128 px, but the games cut a strip into a fixed number of frames whatever its width, so high-res packs (e.g. 256 px portraits, 220 px mating-press frames) convert the same way. The lover's standard cowgirl strip is 5 frames, or 7 when it is 7 frames of 160 px. A strip whose width does not divide into its frame count is reported and left as it is. Renaming a strip without changing its frame count produces a mis-cut sprite, so the converter does not do that.

### Format Conversion Rules

| Source | Result |
|---|---|
| **Standard-format packs** (Deeproom `.spouse` / `.futa`, v1.5 style) | Copied exactly. The descriptor gets any missing `[info]` keys. Status **ok**. |
| **Modern / ModRoom packs** (`custom_data.wife`, `custom_*_0.png`) | Only what is exact is converted: a strip that already has v1.5's frame count is renamed, and the partner X-ray (3 to 4 frames, a pad: a blank frame is added) is converted. Other strips are **not converted** because v1.5 cannot cut them; the pack is **partial**, or **skipped** when nothing converts. |
| Same, with **`--approximate`** (the converter also asks when you run it interactively) | Frames are dropped so every strip is cut correctly. For three strips the frames to keep were **learned from packs that ship both formats**: lover mating press 24 to 9 keeps modern frames 0-7 and 19, lover cowgirl 19 to 5 keeps 0, 1, 2, 14 and 17, partner mating press 5 to 4 keeps 0-3. Every other strip keeps its first N frames, and portraits are layered face strips that do not map frame for frame, so check them. Status **approximate**. |
| Bedrooms | Copied; `background.png` / `custom_background.png` aliased. |

Everything left over from the other format (`_0.png` strips, `custom_data.wife`) is removed from the output, so each pack ships **one descriptor and one set of names**.

---

## Descriptor Rules

Descriptor conversion only **adds** keys and never changes a value; line endings, BOM and unknown lines are preserved.
- `[info]` gets `name` (from the folder name, clamped by the game at 36 characters), `desc` and `author` when absent.
- **Bidirectional Descriptor Mapping**:
  - `[xray] origin_x / origin_y` or `[sprite] xray_offset_y` -> `[sprite] xray_x / xray_y`
  - `[deepthroat] origin_y` -> `[sprite] deepthroat_origin_y` + 70 (Deeproom draws partner deepthroat 70 px higher than v1.5; added only when the pack has a `[deepthroat]` block)
  - `[condom] condom_y_mpress / condom_y_cowgirls` -> `[sprite] condom_y / standing_condom_y`

---

## Safety and File Handling

- **Staging.** Packs are converted in a temporary folder; the destination is only touched once at least one pack was produced. `--clean` removes the old `custom/` at that point, not before.
- **No overwriting, no piling up of copies.** Running the converter again into the same folder skips packs that are already there unchanged. A pack with the same name but different content is added next to the old one with the tag that tells them apart (or `_2` as a last resort).
- **`--dry-run`** converts into a temporary folder, writes only the report, and leaves the destination alone.
- **Zip files** are checked for paths that would write outside the temporary folder; an unsafe archive is skipped.
- **Duplicates** (same character found twice) are skipped and listed in the report. Nothing is copied into a `!duplicates` folder any more.
- **Duplicate Quarantine Category Isolation**: `custom_futas` (Lovers/Tops) and `custom_wives` (Partners/Bottoms) are strictly isolated and never match as duplicates. Bypasses generic placeholder names (`"example"`, `"partner"`, `"wife"`) in Tier 1 duplicate clustering.

---

## Additional Features

- **Real-Time Visual Progress Bar**: Displays dynamic percentage and current character pack name during batch conversions so the terminal never appears stalled.
- **Interactive Approximate Gating**: Lossy frame reduction is gated behind an interactive `[y/N]` prompt (defaulting safely to No) and `--no-approximate` / `--approximate` CLI flags.
- **Container unwrapping**: finds characters inside Deeproom's `custom_stuff/` and skips `Templates/`, `Ball Clench Stuff/`, `Custom Sperm/`, `texture_packs/`.
- **Loose portrait mapping**: a single unnumbered `*portrait*.png` becomes `custom_portrait.png` when a pack has none (never an `_alt` or `_0` strip).
- **Audio and SFX folders** are copied as they are.
- **Raw art files** (`.aseprite`, `.psd`, `.clip`, ...) are not copied.
- **`_manifest.txt`** index files are written, sorted alphabetically.

---

## Report Statuses

The conversion report `output/conversion_report.md` tracks items with the following statuses:
- **ok**: Converted exactly or standard-format pack copied cleanly.
- **approximate**: Converted using `--approximate` with dropped/selected frames.
- **partial**: Modern pack where only exact-matching strips or pads could convert without `--approximate`.
- **skipped**: Excluded intentionally (e.g. incompatible strips without approximate mode, duplicate entries, or unsafe zip archives), accompanied by the specific reason.

---

## Full Command-Line Options

```
usage: Modded_to_WB_1.5.py [-h] [-d DEST] [--quarantine-duplicates]
                           [--no-quarantine-duplicates] [--clean]
                           [--approximate] [--no-approximate] [--dry-run] [-y]
                           [inputs ...]

positional arguments:
  inputs                Path(s) to ModRoom game folder, individual custom_*
                        directories, character packs, or mod .zip archives.

options:
  -h, --help            show this help message and exit
  -d DEST, --dest DEST  Destination directory (v1.5 game folder or export
                        folder).
  --quarantine-duplicates
                        Automatically detect and quarantine duplicate custom
                        character/room folders (default: True)
  --no-quarantine-duplicates
                        Disable duplicate custom folder quarantine
  --clean               Clean destination custom/ folder before converting.
  --approximate         Also convert strips whose frame counts differ by
                        dropping frames (first N kept); listed as
                        'approximate' in the report.
  --no-approximate      Disallow lossy frame reduction (default: safe)
  --dry-run             Convert into a temporary folder and write only the
                        report; nothing is written to the destination.
  -y, --yes             Non-interactive execution (accept defaults).
```

---

## Tests and the Shared Module

`python -m unittest discover -s tests` runs the tests (conversion core, PNG pad/crop, descriptor rules, ModRoom's rules, and end-to-end runs on synthetic packs).

The conversion core is `core/wbconv.py`. **Four identical copies exist** (both converters, the WB Mobile Patcher's `wbp/wbconv.py` and the Custom Studio's `backend/wbconv.py`): edit the one in `Modded_to_WB_1.5_Converter_v1.1/core/` and run the patcher's `python tools/sync_wbconv.py` (`--check` only reports).

---

## Limits

- Modern-format strips cannot be turned into v1.5 strips exactly, because the formats cut animations differently; use `--approximate` and check the characters in game (see the report). The learned frame maps come from small samples (4 lover packs, 10 partner packs that carry both formats), so they are a best estimate, not a guarantee.
- The 17-frame modern portrait is a layered face strip and is not converted to the 10-frame layout without `--approximate`.
- Nothing here was tested in the game; the output files were checked for frame counts, descriptors and structure.
