#!/usr/bin/env python3
"""
POD → SMF Extractor
Author: Johnny Shumway (JShum00)

Purpose:
    Stream-extracts individual .SMF models from a .POD file used in Terminal Reality games.
    Each SMF chunk begins with 'C3DModel' and ends before the next one.
    When a texture line is found (e.g. 'GMCJimmy_bump.TIF'), the file is renamed accordingly.

Usage:
    python pod_smf_extract.py <input_pod> <output_dir>
"""

from pathlib import Path


def extract_smfs_from_pod(pod_path: str, output_dir: str) -> None:
    """Extracts SMF models from a POD file into the specified output directory."""
    pod_path = Path(pod_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    smf_count = 0
    current_file = None
    current_path = None

    print(f"[*] Extracting SMFs from: {pod_path}")
    print(f"[*] Output directory: {output_dir}\n")

    with pod_path.open("rb") as pod_file:
        for raw_line in pod_file:
            stripped = raw_line.strip()

            # Start of a new SMF
            if stripped == b"C3DModel":
                if current_file:
                    current_file.close()
                    smf_count += 1
                    print(f"[+] Finished SMF #{smf_count:04d}: {current_path.name}")

                filename = f"smf_{smf_count:04d}.smf"
                current_path = output_dir / filename
                current_file = current_path.open("wb")
                print(f"[*] Started new SMF → {current_path.name}")

            if current_file:
                current_file.write(raw_line)

                # Detect texture reference for renaming
                if b"_bump.TIF" in stripped:
                    try:
                        text = stripped.decode("utf-8").strip('"')
                        model_name = text.split("_")[0]
                        new_path = output_dir / f"{model_name}.smf"

                        if new_path != current_path:
                            current_file.close()
                            current_path.rename(new_path)
                            print(f"[↻ ] Renamed: {current_path.name} → {new_path.name}")
                            current_path = new_path
                            current_file = current_path.open("ab")

                    except UnicodeDecodeError:
                        print(f"[!] Warning: Could not decode line while renaming: {stripped!r}")
                    except Exception as exc:
                        print(f"[!] Warning: Failed to rename SMF: {exc}")

        # finalize
        if current_file:
            current_file.close()
            smf_count += 1
            print(f"[+] Finished SMF #{smf_count:04d}: {current_path.name}")

    print(f"\n[✓] Extraction complete. {smf_count} SMFs written from {pod_path.name} → {output_dir}")


def main():
    import sys

    if len(sys.argv) != 3:
        print("Usage: python pod_smf_extract.py <pod_file> <output_directory>")
        return

    extract_smfs_from_pod(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
