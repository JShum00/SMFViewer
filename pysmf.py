"""
SMF Parser
Author: Johnny Shumway (jShum00)

Parses Terminal Reality .SMF model files used in games like 4x4 Evolution 2.
Extracts vertex data, face indices, texture references, and submesh structure.

Each SMF file is read line-by-line with defensive parsing to handle small format variations.
The resulting data can be consumed by the SMF Viewer or exported to other 3D formats.
"""

import re
from typing import TypedDict

Vertex = list[float]
Face = list[int]


class SubmeshMaterial(TypedDict):
    values: list[str]
    texture: str
    raw_line: str


class Submesh(TypedDict):
    name: str
    vertices: list[Vertex]
    faces: list[Face]
    textures: list[str]
    vertex_count: int | None
    face_count: int | None
    material: SubmeshMaterial | None


class ParsedModel(TypedDict):
    header: dict[str, str]
    version: int | None
    vertices: list[Vertex]
    submeshes: list[Submesh]
    textures: list[str]


class SMFParser:
    """Parser for Terminal Reality .SMF files."""

    # Submesh names in SMF files resemble identifiers; geometry rows do not.
    _SUBMESH_NAME_RE: re.Pattern[str] = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
    _VERTEX_MARKER_RE: re.Pattern[str] = re.compile(r'^v\d+$', re.IGNORECASE)

    def __init__(self) -> None:
        """Initialize storage for parsed model data."""
        self.vertices: list[Vertex] = []   # global vertex list (all submeshes)
        self.submeshes: list[Submesh] = []  # list of dicts, one per submesh
        self.textures: list[str] = []      # list of unique texture filenames
        self.version: int | None = None    # SMF format version
        self.header: dict[str, str] = {}   # header info (e.g., C3DModel tag)

    # -------------------------------------------------------------------------

    def _clean_tex(self, line: str) -> str:
        """
        Extract and clean texture filename from a line.

        Args:
            line (str): A line containing a texture reference, e.g. `"GMCJimmy.TIF"`

        Returns:
            str: Cleaned texture filename.
        """
        tex = line.replace('"', '').strip()
        tex = tex.split(',')[-1].strip()
        return tex

    def _parse_material_line(self, line: str) -> SubmeshMaterial | None:
        """Parse a 5-value material line followed by a texture filename."""
        parts = [part.strip().replace('"', '') for part in line.split(',')]
        if len(parts) < 6:
            return None

        texture = parts[-1]
        if not texture or ".TIF" not in texture.upper():
            return None

        return {
            "values": parts[:5],
            "texture": texture,
            "raw_line": line,
        }

    def _is_submesh_name(self, line: str) -> bool:
        """
        Return True when a line looks like a valid submesh identifier.

        Valid names start with a letter and may continue with letters,
        digits, or underscores. Comma-delimited lines are always rejected
        to avoid matching geometry rows or count metadata. Vertex markers
        such as `v1`/`v2` are excluded so they remain metadata within the
        current submesh block instead of opening a new submesh record.
        """
        if ',' in line:
            return False
        if self._is_vertex_marker(line):
            return False
        return bool(self._SUBMESH_NAME_RE.fullmatch(line))

    def _is_vertex_marker(self, line: str) -> bool:
        """Return True when a line is a mesh-section marker such as `v1`."""
        return bool(self._VERTEX_MARKER_RE.fullmatch(line))

    # -------------------------------------------------------------------------

    def parse(self, path: str) -> ParsedModel:
        """
        Parse an .SMF file into structured data.

        Args:
            path (str): Path to the SMF file.

        Returns:
            dict: A dictionary containing model metadata and geometry:
                {
                    "header": {...},
                    "version": int,
                    "vertices": [...],
                    "submeshes": [...],
                    "textures": [...]
                }
        """
        self.vertices = []
        self.submeshes = []
        self.textures = []
        self.version = None
        self.header = {}

        # Some game assets contain odd bytes, so parse defensively and ignore
        # decode errors instead of failing the whole model load.
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [ln.strip() for ln in f if ln.strip()]

        i = 0
        current_submesh: Submesh | None = None

        while i < len(lines):
            line = lines[i]

            # ---------------- Top-level header ----------------
            if line.startswith("C3DModel"):
                self.header["type"] = "C3DModel"
                i += 1
                continue

            # ---------------- Version number ----------------
            if self.version is None and line.isdigit():
                try:
                    self.version = int(line)
                except ValueError:
                    self.version = None
                i += 1
                continue

            # ---------------- Submesh block start ----------------
            # Submesh names are identifier-like tokens (e.g., "Body", "Wheel_01")
            if self._is_submesh_name(line):
                if current_submesh:
                    self.submeshes.append(current_submesh)

                # Many files store vertex/face counts a couple of rows after
                # the submesh label, so probe nearby before parsing geometry.
                look = i + 1
                vertex_count: int | None = None
                face_count: int | None = None
                if look + 2 < len(lines):
                    candidate = lines[look + 2]
                    parts = candidate.split(',')
                    if len(parts) >= 4:
                        try:
                            vertex_count = int(parts[0])
                            face_count = int(parts[2])
                        except ValueError:
                            vertex_count = face_count = None

                current_submesh = {
                    "name": line,
                    "vertices": [],
                    "faces": [],
                    "textures": [],
                    "vertex_count": vertex_count,
                    "face_count": face_count,
                    "material": None,
                }

                i += 1
                continue

            # ---------------- Vertex marker (v1, v2...) ----------------
            if self._is_vertex_marker(line):
                i += 1
                continue

            # ---------------- Texture references (.TIF) ----------------
            if ".TIF" in line.upper():
                tex = self._clean_tex(line)
                if current_submesh:
                    material = self._parse_material_line(line)
                    if material is not None:
                        current_submesh["material"] = material
                    # Texture/material metadata should appear before the vertex block.
                    # Once vertices start, later `.TIF` lines are not treated as
                    # canonical submesh texture assignments.
                    if len(current_submesh["vertices"]) == 0 and tex:
                        if tex not in current_submesh["textures"]:
                            current_submesh["textures"].append(tex)
                        if tex not in self.textures:
                            self.textures.append(tex)
                else:
                    if tex and tex not in self.textures:
                        self.textures.append(tex)
                i += 1
                continue

            # ---------------- Geometry (vertices or faces) ----------------
            parts = line.split(',')

            # Populate vertex/face count hints if missing
            if current_submesh and current_submesh["vertex_count"] is None and current_submesh["face_count"] is None:
                # Some SMFs shift the count row around, so scan a small local
                # window instead of relying on one fixed offset.
                back_range = max(0, i - 6)
                found_counts = False
                for j in range(back_range, min(i + 3, len(lines))):
                    cand = lines[j]
                    p = cand.split(',')
                    if len(p) >= 4:
                        try:
                            vc = int(p[0])
                            fc = int(p[2])
                            current_submesh['vertex_count'] = vc
                            current_submesh['face_count'] = fc
                            found_counts = True
                            break
                        except Exception:
                            continue
                if not found_counts:
                    current_submesh['vertex_count'] = None
                    current_submesh['face_count'] = None

            # Standard SMF vertices use 8 floats: position, extra per-vertex
            # data, and UV coordinates.
            if len(parts) == 8:
                if current_submesh is None:
                    i += 1
                    continue
                try:
                    v = [float(x) for x in parts]
                    current_submesh["vertices"].append(v)
                    self.vertices.append(v)
                except ValueError:
                    pass
                i += 1
                continue

            # Faces are triangle index triplets into the current submesh.
            if len(parts) == 3:
                try:
                    f = [int(x) for x in parts]
                    if current_submesh:
                        current_submesh["faces"].append(f)
                except ValueError:
                    pass
                i += 1
                continue

            # ---------------- Fallback: skip unknown line ----------------
            i += 1

        # Flush the last active submesh when the file ends without another header.
        if current_submesh:
            self.submeshes.append(current_submesh)

        # Preserve first-seen ordering while collapsing duplicate texture refs.
        for sm in self.submeshes:
            sm["textures"] = list(dict.fromkeys(sm.get("textures", [])))
        self.textures = list(dict.fromkeys(self.textures))

        # Return structured data
        return {
            "header": self.header,
            "version": self.version,
            "vertices": self.vertices,
            "submeshes": self.submeshes,
            "textures": self.textures,
        }
