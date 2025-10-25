"""
Python-SMF Viewer GUI
Author: Johnny Shumway (jShum00)

A simple 3D model viewer for Terminal Reality .SMF files.
Uses PyGame + PyOpenGL for real-time rendering and Tkinter for file dialogs.

Controls:
  O: Open SMF model
  E: Export to OBJ
  W: Toggle wireframe
  Arrow Keys: Orbit camera left/right
  Numpad +/-: Camera Zoom
  SPACE: Pause/Resume incremental draw
  ESC: Quit viewer
"""

import os
import threading
import time
import math
import numpy as np
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
from tkinter import filedialog, Tk
from pysmf import SMFParser
from pysmf_export import export_to_obj
from pysmf_print import print_smf_summary
from OpenGL.GLUT import glutInit, glutBitmapCharacter, GLUT_BITMAP_HELVETICA_18

class SMFViewer:
    """A basic OpenGL-based SMF model viewer with orbit camera and OBJ export."""

    def __init__(self, width=1600, height=900):
        """Initialize window, OpenGL context, and default state."""
        pygame.init()
        glutInit()
        self.width = width
        self.height = height
        pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL)
        pygame.display.set_caption("SMF Viewer")

        # Projection setup
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, width / height, 0.1, 1000.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # Default OpenGL state
        glClearColor(0.1, 0.1, 0.1, 1.0)
        glEnable(GL_DEPTH_TEST)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)  # start in wireframe mode

        # UI Data
        self.ui_visible = True
        self.ui_alpha = 0.35
        self.last_mouse_move = time.time()
        self.ui_fade_speed = 0.01
        self.ui_timeout = 1.0

        # Button Data
        self.button_labels = ["Open", "Export", "Wireframe", "Exit"]
        self.buttons = []
        self.hover_index = None

        # Model state
        self.model_data = None
        self.model_center = np.array([0.0, 0.0, 0.0])
        self.model_size = 1.0
        self.last_loaded_path = None

        # Drawing state
        self.drawing = False
        self.paused = False
        self.draw_index = 0
        self.wireframe = True

        # Camera state
        self.camera_radius = 20.0    # how far we orbit from target
        self.camera_angle_az = 25.0  # degrees around Y-axis
        self.camera_height = 4.0     # height above ground

        # Start background thread to handle incremental drawing
        threading.Thread(target=self.draw_model_incremental, daemon=True).start()


    # -------------------------------------------------------------------------

    def load_smf(self):
        """Open file dialog and load an SMF model."""
        root = Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Select SMF File",
            filetypes=[("SMF files", "*.smf"), ("All files", "*.*")]
        )
        root.destroy()
        if not path:
            return

        self.last_loaded_path = path
        parser = SMFParser()
        self.model_data = parser.parse(path)
        
        # Print parser summary to the console        
        print_smf_summary(path)

        # Flatten all vertices for global metrics
        verts = np.concatenate([np.array(sm["vertices"]) for sm in self.model_data["submeshes"]], axis=0)
        self.model_center = verts[:, :3].mean(axis=0)
        self.model_size = np.linalg.norm(verts[:, :3].ptp(axis=0))

        total_verts = verts.shape[0]
        total_faces = sum(len(sm["faces"]) for sm in self.model_data["submeshes"])
        print(f"Loaded {total_verts} vertices and {total_faces} faces from {path}")

        self.drawing = True
        self.draw_index = 0

    # -------------------------------------------------------------------------

    def draw_model_incremental(self):
        """Progressively reveal model submeshes over time."""
        while True:
            if self.drawing and not self.paused and self.model_data:
                if self.draw_index < len(self.model_data["submeshes"]):
                    self.draw_index += 1
                else:
                    self.drawing = False
            time.sleep(0.1)

    # -------------------------------------------------------------------------

    def toggle_wireframe(self):
        self.wireframe = not self.wireframe
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe else GL_FILL)
        print("Wireframe mode:", self.wireframe)

    # -------------------------------------------------------------------------

    def export_obj(self):
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

        if obj_path:
            try:
                export_to_obj(self.last_loaded_path, obj_path)
            except AttributeError:
                print("No SMF path cached. Reopen model before exporting.")
        else:
            print("Export cancelled.")

    # -------------------------------------------------------------------------
    
    def run(self):
        """Main event/render loop."""
        clock = pygame.time.Clock()
        running = True

        while running:
            # ---------------- Event handling ----------------
            for event in pygame.event.get():
                if event.type == QUIT or (event.type == KEYDOWN and event.key == K_ESCAPE):
                    running = False
                elif event.type == MOUSEMOTION:
                    mx, my = event.pos
                    self.last_mouse_move = time.time() # reset timer
                    self.hover_index = None
                    for i, (left, top, right, bottom) in enumerate(self.buttons):
                        if left <= mx <= right and top <= my <= bottom:
                            self.hover_index = i
                            break
                elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                    mx, my = event.pos
                    for i, (left, top, right, bottom) in enumerate(self.buttons):
                        if left <= mx <= right and top <= my <= bottom:
                            label = self.button_labels[i]
                            print(f"[UI] {label} clicked")
                            if label == "Exit":
                                running = False
                            elif label == "Wireframe":
                                self.toggle_wireframe()
                            elif label == "Open":
                                threading.Thread(target=self.load_smf, daemon=True).start()
                            elif label == "Export":
                                threading.Thread(target=self.export_obj, daemon=True).start()
                elif event.type == KEYDOWN:
                    if event.key == K_SPACE:
                        self.paused = not self.paused
                        print("Paused" if self.paused else "Resumed")

                    elif event.key == K_o:
                        threading.Thread(target=self.load_smf, daemon=True).start()

                    elif event.key == K_e:
                        threading.Thread(target=self.export_obj, daemon=True).start()

                    elif event.key == K_w:
                        self.toggle_wireframe()

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
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
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
                glColor3f(0.6, 0.8, 1.0)
                glPushMatrix()
                glTranslatef(-self.model_center[0],
                             -self.model_center[1] + 2.0,
                             -self.model_center[2] + 2.0)
                for sm in self.model_data["submeshes"][:self.draw_index]:
                    verts_np = np.array(sm["vertices"])
                    glBegin(GL_TRIANGLES)
                    for f in sm["faces"]:
                        for vi in f:
                            try:
                                glVertex3f(*verts_np[vi][:3])
                            except Exception:
                                continue
                    glEnd()
                glPopMatrix()

            # --------------- Fade Overlay ---------------
            idle_time = time.time() - self.last_mouse_move
            if idle_time > self.ui_timeout:
                self.ui_visible = False
            else:
                self.ui_visible = True

            # Fade toward Target
            target_alpha = 0.35 if self.ui_visible else 0.0
            if self.ui_alpha < target_alpha:
                self.ui_alpha = min(self.ui_alpha + self.ui_fade_speed, target_alpha)
            elif self.ui_alpha > target_alpha:
                self.ui_alpha = max(self.ui_alpha - self.ui_fade_speed, target_alpha)

            # skip UI draw entirely if fully hidden
            if self.ui_alpha <= 0.01:
                pygame.display.flip()
                clock.tick(60)
                continue

            # --------------- Draw overlay ---------------
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

            glMatrixMode(GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity()
            glOrtho(0, self.width, self.height, 0, -1, 1)
            glMatrixMode(GL_MODELVIEW)
            glPushMatrix()
            glLoadIdentity()

            # Draw semi-transparent rectangle
            panel_width = self.width // 5
            glColor4f(0.0, 0.0, 0.0, self.ui_alpha * 0.35) # 35% Opacity, Black
            glBegin(GL_QUADS)
            glVertex2f(self.width - panel_width, 0)             # bottom-left
            glVertex2f(self.width, 0)                           # bottom-right
            glVertex2f(self.width, self.height)                 # top-left
            glVertex2f(self.width - panel_width, self.height)   # top-right
            glEnd()


            # ------------------ Draw button ------------------------
            self.buttons = []
            button_count = 4
            button_height = 50
            button_spacing = (self.height - (button_count * button_height)) // (button_count + 1)
            panel_width = self.width // 5

            for i in range(button_count):
                    top = button_spacing + i * (button_height + button_spacing)
                    bottom = top + button_height + 20
                    left = self.width - panel_width + 20
                    right = self.width - 20
                    self.buttons.append((left, top, right, bottom))
                    
                    # hover highlight
                    if i == self.hover_index:
                        glColor4f(0.6, 0.6, 0.6, self.ui_alpha + 1.0)
                    else:
                        glColor4f(0.3, 0.3, 0.3, self.ui_alpha)

                    glBegin(GL_QUADS)
                    glVertex2f(left, top)
                    glVertex2f(right, top)
                    glVertex2f(right, bottom)
                    glVertex2f(left, bottom)
                    glEnd()

            # --- Draw Button Labels ---
            glColor3f(1.0, 1.0, 1.0)    # white text
            for i, label in enumerate(self.button_labels):
                top = button_spacing + i * (button_height + button_spacing)
                left = self.width - panel_width + 40
                baseline = top + (button_height) + 5

                glRasterPos2f(left, baseline)
                for ch in label:
                    glutBitmapCharacter(GLUT_BITMAP_HELVETICA_18, ord(ch))

            # Restore 3D State
            glDisable(GL_BLEND)
            glMatrixMode(GL_MODELVIEW)
            glPopMatrix()
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glEnable(GL_DEPTH_TEST)

            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe else GL_FILL)

            pygame.display.flip()
            clock.tick(60)

        pygame.quit()


# -------------------------------------------------------------------------

if __name__ == "__main__":
    viewer = SMFViewer()
    print(__doc__)
    viewer.run()

