"""Material grouping and viewer-side render-role helpers."""

from pysmf import SubmeshMaterial

from pysmf_gui_types import MaterialPatternGroup, RenderRole, SubmeshPreviewState


def tuple_family_for_submesh(submesh: dict[str, object]) -> str:
    """Return the best-known tuple-pattern family for a submesh."""
    material = submesh.get("material")
    values = tuple(material["values"]) if isinstance(material, dict) and "values" in material else None
    if values is None:
        return "Unknown family"
    if values == ("1", "1", "64", "0", "1"):
        return "Body/Mirror family"
    if values == ("1", "1", "64", "1", "0"):
        return "GlassI family"
    if values == ("1", "1", "64", "1", "1"):
        return "GlassE family"
    if len(values) >= 3 and values[2] == "32":
        return "Light/Fog family"
    if values == ("1.25", "0", "0", "0", "0"):
        return "Cockpit family"
    if values == ("1", "0", "0", "0", "0"):
        return "Plain opaque family"
    return "Unknown family"


def render_role_for_submesh(submesh: dict[str, object]) -> RenderRole:
    """Classify a submesh into a coarse viewer render role."""
    name = str(submesh.get("name", ""))
    family = tuple_family_for_submesh(submesh)
    light_overlay_names = {
        "LightFL", "LightFR", "LightHL", "LightHR",
        "LightBL", "LightBR", "LightRL", "LightRR", "LightBC",
    }

    if family == "GlassI family":
        return "glass_interior"
    if family == "GlassE family":
        return "paint_glasse_frame"
    if family == "Light/Fog family" and name in light_overlay_names:
        return "light_overlay"
    if family == "Body/Mirror family" and name == "Body":
        return "paint_body"
    return "opaque_neutral"


def default_preview_state(material: SubmeshMaterial | None) -> SubmeshPreviewState:
    """Build initial preview state from parsed tuple values for research."""
    values = material["values"] if material is not None else ["", "", "", "", ""]
    opacity = 1.0
    try:
        if len(values) > 1 and values[1] != "":
            opacity = max(0.0, min(1.0, float(values[1])))
    except ValueError:
        opacity = 1.0

    def parse_flag(index: int) -> bool:
        try:
            return len(values) > index and float(values[index]) > 0.0
        except ValueError:
            return False

    return {
        "opacity": opacity,
        "exterior_transparent": parse_flag(3),
        "interior_transparent": parse_flag(4),
    }


def build_material_pattern_groups(
    submeshes: list[dict[str, object]],
) -> tuple[dict[tuple[str, ...], MaterialPatternGroup], list[tuple[str, ...] | None]]:
    """Build exact-tuple material groups and per-submesh key lookups."""
    material_pattern_groups: dict[tuple[str, ...], MaterialPatternGroup] = {}
    submesh_group_keys: list[tuple[str, ...] | None] = []
    grouped_names: dict[tuple[str, ...], list[str]] = {}
    ordered_keys: list[tuple[str, ...]] = []

    for submesh in submeshes:
        material = submesh.get("material")
        if not isinstance(material, dict):
            submesh_group_keys.append(None)
            continue

        key = tuple(material["values"])
        submesh_group_keys.append(key)
        if key not in grouped_names:
            grouped_names[key] = []
            ordered_keys.append(key)
        grouped_names[key].append(str(submesh["name"]))

    def build_note(names: list[str]) -> str:
        if len(names) == 1:
            return f"Unique to {names[0]}"
        for prefix in ("Light", "Fog", "Wiper", "Mirror"):
            if all(name.startswith(prefix) for name in names):
                return f"Shared by all {prefix}* meshes"
        return f"Shared by {len(names)} meshes"

    for index, key in enumerate(ordered_keys, start=1):
        members = grouped_names[key]
        material_pattern_groups[key] = {
            "group_id": f"G{index}",
            "values": list(key),
            "members": members,
            "note": build_note(members),
        }

    return material_pattern_groups, submesh_group_keys
