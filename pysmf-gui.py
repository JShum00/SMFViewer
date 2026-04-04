"""
Python-SMF Viewer GUI
Author: Johnny Shumway (jShum00)

A simple 3D model viewer for Terminal Reality .SMF files.
Uses PyGame + PyOpenGL for real-time rendering and in-app overlay dialogs.

Controls:
  O: Open SMF model
  E: Export to OBJ
  W: Toggle wireframe
  M: Texture View
  L: Toggle shading
  H: Toggle shadows
  Left/Right: Orbit camera left/right
  Up/Down: Camera Zoom
  CTRL + Left/Right: Fast orbit (2x speed)
  CTRL + Up/Down: Fast camera zoom
  Numpad +/-: Camera Zoom
  Middle Mouse Drag: Full 3D orbit camera
  Right Mouse Drag: Orbit camera left/right
  Mouse Wheel: Camera Zoom
  SPACE: Legacy no-op
  ESC: Quit viewer
"""

import math
import os
from pathlib import Path
import json
import re
import threading

import numpy as np
import pygame
from PIL import Image
from OpenGL.GL import (
    GL_ALPHA_TEST,
    GL_BLEND,
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_FILL,
    GL_FRONT_AND_BACK,
    GL_GREATER,
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
    glAlphaFunc,
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
    K_h,
    K_LEFT,
    K_l,
    K_RIGHT,
    K_s,
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
from pysmf import ParsedModel, SMFParser, SubmeshMaterial
from pysmf_export import export_to_obj
from pysmf_print import print_smf_summary
from pysmf_gui_materials import (
    build_material_pattern_groups,
    default_preview_state,
    render_role_for_submesh,
    tuple_family_for_submesh,
)
from pysmf_gui_model import (
    PreparedSubmesh,
    compute_model_metrics,
    normalize_vector,
    prepare_submeshes,
)
from pysmf_gui_trk import (
    load_trk_map,
    parse_trk_file,
    resolve_trk_candidates,
)
from pysmf_gui_types import (
    MaterialPatternGroup,
    ModalEntry,
    ParsedTRK,
    PendingModelLoad,
    RGBColor,
    RenderRole,
    SidebarGroup,
    SUBMESH_GROUPS,
    SubmeshPreviewState,
    TexturePayload,
    ViewerSettings,
)


def get_submesh_group(name: str) -> str:
    """Return the configured sidebar group for a submesh name."""
    for group, pattern in SUBMESH_GROUPS:
        if re.match(pattern, name, re.IGNORECASE):
            return group
    return "Other"


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
        self.inspector_width = 420
        pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL | RESIZABLE)
        pygame.display.set_caption("PySMF - SMF Viewer")

        self._configure_3d_viewport()

        # Default OpenGL state
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glEnable(GL_DEPTH_TEST)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)  # start in wireframe mode

        # UI hitboxes are rebuilt every frame because layout depends on window
        # size, hover state, and which sidebar groups are expanded.
        self.button_labels: list[str] = ["Open", "Export", "Specs", "Settings", "Wireframe", "Texture", "Opacity", "Shading", "Shadows", "Exit"]
        self.button_display_labels: dict[str, str] = {
            "Open": "📂 Open",
            "Export": "💾 Export",
            "Specs": "📋 Specs",
            "Settings": "⚙️ Settings",
            "Wireframe": "🔲 Wireframe",
            "Texture": "🖼️ Texture",
            "Opacity": "🔆 Opacity",
            "Shading": "💡 Shading",
            "Shadows": "🌒 Shadows",
            "Exit": "❌ Exit",
        }
        self.button_tooltips: dict[str, str] = {
            "Open": "Open Model — O",
            "Export": "Export to OBJ — E",
            "Specs": "Vehicle Specs — S",
            "Settings": "Viewer Settings",
            "Wireframe": "Toggle Wireframe — W",
            "Texture": "Toggle Texture — M",
            "Opacity": "Toggle Opacity",
            "Shading": "Toggle Shading",
            "Shadows": "Toggle Shadows",
            "Exit": "Exit Viewer — ESC",
        }
        self.toolbar_label_font: pygame.font.Font | None = self._load_toolbar_label_font()
        self.toolbar_label_texture_cache: dict[tuple[str, tuple[int, int, int]], tuple[int, int, int]] = {}
        self.buttons: list[tuple[int, int, int, int]] = []
        self.hover_index: int | None = None
        self.mesh_row_rects: list[tuple[int, int, int, int]] = []
        self.mesh_eye_rects: list[tuple[int, int, int, int]] = []
        self.mesh_row_indices: list[int] = []
        self.mesh_eye_indices: list[int] = []
        self.group_header_rects: list[tuple[int, int, int, int]] = []
        self.group_arrow_rects: list[tuple[int, int, int, int]] = []
        self.group_eye_rects: list[tuple[int, int, int, int]] = []
        self.group_header_indices: list[int] = []
        self.hover_mesh_row_index: int | None = None
        self.hover_mesh_eye_index: int | None = None
        self.hover_group_header_index: int | None = None
        self.hover_group_eye_index: int | None = None
        self.sidebar_scroll_offset = 0.0
        self.sidebar_content_height = 0.0
        self.sidebar_visible_height = 0.0
        self.sidebar_scrollbar_track: tuple[int, int, int, int] | None = None
        self.sidebar_scrollbar_thumb: tuple[int, int, int, int] | None = None
        self.dragging_sidebar_thumb = False
        self.sidebar_drag_offset = 0.0
        self.dragging_camera_orbit = False
        self.dragging_camera_full_orbit = False
        self.right_panel_mode = "inspector"
        self.right_panel_tab_rects: dict[str, tuple[int, int, int, int]] = {}
        self.material_field_rects: list[tuple[int, int, int, int]] = []
        self.hover_material_field_index: int | None = None
        self.inspector_tooltip_rects: list[tuple[int, int, int, int]] = []
        self.inspector_tooltip_texts: list[str] = []
        self.hover_inspector_tooltip: str | None = None
        self.inspector_scroll_offset = 0.0
        self.inspector_content_height = 0.0
        self.inspector_visible_height = 0.0
        self.inspector_scrollbar_track: tuple[int, int, int, int] | None = None
        self.inspector_scrollbar_thumb: tuple[int, int, int, int] | None = None
        self.dragging_inspector_thumb = False
        self.inspector_drag_offset = 0.0
        self.specs_scroll_offset = 0.0
        self.specs_content_height = 0.0
        self.specs_visible_height = 0.0
        self.specs_scrollbar_track: tuple[int, int, int, int] | None = None
        self.specs_scrollbar_thumb: tuple[int, int, int, int] | None = None
        self.dragging_specs_thumb = False
        self.specs_drag_offset = 0.0
        self.specs_swatch_rects: list[tuple[int, int, int, int]] = []
        self.specs_swatch_colors: list[RGBColor] = []
        self.hover_specs_swatch_index: int | None = None
        self.modal: dict[str, object] | None = None
        self.modal_entry_rects: list[tuple[int, int, int, int]] = []
        self.modal_entry_indices: list[int] = []
        self.modal_button_rects: dict[str, tuple[int, int, int, int]] = {}
        self.modal_field_rects: dict[str, tuple[int, int, int, int]] = {}
        self.modal_scroll_offset = 0.0
        self.modal_content_height = 0.0
        self.modal_visible_height = 0.0
        self.modal_scrollbar_track: tuple[int, int, int, int] | None = None
        self.modal_scrollbar_thumb: tuple[int, int, int, int] | None = None
        self.dragging_modal_thumb = False
        self.modal_drag_offset = 0.0
        self.active_settings_field: str | None = None

        # Parsed model state plus session-local selection/inspector state.
        self.model_data: ParsedModel | None = None
        self.model_center: np.ndarray = np.array([0.0, 0.0, 0.0])
        self.model_size: float = 1.0
        self.last_loaded_path: str | None = None
        self.texture_id: int | None = None
        self.texture_rgba: np.ndarray | None = None
        self.body_tinted_texture_id: int | None = None
        self.glasse_frame_texture_id: int | None = None
        self.tinted_texture_color: RGBColor | None = None
        self.submesh_visibility: list[bool] = []
        self.selected_submesh_index: int | None = None
        self.active_material_field_index: int | None = None
        self.editable_material_values: list[list[str]] = []
        self.submesh_preview_states: list[SubmeshPreviewState] = []
        self.prepared_submeshes: list[PreparedSubmesh] = []
        self.submesh_render_roles: list[RenderRole] = []
        self.submesh_render_buckets: list[str] = []
        self.submesh_texture_modes: list[str] = []
        self.render_bucket_indices: dict[str, list[int]] = {
            "opaque": [],
            "glasse_frame": [],
            "transparent": [],
        }
        self.material_pattern_groups: dict[tuple[str, ...], MaterialPatternGroup] = {}
        self.submesh_group_keys: list[tuple[str, ...] | None] = []
        self.sidebar_groups: list[SidebarGroup] = []
        self.sidebar_group_expanded: list[bool] = []
        self.inspector_status_message = "Tuple families drive preview roles. Field edits affect preview only."
        self._state_lock = threading.Lock()
        self._pending_model_load: PendingModelLoad | None = None
        self.settings_path = Path(__file__).resolve().with_name("viewer_settings.json")
        self.viewer_settings = self._load_viewer_settings()
        self.settings_draft: ViewerSettings | None = None
        self.trk_map = self._load_trk_map()
        self.loaded_trk_path: str | None = None
        self.loaded_trk_specs: ParsedTRK | None = None
        self.active_paint_color: RGBColor | None = None

        # Render toggles affect only the current viewer session.
        self.wireframe = True
        self.show_texture = False
        self.render_assumed_opacity = True
        self.enable_shading = True
        self.enable_shadows = False
        self.lighting_quality_mode = "fast"

        # Viewer-only lighting constants for a simple diffuse pass and a
        # projected shadow onto the ground plane.
        self.light_direction = normalize_vector(np.array([0.55, 1.0, 0.35], dtype=np.float32))
        self.shadow_direction = -self.light_direction
        self.light_ambient = 0.36
        self.light_diffuse = 0.64
        self.shadow_y_offset = 0.03
        self.shadow_opacity = 0.22
        self.grid_y = -3.0

        # Orbit camera around the current model center using yaw/pitch.
        self.camera_radius = 20.0
        self.camera_yaw_deg = 25.0
        self.camera_pitch_deg = 12.0
        self.camera_min_pitch_deg = -85.0
        self.camera_max_pitch_deg = 85.0
        self.camera_min_radius = 2.0
        self.camera_zoom_step = 1.0
        self.camera_fast_zoom_step = 2.0
        self.camera_orbit_step = 1.0
        self.camera_pitch_step = 0.5

    # -------------------------------------------------------------------------

    def _adjust_camera_zoom(self, delta: float) -> None:
        """Apply a signed zoom delta while keeping the camera radius valid."""
        self.camera_radius = max(self.camera_min_radius, self.camera_radius + delta)

    # -------------------------------------------------------------------------

    def _adjust_camera_pitch(self, delta: float) -> None:
        """Apply a signed pitch delta while keeping the camera upright."""
        next_pitch = self.camera_pitch_deg + delta
        self.camera_pitch_deg = max(self.camera_min_pitch_deg, min(next_pitch, self.camera_max_pitch_deg))

    # -------------------------------------------------------------------------

    def _shade_factor_for_submesh(self, submesh_index: int, role: RenderRole) -> float:
        """Return one cached lighting multiplier for a whole submesh."""
        if not self.enable_shading or role == "light_overlay":
            return 1.0
        if self.lighting_quality_mode != "fast":
            return 1.0
        if not (0 <= submesh_index < len(self.prepared_submeshes)):
            return 1.0
        return self.prepared_submeshes[submesh_index].light_factor

    # -------------------------------------------------------------------------

    def _project_shadow_vertex(self, vertex: np.ndarray, translate_y: float) -> np.ndarray:
        """Project a local-space vertex onto the ground plane using the shadow direction."""
        direction_y = float(self.shadow_direction[1])
        if abs(direction_y) <= 1e-8:
            return vertex.astype(np.float32)

        world_y = float(vertex[1] + translate_y)
        target_y = self.grid_y + self.shadow_y_offset
        travel = (target_y - world_y) / direction_y
        projected = vertex[:3] + self.shadow_direction * travel
        return projected.astype(np.float32)

    # -------------------------------------------------------------------------

    def _draw_projected_ground_shadow(self, translate_y: float, render_roles: list[RenderRole]) -> None:
        """Draw a simple projected shadow pass onto the ground plane."""
        if (
            self.model_data is None
            or self.wireframe
            or not self.enable_shadows
            or abs(float(self.shadow_direction[1])) <= 1e-8
        ):
            return

        glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0.0, 0.0, 0.0, self.shadow_opacity)

        for i, sm in enumerate(self.model_data["submeshes"]):
            if i < len(self.submesh_visibility) and not self.submesh_visibility[i]:
                continue
            if render_roles[i] == "light_overlay" or not sm["vertices"]:
                continue
            prepared = self.prepared_submeshes[i] if i < len(self.prepared_submeshes) else None
            if prepared is None or prepared.positions is None:
                continue
            glBegin(GL_TRIANGLES)
            for face in sm["faces"]:
                if len(face) != 3:
                    continue
                for vi in face:
                    if 0 <= vi < len(prepared.positions):
                        projected = self._project_shadow_vertex(prepared.positions[vi], translate_y)
                        glVertex3f(float(projected[0]), float(projected[1]), float(projected[2]))
            glEnd()

    # -------------------------------------------------------------------------

    def _update_camera_drag_capture(self) -> None:
        """Keep cursor grab/visibility in sync with the active camera drag mode."""
        drag_active = self.dragging_camera_orbit or self.dragging_camera_full_orbit
        pygame.mouse.set_visible(not drag_active)
        pygame.event.set_grab(drag_active)

    # -------------------------------------------------------------------------

    def _set_camera_orbit_drag(self, active: bool) -> None:
        """Toggle relative-motion yaw-only orbit drag mode for the right mouse button."""
        self.dragging_camera_orbit = active
        self._update_camera_drag_capture()

    # -------------------------------------------------------------------------

    def _set_camera_full_orbit_drag(self, active: bool) -> None:
        """Toggle relative-motion yaw/pitch orbit drag mode for the middle mouse button."""
        self.dragging_camera_full_orbit = active
        self._update_camera_drag_capture()

    # -------------------------------------------------------------------------

    def _modal_active(self) -> bool:
        """Return whether an in-app modal dialog currently owns input."""
        return self.modal is not None

    # -------------------------------------------------------------------------

    def _clamp_modal_scroll(self) -> None:
        """Clamp the active modal's list scroll offset."""
        max_scroll = max(0.0, self.modal_content_height - self.modal_visible_height)
        self.modal_scroll_offset = max(0.0, min(self.modal_scroll_offset, max_scroll))

    # -------------------------------------------------------------------------

    def _clamp_specs_scroll(self) -> None:
        """Clamp the specs pane scroll offset."""
        max_scroll = max(0.0, self.specs_content_height - self.specs_visible_height)
        self.specs_scroll_offset = max(0.0, min(self.specs_scroll_offset, max_scroll))

    # -------------------------------------------------------------------------

    def _clamp_inspector_scroll(self) -> None:
        """Clamp the inspector pane scroll offset."""
        max_scroll = max(0.0, self.inspector_content_height - self.inspector_visible_height)
        self.inspector_scroll_offset = max(0.0, min(self.inspector_scroll_offset, max_scroll))

    # -------------------------------------------------------------------------

    def _close_modal(self) -> None:
        """Close the active modal and clear its transient hitboxes."""
        self.modal = None
        self.modal_entry_rects = []
        self.modal_entry_indices = []
        self.modal_button_rects = {}
        self.modal_field_rects = {}
        self.modal_scrollbar_track = None
        self.modal_scrollbar_thumb = None
        self.dragging_modal_thumb = False
        self.active_settings_field = None

    # -------------------------------------------------------------------------

    def _default_viewer_settings(self) -> ViewerSettings:
        """Return the persisted settings structure with empty defaults."""
        return {
            "default_smf_dir": "",
            "default_trk_dir": "",
            "default_tif_dir": "",
        }

    # -------------------------------------------------------------------------

    def _load_viewer_settings(self) -> ViewerSettings:
        """Load viewer settings from disk, falling back to empty defaults."""
        defaults = self._default_viewer_settings()
        if not self.settings_path.exists():
            return defaults

        try:
            raw_settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Warning: failed to load viewer settings {self.settings_path}: {exc}")
            return defaults

        if not isinstance(raw_settings, dict):
            print(f"Warning: viewer settings file has unexpected format: {self.settings_path}")
            return defaults

        settings = defaults.copy()
        for key in settings:
            value = raw_settings.get(key, "")
            settings[key] = value.strip() if isinstance(value, str) else ""
        return settings

    # -------------------------------------------------------------------------

    def _save_viewer_settings(self, settings: ViewerSettings) -> None:
        """Persist viewer settings to disk as JSON."""
        payload = {
            key: value.strip()
            for key, value in settings.items()
        }
        self.settings_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # -------------------------------------------------------------------------

    def _configured_directory(self, setting_key: str) -> str | None:
        """Return a validated configured directory when one exists."""
        configured = self.viewer_settings.get(setting_key, "").strip()
        if configured and os.path.isdir(configured):
            return configured
        return None

    # -------------------------------------------------------------------------

    def _preferred_smf_dir(self) -> str:
        """Return the best starting directory for SMF browsing."""
        return self._configured_directory("default_smf_dir") or os.getcwd()

    # -------------------------------------------------------------------------

    def _preferred_trk_dir(self, model_dir: str) -> str:
        """Return the preferred TRK directory for lookup and manual prompts."""
        configured = self._configured_directory("default_trk_dir")
        if configured is not None:
            return configured
        default_trk_dir = os.path.normpath(os.path.join(model_dir, "..", "TRUCK"))
        return default_trk_dir if os.path.isdir(default_trk_dir) else model_dir

    # -------------------------------------------------------------------------

    def _preferred_tif_dir(self, model_dir: str) -> str:
        """Return the preferred texture directory for lookup and manual prompts."""
        configured = self._configured_directory("default_tif_dir")
        if configured is not None:
            return configured
        default_tif_dir = os.path.normpath(os.path.join(model_dir, "..", "ART"))
        return default_tif_dir if os.path.isdir(default_tif_dir) else model_dir

    # -------------------------------------------------------------------------

    def _open_settings_modal(self) -> None:
        """Open the viewer settings modal with a copy of the current values."""
        self.settings_draft = self.viewer_settings.copy()
        self.modal = {
            "type": "settings",
            "title": "Viewer Settings",
        }
        self.active_settings_field = "default_smf_dir"

    # -------------------------------------------------------------------------

    def _reopen_settings_modal(self) -> None:
        """Reopen the settings modal after a browse action updates the draft."""
        if self.settings_draft is None:
            self.settings_draft = self.viewer_settings.copy()
        self.modal = {
            "type": "settings",
            "title": "Viewer Settings",
        }

    # -------------------------------------------------------------------------

    def _apply_settings_draft(self) -> None:
        """Apply the current settings draft to the active viewer session."""
        if self.settings_draft is None:
            return
        self.viewer_settings = {
            key: value.strip()
            for key, value in self.settings_draft.items()
        }

    # -------------------------------------------------------------------------

    def _open_message_modal(self, title: str, message: str) -> None:
        """Show a simple informational modal with an OK button."""
        self.modal = {
            "type": "message",
            "title": title,
            "message": message,
        }
        self.modal_scroll_offset = 0.0

    # -------------------------------------------------------------------------

    def _open_confirmation_modal(self, title: str, message: str, confirm_action: str, payload: dict[str, str]) -> None:
        """Show a yes/no confirmation modal with a follow-up action."""
        self.modal = {
            "type": "confirm",
            "title": title,
            "message": message,
            "confirm_action": confirm_action,
            "payload": payload,
        }
        self.modal_scroll_offset = 0.0

    # -------------------------------------------------------------------------

    def _refresh_file_dialog_entries(self) -> None:
        """Rebuild the visible entries for the active file dialog."""
        if self.modal is None or self.modal.get("type") != "file_dialog":
            return

        current_dir = Path(str(self.modal["current_dir"]))
        allowed_suffixes = tuple(str(suffix).lower() for suffix in self.modal.get("allowed_suffixes", []))
        directory_only = bool(self.modal.get("directory_only"))
        entries: list[ModalEntry] = []

        if current_dir.parent != current_dir:
            entries.append({"label": "..", "path": str(current_dir.parent), "is_dir": True})

        try:
            children = sorted(current_dir.iterdir(), key=lambda child: (not child.is_dir(), child.name.lower()))
        except OSError:
            children = []

        for child in children:
            if child.is_dir():
                entries.append({"label": f"[{child.name}]", "path": str(child), "is_dir": True})
            elif not directory_only and (not allowed_suffixes or child.suffix.lower() in allowed_suffixes):
                entries.append({"label": child.name, "path": str(child), "is_dir": False})

        self.modal["entries"] = entries
        self.modal_content_height = max(0.0, len(entries) * 32.0)
        self._clamp_modal_scroll()

    # -------------------------------------------------------------------------

    def _open_file_dialog(
        self,
        purpose: str,
        title: str,
        start_dir: str,
        allowed_suffixes: tuple[str, ...],
        save_mode: bool = False,
        default_name: str = "",
        directory_only: bool = False,
        target_field: str = "",
    ) -> None:
        """Open a non-blocking in-app file dialog."""
        current_dir = Path(start_dir if os.path.isdir(start_dir) else os.getcwd())
        self.modal = {
            "type": "file_dialog",
            "purpose": purpose,
            "title": title,
            "current_dir": str(current_dir),
            "allowed_suffixes": allowed_suffixes,
            "save_mode": save_mode,
            "directory_only": directory_only,
            "target_field": target_field,
            "selected_path": "",
            "filename_input": default_name,
        }
        self.modal_scroll_offset = 0.0
        self._refresh_file_dialog_entries()

    # -------------------------------------------------------------------------

    def _open_variant_modal(self, choices: list[tuple[str, str]]) -> None:
        """Open a modal list for choosing one of several TRK variants."""
        self.modal = {
            "type": "variant_select",
            "title": "Select TRK Variant",
            "message": "Multiple TRK variants were found for this model.",
            "choices": [{"label": label, "path": path, "is_dir": False} for label, path in choices],
            "selected_index": 0,
        }
        self.modal_scroll_offset = 0.0
        self.modal_content_height = max(0.0, len(choices) * 34.0)
        self._clamp_modal_scroll()

    # -------------------------------------------------------------------------

    def _handle_confirm_action(self, action: str, payload: dict[str, str]) -> None:
        """Execute a deferred modal confirmation action."""
        if action == "choose_texture":
            self._open_file_dialog(
                "manual_texture",
                "Select Texture File",
                payload["start_dir"],
                (".tif", ".tiff"),
            )

    # -------------------------------------------------------------------------

    def _open_settings_directory_dialog(self, setting_key: str) -> None:
        """Open a directory picker for one settings field."""
        if self.settings_draft is None:
            self.settings_draft = self.viewer_settings.copy()
        start_dir = self.settings_draft.get(setting_key, "").strip() or os.getcwd()
        self._open_file_dialog(
            "settings_dir",
            "Select Default Folder",
            start_dir,
            (),
            directory_only=True,
            target_field=setting_key,
        )

    # -------------------------------------------------------------------------

    def _handle_modal_file_selected(self, selected_path: str) -> None:
        """Route a completed file-dialog selection to the owning workflow."""
        if self.modal is None or self.modal.get("type") != "file_dialog":
            return

        purpose = str(self.modal["purpose"])
        target_field = str(self.modal.get("target_field", ""))
        self._close_modal()
        if not selected_path:
            return

        if purpose == "open_smf":
            self._load_smf_from_path(selected_path)
        elif purpose == "manual_trk":
            self._load_selected_trk(selected_path)
        elif purpose == "manual_texture":
            self._load_selected_texture(selected_path)
        elif purpose == "settings_dir":
            if self.settings_draft is not None and target_field in self.settings_draft:
                self.settings_draft[target_field] = selected_path
            self._reopen_settings_modal()
            self.active_settings_field = target_field or self.active_settings_field
        elif purpose == "export_obj":
            if self.last_loaded_path is not None:
                export_to_obj(self.last_loaded_path, selected_path)

    # -------------------------------------------------------------------------

    def _update_modal_hover(self, mx: int, my: int) -> None:
        """Refresh modal hover state by rebuilding entry hitboxes each frame."""
        return

    # -------------------------------------------------------------------------

    def _load_trk_map(self) -> dict[str, list[str]]:
        """Load the TRK filename map from the viewer directory."""
        return load_trk_map(Path(__file__).resolve().with_name("trk_map.json"))

    # -------------------------------------------------------------------------

    def _is_button_enabled(self, label: str) -> bool:
        """Return whether a toolbar button should accept clicks."""
        if label == "Specs":
            return self.model_data is not None
        return True

    # -------------------------------------------------------------------------

    def _current_model_key(self) -> str | None:
        """Return the current SMF basename normalized for TRK lookup."""
        if self.last_loaded_path is None:
            return None
        return Path(self.last_loaded_path).stem.upper()

    # -------------------------------------------------------------------------

    def _parse_trk_file(self, trk_path: str) -> ParsedTRK:
        """Parse a TRK file for the limited set of fields used by the specs UI."""
        return parse_trk_file(trk_path)

    # -------------------------------------------------------------------------

    def _find_trk_candidates(self, model_key: str, model_dir: str) -> list[str]:
        """Resolve TRK filenames from the loaded map against the SMF directory."""
        return resolve_trk_candidates(self.trk_map, model_key, self._preferred_trk_dir(model_dir))

    # -------------------------------------------------------------------------

    def _prompt_for_trk_path(self, model_dir: str) -> str:
        """Prompt the user to locate a TRK file manually."""
        self._open_file_dialog(
            "manual_trk",
            "Select TRK File",
            self._preferred_trk_dir(model_dir),
            (".trk",),
        )
        return ""

    # -------------------------------------------------------------------------

    def _prompt_for_trk_variant(self, trk_paths: list[str]) -> str:
        """Show a small dropdown dialog when multiple TRK variants match a model."""
        if not trk_paths:
            return ""

        choices: list[tuple[str, str]] = []
        seen_labels: dict[str, int] = {}
        for trk_path in trk_paths:
            try:
                truck_name = self._parse_trk_file(trk_path)["truckName"] or os.path.basename(trk_path)
            except OSError:
                truck_name = os.path.basename(trk_path)
            label = truck_name
            seen_labels[label] = seen_labels.get(label, 0) + 1
            if seen_labels[label] > 1:
                label = f"{truck_name} ({os.path.basename(trk_path)})"
            choices.append((label, trk_path))
        self._open_variant_modal(choices)
        return ""

    # -------------------------------------------------------------------------

    def _resolve_trk_for_current_model(self) -> None:
        """Resolve, parse, and cache the TRK file for the currently loaded SMF."""
        self.loaded_trk_path = None
        self.loaded_trk_specs = None

        model_key = self._current_model_key()
        if model_key is None or self.last_loaded_path is None:
            return

        model_dir = os.path.dirname(self.last_loaded_path)
        trk_path = ""
        candidates = self._find_trk_candidates(model_key, model_dir)

        if len(candidates) == 1:
            self._load_selected_trk(candidates[0])
            return
        elif len(candidates) > 1:
            self._prompt_for_trk_variant(candidates)
            return
        else:
            self._prompt_for_trk_path(model_dir)
            return

        if not trk_path:
            print(f"TRK selection cancelled for model {model_key}")
            return

    # -------------------------------------------------------------------------

    def _load_selected_trk(self, trk_path: str) -> None:
        """Parse and cache a selected TRK file."""
        try:
            self.loaded_trk_specs = self._parse_trk_file(trk_path)
            self.loaded_trk_path = trk_path
            print(f"Loaded TRK specs: {trk_path}")
        except OSError as exc:
            self.loaded_trk_specs = None
            self.loaded_trk_path = None
            self._open_message_modal("TRK Load Failed", f"Could not read TRK file:\n{trk_path}\n\n{exc}")

    # -------------------------------------------------------------------------

    def _format_specs_value(self, value: str | list[str]) -> str:
        """Convert specs data into a display-ready string."""
        if isinstance(value, list):
            return ", ".join(value) if value else "EMPTY"
        return value if value else "N/A"

    # -------------------------------------------------------------------------

    def _set_active_paint_color(self, color: RGBColor) -> None:
        """Persist the selected paint color on the main viewer state."""
        # Color switching is temporarily disabled while paint-role rendering is
        # being reworked. Keep the helper in place so the Specs UI can be
        # re-enabled without changing call sites again.
        # self.active_paint_color = color
        # self._rebuild_tinted_texture_variants()
        return

    # -------------------------------------------------------------------------

    def open_specs_window(self) -> None:
        """Switch the right pane into specs mode."""
        if self.model_data is None:
            return
        self.right_panel_mode = "specs"


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
        width = max(110, 28 + len(label) * 11)
        if label == "Shadows":
            width += 12
        return width

    # -------------------------------------------------------------------------

    def _toolbar_button_text(self, label: str) -> str:
        """Return a toolbar label that is safe for the current GLUT text renderer."""
        preferred = self.button_display_labels.get(label, label)
        if any(ord(ch) > 255 for ch in preferred):
            return label
        return preferred

    # -------------------------------------------------------------------------

    def _toolbar_label_parts(self, label: str) -> tuple[str, str]:
        """Split a display label into leading emoji and trailing ASCII text."""
        display_label = self.button_display_labels.get(label, label).strip()
        if not display_label:
            return "", label
        parts = display_label.split(" ", 1)
        if len(parts) == 2 and any(ord(ch) > 255 for ch in parts[0]):
            return parts[0], parts[1]
        return "", label

    # -------------------------------------------------------------------------

    def _load_toolbar_label_font(self) -> pygame.font.Font | None:
        """Load a system font that can render toolbar emoji labels when available."""
        if not pygame.font.get_init():
            pygame.font.init()

        for font_name in ("segoeuiemoji", "notocoloremoji", "applesymbols"):
            font_path = pygame.font.match_font(font_name)
            if font_path:
                try:
                    return pygame.font.Font(font_path, 22)
                except Exception:
                    continue
        return None

    # -------------------------------------------------------------------------

    def _toolbar_tooltip_text(self, label: str) -> str:
        """Return tooltip text sanitized for the current GLUT text renderer."""
        tooltip = self.button_tooltips.get(label, label)
        return tooltip.replace("—", "-")

    # -------------------------------------------------------------------------

    def _toolbar_label_texture(
        self,
        glyph: str,
        color: tuple[int, int, int],
    ) -> tuple[int, int, int] | None:
        """Return a cached OpenGL texture for a toolbar label surface."""
        if self.toolbar_label_font is None:
            return None

        cache_key = (glyph, color)
        cached = self.toolbar_label_texture_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            surface = self.toolbar_label_font.render(glyph, True, color)
        except Exception:
            return None
        if surface.get_width() <= 0 or surface.get_height() <= 0:
            return None

        rgba_surface = surface.convert_alpha()
        image_bytes = pygame.image.tostring(rgba_surface, "RGBA", False)
        texture_id = self._upload_texture(image_bytes, rgba_surface.get_width(), rgba_surface.get_height())
        cached = (texture_id, rgba_surface.get_width(), rgba_surface.get_height())
        self.toolbar_label_texture_cache[cache_key] = cached
        return cached

    # -------------------------------------------------------------------------

    def _draw_toolbar_label(self, left: int, top: int, right: int, bottom: int, label: str, enabled: bool) -> None:
        """Draw one toolbar label using emoji-capable surfaces when available."""
        color = (255, 255, 255) if enabled else (133, 133, 133)
        emoji_glyph, ascii_label = self._toolbar_label_parts(label)
        texture_info = self._toolbar_label_texture(emoji_glyph, color) if emoji_glyph else None
        if texture_info is None and emoji_glyph:
            glColor3f(1.0, 1.0, 1.0) if enabled else glColor3f(0.52, 0.52, 0.52)
            self._draw_text(left + 14, top + 22, label)
            return
        if texture_info is None and not emoji_glyph:
            glColor3f(1.0, 1.0, 1.0) if enabled else glColor3f(0.52, 0.52, 0.52)
            self._draw_text(left + 14, top + 22, self._toolbar_button_text(label))
            return

        texture_id, width, height = texture_info
        icon_max_height = max(1.0, float((bottom - top) - 8))
        icon_scale = min(icon_max_height / height, 1.0)
        draw_width = width * icon_scale
        draw_height = height * icon_scale
        ascii_width = len(ascii_label) * 11 if ascii_label else 0
        gap = 8.0 if ascii_label else 0.0
        total_width = draw_width + gap + ascii_width
        content_left = float(left) + max(0.0, ((right - left) - total_width) / 2.0)
        draw_left = content_left
        draw_top = float(top) + ((bottom - top) - draw_height) / 2.0
        draw_right = draw_left + draw_width
        draw_bottom = draw_top + draw_height

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, texture_id)
        glColor4f(1.0, 1.0, 1.0, 1.0)
        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 0.0)
        glVertex2f(draw_left, draw_top)
        glTexCoord2f(1.0, 0.0)
        glVertex2f(draw_right, draw_top)
        glTexCoord2f(1.0, 1.0)
        glVertex2f(draw_right, draw_bottom)
        glTexCoord2f(0.0, 1.0)
        glVertex2f(draw_left, draw_bottom)
        glEnd()
        glBindTexture(GL_TEXTURE_2D, 0)
        glDisable(GL_TEXTURE_2D)

        if ascii_label:
            glColor3f(1.0, 1.0, 1.0) if enabled else glColor3f(0.52, 0.52, 0.52)
            self._draw_text(draw_right + gap, top + 22, ascii_label)

    # -------------------------------------------------------------------------

    def _clear_toolbar_label_textures(self) -> None:
        """Release cached toolbar label textures when the viewer shuts down."""
        for texture_id, _width, _height in self.toolbar_label_texture_cache.values():
            self._delete_texture_handle(texture_id)
        self.toolbar_label_texture_cache.clear()

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
        (
            self.material_pattern_groups,
            self.submesh_group_keys,
        ) = build_material_pattern_groups(self.model_data["submeshes"])

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

    def _tuple_family_for_submesh(self, submesh: dict[str, object]) -> str:
        """Return the best-known tuple-pattern family for a submesh."""
        return tuple_family_for_submesh(submesh)

    # -------------------------------------------------------------------------

    def _render_role_for_submesh(self, submesh: dict[str, object]) -> RenderRole:
        """Classify a submesh into a coarse viewer render role."""
        return render_role_for_submesh(submesh)

    # -------------------------------------------------------------------------

    def _rebuild_render_metadata(self) -> None:
        """Cache render-role metadata so the hot draw loop stays branch-light."""
        self.submesh_render_roles = []
        self.submesh_render_buckets = []
        self.submesh_texture_modes = []
        self.render_bucket_indices = {
            "opaque": [],
            "glasse_frame": [],
            "transparent": [],
        }
        if self.model_data is None:
            return

        for index, submesh in enumerate(self.model_data["submeshes"]):
            role = self._render_role_for_submesh(submesh)
            self.submesh_render_roles.append(role)
            if role == "paint_glasse_frame":
                self.submesh_render_buckets.append("glasse_frame")
                self.render_bucket_indices["glasse_frame"].append(index)
            elif role in {"glass_interior", "light_overlay"}:
                self.submesh_render_buckets.append("transparent")
                self.render_bucket_indices["transparent"].append(index)
            else:
                self.submesh_render_buckets.append("opaque")
                self.render_bucket_indices["opaque"].append(index)

            if role == "paint_glasse_frame":
                self.submesh_texture_modes.append("glasse_frame")
            elif role == "paint_body":
                self.submesh_texture_modes.append("body")
            else:
                self.submesh_texture_modes.append("base")

    # -------------------------------------------------------------------------

    def _role_alpha_for_submesh(self, submesh_index: int, role: RenderRole) -> float:
        """Return the preview alpha for a classified render role."""
        if not self.render_assumed_opacity:
            return 1.0
        preview = self.submesh_preview_states[submesh_index] if 0 <= submesh_index < len(self.submesh_preview_states) else None
        if role == "glass_interior":
            if preview is not None:
                return max(0.05, min(1.0, preview["opacity"]))
            return 0.55
        if role == "paint_glasse_frame":
            if preview is not None and (preview["exterior_transparent"] or preview["interior_transparent"]):
                return max(0.15, min(1.0, preview["opacity"]))
            return 1.0
        if role == "light_overlay":
            if preview is not None:
                return max(0.10, min(1.0, preview["opacity"]))
            return 0.72
        return 1.0

    # -------------------------------------------------------------------------

    def _delete_texture_handle(self, texture_id: int | None) -> None:
        """Delete an OpenGL texture if one is currently allocated."""
        if texture_id is not None:
            glDeleteTextures([texture_id])

    # -------------------------------------------------------------------------

    def _clear_tinted_texture_variants(self) -> None:
        """Drop any cached tinted texture variants derived from the base texture."""
        self._delete_texture_handle(self.body_tinted_texture_id)
        self._delete_texture_handle(self.glasse_frame_texture_id)
        self.body_tinted_texture_id = None
        self.glasse_frame_texture_id = None
        self.tinted_texture_color = None

    # -------------------------------------------------------------------------

    def _cache_texture_rgba(self, image_bytes: bytes, width: int, height: int) -> None:
        """Store the uploaded RGBA texture bytes in CPU memory for tint masking."""
        self.texture_rgba = np.frombuffer(image_bytes, dtype=np.uint8).reshape((height, width, 4)).copy()
        self._clear_tinted_texture_variants()

    # -------------------------------------------------------------------------

    def _rebuild_tinted_texture_variants(self) -> None:
        """Rebuild cached Body/GlassE texture variants for the active paint color."""
        self._clear_tinted_texture_variants()
        if self.texture_rgba is None or self.active_paint_color is None:
            return

        source = self.texture_rgba.astype(np.float32) / 255.0
        rgb = source[..., :3]
        alpha = source[..., 3:4]
        paint = np.array(self.active_paint_color, dtype=np.float32).reshape((1, 1, 3)) / 255.0

        luminance = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]

        body_tinted_rgb = np.clip(rgb * paint, 0.0, 1.0)
        body_tinted = np.concatenate((body_tinted_rgb, alpha), axis=2)

        glasse_tinted_rgb = np.clip(rgb * paint, 0.0, 1.0)
        glasse_alpha = alpha.copy()
        dark_window_mask = luminance <= 0.20
        glasse_alpha[dark_window_mask, 0] *= 0.38
        transition_mask = (luminance > 0.20) & (luminance < 0.34)
        if np.any(transition_mask):
            transition_alpha = 0.38 + (np.clip((luminance[transition_mask] - 0.20) / 0.14, 0.0, 1.0) * 0.62)
            glasse_alpha[transition_mask, 0] *= transition_alpha
        glasse_frame = np.concatenate((glasse_tinted_rgb, np.clip(glasse_alpha, 0.0, 1.0)), axis=2)

        body_tinted_bytes = (np.clip(body_tinted, 0.0, 1.0) * 255.0).astype(np.uint8).tobytes()
        glasse_frame_bytes = (np.clip(glasse_frame, 0.0, 1.0) * 255.0).astype(np.uint8).tobytes()
        height, width, _ = self.texture_rgba.shape
        self.body_tinted_texture_id = self._upload_texture(body_tinted_bytes, width, height)
        self.glasse_frame_texture_id = self._upload_texture(glasse_frame_bytes, width, height)
        self.tinted_texture_color = self.active_paint_color

    # -------------------------------------------------------------------------

    def _build_sidebar_groups(self) -> None:
        """Build sidebar groups from the configured regex-based group patterns."""
        self.sidebar_groups = []
        self.sidebar_group_expanded = []
        if self.model_data is None:
            return

        order = [group for group, _pattern in SUBMESH_GROUPS]
        grouped: dict[str, list[int]] = {label: [] for label in order}
        for index, submesh in enumerate(self.model_data["submeshes"]):
            grouped[get_submesh_group(submesh["name"])].append(index)

        for label in order:
            if grouped[label]:
                self.sidebar_groups.append({
                    "label": label,
                    "submesh_indices": grouped[label],
                })
                self.sidebar_group_expanded.append(False)

    # -------------------------------------------------------------------------

    def _group_visibility_state(self, group_index: int) -> bool:
        """Return True when any submesh in a sidebar group is visible."""
        if not (0 <= group_index < len(self.sidebar_groups)):
            return True
        return any(
            0 <= submesh_index < len(self.submesh_visibility) and self.submesh_visibility[submesh_index]
            for submesh_index in self.sidebar_groups[group_index]["submesh_indices"]
        )

    # -------------------------------------------------------------------------

    def _set_group_visibility(self, group_index: int, visible: bool) -> None:
        """Apply one visibility state to every submesh in a sidebar group."""
        if not (0 <= group_index < len(self.sidebar_groups)):
            return
        group = self.sidebar_groups[group_index]
        for submesh_index in group["submesh_indices"]:
            if 0 <= submesh_index < len(self.submesh_visibility):
                self.submesh_visibility[submesh_index] = visible
        print(f"Group {group['label']}: {'shown' if visible else 'hidden'}")

    # -------------------------------------------------------------------------

    def _toggle_group_visibility(self, group_index: int) -> None:
        """Invert a sidebar group's current aggregate visibility."""
        self._set_group_visibility(group_index, not self._group_visibility_state(group_index))

    # -------------------------------------------------------------------------

    def _default_preview_state(self, material: SubmeshMaterial | None) -> SubmeshPreviewState:
        """Build initial preview state from parsed tuple values for research."""
        return default_preview_state(material)

    # -------------------------------------------------------------------------

    def _submit_material_field(self) -> None:
        """Commit the active inspector field into preview state."""
        if self.selected_submesh_index is None or self.active_material_field_index is None:
            return

        submesh_index = self.selected_submesh_index
        field_index = self.active_material_field_index
        raw_value = self.editable_material_values[submesh_index][field_index].strip()
        submesh_name = self.model_data["submeshes"][submesh_index]["name"] if self.model_data is not None else "submesh"
        role = self._render_role_for_submesh(self.model_data["submeshes"][submesh_index]) if self.model_data is not None else "opaque_neutral"
        family = self._tuple_family_for_submesh(self.model_data["submeshes"][submesh_index]) if self.model_data is not None else "Unknown family"

        try:
            parsed = float(raw_value)
        except ValueError:
            self.inspector_status_message = (
                f"{submesh_name}: invalid numeric input for Tuple {field_index + 1}; preview unchanged."
            )
            print(self.inspector_status_message)
            self.active_material_field_index = None
            return

        if field_index == 1 and role in {"glass_interior", "paint_glasse_frame", "light_overlay"}:
            self.submesh_preview_states[submesh_index]["opacity"] = max(0.0, min(1.0, parsed))
            self.inspector_status_message = (
                f"{submesh_name}: Tuple 2 preview alpha updated to {self.submesh_preview_states[submesh_index]['opacity']:.3f}"
            )
        elif field_index == 3 and role in {"glass_interior", "paint_glasse_frame", "light_overlay"}:
            self.submesh_preview_states[submesh_index]["exterior_transparent"] = parsed > 0.0
            state = "on" if self.submesh_preview_states[submesh_index]["exterior_transparent"] else "off"
            self.inspector_status_message = f"{submesh_name}: Tuple 4 experimental flag = {state}"
        elif field_index == 4 and role in {"glass_interior", "paint_glasse_frame", "light_overlay"}:
            self.submesh_preview_states[submesh_index]["interior_transparent"] = parsed > 0.0
            state = "on" if self.submesh_preview_states[submesh_index]["interior_transparent"] else "off"
            self.inspector_status_message = f"{submesh_name}: Tuple 5 experimental flag = {state}"
        else:
            self.inspector_status_message = (
                f"{submesh_name}: Tuple {field_index + 1} stored for research; preview unchanged for {family} / {self._render_role_label(role)}."
            )
        print(self.inspector_status_message)
        self.active_material_field_index = None

    def _texture_status_label(self) -> str:
        """Return the current texture toggle status for the toolbar."""
        if self.texture_id is None:
            return "Texture: Unavailable"
        return f"Texture: {'On' if self.show_texture else 'Off'}"

    # -------------------------------------------------------------------------

    def _material_field_label(self, index: int) -> str:
        """Return a neutral label for a material tuple slot."""
        labels = [
            "Tuple 1",
            "Tuple 2",
            "Tuple 3",
            "Tuple 4",
            "Tuple 5",
        ]
        return labels[index] if 0 <= index < len(labels) else f"Value {index + 1}"

    # -------------------------------------------------------------------------

    def _render_role_label(self, role: RenderRole) -> str:
        """Return a user-facing render-role label for the inspector."""
        labels = {
            "paint_body": "Painted Body",
            "paint_glasse_frame": "GlassE Frame",
            "glass_interior": "Glass Interior",
            "light_overlay": "Light Overlay",
            "opaque_neutral": "Opaque Neutral",
        }
        return labels.get(role, role)

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
            f"Role Transparency: {'On' if self.render_assumed_opacity else 'Off'}",
            f"Shading: {'On' if self.enable_shading else 'Off'}",
            f"Shadows: {'On' if self.enable_shadows else 'Off'}",
            f"Visible: {visible_submeshes}/{total_submeshes}",
        ]

    # -------------------------------------------------------------------------

    def _handle_button_action(self, label: str) -> bool:
        """Execute a toolbar action. Returns False when the viewer should exit."""
        if not self._is_button_enabled(label):
            return True
        print(f"[UI] {label} clicked")
        if label == "Exit":
            return False
        if label == "Wireframe":
            self.toggle_wireframe()
        elif label == "Texture":
            self.toggle_texture()
        elif label == "Open":
            self.load_smf()
        elif label == "Export":
            self.export_obj()
        elif label == "Specs":
            self.open_specs_window()
        elif label == "Settings":
            self._open_settings_modal()
        elif label == "Opacity":
            self.render_assumed_opacity = not self.render_assumed_opacity
            print("Role-based transparency preview:", self.render_assumed_opacity)
        elif label == "Shading":
            self.toggle_shading()
        elif label == "Shadows":
            self.toggle_shadows()
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
            enabled = self._is_button_enabled(label)

            if not enabled:
                glColor4f(0.18, 0.18, 0.18, 1.0)
            elif button_index == self.hover_index:
                glColor4f(0.34, 0.34, 0.34, 1.0)
            else:
                glColor4f(0.24, 0.24, 0.24, 1.0)

            glBegin(GL_QUADS)
            glVertex2f(left, top)
            glVertex2f(right, top)
            glVertex2f(right, bottom)
            glVertex2f(left, bottom)
            glEnd()

            border_tint = 0.26 if not enabled else 0.42
            glColor4f(border_tint, border_tint, border_tint, 1.0)
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

            self._draw_toolbar_label(left, top, right, bottom, label, enabled)
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

        self._draw_toolbar_label(left, top, right, bottom, right_label, True)

        if self.hover_index is not None and 0 <= self.hover_index < len(self.button_labels):
            tooltip_text = self._toolbar_tooltip_text(self.button_labels[self.hover_index])
            tooltip_width = max(160, 20 + len(tooltip_text) * 8)
            tooltip_height = 30
            mouse_x, mouse_y = pygame.mouse.get_pos()
            tooltip_left = min(self.width - tooltip_width - 12, max(12, mouse_x + 14))
            tooltip_top = toolbar_bottom + 8

            glColor4f(0.08, 0.08, 0.08, 0.96)
            glBegin(GL_QUADS)
            glVertex2f(tooltip_left, tooltip_top)
            glVertex2f(tooltip_left + tooltip_width, tooltip_top)
            glVertex2f(tooltip_left + tooltip_width, tooltip_top + tooltip_height)
            glVertex2f(tooltip_left, tooltip_top + tooltip_height)
            glEnd()

            glColor4f(0.42, 0.42, 0.42, 1.0)
            glBegin(GL_LINES)
            glVertex2f(tooltip_left, tooltip_top)
            glVertex2f(tooltip_left + tooltip_width, tooltip_top)
            glVertex2f(tooltip_left + tooltip_width, tooltip_top)
            glVertex2f(tooltip_left + tooltip_width, tooltip_top + tooltip_height)
            glVertex2f(tooltip_left + tooltip_width, tooltip_top + tooltip_height)
            glVertex2f(tooltip_left, tooltip_top + tooltip_height)
            glVertex2f(tooltip_left, tooltip_top + tooltip_height)
            glVertex2f(tooltip_left, tooltip_top)
            glEnd()

            glColor3f(0.96, 0.96, 0.96)
            self._draw_text(tooltip_left + 8, tooltip_top + 20, tooltip_text)

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
        self.group_eye_rects = []
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
                    group_eye_right = header_right - 10
                    group_eye_left = group_eye_right - eye_size
                    group_eye_top = header_top + 5
                    group_eye_bottom = group_eye_top + eye_size
                    group_visible = self._group_visibility_state(group_index)

                    self.group_header_rects.append((header_left, header_top, header_right, header_bottom))
                    self.group_arrow_rects.append((arrow_left, arrow_top, arrow_right, arrow_bottom))
                    self.group_eye_rects.append((group_eye_left, group_eye_top, group_eye_right, group_eye_bottom))
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
                    self._draw_eye_icon(
                        group_eye_left,
                        group_eye_top,
                        group_eye_right,
                        group_eye_bottom,
                        visible=group_visible,
                        hovered=(group_index == self.hover_group_eye_index),
                    )

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
        """Render the right-side inspector or specs pane."""
        inspector_left = self.width - self.inspector_width
        inspector_right = self.width
        inspector_top = self.toolbar_height
        inspector_bottom = self.height - self.statusbar_height
        panel_inner_left = inspector_left + 16
        panel_inner_right = inspector_right - 16
        panel_width = panel_inner_right - panel_inner_left

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
        self.inspector_tooltip_rects = []
        self.inspector_tooltip_texts = []
        self.hover_inspector_tooltip = None
        self.right_panel_tab_rects = {}
        self.specs_swatch_rects = []
        self.specs_swatch_colors = []
        self.inspector_scrollbar_track = None
        self.inspector_scrollbar_thumb = None

        tab_top = inspector_top + 16
        tab_bottom = tab_top + 30
        tab_width = 120
        inspector_tab = (panel_inner_left, tab_top, panel_inner_left + tab_width, tab_bottom)
        specs_tab = (panel_inner_left + tab_width + 10, tab_top, panel_inner_left + tab_width * 2 + 10, tab_bottom)
        self.right_panel_tab_rects = {"inspector": inspector_tab, "specs": specs_tab}

        for mode, rect in self.right_panel_tab_rects.items():
            left, top, right, bottom = rect
            active = self.right_panel_mode == mode
            glColor4f(0.26, 0.30, 0.35, 1.0) if active else glColor4f(0.17, 0.17, 0.17, 1.0)
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
            glColor3f(0.96, 0.96, 0.96) if active else glColor3f(0.78, 0.78, 0.78)
            self._draw_text(left + 14, top + 20, "Inspector" if mode == "inspector" else "Specs")

        if self.right_panel_mode == "inspector":
            self._draw_text(panel_inner_left, inspector_top + 68, "Submesh Inspector")
            glColor3f(0.74, 0.74, 0.74)
            self._draw_text(panel_inner_left, inspector_top + 88, "Pattern groups are preserved for format")
            self._draw_text(panel_inner_left, inspector_top + 106, "research. Tuple families drive preview roles.")
            self._draw_text(panel_inner_left, inspector_top + 124, self._truncate_text(self.inspector_status_message, 48))
            content_top = inspector_top + 156
            content_bottom = inspector_bottom - 12
            self.inspector_visible_height = max(0.0, content_bottom - content_top)

            if self.model_data is None or self.selected_submesh_index is None:
                glColor3f(0.86, 0.86, 0.86)
                self._draw_text(panel_inner_left, content_top + 18, "No submesh selected.")
                self._draw_text(panel_inner_left, content_top + 36, "Load a model and click a mesh row.")
                self.inspector_content_height = 54.0
            else:
                submesh = self.model_data["submeshes"][self.selected_submesh_index]
                material = submesh["material"]
                texture_name = self._texture_for_submesh(self.selected_submesh_index)
                raw_line = material["raw_line"] if material is not None else "No parsed material line"
                parsed_tuple = ", ".join(material["values"]) if material is not None else "No pattern data"
                committed_line = self._committed_material_line(self.selected_submesh_index)
                preview_state = self.submesh_preview_states[self.selected_submesh_index]
                pattern_group = self._pattern_group_for_submesh(self.selected_submesh_index)
                tuple_family = self._tuple_family_for_submesh(submesh)
                render_role = self._render_role_label(self._render_role_for_submesh(submesh))
                content_y = 0.0
                label_step = 20
                section_gap = 16

                def register_tooltip(top: float, bottom: float, full_text: str, displayed_text: str) -> None:
                    if full_text != displayed_text:
                        self.inspector_tooltip_rects.append(
                            (panel_inner_left, int(top), panel_inner_right - 24, int(bottom))
                        )
                        self.inspector_tooltip_texts.append(full_text)

                def draw_row(label: str, value: str, value_chars: int = 42) -> None:
                    nonlocal content_y
                    draw_y = content_top + content_y - self.inspector_scroll_offset
                    truncated_value = self._truncate_text(value, value_chars)
                    if draw_y + label_step >= content_top and draw_y <= content_bottom:
                        glColor3f(0.72, 0.72, 0.72)
                        self._draw_text(panel_inner_left, draw_y + 14, label)
                        glColor3f(0.90, 0.90, 0.90)
                        self._draw_text(panel_inner_left, draw_y + 36, truncated_value)
                        register_tooltip(draw_y + 18, draw_y + 40, value, truncated_value)
                    content_y += 42

                def draw_line(text: str, color: tuple[float, float, float] = (0.92, 0.92, 0.92), chars: int = 42) -> None:
                    nonlocal content_y
                    draw_y = content_top + content_y - self.inspector_scroll_offset
                    truncated = self._truncate_text(text, chars)
                    if draw_y + label_step >= content_top and draw_y <= content_bottom:
                        glColor3f(*color)
                        self._draw_text(panel_inner_left, draw_y + 14, truncated)
                        register_tooltip(draw_y, draw_y + 18, text, truncated)
                    content_y += 20

                glColor3f(0.92, 0.92, 0.92)
                draw_line("Selected", (0.92, 0.92, 0.92), 42)
                draw_line(submesh["name"], (0.92, 0.92, 0.92), 28)
                content_y += section_gap
                draw_row("Texture", texture_name, 34)
                draw_row("Parsed line", raw_line, 46)
                draw_row("Parsed tuple", parsed_tuple, 46)
                draw_row("Editable tuple", ", ".join(self.editable_material_values[self.selected_submesh_index]), 46)
                draw_row("Pattern class", f"{pattern_group['group_id']} | {pattern_group['note']}" if pattern_group is not None else "No pattern group available", 46)
                draw_row("Pattern peers", ", ".join(pattern_group["members"]) if pattern_group is not None else "No pattern peers", 46)
                draw_row("Tuple family", tuple_family, 46)
                draw_row("Preview role", render_role, 46)
                draw_row("Stored tuple", committed_line, 46)
                draw_row(
                    "Experimental preview",
                    f"alpha {preview_state['opacity']:.3f} | T4 {'on' if preview_state['exterior_transparent'] else 'off'} | T5 {'on' if preview_state['interior_transparent'] else 'off'}",
                    46,
                )

                field_top = content_top + content_y - self.inspector_scroll_offset + 8
                field_height = 34
                field_gap = 10
                label_width = 108
                value_left = panel_inner_left + label_width
                value_right = panel_inner_right - 18

                # These fields are session-local edits; the original SMF file is not
                # modified by the live preview workflow.
                for i, value in enumerate(self.editable_material_values[self.selected_submesh_index]):
                    box_top = field_top + i * (field_height + field_gap)
                    box_bottom = box_top + field_height
                    box_rect = (value_left, box_top, value_right, box_bottom)
                    if box_bottom >= content_top and box_top <= content_bottom:
                        self.material_field_rects.append(box_rect)

                    if box_bottom >= content_top and box_top <= content_bottom:
                        glColor3f(0.84, 0.84, 0.84)
                        self._draw_text(panel_inner_left, box_top + 22, self._material_field_label(i))

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
                        self._draw_text(value_left + 10, box_top + 22, self._truncate_text(display_value, 28))

                self.inspector_content_height = content_y + 8 + len(self.editable_material_values[self.selected_submesh_index]) * (field_height + field_gap) + 12
                self._clamp_inspector_scroll()

                scrollable = self.inspector_content_height > self.inspector_visible_height
                if scrollable and self.inspector_visible_height > 0:
                    track_left = inspector_right - 18
                    track_right = inspector_right - 8
                    track_top = content_top
                    track_bottom = content_bottom
                    self.inspector_scrollbar_track = (track_left, track_top, track_right, track_bottom)
                    glColor4f(0.16, 0.16, 0.16, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(track_left, track_top)
                    glVertex2f(track_right, track_top)
                    glVertex2f(track_right, track_bottom)
                    glVertex2f(track_left, track_bottom)
                    glEnd()

                    visible_ratio = self.inspector_visible_height / self.inspector_content_height
                    thumb_height = max(32.0, (track_bottom - track_top) * visible_ratio)
                    max_scroll = self.inspector_content_height - self.inspector_visible_height
                    thumb_range = (track_bottom - track_top) - thumb_height
                    thumb_top = track_top if max_scroll <= 0 else track_top + (self.inspector_scroll_offset / max_scroll) * thumb_range
                    thumb_bottom = thumb_top + thumb_height
                    self.inspector_scrollbar_thumb = (track_left, int(thumb_top), track_right, int(thumb_bottom))
                    glColor4f(0.36, 0.36, 0.36, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(track_left, thumb_top)
                    glVertex2f(track_right, thumb_top)
                    glVertex2f(track_right, thumb_bottom)
                    glVertex2f(track_left, thumb_bottom)
                    glEnd()

            mouse_x, mouse_y = pygame.mouse.get_pos()
            for i, (left, top, right, bottom) in enumerate(self.inspector_tooltip_rects):
                if left <= mouse_x <= right and top <= mouse_y <= bottom and i < len(self.inspector_tooltip_texts):
                    self.hover_inspector_tooltip = self.inspector_tooltip_texts[i]
                    break

            if self.hover_inspector_tooltip:
                tooltip_text = self.hover_inspector_tooltip
                tooltip_width = min(panel_width - 20, max(160, 20 + len(tooltip_text) * 8))
                tooltip_height = 30
                tooltip_left = min(inspector_right - tooltip_width - 12, max(inspector_left + 12, mouse_x + 14))
                tooltip_top = min(inspector_bottom - tooltip_height - 12, max(inspector_top + 12, mouse_y + 14))
                glColor4f(0.08, 0.08, 0.08, 0.96)
                glBegin(GL_QUADS)
                glVertex2f(tooltip_left, tooltip_top)
                glVertex2f(tooltip_left + tooltip_width, tooltip_top)
                glVertex2f(tooltip_left + tooltip_width, tooltip_top + tooltip_height)
                glVertex2f(tooltip_left, tooltip_top + tooltip_height)
                glEnd()
                glColor4f(0.42, 0.42, 0.42, 1.0)
                glBegin(GL_LINES)
                glVertex2f(tooltip_left, tooltip_top)
                glVertex2f(tooltip_left + tooltip_width, tooltip_top)
                glVertex2f(tooltip_left + tooltip_width, tooltip_top)
                glVertex2f(tooltip_left + tooltip_width, tooltip_top + tooltip_height)
                glVertex2f(tooltip_left + tooltip_width, tooltip_top + tooltip_height)
                glVertex2f(tooltip_left, tooltip_top + tooltip_height)
                glVertex2f(tooltip_left, tooltip_top + tooltip_height)
                glVertex2f(tooltip_left, tooltip_top)
                glEnd()
                glColor3f(0.96, 0.96, 0.96)
                self._draw_text(tooltip_left + 8, tooltip_top + 20, tooltip_text)
        else:
            glColor3f(0.92, 0.92, 0.92)
            self._draw_text(panel_inner_left, inspector_top + 68, "Vehicle Specs")
            glColor3f(0.74, 0.74, 0.74)
            self._draw_text(panel_inner_left, inspector_top + 88, "Loaded from mapped TRK data.")
            self._draw_text(panel_inner_left, inspector_top + 106, "Paint swatches are currently read-only.")

            content_top = inspector_top + 136
            content_bottom = inspector_bottom - 12
            self.specs_visible_height = max(0.0, content_bottom - content_top)
            self.specs_scrollbar_track = None
            self.specs_scrollbar_thumb = None

            if self.loaded_trk_specs is None:
                self.specs_content_height = 0.0
                glColor3f(0.86, 0.86, 0.86)
                self._draw_text(panel_inner_left, content_top + 20, "No TRK specs loaded.")
                self._draw_text(panel_inner_left, content_top + 34, "Load a model or choose a TRK manually.")
            else:
                specs = self.loaded_trk_specs
                specs_rows: list[tuple[str, str | list[str], bool]] = [
                    ("Identity", "", True),
                    ("Name", specs["truckName"], False),
                    ("Model", specs["truckModel"], False),
                    ("Class", specs["truckClass"], False),
                    ("Cost", specs["truckCost"], False),
                    ("Year", specs["truckModelYear"], False),
                    ("Team Req", specs["teamRequirement"], False),
                    ("Dimensions", "", True),
                    ("Length", specs["truckLength"], False),
                    ("Height", specs["truckHeight"], False),
                    ("Wheelbase", specs["truckWheelbase"], False),
                    ("Front Track", specs["truckFrontTrack"], False),
                    ("Rear Track", specs["truckRearTrack"], False),
                    ("Performance", "", True),
                    ("Accel", specs["truckAcceleration"], False),
                    ("Top Speed", specs["truckTopSpeed"], False),
                    ("Handling", specs["truckHandling"], False),
                    ("Engine", "", True),
                    ("Max HP", specs["eng_maxHP"], False),
                    ("HP RPM", specs["eng_maxHPRPM"], False),
                    ("Torque", specs["eng_maxTorque"], False),
                    ("Redline", specs["eng_redline"], False),
                    ("Displacement", specs["eng_displacement"], False),
                    ("Parts", "", True),
                    ("Tire Model", specs["tireModelBaseName"], False),
                    ("Stock Parts", specs["stockPartList"], False),
                    ("Paint", "", True),
                    ("Colors", specs["numColors"], False),
                ]

                content_y = 0.0
                self.specs_swatch_rects = []
                self.specs_swatch_colors = []
                for label, value, is_header in specs_rows:
                    draw_y = content_top + content_y - self.specs_scroll_offset
                    if is_header:
                        if draw_y + 24 >= content_top and draw_y <= content_bottom:
                            glColor4f(0.18, 0.22, 0.28, 1.0)
                            glBegin(GL_QUADS)
                            glVertex2f(panel_inner_left, draw_y)
                            glVertex2f(panel_inner_right, draw_y)
                            glVertex2f(panel_inner_right, draw_y + 24)
                            glVertex2f(panel_inner_left, draw_y + 24)
                            glEnd()
                            glColor3f(0.96, 0.96, 0.96)
                            self._draw_text(panel_inner_left + 8, draw_y + 17, label)
                        content_y += 34
                        continue

                    if draw_y + 16 >= content_top and draw_y <= content_bottom:
                        glColor3f(0.74, 0.74, 0.74)
                        self._draw_text(panel_inner_left, draw_y + 16, f"{label}:")
                        glColor3f(0.92, 0.92, 0.92)
                        self._draw_text(panel_inner_left + 104, draw_y + 16, self._truncate_text(self._format_specs_value(value), 22))
                    content_y += 24

                if specs["colorList"]:
                    # Auto-selecting a swatch is temporarily disabled along with
                    # click-to-switch paint behavior.
                    # if self.active_paint_color is None:
                    #     self.active_paint_color = specs["colorList"][0]
                    #     self._rebuild_tinted_texture_variants()
                    swatch_size = 26
                    swatch_gap = 8
                    swatch_y = content_y + 2
                    for index, color in enumerate(specs["colorList"]):
                        row = index // 5
                        col = index % 5
                        left = panel_inner_left + col * (swatch_size + swatch_gap)
                        top = content_top + swatch_y + row * (swatch_size + swatch_gap) - self.specs_scroll_offset
                        rect = (left, top, left + swatch_size, top + swatch_size)
                        if content_top <= top <= content_bottom or content_top <= (top + swatch_size) <= content_bottom:
                            self.specs_swatch_rects.append(rect)
                            self.specs_swatch_colors.append(color)
                        border = 3 if self.active_paint_color == color else 1
                        glColor4f(0.95, 0.95, 0.95, 1.0) if self.active_paint_color == color else glColor4f(0.35, 0.35, 0.35, 1.0)
                        glBegin(GL_QUADS)
                        glVertex2f(left - border, top - border)
                        glVertex2f(left + swatch_size + border, top - border)
                        glVertex2f(left + swatch_size + border, top + swatch_size + border)
                        glVertex2f(left - border, top + swatch_size + border)
                        glEnd()
                        glColor3f(color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
                        glBegin(GL_QUADS)
                        glVertex2f(left, top)
                        glVertex2f(left + swatch_size, top)
                        glVertex2f(left + swatch_size, top + swatch_size)
                        glVertex2f(left, top + swatch_size)
                        glEnd()
                    content_y = swatch_y + ((len(specs["colorList"]) - 1) // 5 + 1) * (swatch_size + swatch_gap)

                self.specs_content_height = max(0.0, content_y + 16)
                self._clamp_specs_scroll()

                scrollable = self.specs_content_height > self.specs_visible_height
                if scrollable and self.specs_visible_height > 0:
                    track_left = inspector_right - 18
                    track_right = inspector_right - 8
                    track_top = content_top
                    track_bottom = content_bottom
                    self.specs_scrollbar_track = (track_left, track_top, track_right, track_bottom)
                    glColor4f(0.16, 0.16, 0.16, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(track_left, track_top)
                    glVertex2f(track_right, track_top)
                    glVertex2f(track_right, track_bottom)
                    glVertex2f(track_left, track_bottom)
                    glEnd()

                    visible_ratio = self.specs_visible_height / self.specs_content_height
                    thumb_height = max(32.0, (track_bottom - track_top) * visible_ratio)
                    max_scroll = self.specs_content_height - self.specs_visible_height
                    thumb_range = (track_bottom - track_top) - thumb_height
                    thumb_top = track_top if max_scroll <= 0 else track_top + (self.specs_scroll_offset / max_scroll) * thumb_range
                    thumb_bottom = thumb_top + thumb_height
                    self.specs_scrollbar_thumb = (track_left, int(thumb_top), track_right, int(thumb_bottom))
                    glColor4f(0.36, 0.36, 0.36, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(track_left, thumb_top)
                    glVertex2f(track_right, thumb_top)
                    glVertex2f(track_right, thumb_bottom)
                    glVertex2f(track_left, thumb_bottom)
                    glEnd()

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

    def _wrap_overlay_text(self, text: str, max_chars: int) -> list[str]:
        """Wrap plain text into short lines for overlay dialogs."""
        words = text.replace("\n", " \n ").split()
        lines: list[str] = []
        current = ""
        for word in words:
            if word == "\n":
                lines.append(current.rstrip())
                current = ""
                continue
            candidate = word if not current else f"{current} {word}"
            if len(candidate) > max_chars:
                if current:
                    lines.append(current)
                    current = word
                else:
                    lines.append(word[:max_chars])
                    current = word[max_chars:]
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    # -------------------------------------------------------------------------

    def _draw_modal(self) -> None:
        """Draw the active in-app modal dialog, if any."""
        if self.modal is None:
            return

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

        glColor4f(0.03, 0.03, 0.03, 0.70)
        glBegin(GL_QUADS)
        glVertex2f(0, 0)
        glVertex2f(self.width, 0)
        glVertex2f(self.width, self.height)
        glVertex2f(0, self.height)
        glEnd()

        modal_left = max(120, (self.width - 760) // 2)
        modal_top = max(96, (self.height - 520) // 2)
        modal_right = min(self.width - 120, modal_left + 760)
        modal_bottom = min(self.height - 96, modal_top + 520)
        panel_left = modal_left + 18
        panel_right = modal_right - 18

        glColor4f(0.12, 0.12, 0.12, 0.98)
        glBegin(GL_QUADS)
        glVertex2f(modal_left, modal_top)
        glVertex2f(modal_right, modal_top)
        glVertex2f(modal_right, modal_bottom)
        glVertex2f(modal_left, modal_bottom)
        glEnd()
        glColor4f(0.42, 0.42, 0.42, 1.0)
        glBegin(GL_LINES)
        glVertex2f(modal_left, modal_top)
        glVertex2f(modal_right, modal_top)
        glVertex2f(modal_right, modal_top)
        glVertex2f(modal_right, modal_bottom)
        glVertex2f(modal_right, modal_bottom)
        glVertex2f(modal_left, modal_bottom)
        glVertex2f(modal_left, modal_bottom)
        glVertex2f(modal_left, modal_top)
        glEnd()

        glColor3f(0.96, 0.96, 0.96)
        self._draw_text(panel_left, modal_top + 24, str(self.modal["title"]))

        self.modal_button_rects = {}
        self.modal_entry_rects = []
        self.modal_entry_indices = []
        self.modal_field_rects = {}
        self.modal_scrollbar_track = None
        self.modal_scrollbar_thumb = None

        modal_type = str(self.modal["type"])
        if modal_type in ("message", "confirm"):
            glColor3f(0.82, 0.82, 0.82)
            for line_index, line in enumerate(self._wrap_overlay_text(str(self.modal["message"]), 68)):
                self._draw_text(panel_left, modal_top + 60 + line_index * 18, line)

            buttons = ["OK"] if modal_type == "message" else ["Yes", "No"]
            button_width = 120
            total_width = len(buttons) * button_width + max(0, len(buttons) - 1) * 16
            left = (modal_left + modal_right - total_width) // 2
            for label in buttons:
                rect = (left, modal_bottom - 58, left + button_width, modal_bottom - 20)
                self.modal_button_rects[label.lower()] = rect
                glColor4f(0.22, 0.22, 0.22, 1.0)
                glBegin(GL_QUADS)
                glVertex2f(rect[0], rect[1])
                glVertex2f(rect[2], rect[1])
                glVertex2f(rect[2], rect[3])
                glVertex2f(rect[0], rect[3])
                glEnd()
                glColor4f(0.42, 0.42, 0.42, 1.0)
                glBegin(GL_LINES)
                glVertex2f(rect[0], rect[1])
                glVertex2f(rect[2], rect[1])
                glVertex2f(rect[2], rect[1])
                glVertex2f(rect[2], rect[3])
                glVertex2f(rect[2], rect[3])
                glVertex2f(rect[0], rect[3])
                glVertex2f(rect[0], rect[3])
                glVertex2f(rect[0], rect[1])
                glEnd()
                glColor3f(0.96, 0.96, 0.96)
                self._draw_text(rect[0] + 34, rect[1] + 24, label)
                left += button_width + 16
        else:
            list_top = modal_top + 74
            list_bottom = modal_bottom - 108
            self.modal_visible_height = max(0.0, list_bottom - list_top)
            row_height = 28
            row_gap = 4

            if modal_type == "file_dialog":
                glColor3f(0.72, 0.72, 0.72)
                self._draw_text(panel_left, modal_top + 50, self._truncate_text(str(self.modal["current_dir"]), 78))
                entries = list(self.modal.get("entries", []))
                self.modal_content_height = max(0.0, len(entries) * (row_height + row_gap))
                self._clamp_modal_scroll()

                scrollable = self.modal_content_height > self.modal_visible_height
                if scrollable and self.modal_visible_height > 0:
                    track_left = modal_right - 24
                    track_right = modal_right - 12
                    self.modal_scrollbar_track = (track_left, list_top, track_right, list_bottom)
                    glColor4f(0.16, 0.16, 0.16, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(track_left, list_top)
                    glVertex2f(track_right, list_top)
                    glVertex2f(track_right, list_bottom)
                    glVertex2f(track_left, list_bottom)
                    glEnd()

                    visible_ratio = self.modal_visible_height / self.modal_content_height
                    thumb_height = max(32.0, (list_bottom - list_top) * visible_ratio)
                    max_scroll = self.modal_content_height - self.modal_visible_height
                    thumb_range = (list_bottom - list_top) - thumb_height
                    thumb_top = list_top if max_scroll <= 0 else list_top + (self.modal_scroll_offset / max_scroll) * thumb_range
                    thumb_bottom = thumb_top + thumb_height
                    self.modal_scrollbar_thumb = (track_left, int(thumb_top), track_right, int(thumb_bottom))
                    glColor4f(0.36, 0.36, 0.36, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(track_left, thumb_top)
                    glVertex2f(track_right, thumb_top)
                    glVertex2f(track_right, thumb_bottom)
                    glVertex2f(track_left, thumb_bottom)
                    glEnd()

                selected_path = str(self.modal.get("selected_path", ""))
                row_y = list_top - self.modal_scroll_offset
                for index, entry in enumerate(entries):
                    if row_y + row_height >= list_top and row_y <= list_bottom:
                        rect = (panel_left, int(row_y), modal_right - 32, int(row_y + row_height))
                        self.modal_entry_rects.append(rect)
                        self.modal_entry_indices.append(index)
                        is_selected = selected_path == entry["path"]
                        glColor4f(0.24, 0.30, 0.38, 1.0) if is_selected else glColor4f(0.17, 0.17, 0.17, 1.0)
                        glBegin(GL_QUADS)
                        glVertex2f(rect[0], rect[1])
                        glVertex2f(rect[2], rect[1])
                        glVertex2f(rect[2], rect[3])
                        glVertex2f(rect[0], rect[3])
                        glEnd()
                        glColor3f(0.92, 0.92, 0.92)
                        self._draw_text(rect[0] + 8, rect[1] + 19, self._truncate_text(str(entry["label"]), 66))
                    row_y += row_height + row_gap

                if bool(self.modal.get("save_mode")):
                    filename_rect = (panel_left, modal_bottom - 92, panel_right, modal_bottom - 58)
                    self.modal_button_rects["filename_input"] = filename_rect
                    glColor3f(0.72, 0.72, 0.72)
                    self._draw_text(panel_left, modal_bottom - 100, "Filename")
                    glColor4f(0.18, 0.18, 0.18, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(filename_rect[0], filename_rect[1])
                    glVertex2f(filename_rect[2], filename_rect[1])
                    glVertex2f(filename_rect[2], filename_rect[3])
                    glVertex2f(filename_rect[0], filename_rect[3])
                    glEnd()
                    glColor3f(0.96, 0.96, 0.96)
                    self._draw_text(filename_rect[0] + 10, filename_rect[1] + 22, self._truncate_text(str(self.modal.get("filename_input", "")) + "_", 48))

                cancel_rect = (modal_right - 270, modal_bottom - 46, modal_right - 150, modal_bottom - 12)
                accept_rect = (modal_right - 138, modal_bottom - 46, modal_right - 18, modal_bottom - 12)
                self.modal_button_rects["cancel"] = cancel_rect
                self.modal_button_rects["accept"] = accept_rect
                accept_label = "Save" if bool(self.modal.get("save_mode")) else ("Select" if bool(self.modal.get("directory_only")) else "Open")
                for name, rect in (("Cancel", cancel_rect), (accept_label, accept_rect)):
                    glColor4f(0.22, 0.22, 0.22, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(rect[0], rect[1])
                    glVertex2f(rect[2], rect[1])
                    glVertex2f(rect[2], rect[3])
                    glVertex2f(rect[0], rect[3])
                    glEnd()
                    glColor3f(0.96, 0.96, 0.96)
                    self._draw_text(rect[0] + 28, rect[1] + 22, name)
            elif modal_type == "variant_select":
                glColor3f(0.82, 0.82, 0.82)
                self._draw_text(panel_left, modal_top + 50, str(self.modal["message"]))
                choices = list(self.modal.get("choices", []))
                self.modal_content_height = max(0.0, len(choices) * (row_height + row_gap))
                self._clamp_modal_scroll()
                row_y = list_top - self.modal_scroll_offset
                selected_index = int(self.modal.get("selected_index", 0))
                for index, choice in enumerate(choices):
                    if row_y + row_height >= list_top and row_y <= list_bottom:
                        rect = (panel_left, int(row_y), panel_right, int(row_y + row_height))
                        self.modal_entry_rects.append(rect)
                        self.modal_entry_indices.append(index)
                        glColor4f(0.24, 0.30, 0.38, 1.0) if index == selected_index else glColor4f(0.17, 0.17, 0.17, 1.0)
                        glBegin(GL_QUADS)
                        glVertex2f(rect[0], rect[1])
                        glVertex2f(rect[2], rect[1])
                        glVertex2f(rect[2], rect[3])
                        glVertex2f(rect[0], rect[3])
                        glEnd()
                        glColor3f(0.92, 0.92, 0.92)
                        self._draw_text(rect[0] + 8, rect[1] + 19, self._truncate_text(str(choice["label"]), 70))
                    row_y += row_height + row_gap
                self.modal_button_rects["cancel"] = (modal_right - 270, modal_bottom - 46, modal_right - 150, modal_bottom - 12)
                self.modal_button_rects["accept"] = (modal_right - 138, modal_bottom - 46, modal_right - 18, modal_bottom - 12)
                for name, rect in (("Cancel", self.modal_button_rects["cancel"]), ("Open", self.modal_button_rects["accept"])):
                    glColor4f(0.22, 0.22, 0.22, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(rect[0], rect[1])
                    glVertex2f(rect[2], rect[1])
                    glVertex2f(rect[2], rect[3])
                    glVertex2f(rect[0], rect[3])
                    glEnd()
                    glColor3f(0.96, 0.96, 0.96)
                    self._draw_text(rect[0] + 28, rect[1] + 22, name)
            elif modal_type == "settings":
                if self.settings_draft is None:
                    self.settings_draft = self.viewer_settings.copy()

                glColor3f(0.78, 0.78, 0.78)
                self._draw_text(panel_left, modal_top + 50, "Configure default folders used by SMF, TRK, and texture workflows.")

                fields = [
                    ("default_smf_dir", "Default SMF Folder"),
                    ("default_trk_dir", "Default TRK Folder"),
                    ("default_tif_dir", "Default TIF Folder"),
                ]
                field_top = modal_top + 96
                field_height = 34
                field_gap = 66
                browse_width = 96
                field_right = panel_right - browse_width - 12

                for index, (field_name, label) in enumerate(fields):
                    y = field_top + index * field_gap
                    field_rect = (panel_left, y + 16, field_right, y + 16 + field_height)
                    browse_rect = (field_right + 12, y + 16, panel_right, y + 16 + field_height)
                    self.modal_field_rects[field_name] = field_rect
                    self.modal_button_rects[f"browse:{field_name}"] = browse_rect

                    glColor3f(0.72, 0.72, 0.72)
                    self._draw_text(panel_left, y, label)

                    is_active = self.active_settings_field == field_name
                    glColor4f(0.22, 0.28, 0.34, 1.0) if is_active else glColor4f(0.18, 0.18, 0.18, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(field_rect[0], field_rect[1])
                    glVertex2f(field_rect[2], field_rect[1])
                    glVertex2f(field_rect[2], field_rect[3])
                    glVertex2f(field_rect[0], field_rect[3])
                    glEnd()

                    glColor4f(0.42, 0.42, 0.42, 1.0)
                    glBegin(GL_LINES)
                    glVertex2f(field_rect[0], field_rect[1])
                    glVertex2f(field_rect[2], field_rect[1])
                    glVertex2f(field_rect[2], field_rect[1])
                    glVertex2f(field_rect[2], field_rect[3])
                    glVertex2f(field_rect[2], field_rect[3])
                    glVertex2f(field_rect[0], field_rect[3])
                    glVertex2f(field_rect[0], field_rect[3])
                    glVertex2f(field_rect[0], field_rect[1])
                    glEnd()

                    field_value = self.settings_draft.get(field_name, "")
                    display_value = self._truncate_text(field_value + ("_" if is_active else ""), 58)
                    glColor3f(0.96, 0.96, 0.96)
                    self._draw_text(field_rect[0] + 10, field_rect[1] + 22, display_value)

                    glColor4f(0.22, 0.22, 0.22, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(browse_rect[0], browse_rect[1])
                    glVertex2f(browse_rect[2], browse_rect[1])
                    glVertex2f(browse_rect[2], browse_rect[3])
                    glVertex2f(browse_rect[0], browse_rect[3])
                    glEnd()
                    glColor3f(0.96, 0.96, 0.96)
                    self._draw_text(browse_rect[0] + 18, browse_rect[1] + 22, "Browse")

                helper_top = field_top + len(fields) * field_gap + 8
                glColor3f(0.64, 0.64, 0.64)
                self._draw_text(panel_left, helper_top, "Apply uses these values for the current session only.")
                self._draw_text(panel_left, helper_top + 20, "Save & Apply also writes them to viewer_settings.json.")

                cancel_rect = (panel_left, modal_bottom - 46, panel_left + 120, modal_bottom - 12)
                apply_rect = (modal_right - 290, modal_bottom - 46, modal_right - 170, modal_bottom - 12)
                save_rect = (modal_right - 158, modal_bottom - 46, modal_right - 18, modal_bottom - 12)
                self.modal_button_rects["cancel"] = cancel_rect
                self.modal_button_rects["apply"] = apply_rect
                self.modal_button_rects["save_apply"] = save_rect
                for name, rect in (("Cancel", cancel_rect), ("Apply", apply_rect), ("Save & Apply", save_rect)):
                    glColor4f(0.22, 0.22, 0.22, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(rect[0], rect[1])
                    glVertex2f(rect[2], rect[1])
                    glVertex2f(rect[2], rect[3])
                    glVertex2f(rect[0], rect[3])
                    glEnd()
                    glColor3f(0.96, 0.96, 0.96)
                    self._draw_text(rect[0] + 18, rect[1] + 22, name)

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

    def _modal_accept(self) -> None:
        """Execute the accept action for the active modal."""
        if self.modal is None:
            return

        modal_type = str(self.modal["type"])
        if modal_type == "message":
            self._close_modal()
        elif modal_type == "confirm":
            action = str(self.modal["confirm_action"])
            payload = dict(self.modal["payload"])  # type: ignore[arg-type]
            self._close_modal()
            self._handle_confirm_action(action, payload)
        elif modal_type == "variant_select":
            choices = list(self.modal.get("choices", []))
            selected_index = int(self.modal.get("selected_index", 0))
            selected_path = str(choices[selected_index]["path"]) if choices else ""
            self._close_modal()
            if selected_path:
                self._load_selected_trk(selected_path)
        elif modal_type == "file_dialog":
            current_dir = str(self.modal["current_dir"])
            if bool(self.modal.get("save_mode")):
                raw_name = str(self.modal.get("filename_input", "")).strip()
                if not raw_name:
                    return
                suffixes = tuple(str(suffix) for suffix in self.modal.get("allowed_suffixes", []))
                if suffixes and not raw_name.lower().endswith(tuple(suffix.lower() for suffix in suffixes)):
                    raw_name += suffixes[0]
                self._handle_modal_file_selected(os.path.join(current_dir, raw_name))
            else:
                selected_path = str(self.modal.get("selected_path", "")).strip()
                if bool(self.modal.get("directory_only")):
                    selected_path = selected_path or current_dir
                if selected_path:
                    self._handle_modal_file_selected(selected_path)
        elif modal_type == "settings":
            self._apply_settings_draft()
            self._close_modal()

    # -------------------------------------------------------------------------

    def _handle_modal_left_click(self, mx: int, my: int) -> None:
        """Handle a left-click while a modal owns input."""
        if self.modal is None:
            return

        if self._point_in_rect(mx, my, self.modal_scrollbar_thumb):
            assert self.modal_scrollbar_thumb is not None
            self.dragging_modal_thumb = True
            self.modal_drag_offset = my - self.modal_scrollbar_thumb[1]
            return

        for name, rect in self.modal_button_rects.items():
            if self._point_in_rect(mx, my, rect):
                if name in ("ok", "yes", "accept", "apply"):
                    self._modal_accept()
                elif name == "save_apply":
                    self._apply_settings_draft()
                    try:
                        self._save_viewer_settings(self.viewer_settings)
                    except OSError as exc:
                        self._open_message_modal("Settings Save Failed", f"Could not write settings file:\n{self.settings_path}\n\n{exc}")
                        return
                    self._close_modal()
                elif name.startswith("browse:"):
                    self.active_settings_field = name.split(":", 1)[1]
                    self._open_settings_directory_dialog(self.active_settings_field)
                elif name in ("no", "cancel"):
                    self._close_modal()
                return

        modal_type = str(self.modal["type"])
        if modal_type == "settings":
            for field_name, rect in self.modal_field_rects.items():
                if self._point_in_rect(mx, my, rect):
                    self.active_settings_field = field_name
                    return
        for rect, entry_index in zip(self.modal_entry_rects, self.modal_entry_indices):
            if not self._point_in_rect(mx, my, rect):
                continue
            if modal_type == "variant_select":
                self.modal["selected_index"] = entry_index
                return
            if modal_type == "file_dialog":
                entries = list(self.modal.get("entries", []))
                if not (0 <= entry_index < len(entries)):
                    return
                entry = entries[entry_index]
                if bool(entry["is_dir"]):
                    self.modal["current_dir"] = str(entry["path"])
                    self.modal["selected_path"] = ""
                    self._refresh_file_dialog_entries()
                else:
                    self.modal["selected_path"] = str(entry["path"])
                    if bool(self.modal.get("save_mode")):
                        self.modal["filename_input"] = os.path.basename(str(entry["path"]))
                return

    # -------------------------------------------------------------------------

    def _handle_modal_scroll(self, delta: int) -> None:
        """Scroll the active modal's selectable list."""
        if self.modal is None:
            return
        if str(self.modal["type"]) in ("file_dialog", "variant_select"):
            self.modal_scroll_offset += delta
            self._clamp_modal_scroll()

    # -------------------------------------------------------------------------

    def _handle_modal_textinput(self, text: str) -> None:
        """Route text input into the active modal when applicable."""
        if self.modal is None:
            return

        modal_type = str(self.modal["type"])
        allowed = "".join(ch for ch in text if ch not in "\n\r")
        if modal_type == "file_dialog" and bool(self.modal.get("save_mode")):
            self.modal["filename_input"] = str(self.modal.get("filename_input", "")) + allowed
        elif modal_type == "settings" and self.settings_draft is not None and self.active_settings_field is not None:
            self.settings_draft[self.active_settings_field] = self.settings_draft.get(self.active_settings_field, "") + allowed

    # -------------------------------------------------------------------------

    def _handle_modal_keydown(self, event: pygame.event.Event) -> None:
        """Handle keyboard interaction for the active modal."""
        if self.modal is None:
            return
        if event.key == K_ESCAPE:
            self._close_modal()
            return
        modal_type = str(self.modal["type"])
        if modal_type == "file_dialog" and bool(self.modal.get("save_mode")):
            if event.key == K_BACKSPACE:
                self.modal["filename_input"] = str(self.modal.get("filename_input", ""))[:-1]
            elif event.key in (K_RETURN, K_KP_ENTER):
                self._modal_accept()
        elif modal_type == "settings":
            fields = ["default_smf_dir", "default_trk_dir", "default_tif_dir"]
            if event.key == K_BACKSPACE and self.settings_draft is not None and self.active_settings_field is not None:
                self.settings_draft[self.active_settings_field] = self.settings_draft.get(self.active_settings_field, "")[:-1]
            elif event.key == K_TAB:
                current_index = fields.index(self.active_settings_field) if self.active_settings_field in fields else 0
                self.active_settings_field = fields[(current_index + 1) % len(fields)]
            elif event.key in (K_RETURN, K_KP_ENTER):
                self._modal_accept()
        elif event.key in (K_RETURN, K_KP_ENTER):
            self._modal_accept()

    # -------------------------------------------------------------------------

    def _submesh_vertex_arrays(self) -> list[np.ndarray]:
        """Return cached non-empty `(n, 8)` vertex arrays for the loaded model."""
        return [
            prepared.vertices
            for prepared in self.prepared_submeshes
            if prepared.vertices is not None
        ]

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

    def _discover_texture_for_smf(self, smf_path: str) -> tuple[TexturePayload | None, dict[str, str] | None]:
        """Try the default texture search path and return payload plus an optional prompt."""
        model_dir = os.path.dirname(smf_path)
        model_name = os.path.splitext(os.path.basename(smf_path))[0]
        configured_texture_dir = self._configured_directory("default_tif_dir")
        fallback_texture_dir = os.path.normpath(os.path.join(model_dir, "..", "ART"))
        texture_search_dirs: list[str] = []
        if configured_texture_dir is not None:
            texture_search_dirs.append(configured_texture_dir)
        if fallback_texture_dir not in texture_search_dirs:
            texture_search_dirs.append(fallback_texture_dir)
        prompt_start_dir = self._preferred_tif_dir(model_dir)
        # The usual Terminal Reality layout is `MODELS/<name>.SMF` paired with
        # `ART/<name>.TIF`, so try that first before prompting the user.
        candidates = [
            os.path.join(texture_dir, f"{model_name}{ext}")
            for texture_dir in texture_search_dirs
            for ext in (".TIF", ".tif", ".TIFF", ".tiff")
        ]

        texture_path = next((candidate for candidate in candidates if os.path.exists(candidate)), None)
        if texture_path is not None:
            print(f"Loaded texture: {texture_path}")
            payload = self._decode_texture(texture_path)
            if payload is not None:
                return payload, None

            print(f"Warning: auto-discovered texture could not be decoded: {texture_path}")
            return None, {
                "start_dir": prompt_start_dir,
                "message": (
                    "We found the associated texture file, but it could not be decoded. "
                    "Choose a different texture manually?"
                ),
            }
        else:
            print(f"Warning: texture not found in {texture_search_dirs} for model {model_name}")
            return None, {
                "start_dir": prompt_start_dir,
                "message": (
                    "We could not find the associated texture for the model. "
                    "Choose a texture manually?"
                ),
            }

    # -------------------------------------------------------------------------

    def _load_selected_texture(self, texture_path: str) -> None:
        """Decode and upload a manually chosen texture."""
        payload = self._decode_texture(texture_path)
        if payload is None:
            self._open_message_modal("Texture Load Failed", f"Could not decode texture:\n{texture_path}")
            return

        self._delete_texture_handle(self.texture_id)
        self.texture_id = None
        self._clear_tinted_texture_variants()
        image_bytes, width, height = payload
        self._cache_texture_rgba(image_bytes, width, height)
        self.texture_id = self._upload_texture(image_bytes, width, height)
        self._rebuild_tinted_texture_variants()
        # Textured models default to shadows off because the extra pass is
        # optional and significantly more expensive than the base fast path.
        self.enable_shadows = False
        print(f"Loaded texture: {texture_path}")

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
        self._delete_texture_handle(self.texture_id)
        self.texture_id = None
        self._clear_tinted_texture_variants()
        self.texture_rgba = None

        texture_payload = pending["texture_payload"]
        if texture_payload is not None:
            image_bytes, width, height = texture_payload
            self._cache_texture_rgba(image_bytes, width, height)
            self.texture_id = self._upload_texture(image_bytes, width, height)
            self._rebuild_tinted_texture_variants()

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
        # Convert geometry to NumPy once so the render loop can reuse the same
        # arrays for shading, UV lookup, and projected shadows.
        self.prepared_submeshes = prepare_submeshes(
            self.model_data,
            self.light_direction,
            self.light_ambient,
            self.light_diffuse,
        )
        # Render roles, draw buckets, and texture-selection policy are cached
        # here so the frame loop does not have to reclassify every submesh.
        self._rebuild_render_metadata()
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
        self.group_eye_rects = []
        self.group_header_indices = []
        self.material_field_rects = []
        self.hover_mesh_row_index = None
        self.hover_mesh_eye_index = None
        self.hover_group_header_index = None
        self.hover_group_eye_index = None
        self.hover_material_field_index = None
        self.inspector_status_message = "Tuple families drive preview roles. Field edits affect preview only."
        self.right_panel_mode = "inspector"
        self.inspector_scroll_offset = 0.0
        self.specs_scroll_offset = 0.0
        self.specs_swatch_rects = []
        self.specs_swatch_colors = []
        self.enable_shadows = self.texture_id is None
        self._resolve_trk_for_current_model()
        texture_prompt = pending["texture_prompt"]
        if texture_prompt is not None:
            self._open_confirmation_modal(
                "Texture Unavailable",
                texture_prompt["message"],
                "choose_texture",
                {"start_dir": texture_prompt["start_dir"]},
            )

        print_smf_summary(self.last_loaded_path)
        print(
            f"Loaded {pending['total_verts']} vertices and "
            f"{pending['total_faces']} faces from {self.last_loaded_path}"
        )

    # -------------------------------------------------------------------------

    def _load_smf_from_path(self, path: str) -> None:
        """Parse and queue an SMF model from a chosen path."""
        parser = SMFParser()
        model_data = parser.parse(path)
        texture_payload, texture_prompt = self._discover_texture_for_smf(path)
        model_center, model_size, total_verts, total_faces = compute_model_metrics(model_data)
        if total_verts == 0:
            print(f"Warning: no vertex data found in {path}")

        # File dialogs and parsing may happen away from the render loop; stash
        # the result and let `run()` apply it on the next frame.
        with self._state_lock:
            self._pending_model_load = {
                "path": path,
                "model_data": model_data,
                "model_center": model_center,
                "model_size": model_size,
                "texture_payload": texture_payload,
                "texture_prompt": texture_prompt,
                "total_verts": total_verts,
                "total_faces": total_faces,
            } # type: ignore

    # -------------------------------------------------------------------------

    def load_smf(self) -> None:
        """Open a non-blocking in-app file dialog for SMF loading."""
        self._open_file_dialog("open_smf", "Select SMF File", self._preferred_smf_dir(), (".smf",))

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

    def toggle_shading(self) -> None:
        """Toggle fast brightness modulation for model geometry."""
        self.enable_shading = not self.enable_shading
        print("Shading:", self.enable_shading)

    # -------------------------------------------------------------------------

    def toggle_shadows(self) -> None:
        """Toggle the projected ground-shadow pass independently of shading."""
        self.enable_shadows = not self.enable_shadows
        print("Shadows:", self.enable_shadows)

    # -------------------------------------------------------------------------

    def export_obj(self) -> None:
        """Prompt for a destination path and export the current model as OBJ."""
        if not self.model_data:
            print("No model loaded to export.")
            return

        if self.last_loaded_path is None:
            print("No SMF path cached. Reopen model before exporting.")
            return

        suggested_name = f"{Path(self.last_loaded_path).stem}.obj"
        self._open_file_dialog("export_obj", "Export SMF as OBJ", os.getcwd(), (".obj",), save_mode=True, default_name=suggested_name)

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
                if event.type == QUIT:
                    running = False
                elif self._modal_active():
                    if event.type == MOUSEMOTION:
                        if self.dragging_modal_thumb and self.modal_scrollbar_track and self.modal_scrollbar_thumb:
                            track_left, track_top, track_right, track_bottom = self.modal_scrollbar_track
                            thumb_left, thumb_top, thumb_right, thumb_bottom = self.modal_scrollbar_thumb
                            thumb_height = thumb_bottom - thumb_top
                            travel = max(0, (track_bottom - track_top) - thumb_height)
                            target_top = event.pos[1] - self.modal_drag_offset
                            clamped_top = max(track_top, min(target_top, track_bottom - thumb_height))
                            max_scroll = max(0.0, self.modal_content_height - self.modal_visible_height)
                            self.modal_scroll_offset = 0.0 if travel <= 0 or max_scroll <= 0 else ((clamped_top - track_top) / travel) * max_scroll
                            self._clamp_modal_scroll()
                    elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                        self._handle_modal_left_click(*event.pos)
                    elif event.type == MOUSEBUTTONUP and event.button == 1:
                        self.dragging_modal_thumb = False
                    elif event.type == MOUSEBUTTONDOWN and event.button in (4, 5):
                        self._handle_modal_scroll(-40 if event.button == 4 else 40)
                    elif event.type == TEXTINPUT:
                        self._handle_modal_textinput(event.text)
                    elif event.type == KEYDOWN:
                        self._handle_modal_keydown(event)
                    continue
                elif event.type == KEYDOWN and event.key == K_ESCAPE:
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
                    elif self.dragging_inspector_thumb and self.inspector_scrollbar_track and self.inspector_scrollbar_thumb:
                        track_left, track_top, track_right, track_bottom = self.inspector_scrollbar_track
                        thumb_left, thumb_top, thumb_right, thumb_bottom = self.inspector_scrollbar_thumb
                        thumb_height = thumb_bottom - thumb_top
                        travel = max(0, (track_bottom - track_top) - thumb_height)
                        target_top = my - self.inspector_drag_offset
                        clamped_top = max(track_top, min(target_top, track_bottom - thumb_height))
                        max_scroll = max(0.0, self.inspector_content_height - self.inspector_visible_height)
                        self.inspector_scroll_offset = 0.0 if travel <= 0 or max_scroll <= 0 else ((clamped_top - track_top) / travel) * max_scroll
                        self._clamp_inspector_scroll()
                    elif self.dragging_specs_thumb and self.specs_scrollbar_track and self.specs_scrollbar_thumb:
                        track_left, track_top, track_right, track_bottom = self.specs_scrollbar_track
                        thumb_left, thumb_top, thumb_right, thumb_bottom = self.specs_scrollbar_thumb
                        thumb_height = thumb_bottom - thumb_top
                        travel = max(0, (track_bottom - track_top) - thumb_height)
                        target_top = my - self.specs_drag_offset
                        clamped_top = max(track_top, min(target_top, track_bottom - thumb_height))
                        max_scroll = max(0.0, self.specs_content_height - self.specs_visible_height)
                        self.specs_scroll_offset = 0.0 if travel <= 0 or max_scroll <= 0 else ((clamped_top - track_top) / travel) * max_scroll
                        self._clamp_specs_scroll()
                    elif self.dragging_camera_full_orbit and (event.rel[0] != 0 or event.rel[1] != 0):
                        self.camera_yaw_deg += event.rel[0] * self.camera_orbit_step
                        self._adjust_camera_pitch(-event.rel[1] * self.camera_pitch_step)
                    elif self.dragging_camera_orbit and event.rel[0] != 0:
                        self.camera_yaw_deg += math.copysign(self.camera_orbit_step, event.rel[0])
                    # Hover state is recomputed from scratch each frame rather than
                    # incrementally tracking overlapping hitboxes.
                    self.hover_index = None
                    self.hover_mesh_row_index = None
                    self.hover_mesh_eye_index = None
                    self.hover_group_header_index = None
                    self.hover_group_eye_index = None
                    self.hover_material_field_index = None
                    self.hover_specs_swatch_index = None
                    self.hover_inspector_tooltip = None
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
                    for i, (left, top, right, bottom) in enumerate(self.group_eye_rects):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_group_eye_index = self.group_header_indices[i]
                            break
                    for i, (left, top, right, bottom) in enumerate(self.material_field_rects):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_material_field_index = i
                            break
                    for i, (left, top, right, bottom) in enumerate(self.specs_swatch_rects):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_specs_swatch_index = i
                            break
                    for i, (left, top, right, bottom) in enumerate(self.inspector_tooltip_rects):
                        if left <= mx <= right and top <= my <= bottom and i < len(self.inspector_tooltip_texts):
                            self.hover_inspector_tooltip = self.inspector_tooltip_texts[i]
                            break
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    if self._point_in_rect(mx, my, self.sidebar_scrollbar_thumb):
                        assert self.sidebar_scrollbar_thumb is not None
                        self.dragging_sidebar_thumb = True
                        self.sidebar_drag_offset = my - self.sidebar_scrollbar_thumb[1]
                        continue
                    if self._point_in_rect(mx, my, self.inspector_scrollbar_thumb):
                        assert self.inspector_scrollbar_thumb is not None
                        self.dragging_inspector_thumb = True
                        self.inspector_drag_offset = my - self.inspector_scrollbar_thumb[1]
                        continue
                    if self._point_in_rect(mx, my, self.specs_scrollbar_thumb):
                        assert self.specs_scrollbar_thumb is not None
                        self.dragging_specs_thumb = True
                        self.specs_drag_offset = my - self.specs_scrollbar_thumb[1]
                        continue
                    for i, (left, top, right, bottom) in enumerate(self.buttons):
                        if left <= mx <= right and top <= my <= bottom:
                            label = self.button_labels[i]
                            running = self._handle_button_action(label)
                            break
                    else:
                        clicked = False
                        for mode, rect in self.right_panel_tab_rects.items():
                            if self._point_in_rect(mx, my, rect):
                                self.right_panel_mode = mode
                                self.active_material_field_index = None
                                if mode == "inspector":
                                    self._clamp_inspector_scroll()
                                else:
                                    self._clamp_specs_scroll()
                                clicked = True
                                break
                        if self._point_in_rect(mx, my, self.sidebar_scrollbar_track):
                            clicked = True
                        if not clicked:
                            for i, (left, top, right, bottom) in enumerate(self.group_arrow_rects):
                                if left <= mx <= right and top <= my <= bottom:
                                    group_index = self.group_header_indices[i]
                                    self.sidebar_group_expanded[group_index] = not self.sidebar_group_expanded[group_index]
                                    clicked = True
                                    break
                        if not clicked:
                            for i, (left, top, right, bottom) in enumerate(self.group_eye_rects):
                                if left <= mx <= right and top <= my <= bottom:
                                    group_index = self.group_header_indices[i]
                                    self._toggle_group_visibility(group_index)
                                    clicked = True
                                    break
                        if not clicked:
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
                        if not clicked and self.right_panel_mode == "inspector":
                            for i, (left, top, right, bottom) in enumerate(self.material_field_rects):
                                if left <= mx <= right and top <= my <= bottom:
                                    self.active_material_field_index = i
                                    clicked = True
                                    break
                        if not clicked and self.right_panel_mode == "specs":
                            # Color switching is temporarily disabled while the
                            # paint/tint pipeline is being reworked.
                            # for i, rect in enumerate(self.specs_swatch_rects):
                            #     if self._point_in_rect(mx, my, rect) and i < len(self.specs_swatch_colors):
                            #         self._set_active_paint_color(self.specs_swatch_colors[i])
                            #         clicked = True
                            #         break
                            pass
                        if not clicked:
                            self.active_material_field_index = None
                elif event.type == MOUSEBUTTONUP and event.button == 1:
                    self.dragging_sidebar_thumb = False
                    self.dragging_inspector_thumb = False
                    self.dragging_specs_thumb = False
                elif event.type == MOUSEBUTTONDOWN and event.button == 2:
                    self._set_camera_full_orbit_drag(True)
                elif event.type == MOUSEBUTTONUP and event.button == 2:
                    self._set_camera_full_orbit_drag(False)
                elif event.type == MOUSEBUTTONDOWN and event.button == 3:
                    self._set_camera_orbit_drag(True)
                elif event.type == MOUSEBUTTONUP and event.button == 3:
                    self._set_camera_orbit_drag(False)
                elif event.type == MOUSEBUTTONDOWN and event.button in (4, 5):
                    mx, my = event.pos
                    sidebar_hovered = 0 <= mx <= self.sidebar_width and self.toolbar_height <= my <= (self.height - self.statusbar_height)
                    specs_hovered = (
                        self.right_panel_mode == "specs"
                        and (self.width - self.inspector_width) <= mx <= self.width
                        and self.toolbar_height <= my <= (self.height - self.statusbar_height)
                    )
                    inspector_hovered = (
                        self.right_panel_mode == "inspector"
                        and (self.width - self.inspector_width) <= mx <= self.width
                        and self.toolbar_height <= my <= (self.height - self.statusbar_height)
                    )
                    if sidebar_hovered:
                        self._scroll_sidebar(-40 if event.button == 4 else 40)
                    elif inspector_hovered:
                        self.inspector_scroll_offset += -40 if event.button == 4 else 40
                        self._clamp_inspector_scroll()
                    elif specs_hovered:
                        self.specs_scroll_offset += -40 if event.button == 4 else 40
                        self._clamp_specs_scroll()
                    else:
                        self._adjust_camera_zoom(-self.camera_zoom_step if event.button == 4 else self.camera_zoom_step)
                elif event.type == TEXTINPUT:
                    if (
                        self.right_panel_mode == "inspector"
                        and self.selected_submesh_index is not None
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
                        self.right_panel_mode == "inspector"
                        and
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

                    elif event.key == K_s:
                        self.open_specs_window()

                    elif event.key == K_w:
                        self.toggle_wireframe()

                    elif event.key == K_m:
                        self.toggle_texture()

                    elif event.key == K_l:
                        self.toggle_shading()

                    elif event.key == K_h:
                        self.toggle_shadows()

            # ---------------- Continuous input ----------------
            # Camera motion is polled each frame so held keys feel continuous.
            if not self._modal_active():
                keys = pygame.key.get_pressed()
                ctrl_held = bool(pygame.key.get_mods() & KMOD_CTRL)
                orbit_step = self.camera_orbit_step * (2.0 if ctrl_held else 1.0)
                if keys[K_LEFT]:
                    self.camera_yaw_deg -= orbit_step
                if keys[K_RIGHT]:
                    self.camera_yaw_deg += orbit_step
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

            yaw = math.radians(self.camera_yaw_deg)
            pitch = math.radians(self.camera_pitch_deg)
            cx, cy, cz = self.model_center
            cos_pitch = math.cos(pitch)
            eye_x = cx + self.camera_radius * cos_pitch * math.cos(yaw)
            eye_y = cy + self.camera_radius * math.sin(pitch)
            eye_z = cz + self.camera_radius * cos_pitch * math.sin(yaw)

            # The model is re-centered before drawing, so the orbit target stays fixed at the origin.
            gluLookAt(eye_x, eye_y, eye_z, 0, 0, 0, 0, 1, 0)

            # ---------------- Draw grid ----------------
            glBegin(GL_LINES)
            glColor3f(0.0, 0.8, 1.0)
            grid_range = int(max(10, self.model_size / 2))
            for x in range(-grid_range, grid_range + 1):
                glVertex3f(x, self.grid_y, -grid_range)
                glVertex3f(x, self.grid_y, grid_range)
            for z in range(-grid_range, grid_range + 1):
                glVertex3f(-grid_range, self.grid_y, z)
                glVertex3f(grid_range, self.grid_y, z)
            glEnd()

            # ---------------- Draw model ----------------
            if self.model_data:
                textured = self.texture_id is not None and self.show_texture and not self.wireframe
                if textured:
                    glEnable(GL_TEXTURE_2D)
                    glEnable(GL_BLEND)
                    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                else:
                    glDisable(GL_TEXTURE_2D)
                    glColor3f(0.6, 0.8, 1.0)
                glPushMatrix()
                # Models are recentered around their computed midpoint so they
                # load at the world origin instead of carrying source offsets.
                translate_x = -self.model_center[0]
                translate_y = -self.model_center[1]
                translate_z = -self.model_center[2]
                glTranslatef(translate_x, translate_y, translate_z)
                if textured and self.active_paint_color is not None and self.tinted_texture_color != self.active_paint_color:
                    self._rebuild_tinted_texture_variants()

                opaque_indices = self.render_bucket_indices["opaque"]
                glasse_frame_indices = self.render_bucket_indices["glasse_frame"]
                transparent_indices = self.render_bucket_indices["transparent"]

                # Fast textured shading uses one cached light factor per
                # submesh, avoiding per-vertex Python color calls.
                self._draw_projected_ground_shadow(translate_y, self.submesh_render_roles)
                if textured:
                    glEnable(GL_TEXTURE_2D)

                for submesh_indices in (opaque_indices, glasse_frame_indices, transparent_indices):
                    for i in submesh_indices:
                        sm = self.model_data["submeshes"][i]
                        if i < len(self.submesh_visibility) and not self.submesh_visibility[i]:
                            continue
                        if not sm["vertices"]:
                            continue
                        prepared = self.prepared_submeshes[i] if i < len(self.prepared_submeshes) else None
                        if prepared is None or prepared.vertices is None:
                            continue

                        role = self.submesh_render_roles[i] if i < len(self.submesh_render_roles) else "opaque_neutral"
                        alpha = self._role_alpha_for_submesh(i, role)
                        submesh_texture_id = self.texture_id
                        if textured:
                            if self.active_paint_color is not None:
                                texture_mode = self.submesh_texture_modes[i] if i < len(self.submesh_texture_modes) else "base"
                                if texture_mode == "glasse_frame" and self.glasse_frame_texture_id is not None:
                                    submesh_texture_id = self.glasse_frame_texture_id
                                elif texture_mode == "body" and self.body_tinted_texture_id is not None:
                                    submesh_texture_id = self.body_tinted_texture_id
                            glBindTexture(GL_TEXTURE_2D, submesh_texture_id)
                            glDisable(GL_ALPHA_TEST)

                        verts_np = prepared.vertices
                        shade = self._shade_factor_for_submesh(i, role)
                        if textured:
                            glColor4f(shade, shade, shade, alpha)
                        elif not self.wireframe:
                            glColor4f(0.6 * shade, 0.8 * shade, 1.0 * shade, alpha)
                        glBegin(GL_TRIANGLES)
                        for f in sm["faces"]:
                            for vi in f:
                                try:
                                    if textured:
                                        u = verts_np[vi][6]
                                        v = verts_np[vi][7]
                                        glTexCoord2f(u, v)
                                    glVertex3f(*verts_np[vi][:3])
                                except Exception:
                                    continue
                        glEnd()
                glPopMatrix()
                if textured:
                    glDisable(GL_ALPHA_TEST)
                    glBindTexture(GL_TEXTURE_2D, 0)
                    glDisable(GL_TEXTURE_2D)
                    glDisable(GL_BLEND)

            self._draw_toolbar()
            self._draw_sidebar()
            self._draw_inspector()
            self._draw_statusbar()
            self._draw_modal()

            pygame.display.flip()
            clock.tick(60)

        self._set_camera_orbit_drag(False)
        self._set_camera_full_orbit_drag(False)
        self._clear_toolbar_label_textures()
        pygame.quit()
        pygame.quit()


# -------------------------------------------------------------------------

if __name__ == "__main__":
    viewer = SMFViewer()
    print(__doc__)
    viewer.run()
