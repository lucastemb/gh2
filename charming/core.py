import sys
import math
import colorsys
import string
from abc import ABCMeta, abstractclassmethod
from pyfiglet import Figlet
from . import constants

from .globals import WINDOWS
from .globals import BROWSER
from .globals import POSIX

from .utils import map
from .utils import dist
from .utils import Matrix
from .utils import angle_between
from .utils import get_char_width
from .utils import to_left
from .utils import generate_xtermjs_colors
from .utils import logger


class Sketch(object):

    def __init__(self, renderer, context, image_loader, timer):
        self.renderer = renderer
        self.context = context
        self.image_loader = image_loader
        self.timer = timer

        self.frame_rate = 30
        self.is_loop = True
        self.frame_count = 0
        self.key = 0
        self.key_code = 0
        self.mouse_x = 0
        self.mouse_y = 0
        self.pmouse_x = 0
        self.pmouse_y = 0
        self.mouse_button = 0
        self.has_setup_hook = False
        self.has_draw_hook = False
        self.hooks_map = {
            'setup': lambda: None,
            'draw': lambda: None,
            'mouse_clicked': lambda: None,
            'mouse_pressed': lambda: None,
            'mouse_released': lambda: None,
            'mouse_moved': lambda: None,
            'mouse_dragged': lambda: None,
            'mouse_wheel': lambda: None,
            'key_typed': lambda: None,
            'key_pressed': lambda: None,
            'key_released': lambda: None,
            'window_resized': lambda: None,
        }

    def run(self):
        try:
            self._setup()
            self._loop()
            if self.has_draw_hook and self.has_setup_hook:
                self.timer.run(1000 / self.frame_rate, self._loop)
            else:
                self.timer.wait()
        except Exception as e:
            logger.debug(e)
            raise e
        finally:
            self.context.close()
            logger.log_record()

    @logger.record('setup')
    def _setup(self):
        if self.has_setup_hook:
            setup_hook = self.hooks_map['setup']
            setup_hook()

        if not self.context.has_open:
            print('Call size to open context.')
            return

        self.renderer.setup(self.context.width, self.context.height)

    @logger.record('loop')
    def _loop(self):
        events = self.context.get_events()
        for e in events:
            self._handle_event(e)

        if self.is_loop:
            if self.has_draw_hook:
                draw_hook = self.hooks_map['draw']
                draw_hook()

            if self.renderer.has_background_called:
                self.context.background(self.renderer.background_color)

            self.renderer.render()
            self.context.draw(
                self.renderer.diff_buffer,
                self.renderer.color_pair
            )

            self.renderer.has_background_called = False
            self.frame_count += 1

    def add_hook(self, name, hook):
        self.hooks_map[name] = hook

    def _handle_event(self, e):
        if e.type == 'mouse':
            self.pmouse_x = self.mouse_x
            self.pmouse_y = self.mouse_y
            self.mouse_x = e.x
            self.mouse_y = e.y
            mouse_hook = self.hooks_map['mouse_clicked']
            mouse_hook()
        elif e.type == "window":
            window_hook = self.hooks_map['window_resized']
            window_hook()
        elif e.type == "keyboard":
            self.key = e.key
            keyTyped_hook = self.hooks_map['key_typed']
            keyTyped_hook()


class Renderer(object):

    color_pair = []

    def __init__(self):
        self.shape_queue = []
        self._flag = True
        self._color_by_pos = {}
        self.diff_buffer = []

        # styles
        self.color_channels = (255,)
        self.stroke_weight = 0
        self.is_stroke_enabled = True
        self.is_fill_enabled = True
        self.is_tint_enabled = False
        self.rect_mode = constants.CORNER
        self.ellipse_mode = constants.CENTER
        self.image_mode = constants.CORNER
        self.text_align_x = constants.LEFT
        self.text_align_y = constants.TOP
        self.text_size = constants.NORMAL
        self.text_font = 'standard'

        self.has_background_called = False
        self.transform_matrix_stack = []
        self.width = 10
        self.height = 10

    def init(self, mode):
        self.fill_color = CColor.empty()
        self.background_color = CColor.empty()
        self.pre_background_color = CColor.empty()
        self.stroke_color = CColor('*')
        self.tint_color = CColor('·')
        self.mode = mode

    def setup(self, width, height):
        self.width = width
        self.height = height

    def render(self):
        self.diff_buffer.clear()
        while len(self.shape_queue) > 0:
            shape = self.shape_queue.pop(0)
            self._render_shape(shape)
        self.transform_matrix_stack.clear()

    def add_element(self, element):
        if isinstance(element, CImage):
            element = self._image_to_shape(element)
        elif isinstance(element, CText):
            element = self._text_to_shape(element)
        if element.is_auto:
            element.fill_color = self.fill_color
            element.stroke_color = self.stroke_color
            element.tint_color = self.tint_color
            element.stroke_weight = self.stroke_weight
            element.is_tint_enabled = self.is_tint_enabled
            element.is_fill_enabled = self.is_fill_enabled
            element.is_stroke_enabled = self.is_stroke_enabled
            element.transform_matrix_stack = self.transform_matrix_stack[:]
        self.shape_queue.append(element)

    def background(self, color):
        self.has_background_called = True
        self.pre_background_color = self.background_color
        self.background_color = color

    def _text_to_shape(self, text):
        return text.to_shape(
            self.text_size,
            self.text_font,
            self.text_align_x,
            self.text_align_y
        )

    def _image_to_shape(self, image):
        return 1

    @logger.record('render shape')
    def _render_shape(self, shape):
        vertices = self._vertex_processing(
            shape.points,
            shape.stroke_color,
            shape.tint_color,
            shape.is_tint_enabled,
            shape.stroke_weight,
            shape.transform_matrix_stack,
            shape.primitive_type
        )

        primitives = self._primitive_assembly(
            vertices,
            shape.primitive_type,
            shape.close_mode,
            shape.options
        )

        fragments = self._rasterization(
            primitives,
            shape.fill_color,
            shape.tint_color,
            shape.is_stroke_enabled,
            shape.is_fill_enabled,
            shape.primitive_type
        )

        fragments_clipped = self._clipping(fragments)
        self._fragment_processing(fragments_clipped)

    @logger.record('vertex processing')
    def _vertex_processing(self, points, stroke_color, tint_color, is_tint_enabled, stroke_weight, transform_matrix_stack, primitive_type):
        tm = Matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        sm = Matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        rotation = 0
        while len(transform_matrix_stack) > 0:
            matrix = transform_matrix_stack.pop()
            tm = matrix * tm
            if matrix.type == "scale":
                sm = matrix * sm
            elif matrix.type == "rotate":
                rotation += matrix.value
        sx = sm[0][0]
        sy = sm[1][1]

        for p in points:
            # transform
            mp = Matrix([[p.x], [p.y], [1]])
            tp = tm * mp
            p.x = int(tp[0][0])
            p.y = int(tp[1][0])
            p.weight_x = sx * stroke_weight if stroke_weight != 0 else sx - 1
            p.weight_y = sy * stroke_weight if stroke_weight != 0 else sy - 1
            p.rotation = rotation

            # screen map && color
            if primitive_type == constants.IMAGE:
                ch = p.color.ch if not is_tint_enabled else tint_color.ch
                p.color = CColor.create(ch, p.color.fg, p.color.bg)
            elif primitive_type == constants.TEXT:
                p.color = CColor.create(
                    p.color.ch,
                    stroke_color.fg,
                    stroke_color.bg
                )
            else:
                p.color = stroke_color

        return points

    @logger.record('primitive assembly')
    def _primitive_assembly(self, vertices, primitive_type, close_mode, options):
        # vertices
        if primitive_type == constants.POLYGON:
            if close_mode == constants.CLOSE:
                normal_vertices = [
                    v for v in vertices
                    if v.type == "normal"
                ]
                vertices.append(normal_vertices[0])
            ps = [vertices]
        elif primitive_type == constants.POINTS:
            ps = [[v] for v in vertices]
        elif primitive_type == constants.LINES:
            ps = [
                [vertices[i],
                 vertices[i + 1]]
                for i in range(0, len(vertices) - 1, 2)
            ]
        elif primitive_type == constants.TRIANGLES:
            ps = [
                [vertices[i],
                 vertices[i + 1],
                 vertices[i + 2],
                 vertices[i]]
                for i in range(0, len(vertices) - 2, 3)
            ]
        elif primitive_type == constants.TRIANGLE_STRIP:
            ps = [
                [vertices[i],
                 vertices[i + 1],
                 vertices[i + 2],
                 vertices[i]]
                for i in range(len(vertices) - 2)
            ]
        elif primitive_type == constants.TRIANGLE_FAN:
            ps = [
                [vertices[0],
                 vertices[i],
                 vertices[i + 1],
                 vertices[0]]
                for i in range(1, len(vertices) - 1)
            ]
        elif primitive_type == constants.QUADS:
            ps = [
                [vertices[i],
                 vertices[i + 1],
                 vertices[i + 2],
                 vertices[i + 3],
                 vertices[i]]
                for i in range(0, len(vertices) - 3, 4)
            ]
        elif primitive_type == constants.QUAD_STRIP:
            ps = [
                [vertices[i],
                 vertices[i + 1],
                 vertices[i + 3],
                 vertices[i + 2],
                 vertices[i]]
                for i in range(len(vertices) - 3, 2)
            ]
        elif primitive_type == constants.ARC:
            start = options['start']
            stop = options['stop']
            mode = options['mode']
            p1, p2, p3, p4 = vertices
            a = int(dist(p1.x, p1.y, p2.x, p2.y) / 2)
            b = int(dist(p1.x, p1.y, p4.x, p4.y) / 2)
            x0 = int((p1.x + p3.x) / 2)
            y0 = int((p1.y + p3.y) / 2)
            rotation = angle_between(1, 0, p2.x - p1.x, p2.y - p1.y)
            points = self._discretize_arc(
                x0, y0, a, b, start, stop, p1.color, rotation, mode
            )
            ps = [points]
        elif primitive_type == constants.CURVE:
            points = []
            curve_tightness = options['curve_tightness']
            for i in range(len(vertices) - 3):
                points += self._discretize_curve(
                    vertices[i],
                    vertices[i + 1],
                    vertices[i + 2],
                    vertices[i + 3],
                    vertices[i].color,
                    curve_tightness
                )
            ps = [points]
        elif primitive_type == constants.BEZIER:
            points = []
            for i in range(0, len(vertices) - 3, 3):
                points += self._discretize_bezier(
                    vertices[i],
                    vertices[i + 1],
                    vertices[i + 2],
                    vertices[i + 3],
                    vertices[i].color
                )
            ps = [points]
        elif primitive_type == constants.IMAGE:
            w = options['width']
            h = options['height']
            ps = []
            for j in range(0, h - 1):
                for i in range(0, w - 1):
                    i1 = j * w + i
                    i2 = j * w + i + 1
                    i3 = (j + 1) * w + i + 1
                    i4 = (j + 1) * w + i
                    ps.append(
                        [vertices[i1],
                         vertices[i2],
                         vertices[i3],
                         vertices[i4]]
                    )
        elif primitive_type == constants.TEXT:
            ps = [[v] for v in vertices]

        # edges
        edges_list = []
        for vertices in ps:
            unique_vertices = [
                v for i, v in enumerate(vertices)
                if i == 0
                or (v.x != vertices[i - 1].x or v.y != vertices[i - 1].y)
            ]
            normal_vertices = [
                v for v in unique_vertices
                if v.type == "normal"
            ]
            contour_vertices = [
                v for v in unique_vertices
                if v.type == "contour"
            ]
            normal_edges = self._vertices_to_edges(normal_vertices)
            contour_edges = self._vertices_to_edges(contour_vertices)
            edges_list.append(normal_edges + contour_edges)

        return edges_list

    @logger.record('rasterizatioin')
    def _rasterization(self, primitives, fill_color, tint_color, is_stroke_enabled, is_fill_enabled, primitive_type):
        fragments = []

        for edges in primitives:
            fill_pixels = []
            stroke_pixels = []

            if len(edges) == 0:
                fragments.append([])
            elif len(edges) == 1:
                stroke_pixels += self._rasterize_line(
                    edges[0][0], edges[0][-1]
                )
                fragments.append(stroke_pixels)
            else:
                # fill polygon
                if is_fill_enabled:
                    fill_edges = self._close_polygon(edges)

                    if primitive_type == constants.IMAGE or primitive_type == constants.TEXT:
                        fill_color = fill_edges[0][0].color

                    fill_pixels += self._scan_line_filling(
                        fill_edges, fill_color
                    )

                # stroke the polygon
                if is_stroke_enabled:
                    for e in edges:
                        stroke_pixels += self._rasterize_line(
                            e[0],
                            e[1],
                        )

                pixels = fill_pixels + stroke_pixels
                fragments.append(pixels)
        return fragments

    @logger.record('clipping')
    def _clipping(self, fragments):
        return [
            [
                p for p in pixels
                if p.x >= 0
                and p.x < self.width
                and p.y >= 0
                and p.y < self.height
            ]
            for pixels in fragments
        ]

    @logger.record('fragment processing')
    def _fragment_processing(self, fragemnts):
        color_by_pos = {}

        for pixels in fragemnts:
            for p in pixels:
                key = f'({p.x},{p.y})'
                color_by_pos[key] = [p, self._flag]

        diff_colors = color_by_pos.copy()

        # remove
        remove_keys = []
        for key, value in diff_colors.items():
            if key in self._color_by_pos:
                self._color_by_pos[key][1] = self._flag
                pvalue = self._color_by_pos[key]
                if pvalue[0] == value[0]:
                    remove_keys.append(key)

        for key in remove_keys:
            diff_colors.pop(key)

        # add
        if self.has_background_called:
            keys = [
                key for key, value in self._color_by_pos.items()
                if value[1] != self._flag
            ]
            for key in keys:
                pp = self._color_by_pos[key][0]
                if pp.color != self.background_color:
                    diff_colors[key] = [
                        Point(pp.x, pp.y, self.background_color),
                        pp, self._flag
                    ]

            if self.background_color != self.pre_background_color:
                for x in range(self.width):
                    for y in range(self.height):
                        key = f'({x},{y})'
                        if not key in color_by_pos and not key in diff_colors:
                            diff_colors[key] = [
                                Point(x, y, self.background_color),
                                self._flag
                            ]

        self.diff_buffer = [value[0] for value in diff_colors.values()]
        self._color_by_pos = color_by_pos
        self._flag = not self._flag

    def get_pixels(self):
        pixels = []
        for i in range(self.width):
            for j in range(self.height):
                key = f'({i},{j})'
                if key in self._color_by_pos:
                    pixels.append(self._color_by_pos[key][0])
                else:
                    pixels.append(self.background_color)
        return pixels

    @logger.record('polygon filling')
    def _scan_line_filling(self, polygon, fill_color):
        '''
        https://www.cs.uic.edu/~jbell/CourseNotes/ComputerGraphics/PolygonFilling.html
        '''
        pixels = []
        ymin = float('inf')
        ymax = float('-inf')
        for e in polygon:
            v1, v2 = e
            ymin = min(v1.y, v2.y, ymin)
            ymax = max(v1.y, v2.y, ymax)

        def has_intersect(e, y):
            v1, v2 = e
            if v1.y > v2.y:
                return y < v1.y and y >= v2.y
            elif v1.y == v2.y:
                return y == v1.y
            else:
                return y > v1.y and y <= v2.y

        for y in range(ymin, ymax + 1):
            # calc the intersections
            intersections = []
            for i, e in enumerate(polygon):
                if has_intersect(e, y):
                    v1, v2 = e
                    if v1.y == v2.y:
                        x = v2.x
                    else:
                        x = round(map(y, v1.y, v2.y, v1.x, v2.x))

                    # pay more attention if is a joint point
                    ne = polygon[i + 1] if i < len(polygon) - 1 else polygon[0]
                    v3 = ne[1]
                    y_diff = (v1.y - y) * (v3.y - y)
                    is_left = to_left(v1.x, v1.y, v2.x, v2.y, v3.x, v3.y)
                    is_joint = x == v2.x and y == v2.y
                    if is_joint and (y_diff > 0 or (y_diff == 0 and is_left)):
                        intersections += [x, x]
                    else:
                        intersections += [x]

            if len(intersections) == 1:
                pixels += [Point(intersections[0], y, fill_color)]
            else:
                intersections_sorted = sorted(intersections)
                is_draw = True
                for i, x0 in enumerate(intersections_sorted):
                    if is_draw and i < len(intersections_sorted) - 1:
                        x1 = intersections_sorted[i + 1]
                        pixels += self._rasterize_line(
                            Point(x0, y, fill_color),
                            Point(x1, y, fill_color)
                        )
                    is_draw = not is_draw
        return pixels

    @logger.record('draw line')
    def _rasterize_line(self, v1, v2):
        pixels = []

        dx = abs(v1.x - v2.x)
        dy = abs(v1.y - v2.y)

        if dx >= dy:
            start_x = min(v1.x, v2.x)
            end_x = max(v1.x, v2.x)
            for x in range(start_x, end_x + 1):
                y = map(x, v1.x, v2.x, v1.y, v2.y)
                pixels += self._rasterize_point(
                    x, round(y),
                    v1.color,
                    v1.weight_x, v1.weight_y,
                    v1.rotation
                )
        else:
            start_y = min(v1.y, v2.y)
            end_y = max(v1.y, v2.y)
            for y in range(start_y, end_y + 1):
                x = map(y, v1.y, v2.y, v1.x, v2.x)
                pixels += self._rasterize_point(
                    round(x), y,
                    v1.color,
                    v1.weight_x, v1.weight_y,
                    v1.rotation
                )

        return pixels

    def _rasterize_point(self, x, y, color, stroke_weight_x=0, stroke_weight_y=0, rotation=0):
        if stroke_weight_x == 0 or stroke_weight_y == 0:
            return [Point(x, y, color)]

        vertices = self._discretize_arc(
            x, y,
            stroke_weight_x,
            stroke_weight_y,
            0,
            constants.TAU,
            color,
            rotation
        )
        edges = self._vertices_to_edges(vertices)
        return self._scan_line_filling(edges, color)

    def _discretize_ellipse(self, x0, y0, color, rotation):
        pass

    def _discretize_arc(self, x0, y0, a, b, start, stop, color, rotation=0, mode=constants.CHORD):
        if a == 0 or b == 0:
            return [Point(x0, y0, color)]

        points = []
        pre_x = a
        pre_y = 0
        pre_angle = 0
        angle = start
        cs = (2 * math.pi * b + 4 * (a - b)) * (stop - start) / (math.pi * 2)
        cnt = max(10, int(cs / 20) * 10)
        step = (stop - start) / cnt

        while angle < stop or math.isclose(angle, stop, abs_tol=1e-9):
            theta = angle - pre_angle
            pre_angle = angle
            angle += step

            cos = math.cos(theta)
            sin = math.sin(theta)

            x = pre_x * cos + pre_y * sin * (-a / b)
            y = pre_x * sin * (b / a) + pre_y * cos
            if x != pre_x or y != pre_y:
                pre_x = x
                pre_y = y
                rotated_x = math.cos(rotation) * x - math.sin(rotation) * y
                rotated_y = math.sin(rotation) * x + math.cos(rotation) * y
                points.append(
                    Point(
                        round(rotated_x + x0),
                        round(rotated_y + y0),
                        color=color
                    )
                )
        if mode == constants.PIE:
            points.insert(0, Point(x0, y0, color=color))
            points.append(points[0])
        elif mode == constants.CHORD:
            points.append(points[0])

        return points

    def _discretize_curve(self, p0, p1, p2, p3, color, s):
        t = 0
        d = dist(p1.x, p1.y, p2.x, p2.y)
        cnt = int(d / 2)
        points = []
        pre_x = None
        pre_y = None
        s = 1 - s
        while t < 1 or math.isclose(t, 1, abs_tol=1e-9):
            t3 = t ** 3
            t2 = t ** 2
            t1 = t
            t0 = 1
            a = -s * t3 + 2 * s * t2 - s * t1
            b = (2 - s) * t3 + (s - 3) * t2 + 1 * t0
            c = (s - 2) * t3 + (3 - 2 * s) * t2 + s * t1
            d = s * t3 - s * t2
            x = round(a * p0.x + b * p1.x + c * p2.x + d * p3.x)
            y = round(a * p0.y + b * p1.y + c * p2.y + d * p3.y)
            if pre_x != x or pre_y != y:
                points.append(Point(x, y, color=color))
            pre_x = x
            pre_y = y
            t += 1 / cnt
        return points

    def _discretize_bezier(self, p0, p1, p2, p3, color):
        t = 0
        d1 = dist(p0.x, p0.y, p1.x, p1.y)
        d2 = dist(p1.x, p1.y, p2.x, p2.y)
        d3 = dist(p2.x, p2.y, p3.x, p3.y)
        cnt = int((d1 + d2 + d3) / 3)
        points = []
        pre_x = None
        pre_y = None
        while t < 1 or math.isclose(t, 1, abs_tol=1e-9):
            a = (1 - t) ** 3
            b = 3 * t * (1 - t) ** 2
            c = 3 * t ** 2 * (1 - t)
            d = t ** 3
            x = round(a * p0.x + b * p1.x + c * p2.x + d * p3.x)
            y = round(a * p0.y + b * p1.y + c * p2.y + d * p3.y)
            if pre_x != x or pre_y != y:
                points.append(Point(x, y, color=color))
            pre_x = x
            pre_y = y
            t += 1 / cnt
        return points

    def _vertices_to_edges(self, vertices):
        if len(vertices) == 0:
            return []
        elif len(vertices) == 1:
            v = vertices[0]
            return [(v,)]
        else:
            edges = []
            for i in range(1, len(vertices)):
                v1 = vertices[i - 1]
                v2 = vertices[i]
                edges.append((v1, v2))
            return edges

    def _close_polygon(self, edges):
        fill_edges = edges.copy()
        normal_edges = [
            e for e in fill_edges
            if e[0].type == "normal"
        ]
        first_point = normal_edges[0][0]
        last_point = normal_edges[-1][1]
        if last_point.x != first_point.x or last_point.y != first_point.y:
            fill_edges.append((last_point, first_point))
        return fill_edges


class Context(metaclass=ABCMeta):

    @abstractclassmethod
    def close(self):
        """ close the drawing context and restore state of canvas """

    @abstractclassmethod
    def no_cursor(self):
        """ hide cursor """

    @abstractclassmethod
    def cursor(self):
        """ show cursor """

    @abstractclassmethod
    def get_events(self):
        """ get event: mouse event, keyboard event, cursor event """

    @abstractclassmethod
    def clear(self):
        """ clear the screen when called background() """

    @abstractclassmethod
    def addch(self, x, y, ch, fg=None, bg=None):
        """ add ch to screen """

    @abstractclassmethod
    def enable_colors(self):
        """ enable colors """

    @abstractclassmethod
    def init(self):
        """ init the terminal """

    @abstractclassmethod
    def update_window(self):
        """ update the size of the window """

    @abstractclassmethod
    def refresh(self):
        """ refresh the physical sceen """

    @abstractclassmethod
    def background(self, color):
        """ set the background of the screen """

    def __init__(self):
        self.window_width = 0
        self.window_height = 0
        self.terminal_width = 0
        self.terminal_height = 0
        self.inner_width = 0
        self.inner_height = 0
        self.width = 0
        self.height = 0
        self.has_open = False
        self._pad_width = 0
        self._pad_height = 0
        self._buffer = []
        self._cell_poss = []
        self._color_pair = []
        self._pad_x = 0
        self._pad_y = 0
        self._screen = None
        self._background_color = constants.BLACK

    def open(self, width=10, height=10, is_full_screen=False):
        self.init()

        if is_full_screen:
            self.width = self.window_width
            self.height = self.window_height
        else:
            self.width = width
            self.height = height

        self._pad_width = self.width + 2
        self._pad_height = self.height + 2
        self._update_pad()
        self.has_open = True

    @logger.record('flush screen')
    def draw(self, buffer, color_pair):
        self._buffer = buffer
        self._color_pair = color_pair
        self._update_pad()
        self.enable_colors()

        for p in buffer:
            x = p.x + self._pad_x + 1
            y = p.y + self._pad_y + 1
            ch = p.color.ch
            ch = ch[0] if isinstance(ch, tuple) else ch
            if self._in(x, y):
                self.addch(x, y, ch, p.color.fg, p.color.bg)

        # update the physical sceen
        self.refresh()

    def _update_pad(self):
        # update location
        self._pad_x = (self.window_width - self._pad_width) // 2
        self._pad_y = (self.window_height - self._pad_height) // 2

        # draw pad
        for i in range(self._pad_width):
            x = self._pad_x + i
            y = self._pad_y
            if self._in(x, y):
                ch = '+' if i == 0 else '-'
                self.addch(x, y, ch)

        # right
        for i in range(self._pad_height - 1):
            x = self._pad_x + self._pad_width - 1
            y = self._pad_y + i
            if self._in(x, y):
                ch = '+' if i == 0 else '|'
                self.addch(x, y, ch)

        # left
        for i in range(self._pad_height - 1):
            x = self._pad_x
            y = self._pad_y + 1 + i
            if self._in(x, y):
                ch = '+' if i == self._pad_height - 2 else '|'
                self.addch(x, y, ch)

        # bottom
        for i in range(self._pad_width - 1):
            x = self._pad_x + 1 + i
            y = self._pad_y + self._pad_height - 1
            if self._in(x, y):
                ch = '+' if i == self._pad_width - 2 else '-'
                self.addch(x, y, ch)

    def _in(self, x, y):
        return x >= 0 and x < self.window_width and y >= 0 and y < self.window_height

    def _resize(self):
        self._screen.clear()
        self.update_window()
        self.background(self._background_color)
        self.draw(self._buffer, self._color_pair)


if sys.platform == WINDOWS:
    class WindowsContext(Context):
        def __init__(self):
            super(WindowsContext, self).__init__()

        def init(self):
            print('hello windows context')

        def close(self):
            pass

        def no_cursor(self):
            pass

        def cursor(self):
            pass

        def get_events(self):
            pass

        def clear(self):
            pass

        def update_window(self):
            pass

        def enable_colors(self):
            pass

        def addch(self):
            pass

        def refresh(self):
            pass

        def background(self, color):
            pass


elif sys.platform == BROWSER:

    from js import document as doc  # pylint: disable=imports
    from js import window  # pylint: disable=imports
    from js import term  # pylint: disable=imports
    from js import fit_addon  # pylint: disable=imports

    class BrowserContext(Context):

        def __init__(self):
            super(BrowserContext, self).__init__()
            self.terminal_width = 720
            self.terminal_height = 408
            self.inner_width = window.innerWidth
            self.inner_height = window.innerHeight
            self.options = None
            self._write_content = ''
            self._has_cursor = True
            self._container = None
            self._color_palette = generate_xtermjs_colors()

        def init(self):
            if self.options == None:
                self.options = {}

            self._screen = term
            for key, value in self.options.items():
                self._screen.setOption(key, value)

            # set the css styles of container
            self._container = doc.getElementById("terminal")
            self._styles(self._container, {
                'background': 'black',
                'width': self.terminal_width,
                'height': self.terminal_height,
                'display': 'flex',
                'justifyContent': 'center',
                'alignItems': 'center'
            })

            self.fit_addon = fit_addon
            self._screen.loadAddon(fit_addon)
            self._screen.open(self._container)
            fit_addon.fit()

            self.window_height = self._screen.rows
            self.window_width = self._screen.cols

        def addch(self, x, y, ch, fg=constants.WHITE, bg=constants.BLACK):
            _x = x - self._pad_x
            _y = y - self._pad_y

            if _y > 0 and _y < self._pad_height - 1:
                x = self._cell_poss[_y - 1]['list'][_x] + self._pad_x

            csi_fg = f'\x1b[38;5;{fg}m'
            csi_bg = f'\x1b[48;5;{bg}m'
            csi_pos = f'\x1b[{y + 1};{x};H'
            self._write_content += f'{csi_pos}{csi_fg}{csi_bg}{ch}'

            if get_char_width(ch) == 2:
                csi_pos = f'\x1b[{y + 1};{x + 1};H'
                ch = " "
                self._write_content += f'{csi_pos}{csi_fg}{csi_bg}{ch}'

        def close(self):
            self._screen.clear()

        def no_cursor(self):
            self._has_cursor = False

        def cursor(self):
            self._has_cursor = True

        def enable_colors(self):
            pass

        def get_events(self):
            return []

        def clear(self):
            self._screen.clear()

        def update_window(self):
            pass

        def background(self, color_index):
            r, g, b = self._color_palette[color_index]
            color = f'rgb({r}, {g}, {b})'
            self._styles(self._container, {
                'background': color
            })
            self._screen.setOption('theme', {
                'background': color
            })

        def refresh(self):
            cursor_control = '\x1b[?25h' if self._has_cursor else '\x1b[?25l'
            self._screen.write(self._write_content + cursor_control)
            self._write_content = ''

        def _styles(self, dom, styles):
            for key, value in styles.items():
                dom.style[key] = f'{value}px' if isinstance(
                    value, int) else value


else:
    import curses

    class CursesContext(Context):

        def __init__(self):
            super(CursesContext, self).__init__()
            self._screen = curses.initscr()
            self.window_width = self._screen.getmaxyx()[1]
            self.window_height = self._screen.getmaxyx()[0]

        def init(self):
            self._screen.keypad(1)
            self._screen.nodelay(1)
            self._screen.leaveok(False)

            # init
            curses.noecho()
            curses.cbreak()
            curses.start_color()

            # Enable mouse events
            curses.mousemask(curses.ALL_MOUSE_EVENTS |
                             curses.REPORT_MOUSE_POSITION)

        def close(self):
            self._screen.keypad(0)
            curses.nocbreak()
            curses.echo()
            curses.endwin()

        def no_cursor(self):
            curses.curs_set(0)

        def cursor(self):
            curses.curs_set(1)

        def get_events(self):
            event_queue = []
            key = self._screen.getch()
            while key != -1:
                if key == curses.KEY_RESIZE:
                    self._resize()
                    event_queue.append(WindowEvent())
                elif key == curses.KEY_MOUSE:
                    _, x, y, _, bstate = curses.getmouse()
                    _x = x - (self._pad_x + 1)
                    _y = y - (self._pad_y + 1)
                    x_in = _x > 0 and _x < self._pad_width - 1
                    y_in = _y > 0 and _y < self._pad_width - 1
                    if x_in and y_in:
                        event_queue.append(MouseEvent(_x, _y, bstate))
                else:
                    # self._screen.move(10, 10)
                    event_queue.append(KeyboardEvent(key))
                key = self._screen.getch()
            return event_queue

        def addch(self, x, y, ch, fg=None, bg=None):
            # (window_height - 1, window_width - 1) is not available
            if x >= self.window_width - 1 and y >= self.window_height - 1:
                return

            if fg != None and bg != None:
                color_index = self._get_color_index(fg, bg)
                self._screen.addstr(
                    y, x, ch, curses.color_pair(color_index)
                )
            else:
                self._screen.addstr(
                    y, x, ch
                )

        def clear(self):
            self._screen.clear()

        def refresh(self):
            self._screen.refresh()

        def background(self, color):
            pass
            # self.clear()
            # self._background_color = color
            # fg = color.fg
            # bg = color.bg
            # ch = color.ch[0] if isinstance(color.ch, tuple) else color.ch
            # color_index = self._get_color_index(fg, bg)
            # self._screen.bkgd(ch, curses.color_pair(color_index))

        def enable_colors(self):
            for i, c in enumerate(self._color_pair):
                if not c.has_init:
                    curses.init_pair(i + 1, c.fg, c.bg)
                    c.has_init = True

        def update_window(self):
            curses.update_lines_cols()
            self.window_width = self._screen.getmaxyx()[1]
            self.window_height = self._screen.getmaxyx()[0]

        def _get_color_index(self, fg, bg):
            color_index = -1
            for i, c in enumerate(self._color_pair):
                if fg == c.fg and bg == c.bg:
                    color_index = i + 1
            return color_index


class Timer(metaclass=ABCMeta):
    @abstractclassmethod
    def run(self, ms, callback):
        pass

    @abstractclassmethod
    def stop(self, ms, callback):
        pass

    @abstractclassmethod
    def wait(self):
        pass


class ImageLoader(metaclass=ABCMeta):

    @abstractclassmethod
    def load(self, src):
        '''load image data'''
        pass

    def convert_color(self, data):
        pixels = []
        CColor.save()
        CColor.color_mode = constants.RGB
        CColor.color_channels = (255, 255, 255)
        for r, g, b, _ in data:
            c = (r, g, b)
            pixels.append(CColor('·', c, c))
        CColor.restore()
        return pixels


if sys.platform == BROWSER:
    from js import window  # pylint: disable=imports

    class BrowserTimer(Timer):
        def run(self, ms, callback):
            self.t = window.setInterval(callback, ms)

        def stop(self):
            window.clearInterval(self.t)

        def wait(self):
            pass

    class BrowserImageLoader(ImageLoader):
        def load(self, src):
            pass
else:
    import time
    from PIL import Image

    class LocalTimer(Timer):

        def run(self, ms, callback):
            while True:
                t1 = time.time()
                callback()
                t2 = time.time()
                d = ms / 1000 - (t2 - t1)
                if d > 0:
                    time.sleep(d)

        def stop(self):
            pass

        def wait(self):
            input()

    class PILImageLoader(ImageLoader):
        def load(self, src):
            image = Image.open(src)
            w, h = image.size
            data = image.getdata()
            pixels = self.convert_color(data)
            return CImage(pixels, w, h)


class CShape(object):

    def __init__(self, points=None, is_auto=True, primitive_type=constants.POLYGON, close_mode=constants.CLOSE, options=None):
        self.points = [] if points == None else points
        self.options = {} if options == None else options
        self.is_auto = is_auto
        self.primitive_type = primitive_type
        self.close_mode = close_mode
        self.fill_color = None
        self.stroke_color = None
        self.tint_color = None
        self.stroke_weight = None
        self.transform_matrix_stack = []
        self.is_stroke_enabled = True
        self.is_fill_enabled = True
        self.is_tint_enabled = False

    def __str__(self):
        attrs = {
            'fill_color': self.fill_color,
            'stroke_color': self.stroke_color,
            'primitive_type': self.primitive_type,
            'close_mode': self.close_mode,
            'is_stroke_enabled': self.is_stroke_enabled,
            'is_fill_enabled': self.is_fill_enabled,
            'stroke_weight': self.stroke_weight,
            'points': self.points
        }
        return attrs.__str__()

    __repr__ = __str__


class Point(object):

    def __init__(self, x, y, color=None, weight_x=0, weight_y=0, rotation=0, type="normal"):
        self.x = x
        self.y = y
        self.weight_x = weight_x
        self.weight_y = weight_y
        self.color = color
        self.type = type
        self.rotation = rotation
        self.color = CColor.empty() if color == None else color

    def __str__(self):
        attrs = {
            "x": self.x,
            "y": self.y,
            "color": self.color
        }
        return attrs.__str__()

    def __eq__(self, other):
        x = self.x == other.x
        y = self.y == other.y
        weight_x = self.weight_x == other.weight_x
        weight_y = self.weight_y == other.weight_y
        color = self.color == other.color
        type = self.type == other.type
        return x and y and weight_x and weight_y and color and type

    def __hash__(self):
        return hash(f'({self.x}, {self.y})')

    __repr__ = __str__


class CColor(object):

    color_mode = constants.ANSI
    color_channels = (255,)

    def __init__(self, ch=" ", fg=None, bg=None):
        self.has_init = False
        if isinstance(ch, self.__class__):
            self.ch = ch.ch
            self.fg = ch.fg
            self.bg = ch.bg
        else:
            self.ch = ch
            if self.color_mode == constants.ANSI:
                self.fg = self._init_ansi(fg, constants.WHITE)
                self.bg = self._init_ansi(bg, constants.BLACK)
            elif self.color_mode == constants.RGB:
                m1, m2, m3 = self.color_channels  # pylint: disable=unbalanced-tuple-unpacking
                self.fg = self._init_truecolor(fg, (m1, m2, m3))
                self.bg = self._init_truecolor(bg, (0, 0, 0))
            else:
                m1, m2, m3 = self.color_channels  # pylint: disable=unbalanced-tuple-unpacking
                self.fg = self._init_truecolor(fg, (m1, 0, m3))
                self.bg = self._init_truecolor(bg, (0, 0, 0))

        self.add_color(self)

    def _init_ansi(self, index, default):
        if index == None:
            index = default
        return round(map(index, 0, self.color_channels[0], 0, 255))

    def _init_truecolor(self, channels, default):
        if channels == None:
            channels = default
        elif len(channels) == 1:
            g = channels[0]
            channels = (g, g, g)
        c1, c2, c3 = [
            map(c, 0, self.color_channels[i], 0, 1)
            for i, c in enumerate(channels)
        ]
        if self.color_mode == constants.RGB:
            return self.rgb_to_ansi256(c1, c2, c3)
        else:
            return self.hsv_to_ansi256(c1, c2, c3)

    def __eq__(self, other):
        if other == None:
            return False
        ch = self.ch == other.ch
        fg = self.fg == other.fg
        bg = self.bg == other.bg
        if ch and self.ch == " ":
            return bg
        else:
            return ch and fg and bg

    def __len__(self):
        return get_char_width(self.ch)

    @classmethod
    def create(cls, ch, fg, bg):
        cls.save()
        cls.color_mode = constants.ANSI
        cls.color_channels = (255,)
        c = cls(ch, fg, bg)
        cls.restore()
        return c

    @classmethod
    def empty(cls):
        # solve unicode problem
        if cls.color_mode == constants.ANSI:
            return cls(" ", constants.BLACK)
        else:
            return cls(" ", (0, 0, 0))

    @classmethod
    def rgb_to_ansi256(cls, r, g, b):
        r *= 255
        g *= 255
        b *= 255
        if r == g and g == b:
            if r < 8:
                return 16
            if r > 248:
                return 231
            return round(((r - 8) / 247) * 24) + 232

        ansi = 16 \
            + (36 * round(r / 255 * 5)) \
            + (6 * round(g / 255 * 5)) \
            + round(b / 255 * 5)

        return ansi

    @classmethod
    def ansi256_to_rgb(cls, v):
        if v < 16:
            return cls.ansi16_to_rgb(v)

        if v >= 232:
            c = (v - 232) * 10 + 8
            return (c, c, c)

        v -= 16
        rem = v % 36
        r = math.floor(v / 36) / 5 * 255
        g = math.floor(rem / 6) / 5 * 255
        b = (rem % 6) / 5 * 255
        return (r / 255, g / 255, b / 255)

    @classmethod
    def ansi16_to_rgb(cls, v):
        color = v % 10
        if color == 0 or color == 7:
            if v > 50:
                color += 3.5
            color = color / 10.5 * 255
            return (color / 255, color / 255, color / 255)

        mult = (~~(v > 50) + 1) * 0.5
        r = (color & 1) * mult
        g = ((color >> 1) & 1) * mult
        b = ((color >> 2) & 1) * mult
        return (r, g, b)

    @classmethod
    def rgb_to_hsb(cls, r, g, b):
        return colorsys.rgb_to_hsv(r, g, b)

    @classmethod
    def hsb_to_rgb(cls, h, s, b):
        return colorsys.hsv_to_rgb(h, s, b)

    @classmethod
    def hsv_to_ansi256(cls, h, s, v):
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return cls.rgb_to_ansi256(r, g, b)

    @classmethod
    def save(cls):
        cls._color_channels = cls.color_channels
        cls._color_mode = cls.color_mode

    @classmethod
    def restore(cls):
        cls.color_channels = cls._color_channels
        cls.color_mode = cls._color_mode

    @classmethod
    def add_color(cls, c):
        for color in Renderer.color_pair:
            if color.fg == c.fg and color.bg == c.bg:
                return None
        Renderer.color_pair.append(c)

    def __str__(self):
        attrs = {
            "ch": self.ch,
            "fg": self.fg,
            "bg": self.bg
        }
        return attrs.__str__()

    __repr__ = __str__


class CImage(object):

    def __init__(self, pixels, width, height):
        self._pixels = pixels
        self.pixels = []
        self.width = width
        self.height = height

    def load_pixels(self):
        self.pixels = [p for p in self._pixels]

    def update_pixels(self):
        self._pixels = [p for p in self.pixels]

    def copy(self):
        return self.__class__(self.pixels, self.width, self.height)

    def __getitem__(self, index):
        return self._pixels[index]

    def __setitem__(self, key, value):
        self._pixels[key] = value

    def __repr__(self):
        attrs = {
            'pixels': self._pixels,
            'width': self.width,
            'height': self.height
        }
        return attrs.__repr__()

    __str__ = __repr__


class CText(object):

    def __init__(self, text, x, y):
        self.text = text
        self.x = x
        self.y = y

    def to_shape(self, size, font, align_x, align_y):
        text = self._convert(self.text, size, font)
        matrix = self._matrixlize(text)
        height = matrix.row
        width = matrix.col

        if align_x == constants.RIGHT:
            self.x -= width
        elif align_x == constants.CENTER:
            self.x -= width / 2

        if align_y == constants.BOTTOM:
            self.y -= height
        elif align_y == constants.MIDDLE:
            self.y -= height / 2

        points = []
        for i, chars in enumerate(matrix):
            for j, ch in enumerate(chars):
                x0 = self.x + j
                y0 = self.y + i
                color = CColor(ch)
                points.append(Point(x0, y0, color=color))

        return CShape(points=points, primitive_type=constants.TEXT)

    @classmethod
    def text_width(cls, text, size, font):
        text = cls._convert(text, size, font)
        matrix = cls._matrixlize(text)
        return matrix.col

    @classmethod
    def text_height(cls, text, size, font):
        text = cls._convert(text, size, font)
        matrix = cls._matrixlize(text)
        return matrix.row

    @classmethod
    def _convert(cls, text, size, font):
        if size == constants.BIG:
            f = Figlet(font=font)
            text = f.renderText(text)
        elif size == constants.LARGE:
            f = Figlet(font=font)
            matrix = cls._matrixlize(text)
            max_width_list = [-1 for _ in range(matrix.col)]
            max_height = -1
            total_width = 0
            steps = []

            for j in range(matrix.col):
                for i in range(matrix.row):
                    ftext = f.renderText(matrix[i][j])
                    m = cls._matrixlize(ftext, False)
                    max_width_list[j] = max(max_width_list[j], m.col)
                    max_height = max(max_height, m.row)
                    matrix[i][j] = m
                start = total_width
                end = start + max_width_list[j]
                total_width = end
                steps.append((start, end))

            def get_info(n):
                for i, (start, end) in enumerate(steps):
                    if n >= start and n < end:
                        return [i, start, end]
                return -1

            text = ""
            for i in range(matrix.row * max_height):
                for j in range(total_width):
                    y0 = int(i / max_height)
                    x0, start, _ = get_info(j)
                    y = i % max_height
                    x = j - start

                    width = max_width_list[x0]
                    m = matrix[y0][x0]
                    mx1 = int((width - m.col) / 2)
                    mx2 = mx1 + m.col
                    my1 = int((max_height - m.row) / 2)
                    my2 = my1 + m.row

                    if x < mx1 or x >= mx2 or y < my1 or y >= my2:
                        text += " "
                    else:
                        text += m[y - my1][x - mx1]
                text += "\n"
        return text

    @staticmethod
    def _matrixlize(text, no_empty_line=True):
        if no_empty_line:
            lines = [
                line for line in text.split('\n')
                if not line in string.whitespace or len(line) == 1
            ]
        else:
            lines = [line for line in text.split('\n')]

        if len(lines) == 0:
            return Matrix([[]])

        max_width = max([len(line) for line in lines])
        matrix = [
            [line[i] if i < len(line) else ' '
             for i in range(max_width)]
            for line in lines
        ]
        return Matrix(matrix)


class Event(object):
    type = ""

    def __init__(self, type):
        self.type = type


class WindowEvent(Event):
    def __init__(self):
        super(WindowEvent, self).__init__('window')


class MouseEvent(Event):
    mouse_type = ""

    def __init__(self, x, y, type):
        super(MouseEvent, self).__init__('mouse')
        self.x = x
        self.y = y
        self.mouse_type = type


class KeyboardEvent(Event):

    def __init__(self, key):
        super(KeyboardEvent, self).__init__('keyboard')
        self.key = key
