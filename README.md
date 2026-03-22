# SMA2-Graphics-Extractor-Inserter

## What is this?
**SMA2 Graphics Extractor / Inserter** is a GUI tool to **extract** and **reinsert** graphic data inside an **SMA2 (GBA)** ROM. all of this is possible thanks to the incredible work made in this repo: https://github.com/KarisaAdvynia/sma2-disasm by KarisaAdvynia, I hope this project is useful for future ROM hackers of SMA2.

Sincerely,  
**Oquendo :D**

The tool uses `binptrs.txt` to determine:
- the **offset** in the ROM (the `startptr` address)
- the **length** (computed from endptr/startptr)
- the **output path** (for example `Graphics/...` or `Tilemaps/...`)

## Files in the repo
- `sma2_gfx_tool.exe`: the GUI executable
- `binptrs.txt`: offsets/lengths map used by the app
- `_internal/` and/or `_internal.zip`: runtime resources required by the PyInstaller-built `.exe` (PySide6)

## Requirements
- Run the `.exe` directly (recommended if you just want to use it).
- To build from source:
  - Python
  - PyInstaller
  - PySide6

## How to use (GUI)
1. Open `sma2_gfx_tool.exe`.
2. In **ROM**, select your `sma2.gba` (or the ROM you want to modify).
3. In **Output**, choose the folder where extracted files will be saved.
4. In **Filter**, pick one:
   - **Graphics only**
   - **Graphics + Tilemaps**
   - **All binptrs entries**
5. Select items in the list (checkboxes) and choose:
   - **Extract selected** (extracts only what you selected)
   - **Extract all** (extracts everything in the current filter)

## Insertion (modifying the ROM)
1. Extract first (or ensure you already have the extracted files matching the expected structure).
2. Click **Insert selected (new ROM)**:
   - choose the input ROM in **ROM**
   - select the **Output** folder where extracted files are located
   - the app generates a new ROM named like: `your_rom_edit.gba`
3. The app checks that file sizes match what `binptrs.txt` expects.

## Notes / warnings
- Always **backup** your ROM before inserting.
- Offsets/lengths in `binptrs.txt` must match your ROM version.
- If you get errors like **“out of bounds”** or **“size mismatch”**, it usually means the ROM version and/or extracted files do not match `binptrs.txt`.
```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
