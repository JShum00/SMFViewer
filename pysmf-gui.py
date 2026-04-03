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
  Arrow Keys: Orbit camera left/right
  Numpad +/-: Camera Zoom
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
    K_ESCAPE,
    K_KP_MINUS,
    K_KP_PLUS,
    K_LEFT,
    K_RIGHT,
    K_SPACE,
    K_e,
    K_m,
    K_o,
    K_w,
    MOUSEBUTTONDOWN,
    MOUSEMOTION,
    OPENGL,
    QUIT,
)
from tkinter import Tk, filedialog, messagebox

from pysmf import ParsedModel, SMFParser
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


class SMFViewer:
    """A basic OpenGL-based SMF model viewer with orbit camera and OBJ export."""

    def __init__(self, width: int = 1600, height: int = 900) -> None:
        """Initialize window, OpenGL context, and default state."""
        pygame.init()
        glutInit()
        self.width = width
        self.height = height
        self.toolbar_height = 64
        self.statusbar_height = 34
        self.sidebar_width = 280
        pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL)
        pygame.display.set_caption("SMF Viewer")

        self._configure_3d_viewport()

        # Default OpenGL state
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glEnable(GL_DEPTH_TEST)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)  # start in wireframe mode

        # Button Data
        self.button_labels: list[str] = ["Open", "Export", "Wireframe", "Texture", "Exit"]
        self.buttons: list[tuple[int, int, int, int]] = []
        self.hover_index: int | None = None
        self.mesh_row_rects: list[tuple[int, int, int, int]] = []
        self.mesh_eye_rects: list[tuple[int, int, int, int]] = []
        self.hover_mesh_row_index: int | None = None
        self.hover_mesh_eye_index: int | None = None

        # Model state
        self.model_data: ParsedModel | None = None
        self.model_center: np.ndarray = np.array([0.0, 0.0, 0.0])
        self.model_size: float = 1.0
        self.last_loaded_path: str | None = None
        self.texture_id: int | None = None
        self.submesh_visibility: list[bool] = []
        self._state_lock = threading.Lock()
        self._pending_model_load: PendingModelLoad | None = None

        # Drawing state
        self.wireframe = True
        self.show_texture = False

        # Camera state
        self.camera_radius = 20.0    # how far we orbit from target
        self.camera_angle_az = 25.0  # degrees around Y-axis
        self.camera_height = 4.0     # height above ground

    # -------------------------------------------------------------------------

    def _configure_3d_viewport(self) -> None:
        """Reserve space for the toolbar and status bar and update the 3D projection."""
        viewport_height = max(1, self.height - self.toolbar_height - self.statusbar_height)
        viewport_width = max(1, self.width - self.sidebar_width)
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

    def _draw_text(self, x: float, y: float, text: str) -> None:
        """Draw GLUT bitmap text in 2D overlay coordinates."""
        glRasterPos2f(x, y)
        for ch in text:
            glutBitmapCharacter(GLUT_BITMAP_HELVETICA_18, ord(ch))

    # -------------------------------------------------------------------------

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
        left = 16
        top = 12
        bottom = toolbar_bottom - 12

        for i, label in enumerate(self.button_labels):
            width = self._button_width(label)
            right = left + width
            self.buttons.append((left, top, right, bottom))

            if i == self.hover_index:
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
        row_width = self.sidebar_width - 28

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

        if self.model_data is not None:
            row_top = root_bottom + row_gap
            for i, submesh in enumerate(self.model_data["submeshes"]):
                row_bottom = row_top + row_height
                row_left = root_left
                row_right = root_left + row_width
                eye_right = row_right - 10
                eye_left = eye_right - eye_size
                eye_top = row_top + 5
                eye_bottom = eye_top + eye_size
                visible = self.submesh_visibility[i] if i < len(self.submesh_visibility) else True

                self.mesh_row_rects.append((row_left, row_top, row_right, row_bottom))
                self.mesh_eye_rects.append((eye_left, eye_top, eye_right, eye_bottom))

                if i == self.hover_mesh_row_index:
                    glColor4f(0.20, 0.20, 0.20, 1.0)
                    glBegin(GL_QUADS)
                    glVertex2f(row_left, row_top)
                    glVertex2f(row_right, row_top)
                    glVertex2f(row_right, row_bottom)
                    glVertex2f(row_left, row_bottom)
                    glEnd()

                glColor3f(0.88, 0.88, 0.88) if visible else glColor3f(0.48, 0.48, 0.48)
                self._draw_text(child_left, row_top + 19, submesh["name"])
                self._draw_eye_icon(
                    eye_left,
                    eye_top,
                    eye_right,
                    eye_bottom,
                    visible=visible,
                    hovered=(i == self.hover_mesh_eye_index),
                )
                row_top = row_bottom + row_gap

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
        except Exception as exc:
            print(f"Warning: failed to load texture {texture_path}: {exc}")
            return None

    # -------------------------------------------------------------------------

    def load_texture(self, smf_path: str) -> TexturePayload | None:
        """Load a texture from ../ART or prompt the user to choose one manually."""
        model_dir = os.path.dirname(smf_path)
        model_name = os.path.splitext(os.path.basename(smf_path))[0]
        texture_dir = os.path.normpath(os.path.join(model_dir, "..", "ART"))
        candidates = [
            os.path.join(texture_dir, f"{model_name}{ext}")
            for ext in (".TIF", ".tif", ".TIFF", ".tiff")
        ]

        texture_path = next((candidate for candidate in candidates if os.path.exists(candidate)), None)
        if texture_path is not None:
            print(f"Loaded texture: {texture_path}")
            return self._decode_texture(texture_path)

        print(f"Warning: texture not found in {texture_dir} for model {model_name}")

        prompt_root = Tk()
        prompt_root.withdraw()
        should_select = messagebox.askyesno(
            "Texture Not Found",
            "We could not find the associated texture for the model. "
            "Would you like to select it manually?",
            parent=prompt_root,
        )

        if not should_select:
            prompt_root.destroy()
            return None

        texture_path = filedialog.askopenfilename(
            parent=prompt_root,
            title="Select Texture File",
            initialdir=texture_dir if os.path.isdir(texture_dir) else model_dir,
            filetypes=[("TIFF files", ("*.tif", "*.TIF", "*.tiff", "*.TIFF")), ("All files", "*.*")],
        )
        prompt_root.destroy()

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
        self.mesh_row_rects = []
        self.mesh_eye_rects = []
        self.hover_mesh_row_index = None
        self.hover_mesh_eye_index = None

        print_smf_summary(self.last_loaded_path)
        print(
            f"Loaded {pending['total_verts']} vertices and "
            f"{pending['total_faces']} faces from {self.last_loaded_path}"
        )

    # -------------------------------------------------------------------------

    def load_smf(self) -> None:
        """Open file dialog and load an SMF model."""
        root = Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Select SMF File",
            filetypes=[("SMF files", ("*.smf", "*.SMF")), ("All files", "*.*")]
        )
        root.destroy()
        if not path:
            return

        parser = SMFParser()
        model_data = parser.parse(path)
        texture_payload = self.load_texture(path)

        # Flatten all vertices for global metrics
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
        self.wireframe = not self.wireframe
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe else GL_FILL)
        print("Wireframe mode:", self.wireframe)

    # -------------------------------------------------------------------------

    def toggle_texture(self) -> None:
        if self.texture_id is None:
            self.show_texture = False
            print("Texture view: unavailable (no texture loaded)")
            return

        self.show_texture = not self.show_texture
        print("Texture view:", self.show_texture)

    # -------------------------------------------------------------------------

    def export_obj(self) -> None:
        if not self.model_data:
            print("No model loaded to export.")
            return

        root = Tk()
        root.withdraw()
        obj_path = filedialog.asksaveasfilename(
            title="Export SMF as OBJ",
            defaultextension=".obj",
            filetypes=[("Wavefront OBJ", "*.obj")]
        )
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
                elif event.type == MOUSEMOTION:
                    mx, my = event.pos
                    self.hover_index = None
                    self.hover_mesh_row_index = None
                    self.hover_mesh_eye_index = None
                    for i, (left, top, right, bottom) in enumerate(self.buttons):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_index = i
                            break
                    for i, (left, top, right, bottom) in enumerate(self.mesh_row_rects):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_mesh_row_index = i
                            break
                    for i, (left, top, right, bottom) in enumerate(self.mesh_eye_rects):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_mesh_eye_index = i
                            break
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    for i, (left, top, right, bottom) in enumerate(self.buttons):
                        if left <= mx <= right and top <= my <= bottom:
                            label = self.button_labels[i]
                            running = self._handle_button_action(label)
                            break
                    else:
                        for i, (left, top, right, bottom) in enumerate(self.mesh_eye_rects):
                            if left <= mx <= right and top <= my <= bottom:
                                if i < len(self.submesh_visibility):
                                    self.submesh_visibility[i] = not self.submesh_visibility[i]
                                    state = "shown" if self.submesh_visibility[i] else "hidden"
                                    if self.model_data is not None and i < len(self.model_data["submeshes"]):
                                        print(f"Submesh {self.model_data['submeshes'][i]['name']}: {state}")
                                break
                elif event.type == KEYDOWN:
                    if event.key == K_SPACE:
                        print("SPACE is a legacy no-op. Incremental draw has been removed.")

                    elif event.key == K_o:
                        threading.Thread(target=self.load_smf, daemon=True).start()

                    elif event.key == K_e:
                        threading.Thread(target=self.export_obj, daemon=True).start()

                    elif event.key == K_w:
                        self.toggle_wireframe()

                    elif event.key == K_m:
                        self.toggle_texture()

            # ---------------- Continuous input ----------------
            keys = pygame.key.get_pressed()
            if keys[K_LEFT]:
                self.camera_angle_az -= 1.0
            if keys[K_RIGHT]:
                self.camera_angle_az += 1.0
            if keys[K_KP_PLUS]:
                self.camera_radius += 1.0
            if keys[K_KP_MINUS]:
                self.camera_radius -= 1.0            

            # ---------------- Camera setup ----------------
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT) # pyright: ignore[reportOperatorIssue]
            glLoadIdentity()

            theta = math.radians(self.camera_angle_az)
            cx, cy, cz = self.model_center
            eye_x = cx + self.camera_radius * math.cos(theta)
            eye_y = cy + self.camera_height
            eye_z = cz + self.camera_radius * math.sin(theta)

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
                    glColor3f(1.0, 1.0, 1.0)
                else:
                    glDisable(GL_TEXTURE_2D)
                    glColor3f(0.6, 0.8, 1.0)
                glPushMatrix()
                glTranslatef(-self.model_center[0],
                             -self.model_center[1] + 2.0,
                             -self.model_center[2] + 2.0)
                for i, sm in enumerate(self.model_data["submeshes"]):
                    if i < len(self.submesh_visibility) and not self.submesh_visibility[i]:
                        continue
                    if not sm["vertices"]:
                        continue
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
            self._draw_statusbar()

            pygame.display.flip()
            clock.tick(60)

        pygame.quit()


# -------------------------------------------------------------------------

if __name__ == "__main__":
    viewer = SMFViewer()
    print(__doc__)
    viewer.run()
