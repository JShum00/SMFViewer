"""Prepared model data used by the GUI render loop."""

from dataclasses import dataclass

import numpy as np

from pysmf import ParsedModel


@dataclass(slots=True)
class PreparedSubmesh:
    """Cached NumPy views used repeatedly during rendering."""

    vertices: np.ndarray | None
    positions: np.ndarray | None
    normals: np.ndarray | None
    light_factor: float


def normalize_vector(vector: np.ndarray) -> np.ndarray:
    """Return a normalized copy of a 3D vector, or zeros for degenerate input."""
    length = float(np.linalg.norm(vector))
    if length <= 1e-8:
        return np.zeros(3, dtype=np.float32)
    return (vector / length).astype(np.float32)


def build_vertex_normals(vertices: list[list[float]], faces: list[list[int]]) -> np.ndarray | None:
    """Build averaged per-vertex normals for a submesh."""
    if not vertices:
        return None

    positions = np.array(vertices, dtype=np.float32)[:, :3]
    normals = np.zeros_like(positions)
    vertex_count = positions.shape[0]

    for face in faces:
        if len(face) != 3:
            continue
        i0, i1, i2 = face
        if min(i0, i1, i2) < 0 or max(i0, i1, i2) >= vertex_count:
            continue

        edge_a = positions[i1] - positions[i0]
        edge_b = positions[i2] - positions[i0]
        face_normal = np.cross(edge_a, edge_b)
        face_length = float(np.linalg.norm(face_normal))
        if face_length <= 1e-8:
            continue

        face_normal /= face_length
        normals[i0] += face_normal
        normals[i1] += face_normal
        normals[i2] += face_normal

    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-8
    if np.any(valid):
        normals[valid] = normals[valid] / lengths[valid, np.newaxis]
    if np.any(~valid):
        normals[~valid] = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    return normals.astype(np.float32)


def compute_light_factor(
    normal: np.ndarray | None,
    light_direction: np.ndarray,
    ambient: float,
    diffuse_strength: float,
) -> float:
    """Collapse lighting to one multiplier so the GUI avoids per-vertex work."""
    if normal is None:
        return 1.0

    normal_length = float(np.linalg.norm(normal))
    if normal_length <= 1e-8:
        return 1.0

    unit_normal = normal / normal_length
    diffuse = max(0.0, float(np.dot(unit_normal, light_direction)))
    return max(0.0, min(1.0, ambient + diffuse_strength * diffuse))


def compute_submesh_light_factor(
    normals: np.ndarray | None,
    light_direction: np.ndarray,
    ambient: float,
    diffuse_strength: float,
) -> float:
    """Average submesh normals into one factor for the fast textured path."""
    if normals is None or len(normals) == 0:
        return 1.0

    average_normal = normals.mean(axis=0)
    return compute_light_factor(average_normal, light_direction, ambient, diffuse_strength)


def prepare_submeshes(
    model_data: ParsedModel,
    light_direction: np.ndarray,
    ambient: float,
    diffuse_strength: float,
) -> list[PreparedSubmesh]:
    """Convert submesh vertices into cached arrays once per model load."""
    prepared: list[PreparedSubmesh] = []
    for submesh in model_data["submeshes"]:
        if not submesh["vertices"]:
            prepared.append(PreparedSubmesh(vertices=None, positions=None, normals=None, light_factor=1.0))
            continue
        vertices = np.array(submesh["vertices"], dtype=np.float32)
        normals = build_vertex_normals(submesh["vertices"], submesh["faces"])
        prepared.append(
            PreparedSubmesh(
                vertices=vertices,
                positions=vertices[:, :3],
                normals=normals,
                light_factor=compute_submesh_light_factor(normals, light_direction, ambient, diffuse_strength),
            )
        )
    return prepared


def compute_model_metrics(model_data: ParsedModel) -> tuple[np.ndarray, float, int, int]:
    """Compute center, size, vertex count, and face count for the loaded model."""
    vertex_arrays = [
        np.array(submesh["vertices"], dtype=np.float32)
        for submesh in model_data["submeshes"]
        if submesh["vertices"]
    ]
    if not vertex_arrays:
        return np.zeros(3), 1.0, 0, 0

    verts = np.concatenate(vertex_arrays, axis=0)
    model_center = verts[:, :3].mean(axis=0)
    model_size = float(np.linalg.norm(np.ptp(verts[:, :3], axis=0)))
    total_verts = int(verts.shape[0])
    total_faces = sum(len(sm["faces"]) for sm in model_data["submeshes"])
    return model_center, model_size, total_verts, total_faces
