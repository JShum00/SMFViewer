# About SMF

**Author:** Johnny Shumway (`jShum00`)

This document summarizes what PySMF currently understands about **Terminal Reality's `.SMF` model format**, what remains uncertain, and how the project approaches reverse engineering.

## What Is SMF?
`.SMF` appears to be a text-based 3D model format used by Terminal Reality's EVO-era games such as *4x4 Evolution* and *4x4 Evolution 2*.

At a high level, an SMF file contains:
- a file header
- a format version
- repeated submesh blocks
- texture references
- vertex data
- face index data
- an additional material-like line associated with `v1` / `v2` mesh-section markers

It was never publicly documented, so the current understanding comes from inspection of extracted model files and repeated pattern matching across many examples.

> Note  
> [4x4Evolution.NET](http://www.4x4evolution.net/doku.php?id=modding_tools) documents Windows-based community modding tools from Dummiesman and Fuzzy. PySMF focuses on a Python-based inspection and research workflow.

## Reverse Engineering Progress
PySMF now parses the format with reasonable confidence for the core geometry path:

- `C3DModel` file header
- version number
- identifier-like submesh names such as `Body`, `BushBar`, `GlassE`
- per-submesh count hints such as `490,1,598,0`
- mesh-section markers such as `v1`, `v2`
- texture references
- vertex rows with 8 values
- triangle rows with 3 indices

One important parser correction made during this project:

```text
BushBar
1
1
312,1,358,0
v1
1,1,64,0,0,4RUNNERLTD.TIF
```

`v1` is now treated as an in-block mesh-section marker rather than as the submesh name itself. The canonical parsed submesh name remains `BushBar`.

## Working Model Of A Submesh Block
A typical block currently looks like this:

```text
Body
1
1
490,1,598,0
v1
1,1,64,0,1,4RUNNERLTD.TIF
"4RUNNERLTD_bump.TIF"
... vertex rows ...
... face rows ...
```

What PySMF currently interprets with confidence:

- `Body` -> submesh name
- `490,1,598,0` -> count hint line containing at least vertex and face counts
- `v1` -> mesh-section marker
- `4RUNNERLTD.TIF` -> texture reference
- `"4RUNNERLTD_bump.TIF"` -> additional texture/bump reference
- 8-value rows -> vertex position, normal, UV
- 3-value rows -> triangle indices

## Vertex Rows
PySMF currently treats any line with 8 comma-separated numeric values as:

```text
x, y, z, nx, ny, nz, u, v
```

This interpretation is supported by:
- geometry rendering
- normal-like directional values
- stable UV mapping in the OpenGL viewer
- successful OBJ export with UVs preserved

## Face Rows
PySMF treats 3-integer rows as triangle index data:

```text
i0, i1, i2
```

This fits the model geometry and exports correctly to OBJ in current testing.

## Texture Handling
The toolkit currently understands several texture-related behaviors:

- `.TIF` / `.TIFF` filenames are preserved from the SMF
- the viewer tries to load a matching texture from `../ART`
- if automatic lookup fails, the viewer can prompt for manual selection
- TIFF image alpha is used by the viewer when texture mode is active
- bump-map references are preserved as filenames, but no bump mapping is implemented yet

## The Unknown 5-Value Material Tuple
The most interesting unresolved part of the format is the numeric line after `v1`.

Example:

```text
1,1,64,0,1,4RUNNERLTD.TIF
```

PySMF now preserves this as structured data:
- the 5 raw values
- the texture filename
- the original raw line

This is exposed directly in the GUI for research.

## What The Project Has Observed So Far
Using `4RUNNERLTD.SMF` as a grounded test file, the following exact value tuples repeat in meaningful part categories:

| Tuple | Example submeshes |
|---|---|
| `1,1,64,1,1` | `GlassE` |
| `1,1,64,1,0` | `GlassI` |
| `1,1,32,1,0` | `LightFL`, `LightFR`, `LightHL`, `LightHR`, etc. |
| `1,1,64,0,1` | `Body`, `MirrorL`, `MirrorR` |
| `1,1,64,0,0` | `BushBar`, `RollBr1` |
| `1,0.25,32,0,0` | `Fog*`, `Wiper*`, `Snorkel` |
| `1,0,0,0,0` | `Axler`, `RfRack`, `Skid`, `UndBody`, `Winch` |
| `1.25,0,0,0,0` | `Cockpit`, `MudFlps` |

This strongly suggests the tuple is not random and is likely describing a material/rendering class.

## What PySMF Thinks It May Know
These are **working hypotheses**, not settled facts:

- the 5-value line is material- or render-related metadata attached to the submesh block
- exact tuples tend to cluster by part category
- glass and light meshes clearly use distinct tuple families
- some values likely affect transparency or blending behavior
- at least one value may act more like a material-class selector than a simple scalar opacity

## What Remains Unknown
The true semantics of the five values are still unresolved.

For now, the project does **not** claim to know:
- the exact meaning of Value 1
- the exact meaning of Value 3
- whether Values 4 and 5 correspond to exterior/interior transparency, glass/lights behavior, or something broader
- whether the game combines these values with custom TIFF metadata, texture alpha, render order rules, or shader-like state

## How The Viewer Helps Research
The current GUI is intentionally built as a research tool, not just a renderer.

It now provides:
- grouped mesh tree with per-submesh visibility toggles
- submesh selection
- right-side inspector
- parsed material tuple display
- editable session-only values
- committed heuristic preview state
- model-wide exact-tuple grouping so matching parts can be compared quickly

The heuristic preview path exists only to help exploration. It should not be treated as proof of how the game renders these materials.

## Current Heuristic Preview
The viewer currently offers an optional experimental preview path that assumes:

- Value 2 can be treated like an opacity multiplier
- Values 4 and 5 can be treated like local transparency toggles

This is explicitly heuristic. The `Opacity` toolbar toggle can disable these assumptions and render textured meshes without those SMF-based opacity adjustments.

## Why This Matters
The format is already useful for:
- viewing old game assets
- exporting geometry to OBJ
- studying how Terminal Reality organized vehicle submeshes
- collecting evidence about undocumented material data

The remaining material semantics are now one of the most interesting open questions in the format.

## Current Practical Summary
An SMF file can currently be treated as:

```text
header
version
repeated submesh blocks
  name
  count hints
  v1/v2 marker
  material-like tuple + texture
  optional extra texture/bump line
  vertex rows
  face rows
```

That model is good enough today for:
- parsing
- visualization
- per-submesh inspection
- grouped pattern analysis
- OBJ export

It is not yet good enough to claim final parity with the original game renderer.
