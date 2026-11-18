# Changelog: Modded to WB 1.5 Mod Converter

All notable changes to the **Modded to WB 1.5 Mod Converter** tool are documented in this file.

---

## [Version 1.2.1] - 2026-11-17

### Fixes
- **Partner deepthroat height.** A Deeproom partner's `[deepthroat] origin_y` was copied to v1.5's `[sprite] deepthroat_origin_y` unchanged, but Deeproom draws partner deepthroat 70 px higher than v1.5, so the value now gets +70. Packs without a `[deepthroat]` block get no value (v1.5 uses its own default).

---

## [Version 1.2.0] - 2026-11-16

### Highlights
- **No more `_2` copies.** Converting again into a folder that already holds a pack no longer makes a second numbered copy: an unchanged pack is skipped (generated `_manifest.txt` files are ignored in the comparison). Packs that share a display name keep the tag from their folder name (`astolfo_(naked)`) instead of a doubled or numbered name.
- **Robustness.** Pack folder names are made filesystem-safe (a name that crashed the run with WinError 123 is handled, with a fallback to the pack folder name or a hash); a corrupt PNG no longer aborts the whole conversion; a folder that fails to copy is not reported as written; a stray non-folder input is skipped; `--no-approximate` is honoured and the approximate question is asked once. The README starts with a plain-language quick guide.
- Strips are no longer renamed verbatim between formats: ModRoom and standard strips are cut into different numbers of frames (for example partner mating press 5 vs 4, lover mating press 24 vs 9), so a renamed strip was mis-cut by the game. Standard-format packs now convert exactly; modern/ModRoom packs convert only what is exact or safe, or with `--approximate`, and the rest is reported.
- One descriptor per pack (`custom_data.spouse` / `.futa`); `custom_data.wife` and `_0.png` leftovers are removed.

### Added
- **Learned frame maps for `--approximate`** (`FRAME_MAPS` in `core/wbconv.py`): found by comparing the frames of community packs that ship both formats for the same character. Lover mating press 24 to 9 keeps modern frames 0-7 and 19, lover cowgirl 19 to 5 keeps 0, 1, 2, 14, 17, partner mating press 5 to 4 keeps 0-3; other strips keep their first N frames and portraits are never mapped. Small samples (4 and 10 packs), reported as approximate.
- **Shared, tested conversion core (`core/wbconv.py`)**, identical in both converters, standard library only: PNG reading/writing with pad and crop (replaces Pillow), the frame-count tables measured from thousands of packs, descriptor conversion that only adds keys, ModRoom V3.3's admission rules, safe zip extraction and a conversion report.
- **Staged output.** Packs are converted in a temporary folder and published only if at least one was produced. `--clean` no longer empties the destination before anything has been found, and merging never overwrites an existing pack (`name_2`).
- **`--dry-run`** (report only) and **`--approximate`** (keep the first N frames where frame counts differ), and an `output/conversion_report.md` listing every pack as ok / padded / approximate / partial / skipped with the reason.
- **Safe zip extraction** (paths that would escape the temporary folder are rejected) and temporary folders are always removed.
- **Duplicate packs are skipped and listed, not copied** into a `!duplicates` folder.
- Tests: `python -m unittest discover -s tests`.

### Changed
- Interactive runs ask whether to convert ModRoom-format strips approximately (default no); `-y` keeps it off unless `--approximate` is given.
- A strip that already has v1.5's frame count is renamed; the partner X-ray (3 to 4 frames) is padded (a blank frame is added). Forward and reverse cowgirl are no longer copied over each other.
- The loose-portrait fallback never picks an `_alt` or `_0` strip.
- Fallback scan of a `custom/` folder resolves each pack's category instead of treating it as a bedroom.

### Fixed
- `hashlib` was used but never imported, which silently switched off the identical-asset duplicate check.
- `[info]` / `[sprite]` handling no longer rewrites or appends blindly (a duplicate `[sprite]` header and a destructive regex over the whole descriptor are gone).
- The error message named a batch file that does not exist.

## [Version 1.1.0] - 2026-11-13

### Highlights
- Implementation of the **3-Tier Duplicate Detection & Quarantine Pipeline** preventing duplicate variants from polluting `custom/`.
- Implementation of automated **`[info]` Section Synthesis & Fallbacks** guaranteeing 100% compliance with Wife's Bedroom v1.5's Steam Workshop format.
- Recursive multi-depth mod pack discovery engine.
- Intelligent character name sanitization with 36-character UI card clamping.
- Description and author fallback injection (`\Not Found\`).

### Added
- **Deeproom 4.0.3 Kiwami Container & Pack Normalization**:
  * Automatic unwrapping of the new `custom_stuff/` directory structure, discovering all Lovers, Partners, and Bedrooms inside `custom_stuff/custom_futas`, `custom_wives`, `custom_bedrooms`.
  * Filters out non-mod template and asset utility directories (`Templates`, `texture_packs`, `Ball Clench Stuff`, `Custom Sperm`).
  * Full support for `custom_data.wife` in addition to `custom_data.spouse` and `custom_data.futa`.
  * Sprite parity normalization maps `custom_futa_deepthroat_0.png`, `custom_futa_xray_0.png`, `custom_wife_xray_0.png`, etc., to unified v1.5 sprite equivalents (`custom_deepthroat.png`, `custom_xray.png`).
  * Guaranteed `[info]` compliance via `amend_v15_info_section` while 100% preserving Deeproom 4.0.3 rich INI sections (`[personality]`, `[gender]`, `[condom]`, `[colors]`, `[stats_alt_*]`, pose origins).
- **3-Tier Cross-Folder & Multi-Content Duplicate Detection Engine**:
  * Detects duplicates across `custom/` and category subfolders (`custom_wives/`, `custom_futas/`, `custom_bedrooms/`).
  * Deduplicates bedrooms, audio/SFX, and dialogue packs.
  * Isolates redundant duplicates into **`output/!duplicates/`**.
  * Catches exact slug collisions, copy tags (`- Copy`, ` (1)`), and internal descriptor name matches (Tier 1).
  * Fingerprints character portraits and mating press sheets via SHA-256 hashing (Tier 2).
  * Canonical scoring tie-breaker isolates inferior duplicate copies into `output/!duplicates/` and writes `DUPLICATES_REPORT.txt` (Tier 3).
  * Added `--quarantine-duplicates` (default True) and `--no-quarantine-duplicates` CLI flags.
- **Descriptor `[info]` Section Synthesis (`amend_v15_info_section`)**:
  - Automatically inspects and amends every converted character and bedroom pack descriptor (`custom_data.futa`, `custom_data.spouse`, `custom_data.bedroom`, and loose `*.futa`, `*.spouse`, `*.bedroom`).
  - Ensures all three required header keys (`name=`, `desc=`, `author=`) are present under a valid `[info]` block.
- **Character Name Sanitization**:
  - Extracts clean character names from folder names.
  - Strips community and version tags (e.g. `(COMM)`, `(3.5)`, `[1.4]`, `!`, `#`).
  - Applies title-casing and clamps long names cleanly at **36 characters** with ellipsis (`...`) to prevent UI card text overflow.
- **Fallback Strings**:
  - Injects `desc="\Not Found\"` if description is missing or a generic placeholder, while preserving genuine descriptions.
  - Injects `author="\Not Found\"` if author is missing or a generic placeholder, while preserving genuine author credits.
- **Recursive Pack Discovery Engine (`discover_all_packs`)**:
  - Traverses nested subdirectories, multi-pack bundles, and extracted zip folders without early-exit limitations.
- **Workshop Numeric ID Resolution**:
  - Converts raw numeric Steam IDs (e.g. `3821177370`) into human-readable character names using internal INI metadata.

### Changed & Improved
- **Bi-Directional Filename Normalization**:
  - Seamlessly bridges legacy `_0.png` suffixes (`custom_futa_portrait_0.png`, `custom_wife_portrait_0.png`) to standard unnumbered v1.5 names.
- **Project Bloat Stripping**:
  - Filters out raw art files (`.aseprite`, `.clip`, `.psd`, `.blend`, `.bak`).
- **Clean Output Option**:
  - Added `--clean` flag to wipe previous conversion output before building.

---

## [Version 1.0.0] - Baseline Release

### Features
- Initial release of the ModRoom to WB 1.5 conversion tool.
- Category consolidation from `custom_futas/`, `custom_wives/`, `custom_bedrooms/` into unified `custom/`.
- Basic v1.5 `_manifest.txt` generation.
