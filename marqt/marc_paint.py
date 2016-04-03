__author__ = 'mpevans'

from OpenGL.GL import *

from PyQt5 import QtOpenGL
from PyQt5 import QtGui
from PyQt5 import QtCore
from PyQt5 import QtWidgets
from PyQt5.QtOpenGL import *
import PyQt5 as Qt
import math
import time
import numpy as np
from PyQt5.QtGui import QImage
from PyQt5.QtGui import QOpenGLTexture
from marcpy.utilities import enum

CornerTypes = enum(NONE="none", ROUNDED="rounded", FLAT_BRUSH="flat brush")
ResizeModes = enum(STRETCH="stretch", ANCHOR_MIDDLE="anchor middle", ANCHOR_CORNER="anchor corner")
TextAnchorType = enum(ANCHOR_CENTER="anchor middle", ANCHOR_CORNER="anchor corner")


class Keys:
    UP = QtCore.Qt.Key_Up
    DOWN = QtCore.Qt.Key_Down
    LEFT = QtCore.Qt.Key_Left
    RIGHT = QtCore.Qt.Key_Right
    BACKSPACE = QtCore.Qt.Key_Backspace
    RETURN = QtCore.Qt.Key_Return

class MarcPaintWidget(QGLWidget):

    VERTICES_PER_SEMICIRCLE = 6
    DOUBLE_CLICK_TIME = 0.3

    def __init__(self, parent=None, title="A Marc Paint Widget", view_bounds=(0, 1, 0, 1), window_size=(500, 500),
                 bg_color=(0.0, 0.0, 0.0, 1.0), textures={}):
        thisFormat = QGLFormat()
        thisFormat.setSampleBuffers(True)
        thisFormat.setSamples(16)
        super(MarcPaintWidget, self).__init__(thisFormat, parent)

        self.shapes = []
        self.view_bounds = view_bounds
        self.setMouseTracking(True)
        self.click_started = False
        self.click_buttons = None
        self.click_count = 1
        self.last_click = -1
        self.setWindowTitle(title)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.do_animate_frame)
        load_timer = QtCore.QTimer()
        load_timer.singleShot(0, self.on_load)
        self.last_animate = None
        self.time = 0
        self.setGeometry((get_screen_width() - window_size[0])/2,
                         (get_screen_height() - window_size[1])/2,
                         window_size[0], window_size[1])
        self.bg_color = bg_color
        self.setAutoFillBackground(False)
        self.last_resize = None
        self.resize_mode = ResizeModes.ANCHOR_MIDDLE
        self.animation_layers = []
        self.textures = {}
        self.texture_images = {}
        self.textures_to_load = textures
        self.squash_factor = float(self.get_view_width()) * self.height() / self.width() / self.get_view_height()

    def set_view_bounds(self, x_min, x_max, y_min, y_max):
        self.view_bounds = (x_min, x_max, y_min, y_max)
        self.squash_factor = float(self.get_view_width()) * self.height() / self.width() / self.get_view_height()
        vp = glGetIntegerv(GL_VIEWPORT)
        self.setup_2D_view(vp[2], vp[3])

    def get_view_width(self):
        return self.view_bounds[1] - self.view_bounds[0]

    def get_view_height(self):
        return self.view_bounds[3] - self.view_bounds[2]

    def set_window_size(self, width, height):
        self.setGeometry((get_screen_width() - width)/2,
                         (get_screen_height() - height)/2,
                         width, height)
        self.squash_factor = float(self.get_view_width()) * height / width / self.get_view_height()

    def set_resize_mode(self, resize_mode):
        self.resize_mode = resize_mode

    def set_bg_color(self, *color):
        self.bg_color = color

    def paintGL(self):
        self.load_queued_textures()
        glClear(GL_COLOR_BUFFER_BIT)
        vp = glGetIntegerv(GL_VIEWPORT)
        self.setup_2D_view(vp[2], vp[3])
        for shape in self.shapes:
            if isinstance(shape, TextShape):
                if shape.includes_alpha:
                    glColor4f(*shape.color)
                else:
                    glColor3f(*shape.color)
                shape.set_font_and_position()
                self.renderText(shape.position[0], shape.position[1], shape.text, shape.font)
            else:
                shape.do_set_up()
                shape.do_paint_calls()
                shape.do_clean_up()
        self.do_extra_painting()

    def do_extra_painting(self):
        # for any extra opengl called to be done after the flat drawing
        pass

    def resizeGL(self, w, h):
        self.load_queued_textures()
        if self.resize_mode is not ResizeModes.STRETCH:
            if self.last_resize is None:
                self.last_resize = (w, h)
            else:
                delta_width = self.get_view_width() * (float(w)/self.last_resize[0] - 1)
                delta_height = self.get_view_height() * (float(h)/self.last_resize[1] - 1)
                if self.resize_mode is ResizeModes.ANCHOR_MIDDLE:
                    self.view_bounds = (self.view_bounds[0] - delta_width/2,
                                        self.view_bounds[1] + delta_width/2,
                                        self.view_bounds[2] - delta_height/2,
                                        self.view_bounds[3] + delta_height/2)
                else:
                    self.view_bounds = (self.view_bounds[0],
                                        self.view_bounds[1] + delta_width,
                                        self.view_bounds[2] - delta_height,
                                        self.view_bounds[3])
                self.last_resize = (w, h)

        self.setup_2D_view(w, h)
        self.squash_factor = float(self.get_view_width()) * self.height() / self.width() / self.get_view_height()

    def setup_2D_view(self, w, h):
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(self.view_bounds[0], self.view_bounds[1], self.view_bounds[2], self.view_bounds[3], -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW);
        glLoadIdentity();
        glViewport(0, 0, w, h)

    def initializeGL(self):
        self.load_queued_textures()
        if len(self.bg_color) == 3:
            glClearColor(*(self.bg_color + (1.0, )))
        else:
            glClearColor(*self.bg_color)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_MULTISAMPLE)

    def load_texture(self, name, path):
        self.textures_to_load[name] = path

    def load_queued_textures(self):
        for tex_name in self.textures_to_load.keys():
            tex_path = self.textures_to_load.pop(tex_name)
            this_image = QImage(tex_path)
            self.texture_images[tex_name] = this_image
            self.textures[tex_name] = QOpenGLTexture(this_image.mirrored())

    def show(self):
        super(MarcPaintWidget, self).show()
        self.raise_()

    ######### User Interaction Backend ########

    def mousePressEvent(self, event):
        buttons_and_modifiers = []
        if event.buttons() == QtCore.Qt.LeftButton:
            buttons_and_modifiers.append("left")
        if event.buttons() == QtCore.Qt.RightButton:
            buttons_and_modifiers.append("right")
        if event.modifiers() & QtCore.Qt.ShiftModifier:
            buttons_and_modifiers.append("shift")
        if event.modifiers() & QtCore.Qt.MetaModifier:
            buttons_and_modifiers.append("control")
        if event.modifiers() & QtCore.Qt.AltModifier:
            buttons_and_modifiers.append("alt")
        if event.modifiers() & QtCore.Qt.ControlModifier:
            buttons_and_modifiers.append("meta")
        self.click_started = True
        self.click_buttons = buttons_and_modifiers
        self.on_mouse_down(self.mouse_event_to_view_location(event), buttons_and_modifiers)
        super(MarcPaintWidget, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        buttons_and_modifiers = []
        if event.buttons() == QtCore.Qt.LeftButton:
            buttons_and_modifiers.append("left")
        if event.buttons() == QtCore.Qt.RightButton:
            buttons_and_modifiers.append("right")
        if event.modifiers() & QtCore.Qt.ShiftModifier:
            buttons_and_modifiers.append("shift")
        if event.modifiers() & QtCore.Qt.MetaModifier:
            buttons_and_modifiers.append("control")
        if event.modifiers() & QtCore.Qt.AltModifier:
            buttons_and_modifiers.append("alt")
        if event.modifiers() & QtCore.Qt.ControlModifier:
            buttons_and_modifiers.append("meta")
        self.on_mouse_up(self.mouse_event_to_view_location(event), buttons_and_modifiers)
        if self.click_started:
            self.click_started = False
            if time.time() - self.last_click < MarcPaintWidget.DOUBLE_CLICK_TIME:
                self.click_count += 1
            else:
                self.click_count = 1
            self.last_click = time.time()
            self.on_mouse_click(self.mouse_event_to_view_location(event), self.click_buttons, self.click_count)
            self.click_buttons = None
        super(MarcPaintWidget, self).mousePressEvent(event)

    def wheelEvent(self, event):
        self.on_mouse_scroll(event.angleDelta().x(), event.angleDelta().y())

    def mouseMoveEvent(self, event):
        self.click_started = False
        self.click_buttons = None
        if event.buttons() == QtCore.Qt.NoButton:
            self.on_mouse_move(self.mouse_event_to_view_location(event))
        else:
            buttons_and_modifiers = []
            if event.buttons() == QtCore.Qt.LeftButton:
                buttons_and_modifiers.append("left")
            if event.buttons() == QtCore.Qt.RightButton:
                buttons_and_modifiers.append("right")
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                buttons_and_modifiers.append("shift")
            if event.modifiers() & QtCore.Qt.MetaModifier:
                buttons_and_modifiers.append("control")
            if event.modifiers() & QtCore.Qt.AltModifier:
                buttons_and_modifiers.append("alt")
            if event.modifiers() & QtCore.Qt.ControlModifier:
                buttons_and_modifiers.append("meta")
            self.on_mouse_drag(self.mouse_event_to_view_location(event), buttons_and_modifiers)
        super(MarcPaintWidget, self).mouseMoveEvent(event)

    def mouse_event_to_view_location(self, event):
        return self.view_bounds[0] + (self.view_bounds[1] - self.view_bounds[0]) * float(event.x())/self.width(), \
            self.view_bounds[2] + (self.view_bounds[3] - self.view_bounds[2]) * (1-float(event.y())/self.height())

    def keyPressEvent(self, event):
        modifiers = []
        if event.modifiers() & QtCore.Qt.ShiftModifier:
            modifiers.append("shift")
        if event.modifiers() & QtCore.Qt.MetaModifier:
            modifiers.append("control")
        if event.modifiers() & QtCore.Qt.AltModifier:
            modifiers.append("alt")
        if event.modifiers() & QtCore.Qt.ControlModifier:
            modifiers.append("meta")
        self.on_key_press(event.key(), modifiers)

    def keyReleaseEvent(self, event):
        modifiers = []
        if event.modifiers() & QtCore.Qt.ShiftModifier:
            modifiers.append("shift")
        if event.modifiers() & QtCore.Qt.MetaModifier:
            modifiers.append("control")
        if event.modifiers() & QtCore.Qt.AltModifier:
            modifiers.append("alt")
        if event.modifiers() & QtCore.Qt.ControlModifier:
            modifiers.append("meta")
        self.on_key_release(event.key(), modifiers)

    def start_animation(self, interval):
        self.last_animate = time.time()
        self.do_animate_frame()
        self.timer.start(interval)

    def stop_animation(self):
        self.timer.stop()

    def do_animate_frame(self):
        now = time.time()
        self.animate(now - self.last_animate)
        continuing_animation_layers = []
        for animation_layer in self.animation_layers:
            if animation_layer(now - self.last_animate, now - animation_layer.start_time):
                continuing_animation_layers.append(animation_layer)
        self.animation_layers = continuing_animation_layers
        self.last_animate = now
        self.repaint()

    def add_animation_layer(self, animation_function):
        # animation layers return true if they want to continue, false if they want to stop.
        animation_function.start_time = time.time()
        self.animation_layers.append(animation_function)

    # PAINT CALLS TO USE!

    # TODO: draw_line_loop, which will act like draw_line_strip, except that it closes the loop (this also means that it needs to take the average perp between the first and last point
    # TODO: draw_triangles, which basically uses draw_line_loop (but it has to somehow be crammed into one draw call
    # TODO: draw_quads, likewise
    # TODO: fill_ellipses, which would draw circles using triangles. Would take one color for all, one per circle, or two per circle (inside, out)
    # TODO: fill_arcs, which would fill ellipsoid arcs, Would take one color for all, one per arc, two per arc (inside, out), or four per arc (inside, out, start, finish)
    # TODO: draw_circles, which would basically call fill_arcs

    def clear(self):
        self.shapes = []

    def draw_points(self, vertices, colors, width=None):
        if not isinstance(vertices, np.ndarray):
            vertices = np.array(vertices)
        if not isinstance(colors, np.ndarray):
            colors = np.array(colors)

        if vertices.ndim == 1:
            vertices = np.array((vertices, ))

        if width is not None:
            deviations = np.tile(np.array([[-width/2, -width/2],
                                   [-width/2, width/2],
                                   [width/2, -width/2],
                                   [width/2, width/2],
                                   [-width/2, width/2],
                                   [width/2, -width/2]]), (vertices.shape[0], 1))
            triangle_vertices = vertices.repeat(6, axis=0) + deviations
            if colors.ndim == 1:
                self.fill_triangles(triangle_vertices, colors)
            else:
                self.fill_triangles(triangle_vertices, colors.repeat(6, axis=0))
        else:
            self.shapes.append(Points(vertices, colors))

    def fill_triangles(self, vertices, colors=None, texture=None, tex_coords=None):
        # takes a 2D array or list of vertices, and one of colors
        # either give a 1D array of RGB(A) values for color (all triangles painted that color)
        # or give a 2D array with one RGB(A) array for each vertex, or for each triangle
        if not isinstance(vertices, np.ndarray):
            vertices = np.array(vertices)
        if vertices.ndim == 1:
            vertices = np.array((vertices, ))

        if colors is not None:
            if not isinstance(colors, np.ndarray):
                colors = np.array(colors)

        if texture is not None:
            if texture not in self.textures.keys():
                texture = None
            elif not isinstance(tex_coords, np.ndarray):
                tex_coords = np.array(tex_coords)

        if texture is None and colors is None:
            colors = np.array((0, 0, 0))

        self.shapes.append(Triangles(vertices, colors=colors, texture=texture, tex_coords=tex_coords, texture_dict=self.textures))


    def fill_quads(self, vertices, colors=None, texture=None, tex_coords=None):
        if not isinstance(vertices, np.ndarray):
            vertices = np.array(vertices)

        if vertices.ndim == 1:
            vertices = np.array((vertices, ))

        first_corners = vertices[0::4]
        second_corners = vertices[1::4]
        third_corners = vertices[2::4]
        fourth_corners = vertices[3::4]
        triangle_vertices = np.empty([vertices.shape[0]*3/2, vertices.shape[1]])
        triangle_vertices[0::3, :] = first_corners.repeat(2, 0)
        triangle_vertices[2::3, :] = third_corners.repeat(2, 0)
        triangle_vertices[1::6, :] = second_corners
        triangle_vertices[4::6, :] = fourth_corners

        if texture is None:
            if colors is None:
                colors = np.array((0, 0, 0))
            if not isinstance(colors, np.ndarray):
                colors = np.array(colors)

            if colors.ndim == 2 and len(colors) == len(vertices):
                # one color per vertex, so colors like the vertices
                first_corners = colors[0::4]
                second_corners = colors[1::4]
                third_corners = colors[2::4]
                fourth_corners = colors[3::4]
                triangle_color_vertices = np.empty([colors.shape[0]*3/2, colors.shape[1]])
                triangle_color_vertices[0::3, :] = first_corners.repeat(2, 0)
                triangle_color_vertices[2::3, :] = third_corners.repeat(2, 0)
                triangle_color_vertices[1::6, :] = second_corners
                triangle_color_vertices[4::6, :] = fourth_corners
                colors = triangle_color_vertices
            elif colors.ndim == 2 and len(colors)*4 == len(vertices):
                # one color per quad, so just repeat each color once since we're getting two triangles
                colors = colors.repeat(2, 0)
            elif colors.ndim == 1:
                # nothing to do here: just one color for the whole thing
                pass
            else:
                raise WrongNumberOfVerticesException

            self.fill_triangles(triangle_vertices, colors)
        else:
            if texture not in self.textures.keys():
                return
            if not isinstance(tex_coords, np.ndarray):
                tex_coords = np.array(tex_coords)
            first_corners = tex_coords[0::4]
            second_corners = tex_coords[1::4]
            third_corners = tex_coords[2::4]
            fourth_corners = tex_coords[3::4]
            triangle_tex_vertices = np.empty([tex_coords.shape[0]*3/2, tex_coords.shape[1]])
            triangle_tex_vertices[0::3, :] = first_corners.repeat(2, 0)
            triangle_tex_vertices[2::3, :] = third_corners.repeat(2, 0)
            triangle_tex_vertices[1::6, :] = second_corners
            triangle_tex_vertices[4::6, :] = fourth_corners
            self.fill_triangles(triangle_vertices, colors=colors, texture=texture, tex_coords=triangle_tex_vertices)

    def draw_quads(self, vertices, colors=None, width=None, texture=None, tex_coords=None):
        if not isinstance(vertices, np.ndarray):
            vertices = np.array(vertices)

        if vertices.ndim == 1:
            vertices = np.array((vertices, ))

        first_corners = vertices[0::4]
        second_corners = vertices[1::4]
        third_corners = vertices[2::4]
        fourth_corners = vertices[3::4]
        line_vertices = np.empty([vertices.shape[0]*2, vertices.shape[1]])
        line_vertices[0::8, :] = line_vertices[7::8, :] = first_corners
        line_vertices[1::8, :] = line_vertices[2::8, :] = second_corners
        line_vertices[3::8, :] = line_vertices[4::8, :] = third_corners
        line_vertices[5::8, :] = line_vertices[6::8, :] = fourth_corners

        if texture is None:
            if colors is None:
                colors = np.array((0, 0, 0))
            if not isinstance(colors, np.ndarray):
                colors = np.array(colors)

            if colors.ndim == 2 and len(colors) == len(vertices):
                # one color per vertex, so colors like the vertices
                first_corners = colors[0::4]
                second_corners = colors[1::4]
                third_corners = colors[2::4]
                fourth_corners = colors[3::4]
                line_color_vertices = np.empty([vertices.shape[0]*2, colors.shape[1]])
                line_color_vertices[0::8, :] = line_color_vertices[7::8, :] = first_corners
                line_color_vertices[1::8, :] = line_color_vertices[2::8, :] = second_corners
                line_color_vertices[3::8, :] = line_color_vertices[4::8, :] = third_corners
                line_color_vertices[5::8, :] = line_color_vertices[6::8, :] = fourth_corners
                colors = line_color_vertices
            elif colors.ndim == 2 and len(colors)*4 == len(vertices):
                # one color per quad, so just repeat each color once since we're getting four lines
                colors = colors.repeat(4, 0)
            elif colors.ndim == 1:
                # nothing to do here: just one color for the whole thing
                pass
            else:
                raise WrongNumberOfVerticesException

            self.draw_lines(line_vertices, colors, width=width)
        else:
            if texture not in self.textures.keys():
                return
            if not isinstance(tex_coords, np.ndarray):
                tex_coords = np.array(tex_coords)

            first_corners = tex_coords[0::4]
            second_corners = tex_coords[1::4]
            third_corners = tex_coords[2::4]
            fourth_corners = tex_coords[3::4]
            line_tex_vertices = np.empty([tex_coords.shape[0]*2, tex_coords.shape[1]])
            line_tex_vertices[0::8, :] = line_tex_vertices[7::8, :] = first_corners
            line_tex_vertices[1::8, :] = line_tex_vertices[2::8, :] = second_corners
            line_tex_vertices[3::8, :] = line_tex_vertices[4::8, :] = third_corners
            line_tex_vertices[5::8, :] = line_tex_vertices[6::8, :] = fourth_corners

            self.draw_lines(line_vertices, texture=texture, tex_coords=line_tex_vertices)

    def draw_image(self, location, texture_name, width=None, height=None, center_anchored=False):
        if texture_name not in self.textures.keys():
            return

        if width is None:
            if height is None:
                width = height = 1.0
            else:
                width = height * self.texture_images[texture_name].width() / \
                        self.texture_images[texture_name].height() * self.squash_factor
        else:
            if height is None:
                height = width * self.texture_images[texture_name].height() / \
                         self.texture_images[texture_name].width() / self.squash_factor

        if center_anchored:
            self.fill_quads(((location[0]-width/2, location[1]-height/2), (location[0]-width/2, location[1]+height/2),
                             (location[0]+width/2, location[1]+height/2), (location[0]+width/2, location[1]-height/2)),
                            texture=texture_name, tex_coords=((0, 0), (0, 1),  (1, 1),  (1, 0)))
        else:
            self.fill_quads(((location[0], location[1]), (location[0], location[1]+height),
                             (location[0]+width, location[1]+height), (location[0]+width, location[1])),
                            texture=texture_name, tex_coords=((0, 0), (0, 1),  (1, 1),  (1, 0)))
        # returns size, if useful
        return width, height

    def fill_rects(self, locations, dimensions, colors, center_anchored=False):
        if not isinstance(locations, np.ndarray):
            locations = np.array(locations)
        if not isinstance(dimensions, np.ndarray):
            dimensions = np.array(dimensions)
        if not isinstance(colors, np.ndarray):
            colors = np.array(colors)
        if locations.ndim == 1:
            locations = np.array((locations, ))
        if dimensions.ndim == 1:
            dimensions = np.array((dimensions, ))

        vertices = np.empty((locations.shape[0]*4, 2))
        if center_anchored:
            (vertices[0::4])[:, 0] = locations[:, 0] - dimensions[:, 0]/2
            (vertices[1::4])[:, 0] = locations[:, 0] - dimensions[:, 0]/2
            (vertices[2::4])[:, 0] = locations[:, 0] + dimensions[:, 0]/2
            (vertices[3::4])[:, 0] = locations[:, 0] + dimensions[:, 0]/2
            (vertices[0::4])[:, 1] = locations[:, 1] - dimensions[:, 1]/2
            (vertices[1::4])[:, 1] = locations[:, 1] + dimensions[:, 1]/2
            (vertices[2::4])[:, 1] = locations[:, 1] + dimensions[:, 1]/2
            (vertices[3::4])[:, 1] = locations[:, 1] - dimensions[:, 1]/2
            self.fill_quads(vertices, colors)
        else:
            (vertices[0::4])[:, 0] = locations[:, 0]
            (vertices[1::4])[:, 0] = locations[:, 0]
            (vertices[2::4])[:, 0] = locations[:, 0] + dimensions[:, 0]
            (vertices[3::4])[:, 0] = locations[:, 0] + dimensions[:, 0]
            (vertices[0::4])[:, 1] = locations[:, 1]
            (vertices[1::4])[:, 1] = locations[:, 1] + dimensions[:, 1]
            (vertices[2::4])[:, 1] = locations[:, 1] + dimensions[:, 1]
            (vertices[3::4])[:, 1] = locations[:, 1]
            self.fill_quads(vertices, colors)

    def draw_rects(self, locations, dimensions, colors, width=None, center_anchored=False):
        if not isinstance(locations, np.ndarray):
            locations = np.array(locations)
        if not isinstance(dimensions, np.ndarray):
            dimensions = np.array(dimensions)
        if not isinstance(colors, np.ndarray):
            colors = np.array(colors)
        if locations.ndim == 1:
            locations = np.array((locations, ))
        if dimensions.ndim == 1:
            dimensions = np.array((dimensions, ))

        vertices = np.empty((locations.shape[0]*4, 2))
        if center_anchored:
            (vertices[0::4])[:, 0] = locations[:, 0] - dimensions[:, 0]/2
            (vertices[1::4])[:, 0] = locations[:, 0] - dimensions[:, 0]/2
            (vertices[2::4])[:, 0] = locations[:, 0] + dimensions[:, 0]/2
            (vertices[3::4])[:, 0] = locations[:, 0] + dimensions[:, 0]/2
            (vertices[0::4])[:, 1] = locations[:, 1] - dimensions[:, 1]/2
            (vertices[1::4])[:, 1] = locations[:, 1] + dimensions[:, 1]/2
            (vertices[2::4])[:, 1] = locations[:, 1] + dimensions[:, 1]/2
            (vertices[3::4])[:, 1] = locations[:, 1] - dimensions[:, 1]/2
            self.draw_quads(vertices, colors, width=width)
        else:
            (vertices[0::4])[:, 0] = locations[:, 0]
            (vertices[1::4])[:, 0] = locations[:, 0]
            (vertices[2::4])[:, 0] = locations[:, 0] + dimensions[:, 0]
            (vertices[3::4])[:, 0] = locations[:, 0] + dimensions[:, 0]
            (vertices[0::4])[:, 1] = locations[:, 1]
            (vertices[1::4])[:, 1] = locations[:, 1] + dimensions[:, 1]
            (vertices[2::4])[:, 1] = locations[:, 1] + dimensions[:, 1]
            (vertices[3::4])[:, 1] = locations[:, 1]
            self.draw_quads(vertices, colors, width=width)

    def draw_lines(self, vertices, colors, width=None, corner_type=CornerTypes.NONE):
        if not isinstance(vertices, np.ndarray):
            vertices = np.array(vertices)
        if not isinstance(colors, np.ndarray):
            colors = np.array(colors)

        if vertices.ndim == 1:
            vertices = np.array((vertices, ))

        if width is not None:
            assert vertices.shape[0] % 2 == 0
            assert colors.shape == (3,) or \
                colors.shape == (4,) or \
                (colors.shape[0]*2 == vertices.shape[0] or colors.shape[0] == vertices.shape[0]) and \
                (colors.shape[1] == 3 or colors.shape[1] == 4)

            # if one color for each line, repeat the colors so as to have one for each vertex
            if colors.ndim == 2 and colors.shape[0]*2 == vertices.shape[0]:
                colors = colors.repeat(2, axis=0)

            differences = vertices[1:] - vertices[:-1]
            # checks which differences are zero
            # if between the start and end of a single line, remove that line, since it does nothing
            # if between the end of one and the start of the other, we have to make sure to draw a connection
            diff_zero = (differences == 0).all(axis=1)
            # reshape so that vertex pairs are grouped together
            vertices = vertices.reshape([vertices.shape[0]/2, 2, 2])
            # any even numbered diff_zero is a line that starts and ends at the same point, so we remove it
            vertices_to_keep = np.where(~diff_zero[0::2])
            vertices = vertices[vertices_to_keep]

            # if we're removing any vertices, we need to remove the corresponding colors
            if colors.ndim == 2:
                colors = colors.reshape([colors.shape[0]/2, 2, colors.shape[1]])
                colors = colors[vertices_to_keep]
                colors = colors.reshape([colors.shape[0]*2, colors.shape[2]])

            differences = (differences[0::2])[vertices_to_keep]
            unit_differences = differences / np.hypot(differences[:, 0], differences[:, 1])[:, None]
            unit_perps = np.column_stack((unit_differences[:, 1], -unit_differences[:, 0]))

            vertices = vertices.reshape([vertices.shape[0]*2, 2])
            quad_vertices = np.empty((vertices.shape[0]*2, vertices.shape[1]))
            quad_vertices[::4] = vertices[::2] + (unit_perps[:] * width/2)
            quad_vertices[1::4] = vertices[::2] - (unit_perps[:] * width/2)
            quad_vertices[2::4] = vertices[1::2] - (unit_perps[:] * width/2)
            quad_vertices[3::4] = vertices[1::2] + (unit_perps[:] * width/2)

            # since we're drawing quads, we have to double the number of color vertices
            if colors.ndim == 2:
                quad_colors = colors.repeat(2, axis=0)
            else:
                quad_colors = colors

            if corner_type == CornerTypes.ROUNDED:
                self.shapes.append(DepthTestSwitch(True))
                self.fill_quads(quad_vertices, quad_colors)
                self.fill_arcs(vertices, np.full(vertices.shape[0], width/2), colors)
                self.shapes.append(DepthTestSwitch(False))
            else:
                self.fill_quads(quad_vertices, quad_colors)
        else:
            self.shapes.append(Lines(vertices, colors))

    def fill_polygons(self, vertices, colors, start_indices=None):
        if not isinstance(vertices, np.ndarray):
            vertices = np.array(vertices)
        if not isinstance(colors, np.ndarray):
            colors = np.array(colors)
        assert vertices.ndim == 2 and vertices.shape[1] == 2

        self.shapes.append(Polygons(vertices, colors, start_indices))

    def draw_line_strip(self, vertices, colors, width=None, corner_type=CornerTypes.ROUNDED, double_back=True):
        if not isinstance(vertices, np.ndarray):
            vertices = np.array(vertices)
        if not isinstance(colors, np.ndarray):
            colors = np.array(colors)

        assert colors.shape == (3,) or \
            colors.shape == (4,) or \
            colors.shape[0] == vertices.shape[0] and \
            colors.shape[1] == 3 or colors.shape[1] == 4

        if width is not None:
            if corner_type == CornerTypes.FLAT_BRUSH:
                # find differences between vertices
                differences = vertices[1:] - vertices[:-1]
                # which are zero?
                diff_zero = (differences == 0).all(axis=1)
                # vertices that are the same as the previous are removed
                # need to add a False at the beginning, since the first vertex is obviously not the same as its predecessor
                vertices_to_keep = np.where(~np.roll(np.append(diff_zero, False), 1))
                vertices = vertices[vertices_to_keep]
                if vertices.shape[0] < 2:
                    # need at least two points to make a line strip
                    return
                differences = differences[~diff_zero]
                if colors.ndim == 2:
                    colors = colors[vertices_to_keep]

                unit_differences = differences / np.hypot(differences[:, 0], differences[:, 1])[:, None]
                unit_perps = np.column_stack((unit_differences[:, 1], -unit_differences[:, 0]))

                # if the direction vectors are farther than 90 degrees apart (equivalent to being more than root 2
                # apart in terms of distance), then there is an orientation change to account for
                direction_difference = unit_differences[:-1] - unit_differences[1:]
                more_than_90 = np.hypot(direction_difference[:, 0], direction_difference[:, 1]) > 1.41421356237

                average_directions = np.empty((vertices.shape[0] - 2, vertices.shape[1]))
                if double_back:
                    orientation_changes = np.where(more_than_90)
                    no_orientation_changes = np.where(~more_than_90)
                    average_directions[no_orientation_changes] = ((unit_differences[:-1])[no_orientation_changes] +
                                                               (unit_differences[1:])[no_orientation_changes]) / 2
                    average_directions[orientation_changes] = (-(unit_differences[:-1])[orientation_changes] +
                                                               (unit_differences[1:])[orientation_changes]) / 2
                else:
                    average_directions = (unit_differences[:-1] + unit_differences[1:]) / 2

                average_directions /= np.hypot(average_directions[:, 0], average_directions[:, 1])[:, None]
                average_perps = np.column_stack((average_directions[:, 1], -average_directions[:, 0]))

                perps_to_use = np.empty((vertices.shape[0], vertices.shape[1]))
                perps_to_use[0] = unit_perps[0]
                perps_to_use[1:-1] = average_perps
                perps_to_use[-1] = unit_perps[-1]

                # adjust width to compensate for sharper angles

                tri_strip_vertices = np.empty((vertices.shape[0]*2, vertices.shape[1]))
                tri_strip_vertices[0::2] = vertices - perps_to_use * width/2
                tri_strip_vertices[1::2] = vertices + perps_to_use * width/2

                # orientation changes flip the order of vertices until the next orientation change
                if double_back:
                    more_than_90 = np.concatenate((more_than_90, (False, )))
                    to_flip = np.where(np.cumsum(more_than_90) % 2)
                    temp = np.copy((tri_strip_vertices[2::2])[to_flip])
                    (tri_strip_vertices[2::2])[to_flip] = (tri_strip_vertices[3::2])[to_flip]
                    (tri_strip_vertices[3::2])[to_flip] = temp

                if colors.ndim == 2:
                    tri_strip_colors = np.repeat(colors, 2, axis=0)
                    self.shapes.append(TriangleStrip(tri_strip_vertices, tri_strip_colors))
                else:
                    self.shapes.append(TriangleStrip(tri_strip_vertices, colors))
            elif corner_type == CornerTypes.ROUNDED:
                new_vertices = np.empty(((vertices.shape[0]-1)*2, vertices.shape[1]))
                new_vertices[0::2] = vertices[:-1]
                new_vertices[1::2] = vertices[1:]
                if colors.ndim == 2:
                    new_colors = np.empty(((colors.shape[0]-1)*2, colors.shape[1]))
                    new_colors[0::2] = new_colors[:-1]
                    new_colors[1::2] = new_colors[1:]
                    self.draw_lines(new_vertices, new_colors, width=width, corner_type=corner_type)
                else:
                    self.draw_lines(new_vertices, colors, width=width, corner_type=corner_type)
        else:
            self.shapes.append(LineStrip(vertices, colors))

    def draw_text(self, text, (x, y), size, color, font_name, styles="", anchor_type=None):
        if anchor_type is None:
            self.shapes.append(TextShape(text, (x, y), size, font_name, color, self, styles=styles))
        else:
            self.shapes.append(TextShape(text, (x, y), size, font_name, color, self, styles=styles, anchor_type=anchor_type))

    def fill_arcs(self, centers, radii, colors, angle_ranges=(0, 2*math.pi), num_segments=100):
        # takes a numpy N x 2 numpy array of center locations
        # a N length or N x 2 array of radii ( N x 2 allows for ellipses )
        # a single color, an N x (3 or 4) array of colors for each arc separately,
        #  or a 2*N x (3 or 4) array of inner and outer colors for each arc
        # and either a single angle range (default 0 -> 2*pi draws full circles) or a separate
        # angle range for each arc.
        if not isinstance(centers, np.ndarray):
            centers = np.array(centers)
        if not isinstance(radii, np.ndarray):
            radii = np.array(radii)
        if not isinstance(colors, np.ndarray):
            colors = np.array(colors)
        if not isinstance(angle_ranges, np.ndarray):
            angle_ranges = np.array(angle_ranges)

        assert num_segments >= 2

        if centers.ndim == 1:
            assert centers.shape[0] == 2
            centers = np.array([centers])
        else:
            assert centers.ndim == 2 and centers.shape[1] == 2

        assert radii.shape[0] == centers.shape[0]
        assert angle_ranges.shape == (2,) or centers.shape[0] == angle_ranges.shape[0] and angle_ranges.shape[1] == 2
        # either one color for all arcs, one color per arc
        # or 2 colors for all arcs (center color, edge color)
        assert colors.shape == (3,) or \
            colors.shape == (4,) or \
            colors.ndim == 2 and (colors.shape[1] == 3 or colors.shape[1] == 4) and \
            (colors.shape[0] == centers.shape[0]*2 or
             colors.shape[0] == centers.shape[0])

        # start with all the edges at the centers of each arc
        edges = centers.repeat(num_segments + 1, axis=0)

        # then calculate the displacements from the centers for each edge point
        if angle_ranges.ndim == 1:
            angles = np.linspace(angle_ranges[0], angle_ranges[1], num_segments+1)
            displacements = np.tile(np.column_stack((np.cos(angles), np.sin(angles))), (centers.shape[0], 1))
        else:
            zero_to_one_ramps = np.tile(np.linspace(0, 1, num_segments+1), centers.shape[0])
            ranges_repeated = angle_ranges.repeat(num_segments+1, axis=0)
            angles = ranges_repeated[:, 0] * (1-zero_to_one_ramps) + ranges_repeated[:, 1] * zero_to_one_ramps
            displacements = np.column_stack((np.cos(angles), np.sin(angles)))

        if radii.ndim == 2:
            edges += radii.repeat(num_segments+1, axis=0)*displacements
        else:
            edges += radii.repeat(num_segments+1, axis=0)[:, np.newaxis]*displacements

        # finally, insert the centers
        insert_locations = np.arange(0, edges.shape[0], num_segments+1)

        vertices = np.insert(edges, insert_locations, centers, axis=0)
        if centers.shape[0] == 1:
            start_indices = None
        else:
            start_indices = np.arange(0, vertices.shape[0], num_segments+2)

        if colors.ndim == 2:
            if colors.shape[0] == centers.shape[0]:
                new_colors = colors.repeat(num_segments + 2, axis=0)
            elif colors.shape[0] == centers.shape[0]*2:
                # all but the starting center colors will be the edge colors
                new_colors = colors[1::2].repeat(num_segments + 2, axis=0)
                # the the first color of each circle, however, will be the center color
                new_colors[0::num_segments + 2] = colors[0::2]
            self.shapes.append(TriangleFans(vertices, new_colors, start_indices))
        else:
            self.shapes.append(TriangleFans(vertices, colors, start_indices))

    def fill_rings(self, centers, inner_radii, outer_radii, colors, angle_ranges=(0, 2*math.pi), num_segments=100):
        # takes a numpy N x 2 numpy array of center locations
        # a N length or N x 2 array of radii ( N x 2 allows for ellipses )
        # a single color, an N x (3 or 4) array of colors for each arc separately,
        #  or a 2*N x (3 or 4) array of inner and outer colors for each arc
        # and either a single angle range (default 0 -> 2*pi draws full circles) or a separate
        # angle range for each arc.
        if not isinstance(centers, np.ndarray):
            centers = np.array(centers)
        if not isinstance(inner_radii, np.ndarray):
            inner_radii = np.array(inner_radii)
        if not isinstance(outer_radii, np.ndarray):
            outer_radii = np.array(outer_radii)
        if not isinstance(colors, np.ndarray):
            colors = np.array(colors)
        if not isinstance(angle_ranges, np.ndarray):
            angle_ranges = np.array(angle_ranges)

        if centers.ndim == 1:
            assert centers.shape[0] == 2
            centers = np.array([centers])
        else:
            assert centers.ndim == 2 and centers.shape[1] == 2

        assert num_segments >= 2

        if outer_radii.shape[0] == 1:
            outer_radii = outer_radii.repeat(centers.shape[0])

        if inner_radii.shape[0] == 1:
            inner_radii = inner_radii.repeat(centers.shape[0])

        assert outer_radii.shape[0] == centers.shape[0]
        assert inner_radii.shape[0] == centers.shape[0]

        assert angle_ranges.shape == (2,) or centers.shape[0] == angle_ranges.shape[0] and angle_ranges.shape[1] == 2
        # either one color for all arcs, one color per arc
        # or 2 colors for all arcs (center color, edge color)
        assert colors.shape == (3,) or \
            colors.shape == (4,) or \
            colors.ndim == 2 and (colors.shape[1] == 3 or colors.shape[1] == 4) and \
            (colors.shape[0] == centers.shape[0]*2 or
             colors.shape[0] == centers.shape[0])

        # inner edges go |_|__|__|__|__|
        # outer edges go |__|__|__|__|_|
        # we alternate in-out-in-out
        # so six segments divides it into (6-1)*2+1 = 11 pieces
        num_piece_subdivisions = (num_segments-1)*2 + 1

        # start with all the edges at the centers of each arc
        vertices = centers.repeat((num_segments+1)*2, axis=0)

        # then calculate the displacements from the centers for each edge point
        if angle_ranges.ndim == 1:
            angles = np.linspace(angle_ranges[0], angle_ranges[1], num_piece_subdivisions+1)
            angles = np.insert(angles, [0, angles.shape[0]], [angles[0], angles[angles.shape[0]-1]], axis=0)
            displacements = np.tile(np.column_stack((np.cos(angles), np.sin(angles))), (centers.shape[0], 1))
        else:
            zero_to_one_ramps = np.tile(np.linspace(0, 1, num_piece_subdivisions+1), centers.shape[0])
            ranges_repeated = angle_ranges.repeat(num_piece_subdivisions+1, axis=0)
            angles = ranges_repeated[:, 0] * (1-zero_to_one_ramps) + ranges_repeated[:, 1] * zero_to_one_ramps
            # we need to repeat the start and end angles, since both inner and outer edges use both
            start_angles = np.arange(0, centers.shape[0])*(num_piece_subdivisions+1)
            end_angles = start_angles + num_piece_subdivisions
            to_repeat = np.concatenate([start_angles, end_angles])
            angles =  np.insert(angles, to_repeat, angles[to_repeat])
            displacements = np.column_stack((np.cos(angles), np.sin(angles)))

        if inner_radii.ndim == 2:
            vertices[0::2] += inner_radii.repeat(num_segments+1, axis=0)*displacements[0::2]
        else:
            vertices[0::2] += inner_radii.repeat(num_segments+1, axis=0)[:, np.newaxis]*displacements[0::2]

        if outer_radii.ndim == 2:
            vertices[1::2] += outer_radii.repeat(num_segments+1, axis=0)*displacements[1::2]
        else:
            vertices[1::2] += outer_radii.repeat(num_segments+1, axis=0)[:, np.newaxis]*displacements[1::2]

        if centers.shape[0] == 1:
            start_indices = None
        else:
            start_indices = np.arange(0, vertices.shape[0], (num_segments+1)*2)

        # self.shapes.append(TriangleStrip(vertices, np.array([0, 0, 0]), start_indices))


        if colors.ndim == 2:
            if colors.shape[0] == centers.shape[0]:
                new_colors = colors.repeat((num_segments+1)*2, axis=0)
            elif colors.shape[0] == centers.shape[0]*2:
                inner_colors = colors[0::2]
                outer_colors = colors[1::2]
                inner_colors = inner_colors.repeat(num_segments+1, axis=0)
                outer_colors = outer_colors.repeat(num_segments+1, axis=0)
                new_colors = np.empty([vertices.shape[0], colors.shape[1]])
                new_colors[0::2] = inner_colors
                new_colors[1::2] = outer_colors

            self.shapes.append(TriangleStrip(vertices, new_colors, start_indices))
        else:
            self.shapes.append(TriangleStrip(vertices, colors, start_indices))

    # THESE ARE THE METHODS TO OVERWRITE

    def on_load(self):
        pass

    def on_mouse_down(self, (x, y), buttons_and_modifiers):
        # print "mouse down", x, y, buttons
        pass

    def on_mouse_up(self, (x, y), buttons_and_modifiers):
        # print "mouse up", x, y, buttons
        pass

    def on_mouse_click(self, (x, y), buttons_and_modifiers, click_count):
        # print "mouse click", x, y, buttons, click_count
        pass

    def on_mouse_move(self, (x, y)):
        # print "mouse move", x, y
        pass

    def on_mouse_drag(self, (x, y), buttons):
        # print "mouse drag", x, y, buttons
        pass

    def on_mouse_scroll(self, delta_x, delta_y):
        pass

    def on_key_press(self, key, modifiers):
        # print "key pressed", key, modifiers
        pass

    def on_key_release(self, key, modifiers):
        pass

    def animate(self, dt):
        pass


def get_screen_width():
    return QtWidgets.QDesktopWidget().availableGeometry().width()


def get_screen_height():
    return QtWidgets.QDesktopWidget().availableGeometry().height()


class WrongNumberOfVerticesException(Exception):
    pass


######### SHAPES ########
class TextShape:
    def __init__(self, text, (x, y), size, font_name, color, host_widget, styles="",
                anchor_type=TextAnchorType.ANCHOR_CORNER):
        # size either refers to the point size (relative to the view height)
        # or to the max width and max height in view coordinates
        assert isinstance(host_widget, MarcPaintWidget)
        self.text = text
        self.font_name = font_name
        self.color = color
        self.size = size
        self.view_x, self.view_y = x, y
        self.host_widget = host_widget
        self.anchor_type = anchor_type

        # These two attributes need to be recalculated at every draw
        self.position = None
        self.font = None
        self.styles = styles.lower()

        if len(self.color) == 4:
            self.includes_alpha = True
        else:
            self.includes_alpha = False

        self.set_font_and_position()

    def set_font_and_position(self):
        if isinstance(self.size, tuple):
            self.font = QtGui.QFont(self.font_name, self.size[1]/self.host_widget.get_view_height()*self.host_widget.height())
            if "italic" in self.styles:
                self.font.setItalic(True)
            if "bold" in self.styles:
                self.font.setBold(True)

            font_met = QtGui.QFontMetrics(self.font)
            test_width = float(font_met.width(self.text))*self.host_widget.get_view_width()/self.host_widget.width()
            test_height = float(font_met.height())*self.host_widget.get_view_height()/self.host_widget.height()

            # make it as big as possible without exceeding the box
            resize_ratio = max(test_width / self.size[0], test_height / self.size[1])
            self.font.setPointSize(self.size[1]/self.host_widget.get_view_height()*self.host_widget.height()/resize_ratio)
            font_met = QtGui.QFontMetrics(self.font)
            width = float(font_met.width(self.text))/self.host_widget.width()*self.host_widget.get_view_width()
            ascent = float(font_met.ascent())/self.host_widget.height()*self.host_widget.get_view_height()
            height = float(font_met.height())/self.host_widget.height()*self.host_widget.get_view_height()
            descent = float(font_met.descent())/self.host_widget.height()
            if 'q' in self.text or 'y' in self.text or 'p' in self.text or 'g' in self.text or 'j' in self.text:
                vertical_boost = max(self.size[1]/2 - ascent/2, descent)
            else:
                vertical_boost = ascent/2

            if self.anchor_type == TextAnchorType.ANCHOR_CORNER:
                self.position = ((self.view_x - self.host_widget.view_bounds[0] + self.size[0]/2- width/2) /
                                 self.host_widget.get_view_width()*self.host_widget.width(),
                                 (1 - (self.view_y - self.host_widget.view_bounds[2] + vertical_boost) /
                                  self.host_widget.get_view_height())*self.host_widget.height())
            else:
                centered_view_x, centered_view_y = self.view_x - self.size[0]/2, self.view_y - height/2 + descent
                self.position = ((centered_view_x - self.host_widget.view_bounds[0] + self.size[0]/2- width/2) /
                                 self.host_widget.get_view_width()*self.host_widget.width(),
                                 (1 - (centered_view_y - self.host_widget.view_bounds[2]) /
                                  self.host_widget.get_view_height())*self.host_widget.height())
        else:
            # font-size in points (relative to view height)
            self.font = QtGui.QFont(self.font_name, self.size/self.host_widget.get_view_height()*self.host_widget.height())
            if "italic" in self.styles:
                self.font.setItalic(True)
            if "bold" in self.styles:
                self.font.setBold(True)

            if self.anchor_type == TextAnchorType.ANCHOR_CORNER:
                self.position = ((self.view_x-self.host_widget.view_bounds[0])/self.host_widget.get_view_width()*self.host_widget.width(),
                                 (1-(self.view_y-self.host_widget.view_bounds[2])/self.host_widget.get_view_height())*self.host_widget.height())
            else:
                # anchor center
                font_met = QtGui.QFontMetrics(self.font)
                width = float(font_met.width(self.text))
                ascent = float(font_met.ascent())
                self.position = ((self.view_x-self.host_widget.view_bounds[0])/self.host_widget.get_view_width()*self.host_widget.width() - width/2,
                                 (1-(self.view_y-self.host_widget.view_bounds[2])/self.host_widget.get_view_height())*self.host_widget.height() + ascent/2)

class Triangles:
    def __init__(self, vertices, colors=None, texture=None, tex_coords=None, texture_dict=None):
        """

        :param vertices: a 2D numpy array of shape [N, 2], where N is a multiple of 3
        :param colors: a 2D numpy array of shape [N, 3] or [N, 4]
        """
        if texture is None and colors is None:
            colors = np.array((0, 0, 0))

        if texture is not None:
            assert tex_coords is not None and tex_coords.shape == vertices.shape

        if colors is not None:
            assert isinstance(colors, np.ndarray)
            assert colors.shape == (3,) or \
                colors.shape == (4,) or \
                (colors.shape[0]*3 == vertices.shape[0] or colors.shape[0] == vertices.shape[0]) and \
                (colors.shape[1] == 3 or colors.shape[1] == 4)
            if colors.shape == (3,):
                # three color components per vertex: no alpha values
                self.includes_alpha = False
            elif colors.shape == (4,):
                # four color components per vertex: alpha values included
                self.includes_alpha = True
            elif colors.shape[1] == 3:
                # three color components per vertex: no alpha values
                self.includes_alpha = False
            elif colors.shape[1] == 4:
                # four color components per vertex: alpha values included
                self.includes_alpha = True

            if colors.ndim == 2 and colors.shape[0]*3 == vertices.shape[0]:
                # one color per triangle; we need to triplicate the vertices
                colors = np.column_stack((colors, colors, colors)).reshape([colors.shape[0]*3, colors.shape[1]])
        elif texture is not None:
            # this is important: if we're using a texture with no color info, we need to make sure the color is
            # changed to black or it might just have a weird color left over
            colors = np.array((0, 0, 0))

        assert isinstance(vertices, np.ndarray)
        assert vertices.shape[0] % 3 == 0 and vertices.shape[1] == 2

        self.vertices = vertices
        self.colors = colors
        self.texture = texture
        self.texture_dict = texture_dict
        self.tex_coords = tex_coords

    def do_set_up(self):
        if self.colors is not None:
            if self.colors.shape == (4,):
                glColor4f(*self.colors)
            elif self.colors.shape == (3,):
                glColor3f(*self.colors)

    def do_paint_calls(self):
        glEnableClientState(GL_VERTEX_ARRAY)
        if self.texture is not None:
            tex = self.texture_dict[self.texture]
            glEnable(GL_TEXTURE_2D);
            glEnableClientState(GL_TEXTURE_COORD_ARRAY)
            glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_ADD)

        glVertexPointer(2, GL_FLOAT, 0, self.vertices)

        if self.texture is not None:
            tex.bind()
            glTexCoordPointer(2, GL_FLOAT, 0, self.tex_coords)

        if self.colors is not None and self.colors.ndim > 1:
            glEnableClientState(GL_COLOR_ARRAY)
            if self.includes_alpha:
                glColorPointer(4, GL_FLOAT, 0, self.colors)
            else:
                glColorPointer(3, GL_FLOAT, 0, self.colors)

        glDrawArrays(GL_TRIANGLES, 0, len(self.vertices))
        glFlush()
        glDisableClientState(GL_VERTEX_ARRAY)

        if self.colors is not None and self.colors.ndim > 1:
            glDisableClientState(GL_COLOR_ARRAY)
        if self.texture is not None:
            glDisableClientState(GL_TEXTURE_COORD_ARRAY)
            tex.release()

    def do_clean_up(self):
        pass

class DepthTestSwitch:
    def __init__(self, on_or_off, includes_alpha=True):
        self.includes_alpha = includes_alpha
        self.on_or_off = on_or_off

    def do_set_up(self):
        if self.on_or_off:
            glEnable(GL_DEPTH_TEST)
            glClear(GL_DEPTH_BUFFER_BIT)
        else:
            glDisable(GL_DEPTH_TEST)

    def do_paint_calls(self):
        pass

    def do_clean_up(self):
        pass

class Lines:
    def __init__(self, vertices, colors, line_width=1):
        assert isinstance(vertices, np.ndarray)
        assert isinstance(colors, np.ndarray)
        assert vertices.shape[0] % 2 == 0 and vertices.shape[1] == 2
        assert colors.shape == (3,) or \
            colors.shape == (4,) or \
            (colors.shape[0]*2 == vertices.shape[0] or colors.shape[0] == vertices.shape[0]) and \
            (colors.shape[1] == 3 or colors.shape[1] == 4)

        if colors.shape == (3,):
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape == (4,):
            # four color components per vertex: alpha values included
            self.includes_alpha = True
        elif colors.shape[1] == 3:
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape[1] == 4:
            # four color components per vertex: alpha values included
            self.includes_alpha = True

        if colors.ndim == 2 and colors.shape[0]*2 == vertices.shape[0]:
            # one color per line; we need to duplicate the vertices
            colors = np.column_stack((colors, colors)).reshape([colors.shape[0]*2, colors.shape[1]])

        self.vertices = vertices
        self.colors = colors
        self.line_width = line_width

    def do_set_up(self):
        glLineWidth(self.line_width)
        if self.includes_alpha and len(self.colors) == 4:
            glColor4f(*self.colors)
        elif len(self.colors) == 3:
            glColor3f(*self.colors)

    def do_paint_calls(self):
        if (self.includes_alpha and len(self.colors) == 4) or len(self.colors) == 3:
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)
            glDrawArrays(GL_LINES, 0, len(self.vertices))
            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
        else:
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)
            if self.includes_alpha:
                glColorPointer(4, GL_FLOAT, 0, self.colors)
            else:
                glColorPointer(3, GL_FLOAT, 0, self.colors)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)
            glDrawArrays(GL_LINES, 0, len(self.vertices))
            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_COLOR_ARRAY)

    def do_clean_up(self):
        glLineWidth(1)

class Polygons:
    def __init__(self, vertices, colors, starting_indices=None):
        assert isinstance(vertices, np.ndarray)
        assert isinstance(colors, np.ndarray)
        assert starting_indices is None or isinstance(starting_indices, np.ndarray)
        assert vertices.shape[1] == 2
        assert colors.shape == (3,) or \
            colors.shape == (4,) or \
            colors.shape[0] == vertices.shape[0] and \
            (colors.shape[1] == 3 or colors.shape[1] == 4)

        if colors.shape == (3,):
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape == (4,):
            # four color components per vertex: alpha values included
            self.includes_alpha = True
        elif colors.shape[1] == 3:
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape[1] == 4:
            # four color components per vertex: alpha values included
            self.includes_alpha = True

        self.vertices = vertices
        self.colors = colors
        self.starting_indices = starting_indices

    def do_set_up(self):
        if self.includes_alpha and len(self.colors) == 4:
            glColor4f(*self.colors)
        elif len(self.colors) == 3:
            glColor3f(*self.colors)

    def do_paint_calls(self):
        if (self.includes_alpha and len(self.colors) == 4) or len(self.colors) == 3:
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)

            if self.starting_indices is not None:
                counts = (np.roll(self.starting_indices, -1) - self.starting_indices)
                # this assumes we start with vertex zero!
                counts[-1] += len(self.vertices)
                glMultiDrawArrays(GL_LINE_LOOP, self.starting_indices, counts, len(self.starting_indices))
            else:
                glDrawArrays(GL_LINE_LOOP, 0, len(self.vertices))

            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
        else:
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)
            if self.includes_alpha:
                glColorPointer(4, GL_FLOAT, 0, self.colors)
            else:
                glColorPointer(3, GL_FLOAT, 0, self.colors)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)

            if self.starting_indices is not None:
                counts = (np.roll(self.starting_indices, -1) - self.starting_indices)
                # this assumes we start with vertex zero!
                counts[-1] += len(self.vertices)
                glMultiDrawArrays(GL_LINE_LOOP, self.starting_indices, counts, len(self.starting_indices))
            else:
                glDrawArrays(GL_LINE_LOOP, 0, len(self.vertices))

            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_COLOR_ARRAY)

    def do_clean_up(self):
        pass


class TriangleStrip:
    def __init__(self, vertices, colors, starting_indices=None):
        """

        :param vertices: a 2D numpy array of shape [N, 2]
        :param colors: a 2D numpy array of shape [N, 3] or [N, 4]
        """
        assert isinstance(vertices, np.ndarray)
        assert isinstance(colors, np.ndarray)
        assert starting_indices is None or isinstance(starting_indices, np.ndarray)
        assert vertices.shape[1] == 2
        assert colors.shape == (3,) or \
            colors.shape == (4,) or \
            colors.shape[0] == vertices.shape[0] and \
            (colors.shape[1] == 3 or colors.shape[1] == 4)

        if colors.shape == (3,):
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape == (4,):
            # four color components per vertex: alpha values included
            self.includes_alpha = True
        elif colors.shape[1] == 3:
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape[1] == 4:
            # four color components per vertex: alpha values included
            self.includes_alpha = True

        self.vertices = vertices
        self.colors = colors
        self.starting_indices = starting_indices

    def do_set_up(self):
        if self.colors.shape == (4,):
            glColor4f(*self.colors)
        elif self.colors.shape == (3,):
            glColor3f(*self.colors)

    def do_paint_calls(self):
        if self.colors.shape == (4,) or self.colors.shape == (3,):
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)
            if self.starting_indices is not None:
                counts = (np.roll(self.starting_indices, -1) - self.starting_indices)
                # this assumes we start with vertex zero!
                counts[-1] += len(self.vertices)
                glMultiDrawArrays(GL_TRIANGLE_STRIP, self.starting_indices, counts, len(self.starting_indices))
            else:
                glDrawArrays(GL_TRIANGLE_STRIP, 0, len(self.vertices))
            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
        else:
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)
            if self.includes_alpha:
                glColorPointer(4, GL_FLOAT, 0, self.colors)
            else:
                glColorPointer(3, GL_FLOAT, 0, self.colors)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)

            if self.starting_indices is not None:
                counts = (np.roll(self.starting_indices, -1) - self.starting_indices)
                # this assumes we start with vertex zero!
                counts[-1] += len(self.vertices)
                glMultiDrawArrays(GL_TRIANGLE_STRIP, self.starting_indices, counts, len(self.starting_indices))
            else:
                glDrawArrays(GL_TRIANGLE_STRIP, 0, len(self.vertices))

            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_COLOR_ARRAY)

    def do_clean_up(self):
        pass


class TriangleFans:
    def __init__(self, vertices, colors, starting_indices=None):
        assert isinstance(vertices, np.ndarray)
        assert isinstance(colors, np.ndarray)
        assert starting_indices is None or isinstance(starting_indices, np.ndarray)
        assert vertices.shape[1] == 2
        assert colors.shape == (3,) or \
            colors.shape == (4,) or \
            colors.shape[0] == vertices.shape[0] and \
            (colors.shape[1] == 3 or colors.shape[1] == 4)

        if colors.shape == (3,):
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape == (4,):
            # four color components per vertex: alpha values included
            self.includes_alpha = True
        elif colors.shape[1] == 3:
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape[1] == 4:
            # four color components per vertex: alpha values included
            self.includes_alpha = True

        self.vertices = vertices
        self.colors = colors
        self.starting_indices = starting_indices

    def do_set_up(self):
        if self.includes_alpha and len(self.colors) == 4:
            glColor4f(*self.colors)
        elif len(self.colors) == 3:
            glColor3f(*self.colors)

    def do_paint_calls(self):
        if (self.includes_alpha and len(self.colors) == 4) or len(self.colors) == 3:
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)

            if self.starting_indices is not None:
                counts = (np.roll(self.starting_indices, -1) - self.starting_indices)
                # this assumes we start with vertex zero!
                counts[-1] += len(self.vertices)
                glMultiDrawArrays(GL_TRIANGLE_FAN, self.starting_indices, counts, len(self.starting_indices))
            else:
                glDrawArrays(GL_TRIANGLE_FAN, 0, len(self.vertices))

            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
        else:
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)
            if self.includes_alpha:
                glColorPointer(4, GL_FLOAT, 0, self.colors)
            else:
                glColorPointer(3, GL_FLOAT, 0, self.colors)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)

            if self.starting_indices is not None:
                counts = (np.roll(self.starting_indices, -1) - self.starting_indices)
                # this assumes we start with vertex zero!
                counts[-1] += len(self.vertices)
                glMultiDrawArrays(GL_TRIANGLE_FAN, self.starting_indices, counts, len(self.starting_indices))
            else:
                glDrawArrays(GL_TRIANGLE_FAN, 0, len(self.vertices))

            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_COLOR_ARRAY)

    def do_clean_up(self):
        pass

class LineStrip:
    def __init__(self, vertices, colors, line_width=1):
        assert isinstance(vertices, np.ndarray)
        assert isinstance(colors, np.ndarray)
        assert vertices.shape[1] == 2
        assert colors.shape == (3,) or \
            colors.shape == (4,) or \
            colors.shape[0] == vertices.shape[0] and \
            (colors.shape[1] == 3 or colors.shape[1] == 4)

        if colors.shape == (3,):
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape == (4,):
            # four color components per vertex: alpha values included
            self.includes_alpha = True
        elif colors.shape[1] == 3:
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape[1] == 4:
            # four color components per vertex: alpha values included
            self.includes_alpha = True

        self.vertices = vertices
        self.colors = colors
        self.line_width = line_width

    def do_set_up(self):
        glLineWidth(self.line_width)
        if self.includes_alpha and len(self.colors) == 4:
            glColor4f(*self.colors)
        elif len(self.colors) == 3:
            glColor3f(*self.colors)

    def do_paint_calls(self):
        if (self.includes_alpha and len(self.colors) == 4) or len(self.colors) == 3:
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)
            glDrawArrays(GL_LINE_STRIP, 0, len(self.vertices))
            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
        else:
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)
            if self.includes_alpha:
                glColorPointer(4, GL_FLOAT, 0, self.colors)
            else:
                glColorPointer(3, GL_FLOAT, 0, self.colors)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)
            glDrawArrays(GL_LINE_STRIP, 0, len(self.vertices))
            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_COLOR_ARRAY)

    def do_clean_up(self):
        glLineWidth(1)

class Points:
    def __init__(self, vertices, colors):
        assert isinstance(vertices, np.ndarray)
        assert isinstance(colors, np.ndarray)
        assert vertices.shape[1] == 2
        assert colors.shape == (3,) or \
            colors.shape == (4,) or \
            colors.shape[0] == vertices.shape[0] and \
            (colors.shape[1] == 3 or colors.shape[1] == 4)

        if colors.shape == (3,):
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape == (4,):
            # four color components per vertex: alpha values included
            self.includes_alpha = True
        elif colors.shape[1] == 3:
            # three color components per vertex: no alpha values
            self.includes_alpha = False
        elif colors.shape[1] == 4:
            # four color components per vertex: alpha values included
            self.includes_alpha = True
        self.vertices = vertices
        self.colors = colors

    def do_set_up(self):
        if self.includes_alpha and len(self.colors) == 4:
            glColor4f(*self.colors)
        elif len(self.colors) == 3:
            glColor3f(*self.colors)

    def do_paint_calls(self):
        if (self.includes_alpha and len(self.colors) == 4) or len(self.colors) == 3:
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)
            glDrawArrays(GL_POINTS, 0, len(self.vertices))
            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
        else:
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)
            if self.includes_alpha:
                glColorPointer(4, GL_FLOAT, 0, self.colors)
            else:
                glColorPointer(3, GL_FLOAT, 0, self.colors)
            glVertexPointer(2, GL_FLOAT, 0, self.vertices)
            glDrawArrays(GL_POINTS, 0, len(self.vertices))
            glFlush()
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_COLOR_ARRAY)

    def do_clean_up(self):
        pass