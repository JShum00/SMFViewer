# PySMF Toolkit

**Author:** Johnny Shumway (`jShum00`)  
**License:** MIT

PySMF is a reverse-engineered Python toolkit for inspecting, viewing, and exporting **Terminal Reality `.SMF` model files** used by games such as *4x4 Evolution* and *4x4 Evolution 2*.

The toolkit currently includes:
- `POD-2-SMF.py` – extracts SMF data from POD archives
- `pysmf.py` – parses SMF models into typed Python structures
- `pysmf-gui.py` – interactive OpenGL viewer and research UI
- `pysmf_export.py` – exports SMF geometry to multi-object OBJ
- `pysmf_print.py` – prints a structured model summary to the console

## Features
- Loads and displays `.SMF` models in real time with PyGame + PyOpenGL
- Supports textured and wireframe viewing
- Automatically finds matching `.TIF` / `.TIFF` textures in `../ART` when available
- Provides a grouped, scrollable mesh tree with per-submesh visibility toggles
- Shows a right-side inspector for selected submeshes
- Preserves and exposes the unknown 5-value material tuple stored near each `v1` block
- Lets you experiment with those values in-session without writing back to disk
- Shows model-wide material tuple grouping to help compare repeated patterns across submeshes
- Exports SMFs to Blender-friendly multi-object `.OBJ`

## Current Viewer Layout
The GUI now uses a multi-panel layout:

- Top toolbar: `Open`, `Export`, `Wireframe`, `Texture`, `Exit`, `Opacity`
- Left sidebar: grouped mesh tree with expand/collapse arrows and eye toggles
- Center viewport: OpenGL model view
- Right inspector: selected-submesh details, material tuple research, and heuristic preview state
- Bottom status strip: current file, wireframe state, texture state, assumed opacity state, visible-submesh count

The main window is resizable and uses native OS maximize/minimize controls.

## Requirements
Install dependencies with:

```bash
pip install pygame PyOpenGL numpy Pillow
```

Tkinter ships with most Python distributions.

Tested on Python 3.10+ under Linux.

## Controls
Keyboard:

- `O` – open an `.SMF` file
- `E` – export the current model to `.OBJ`
- `W` – toggle wireframe / solid rendering
- `M` – toggle texture view
- `Left` / `Right` – orbit camera
- `Numpad +` / `Numpad -` – zoom
- `Space` – legacy no-op
- `Esc` – quit

Mouse / UI:

- Click group arrows in the left sidebar to expand/collapse mesh groups
- Click mesh rows to select a submesh
- Click eye icons to hide/show individual submeshes
- Use the mouse wheel or scrollbar thumb to scroll the grouped mesh tree
- Click material fields in the inspector to edit them
- Press `Enter` in an active field to commit that one field to the **heuristic** live preview

## What The Toolkit Understands Today
PySMF currently handles these parts of the format with reasonable confidence:

- file header such as `C3DModel`
- format version
- submesh names like `Body`, `GlassE`, `LightFL`
- per-submesh vertex and face count hints
- vertex rows with 8 values:
  - position `x, y, z`
  - normal `nx, ny, nz`
  - UV `u, v`
- face rows with 3 indices
- texture references
- the `v1`-adjacent material line:
  - 5 raw values
  - texture filename
  - original raw line for inspection

## Experimental Material Research
The viewer now treats the 5-value line after a `v1` marker as **research data**, not settled truth.

For example:

```text
1,1,64,0,1,4RUNNERLTD.TIF
```

What PySMF does with this today:
- preserves the raw 5 values exactly
- shows them in the inspector
- groups matching tuples across the model
- allows session-only editing
- offers a **heuristic preview** path for experimentation

What PySMF does **not** claim yet:
- the final semantics of each field
- exact parity with the game’s renderer
- correct transparency/material behavior for all models

The `Opacity` toolbar toggle controls whether the viewer uses the current SMF-based heuristic opacity assumptions or renders textured meshes without those assumed alpha adjustments.

## Heuristic Assumptions In The Viewer
The current live preview is intentionally conservative and experimental:

- `Value 2` is treated as an opacity multiplier
- `Value 4` and `Value 5` are treated as local transparency-related toggles
- `Value 1` and `Value 3` are preserved and shown, but not strongly interpreted yet

This is a research aid, not a final renderer.

## Mesh Grouping In The Sidebar
The viewer currently auto-groups obvious name families:

- `Fog*` -> `Foglights`
- `Glass*` -> `Glass`
- `Light*` -> `Lights`
- `Mirror*` -> `Mirrors`
- `Wiper*` -> `Wipers`
- everything else -> `Other`

These groups are UI-only and do not change parsing or export behavior.

## Example Usage
Run the viewer:

```bash
python3 pysmf-gui.py
```

Export a model:
Tkinter comes pre-installed with most Python distributions.
Tested on Python 3.10+ (Linux).

---

## 🎮 Controls
Key             Action
- O             Open .SMF file.
- E             Export current model to .OBJ
- W             Toggle wireframe/solid.
- SPACE         Pause or resume progressive drawing.
- ← / →       Orbit camera, left/right.
- ESC           Exit Viewer

---

## 📁 File Overview
pysmf.py

```bash
python3 pysmf_export.py
```

Print a model summary:

```bash
python3 pysmf_print.py
```

## Example Summary Output
`pysmf_print.py` prints a structured overview such as:

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

## Notes
- Models may have off-center origins; the viewer recenters them for inspection.
- The parser now treats `v1`, `v2`, etc. as mesh-section markers, not as submesh names.
- Bump map references are preserved as filenames, but the viewer does not implement real bump mapping.
- TIFF image alpha is used in the viewer when texture rendering is enabled.
- The inspector and grouped material analysis are designed to help the community infer the format more accurately over time.
---

## 🔧 Example Usage
Run the viewer:
```bash
python3 pysmf-gui.py
```
Standalone export:
```bash
python3 pysmf-export.py
```
Print model summary only:
```bash
python3 pysmf_print.py
```

---

## 🧠 Notes
The .SMF format was used by Terminal Reality’s EVO engine (circa 2000s). 
Models may have non-centered origins — this viewer recenters them automatically.
Texture and bump map names are parsed but not yet applied in OpenGL.
Wireframe is default for debugging visibility.

---

## 🧬 Credits
Reverse engineering, parser design, and viewer by Johnny Shumway (jShum00).
Inspired by Terminal Reality’s original EVO engine file formats.

---

## 📜 License
This project is licensed under the MIT License — free for learning, modification, and redistribution.

# The MIT License (MIT)
Copyright © 2025 **Johnny Shumway**

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

## Screenshots
Existing screenshots in `Screenshots/` still cover the project history, but some UI images may now lag behind the current multi-panel viewer. The current GUI includes a grouped left mesh tree, right-side inspector, bottom status strip, and top toolbar.

## License
This project is licensed under the MIT License.
