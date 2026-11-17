#!/usr/bin/env python3
"""
Modded to WB 1.5 Converter v1.1
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
import atexit
import hashlib
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / "core"))
import wbconv  # shared, tested conversion core (PNG strips, descriptors, ModRoom rules, safe zip/publish)

# Pack names can contain characters a Windows console cannot encode; never let printing one end the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

VALID_EXTENSIONS = {
    ".png", ".ogg", ".wav", ".mp3", ".json",
    ".futa", ".spouse", ".wife", ".bedroom",
    ".ini", ".jpg", ".jpeg", ".gif", ".webp"
}

IGNORED_PROJECT_EXTENSIONS = {
    ".aseprite", ".ase", ".clip", ".pdn", ".kra",
    ".psd", ".xcf", ".blend", ".zip", ".rar", ".7z",
    ".tar", ".gz", ".bak", ".tmp", ".pdf", ".docx", ".doc"
}

print_progress = wbconv.progress  # shared, throttled bar (kept under the old name)

def sanitize_name(name: str) -> str:
    """Clean, lowercase, filesystem- and manifest-safe identifier (see wbconv.safe_dirname)."""
    return wbconv.safe_dirname(name)

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

NOT_FOUND_STR = "\\Not Found\\"

def clean_folder_name_for_title(folder_name: str, max_len: int = 36) -> str:
    """Cleans a pack folder name into a clean, title-cased display title (clamped to max_len)."""
    s = re.sub(r"^[!#~_\-\s]+", "", folder_name)
    s = re.sub(r"\((COMM|3\.5|1\.4|V1|BS|WIP|Nude|Clothed|Rework)\)", "", s, flags=re.I)
    s = re.sub(r"\[(COMM|3\.5|1\.4|V1|BS|WIP|Nude|Clothed|Rework)\]", "", s, flags=re.I)
    s = re.sub(r'[\\/:*?\"<>|]+', ' ', s)
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split()
    s_title = " ".join(w.capitalize() if not (w.isupper() and len(w) <= 3) else w for w in words)
    if not s_title:
        s_title = folder_name.strip() or "Custom Character"
    if len(s_title) > max_len:
        s_title = s_title[:max_len - 3].rstrip() + "..."
    return s_title

def ensure_info(header_path: Path, folder_name: str):
    """Make sure the descriptor has the [info] keys v1.5 reads. Only absent keys are added; nothing is rewritten."""
    ini = wbconv.Ini(header_path.read_bytes())
    title = clean_folder_name_for_title(folder_name).replace('"', "'")
    ini.add("info", "name", f'"{title}"')
    ini.add("info", "desc", f'"{NOT_FOUND_STR}"')
    ini.add("info", "author", f'"{NOT_FOUND_STR}"')
    if ini.changed:
        header_path.write_bytes(ini.to_bytes())

def compute_file_sha256(path: Path) -> str:
    """Computes SHA-256 hash of a file for exact asset fingerprinting."""
    try:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""

VARIANT_ATTR_TOKENS = {
    "nude", "clothed", "naked", "underwear", "lingerie", "bikini", "bunnysuit",
    "human", "horse", "horsecock", "equine", "knot", "knotted", "diphallia",
    "shiny", "palette", "oral", "bj", "bbw", "milk", "tail", "alt"
}

def extract_variant_tokens(name: str):
    words = set(re.findall(r"[a-zA-Z0-9]+", str(name).lower()))
    return words & VARIANT_ATTR_TOKENS

def normalize_pack_slug(name: str) -> str:
    """Normalizes a folder or character name into a clean comparison slug (Tier 1).
    CRITICAL: Preserves distinguishing attribute tokens (nude, clothed, knot, horse, etc.)
    so distinct variants of the same character are NEVER treated as duplicates."""
    s = re.sub(r"\b(COMM|V\d+(\.\d+)?|WIP|BS)\b", "", name, flags=re.I)
    s = re.sub(r"(\s*-\s*copy(\s*\(\d+\))?|\s*\(\d+\)|_copy(\d+)?|_backup|_old)$", "", s, flags=re.I)
    s = re.sub(r'[\\/:*?\"<>|!#~_.-]+', ' ', s).strip().lower()
    return re.sub(r"\s+", "_", s)

def detect_intrinsic_category(pack_path: Path) -> str:
    """Inspects internal files to determine the true intrinsic category of a pack."""
    try:
        files = {f.name.lower() for f in pack_path.iterdir() if f.is_file()}
        if any(w in files for w in ["custom_data.spouse", "custom_data.wife", "custom_wife.ini"]):
            return "custom_wives"
        if any(w in files for w in ["custom_data.futa", "custom_futa.ini"]):
            return "custom_futas"
        if any(w in files for w in ["custom_data.bedroom", "background.png", "custom_background.png"]):
            return "custom_bedrooms"

        if any("wife" in f for f in files) or any("spouse" in f for f in files) or "custom_cowgirl.png" in files:
            return "custom_wives"
        if any("futa" in f for f in files) or "custom_futa_portrait_0.png" in files:
            return "custom_futas"
        if any("bedroom" in f for f in files) or any("room" in f for f in files):
            return "custom_bedrooms"

        for f in files:
            if f.endswith(".futa"):
                return "custom_futas"
            if f.endswith(".spouse") or f.endswith(".wife"):
                return "custom_wives"
            if f.endswith(".bedroom"):
                return "custom_bedrooms"
    except Exception:
        pass
    return "unknown"

def score_pack_canonical(pack_path: Path, cat: str = "", target_is_v15: bool = False) -> float:
    """Calculates canonical score for duplicate tie-breaking (Tier 3). Higher is preferred."""
    score = 0.0
    valid_exts = {".png", ".ogg", ".wav", ".mp3", ".json", ".futa", ".spouse", ".wife", ".bedroom", ".ini", ".txt"}
    files = [f for f in pack_path.rglob("*") if f.is_file() and f.suffix.lower() in valid_exts]
    score += len(files) * 10.0
    audio_files = [f for f in files if f.suffix.lower() in [".ogg", ".wav", ".mp3"]]
    score += len(audio_files) * 25.0
    file_names = {f.name.lower() for f in files}
    if any("cowgirl" in n for n in file_names):
        score += 30.0
    if any("xray" in n for n in file_names):
        score += 20.0
    name = pack_path.name
    if re.search(r"(\s*-\s*copy|\s*\(\d+\)|_copy|_old|_backup)", name, re.I):
        score -= 50.0
    if name.isdigit() and len(name) >= 7:
        score -= 30.0

    # Category Affinity Bonus & Conflicting Folder Penalty (Ensures wives in custom_wives win over wives in custom_futas)
    intrinsic = detect_intrinsic_category(pack_path)
    if intrinsic != "unknown":
        if cat == intrinsic:
            score += 100.0  # Perfect folder match!
        elif cat == "custom":
            score += 20.0   # Unified format acceptable
        else:
            score -= 100.0  # Severe penalty for misplaced conflicting duplicate!

    # Target Architecture Alignment Bonus
    if target_is_v15 and cat == "custom":
        score += 50.0  # v1.5 prefers unified custom/
    elif not target_is_v15 and cat in ["custom_futas", "custom_wives", "custom_bedrooms"]:
        score += 20.0

    try:
        mtime = max(f.stat().st_mtime for f in files) if files else pack_path.stat().st_mtime
        score += mtime / 1000000000.0
    except Exception:
        pass
    return score

def get_pack_fingerprints(pack_path: Path, cat: str = "") -> dict:
    """Extracts SHA-256 asset fingerprints across characters, bedrooms, SFX/audio, and dialogues (Tier 2)."""
    fps = {}
    try:
        audio_hashes = []
        for f in sorted(pack_path.iterdir()):
            if not f.is_file():
                continue
            fn = f.name.lower()
            ext = f.suffix.lower()
            if fn in ["custom_portrait.png", "custom_futa_portrait_0.png", "custom_wife_portrait_0.png"]:
                fps["portrait"] = compute_file_sha256(f)
            elif fn in ["custom_mating_press.png", "custom_futa_mating_press_0.png", "custom_wife_mating_press_0.png"]:
                fps["mating"] = compute_file_sha256(f)
            elif fn in ["background.png", "custom_background.png"]:
                fps["bg"] = compute_file_sha256(f)
            elif ext in [".ogg", ".wav", ".mp3"] and len(audio_hashes) < 3:
                audio_hashes.append(compute_file_sha256(f))
            elif ext == ".json" and "dialogue" in cat:
                fps["dialogue"] = compute_file_sha256(f)
        if audio_hashes:
            fps["audio_primary"] = audio_hashes[0]
    except Exception:
        pass
    return fps

def is_compatible_category(cat1: str, cat2: str) -> bool:
    """Determines whether two categories can contain duplicate variants (e.g. custom/ vs custom_wives/).
    CRITICAL: custom_futas (Lovers/Tops) and custom_wives (Partners/Bottoms) are distinct gameplay roles
    and must NEVER cluster as duplicates of each other."""
    if cat1 == cat2:
        return True
    if (cat1 == "custom" and cat2 in ["custom_futas", "custom_wives"]) or (cat2 == "custom" and cat1 in ["custom_futas", "custom_wives"]):
        return True
    if (cat1 == "custom" and cat2 == "custom_bedrooms") or (cat2 == "custom" and cat1 == "custom_bedrooms"):
        return True
    if cat1 in {"custom_sounds", "custom_music"} and cat2 in {"custom_sounds", "custom_music"}:
        return True
    if cat1 in {"dialogue", "dialogue_packs", "custom_dialogues"} and cat2 in {"dialogue", "dialogue_packs", "custom_dialogues"}:
        return True
    return False

def quarantine_duplicate_packs(packs_to_convert: list, quarantine_dir: Path, target_is_v15: bool = False, verbose: bool = True):
    """
    3-Tier Cross-Folder & Cross-Category Duplicate Detection & Quarantine Engine:
    Clusters discovered packs across folders/categories, isolates duplicates into '!duplicates', and writes DUPLICATES_REPORT.txt.
    Returns (retained_packs, quarantined_count, list_of_quarantined).
    """
    if len(packs_to_convert) <= 1:
        return packs_to_convert, 0, []

    quarantine_dir = Path(quarantine_dir)

    pack_data = []
    for n_done, (pack_path, cat) in enumerate(packs_to_convert, 1):
        if verbose:
            print_progress(n_done, len(packs_to_convert), prefix="Duplicate check")
        f_slug = normalize_pack_slug(pack_path.name)
        d_name = extract_pack_display_name(pack_path)
        i_slug = normalize_pack_slug(d_name) if d_name else ""
        fps = get_pack_fingerprints(pack_path, cat=cat)
        score = score_pack_canonical(pack_path, cat=cat, target_is_v15=target_is_v15)
        pack_data.append({
            "path": pack_path,
            "cat": cat,
            "folder_slug": f_slug,
            "info_slug": i_slug,
            "fps": fps,
            "score": score
        })

    n = len(pack_data)
    parent = list(range(n))
    def find(i):
        if parent[i] == i: return i
        parent[i] = find(parent[i])
        return parent[i]
    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    pair_reasons = {}
    for i in range(n):
        for j in range(i + 1, n):
            pi = pack_data[i]
            pj = pack_data[j]
            if not is_compatible_category(pi["cat"], pj["cat"]):
                continue

            # Variant Attribute Guard: If two characters have divergent attributes (e.g. nude vs clothed, horse vs knot),
            # they are distinct variants authored for different gameplay preferences and must NEVER be quarantined as duplicates
            v_i = extract_variant_tokens(pi["path"].name) | extract_variant_tokens(pi.get("info_slug", ""))
            v_j = extract_variant_tokens(pj["path"].name) | extract_variant_tokens(pj.get("info_slug", ""))
            if v_i != v_j and (v_i or v_j):
                continue

            is_dup = False
            reason = ""

            # Tier 2: Fingerprint match (SHA-256 of key artwork files)
            # Only identical visual sprites (portrait AND mating press) prove duplicate identity;
            # shared audio or dialogue files must never cause different visual variants to be quarantined
            fps_i, fps_j = pi["fps"], pj["fps"]
            if "mating" in fps_i and "mating" in fps_j and fps_i["mating"] and fps_i["mating"] == fps_j["mating"]:
                if "portrait" in fps_i and "portrait" in fps_j and fps_i["portrait"] and fps_i["portrait"] == fps_j["portrait"]:
                    is_dup = True
                    reason = "Tier 2 Asset Match (Identical portrait & mating sheet SHA-256)"
                elif "portrait" not in fps_i or "portrait" not in fps_j:
                    is_dup = True
                    reason = "Tier 2 Asset Match (Identical mating sheet SHA-256)"
            elif "bg" in fps_i and "bg" in fps_j and fps_i["bg"] and fps_i["bg"] == fps_j["bg"]:
                is_dup = True
                reason = "Tier 2 Asset Match (Identical background image SHA-256)"

            GENERIC_SLUGS = {"example", "custom", "custom_character", "character", "wife", "partner", "futa", "lover", "not_found", "unknown", "unnamed", "none", "new_pack", "template"}
            if not is_dup:
                if pi["folder_slug"] and pi["folder_slug"] == pj["folder_slug"]:
                    is_dup = True
                    reason = f"Tier 1 Name Match (Normalized slug '{pi['folder_slug']}')"
                elif pi["info_slug"] and pi["info_slug"] not in GENERIC_SLUGS and (pi["info_slug"] == pj["folder_slug"] or pi["info_slug"] == pj["info_slug"]):
                    is_dup = True
                    reason = f"Tier 1 Metadata Match (Descriptor [info] name '{pi['info_slug']}')"
                elif pj["info_slug"] and pj["info_slug"] not in GENERIC_SLUGS and pj["info_slug"] == pi["folder_slug"]:
                    is_dup = True
                    reason = f"Tier 1 Metadata Match (Descriptor [info] name '{pj['info_slug']}')"

            if is_dup:
                union(i, j)
                pair_reasons[(min(i, j), max(i, j))] = reason

    clusters = {}
    for i in range(n):
        r = find(i)
        clusters.setdefault(r, []).append(pack_data[i])

    retained_packs = []
    quarantined = []
    quarantined_report_lines = []

    for r, group in clusters.items():
        if len(group) == 1:
            retained_packs.append((group[0]["path"], group[0]["cat"]))
        else:
            group.sort(key=lambda x: x["score"], reverse=True)
            winner = group[0]
            retained_packs.append((winner["path"], winner["cat"]))
            for dup in group[1:]:
                try:
                    quarantined.append((dup["path"], winner["path"]))
                    reason = f"Duplicate of [{winner['cat']}] '{winner['path'].name}' (Score {winner['score']:.1f} vs {dup['score']:.1f})"
                    quarantined_report_lines.append(f"[{dup['cat']}] {dup['path'].name} -> Quarantined (Winner: [{winner['cat']}] {winner['path'].name}) | Reason: {reason}")
                    if verbose:
                        wbconv.say(f"[!] Duplicate Quarantine: Isolated duplicate '[{dup['cat']}] {dup['path'].name}' (Winner: '[{winner['cat']}] {winner['path'].name}').")
                except Exception as m_err:
                    if verbose:
                        wbconv.say(f"[!] Notice: Failed to isolate duplicate '{dup['path'].name}': {m_err}")

    return retained_packs, len(quarantined), quarantined

def convert_modroom_to_15(sources: Union[Path, List[Path]], dest_dir: Path, clean_dest: bool = False, verbose: bool = True, quarantine_duplicates: bool = True, approximate: bool = False, dry_run: bool = False, report=None) -> Dict[str, int]:
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
        "manifests_generated": 0,
        "skipped_packs": 0
    }

    if isinstance(sources, Path):
        source_paths = [sources]
    else:
        source_paths = list(sources)

    dest_dir = dest_dir.resolve()
    final_custom = dest_dir if dest_dir.name.lower() == "custom" else (dest_dir / "custom")
    if report is None:
        report = wbconv.Report("Modded to WB 1.5 conversion report")

    # Convert into a staging folder first: the destination is only touched once at least one pack converted
    staging_root = Path(tempfile.mkdtemp(prefix="mr_to_15_stage_"))
    target_custom = staging_root / "custom"
    target_custom.mkdir(parents=True, exist_ok=True)

    temp_dirs_to_clean: List[Path] = [staging_root]
    atexit.register(lambda: [shutil.rmtree(d, ignore_errors=True) for d in temp_dirs_to_clean])
    packs_to_convert: List[Tuple[Path, str]] = []

    for s_path in source_paths:
        s_res = s_path.resolve()
        if not s_res.exists():
            continue

        if s_res.is_file() and s_res.suffix.lower() == ".zip":
            extracted_temp = Path(tempfile.mkdtemp(prefix="mr_to_15_conv_"))
            temp_dirs_to_clean.append(extracted_temp)
            try:
                with wbconv.Spinner(f"Unpacking {s_res.name}"), zipfile.ZipFile(s_res, 'r') as z:
                    wbconv.safe_extract(z, extracted_temp)
            except (ValueError, zipfile.BadZipFile) as exc:
                print(f"[!] Skipping archive {s_res.name}: {exc}")
                continue
            search_root = extracted_temp
        else:
            search_root = s_res
        if not search_root.is_dir():
            print(f"[!] Skipping {search_root.name}: not a folder or .zip archive")
            continue

        # Non-mod utility directories to ignore
        IGNORED_CONTAINER_NAMES = {
            "templates", "template", "texture_packs", "ball clench stuff",
            "custom sperm", "quarantine", "!duplicates", "__pycache__",
            "custom_music", "custom_sounds", "dialogue", "dialogue_packs"
        }

        # Check if the folder is an individual category directory (custom_futas, custom_wives, custom_bedrooms)
        cat_direct = None
        s_lower = search_root.name.lower()
        if s_lower in ["custom_futas", "custom_wives", "custom_bedrooms"]:
            cat_direct = s_lower

        if cat_direct:
            if verbose:
                print(f"[*] Ingesting individual category directory: {search_root.name} ({cat_direct})")
            for item in sorted(search_root.iterdir()):
                if item.is_dir() and not item.name.startswith(".") and item.name.lower() not in IGNORED_CONTAINER_NAMES:
                    packs_to_convert.append((item, cat_direct))
        else:
            found_sub = False

            # Check for Deeproom 4.0.3 custom_stuff root container
            cs_dir = search_root / "custom_stuff"
            if cs_dir.is_dir():
                for cat in ["custom", "custom_futas", "custom_wives", "custom_bedrooms"]:
                    cat_dir = cs_dir / cat
                    if cat_dir.is_dir():
                        found_sub = True
                        for item in sorted(cat_dir.iterdir()):
                            if item.is_dir() and not item.name.startswith(".") and item.name.lower() not in IGNORED_CONTAINER_NAMES:
                                c = cat if cat != "custom" else determine_modroom_category(item)
                                packs_to_convert.append((item, c))

            # Check for standard subdirectories inside search_root
            if not found_sub:
                for cat in ["custom", "custom_futas", "custom_wives", "custom_bedrooms"]:
                    cat_dir = search_root / cat
                    if cat_dir.is_dir():
                        found_sub = True
                        for item in sorted(cat_dir.iterdir()):
                            if item.is_dir() and not item.name.startswith(".") and item.name.lower() not in IGNORED_CONTAINER_NAMES:
                                packs_to_convert.append((item, cat if cat != "custom" else determine_modroom_category(item)))

            if not found_sub:
                if any(search_root.glob("custom_data.*")) or (search_root / "custom_portrait.png").exists() or (search_root / "custom_background.png").exists():
                    cat = determine_modroom_category(search_root)
                    packs_to_convert.append((search_root, cat))
                else:
                    for item in sorted(search_root.iterdir()):
                        if item.is_dir() and not item.name.startswith(".") and item.name.lower() not in IGNORED_CONTAINER_NAMES:
                            cat = determine_modroom_category(item)
                            packs_to_convert.append((item, cat))

    if verbose:
        print(f"[*] Discovered {len(packs_to_convert)} ModRoom pack(s) across all sources.")

    if quarantine_duplicates:
        q_dir = dest_dir / "!duplicates"  # not created: duplicates are skipped and listed in the conversion report
        packs_to_convert, q_count, q_list = quarantine_duplicate_packs(packs_to_convert, q_dir, target_is_v15=True, verbose=verbose)
        for dup_path, winner_path in q_list:
            report.add(dup_path.name, "?", "v1.5", wbconv.Result("skipped", notes=[f"duplicate of '{winner_path.name}'"]))
        if q_count > 0 and verbose:
            print(f"[+] Duplicate check: skipped {q_count} duplicate pack(s) (nothing is copied or moved; see the conversion report).")
            print(f"[+] Duplicate check: kept {len(packs_to_convert)} unique pack(s).")

    used_names: Set[str] = set()

    for p_idx, (pack_path, cat) in enumerate(packs_to_convert, 1):
        if verbose:
            print_progress(p_idx, len(packs_to_convert), prefix="Converting")
        display_name = extract_pack_display_name(pack_path)
        clean_name = sanitize_name(display_name)

        if clean_name in used_names:
            suffix_tag = "futa" if cat == "custom_futas" else ("wife" if cat == "custom_wives" else "room")
            clean_name = f"{clean_name}_{suffix_tag}"
            clean_name = wbconv.unique_pack_name(clean_name, pack_path.name, used_names)
        used_names.add(clean_name)

        out_pack_dir = wbconv.make_pack_dir(target_custom, clean_name, pack_path.name)  # falls back to the folder name, then a hash, if the OS refuses a name

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

                if ext in IGNORED_PROJECT_EXTENSIONS or (ext == ".txt" and fname_lower != "_manifest.txt") or fpath.name.startswith(".") or fpath.name.endswith("~"):
                    stats["bloat_skipped"] += 1
                    continue

                if (ext in VALID_EXTENSIONS or fname_lower == "_manifest.txt") and fname_lower != "_manifest.txt":
                    dest_file = target_sub / fname_lower
                    shutil.copy2(fpath, dest_file)
                    stats["files_copied"] += 1
                    copied_for_pack += 1

                    if fname_lower in ["custom_data.futa", "custom_data.spouse", "custom_data.wife", "custom_data.bedroom"]:
                        has_header = True

        # Strips and descriptor: shared, tested core (frame counts, one descriptor, no verbatim renames)
        if cat == "custom_bedrooms":
            bg1 = out_pack_dir / "background.png"
            bg2 = out_pack_dir / "custom_background.png"
            if bg1.exists() and not bg2.exists():
                shutil.copy2(bg1, bg2)
                stats["files_copied"] += 1
            elif bg2.exists() and not bg1.exists():
                shutil.copy2(bg2, bg1)
                stats["files_copied"] += 1
            report.add(pack_path.name, "bedroom", "v1.5", wbconv.Result("ok"))
        else:
            kind = "futa" if cat == "custom_futas" else "wife"
            res = wbconv.to_v15(out_pack_dir, kind, clean_folder_name_for_title(display_name), approximate=approximate)
            report.add(pack_path.name, kind, "v1.5", res)
            if res.status == "skipped":
                shutil.rmtree(out_pack_dir, ignore_errors=True)
                stats["skipped_packs"] += 1
                if verbose:
                    wbconv.say(f"[-] Skipped   {kind:7s}: {pack_path.name:25s} ({'; '.join(res.notes + res.skipped)})")
                continue
            if verbose and (res.status != "ok" or res.skipped):
                wbconv.say(f"[~] {res.status:11s}: {pack_path.name} ({'; '.join(res.converted + res.skipped)})")

            # Loose portrait: a single unnumbered *portrait*.png (never an _alt or _0 strip, which have other frame counts)
            if not (out_pack_dir / "custom_portrait.png").exists():
                for f in sorted(out_pack_dir.iterdir()):
                    fl = f.name.lower()
                    if "portrait" in fl and fl.endswith(".png") and "_alt" not in fl and not fl.endswith("_0.png") and fl != "custom_portrait.png":
                        shutil.copy2(f, out_pack_dir / "custom_portrait.png")
                        stats["files_copied"] += 1
                        break

        # Ensure canonical v1.5 header descriptor exists
        target_header_name = "custom_data.futa" if cat == "custom_futas" else ("custom_data.spouse" if cat == "custom_wives" else "custom_data.bedroom")
        dest_header = out_pack_dir / target_header_name

        if not dest_header.exists():
            found_ini = list(out_pack_dir.glob("*.ini"))
            if found_ini:
                shutil.copy2(found_ini[0], dest_header)
            else:
                default_content = f'[info]\nname="{clean_folder_name_for_title(display_name)}"\ndesc="{NOT_FOUND_STR}"\nauthor="{NOT_FOUND_STR}"\n'
                dest_header.write_text(default_content, encoding="utf-8")
            stats["files_copied"] += 1

        # Enforce compliant [info] metadata while preserving all Deeproom 4.0.3 rich sections
        ensure_info(dest_header, display_name)

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
            wbconv.say(f"[+] Converted {tag:7s}: {pack_path.name:25s} -> custom/{clean_name} ({copied_for_pack} files)")

    produced = [p for p in sorted(target_custom.iterdir()) if p.is_dir()]
    if dry_run:
        print(f"[*] Dry run: {len(produced)} pack(s) would be written to '{final_custom}'. Nothing was written.")
    elif produced:
        if clean_dest and final_custom.exists():
            shutil.rmtree(final_custom)
        final_custom.mkdir(parents=True, exist_ok=True)
        for n_done, p in enumerate(produced, 1):
            if verbose:
                print_progress(n_done, len(produced), prefix="Publishing")
            if wbconv.find_identical(final_custom, p.name, p):
                continue  # already in the destination, unchanged: no second copy
            shutil.move(str(p), str(final_custom / wbconv.unique_name(final_custom, p.name)))
        if verbose:
            print("[*] Generating v1.5 _manifest.txt index files...")
        stats["manifests_generated"] += write_v15_manifests(final_custom)
    else:
        print("[!] No pack was converted; the destination was not touched.")

    for tmp_d in temp_dirs_to_clean:
        if tmp_d.exists():
            shutil.rmtree(tmp_d, ignore_errors=True)

    stats["report"] = report
    return stats

def main():
    if sys.version_info < (3, 8):
        print("[!] Error: Python 3.8 or higher is required. Please update Python.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Convert ModRoom / Deeproom 1.4 mods into Wife's Bedroom v1.5 custom architecture.")
    parser.add_argument("inputs", nargs="*", help="Path(s) to ModRoom game folder, individual custom_* directories, character packs, or mod .zip archives.")
    parser.add_argument("-d", "--dest", help="Destination directory (v1.5 game folder or export folder).")
    parser.add_argument("--quarantine-duplicates", action="store_true", default=None, help="Automatically detect and quarantine duplicate custom character/room folders (default: True)")
    parser.add_argument("--no-quarantine-duplicates", action="store_true", default=None, help="Disable duplicate custom folder quarantine")
    parser.add_argument("--clean", action="store_true", help="Clean destination custom/ folder before converting.")
    parser.add_argument("--approximate", action="store_true", help="Also convert strips whose frame counts differ by dropping frames (first N kept); listed as 'approximate' in the report.")
    parser.add_argument("--no-approximate", action="store_true", help="Disallow lossy frame reduction (default: safe)")
    parser.add_argument("--dry-run", action="store_true", help="Convert into a temporary folder and write only the report; nothing is written to the destination.")
    parser.add_argument("-y", "--yes", action="store_true", help="Non-interactive execution (accept defaults).")
    args = parser.parse_args()

    tool_dir = Path(__file__).resolve().parent
    input_dir = tool_dir / "input"
    output_dir = tool_dir / "output" / "custom"

    print("=" * 70)
    print("      MODDED TO WB 1.5 MOD CONVERTER v1.2")
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
        print("    Please drag your mod folder(s) or custom_* directories onto Convert_to_WB_1.5.bat")
        print("    or place your files inside the input/ folder.")
        sys.exit(1)

    dest_dir = Path(args.dest).resolve() if args.dest else output_dir

    print(f"[*] Sources ({len(source_paths)} item(s)):")
    for s in source_paths:
        print(f"    - {s}")
    print(f"[*] Destination : {dest_dir}\n")

    approximate_enabled = False  # Default to safe
    if args.no_approximate:
        approximate_enabled = False
    elif args.approximate:
        approximate_enabled = True
    elif not args.yes and sys.stdin and sys.stdin.isatty():
        try:
            print("ModRoom-format (_0.png) strips are cut into different frame counts than v1.5 reads (for example lover mating press 24 vs 9).")
            print("Without approximation those strips are not converted and the pack is skipped or partial.")
            ans_app = input("Allow approximate frame reduction (drop extra frames for legacy targets)? [y/N]: ").strip().lower()
            if ans_app:
                approximate_enabled = ans_app.startswith("y")
        except Exception:
            approximate_enabled = False

    quarantine_enabled = True  # Default to ON
    if args.no_quarantine_duplicates:
        quarantine_enabled = False
    elif args.quarantine_duplicates:
        quarantine_enabled = True
    elif not args.yes and sys.stdin and sys.stdin.isatty():
        try:
            ans = input("Detect and quarantine duplicate custom assets across packs? [Y/n]: ").strip().lower()
            if ans:
                quarantine_enabled = ans.startswith("y")
        except Exception:
            quarantine_enabled = True

    print(f"[*] Approximate strips   : {'ON (frames dropped where counts differ)' if approximate_enabled else 'OFF (exact conversions only)'}")
    print(f"[*] Duplicate Quarantine : {'ENABLED [Default]' if quarantine_enabled else 'DISABLED'}\n")

    stats = convert_modroom_to_15(source_paths, dest_dir, clean_dest=args.clean, verbose=True, quarantine_duplicates=quarantine_enabled,
                                  approximate=approximate_enabled, dry_run=args.dry_run)
    report_path = tool_dir / "output" / "conversion_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    stats["report"].write(report_path)

    print("\n" + "=" * 70)
    print("              MOD CONVERSION COMPLETE — SUMMARY CARD")
    print("=" * 70)
    print("  Target Architecture   : Wife's Bedroom v1.5 (Unified custom/ Architecture)")
    print(f"  Lovers Converted      : {stats['lovers_converted']:,} Pack(s) (custom_data.futa with [info] section)")
    print(f"  Partners Converted    : {stats['partners_converted']:,} Pack(s) (custom_data.spouse with [info] section)")
    print(f"  Bedrooms Converted    : {stats['bedrooms_converted']:,} Pack(s) (custom_data.bedroom with [info] section)")
    print(f"  Total Assets Packaged : {stats['files_copied']:,} File(s) Integrated")
    print(f"  Raw Art Files Stripped: {stats['bloat_skipped']:,} Project File(s) (.aseprite, .psd, .clip, etc.)")
    print(f"  Manifest Indexes Built: {stats['manifests_generated']:,} _manifest.txt File(s) Generated")
    print(f"  Packs Not Converted   : {stats['skipped_packs']:,} (see the conversion report)")
    print(f"  Conversion Report     : {report_path}")
    print(f"  Duplicate Quarantine  : {'ENABLED' if quarantine_enabled else 'DISABLED'}")
    print(f"  Final Output Location : {dest_dir}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()