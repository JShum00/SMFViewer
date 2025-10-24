# 📘 About SMF: Understanding Terminal Reality's 3D Model Format
**Author:** Johnny Shumway (jShum00)

---

## 🧠 What is SMF?

The **SMF** (Simple Model Format) was used by **Terminal Reality**'s EVO engine, powering games like *4x4 Evolution* and *4x4 Evolution 2* in the early 2000s. These files store 3D model geometry similar to an obj or fbx. Think vertices, faces, uvs, texture references, and the lot. This viewer was made to view the vehicle SMF models.

Unfortunately, SMF was never publicly documented. Every `.SMF` file was bundled inside the game’s proprietary `.POD` archive, which meant there were no clear tools to inspect or convert them — until now.

---

## 🧩 The Reverse Engineering Journey

When I started this project, my goal was simple:
> “I want to see what’s *inside* these old game models — and maybe bring them into Blender.”

But there was no documentation, no code, and no example readers for `.SMF` files.
So, the journey began at the **binary level.**

### Step 1 — Opening the PODs
Using **Okteta** (a hex editor), I examined the game’s `.POD` archives.
Inside were filenames, binary tables, and long a sequence of multiple float-like numbers — which turned out to be vertices.

I manually extracted several `.SMF` chunks and started noticing repeating patterns:

```smf
C3DModel
4
32
0,50
Body
1
1
427,1,538,0
v1
1,1,64,0,1,GMCJimmy.TIF
"GMCJimmy_bump.TIF"
```

This was the key. Each section represented a **submesh** — a component of the model (Body, Wheels, Lights, etc.) — with counts for vertices and faces.

---

### Step 2 — Building the Parser
The `pysmf.py` parser reads `.SMF` files line by line, handling the quirks and structure I discovered:

- `C3DModel` — file header
- `Version` — format version (e.g., 4)
- Submesh names — labels like *Body*, *AxleR*, *BushBar*
- Texture references — `.TIF` filenames
- Vertex lists — 8 values per line: `x, y, z, nx, ny, nz, u, v`
- Face lists — groups of 3 indices (triangles)

The parser doesn’t rely on fixed offsets — it’s **defensive and flexible** — so it handles small differences between models gracefully.

Here’s what it outputs when parsing a vehicle:

```yaml
Version: 4
Submeshes: 25
Vertices: 1837
Textures: ['GMCJimmy.TIF', 'GMCJimmy_bump.TIF']
Body: 427 (hdr:427) verts, 538 (hdr:538) tris, ['GMCJimmy.TIF', 'GMCJimmy_bump.TIF']
AxleR: 68 (hdr:68) verts, 76 (hdr:76) tris, ['GMCJimmy.TIF', 'GMCJimmy_bump.TIF']
```


---

### Step 3 — Visualizing the Data
With the format decoded, I built a **viewer** (`pysmf-gui.py`) using **PyGame** and **PyOpenGL**.

It renders the models in wireframe, supports orbiting around the object, and progressively draws submeshes.
You can even toggle solid mode or export directly to `.OBJ` with a single keypress.

Seeing the old EVO-era trucks and scenery appear in modern OpenGL was surreal — it’s like giving these forgotten assets a second life.

---

### Step 4 — Exporting to OBJ
Finally, `pysmf_export.py` converts SMF data into standard `.OBJ` format —
with each submesh becoming its own named object (`o Body`, `o AxleR`, etc.).

The exported files import flawlessly into Blender, preserving all geometry and UVs.
This makes the format practical for study, restoration, or fan remaster projects.
Although, I have **NOT** dealt with the texture importing, shading, or stuff of that nature.

---

## 🧮 How the Parser Works (in plain English)

1. **Open the file** and strip whitespace.
2. **Detect the header** (`C3DModel`) and version number.
3. **Create a new submesh** whenever a purely alphabetic name appears.
4. **Collect texture filenames** (lines containing `.TIF`).
5. **Parse vertex data** — any line with 8 comma-separated values.
6. **Parse face data** — any line with 3 comma-separated integers.
7. **Store everything** in structured dictionaries and lists.

At the end, all submeshes are stored in a unified Python structure:
```python
{
"version": 4,
"vertices": [...],
"submeshes": [
{"name": "Body", "vertices": [...], "faces": [...], "textures": [...]},
...
],
"textures": [...]
}
```

---

## 🧰 The Toolkit
| Script              | Purpose                                      |
| ------------------- | -------------------------------------------- |
| **pysmf.py**        | Parser for .SMF files                        |
| **pysmf-gui.py**    | Interactive viewer (OpenGL)                  |
| **pysmf_export.py** | Exports SMFs to multi-object .OBJ            |
| **pysmf_print.py**  | Pretty-prints model summaries to the console |

Each module is self-contained, but they all work together to provide a complete toolchain — from raw .POD data to modern, viewable 3D models.

---

## 🧭 Lessons Learned
- Reverse engineering old formats is equal parts detective work and pattern recognition.
- Hex editors like Okteta are invaluable when you’re starting from zero.
- Consistent structure emerges even from undocumented formats — once you see enough examples.
- Python’s text parsing and OpenGL libraries make it surprisingly easy to bring forgotten assets back to life.

---

## 🎯 The Goal

The Python-SMF project isn’t just about nostalgia — it’s about preserving digital history.
By documenting how these files work and making them accessible, others can learn, remix, or even rebuild EVO-era games with modern tools.

---


### 🧮 Data breakdown

| Section | Description |
|----------|-------------|
| `C3DModel` | File type header. |
| `4` | Format version. |
| `<name>` | Submesh identifier (e.g. Body, AxleR, LightHR). |
| `vertex_count, ?, face_count, ?` | Header line giving vertex & triangle counts. |
| `.TIF` lines | Texture and bump map references. |
| 8-value lines | Vertex positions `(x, y, z)`, normals `(nx, ny, nz)`, and UVs `(u, v)`. |
| 3-value lines | Face definitions referencing vertex indices. |

Each submesh repeats this same pattern until the file ends.

---

### 📜 Summary

In short, an `.SMF` file is a **stack of submesh blocks**, each containing:

```yaml
[name]
texturing info
vertex data
triangle index data
```


The parser reads these blocks sequentially, normalizing the information into structured Python lists and dictionaries — making them ready for visualization or export.



