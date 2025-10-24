"""
SMF Parser
Author: Johnny Shumway (jShum00)

Parses Terminal Reality .SMF model files used in games like 4x4 Evolution 2.
Extracts vertex data, face indices, texture references, and submesh structure.

Each SMF file is read line-by-line with defensive parsing to handle small format variations.
The resulting data can be consumed by the SMF Viewer or exported to other 3D formats.
"""

class SMFParser:
    """Parser for Terminal Reality .SMF files."""

    def __init__(self):
        """Initialize storage for parsed model data."""
        self.vertices = []     # global vertex list (all submeshes)
        self.submeshes = []    # list of dicts, one per submesh
        self.textures = []     # list of unique texture filenames
        self.version = None    # SMF format version
        self.header = {}       # header info (e.g., C3DModel tag)

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

    # -------------------------------------------------------------------------

    def parse(self, path: str) -> dict:
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
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [ln.strip() for ln in f if ln.strip()]

        i = 0
        current_submesh = None

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
            # Submesh names are alphabetic tokens (e.g., "Body", "AxleR")
            if line.isalpha():
                if current_submesh:
                    self.submeshes.append(current_submesh)

                current_submesh = {
                    "name": line,
                    "vertices": [],
                    "faces": [],
                    "textures": []
                }

                # Attempt to read vertex/face count hints from nearby lines
                look = i + 1
                vertex_count = None
                face_count = None
                if look + 2 < len(lines):
                    candidate = lines[look + 2]
                    parts = candidate.split(',')
                    if len(parts) >= 4:
                        try:
                            vertex_count = int(parts[0])
                            face_count = int(parts[2])
                        except ValueError:
                            vertex_count = face_count = None

                i += 1
                continue

            # ---------------- Vertex marker (v1, v2...) ----------------
            if line.lower().startswith('v'):
                i += 1
                continue

            # ---------------- Texture references (.TIF) ----------------
            if ".TIF" in line.upper():
                tex = self._clean_tex(line)
                if current_submesh:
                    # Only record textures before vertex data begins
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
            if current_submesh and 'vertex_count' not in current_submesh:
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

            # ---------------- Vertex data (8 floats) ----------------
            if len(parts) == 8:
                try:
                    v = [float(x) for x in parts]
                    current_submesh["vertices"].append(v)
                    self.vertices.append(v)
                except ValueError:
                    pass
                i += 1
                continue

            # ---------------- Face data (3 ints) ----------------
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

        # Close final submesh
        if current_submesh:
            self.submeshes.append(current_submesh)

        # Deduplicate texture lists
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

