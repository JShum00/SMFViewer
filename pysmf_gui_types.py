"""Shared viewer-specific types and lightweight grouping helpers."""

from typing import TypeAlias, TypedDict

import numpy as np

from pysmf import ParsedModel


TexturePayload: TypeAlias = tuple[bytes, int, int]
RGBColor: TypeAlias = tuple[int, int, int]
RenderRole: TypeAlias = str


SUBMESH_GROUPS: list[tuple[str, str]] = [
    ("Lights", r"^light"),
    ("Foglights", r"^fog"),
    ("Glass", r"^glass"),
    ("Wheels", r"^(wheel|tire|axle)"),
    ("Body", r"^(body|mirror|cockpit|glass|spare|visor|clad)"),
    ("Accessories", r"^(roll|bush|bumper|steps?|skid|mud|snorkel|winch|wiper|rack|bed|antenna|flare|hscoop|fflare)"),
    ("Other", r".*"),
]


class PendingModelLoad(TypedDict):
    path: str
    model_data: ParsedModel
    model_center: np.ndarray
    model_size: float
    texture_payload: TexturePayload | None
    texture_prompt: dict[str, str] | None
    total_verts: int
    total_faces: int


class SubmeshPreviewState(TypedDict):
    opacity: float
    exterior_transparent: bool
    interior_transparent: bool


class MaterialPatternGroup(TypedDict):
    group_id: str
    values: list[str]
    members: list[str]
    note: str


class SidebarGroup(TypedDict):
    label: str
    submesh_indices: list[int]


class ParsedTRK(TypedDict):
    truckName: str
    truckModel: str
    truckClass: str
    truckCost: str
    truckModelYear: str
    truckLength: str
    truckHeight: str
    truckWheelbase: str
    truckFrontTrack: str
    truckRearTrack: str
    truckAcceleration: str
    truckTopSpeed: str
    truckHandling: str
    tireModelBaseName: str
    teamRequirement: str
    eng_maxHP: str
    eng_maxHPRPM: str
    eng_maxTorque: str
    eng_redline: str
    eng_displacement: str
    numColors: str
    colorList: list[RGBColor]
    numStockParts: str
    stockPartList: list[str]


class ModalEntry(TypedDict):
    label: str
    path: str
    is_dir: bool


class ViewerSettings(TypedDict):
    default_smf_dir: str
    default_trk_dir: str
    default_tif_dir: str
