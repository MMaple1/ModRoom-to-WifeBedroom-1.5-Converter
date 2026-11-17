# Modded to WB 1.5 Mod Converter v1.2

Converts **FutasRoom / ModRoom v3.3 / Deeproom 4.0.3 Kiwami / Vanilla v1.2** custom mods (from `custom_stuff/`, `custom_futas/`, `custom_wives/`, `custom_bedrooms/`, or loose folders) into the unified **Wife's Bedroom v1.5** `custom/` layout:

- `custom/<name>/custom_data.futa` (lovers)
- `custom/<name>/custom_data.spouse` (partners)
- `custom/<name>/custom_data.bedroom` (bedrooms)

Standard library only (Python 3.8 or newer). No Pillow.

---

## Start here (the short version)

**What it does:** takes character mods made for ModRoom, Deeproom or FutasRoom and turns them into the single `custom` folder format the original Wife's Bedroom v1.5 reads.

1. Make sure **Python** is installed (free from python.org; tick *Add python.exe to PATH* when installing).
2. **Drag your mod folder (or its `.zip`) onto `Convert_to_WB_1.5.bat`.**
3. A black window opens. Press **Enter** every time it asks a question; the default answers are fine.
4. When it says it is finished, press any key to close the window. Your converted mods are in **`output/custom`** next to the `.bat` file; copy that folder into your Wife's Bedroom v1.5 game folder.

**If something goes wrong:** open `output/conversion_report.md` (any text editor works). It lists every character and says what happened to it and why. *Skipped* means the character was left out on purpose, with the reason beside it. Many ModRoom characters cannot be converted exactly because the two games cut their animations differently; answer **y** to the "approximately" question if you would rather have them converted with some frames dropped.

The rest of this page is for people who want the details.

---

## Quick start

1. Drag your mod folder (or a `.zip`) onto **`Convert_to_WB_1.5.bat`**, or put it in `input/`.
2. Press **Enter** to accept the defaults.
3. The converted packs are in **`output/custom/`** and a per-pack **`output/conversion_report.md`** says what was converted exactly, padded, approximated or skipped.

Command line: `python Modded_to_WB_1.5.py [-d DEST] [--clean] [--approximate] [--dry-run] [-y] INPUT...`

---

## What converts, and how exactly

The two pack formats do not only differ in file names: a strip is cut into a different number of frames.

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

(Frames are usually 160 px wide and portrait frames 128 px, but the games cut a strip into a fixed number of frames whatever its width, so high-res packs (e.g. 256 px portraits, 220 px mating-press frames) convert the same way. The lover's standard cowgirl strip is 5 frames, or 7 when it is 7 frames of 160 px. A strip whose width does not divide into its frame count is reported and left as it is.) Renaming a strip without changing its frame count produces a mis-cut sprite, so the converter does not do that:

| Source | Result |
|---|---|
| **Standard-format packs** (Deeproom `.spouse` / `.futa`, v1.5 style) | Copied exactly. The descriptor gets any missing `[info]` keys. Status **ok**. |
| **Modern / ModRoom packs** (`custom_data.wife`, `custom_*_0.png`) | Only what is exact is converted: a strip that already has v1.5's frame count is renamed, and the partner X-ray (3 to 4 frames, a pad: a blank frame is added) is converted. Other strips are **not converted** because v1.5 cannot cut them; the pack is **partial**, or **skipped** when nothing converts. |
| Same, with **`--approximate`** (the converter also asks when you run it interactively) | Frames are dropped so every strip is cut correctly. For three strips the frames to keep were **learned from packs that ship both formats**: lover mating press 24 to 9 keeps modern frames 0-7 and 19, lover cowgirl 19 to 5 keeps 0, 1, 2, 14 and 17, partner mating press 5 to 4 keeps 0-3. Every other strip keeps its first N frames, and portraits are layered face strips that do not map frame for frame, so check them. Status **approximate**. |
| Bedrooms | Copied; `background.png` / `custom_background.png` aliased. |

Everything left over from the other format (`_0.png` strips, `custom_data.wife`) is removed from the output, so each pack ships **one descriptor and one set of names**.

Descriptor conversion only **adds** keys and never changes a value; line endings, BOM and unknown lines are preserved. `[info]` gets `name` (from the folder name, clamped by the game at 36 characters), `desc` and `author` when absent.

---

## Safety

- **Staging.** Packs are converted in a temporary folder; the destination is only touched once at least one pack was produced. `--clean` removes the old `custom/` at that point, not before.
- **No overwriting, no piling up of copies.** Running the converter again into the same folder skips packs that are already there unchanged. A pack with the same name but different content is added next to the old one with the tag that tells them apart (or `_2` as a last resort).
- **`--dry-run`** converts into a temporary folder, writes only the report, and leaves the destination alone.
- **Zip files** are checked for paths that would write outside the temporary folder; an unsafe archive is skipped.
- **Duplicates** (same character found twice) are skipped and listed in the report. Nothing is copied into a `!duplicates` folder any more.

---

## Other features

- **Real-Time Visual Progress Bar**: Displays dynamic percentage and current character pack name during batch conversions so the terminal never appears stalled.
- **Interactive Approximate Gating**: Lossy frame reduction is gated behind an interactive `[y/N]` prompt (defaulting safely to No) and `--no-approximate` / `--approximate` CLI flags.
- **Bidirectional Descriptor Mapping**:
  - `[xray] origin_x / origin_y` or `[sprite] xray_offset_y` -> `[sprite] xray_x / xray_y`
  - `[deepthroat] origin_y` -> `[sprite] deepthroat_origin_y`
  - `[condom] condom_y_mpress / condom_y_cowgirls` -> `[sprite] condom_y / standing_condom_y`
- **Duplicate Quarantine Category Isolation**: `custom_futas` (Lovers/Tops) and `custom_wives` (Partners/Bottoms) are strictly isolated and never match as duplicates. Bypasses generic placeholder names (`"example"`, `"partner"`, `"wife"`) in Tier 1 duplicate clustering.
- **Container unwrapping**: finds characters inside Deeproom's `custom_stuff/` and skips `Templates/`, `Ball Clench Stuff/`, `Custom Sperm/`, `texture_packs/`.
- **Loose portrait mapping**: a single unnumbered `*portrait*.png` becomes `custom_portrait.png` when a pack has none (never an `_alt` or `_0` strip).
- **Audio and SFX folders** are copied as they are.
- **Raw art files** (`.aseprite`, `.psd`, `.clip`, ...) are not copied.
- **`_manifest.txt`** index files are written, sorted alphabetically.

---

## Tests and the shared module

`python -m unittest discover -s tests` runs the tests (conversion core, PNG pad/crop, descriptor rules, ModRoom's rules, and end-to-end runs on synthetic packs).

The conversion core is `core/wbconv.py`. **The other converter (`WB_1.5_to_Modded`) carries an identical copy**; change both together.

## Limits

- Modern-format strips cannot be turned into v1.5 strips exactly, because the formats cut animations differently; use `--approximate` and check the characters in game (see the report). The learned frame maps come from small samples (4 lover packs, 10 partner packs that carry both formats), so they are a best estimate, not a guarantee.
- The 17-frame modern portrait is a layered face strip and is not converted to the 10-frame layout without `--approximate`.
- Nothing here was tested in the game; the output files were checked for frame counts, descriptors and structure.
