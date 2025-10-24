"""
SMF Summary Printer
Author: Johnny Shumway (jShum00)

Reads a Terminal Reality .SMF file using SMFParser and prints a formatted summary:
  - Version
  - Submesh count
  - Vertex/triangle totals
  - Textures per submesh
"""

from pysmf import SMFParser


def print_smf_summary(path: str):
    """Parse an SMF file and print its contents in a readable format."""
    parser = SMFParser()
    data = parser.parse(path)

    print("\n============================ SMF MODEL SUMMARY ============================")
    print(f"File: {path}")
    print(f"Version: {data['version']}")
    print(f"Submeshes: {len(data['submeshes'])}")
    print(f"Total Vertices: {len(data['vertices'])}")
    print(f"Textures: {', '.join(data['textures']) if data['textures'] else 'None'}")
    print("---------------------------------------------------------------------------")

    for sm in data["submeshes"]:
        vc = sm.get("vertex_count")
        fc = sm.get("face_count")
        vc_display = f"{len(sm['vertices'])}" if vc is None else f"{len(sm['vertices'])} (hdr:{vc})"
        fc_display = f"{len(sm['faces'])}" if fc is None else f"{len(sm['faces'])} (hdr:{fc})"

        tex_display = ", ".join(sm["textures"]) if sm["textures"] else "None"
        print(f"  {sm['name']:<12} | {vc_display:>8} verts | {fc_display:>8} tris | {tex_display}")

    print("=========================================================================\n")


if __name__ == "__main__":
    # For manual testing
    print_smf_summary("Test.smf")

