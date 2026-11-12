#!/usr/bin/env python3
"""
ModRoom to WB 1.5 Converter v1.0
-------------------------------------------------------------------------------
Converts ModRoom / Deeproom 1.4 custom mods (custom_futas, custom_wives,
custom_bedrooms) into Wife's Bedroom v1.5's unified custom/ architecture:
  - custom/<character_name>/custom_data.futa   (Lovers)
  - custom/<character_name>/custom_data.spouse (Partners / Spouses)
  - custom/<bedroom_name>/custom_data.bedroom   (Room Backgrounds)

Features:
  - Multi-Input & Individual custom_* Folder Ingestion: Accepts individual
    category folders (custom_futas, custom_wives, custom_bedrooms), multiple
    custom_* folders dragged together, full ModRoom game folders, single character
    packs, or mod .zip archives.
  - v1.5 Header Synthesis: Guarantees every converted mod has the appropriate
    custom_data.futa, custom_data.spouse, or custom_data.bedroom header required
    by Wife's Bedroom v1.5's native engine.
  - Sprite Parity Normalization: Bridges legacy Deeproom sprite filenames
    (e.g., custom_wife_portrait_0.png -> custom_portrait.png,
    custom_wife_mating_press.png -> custom_mating_press.png) for 100% v1.5 compatibility.
  - File Filter: Strips raw art project files (.aseprite, .clip, .pdn, .kra, .zip)
    and backup files (.bak, ~) for clean, lightweight game-ready packs.
  - Manifest Generation: Generates clean _manifest.txt files for mobile & PC compatibility.
  - Destination Selection: Export to output/custom/ or merge directly
    into an existing Wife's Bedroom v1.5 installation.
-------------------------------------------------------------------------------
"""

import sys
import os
import re
import shutil
import zipfile
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Union

VALID_EXTENSIONS = {
    ".png", ".ogg", ".wav", ".mp3", ".json",
    ".futa", ".spouse", ".wife", ".bedroom",
    ".ini", ".txt", ".jpg", ".jpeg", ".gif", ".webp"
}

IGNORED_PROJECT_EXTENSIONS = {
    ".aseprite", ".ase", ".clip", ".pdn", ".kra",
    ".psd", ".xcf", ".blend", ".zip", ".rar", ".7z",
    ".bak", ".tmp"
}

def sanitize_name(name: str) -> str:
    """Sanitizes names into clean, lowercase filesystem and manifest-safe identifiers."""
    clean = re.sub(r'[\/:*?"<>|]', "_", str(name)).strip()
    clean = clean.lower()
    clean = re.sub(r'\s+', '_', clean)
    clean = re.sub(r'_+', '_', clean).strip('_')
    return clean or "unnamed_mod"

def extract_pack_display_name(pack_path: Path) -> str:
    """Extracts clean display name from internal INI files or folder name."""
    for ini_file in pack_path.glob("*.ini"):
        if ini_file.is_file():
            try:
                content = ini_file.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"^\s*name\s*=\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
                if m:
                    extracted = m.group(1).strip()
                    extracted = re.sub(r'[\/:*?"<>|]', "", extracted).strip()
                    if extracted and len(extracted) >= 2:
                        return extracted
            except Exception:
                pass

    for data_file in pack_path.glob("custom_data.*"):
        if data_file.is_file():
            try:
                content = data_file.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"^\s*name\s*=\s*(.+)$", content, re.MULTILINE | re.IGNORECASE)
                if m:
                    extracted = m.group(1).strip()
                    extracted = re.sub(r'[\/:*?"<>|]', "", extracted).strip()
                    if extracted and len(extracted) >= 2:
                        return extracted
            except Exception:
                pass

    return pack_path.name

def determine_modroom_category(pack_path: Path, parent_hint: Optional[str] = None) -> str:
    """
    Identifies whether a ModRoom pack is a Lover (Futa), Partner (Wife),
    or Bedroom based on location or data headers.
    """
    if parent_hint in ["custom_futas", "custom_wives", "custom_bedrooms"]:
        return parent_hint

    p_str = str(pack_path).lower()
    if "custom_futas" in p_str or "futa" in pack_path.name.lower():
        return "custom_futas"
    if "custom_wives" in p_str or "wife" in pack_path.name.lower() or "partner" in pack_path.name.lower():
        return "custom_wives"
    if "custom_bedrooms" in p_str or "bedroom" in pack_path.name.lower() or "background" in pack_path.name.lower():
        return "custom_bedrooms"

    if (pack_path / "custom_data.futa").exists():
        return "custom_futas"
    if (pack_path / "custom_data.spouse").exists() or (pack_path / "custom_data.wife").exists() or (pack_path / "custom_wife.ini").exists():
        return "custom_wives"
    if (pack_path / "custom_data.bedroom").exists() or (pack_path / "custom_background.png").exists():
        return "custom_bedrooms"

    return "custom_futas"

def write_v15_manifests(custom_root: Path) -> int:
    """Generates clean _manifest.txt files for the unified custom/ directory and all packs."""
    manifest_count = 0
    if not custom_root.is_dir():
        return 0

    top_dirs = sorted([d.name for d in custom_root.iterdir() if d.is_dir() and not d.name.startswith(".")])
    if top_dirs:
        (custom_root / "_manifest.txt").write_text("\n".join(top_dirs) + "\n", encoding="utf-8")
        manifest_count += 1

    for pack_dir in custom_root.iterdir():
        if pack_dir.is_dir() and not pack_dir.name.startswith("."):
            for root, dirs, files in os.walk(pack_dir):
                clean_dirs = sorted([d for d in dirs if not d.startswith(".") and d != "__pycache__"])
                clean_files = sorted([f for f in files if Path(f).suffix.lower() in VALID_EXTENSIONS and f != "_manifest.txt" and not f.startswith(".") and not f.endswith("~")])
                entries = clean_dirs + clean_files
                if entries:
                    (Path(root) / "_manifest.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")
                    manifest_count += 1

    return manifest_count

def convert_modroom_to_15(sources: Union[Path, List[Path]], dest_dir: Path, clean_dest: bool = False, verbose: bool = True) -> Dict[str, int]:
    """
    Extracts ModRoom 1.4 custom mods (including individual custom_* folders)
    and converts them into unified v1.5 custom/ architecture.
    Returns summary statistics dictionary.
    """
    stats = {
        "lovers_converted": 0,
        "partners_converted": 0,
        "bedrooms_converted": 0,
        "files_copied": 0,
        "bloat_skipped": 0,
        "manifests_generated": 0
    }

    if isinstance(sources, Path):
        source_paths = [sources]
    else:
        source_paths = list(sources)

    dest_dir = dest_dir.resolve()
    target_custom = dest_dir if dest_dir.name.lower() == "custom" else (dest_dir / "custom")

    if clean_dest and target_custom.exists():
        shutil.rmtree(target_custom)

    target_custom.mkdir(parents=True, exist_ok=True)

    temp_dirs_to_clean: List[Path] = []
    packs_to_convert: List[Tuple[Path, str]] = []

    for s_path in source_paths:
        s_res = s_path.resolve()
        if not s_res.exists():
            continue

        if s_res.is_file() and s_res.suffix.lower() == ".zip":
            import tempfile
            extracted_temp = Path(tempfile.mkdtemp(prefix="mr_to_15_conv_"))
            temp_dirs_to_clean.append(extracted_temp)
            if verbose:
                print(f"[*] Unpacking source archive: {s_res.name}...")
            with zipfile.ZipFile(s_res, 'r') as z:
                z.extractall(extracted_temp)
            search_root = extracted_temp
        else:
            search_root = s_res

        # Check if the folder is an individual category directory (custom_futas, custom_wives, custom_bedrooms)
        cat_direct = None
        s_lower = search_root.name.lower()
        if s_lower in ["custom_futas", "custom_wives", "custom_bedrooms"]:
            cat_direct = s_lower

        if cat_direct:
            if verbose:
                print(f"[*] Ingesting individual category directory: {search_root.name} ({cat_direct})")
            for item in sorted(search_root.iterdir()):
                if item.is_dir() and not item.name.startswith("."):
                    packs_to_convert.append((item, cat_direct))
        else:
            # Check for standard subdirectories inside search_root
            found_sub = False
            for cat in ["custom_futas", "custom_wives", "custom_bedrooms"]:
                cat_dir = search_root / cat
                if cat_dir.is_dir():
                    found_sub = True
                    for item in sorted(cat_dir.iterdir()):
                        if item.is_dir() and not item.name.startswith("."):
                            packs_to_convert.append((item, cat))

            if not found_sub:
                if any(search_root.glob("custom_data.*")) or (search_root / "custom_portrait.png").exists() or (search_root / "custom_background.png").exists():
                    cat = determine_modroom_category(search_root)
                    packs_to_convert.append((search_root, cat))
                else:
                    for item in sorted(search_root.iterdir()):
                        if item.is_dir() and not item.name.startswith("."):
                            cat = determine_modroom_category(item)
                            packs_to_convert.append((item, cat))

    if verbose:
        print(f"[*] Discovered {len(packs_to_convert)} ModRoom pack(s) across all sources.")

    used_names: Set[str] = set()

    for pack_path, cat in packs_to_convert:
        display_name = extract_pack_display_name(pack_path)
        clean_name = sanitize_name(display_name)

        if clean_name in used_names:
            suffix_tag = "futa" if cat == "custom_futas" else ("wife" if cat == "custom_wives" else "room")
            clean_name = f"{clean_name}_{suffix_tag}"
            if clean_name in used_names:
                clean_name = f"{clean_name}_{sanitize_name(pack_path.name)}"
        used_names.add(clean_name)

        out_pack_dir = target_custom / clean_name
        out_pack_dir.mkdir(parents=True, exist_ok=True)

        copied_for_pack = 0
        has_header = False

        for root, dirs, files in os.walk(pack_path):
            rel_p = Path(root).relative_to(pack_path)
            target_sub = out_pack_dir / rel_p
            target_sub.mkdir(parents=True, exist_ok=True)

            for f in files:
                fpath = Path(root) / f
                ext = fpath.suffix.lower()
                fname_lower = fpath.name.lower()

                if ext in IGNORED_PROJECT_EXTENSIONS or fpath.name.startswith(".") or fpath.name.endswith("~"):
                    stats["bloat_skipped"] += 1
                    continue

                if ext in VALID_EXTENSIONS and fname_lower != "_manifest.txt":
                    dest_file = target_sub / fname_lower
                    shutil.copy2(fpath, dest_file)
                    stats["files_copied"] += 1
                    copied_for_pack += 1

                    if fname_lower in ["custom_data.futa", "custom_data.spouse", "custom_data.bedroom"]:
                        has_header = True

        # v1.5 Sprite Parity Normalization for Wives/Partners
        if cat == "custom_wives":
            # If partner has custom_wife_portrait_0.png but not custom_portrait.png
            p0 = out_pack_dir / "custom_wife_portrait_0.png"
            cp = out_pack_dir / "custom_portrait.png"
            if p0.exists() and not cp.exists():
                shutil.copy2(p0, cp)
                stats["files_copied"] += 1

            # If partner has custom_wife_mating_press.png but not custom_mating_press.png
            mp = out_pack_dir / "custom_wife_mating_press.png"
            cmp = out_pack_dir / "custom_mating_press.png"
            if mp.exists() and not cmp.exists():
                shutil.copy2(mp, cmp)
                stats["files_copied"] += 1

        # v1.5 Header Synthesis if missing
        if not has_header:
            header_name = "custom_data.futa" if cat == "custom_futas" else ("custom_data.spouse" if cat == "custom_wives" else "custom_data.bedroom")
            dest_header = out_pack_dir / header_name

            # Check if an existing INI can be used as the header
            found_ini = list(out_pack_dir.glob("*.ini"))
            if found_ini:
                shutil.copy2(found_ini[0], dest_header)
            else:
                default_content = f"[info]\nname={display_name}\nauthor=ModRoom\ndesc=Converted from ModRoom 1.4\n"
                dest_header.write_text(default_content, encoding="utf-8")
            stats["files_copied"] += 1

        if cat == "custom_futas":
            stats["lovers_converted"] += 1
            tag = "Lover"
        elif cat == "custom_wives":
            stats["partners_converted"] += 1
            tag = "Partner"
        else:
            stats["bedrooms_converted"] += 1
            tag = "Bedroom"

        if verbose:
            print(f"[+] Converted {tag:7s}: {pack_path.name:25s} -> custom/{clean_name} ({copied_for_pack} files)")

    if verbose:
        print("[*] Generating v1.5 _manifest.txt index files...")
    stats["manifests_generated"] += write_v15_manifests(target_custom)

    for tmp_d in temp_dirs_to_clean:
        if tmp_d.exists():
            shutil.rmtree(tmp_d, ignore_errors=True)

    return stats

def main():
    if sys.version_info < (3, 8):
        print("[!] Error: Python 3.8 or higher is required. Please update Python.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Convert ModRoom / Deeproom 1.4 mods into Wife's Bedroom v1.5 custom architecture.")
    parser.add_argument("inputs", nargs="*", help="Path(s) to ModRoom game folder, individual custom_* directories, character packs, or mod .zip archives.")
    parser.add_argument("-d", "--dest", help="Destination directory (v1.5 game folder or export folder).")
    parser.add_argument("--clean", action="store_true", help="Clean destination custom/ folder before converting.")
    parser.add_argument("-y", "--yes", action="store_true", help="Non-interactive execution (accept defaults).")
    args = parser.parse_args()

    tool_dir = Path(__file__).resolve().parent
    input_dir = tool_dir / "input"
    output_dir = tool_dir / "output" / "custom"

    print("=" * 70)
    print("      MODROOM TO WB 1.5 MOD CONVERTER v1.0")
    print("=" * 70)

    source_paths = []
    if args.inputs:
        for p in args.inputs:
            cand = Path(p).resolve()
            if cand.exists():
                source_paths.append(cand)

    if not source_paths:
        if input_dir.is_dir():
            for item in input_dir.iterdir():
                if item.name.startswith("."):
                    continue
                if item.is_dir() or item.suffix.lower() == ".zip":
                    source_paths.append(item.resolve())

    if not source_paths:
        if not args.yes and sys.stdin and sys.stdin.isatty():
            try:
                user_in = input("Enter path(s) to ModRoom game folder, custom_* directories, or .zip: ").strip().strip('"').strip("'")
                if user_in and Path(user_in).exists():
                    source_paths = [Path(user_in).resolve()]
            except Exception:
                pass

    if not source_paths:
        print("[!] Error: No valid ModRoom mod folder or .zip archive provided.")
        print("    Please drag your mod folder(s) or custom_* directories onto Convert_ModRoom_to_1.5.bat")
        print("    or place your files inside the input/ folder.")
        sys.exit(1)

    dest_dir = Path(args.dest).resolve() if args.dest else output_dir

    print(f"[*] Sources ({len(source_paths)} item(s)):")
    for s in source_paths:
        print(f"    - {s}")
    print(f"[*] Destination : {dest_dir}\n")

    stats = convert_modroom_to_15(source_paths, dest_dir, clean_dest=args.clean, verbose=True)

    print("\n" + "=" * 70)
    print("CONVERSION COMPLETE - SUMMARY REPORT")
    print("=" * 70)
    print(f"  Lovers Converted (custom_data.futa)   : {stats['lovers_converted']}")
    print(f"  Partners Converted (custom_data.spouse): {stats['partners_converted']}")
    print(f"  Bedrooms Converted (custom_data.bedroom): {stats['bedrooms_converted']}")
    print(f"  Total Assets Integrated               : {stats['files_copied']}")
    print(f"  Raw Art Project Files Stripped        : {stats['bloat_skipped']}")
    print(f"  Manifest Indexes Generated            : {stats['manifests_generated']}")
    print("-" * 70)
    print(f"[+] Converted v1.5 mods ready at:\n    {dest_dir}")
    print("=" * 70)

if __name__ == "__main__":
    main()
