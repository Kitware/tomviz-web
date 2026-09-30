"""The slice's in-view handles, after the desktop's
``vtkNonOrthoImagePlaneWidget``.

A double-headed arrow along the plane normal and a sphere at the plane
center. With the left button:

- dragging the slice itself pushes the plane along its normal (an
  axis-aligned slice steps through its indices);
- dragging the arrow tilts the plane;
- dragging the sphere slides the plane's center across it.

Tilting and sliding only make sense for a Custom plane: the owner switches
an axis-aligned slice to Custom when either starts (``on_start``). Events
the handles do not claim fall through to the camera. Mouse events reach
the server's interactor through the remote view, so the widget observes
the interactor like any VTK widget, ahead of the interactor style.

Unlike the desktop, a push follows the whole drag rather than each mouse
step, so a slow drag still moves an axis-aligned slice, and the handles
keep a constant size on screen through zooming.

Without a slice prop and without the sphere only the arrow is left, which
is how the volume's exploded view edits its custom direction.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersSources import vtkConeSource, vtkLineSource, vtkSphereSource
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkCellPicker,
    vtkPolyDataMapper,
    vtkProperty,
)

PUSHING = "pushing"
ROTATING = "rotating"
MOVING = "moving"

ARROW_COLOR = (1.0, 1.0, 1.0)
SELECTED_COLOR = (0.0, 0.0, 1.0)  # the desktop's highlight
ARROW_LENGTH = 0.3  # of the plane's half diagonal, each way (the desktop's)
HANDLE_PIXELS = 5.0 * 1.5 / math.sqrt(2)  # sphere / cone radius on screen
PICK_TOLERANCE = 0.005  # the desktop's

PRIORITY = 1.0  # ahead of the interactor style (0)


def _normalized(v):
    length = math.sqrt(sum(c * c for c in v))
    return tuple(c / length for c in v) if length > 0 else (0.0, 0.0, 1.0)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


class SlicePlaneWidget:
    """Handles for one slice. The owner places them (``place``) and reacts
    to the callbacks; the widget never moves the plane itself:

    - ``on_start(state)`` when a drag begins;
    - ``on_push(distance)``: move the plane to ``distance`` along its normal
      from where it was when the drag began;
    - ``on_rotate(normal)``: the new plane normal;
    - ``on_move(center)``: the new plane center;
    - ``on_end()`` when the drag is over.
    """

    def __init__(
        self,
        interactor,
        renderer,
        slice_prop,
        on_start: Callable[[str], None],
        on_push: Callable[[float], None],
        on_rotate: Callable[[tuple], None],
        on_move: Callable[[tuple], None],
        on_end: Callable[[], None],
        show_sphere: bool = True,
    ):
        self.interactor = interactor
        self.renderer = renderer
        self.slice_prop = slice_prop
        self._on_start = on_start
        self._on_push = on_push
        self._on_rotate = on_rotate
        self._on_move = on_move
        self._on_end = on_end

        self.state = None
        self._visible = False
        self._interactive = True
        self._center = (0.0, 0.0, 0.0)
        self._normal = (0.0, 0.0, 1.0)
        self._half_diagonal = 1.0
        self._pick_position = (0.0, 0.0, 0.0)
        self._drag_start = (0.0, 0.0, 0.0)

        self.property = vtkProperty(color=ARROW_COLOR, line_width=2)
        self.selected_property = vtkProperty(color=SELECTED_COLOR, line_width=2)

        self.lines = (vtkLineSource(), vtkLineSource())
        self.cones = (vtkConeSource(resolution=12), vtkConeSource(resolution=12))
        self.sphere = vtkSphereSource(theta_resolution=16, phi_resolution=8)
        self.arrow_actors = [
            self._actor(source) for source in (*self.lines, *self.cones)
        ]
        self.sphere_actor = self._actor(self.sphere) if show_sphere else None

        self.picker = vtkCellPicker()
        self.picker.SetTolerance(PICK_TOLERANCE)
        self.picker.PickFromListOn()
        for prop in (*self.props, slice_prop):
            if prop is not None:
                self.picker.AddPickList(prop)

        self._observers = {
            event: interactor.AddObserver(event, callback, PRIORITY)
            for event, callback in (
                ("LeftButtonPressEvent", self._on_press),
                ("MouseMoveEvent", self._on_mouse_move),
                ("LeftButtonReleaseEvent", self._on_release),
            )
        }
        # Keep the handles a constant size on screen whatever the zoom.
        self._render_observer = renderer.AddObserver("StartEvent", self._resize)
        self.set_visible(False)

    def _actor(self, source):
        actor = vtkActor(mapper=vtkPolyDataMapper(), property=self.property)
        source >> actor.mapper
        actor.PickableOn()
        actor.UseBoundsOff()  # never widen the camera's view of the data
        return actor

    @property
    def props(self):
        if self.sphere_actor is None:
            return tuple(self.arrow_actors)
        return (*self.arrow_actors, self.sphere_actor)

    def finalize(self):
        for tag in self._observers.values():
            self.interactor.RemoveObserver(tag)
        self._observers = {}
        self.renderer.RemoveObserver(self._render_observer)

    # ---- state -------------------------------------------------------------

    def set_visible(self, visible: bool):
        self._visible = bool(visible)
        for actor in self.props:
            actor.SetVisibility(self._visible)

    @property
    def interactive(self):
        return self._interactive

    @interactive.setter
    def interactive(self, value):
        self._interactive = bool(value)

    def place(self, center, normal, half_diagonal):
        """Put the handles on a plane through ``center``."""
        self._center = tuple(center)
        self._normal = _normalized(normal)
        self._half_diagonal = max(half_diagonal, 1e-12)
        length = ARROW_LENGTH * self._half_diagonal
        for sign, line, cone in zip((1, -1), self.lines, self.cones, strict=True):
            tip = tuple(
                c + sign * length * n
                for c, n in zip(self._center, self._normal, strict=True)
            )
            line.SetPoint1(*self._center)
            line.SetPoint2(*tip)
            cone.SetCenter(*tip)
            cone.SetDirection(*(sign * n for n in self._normal))
        self.sphere.SetCenter(*self._center)
        self._resize()

    def _resize(self, *_):
        """Size the sphere and cones in pixels, as the desktop does once."""
        radius = self._pixels_to_world(self._center, HANDLE_PIXELS)
        if radius is None:
            return
        self.sphere.SetRadius(radius)
        for cone in self.cones:
            cone.SetRadius(radius)
            cone.SetHeight(2 * radius)

    # ---- coordinates -------------------------------------------------------

    def _world_to_display(self, point):
        self.renderer.SetWorldPoint(*point, 1.0)
        self.renderer.WorldToDisplay()
        return self.renderer.GetDisplayPoint()

    def _display_to_world(self, x, y, z):
        self.renderer.SetDisplayPoint(x, y, z)
        self.renderer.DisplayToWorld()
        w = self.renderer.GetWorldPoint()
        if w[3] == 0:
            return None
        return (w[0] / w[3], w[1] / w[3], w[2] / w[3])

    def _pixels_to_world(self, point, pixels):
        if self.renderer.GetRenderWindow() is None:
            return None
        width, height = self.renderer.GetSize()
        if width <= 0 or height <= 0:
            return None
        x, y, z = self._world_to_display(point)
        a = self._display_to_world(x, y, z)
        b = self._display_to_world(x + pixels, y, z)
        if a is None or b is None:
            return None
        return math.dist(a, b)

    def _event_world_point(self, position):
        """The event position in world space, at the depth of the pick."""
        depth = self._world_to_display(self._pick_position)[2]
        return self._display_to_world(position[0], position[1], depth)

    # ---- events ------------------------------------------------------------

    def _abort(self, event):
        """Keep the event from the interactor style (the camera)."""
        self.interactor.GetCommand(self._observers[event]).SetAbortFlag(1)

    def _on_press(self, _interactor, event):
        if not (self._visible and self._interactive):
            return
        x, y = self.interactor.GetEventPosition()
        if not self.renderer.IsInViewport(x, y):
            return
        if not self.picker.Pick(x, y, 0.0, self.renderer):
            return
        prop = self.picker.GetViewProp()
        if prop in self.arrow_actors:
            state = ROTATING
        elif prop is not None and prop is self.sphere_actor:
            state = MOVING
        elif prop is not None and prop is self.slice_prop:
            state = PUSHING
        else:
            return

        self._pick_position = tuple(self.picker.GetPickPosition())
        self._drag_start = self._pick_position
        self.state = state
        self._highlight(True)
        self._abort(event)
        self._on_start(state)
        self.interactor.Render()

    def _on_mouse_move(self, _interactor, event):
        if self.state is None:
            return
        position = self.interactor.GetEventPosition()
        point = self._event_world_point(position)
        if point is None:
            return

        if self.state == PUSHING:
            motion = tuple(p - s for p, s in zip(point, self._drag_start, strict=True))
            self._on_push(_dot(motion, self._normal))
        elif self.state == ROTATING:
            normal = self._rotated_normal(position, point)
            if normal is not None:
                self._on_rotate(normal)
        elif self.state == MOVING:
            center = self._point_on_plane(position)
            if center is not None:
                self._on_move(center)

        self._abort(event)
        self.interactor.Render()

    def _on_release(self, _interactor, event):
        if self.state is None:
            return
        self.state = None
        self._highlight(False)
        self._abort(event)
        self._on_end()
        self.interactor.Render()

    def _highlight(self, on):
        prop = self.selected_property if on else self.property
        for actor in self.props:
            actor.SetProperty(prop)

    # ---- motions -----------------------------------------------------------

    def _rotated_normal(self, position, point):
        """The desktop's rotation: about the axis perpendicular to both the
        view direction and the mouse motion, by an angle proportional to the
        motion's share of the viewport diagonal."""
        last_position = self.interactor.GetLastEventPosition()
        last_point = self._event_world_point(last_position)
        if last_point is None:
            return None
        motion = tuple(p - q for p, q in zip(point, last_point, strict=True))
        view_plane_normal = self.renderer.GetActiveCamera().GetViewPlaneNormal()
        axis = _cross(view_plane_normal, motion)
        if math.sqrt(_dot(axis, axis)) == 0:
            return None
        width, height = self.renderer.GetSize()
        pixels = math.dist(position, last_position)
        theta = 360.0 * pixels / math.hypot(width, height)
        transform = vtkTransform()
        transform.RotateWXYZ(theta, *_normalized(axis))
        return tuple(transform.TransformNormal(self._normal))

    def _point_on_plane(self, position):
        """Where the ray under the cursor meets the plane, if it does."""
        near = self._display_to_world(position[0], position[1], 0.0)
        far = self._display_to_world(position[0], position[1], 1.0)
        if near is None or far is None:
            return None
        direction = tuple(f - n for f, n in zip(far, near, strict=True))
        denominator = _dot(direction, self._normal)
        if abs(denominator) < 1e-12:
            return None
        offset = tuple(c - n for c, n in zip(self._center, near, strict=True))
        t = _dot(offset, self._normal) / denominator
        if not 0.0 <= t <= 1.0:
            return None
        return tuple(n + t * d for n, d in zip(near, direction, strict=True))
