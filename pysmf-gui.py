"""
Python-SMF Viewer GUI
Author: Johnny Shumway (jShum00)

A simple 3D model viewer for Terminal Reality .SMF files.
Uses PyGame + PyOpenGL for real-time rendering and Tkinter for file dialogs.

Controls:
  O: Open SMF model
  E: Export to OBJ
  W: Toggle wireframe
  M: Texture View
  Left/Right: Orbit camera left/right
  Up/Down: Camera Zoom
  CTRL + Left/Right: Fast orbit (2x speed)
  CTRL + Up/Down: Fast camera zoom
  Numpad +/-: Camera Zoom
  Right Mouse Drag: Orbit camera left/right
  Mouse Wheel: Camera Zoom
  SPACE: Legacy no-op
  ESC: Quit viewer
"""

import math
import os
import threading
from typing import TypeAlias, TypedDict

import numpy as np
import pygame
from PIL import Image
from OpenGL.GL import (
    GL_BLEND,
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_FILL,
    GL_FRONT_AND_BACK,
    GL_LINEAR,
    GL_LINE,
    GL_LINES,
    GL_MODELVIEW,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_PROJECTION,
    GL_QUADS,
    GL_RGBA,
    GL_SRC_ALPHA,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TRIANGLES,
    GL_UNSIGNED_BYTE,
    glBegin,
    glBindTexture,
    glBlendFunc,
    glClear,
    glClearColor,
    glColor3f,
    glColor4f,
    glDeleteTextures,
    glDisable,
    glEnable,
    glEnd,
    glGenTextures,
    glLoadIdentity,
    glMatrixMode,
    glOrtho,
    glPolygonMode,
    glPopMatrix,
    glPushMatrix,
    glRasterPos2f,
    glTexCoord2f,
    glTexImage2D,
    glTexParameteri,
    glTranslatef,
    glVertex2f,
    glVertex3f,
    glViewport,
)
from OpenGL.GLU import gluLookAt, gluPerspective
from OpenGL.GLUT import glutInit, glutBitmapCharacter, GLUT_BITMAP_HELVETICA_18 # type: ignore
from pygame.locals import (
    DOUBLEBUF,
    KEYDOWN,
    KMOD_CTRL,
    K_BACKSPACE,
    K_DOWN,
    K_ESCAPE,
    K_KP_MINUS,
    K_KP_ENTER,
    K_KP_PLUS,
    K_LEFT,
    K_RIGHT,
    K_UP,
    K_RETURN,
    K_SPACE,
    K_TAB,
    K_e,
    K_m,
    K_o,
    K_w,
    MOUSEBUTTONDOWN,
    MOUSEMOTION,
    MOUSEBUTTONUP,
    OPENGL,
    QUIT,
    RESIZABLE,
    TEXTINPUT,
    VIDEORESIZE,
)
from tkinter import Tk, filedialog, messagebox

from pysmf import ParsedModel, SMFParser, SubmeshMaterial
from pysmf_export import export_to_obj
from pysmf_print import print_smf_summary


TexturePayload: TypeAlias = tuple[bytes, int, int]


class PendingModelLoad(TypedDict):
    path: str
    model_data: ParsedModel
    model_center: np.ndarray
    model_size: float
    texture_payload: TexturePayload | None
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


class SMFViewer:
    """A basic OpenGL-based SMF model viewer with orbit camera and OBJ export."""

    def __init__(self, width: int = 1600, height: int = 900) -> None:
        """Initialize window, OpenGL context, and default state."""
        pygame.init()
        glutInit()
        self.width = width
        self.height = height
        self.min_width = 1280
        self.min_height = 720
        self.toolbar_height = 64
        self.statusbar_height = 34
        self.sidebar_width = 280
        self.inspector_width = 360
        pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL | RESIZABLE)
        pygame.display.set_caption("PySMF - SMF Viewer")

        self._configure_3d_viewport()

        # Default OpenGL state
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glEnable(GL_DEPTH_TEST)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)  # start in wireframe mode

        # UI hitboxes are rebuilt every frame because layout depends on window
        # size, hover state, and which sidebar groups are expanded.
        self.button_labels: list[str] = ["Open", "Export", "Wireframe", "Texture", "Exit", "Opacity"]
        self.buttons: list[tuple[int, int, int, int]] = []
        self.hover_index: int | None = None
        self.mesh_row_rects: list[tuple[int, int, int, int]] = []
        self.mesh_eye_rects: list[tuple[int, int, int, int]] = []
        self.mesh_row_indices: list[int] = []
        self.mesh_eye_indices: list[int] = []
        self.group_header_rects: list[tuple[int, int, int, int]] = []
        self.group_arrow_rects: list[tuple[int, int, int, int]] = []
        self.group_header_indices: list[int] = []
        self.hover_mesh_row_index: int | None = None
        self.hover_mesh_eye_index: int | None = None
        self.hover_group_header_index: int | None = None
        self.sidebar_scroll_offset = 0.0
        self.sidebar_content_height = 0.0
        self.sidebar_visible_height = 0.0
        self.sidebar_scrollbar_track: tuple[int, int, int, int] | None = None
        self.sidebar_scrollbar_thumb: tuple[int, int, int, int] | None = None
        self.dragging_sidebar_thumb = False
        self.sidebar_drag_offset = 0.0
        self.dragging_camera_orbit = False
        self.material_field_rects: list[tuple[int, int, int, int]] = []
        self.hover_material_field_index: int | None = None

        # Parsed model state plus session-local selection/inspector state.
        self.model_data: ParsedModel | None = None
        self.model_center: np.ndarray = np.array([0.0, 0.0, 0.0])
        self.model_size: float = 1.0
        self.last_loaded_path: str | None = None
        self.texture_id: int | None = None
        self.submesh_visibility: list[bool] = []
        self.selected_submesh_index: int | None = None
        self.active_material_field_index: int | None = None
        self.editable_material_values: list[list[str]] = []
        self.submesh_preview_states: list[SubmeshPreviewState] = []
        self.material_pattern_groups: dict[tuple[str, ...], MaterialPatternGroup] = {}
        self.submesh_group_keys: list[tuple[str, ...] | None] = []
        self.sidebar_groups: list[SidebarGroup] = []
        self.sidebar_group_expanded: list[bool] = []
        self.inspector_status_message = "Pattern inspector is primary. Live preview remains heuristic."
        self._state_lock = threading.Lock()
        self._pending_model_load: PendingModelLoad | None = None

        # Render toggles affect only the current viewer session.
        self.wireframe = True
        self.show_texture = False
        self.render_assumed_opacity = True

        # Simple orbit camera around the current model center.
        self.camera_radius = 20.0    # how far we orbit from target
        self.camera_angle_az = 25.0  # degrees around Y-axis
        self.camera_height = 4.0     # height above ground
        self.camera_min_radius = 2.0
        self.camera_zoom_step = 1.0
        self.camera_fast_zoom_step = 2.0
        self.camera_orbit_step = 1.0

    # -------------------------------------------------------------------------

    def _adjust_camera_zoom(self, delta: float) -> None:
        """Apply a signed zoom delta while keeping the camera radius valid."""
        self.camera_radius = max(self.camera_min_radius, self.camera_radius + delta)

    # -------------------------------------------------------------------------

    def _set_camera_orbit_drag(self, active: bool) -> None:
        """Toggle relative-motion orbit drag mode for the right mouse button."""
        self.dragging_camera_orbit = active
        pygame.mouse.set_visible(not active)
        pygame.event.set_grab(active)

    # -------------------------------------------------------------------------

    def _create_dialog_root(self) -> Tk:
        """Create a hidden Tk root that stays above the pygame window for dialogs."""
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.lift()
        root.update()
        return root

    # -------------------------------------------------------------------------

    def _configure_3d_viewport(self) -> None:
        """Reserve space for the toolbar and status bar and update the 3D projection."""
        # The central 3D viewport excludes the sidebar and inspector; those panels
        # are drawn afterward as 2D overlays.
        viewport_height = max(1, self.height - self.toolbar_height - self.statusbar_height)
        viewport_width = max(1, self.width - self.sidebar_width - self.inspector_width)
        glViewport(self.sidebar_width, self.statusbar_height, viewport_width, viewport_height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, viewport_width / viewport_height, 0.1, 1000.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    # -------------------------------------------------------------------------

    def _button_width(self, label: str) -> int:
        """Approximate button width for GLUT bitmap text."""
        return max(110, 28 + len(label) * 11)

    # -------------------------------------------------------------------------

    def _set_window_size(self, width: int, height: int) -> None:
        """Clamp and apply the current window size."""
        self.width = max(self.min_width, width)
        self.height = max(self.min_height, height)
        pygame.display.set_mode((self.width, self.height), DOUBLEBUF | OPENGL | RESIZABLE)
        self._configure_3d_viewport()

    # -------------------------------------------------------------------------

    def _clamp_sidebar_scroll(self) -> None:
        """Clamp the sidebar scroll offset to the current content range."""
        max_scroll = max(0.0, self.sidebar_content_height - self.sidebar_visible_height)
        self.sidebar_scroll_offset = max(0.0, min(self.sidebar_scroll_offset, max_scroll))

    # -------------------------------------------------------------------------

    def _scroll_sidebar(self, delta: float) -> None:
        """Scroll the sidebar list by a signed number of pixels."""
        self.sidebar_scroll_offset += delta
        self._clamp_sidebar_scroll()

    # -------------------------------------------------------------------------

    def _point_in_rect(self, x: int, y: int, rect: tuple[int, int, int, int] | None) -> bool:
        """Return True when a screen-space point lies inside a rect."""
        if rect is None:
            return False
        left, top, right, bottom = rect
        return left <= x <= right and top <= y <= bottom

    def _draw_text(self, x: float, y: float, text: str) -> None:
        """Draw GLUT bitmap text in 2D overlay coordinates."""
        glRasterPos2f(x, y)
        for ch in text:
            glutBitmapCharacter(GLUT_BITMAP_HELVETICA_18, ord(ch))

    # -------------------------------------------------------------------------

    def _truncate_text(self, text: str, max_chars: int) -> str:
        """Return a shortened label that fits the fixed-width overlay UI."""
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars - 3]}..."

    # -------------------------------------------------------------------------

    def _material_for_submesh(self, submesh_index: int) -> SubmeshMaterial | None:
        """Return parsed material metadata for a submesh when available."""
        if self.model_data is None or not (0 <= submesh_index < len(self.model_data["submeshes"])):
            return None
        return self.model_data["submeshes"][submesh_index]["material"]

    # -------------------------------------------------------------------------

    def _texture_for_submesh(self, submesh_index: int) -> str:
        """Return the best-known texture label for a submesh."""
        if self.model_data is None or not (0 <= submesh_index < len(self.model_data["submeshes"])):
            return "None"

        submesh = self.model_data["submeshes"][submesh_index]
        material = submesh["material"]
        if material is not None:
            return material["texture"]
        if submesh["textures"]:
            return submesh["textures"][0]
        return "None"

    # -------------------------------------------------------------------------

    def _current_material_line(self, submesh_index: int) -> str:
        """Return the current session-only material line for a submesh."""
        values = self.editable_material_values[submesh_index]
        texture = self._texture_for_submesh(submesh_index)
        return ",".join(values + [texture])

    # -------------------------------------------------------------------------

    def _committed_material_line(self, submesh_index: int) -> str:
        """Return the committed preview line for a submesh."""
        if not (0 <= submesh_index < len(self.editable_material_values)):
            return "No committed preview"

        committed = self.editable_material_values[submesh_index].copy()
        preview = self.submesh_preview_states[submesh_index]
        committed[1] = f"{preview['opacity']:.3f}".rstrip("0").rstrip(".") if "." in f"{preview['opacity']:.3f}" else f"{preview['opacity']:.3f}"
        committed[3] = "1" if preview["exterior_transparent"] else "0"
        committed[4] = "1" if preview["interior_transparent"] else "0"
        texture = self._texture_for_submesh(submesh_index)
        return ",".join(committed + [texture])

    # -------------------------------------------------------------------------

    def _pattern_key_for_submesh(self, submesh_index: int) -> tuple[str, ...] | None:
        """Return the parsed material tuple for a submesh when available."""
        material = self._material_for_submesh(submesh_index)
        if material is None:
            return None
        return tuple(material["values"])

    # -------------------------------------------------------------------------

    def _build_material_pattern_groups(self) -> None:
        """Build exact-tuple material groups for the loaded model."""
        self.material_pattern_groups = {}
        self.submesh_group_keys = []
        if self.model_data is None:
            return

        grouped_names: dict[tuple[str, ...], list[str]] = {}
        ordered_keys: list[tuple[str, ...]] = []

        for submesh in self.model_data["submeshes"]:
            material = submesh["material"]
            if material is None:
                self.submesh_group_keys.append(None)
                continue

            # Group by the exact 5-value tuple so repeated material patterns are
            # easy to compare across multiple submeshes.
            key = tuple(material["values"])
            self.submesh_group_keys.append(key)
            if key not in grouped_names:
                grouped_names[key] = []
                ordered_keys.append(key)
            grouped_names[key].append(submesh["name"])

        def build_note(names: list[str]) -> str:
            if len(names) == 1:
                return f"Unique to {names[0]}"
            for prefix in ("Light", "Fog", "Wiper", "Mirror"):
                if all(name.startswith(prefix) for name in names):
                    return f"Shared by all {prefix}* meshes"
            return f"Shared by {len(names)} meshes"

        for index, key in enumerate(ordered_keys, start=1):
            members = grouped_names[key]
            self.material_pattern_groups[key] = {
                "group_id": f"G{index}",
                "values": list(key),
                "members": members,
                "note": build_note(members),
            }

    # -------------------------------------------------------------------------

    def _pattern_group_for_submesh(self, submesh_index: int) -> MaterialPatternGroup | None:
        """Return the material group for the selected submesh."""
        if not (0 <= submesh_index < len(self.submesh_group_keys)):
            return None
        key = self.submesh_group_keys[submesh_index]
        if key is None:
            return None
        return self.material_pattern_groups.get(key)

    # -------------------------------------------------------------------------

    def _sidebar_group_label(self, name: str) -> str:
        """Return the sidebar group label for a submesh name."""
        prefixes = (
            ("Fog", "Foglights"),
            ("Glass", "Glass"),
            ("Light", "Lights"),
            ("Mirror", "Mirrors"),
            ("Wiper", "Wipers"),
        )
        for prefix, label in prefixes:
            if name.startswith(prefix):
                return label
        return "Other"

    # -------------------------------------------------------------------------

    def _build_sidebar_groups(self) -> None:
        """Build sidebar groups from submesh name prefixes."""
        self.sidebar_groups = []
        self.sidebar_group_expanded = []
        if self.model_data is None:
            return

        order = ["Foglights", "Glass", "Lights", "Mirrors", "Wipers", "Other"]
        grouped: dict[str, list[int]] = {label: [] for label in order}
        for index, submesh in enumerate(self.model_data["submeshes"]):
            grouped[self._sidebar_group_label(submesh["name"])].append(index)

        for label in order:
            if grouped[label]:
                self.sidebar_groups.append({
                    "label": label,
                    "submesh_indices": grouped[label],
                })
                self.sidebar_group_expanded.append(False)

    # -------------------------------------------------------------------------

    def _default_preview_state(self, material: SubmeshMaterial | None) -> SubmeshPreviewState:
        """Build initial preview state from parsed submesh material values."""
        values = material["values"] if material is not None else ["", "", "", "", ""]
        opacity = 1.0
        try:
            if values[1] != "":
                opacity = max(0.0, min(1.0, float(values[1])))
        except (IndexError, ValueError):
            opacity = 1.0

        # The fourth and fifth parsed values are treated as transparency flags.
        def parse_flag(index: int) -> bool:
            try:
                return float(values[index]) > 0.0
            except (IndexError, ValueError):
                return False

        return {
            "opacity": opacity,
            "exterior_transparent": parse_flag(3),
            "interior_transparent": parse_flag(4),
        }

    # -------------------------------------------------------------------------

    def _submit_material_field(self) -> None:
        """Commit the active inspector field into preview state."""
        if self.selected_submesh_index is None or self.active_material_field_index is None:
            return

        submesh_index = self.selected_submesh_index
        field_index = self.active_material_field_index
        raw_value = self.editable_material_values[submesh_index][field_index].strip()
        submesh_name = self.model_data["submeshes"][submesh_index]["name"] if self.model_data is not None else "submesh"

        # Only a subset of the tuple currently drives preview behavior; the other
        # fields are still editable so they can be inspected and compared.
        try:
            if field_index == 1:
                parsed = float(raw_value)
                self.submesh_preview_states[submesh_index]["opacity"] = max(0.0, min(1.0, parsed))
                self.inspector_status_message = (
                    f"{submesh_name}: committed Value 2 opacity = "
                    f"{self.submesh_preview_states[submesh_index]['opacity']:.3f}"
                )
            elif field_index == 3:
                parsed = float(raw_value)
                self.submesh_preview_states[submesh_index]["exterior_transparent"] = parsed > 0.0
                state = "on" if self.submesh_preview_states[submesh_index]["exterior_transparent"] else "off"
                self.inspector_status_message = f"{submesh_name}: committed Value 4 exterior transparency = {state}"
            elif field_index == 4:
                parsed = float(raw_value)
                self.submesh_preview_states[submesh_index]["interior_transparent"] = parsed > 0.0
                state = "on" if self.submesh_preview_states[submesh_index]["interior_transparent"] else "off"
                self.inspector_status_message = f"{submesh_name}: committed Value 5 interior transparency = {state}"
            else:
                self.inspector_status_message = (
                    f"{submesh_name}: Value {field_index + 1} stored for research; preview unchanged."
                )
            print(self.inspector_status_message)
        except ValueError:
            self.inspector_status_message = (
                f"{submesh_name}: invalid numeric input for Value {field_index + 1}; preview unchanged."
            )
            print(self.inspector_status_message)
        finally:
            self.active_material_field_index = None

    def _texture_status_label(self) -> str:
        """Return the current texture toggle status for the toolbar."""
        if self.texture_id is None:
            return "Texture: Unavailable"
        return f"Texture: {'On' if self.show_texture else 'Off'}"

    # -------------------------------------------------------------------------

    def _status_labels(self) -> list[str]:
        """Return compact status-strip text."""
        file_label = (
            f"File: {os.path.basename(self.last_loaded_path)}"
            if self.last_loaded_path is not None
            else "File: No model loaded"
        )
        visible_submeshes = sum(1 for visible in self.submesh_visibility if visible)
        total_submeshes = len(self.submesh_visibility)
        return [
            file_label,
            f"Wireframe: {'On' if self.wireframe else 'Off'}",
            self._texture_status_label(),
            f"Assumed Opacity: {'On' if self.render_assumed_opacity else 'Off'}",
            f"Visible: {visible_submeshes}/{total_submeshes}",
        ]

    # -------------------------------------------------------------------------

    def _handle_button_action(self, label: str) -> bool:
        """Execute a toolbar action. Returns False when the viewer should exit."""
        print(f"[UI] {label} clicked")
        if label == "Exit":
            return False
        if label == "Wireframe":
            self.toggle_wireframe()
        elif label == "Texture":
            self.toggle_texture()
        elif label == "Open":
            threading.Thread(target=self.load_smf, daemon=True).start()
        elif label == "Export":
            threading.Thread(target=self.export_obj, daemon=True).start()
        elif label == "Opacity":
            self.render_assumed_opacity = not self.render_assumed_opacity
            print("Assumed SMF opacity:", self.render_assumed_opacity)
        return True

    # -------------------------------------------------------------------------

    def _draw_toolbar(self) -> None:
        """Render the persistent top toolbar and update button hitboxes."""
        toolbar_top = 0
        toolbar_bottom = self.toolbar_height
        toolbar_alpha = 0.95

        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glColor4f(0.12, 0.12, 0.12, toolbar_alpha)
        glBegin(GL_QUADS)
        glVertex2f(0, toolbar_top)
        glVertex2f(self.width, toolbar_top)
        glVertex2f(self.width, toolbar_bottom)
        glVertex2f(0, toolbar_bottom)
        glEnd()

        glColor4f(0.22, 0.22, 0.22, 1.0)
        glBegin(GL_QUADS)
        glVertex2f(0, toolbar_bottom - 2)
        glVertex2f(self.width, toolbar_bottom - 2)
        glVertex2f(self.width, toolbar_bottom)
        glVertex2f(0, toolbar_bottom)
        glEnd()

        self.buttons = []
        top = 12
        bottom = toolbar_bottom - 12

        # Keep Exit separated on the far right so it behaves like a global action.
        left_labels = self.button_labels[:-1]
        right_label = self.button_labels[-1]
        left = 16

        for label in left_labels:
            width = self._button_width(label)
            right = left + width
            self.buttons.append((left, top, right, bottom))
            button_index = len(self.buttons) - 1

            if button_index == self.hover_index:
                glColor4f(0.34, 0.34, 0.34, 1.0)
            else:
                glColor4f(0.24, 0.24, 0.24, 1.0)

            glBegin(GL_QUADS)
            glVertex2f(left, top)
            glVertex2f(right, top)
            glVertex2f(right, bottom)
            glVertex2f(left, bottom)
            glEnd()

            glColor4f(0.42, 0.42, 0.42, 1.0)
            glBegin(GL_LINES)
            glVertex2f(left, top)
            glVertex2f(right, top)
            glVertex2f(right, top)
            glVertex2f(right, bottom)
            glVertex2f(right, bottom)
            glVertex2f(left, bottom)
            glVertex2f(left, bottom)
            glVertex2f(left, top)
            glEnd()

            glColor3f(1.0, 1.0, 1.0)
            self._draw_text(left + 14, top + 22, label)
            left = right + 12

        right_width = self._button_width(right_label) + 18
        right = self.width - 16
        left = right - right_width
        self.buttons.append((left, top, right, bottom))
        button_index = len(self.buttons) - 1

        if button_index == self.hover_index:
            glColor4f(0.34, 0.34, 0.34, 1.0)
        else:
            glColor4f(0.24, 0.24, 0.24, 1.0)

        glBegin(GL_QUADS)
        glVertex2f(left, top)
        glVertex2f(right, top)
        glVertex2f(right, bottom)
        glVertex2f(left, bottom)
        glEnd()

        glColor4f(0.42, 0.42, 0.42, 1.0)
        glBegin(GL_LINES)
        glVertex2f(left, top)
        glVertex2f(right, top)
        glVertex2f(right, top)
        glVertex2f(right, bottom)
        glVertex2f(right, bottom)
        glVertex2f(left, bottom)
        glVertex2f(left, bottom)
        glVertex2f(left, top)
        glEnd()

        glColor3f(1.0, 1.0, 1.0)
        self._draw_text(left + 14, top + 22, right_label)

        glDisable(GL_BLEND)
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glEnable(GL_DEPTH_TEST)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe else GL_FILL)
        self._configure_3d_viewport()

    # -------------------------------------------------------------------------

    def _draw_eye_icon(self, left: int, top: int, right: int, bottom: int, visible: bool, hovered: bool) -> None:
        """Draw a minimal eye icon for sidebar visibility toggles."""
        mid_x = (left + right) / 2
        mid_y = (top + bottom) / 2
        half_width = (right - left) * 0.36
        half_height = (bottom - top) * 0.22

        if hovered:
            glColor4f(0.30, 0.30, 0.30, 1.0)
            glBegin(GL_QUADS)
            glVertex2f(left, top)
            glVertex2f(right, top)
            glVertex2f(right, bottom)
            glVertex2f(left, bottom)
            glEnd()

        glColor3f(0.92, 0.92, 0.92) if visible else glColor3f(0.46, 0.46, 0.46)
        glBegin(GL_LINES)
        glVertex2f(mid_x - half_width, mid_y)
        glVertex2f(mid_x, mid_y - half_height)
        glVertex2f(mid_x, mid_y - half_height)
        glVertex2f(mid_x + half_width, mid_y)
        glVertex2f(mid_x + half_width, mid_y)
        glVertex2f(mid_x, mid_y + half_height)
        glVertex2f(mid_x, mid_y + half_height)
        glVertex2f(mid_x - half_width, mid_y)
        glEnd()

        iris_half = 2 if visible else 1
        glBegin(GL_QUADS)
        glVertex2f(mid_x - iris_half, mid_y - iris_half)
        glVertex2f(mid_x + iris_half, mid_y - iris_half)
        glVertex2f(mid_x + iris_half, mid_y + iris_half)
        glVertex2f(mid_x - iris_half, mid_y + iris_half)
        glEnd()

        if not visible:
            glBegin(GL_LINES)
            glVertex2f(left + 4, bottom - 4)
            glVertex2f(right - 4, top + 4)
            glEnd()

    # -------------------------------------------------------------------------

    def _draw_sidebar(self) -> None:
        """Render the left mesh tree and per-submesh visibility controls."""
        sidebar_top = self.toolbar_height
        sidebar_bottom = self.height - self.statusbar_height
        row_height = 28
        row_gap = 6
        root_left = 14
        text_left = root_left + 12
        child_left = root_left + 24
        eye_size = 18
        scrollbar_width = 12
        scrollbar_margin = 10
        row_width = self.sidebar_width - 28 - scrollbar_width - scrollbar_margin

        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glColor4f(0.11, 0.11, 0.11, 0.96)
        glBegin(GL_QUADS)
        glVertex2f(0, sidebar_top)
        glVertex2f(self.sidebar_width, sidebar_top)
        glVertex2f(self.sidebar_width, sidebar_bottom)
        glVertex2f(0, sidebar_bottom)
        glEnd()

        glColor4f(0.20, 0.20, 0.20, 1.0)
        glBegin(GL_QUADS)
        glVertex2f(self.sidebar_width - 2, sidebar_top)
        glVertex2f(self.sidebar_width, sidebar_top)
        glVertex2f(self.sidebar_width, sidebar_bottom)
        glVertex2f(self.sidebar_width - 2, sidebar_bottom)
        glEnd()

        self.mesh_row_rects = []
        self.mesh_eye_rects = []
        self.mesh_row_indices = []
        self.mesh_eye_indices = []
        self.group_header_rects = []
        self.group_arrow_rects = []
        self.group_header_indices = []
        self.sidebar_scrollbar_track = None
        self.sidebar_scrollbar_thumb = None

        root_top = sidebar_top + 14
        root_bottom = root_top + row_height
        root_label = os.path.basename(self.last_loaded_path) if self.last_loaded_path else "No model loaded"

        glColor4f(0.18, 0.18, 0.18, 1.0)
        glBegin(GL_QUADS)
        glVertex2f(root_left, root_top)
        glVertex2f(root_left + row_width, root_top)
        glVertex2f(root_left + row_width, root_bottom)
        glVertex2f(root_left, root_bottom)
        glEnd()

        glColor3f(0.92, 0.92, 0.92)
        self._draw_text(text_left, root_top + 19, root_label)

        list_top = root_bottom + row_gap
        list_bottom = sidebar_bottom - 12
        self.sidebar_visible_height = max(0.0, list_bottom - list_top)

        if self.model_data is not None:
            row_step = row_height + row_gap
            total_rows = len(self.sidebar_groups)
            for group_index, group in enumerate(self.sidebar_groups):
                if self.sidebar_group_expanded[group_index]:
                    total_rows += len(group["submesh_indices"])
            self.sidebar_content_height = max(0.0, total_rows * row_step - row_gap)
            self._clamp_sidebar_scroll()

            scrollable = self.sidebar_content_height > self.sidebar_visible_height
            if scrollable and self.sidebar_visible_height > 0:
                # Thumb size tracks the visible/content ratio so scrolling scales
                # naturally with long submesh lists.
                track_left = self.sidebar_width - scrollbar_width - 8
                track_right = self.sidebar_width - 8
                track_top = list_top
                track_bottom = list_bottom
                self.sidebar_scrollbar_track = (track_left, track_top, track_right, track_bottom)

                glColor4f(0.16, 0.16, 0.16, 1.0)
                glBegin(GL_QUADS)
                glVertex2f(track_left, track_top)
                glVertex2f(track_right, track_top)
                glVertex2f(track_right, track_bottom)
                glVertex2f(track_left, track_bottom)
                glEnd()

                visible_ratio = self.sidebar_visible_height / self.sidebar_content_height
                thumb_height = max(32.0, (track_bottom - track_top) * visible_ratio)
                max_scroll = self.sidebar_content_height - self.sidebar_visible_height
                thumb_range = (track_bottom - track_top) - thumb_height
                thumb_top = track_top if max_scroll <= 0 else track_top + (self.sidebar_scroll_offset / max_scroll) * thumb_range
                thumb_bottom = thumb_top + thumb_height
                self.sidebar_scrollbar_thumb = (
                    int(track_left),
                    int(thumb_top),
                    int(track_right),
                    int(thumb_bottom),
                )

                glColor4f(0.34, 0.34, 0.34, 1.0)
                glBegin(GL_QUADS)
                glVertex2f(track_left, thumb_top)
                glVertex2f(track_right, thumb_top)
                glVertex2f(track_right, thumb_bottom)
                glVertex2f(track_left, thumb_bottom)
                glEnd()
            else:
                self.sidebar_scroll_offset = 0.0

            content_row_index = 0
            for group_index, group in enumerate(self.sidebar_groups):
                # Headers and child rows share one virtual row index so expand/
                # collapse operations feed directly into scroll math.
                header_content_top = list_top + content_row_index * row_step
                header_top = int(header_content_top - self.sidebar_scroll_offset)
                header_bottom = header_top + row_height
                if not (header_bottom < list_top or header_top > list_bottom):
                    header_left = root_left
                    header_right = root_left + row_width
                    arrow_left = header_left + 8
                    arrow_right = arrow_left + 12
                    arrow_top = header_top + 8
                    arrow_bottom = arrow_top + 12

                    self.group_header_rects.append((header_left, header_top, header_right, header_bottom))
                    self.group_arrow_rects.append((arrow_left, arrow_top, arrow_right, arrow_bottom))
                    self.group_header_indices.append(group_index)

                    if group_index == self.hover_group_header_index:
                        glColor4f(0.20, 0.20, 0.20, 1.0)
                    else:
                        glColor4f(0.16, 0.16, 0.16, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(header_left, header_top)
                    glVertex2f(header_right, header_top)
                    glVertex2f(header_right, header_bottom)
                    glVertex2f(header_left, header_bottom)
                    glEnd()

                    glColor3f(0.90, 0.90, 0.90)
                    glBegin(GL_LINES)
                    if self.sidebar_group_expanded[group_index]:
                        glVertex2f(arrow_left, arrow_top + 2)
                        glVertex2f(arrow_right, arrow_top + 2)
                        glVertex2f(arrow_left, arrow_top + 2)
                        glVertex2f((arrow_left + arrow_right) / 2, arrow_bottom)
                        glVertex2f(arrow_right, arrow_top + 2)
                        glVertex2f((arrow_left + arrow_right) / 2, arrow_bottom)
                    else:
                        glVertex2f(arrow_left + 2, arrow_top)
                        glVertex2f(arrow_right, (arrow_top + arrow_bottom) / 2)
                        glVertex2f(arrow_left + 2, arrow_bottom)
                        glVertex2f(arrow_right, (arrow_top + arrow_bottom) / 2)
                        glVertex2f(arrow_left + 2, arrow_top)
                        glVertex2f(arrow_left + 2, arrow_bottom)
                    glEnd()

                    glColor3f(0.90, 0.90, 0.90)
                    self._draw_text(header_left + 28, header_top + 19, group["label"])

                content_row_index += 1

                if not self.sidebar_group_expanded[group_index]:
                    continue

                for submesh_index in group["submesh_indices"]:
                    content_top = list_top + content_row_index * row_step
                    row_top = int(content_top - self.sidebar_scroll_offset)
                    row_bottom = row_top + row_height
                    content_row_index += 1

                    if row_bottom < list_top or row_top > list_bottom:
                        continue

                    row_left = root_left + 14
                    row_right = root_left + row_width
                    eye_right = row_right - 10
                    eye_left = eye_right - eye_size
                    eye_top = row_top + 5
                    eye_bottom = eye_top + eye_size
                    visible = self.submesh_visibility[submesh_index] if submesh_index < len(self.submesh_visibility) else True
                    submesh = self.model_data["submeshes"][submesh_index]

                    self.mesh_row_rects.append((row_left, row_top, row_right, row_bottom))
                    self.mesh_eye_rects.append((eye_left, eye_top, eye_right, eye_bottom))
                    self.mesh_row_indices.append(submesh_index)
                    self.mesh_eye_indices.append(submesh_index)

                    if submesh_index == self.selected_submesh_index:
                        glColor4f(0.24, 0.30, 0.38, 1.0)
                        glBegin(GL_QUADS)
                        glVertex2f(row_left, row_top)
                        glVertex2f(row_right, row_top)
                        glVertex2f(row_right, row_bottom)
                        glVertex2f(row_left, row_bottom)
                        glEnd()
                    elif submesh_index == self.hover_mesh_row_index:
                        glColor4f(0.20, 0.20, 0.20, 1.0)
                        glBegin(GL_QUADS)
                        glVertex2f(row_left, row_top)
                        glVertex2f(row_right, row_top)
                        glVertex2f(row_right, row_bottom)
                        glVertex2f(row_left, row_bottom)
                        glEnd()

                    glColor3f(0.88, 0.88, 0.88) if visible else glColor3f(0.48, 0.48, 0.48)
                    self._draw_text(child_left + 14, row_top + 19, submesh["name"])
                    self._draw_eye_icon(
                        eye_left,
                        eye_top,
                        eye_right,
                        eye_bottom,
                        visible=visible,
                        hovered=(submesh_index == self.hover_mesh_eye_index),
                    )
        else:
            self.sidebar_content_height = 0.0
            self.sidebar_visible_height = max(0.0, list_bottom - list_top)
            self.sidebar_scroll_offset = 0.0

        glDisable(GL_BLEND)
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glEnable(GL_DEPTH_TEST)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe else GL_FILL)
        self._configure_3d_viewport()

    # -------------------------------------------------------------------------

    def _draw_inspector(self) -> None:
        """Render the right-side submesh material inspector."""
        inspector_left = self.width - self.inspector_width
        inspector_right = self.width
        inspector_top = self.toolbar_height
        inspector_bottom = self.height - self.statusbar_height
        panel_inner_left = inspector_left + 16
        panel_width = self.inspector_width - 32

        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glColor4f(0.11, 0.11, 0.11, 0.96)
        glBegin(GL_QUADS)
        glVertex2f(inspector_left, inspector_top)
        glVertex2f(inspector_right, inspector_top)
        glVertex2f(inspector_right, inspector_bottom)
        glVertex2f(inspector_left, inspector_bottom)
        glEnd()

        glColor4f(0.20, 0.20, 0.20, 1.0)
        glBegin(GL_QUADS)
        glVertex2f(inspector_left, inspector_top)
        glVertex2f(inspector_left + 2, inspector_top)
        glVertex2f(inspector_left + 2, inspector_bottom)
        glVertex2f(inspector_left, inspector_bottom)
        glEnd()

        self.material_field_rects = []
        self._draw_text(panel_inner_left, inspector_top + 20, "Submesh Inspector")
        glColor3f(0.74, 0.74, 0.74)
        self._draw_text(panel_inner_left, inspector_top + 36, "Pattern inspector is primary. Live preview")
        self._draw_text(panel_inner_left, inspector_top + 49, "is heuristic and only updates after Enter.")
        self._draw_text(panel_inner_left, inspector_top + 62, self._truncate_text(self.inspector_status_message, 48))

        if self.model_data is None or self.selected_submesh_index is None:
            glColor3f(0.86, 0.86, 0.86)
            self._draw_text(panel_inner_left, inspector_top + 98, "No submesh selected.")
            self._draw_text(panel_inner_left, inspector_top + 112, "Load a model and click a mesh row.")
        else:
            submesh = self.model_data["submeshes"][self.selected_submesh_index]
            material = submesh["material"]
            texture_name = self._texture_for_submesh(self.selected_submesh_index)
            raw_line = material["raw_line"] if material is not None else "No parsed material line"
            parsed_tuple = ", ".join(material["values"]) if material is not None else "No pattern data"
            current_line = self._current_material_line(self.selected_submesh_index)
            committed_line = self._committed_material_line(self.selected_submesh_index)
            preview_state = self.submesh_preview_states[self.selected_submesh_index]
            pattern_group = self._pattern_group_for_submesh(self.selected_submesh_index)

            glColor3f(0.92, 0.92, 0.92)
            self._draw_text(panel_inner_left, inspector_top + 96, "Selected")
            self._draw_text(
                panel_inner_left,
                inspector_top + 112,
                self._truncate_text(submesh["name"], 28),
            )

            glColor3f(0.72, 0.72, 0.72)
            self._draw_text(panel_inner_left, inspector_top + 140, "Texture")
            glColor3f(0.90, 0.90, 0.90)
            self._draw_text(panel_inner_left, inspector_top + 156, self._truncate_text(texture_name, 32))

            glColor3f(0.72, 0.72, 0.72)
            self._draw_text(panel_inner_left, inspector_top + 184, "Parsed line")
            glColor3f(0.90, 0.90, 0.90)
            self._draw_text(panel_inner_left, inspector_top + 200, self._truncate_text(raw_line, 42))

            glColor3f(0.72, 0.72, 0.72)
            self._draw_text(panel_inner_left, inspector_top + 228, "Parsed tuple")
            glColor3f(0.90, 0.90, 0.90)
            self._draw_text(panel_inner_left, inspector_top + 244, self._truncate_text(parsed_tuple, 42))

            glColor3f(0.72, 0.72, 0.72)
            self._draw_text(panel_inner_left, inspector_top + 272, "Current editable tuple")
            glColor3f(0.90, 0.90, 0.90)
            self._draw_text(panel_inner_left, inspector_top + 288, self._truncate_text(", ".join(self.editable_material_values[self.selected_submesh_index]), 42))

            glColor3f(0.72, 0.72, 0.72)
            self._draw_text(panel_inner_left, inspector_top + 316, "Pattern class")
            glColor3f(0.90, 0.90, 0.90)
            self._draw_text(
                panel_inner_left,
                inspector_top + 332,
                self._truncate_text(
                    f"{pattern_group['group_id']} | {pattern_group['note']}" if pattern_group is not None else "No pattern group available",
                    42,
                ),
            )
            glColor3f(0.72, 0.72, 0.72)
            self._draw_text(
                panel_inner_left,
                inspector_top + 346,
                f"Matches: {max(0, len(pattern_group['members']) - 1) if pattern_group is not None else 0} other submeshes",
            )
            glColor3f(0.90, 0.90, 0.90)
            self._draw_text(
                panel_inner_left,
                inspector_top + 362,
                self._truncate_text(", ".join(pattern_group["members"]) if pattern_group is not None else "No pattern peers", 42),
            )

            glColor3f(0.72, 0.72, 0.72)
            self._draw_text(panel_inner_left, inspector_top + 390, "Committed preview")
            glColor3f(0.90, 0.90, 0.90)
            self._draw_text(panel_inner_left, inspector_top + 406, self._truncate_text(committed_line, 42))
            self._draw_text(
                panel_inner_left,
                inspector_top + 420,
                self._truncate_text(
                    (
                        f"Heuristic: opacity {preview_state['opacity']:.3f} | "
                        f"Ext {'on' if preview_state['exterior_transparent'] else 'off'} | "
                        f"Int {'on' if preview_state['interior_transparent'] else 'off'}"
                    ),
                    42,
                ),
            )

            field_top = inspector_top + 450
            field_height = 34
            field_gap = 10
            label_width = 74
            value_left = panel_inner_left + label_width
            value_right = inspector_right - 20

            # These fields are session-local edits; the original SMF file is not
            # modified by the live preview workflow.
            for i, value in enumerate(self.editable_material_values[self.selected_submesh_index]):
                box_top = field_top + i * (field_height + field_gap)
                box_bottom = box_top + field_height
                box_rect = (value_left, box_top, value_right, box_bottom)
                self.material_field_rects.append(box_rect)

                glColor3f(0.84, 0.84, 0.84)
                self._draw_text(panel_inner_left, box_top + 22, f"Value {i + 1}")

                if i == self.active_material_field_index:
                    glColor4f(0.24, 0.30, 0.38, 1.0)
                elif i == self.hover_material_field_index:
                    glColor4f(0.22, 0.22, 0.22, 1.0)
                else:
                    glColor4f(0.18, 0.18, 0.18, 1.0)
                glBegin(GL_QUADS)
                glVertex2f(value_left, box_top)
                glVertex2f(value_right, box_top)
                glVertex2f(value_right, box_bottom)
                glVertex2f(value_left, box_bottom)
                glEnd()

                glColor4f(0.40, 0.40, 0.40, 1.0)
                glBegin(GL_LINES)
                glVertex2f(value_left, box_top)
                glVertex2f(value_right, box_top)
                glVertex2f(value_right, box_top)
                glVertex2f(value_right, box_bottom)
                glVertex2f(value_right, box_bottom)
                glVertex2f(value_left, box_bottom)
                glVertex2f(value_left, box_bottom)
                glVertex2f(value_left, box_top)
                glEnd()

                display_value = value if value else "-"
                if i == self.active_material_field_index:
                    display_value = f"{display_value}_"
                glColor3f(0.96, 0.96, 0.96)
                self._draw_text(value_left + 10, box_top + 22, self._truncate_text(display_value, 22))

        glDisable(GL_BLEND)
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glEnable(GL_DEPTH_TEST)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe else GL_FILL)
        self._configure_3d_viewport()

    # -------------------------------------------------------------------------

    def _draw_statusbar(self) -> None:
        """Render a persistent bottom status strip."""
        status_top = self.height - self.statusbar_height
        status_bottom = self.height

        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glColor4f(0.10, 0.10, 0.10, 0.96)
        glBegin(GL_QUADS)
        glVertex2f(0, status_top)
        glVertex2f(self.width, status_top)
        glVertex2f(self.width, status_bottom)
        glVertex2f(0, status_bottom)
        glEnd()

        glColor4f(0.22, 0.22, 0.22, 1.0)
        glBegin(GL_QUADS)
        glVertex2f(0, status_top)
        glVertex2f(self.width, status_top)
        glVertex2f(self.width, status_top + 2)
        glVertex2f(0, status_top + 2)
        glEnd()

        status_text = "   |   ".join(self._status_labels())
        glColor3f(0.86, 0.86, 0.86)
        self._draw_text(16, status_top + 21, status_text)

        glDisable(GL_BLEND)
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glEnable(GL_DEPTH_TEST)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe else GL_FILL)
        self._configure_3d_viewport()

    # -------------------------------------------------------------------------

    def _submesh_vertex_arrays(self) -> list[np.ndarray]:
        """Return only non-empty `(n, 8)` vertex arrays from parsed submeshes."""
        arrays: list[np.ndarray] = []
        if self.model_data is None:
            return arrays

        for sm in self.model_data["submeshes"]:
            if sm["vertices"]:
                arrays.append(np.array(sm["vertices"], dtype=float))
        return arrays

    # -------------------------------------------------------------------------

    def _upload_texture(self, image_bytes: bytes, width: int, height: int) -> int:
        """Upload decoded RGBA texture bytes to the current OpenGL context."""
        texture_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGBA,
            width,
            height,
            0,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            image_bytes,
        )
        glBindTexture(GL_TEXTURE_2D, 0)
        return texture_id

    # -------------------------------------------------------------------------

    def _decode_texture(self, texture_path: str) -> TexturePayload | None:
        """Decode a texture file into RGBA bytes."""
        try:
            with Image.open(texture_path) as image:
                image_rgba = image.convert("RGBA")
                return image_rgba.tobytes(), image_rgba.size[0], image_rgba.size[1]
        except Exception as pillow_exc:
            print(f"Warning: Pillow failed to load texture {texture_path}: {pillow_exc}")

        try:
            # Some legacy TIFF variants load correctly in SDL/pygame even when
            # Pillow cannot identify them.
            surface = pygame.image.load(texture_path).convert_alpha()
            image_bytes = pygame.image.tobytes(surface, "RGBA", False)
            width, height = surface.get_size()
            print(f"Loaded texture via pygame fallback: {texture_path}")
            return image_bytes, width, height
        except Exception as pygame_exc:
            print(f"Warning: pygame also failed to load texture {texture_path}: {pygame_exc}")
            return None

    # -------------------------------------------------------------------------

    def _prompt_for_texture_path(
        self,
        model_dir: str,
        texture_dir: str,
        prompt_message: str,
    ) -> str:
        """Prompt the user to select a texture file manually."""
        prompt_root = self._create_dialog_root()
        try:
            should_select = messagebox.askyesno(
                "Texture Unavailable",
                prompt_message,
                parent=prompt_root,
            )

            if not should_select:
                return ""

            return filedialog.askopenfilename(
                parent=prompt_root,
                title="Select Texture File",
                initialdir=texture_dir if os.path.isdir(texture_dir) else model_dir,
                filetypes=[("TIFF files", ("*.tif", "*.TIF", "*.tiff", "*.TIFF")), ("All files", "*.*")],
            )
        finally:
            prompt_root.destroy()

    # -------------------------------------------------------------------------

    def load_texture(self, smf_path: str) -> TexturePayload | None:
        """Load a texture from ../ART or prompt the user to choose one manually."""
        model_dir = os.path.dirname(smf_path)
        model_name = os.path.splitext(os.path.basename(smf_path))[0]
        texture_dir = os.path.normpath(os.path.join(model_dir, "..", "ART"))
        # The usual Terminal Reality layout is `MODELS/<name>.SMF` paired with
        # `ART/<name>.TIF`, so try that first before prompting the user.
        candidates = [
            os.path.join(texture_dir, f"{model_name}{ext}")
            for ext in (".TIF", ".tif", ".TIFF", ".tiff")
        ]

        texture_path = next((candidate for candidate in candidates if os.path.exists(candidate)), None)
        if texture_path is not None:
            print(f"Loaded texture: {texture_path}")
            payload = self._decode_texture(texture_path)
            if payload is not None:
                return payload

            print(f"Warning: auto-discovered texture could not be decoded: {texture_path}")
            texture_path = self._prompt_for_texture_path(
                model_dir,
                texture_dir,
                "We found the associated texture file, but it could not be decoded. "
                "Would you like to select a different texture manually?",
            )
        else:
            print(f"Warning: texture not found in {texture_dir} for model {model_name}")
            texture_path = self._prompt_for_texture_path(
                model_dir,
                texture_dir,
                "We could not find the associated texture for the model. "
                "Would you like to select it manually?",
            )

        if not texture_path:
            return None

        print(f"Loaded texture: {texture_path}")
        return self._decode_texture(texture_path)

    # -------------------------------------------------------------------------

    def _apply_pending_model_load(self) -> None:
        """Apply parsed model state and upload any pending texture on the GL thread."""
        with self._state_lock:
            pending = self._pending_model_load
            self._pending_model_load = None

        if pending is None:
            return

        # OpenGL texture creation must happen on the active render thread, so
        # background loading stops at decoded bytes and hands them off here.
        if self.texture_id is not None:
            glDeleteTextures([self.texture_id])
            self.texture_id = None

        texture_payload = pending["texture_payload"]
        if texture_payload is not None:
            image_bytes, width, height = texture_payload
            self.texture_id = self._upload_texture(image_bytes, width, height)

        self.last_loaded_path = pending["path"]
        self.model_data = pending["model_data"]
        self.model_center = pending["model_center"]
        self.model_size = pending["model_size"]
        self.show_texture = False
        self.submesh_visibility = [True] * len(self.model_data["submeshes"])
        self.selected_submesh_index = 0 if self.model_data["submeshes"] else None
        self.active_material_field_index = None
        self.editable_material_values = []
        self.submesh_preview_states = []
        # Rebuild transient UI state from the newly loaded model.
        for submesh in self.model_data["submeshes"]:
            material = submesh["material"]
            if material is not None:
                self.editable_material_values.append(material["values"].copy())
            else:
                self.editable_material_values.append(["", "", "", "", ""])
            self.submesh_preview_states.append(self._default_preview_state(material))
        self._build_material_pattern_groups()
        self._build_sidebar_groups()
        self.mesh_row_rects = []
        self.mesh_eye_rects = []
        self.mesh_row_indices = []
        self.mesh_eye_indices = []
        self.group_header_rects = []
        self.group_arrow_rects = []
        self.group_header_indices = []
        self.material_field_rects = []
        self.hover_mesh_row_index = None
        self.hover_mesh_eye_index = None
        self.hover_group_header_index = None
        self.hover_material_field_index = None
        self.inspector_status_message = "Pattern inspector is primary. Live preview remains heuristic."

        print_smf_summary(self.last_loaded_path)
        print(
            f"Loaded {pending['total_verts']} vertices and "
            f"{pending['total_faces']} faces from {self.last_loaded_path}"
        )

    # -------------------------------------------------------------------------

    def load_smf(self) -> None:
        """Open file dialog and load an SMF model."""
        root = self._create_dialog_root()
        try:
            path = filedialog.askopenfilename(
                parent=root,
                title="Select SMF File",
                filetypes=[("SMF files", ("*.smf", "*.SMF")), ("All files", "*.*")]
            )
        finally:
            root.destroy()
        if not path:
            return

        parser = SMFParser()
        model_data = parser.parse(path)
        texture_payload = self.load_texture(path)

        # Flatten submesh-local vertices into one array so camera framing uses
        # the whole model instead of whichever submesh was parsed last.
        vertex_arrays = [
            np.array(sm["vertices"], dtype=float)
            for sm in model_data["submeshes"]
            if sm["vertices"]
        ]
        if not vertex_arrays:
            print(f"Warning: no vertex data found in {path}")
            model_center = np.zeros(3)
            model_size = 1.0
            total_verts = 0
            total_faces = 0
        else:
            verts = np.concatenate(vertex_arrays, axis=0)
            model_center = verts[:, :3].mean(axis=0)
            model_size = np.linalg.norm(np.ptp(verts[:, :3], axis=0))

            total_verts = verts.shape[0]
            total_faces = sum(len(sm["faces"]) for sm in model_data["submeshes"])

        # File dialogs and parsing may happen away from the render loop; stash
        # the result and let `run()` apply it on the next frame.
        with self._state_lock:
            self._pending_model_load = {
                "path": path,
                "model_data": model_data,
                "model_center": model_center,
                "model_size": model_size,
                "texture_payload": texture_payload,
                "total_verts": total_verts,
                "total_faces": total_faces,
            } # type: ignore

    # -------------------------------------------------------------------------

    def toggle_wireframe(self) -> None:
        """Toggle polygon fill mode for the 3D scene."""
        self.wireframe = not self.wireframe
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe else GL_FILL)
        print("Wireframe mode:", self.wireframe)

    # -------------------------------------------------------------------------

    def toggle_texture(self) -> None:
        """Toggle textured rendering when a decoded texture is available."""
        if self.texture_id is None:
            self.show_texture = False
            print("Texture view: unavailable (no texture loaded)")
            return

        self.show_texture = not self.show_texture
        print("Texture view:", self.show_texture)

    # -------------------------------------------------------------------------

    def export_obj(self) -> None:
        """Prompt for a destination path and export the current model as OBJ."""
        if not self.model_data:
            print("No model loaded to export.")
            return

        root = self._create_dialog_root()
        try:
            obj_path = filedialog.asksaveasfilename(
                parent=root,
                title="Export SMF as OBJ",
                defaultextension=".obj",
                filetypes=[("Wavefront OBJ", "*.obj")]
            )
        finally:
            root.destroy()

        if not obj_path:
            print("Export cancelled.")
            return

        if self.last_loaded_path is None:
            print("No SMF path cached. Reopen model before exporting.")
            return

        export_to_obj(self.last_loaded_path, obj_path)

    # -------------------------------------------------------------------------
    
    def run(self) -> None:
        """Main event/render loop."""
        clock = pygame.time.Clock()
        running = True

        while running:
            self._apply_pending_model_load()
            self._configure_3d_viewport()

            # ---------------- Event handling ----------------
            for event in pygame.event.get():
                if event.type == QUIT or (event.type == KEYDOWN and event.key == K_ESCAPE):
                    running = False
                elif event.type == VIDEORESIZE:
                    self._set_window_size(event.w, event.h)
                elif event.type == MOUSEMOTION:
                    mx, my = event.pos
                    if self.dragging_sidebar_thumb and self.sidebar_scrollbar_track and self.sidebar_scrollbar_thumb:
                        # Convert thumb motion back into content-space scroll distance.
                        track_left, track_top, track_right, track_bottom = self.sidebar_scrollbar_track
                        thumb_left, thumb_top, thumb_right, thumb_bottom = self.sidebar_scrollbar_thumb
                        thumb_height = thumb_bottom - thumb_top
                        travel = max(0, (track_bottom - track_top) - thumb_height)
                        target_top = my - self.sidebar_drag_offset
                        clamped_top = max(track_top, min(target_top, track_bottom - thumb_height))
                        max_scroll = max(0.0, self.sidebar_content_height - self.sidebar_visible_height)
                        self.sidebar_scroll_offset = 0.0 if travel <= 0 or max_scroll <= 0 else ((clamped_top - track_top) / travel) * max_scroll
                        self._clamp_sidebar_scroll()
                    elif self.dragging_camera_orbit and event.rel[0] != 0:
                        self.camera_angle_az += math.copysign(self.camera_orbit_step, event.rel[0])
                    # Hover state is recomputed from scratch each frame rather than
                    # incrementally tracking overlapping hitboxes.
                    self.hover_index = None
                    self.hover_mesh_row_index = None
                    self.hover_mesh_eye_index = None
                    self.hover_group_header_index = None
                    self.hover_material_field_index = None
                    for i, (left, top, right, bottom) in enumerate(self.buttons):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_index = i
                            break
                    for i, (left, top, right, bottom) in enumerate(self.mesh_row_rects):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_mesh_row_index = self.mesh_row_indices[i]
                            break
                    for i, (left, top, right, bottom) in enumerate(self.mesh_eye_rects):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_mesh_eye_index = self.mesh_eye_indices[i]
                            break
                    for i, (left, top, right, bottom) in enumerate(self.group_header_rects):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_group_header_index = self.group_header_indices[i]
                            break
                    for i, (left, top, right, bottom) in enumerate(self.material_field_rects):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_material_field_index = i
                            break
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    if self._point_in_rect(mx, my, self.sidebar_scrollbar_thumb):
                        assert self.sidebar_scrollbar_thumb is not None
                        self.dragging_sidebar_thumb = True
                        self.sidebar_drag_offset = my - self.sidebar_scrollbar_thumb[1]
                        continue
                    for i, (left, top, right, bottom) in enumerate(self.buttons):
                        if left <= mx <= right and top <= my <= bottom:
                            label = self.button_labels[i]
                            running = self._handle_button_action(label)
                            break
                    else:
                        clicked = False
                        if self._point_in_rect(mx, my, self.sidebar_scrollbar_track):
                            clicked = True
                        if not clicked:
                            for i, (left, top, right, bottom) in enumerate(self.group_arrow_rects):
                                if left <= mx <= right and top <= my <= bottom:
                                    group_index = self.group_header_indices[i]
                                    self.sidebar_group_expanded[group_index] = not self.sidebar_group_expanded[group_index]
                                    clicked = True
                                    break
                        for i, (left, top, right, bottom) in enumerate(self.mesh_eye_rects):
                            if left <= mx <= right and top <= my <= bottom:
                                submesh_index = self.mesh_eye_indices[i]
                                if submesh_index < len(self.submesh_visibility):
                                    self.submesh_visibility[submesh_index] = not self.submesh_visibility[submesh_index]
                                    state = "shown" if self.submesh_visibility[submesh_index] else "hidden"
                                    if self.model_data is not None and submesh_index < len(self.model_data["submeshes"]):
                                        print(f"Submesh {self.model_data['submeshes'][submesh_index]['name']}: {state}")
                                clicked = True
                                break
                        if not clicked:
                            for i, (left, top, right, bottom) in enumerate(self.mesh_row_rects):
                                if left <= mx <= right and top <= my <= bottom:
                                    submesh_index = self.mesh_row_indices[i]
                                    self.selected_submesh_index = submesh_index
                                    self.active_material_field_index = None
                                    clicked = True
                                    if self.model_data is not None and submesh_index < len(self.model_data["submeshes"]):
                                        print(f"Selected submesh: {self.model_data['submeshes'][submesh_index]['name']}")
                                    break
                        if not clicked:
                            for i, (left, top, right, bottom) in enumerate(self.material_field_rects):
                                if left <= mx <= right and top <= my <= bottom:
                                    self.active_material_field_index = i
                                    clicked = True
                                    break
                        if not clicked:
                            self.active_material_field_index = None
                elif event.type == MOUSEBUTTONUP and event.button == 1:
                    self.dragging_sidebar_thumb = False
                elif event.type == MOUSEBUTTONDOWN and event.button == 3:
                    self._set_camera_orbit_drag(True)
                elif event.type == MOUSEBUTTONUP and event.button == 3:
                    self._set_camera_orbit_drag(False)
                elif event.type == MOUSEBUTTONDOWN and event.button in (4, 5):
                    mx, my = event.pos
                    sidebar_hovered = 0 <= mx <= self.sidebar_width and self.toolbar_height <= my <= (self.height - self.statusbar_height)
                    if sidebar_hovered:
                        self._scroll_sidebar(-40 if event.button == 4 else 40)
                    else:
                        self._adjust_camera_zoom(-self.camera_zoom_step if event.button == 4 else self.camera_zoom_step)
                elif event.type == TEXTINPUT:
                    if (
                        self.selected_submesh_index is not None
                        and self.active_material_field_index is not None
                    ):
                        # The inspector currently accepts only numeric input because
                        # preview values are interpreted as floats/flags.
                        allowed_chars = "0123456789.-"
                        filtered = "".join(ch for ch in event.text if ch in allowed_chars)
                        if filtered:
                            current = self.editable_material_values[self.selected_submesh_index][self.active_material_field_index]
                            self.editable_material_values[self.selected_submesh_index][self.active_material_field_index] = current + filtered
                elif event.type == KEYDOWN:
                    if (
                        self.selected_submesh_index is not None
                        and self.active_material_field_index is not None
                    ):
                        current = self.editable_material_values[self.selected_submesh_index][self.active_material_field_index]
                        if event.key == K_BACKSPACE:
                            self.editable_material_values[self.selected_submesh_index][self.active_material_field_index] = current[:-1]
                            continue
                        if event.key in (K_RETURN, K_KP_ENTER):
                            self._submit_material_field()
                            continue
                        if event.key == K_TAB:
                            self.active_material_field_index = (self.active_material_field_index + 1) % 5
                            continue

                    if event.key == K_SPACE:
                        print("SPACE is a legacy no-op. Incremental draw has been removed.")

                    elif event.key == K_o:
                        self.load_smf()

                    elif event.key == K_e:
                        self.export_obj()

                    elif event.key == K_w:
                        self.toggle_wireframe()

                    elif event.key == K_m:
                        self.toggle_texture()

            # ---------------- Continuous input ----------------
            # Camera motion is polled each frame so held keys feel continuous.
            keys = pygame.key.get_pressed()
            ctrl_held = bool(pygame.key.get_mods() & KMOD_CTRL)
            orbit_step = self.camera_orbit_step * (2.0 if ctrl_held else 1.0)
            if keys[K_LEFT]:
                self.camera_angle_az -= orbit_step
            if keys[K_RIGHT]:
                self.camera_angle_az += orbit_step
            if keys[K_KP_PLUS]:
                self._adjust_camera_zoom(self.camera_zoom_step)
            if keys[K_KP_MINUS]:
                self._adjust_camera_zoom(-self.camera_zoom_step)
            if ctrl_held and keys[K_UP]:
                self._adjust_camera_zoom(-self.camera_fast_zoom_step)
            elif keys[K_UP]:
                self._adjust_camera_zoom(-self.camera_zoom_step)
            if ctrl_held and keys[K_DOWN]:
                self._adjust_camera_zoom(self.camera_fast_zoom_step)
            elif keys[K_DOWN]:
                self._adjust_camera_zoom(self.camera_zoom_step)

            # ---------------- Camera setup ----------------
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT) # pyright: ignore[reportOperatorIssue]
            glLoadIdentity()

            theta = math.radians(self.camera_angle_az)
            cx, cy, cz = self.model_center
            eye_x = cx + self.camera_radius * math.cos(theta)
            eye_y = cy + self.camera_height
            eye_z = cz + self.camera_radius * math.sin(theta)

            # The model is re-centered before drawing, so the orbit target stays fixed at the origin.
            gluLookAt(eye_x, eye_y, eye_z, 0, 0, 0, 0, 1, 0)

            # ---------------- Draw grid ----------------
            glBegin(GL_LINES)
            glColor3f(0.0, 0.8, 1.0)
            grid_range = int(max(10, self.model_size / 2))
            for x in range(-grid_range, grid_range + 1):
                glVertex3f(x, 0, -grid_range)
                glVertex3f(x, 0, grid_range)
            for z in range(-grid_range, grid_range + 1):
                glVertex3f(-grid_range, 0, z)
                glVertex3f(grid_range, 0, z)
            glEnd()

            # ---------------- Draw model ----------------
            if self.model_data:
                textured = self.texture_id is not None and self.show_texture and not self.wireframe
                if textured:
                    glEnable(GL_TEXTURE_2D)
                    glBindTexture(GL_TEXTURE_2D, self.texture_id)
                    glEnable(GL_BLEND)
                    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                else:
                    glDisable(GL_TEXTURE_2D)
                    glColor3f(0.6, 0.8, 1.0)
                glPushMatrix()
                # Keep models near the origin so the grid and camera remain useful
                # across assets with different source coordinates.
                glTranslatef(-self.model_center[0],
                             -self.model_center[1] + 2.0,
                             -self.model_center[2] + 2.0)
                for i, sm in enumerate(self.model_data["submeshes"]):
                    if i < len(self.submesh_visibility) and not self.submesh_visibility[i]:
                        continue
                    if not sm["vertices"]:
                        continue
                    alpha = 1.0
                    if textured:
                        if self.render_assumed_opacity and i < len(self.submesh_preview_states):
                            # Transparency remains heuristic until the full SMF
                            # material semantics are better understood.
                            preview = self.submesh_preview_states[i]
                            alpha = preview["opacity"]
                            if preview["exterior_transparent"]:
                                alpha = min(alpha, 0.45)
                            if preview["interior_transparent"]:
                                alpha = min(alpha, 0.70)
                        glColor4f(1.0, 1.0, 1.0, alpha)
                    verts_np = np.array(sm["vertices"])
                    glBegin(GL_TRIANGLES)
                    for f in sm["faces"]:
                        for vi in f:
                            try:
                                if textured:
                                    glTexCoord2f(verts_np[vi][6], verts_np[vi][7])
                                glVertex3f(*verts_np[vi][:3])
                            except Exception:
                                continue
                    glEnd()
                glPopMatrix()
                if textured:
                    glBindTexture(GL_TEXTURE_2D, 0)
                    glDisable(GL_TEXTURE_2D)
                    glDisable(GL_BLEND)

            self._draw_toolbar()
            self._draw_sidebar()
            self._draw_inspector()
            self._draw_statusbar()

            pygame.display.flip()
            clock.tick(60)

        self._set_camera_orbit_drag(False)
        pygame.quit()


# -------------------------------------------------------------------------

if __name__ == "__main__":
    viewer = SMFViewer()
    print(__doc__)
    viewer.run()
