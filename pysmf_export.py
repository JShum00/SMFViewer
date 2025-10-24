"""
SMF to OBJ Exporter
Author: Johnny Shumway (jShum00)

Converts a Terminal Reality .SMF model into a multi-object Wavefront .OBJ file.
Each SMF submesh is written as its own `o` section, preserving structure.
The exporter is compatible with Blender and other 3D software.
"""

import numpy as np
from tkinter import filedialog, Tk
from pysmf import SMFParser


def export_to_obj(smf_path, obj_path):
    """
    Convert a .SMF file into a Wavefront .OBJ file.

    Args:
        smf_path (str): Path to the source SMF file.
        obj_path (str): Destination path for the exported OBJ.

    Each SMF submesh becomes a separate OBJ object, maintaining
    the original subdivision structure. UVs are written if present.
    """
    parser = SMFParser()
    model = parser.parse(smf_path)

    with open(obj_path, 'w') as f:
        f.write("# Exported from Python-SMF Viewer\n")
        f.write(f"# Source: {smf_path}\n\n")

        vertex_offset = 0  # Global index offset between submeshes

        for sm_index, sm in enumerate(model['submeshes']):
            name = sm.get('name', f"Submesh_{sm_index}")
            verts = np.array(sm['vertices'])
            faces = sm['faces']

            f.write(f"o {name}\n")

            # Write vertex positions
            for v in verts:
                f.write(f"v {v[0]} {v[1]} {v[2]}\n")

            # Write texture coordinates if present (UVs)
            if verts.shape[1] >= 8:
                for v in verts:
                    f.write(f"vt {v[6]} {1.0 - v[7]}\n")  # flip V for Blender

            # Write triangle faces (OBJ indices start at 1)
            for face in faces:
                try:
                    i1, i2, i3 = [vi + 1 + vertex_offset for vi in face]
                    if verts.shape[1] >= 8:
                        f.write(f"f {i1}/{i1} {i2}/{i2} {i3}/{i3}\n")
                    else:
                        f.write(f"f {i1} {i2} {i3}\n")
                except Exception:
                    continue

            vertex_offset += len(verts)
            f.write("\n")

    print(f"[✔] Export complete: {obj_path}")


def main():
    """Open file dialogs to select an SMF file and export it as an OBJ."""
    root = Tk()
    root.withdraw()

    smf_path = filedialog.askopenfilename(
        title="Select SMF File",
        filetypes=[("SMF files", "*.smf"), ("All files", "*.*")]
    )
    if not smf_path:
        print("No SMF file selected.")
        return

    obj_path = filedialog.asksaveasfilename(
        title="Save OBJ As",
        defaultextension=".obj",
        filetypes=[("Wavefront OBJ", "*.obj")]
    )
    if not obj_path:
        print("No export path selected.")
        return

    export_to_obj(smf_path, obj_path)


if __name__ == "__main__":
    main()

