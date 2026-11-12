# ModRoom to WB 1.5 Mod Converter v1.0

A dedicated conversion tool that takes ModRoom / Deeproom 1.4 custom mods and converts them into Wife's Bedroom v1.5's unified `custom` folder architecture:
- Lovers $\to$ `custom/<character_name>/` (with `custom_data.futa`)
- Partners / Spouses $\to$ `custom/<character_name>/` (with `custom_data.spouse`)
- Room Backgrounds $\to$ `custom/<bedroom_name>/` (with `custom_data.bedroom`)

You can provide a full ModRoom game directory, individual category folders (`custom_futas`, `custom_wives`, or `custom_bedrooms`), multiple category folders dragged together, or individual character packs!

---

## Quick Start (3 Steps)

1. Find your ModRoom 1.4 game folder, individual category folder(s) (`custom_futas`, `custom_wives`, `custom_bedrooms`), an individual character pack, or a mod `.zip` file.
2. Drag and drop your folder(s) or `.zip` file directly onto `Convert_ModRoom_to_1.5.bat`.
3. Press Enter when prompted.

Your converted mods will be ready in the `output/custom` folder, ready to copy straight into Wife's Bedroom v1.5!

---

## What This Converter Does

### 1. Reorganizes Split Folders into Unified v1.5 Format
In ModRoom and Deeproom 1.4, mods are split across separate folders like `custom_futas`, `custom_wives`, and `custom_bedrooms`.
Wife's Bedroom v1.5 expects all custom mods to live inside a single unified `custom` folder. This tool automatically reorganizes all characters, partners, and bedrooms into their own clean self-contained packs inside `custom/`.

### 2. Accepts Individual `custom_*` Folders
You do not need to convert an entire game at once:
- Drag just `custom_futas` to convert only your Lovers.
- Drag just `custom_wives` to convert only your Partners.
- Drag just `custom_bedrooms` to convert only your Room Backgrounds.
- Select and drag multiple category folders together (for example, both `custom_futas` and `custom_wives`) to convert them simultaneously into a single combined `custom/` directory.

### 3. Synthesizes Required v1.5 Data Headers
Wife's Bedroom v1.5 relies on specific data header files to detect content types:
- Lovers require `custom_data.futa`
- Partners require `custom_data.spouse`
- Bedrooms require `custom_data.bedroom`

If a legacy ModRoom mod uses an older `.ini` file or lacks the exact header name, this tool automatically generates the required header file using the character's real name and stats.

### 4. Normalizes Sprite Filenames for 100% v1.5 Parity
In older Deeproom mods, partner/wife sprites were often named with legacy conventions (such as `custom_wife_portrait_0.png` or `custom_wife_mating_press.png`).
Wife's Bedroom v1.5's native engine looks for `custom_portrait.png` and `custom_mating_press.png`. This tool automatically ensures both filename variants exist so your partners load and display without missing texture errors.

### 5. Strips Unnecessary Art Project Files
Mod creators sometimes leave raw project source files (`.aseprite`, `.clip`, `.pdn`, `.kra`, `.psd`, `.zip`, and `.bak`) inside character folders.
This tool automatically filters out project files, keeping only game-ready images (`.png`), audio (`.ogg`, `.wav`, `.mp3`), and configuration files (`.ini`, `.futa`, `.json`) so your game stays clean and fast.

### 6. Generates Game-Ready Manifest Indexes
Generates clean `_manifest.txt` indexing files inside every converted folder so the mods load instantly in both desktop Wife's Bedroom v1.5 and mobile APK builds.

---

## Ways to Use

### Method 1: Drag and Drop (Easiest)
Drag any of the following directly onto `Convert_ModRoom_to_1.5.bat`:
- A full ModRoom game folder.
- An individual category folder (`custom_futas`, `custom_wives`, or `custom_bedrooms`).
- Multiple category folders selected and dragged together.
- An individual character pack folder.
- A mod `.zip` archive.

### Method 2: Use the "input" Folder
Drop your ModRoom mod folders or `.zip` files into the `input` folder and double-click `Convert_ModRoom_to_1.5.bat`.

### Method 3: Merge Directly into Your v1.5 Game (Advanced)
You can point the converter directly at your existing Wife's Bedroom v1.5 installation so converted mods are placed directly into your `custom` folder:
```
python ModRoom_to_WB_1.5.py "path/to/custom_futas" --dest "path/to/wifes_bedroom_win1_5"
```

---

## Command Line Flags

| Flag | Purpose |
|---|---|
| `-d`, `--dest <path>` | Specify a custom destination folder (e.g. your v1.5 game directory). |
| `--clean` | Cleans target custom/ folder before copying to ensure a fresh, clean export. |
| `-y`, `--yes` | Runs non-interactively without prompting (ideal for automated batch scripts). |

---

## Folder Layout

```
ModRoom_to_WB_1.5_Converter/
├── Convert_ModRoom_to_1.5.bat   (One-click Windows launcher)
├── ModRoom_to_WB_1.5.py         (Conversion engine)
├── README.md                    (This guide)
├── input/                       (Drop mod folders or .zip files here)
└── output/
    └── custom/                  (Converted game-ready v1.5 mods)
        ├── <character_name>/    (Lovers with custom_data.futa)
        ├── <partner_name>/      (Partners with custom_data.spouse)
        └── <bedroom_name>/      (Bedrooms with custom_data.bedroom)
```
