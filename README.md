# 🧭 Python-SMF Toolkit
**Author:** Johnny Shumway (jShum00)
**License:** MIT
**Version:** 1.0

A reverse-engineered Python toolkit for viewing, parsing, and exporting
**Terminal Reality .SMF model files** used in classic games like *4x4 Evolution 2*.

This toolkit includes:
- **`pysmf.py`** – robust SMF parser (extracts vertices, faces, textures, and submeshes)
- **`pysmf-gui.py`** – interactive OpenGL viewer using PyGame + Tkinter
- **`pysmf_export.py`** – multi-object OBJ exporter (Blender compatible)
- **`pysmf_print.py`** – formatted model summary printer

---

## 🚀 Features
- Loads and displays `.SMF` models in real time
- Orbiting camera (arrow keys)
- Progressive submesh draw with pause/resume
- Wireframe toggle
- Direct export to multi-object `.OBJ`
- Human-readable SMF data summary printed to console

---

## 🖥️ Requirements
Install dependencies with:
```bash
pip install pygame PyOpenGL numpy
```
Tkinter comes pre-installed with most Python distributions.
Tested on Python 3.10+ (Linux).

## 🎮 Controls
Key             Action
- O             Open .SMF file.
- E             Export current model to .OBJ
- W             Toggle wireframe/solid.
- SPACE         Pause or resume progressive drawing.
- ← / →       Orbit camera, left/right.
- ESC           Exit Viewer

## 🧩 File Overview
pysmf.py

The main parser.
Reads .SMF line-by-line, reconstructs submeshes, textures, and geometry.

pysmf-gui.py

OpenGL viewer built with PyGame and PyOpenGL.
Uses an orbit camera, grid, and incremental draw thread.

pysmf_export.py

Converts .SMF → .OBJ, keeping each submesh as a distinct object.
Produces clean, Blender-importable geometry.

pysmf_print.py

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

## 🧱 Example Usage
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

## 🧠 Notes
The .SMF format was used by Terminal Reality’s EVO engine (circa 2000s). 
Models may have non-centered origins — this viewer recenters them automatically.
Texture and bump map names are parsed but not yet applied in OpenGL.
Wireframe is default for debugging visibility.

## 🧬 Credits
Reverse engineering, parser design, and viewer by Johnny Shumway (jShum00).
Inspired by Terminal Reality’s original EVO engine file formats.

## 📜 License
This project is licensed under the MIT License — free for learning, modification, and redistribution.

# The MIT License (MIT)
Copyright © 2025 **Johnny Shumway**

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
