# Modded to WB 1.5 Mod Converter

This converter takes character and room mods made for ModRoom, Deeproom, or FutasRoom and turns them into the unified `custom` folder format used by the original Wife's Bedroom v1.5.

## Start here

1. Make sure Python is installed (free from python.org; check the box to add Python to PATH).
2. Drag your mod folder (or `.zip` file) onto `Convert_to_WB_1.5.bat`, or place it in the `input/` folder.
   If you start the `.bat` without dropping anything, it uses the `input/` folder, or asks for a path if that is empty.
3. A command window opens. Press Enter for each question to use the recommended defaults.
4. When finished, press any key to close the window. Converted mods will be in `output/custom/`. Copy that folder into your Wife's Bedroom v1.5 game directory.

**Troubleshooting:** Open `output/conversion_report.md` in any text editor. It lists every character and notes whether it was converted, padded, approximated, or skipped. Items marked *skipped* were excluded intentionally (with a reason provided). Because ModRoom animations use different frame counts, many characters cannot convert identically unless you choose approximate mode.

## The questions it asks

- **Approximate mode (`[y/N]`):** Asks whether to convert strips whose frame counts differ by dropping extra frames. The default is **No** (`N`), which converts safely without losing frames.
- **Skip duplicate packs (`[Y/n]`):** If the same character appears more than once, only the best copy is converted; the others are listed in the report. The default is **Yes**. Nothing in your mod folder is changed.

## What you get

- **`output/custom/`**: The converted character and bedroom folders ready for Wife's Bedroom v1.5.
- **`output/conversion_report.md`**: A detailed report showing what was converted exactly, padded, approximated, or skipped.
- **Dry run output**: If using `--dry-run`, files are processed in a temporary space and only the conversion report is written, leaving destination folders completely untouched.

## Command line

```bash
python Modded_to_WB_1.5.py input_folder
python Modded_to_WB_1.5.py -d "C:/Games/WB1.5" -y my_pack.zip
python Modded_to_WB_1.5.py --approximate --clean input_folder
python Modded_to_WB_1.5.py --dry-run input_folder
```

See DETAILS.md for all options.
For full technical details, frame counts and descriptor rules, see `DETAILS.md`.
