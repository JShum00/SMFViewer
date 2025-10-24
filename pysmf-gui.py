"""
Python-SMF Viewer GUI
Author: Johnny Shumway (jShum00)

A simple 3D model viewer for Terminal Reality .SMF files.
Uses PyGame + PyOpenGL for real-time rendering and Tkinter for file dialogs.

Controls:
  O: Open SMF model
  E: Export to OBJ
  SPACE: Pause/Resume incremental draw
  W: Toggle wireframe
  Arrow Keys: Orbit camera left/right
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


class SMFViewer:
    """A basic OpenGL-based SMF model viewer with orbit camera and OBJ export."""

    def __init__(self, width=1024, height=768):
        """Initialize window, OpenGL context, and default state."""
        pygame.init()
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
        self.camera_radius = 20.0
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
            time.sleep(0.01)

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

                elif event.type == KEYDOWN:
                    if event.key == K_SPACE:
                        self.paused = not self.paused
                        print("Paused" if self.paused else "Resumed")

                    elif event.key == K_o:
                        self.load_smf()

                    elif event.key == K_e:
                        if not self.model_data:
                            print("No model loaded to export.")
                            continue

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

                    elif event.key == K_w:
                        self.wireframe = not self.wireframe
                        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe else GL_FILL)
                        print("Wireframe mode:", self.wireframe)

            # ---------------- Continuous input ----------------
            keys = pygame.key.get_pressed()
            if keys[K_LEFT]:
                self.camera_angle_az -= 1.0
            if keys[K_RIGHT]:
                self.camera_angle_az += 1.0

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

            pygame.display.flip()
            clock.tick(60)

        pygame.quit()


# -------------------------------------------------------------------------

if __name__ == "__main__":
    viewer = SMFViewer()
    print(__doc__)
    viewer.run()

