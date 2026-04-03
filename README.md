# 🧭 Python-SMF Toolkit
**Author:** Johnny Shumway (jShum00)
**License:** MIT
**Version:** 1.32

A reverse-engineered Python toolkit for viewing, parsing, and exporting
**Terminal Reality .SMF model files** used in classic games like *4x4 Evolution* and *4x4 Evolution 2*.

This toolkit includes:
- **`POD-2-SMF.py`** – simple SMF extractor, pull SMF files from POD archives using CLI.
- **`pysmf.py`** – robust SMF parser (extracts vertices, faces, textures, and submeshes)
- **`pysmf-gui.py`** – interactive OpenGL viewer using PyGame + Tkinter
- **`pysmf_export.py`** – multi-object OBJ exporter (Blender compatible)
- **`pysmf_print.py`** – formatted model summary printer

---

## 🚀 Features
- Loads and displays `.SMF` models in real time
- Supports textured and wireframe viewing
- Automatically finds matching `.TIF` / `.TIFF` textures in `../ART` when available
- Orbiting camera with standard and fast controls (`← / →`, `CTRL + ← / →`)
- Camera zoom via mouse wheel, slow `↑ / ↓`, fast `CTRL + ↑ / ↓`, and `Numpad +/-`
- Right-click drag orbit in the 3D viewer with cursor lock while held
- Grouped, scrollable mesh tree with per-submesh visibility toggles
- Right-side inspector for selected submeshes
- Preserves and exposes the unknown 5-value material tuple stored near each `v1` block
- Shows model-wide material tuple grouping to help compare repeated patterns across submeshes
- Direct export to multi-object `.OBJ`
- Human-readable SMF data summary printed to console

---

## 📸 Screenshots

Below are various stages of the **PySMF Viewer** and parser workflow — from command-line inspection to full 3D visualization and export.

### POD -> SMF Extractor<br />
**Extract the SMF files from the POD files in the game directory.**
```bash
python3 POD-2-SMF.py ../4x4Evo2/TRUCK.POD ../exportSMF/
[*] Extracting SMFs from: ../4x4Evo2/TRUCK.POD
[*] Output directory: ../exportSMF

[*] Started new SMF → smf_0000.smf
[↻ ] Renamed: smf_0000.smf → 31x10.smf
[+] Finished SMF #0001: 31x10.smf
[*] Started new SMF → smf_0001.smf
[↻ ] Renamed: smf_0001.smf → 31x10.smf
[+] Finished SMF #0002: 31x10.smf
[*] Started new SMF → smf_0002.smf
[↻ ] Renamed: smf_0002.smf → 31x10.smf
[+] Finished SMF #0003: 31x10.smf
[*] Started new SMF → smf_0003.smf
[↻ ] Renamed: smf_0003.smf → 31x10.smf
[+] Finished SMF #0004: 31x10.smf
[*] Started new SMF → smf_0004.smf
...

[✓] Extraction complete. 320 SMFs written from TRUCK.POD → ../exportSMF
```
> Note: To export textures (*.TIF) and model (*.SMF) files, use my other tool PyPOD, available [here](https://github.com/JShum00/PyPOD).

### Initial Folder<br />
**Viewing parsed file structure**<br />
![File Structure](Screenshots/PySMF-FileStructure.png)

### Command Line Tools<br />
**How to run it:**<br />
```bash
# Once in the VENV, do this:
python3 pysmf-gui.py
```

**The Model Summary:**<br />
```bash
# Example Output:
============================ SMF MODEL SUMMARY ============================
File: /home/jshum/Documents/exportSMF/4RUNNERLTD.smf
Version: 4
Submeshes: 33
Total Vertices: 2079
Textures: 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
---------------------------------------------------------------------------
  Body         | 490 (hdr:490) verts | 598 (hdr:598) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  Axler        | 68 (hdr:68) verts | 76 (hdr:76) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  BushBar      | 312 (hdr:312) verts | 358 (hdr:358) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  Cockpit      | 45 (hdr:45) verts | 34 (hdr:34) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  FogB2        | 47 (hdr:47) verts | 28 (hdr:28) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  FogB3        | 47 (hdr:47) verts | 28 (hdr:28) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  FogR1        | 44 (hdr:44) verts | 28 (hdr:28) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  FogR2        | 44 (hdr:44) verts | 28 (hdr:28) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  FogR3        | 44 (hdr:44) verts | 28 (hdr:28) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  FogR4        | 44 (hdr:44) verts | 28 (hdr:28) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  GlassI       | 44 (hdr:44) verts | 40 (hdr:40) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  GlassE       | 62 (hdr:62) verts | 70 (hdr:70) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  MirrorL      | 55 (hdr:55) verts | 56 (hdr:56) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  MirrorR      | 55 (hdr:55) verts | 56 (hdr:56) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  MudFlps      | 72 (hdr:72) verts | 32 (hdr:32) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  RfRack       | 104 (hdr:104) verts | 84 (hdr:84) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  RollBr1      | 52 (hdr:52) verts | 42 (hdr:42) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  Skid         | 26 (hdr:26) verts | 20 (hdr:20) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  UndBody      | 146 (hdr:146) verts | 130 (hdr:130) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  WiperLT      | 28 (hdr:28) verts | 16 (hdr:16) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  WiperRR      | 33 (hdr:33) verts | 22 (hdr:22) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  WiperRT      | 30 (hdr:30) verts | 16 (hdr:16) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  Winch        | 64 (hdr:64) verts | 38 (hdr:38) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  Snorkel      | 41 (hdr:41) verts | 47 (hdr:47) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  LightFL      | 4 (hdr:4) verts | 2 (hdr:2) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  LightFR      | 4 (hdr:4) verts | 2 (hdr:2) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  LightHL      | 9 (hdr:9) verts | 8 (hdr:8) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  LightHR      | 9 (hdr:9) verts | 8 (hdr:8) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  LightBL      | 13 (hdr:13) verts | 9 (hdr:9) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  LightBR      | 13 (hdr:13) verts | 9 (hdr:9) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  LightRL      | 13 (hdr:13) verts | 9 (hdr:9) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  LightRR      | 13 (hdr:13) verts | 9 (hdr:9) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
  LightBC      | 4 (hdr:4) verts | 2 (hdr:2) tris | 4RUNNERLTD.TIF, 4RUNNERLTD_bump.TIF
=========================================================================

Loaded 2079 vertices and 1961 faces from /home/jshum/Documents/exportSMF/4RUNNERLTD.smf
```

### Graphical Viewer (PySMF GUI)<br />
**Initial launch — OpenGL grid and controls**<br />
![GUI Initial Execution](Screenshots/PySMFGUI-InitialExecution.png)

**SMF file loader in action**<br />
![SMF File Loader](Screenshots/PySMF-SMFFileLoader.png)

**Loaded vehicle model (wireframe)**<br />
![Loaded Vehicle](Screenshots/PySMF-LoadedVehicle.png)

**Solid fill rendering mode**<br />
![Solid View Mode](Screenshots/PySMF-SolidViewMode.png)

**Texture rendering mode**
![Texture View Mode](Screenshots/PySMF-TextureViewMode.png)

**SMF export utility**<br />
![Exporter](Screenshots/PySMF-Exporter.png)

### Integration & Workflow - Blender<br />
![Model Imported to Blender](Screenshots/PySMF-ModelImported2BlenderAsOBJ.png)

---

## 🖥️ Requirements
Create and activate a virtual environment in the project directory, then install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
Tkinter comes pre-installed with most Python distributions.
Tested on Python 3.12+ (Linux).

---

## 🎮 Controls

**Keyboard:**

Key             | Action
----------------|--------------------------------------------
`O`             | Open .SMF file
`E`             | Export current model to .OBJ
`W`             | Toggle wireframe/solid
`M`             | Toggle texture view
`← / →`        | Orbit camera left/right
`↑ / ↓`        | Zoom in/out at standard speed
`CTRL + ← / →` | Orbit camera left/right at 2x speed
`CTRL + ↑ / ↓` | Zoom in/out at 2x speed
`Numpad +/-`    | Zoom in/out
`ESC`           | Exit Viewer

**Mouse / UI:**
- Hold right-click and drag left/right to orbit the camera; the cursor is hidden and locked to the window while held
- Click group arrows in the left sidebar to expand/collapse mesh groups
- Click mesh rows to select a submesh
- Click eye icons to hide/show individual submeshes
- Use the mouse wheel to zoom the camera, or to scroll the grouped mesh tree when hovering the left sidebar
- Drag the scrollbar to scroll the grouped mesh tree
- Click material fields in the inspector to edit them
- Press `Enter` in an active field to commit it to the **heuristic** live preview

---

## 🖼️ Viewer Layout
The GUI uses a multi-panel layout:

- **Top toolbar:** `Open`, `Export`, `Wireframe`, `Texture`, `Exit`, `Opacity`
- **Left sidebar:** grouped mesh tree with expand/collapse arrows and eye toggles
- **Center viewport:** OpenGL model view
- **Right inspector:** selected-submesh details, material tuple research, and heuristic preview state
- **Bottom status strip:** current file, wireframe state, texture state, assumed opacity state, visible-submesh count

The main window is resizable and uses native OS maximize/minimize controls.

---

## 📁 File Overview

**`pysmf.py`**

The main parser.
Reads `.SMF` files, reconstructs submeshes, textures, and geometry. Treats `v1`, `v2`, etc. as mesh-section markers rather than submesh names.

**`pysmf-gui.py`**

OpenGL viewer built with PyGame and PyOpenGL.
Uses an orbit camera, grid, grouped mesh sidebar, right-side inspector, and texture rendering.

**`pysmf_export.py`**

Converts `.SMF` → `.OBJ`, keeping each submesh as a distinct object.
Produces clean, Blender-importable geometry.

**`pysmf_print.py`**

Prints structured summary data to the console automatically when models are loaded:

```yaml
============================ SMF MODEL SUMMARY ============================
File: GMCJimmy.smf
Version: 4
Submeshes: 25
Total Vertices: 1837
Textures: GMCJimmy.TIF, GMCJimmy_bump.TIF
---------------------------------------------------------------------------
  Body         |      427 (hdr:427) verts |      538 (hdr:538) tris | GMCJimmy.TIF, GMCJimmy_bump.TIF
  AxleR        |       68 (hdr:68) verts  |       76 (hdr:76) tris  | GMCJimmy.TIF, GMCJimmy_bump.TIF
=========================================================================
```

---

## 🔬 Experimental Material Research

The viewer treats the 5-value line after a `v1` marker as **research data**, not settled truth.

For example:
```text
1,1,64,0,1,4RUNNERLTD.TIF
```

What PySMF does with this today:
- Preserves the raw 5 values exactly
- Shows them in the inspector
- Groups matching tuples across the model
- Allows session-only editing
- Offers a **heuristic preview** path for experimentation

What PySMF does **not** claim yet:
- The final semantics of each field
- Exact parity with the game's renderer
- Correct transparency/material behavior for all models

The `Opacity` toolbar toggle controls whether the viewer uses the current SMF-based heuristic opacity assumptions or renders textured meshes without those assumed alpha adjustments.

**Current heuristic assumptions (intentionally conservative):**
- `Value 2` is treated as an opacity multiplier
- `Value 4` and `Value 5` are treated as local transparency-related toggles
- `Value 1` and `Value 3` are preserved and shown, but not strongly interpreted yet

---

## 🗂️ Mesh Grouping

The viewer auto-groups obvious name families in the sidebar:

- `Fog*` → `Foglights`
- `Glass*` → `Glass`
- `Light*` → `Lights`
- `Mirror*` → `Mirrors`
- `Wiper*` → `Wipers`
- everything else → `Other`

These groups are UI-only and do not change parsing or export behavior.

---

## 🔧 Example Usage
Run the viewer:
```bash
python3 pysmf-gui.py
```
Standalone export:
```bash
python3 pysmf_export.py
```
Print model summary only:
```bash
python3 pysmf_print.py
```

---

## 🧠 Notes
- The `.SMF` format was used by Terminal Reality's EVO engine (circa 2000s).
- Models may have non-centered origins — this viewer recenters them automatically.
- Bump map references are preserved as filenames, but the viewer does not implement real bump mapping.
- TIFF image alpha is used in the viewer when texture rendering is enabled.
- The inspector and grouped material analysis are designed to help the community infer the format more accurately over time.

---

## 🧬 Credits
Reverse engineering, parser design, and viewer by Johnny Shumway (jShum00).
Inspired by Terminal Reality's original EVO engine file formats.

---

## 📜 License
This project is licensed under the MIT License — free for learning, modification, and redistribution.

# The MIT License (MIT)
Copyright © 2025 **Johnny Shumway**

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
