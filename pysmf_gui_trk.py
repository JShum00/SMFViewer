"""TRK parsing and lookup helpers used by the GUI."""

import json
import os
from pathlib import Path

from pysmf_gui_types import ParsedTRK, RGBColor


def load_trk_map(map_path: Path) -> dict[str, list[str]]:
    """Load the TRK filename map from disk."""
    if not map_path.exists():
        print(f"Warning: TRK map not found at {map_path}")
        return {}

    try:
        raw_map = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: failed to load TRK map {map_path}: {exc}")
        return {}

    cleaned: dict[str, list[str]] = {}
    if not isinstance(raw_map, dict):
        print(f"Warning: TRK map has unexpected format in {map_path}")
        return cleaned

    for key, value in raw_map.items():
        if isinstance(key, str) and isinstance(value, list):
            cleaned[key.upper()] = [str(item) for item in value]
    print(f"Loaded TRK map with {len(cleaned)} model entries from {map_path}")
    return cleaned


def default_trk_data() -> ParsedTRK:
    """Return a default TRK payload structure."""
    return {
        "truckName": "Unknown",
        "truckModel": "",
        "truckClass": "",
        "truckCost": "",
        "truckModelYear": "",
        "truckLength": "",
        "truckHeight": "",
        "truckWheelbase": "",
        "truckFrontTrack": "",
        "truckRearTrack": "",
        "truckAcceleration": "",
        "truckTopSpeed": "",
        "truckHandling": "",
        "tireModelBaseName": "",
        "teamRequirement": "",
        "eng_maxHP": "",
        "eng_maxHPRPM": "",
        "eng_maxTorque": "",
        "eng_redline": "",
        "eng_displacement": "",
        "numColors": "0",
        "colorList": [],
        "numStockParts": "0",
        "stockPartList": [],
    }


def parse_rgb_color(color_line: str) -> RGBColor | None:
    """Parse a TRK HSV/RGB color line and return its RGB tuple."""
    parts = [part.strip() for part in color_line.split(",")]
    if len(parts) < 6:
        return None
    try:
        rgb = tuple(max(0, min(255, int(parts[index]))) for index in (3, 4, 5))
    except ValueError:
        return None
    return rgb  # type: ignore[return-value]


def parse_trk_file(trk_path: str) -> ParsedTRK:
    """Parse a TRK file for the limited set of fields used by the specs UI."""
    data = default_trk_data()
    key_map = {
        "truckName": "truckName",
        "truckModel": "truckModel",
        "truckClass": "truckClass",
        "truckCost": "truckCost",
        "truckModelYear": "truckModelYear",
        "truckLength": "truckLength",
        "truckHeight": "truckHeight",
        "truckWheelbase": "truckWheelbase",
        "truckFrontTrack": "truckFrontTrack",
        "truckRearTrack": "truckRearTrack",
        "truckAcceleration": "truckAcceleration",
        "truckTopSpeed": "truckTopSpeed",
        "truckHandling": "truckHandling",
        "tireModelBaseName": "tireModelBaseName",
        "teamRequirement": "teamRequirement",
        "eng.maxHP": "eng_maxHP",
        "eng.maxHPRPM": "eng_maxHPRPM",
        "eng.maxTorque": "eng_maxTorque",
        "eng.redline": "eng_redline",
        "eng.displacement": "eng_displacement",
        "numColors": "numColors",
        "numStockParts": "numStockParts",
    }

    lines = Path(trk_path).read_text(encoding="utf-8", errors="replace").splitlines()
    index = 0
    while index < len(lines):
        key = lines[index].strip()
        if key in key_map and index + 1 < len(lines):
            data[key_map[key]] = lines[index + 1].strip()  # type: ignore[index]
            index += 2
            continue

        if key == "colorList[]":
            try:
                count = int(data["numColors"])
            except ValueError:
                count = 0
            colors: list[RGBColor] = []
            start = index + 1
            for offset in range(count):
                if start + offset >= len(lines):
                    break
                parsed = parse_rgb_color(lines[start + offset].strip())
                if parsed is not None:
                    colors.append(parsed)
            data["colorList"] = colors
            index = start + count
            continue

        if key == "stockPartList[]":
            try:
                count = int(data["numStockParts"])
            except ValueError:
                count = 0
            if count <= 0:
                data["stockPartList"] = ["EMPTY"]
                index += 1
                continue

            start = index + 1
            parts = [lines[start + offset].strip() for offset in range(count) if start + offset < len(lines)]
            data["stockPartList"] = parts if parts else ["EMPTY"]
            index = start + count
            continue

        index += 1

    if data["numStockParts"] == "0" and not data["stockPartList"]:
        data["stockPartList"] = ["EMPTY"]
    return data


def resolve_trk_candidates(trk_map: dict[str, list[str]], model_key: str, trk_dir: str) -> list[str]:
    """Resolve mapped TRK filenames against a concrete directory."""
    candidates: list[str] = []
    for filename in trk_map.get(model_key, []):
        candidate = os.path.join(trk_dir, filename)
        if os.path.isfile(candidate):
            candidates.append(candidate)
    return candidates
