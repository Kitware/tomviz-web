"""An offscreen VTK render window with the camera and interaction API the
UI and state files need."""

from __future__ import annotations

import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
from vtkmodules.vtkInteractionStyle import (
    vtkInteractorStyleImage,
    vtkInteractorStyleTrackballCamera,
)
from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget
from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
from vtkmodules.vtkRenderingCore import (
    vtkRenderer,
    vtkRenderWindow,
    vtkRenderWindowInteractor,
)

DEFAULT_BACKGROUND = (0.8, 0.8, 0.8)

# Camera directions for the "look along an axis" buttons (ParaView's
# +X/+Y/+Z resets: the camera sits on the positive axis looking at the data).
AXIS_VIEWS = {
    "x": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "y": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "z": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    "isometric": ((1.0, 1.0, 1.0), (0.0, 0.0, 1.0)),
}


class View:
    ID = 0

    def __init__(self):
        View.ID += 1
        self._id = f"{View.ID}"
        self._interaction_mode = "3D"
        self._representations = set()

        self.renderer = vtkRenderer(background=DEFAULT_BACKGROUND)
        self.interactor = vtkRenderWindowInteractor()
        self.render_window = vtkRenderWindow(off_screen_rendering=1)

        self.render_window.AddRenderer(self.renderer)
        self.interactor.SetRenderWindow(self.render_window)
        self._style_3d = vtkInteractorStyleTrackballCamera()
        self._style_2d = vtkInteractorStyleImage()
        self._style_2d.SetInteractionModeToImage2D()
        self.interactor.SetInteractorStyle(self._style_3d)

        self.interactor.Initialize()

        axes_actor = vtkAxesActor()
        self.orientation_marker_widget = vtkOrientationMarkerWidget()
        self.orientation_marker_widget.SetOrientationMarker(axes_actor)
        self.orientation_marker_widget.SetInteractor(self.interactor)
        self.orientation_marker_widget.SetViewport(0.85, 0, 1, 0.15)
        self.orientation_marker_widget.EnabledOn()
        self.orientation_marker_widget.InteractiveOff()

        # ParaView-style "center axes": a small axes actor at the center of
        # rotation, hidden by default.
        self.center_axes = vtkAxesActor()
        self.center_axes.AxisLabelsOff()
        self.center_axes.SetVisibility(False)
        self.renderer.AddViewProp(self.center_axes)

    @property
    def id(self):
        return self._id

    # ---- camera ------------------------------------------------------------

    @property
    def camera(self) -> dict:
        """The active camera as a plain dict (state-file vocabulary)."""
        camera = self.renderer.GetActiveCamera()
        return {
            "position": list(camera.GetPosition()),
            "focalPoint": list(camera.GetFocalPoint()),
            "viewUp": list(camera.GetViewUp()),
            "viewAngle": camera.GetViewAngle(),
            "parallelScale": camera.GetParallelScale(),
            "parallelProjection": bool(camera.GetParallelProjection()),
        }

    def set_camera(
        self,
        position=None,
        focal_point=None,
        view_up=None,
        view_angle=None,
        parallel_scale=None,
        parallel_projection=None,
    ):
        """Set any subset of the active camera's parameters."""
        camera = self.renderer.GetActiveCamera()
        if position is not None:
            camera.SetPosition(*position)
        if focal_point is not None:
            camera.SetFocalPoint(*focal_point)
        if view_up is not None:
            camera.SetViewUp(*view_up)
        if view_angle is not None:
            camera.SetViewAngle(view_angle)
        if parallel_scale is not None:
            camera.SetParallelScale(parallel_scale)
        if parallel_projection is not None:
            camera.SetParallelProjection(bool(parallel_projection))
        self.renderer.ResetCameraClippingRange()
        self._place_center_axes()

    def reset_camera(self):
        self.renderer.ResetCamera()
        self._place_center_axes()

    def adjust_roll(self, angle):
        self.renderer.GetActiveCamera().Roll(angle)

    def look_along(self, axis: str):
        """Move the camera onto one of ``AXIS_VIEWS`` and refit the data."""
        direction, view_up = AXIS_VIEWS[axis]
        camera = self.renderer.GetActiveCamera()
        focal_point = camera.GetFocalPoint()
        distance = camera.GetDistance()
        camera.SetPosition(
            *(f + d * distance for f, d in zip(focal_point, direction, strict=False))
        )
        camera.SetViewUp(*view_up)
        self.reset_camera()

    def apply_isometric_view(self):
        self.look_along("isometric")

    def reset_active_camera_to_positive_x(self):
        self.look_along("x")

    def reset_active_camera_to_positive_y(self):
        self.look_along("y")

    def reset_active_camera_to_positive_z(self):
        self.look_along("z")

    # ---- view settings -----------------------------------------------------

    @property
    def background(self) -> tuple[float, float, float]:
        return tuple(self.renderer.GetBackground())

    @background.setter
    def background(self, color):
        self.renderer.SetBackground(*color)

    @property
    def interaction_mode(self):
        return self._interaction_mode

    @interaction_mode.setter
    def interaction_mode(self, mode):
        """``"3D"``: trackball camera. ``"2D"``: VTK's image style in its
        2D mode plus a parallel projection, so the data cannot be rotated."""
        self._interaction_mode = mode
        two_d = mode == "2D"
        self.interactor.SetInteractorStyle(self._style_2d if two_d else self._style_3d)
        self.renderer.GetActiveCamera().SetParallelProjection(two_d)

    @property
    def orientation_axes_visibility(self):
        return bool(self.orientation_marker_widget.GetEnabled())

    @orientation_axes_visibility.setter
    def orientation_axes_visibility(self, on_off):
        self.orientation_marker_widget.SetEnabled(bool(on_off))

    @property
    def center_axes_visibility(self):
        return bool(self.center_axes.GetVisibility())

    @center_axes_visibility.setter
    def center_axes_visibility(self, on_off):
        self.center_axes.SetVisibility(bool(on_off))
        if on_off:
            self._place_center_axes()

    def _place_center_axes(self):
        """Keep the center axes at the focal point, sized to the scene."""
        if not self.center_axes.GetVisibility():
            return
        camera = self.renderer.GetActiveCamera()
        self.center_axes.SetPosition(*camera.GetFocalPoint())
        bounds = self.renderer.ComputeVisiblePropBounds()
        extent = max(
            bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4]
        )
        size = extent * 0.25 if extent > 0 else 1.0
        self.center_axes.SetTotalLength(size, size, size)

    # ---- representations ---------------------------------------------------

    @property
    def representations(self):
        return list(self._representations)

    def add_representation(self, representation):
        if representation not in self._representations:
            self._representations.add(representation)
            self.renderer.AddViewProp(representation.actor)

    def remove_representation(self, representation):
        if representation in self._representations:
            self._representations.discard(representation)
            self.renderer.RemoveViewProp(representation.actor)

    def clear(self):
        for rep in list(self._representations):
            self.remove_representation(rep)

    def finalize(self):
        """Release the offscreen GL context; the view is not usable after."""
        self.clear()
        self.orientation_marker_widget.SetEnabled(False)
        self.render_window.Finalize()
