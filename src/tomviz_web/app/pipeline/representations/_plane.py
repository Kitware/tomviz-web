"""A plane through the data, what the slice and the clip share.

``vtkImageResliceMapper`` draws the image on ``self.plane``, placed by the
model: an axis-aligned direction and a slice index (-1 for the middle one)
put it on a voxel plane, a Custom direction takes any center and normal.
``SlicePlaneWidget`` gives it the desktop's handles: drag the plane to push
it along its normal, the arrow to tilt it, the center to slide it; tilting
or sliding an axis-aligned plane makes it Custom where it is.

``normal_sign`` flips an axis-aligned plane's normal (the clip's Invert);
a Custom plane's normal is used as given.
"""

from __future__ import annotations

import math

from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkRenderingCore import vtkImageProperty, vtkImageSlice
from vtkmodules.vtkRenderingImage import vtkImageResliceMapper

from tomviz_web.app.pipeline.representations.core import Representation
from tomviz_web.app.pipeline.vtk.slice_widget import (
    MOVING,
    ROTATING,
    SlicePlaneWidget,
)

CUSTOM = "Custom"

# Axis index for each axis-aligned direction
AXIS_BY_DIRECTION = {
    "YZ Plane": 0,
    "XZ Plane": 1,
    "XY Plane": 2,
}


class PlaneRepresentation(Representation):
    def __init__(self, server, view):
        super().__init__(server)

        self._slice = -1  # the middle slice once the extent is known
        self._slice_direction = "XY Plane"
        self._custom_center = None  # the data center until set
        self._custom_normal = (0.0, 0.0, 1.0)
        self.normal_sign = 1.0
        self._visible = False
        self._show_arrow = True
        self._drag_origin = None

        self.plane = vtkPlane()
        self.mapper = vtkImageResliceMapper()
        # The model owns the plane: never follow the camera or its focal point.
        self.mapper.SliceFacesCameraOff()
        self.mapper.SliceAtFocalPointOff()
        self.mapper.SetSlicePlane(self.plane)
        self.property = vtkImageProperty()
        self.actor = vtkImageSlice(mapper=self.mapper, property=self.property)
        self.producer >> self.mapper

        vtk_view = view.vtk_view
        self.widget = SlicePlaneWidget(
            vtk_view.interactor,
            vtk_view.renderer,
            self.actor,
            on_start=self._on_drag_start,
            on_push=self._on_push,
            on_rotate=self._on_rotate,
            on_move=self._on_move,
            on_end=self._on_drag_end,
        )

    @property
    def props(self):
        return (self.actor, *self.widget.props)

    def set_visible(self, visible: bool):
        self._visible = bool(visible)
        self.actor.visibility = self._visible and self.plane_shown
        self._update_widget_visibility()

    @property
    def plane_shown(self) -> bool:
        """Whether the plane is drawn while the sink is visible."""
        return True

    @property
    def handles_shown(self) -> bool:
        return self._visible and self._show_arrow

    def _update_widget_visibility(self):
        self.widget.interactive = self.handles_shown
        self.widget.set_visible(self.handles_shown)

    def detach(self, view):
        super().detach(view)
        self.widget.finalize()

    def set_input(self, image, prepared=None):
        super().set_input(image, prepared)
        self._update_plane()

    @property
    def ShowArrow(self) -> bool:
        return self._show_arrow

    @ShowArrow.setter
    def ShowArrow(self, value):
        """The handles show and respond only with the arrow on."""
        self._show_arrow = bool(value)
        self._update_widget_visibility()

    # ---- plane -------------------------------------------------------------

    @property
    def is_ortho(self) -> bool:
        return self.axis is not None

    @property
    def Slice(self):
        return self._slice

    @Slice.setter
    def Slice(self, value):
        self._slice = int(value)
        self._update_plane()

    @property
    def SliceDirection(self):
        return self._slice_direction

    @SliceDirection.setter
    def SliceDirection(self, value):
        self._slice_direction = value
        self._update_plane()

    @property
    def PlaneCenter(self):
        return tuple(self.plane.GetOrigin())

    @PlaneCenter.setter
    def PlaneCenter(self, center):
        """Where a Custom plane goes through (axis-aligned ones ignore it)."""
        self._custom_center = tuple(float(c) for c in center)
        self._update_plane()

    @property
    def PlaneNormal(self):
        return tuple(self.plane.GetNormal())

    @PlaneNormal.setter
    def PlaneNormal(self, normal):
        """A Custom plane's normal, kept unit length as the desktop's plane
        source does (axis-aligned planes ignore it)."""
        length = math.sqrt(sum(float(c) ** 2 for c in normal))
        if length > 0:
            self._custom_normal = tuple(float(c) / length for c in normal)
            self._update_plane()

    @property
    def axis(self) -> int | None:
        """The axis an axis-aligned plane is normal to; None when Custom."""
        return AXIS_BY_DIRECTION.get(self._slice_direction)

    def slice_count(self) -> int:
        """Slices along the axis; 0 without data or when Custom."""
        image, axis = self.image, self.axis
        if image is None or axis is None:
            return 0
        extent = image.GetExtent()
        return extent[2 * axis + 1] - extent[2 * axis] + 1

    def resolved_slice(self) -> int:
        """The slice index shown: the middle one while unset (-1), clamped
        to the extent."""
        count = self.slice_count()
        if count == 0:
            return self._slice
        if self._slice < 0:
            return count // 2
        return min(self._slice, count - 1)

    def _update_plane(self):
        image = self.image
        if image is None:
            return

        if self.is_ortho:
            axis = self.axis
            self._slice = self.resolved_slice()
            extent = image.GetExtent()
            origin = list(image.GetCenter())
            origin[axis] = (
                image.GetOrigin()[axis]
                + (extent[axis * 2] + self._slice) * image.GetSpacing()[axis]
            )
            normal = [0.0, 0.0, 0.0]
            normal[axis] = self.normal_sign
        else:
            origin = self._custom_center or image.GetCenter()
            normal = self._custom_normal

        self.plane.SetOrigin(*origin)
        self.plane.SetNormal(*normal)
        self._place_widget()
        self._plane_changed()

    def _plane_changed(self):
        """The plane moved (subclasses)."""

    def _place_widget(self):
        image = self.image
        bounds = image.GetBounds()
        if self.is_ortho:
            axis = self.axis
            half_diagonal = 0.5 * math.sqrt(
                sum(
                    (bounds[2 * i + 1] - bounds[2 * i]) ** 2
                    for i in range(3)
                    if i != axis
                )
            )
        else:
            half_diagonal = 0.5 * math.sqrt(
                sum((bounds[2 * i + 1] - bounds[2 * i]) ** 2 for i in range(3))
            )
        self.widget.place(self.plane.GetOrigin(), self.plane.GetNormal(), half_diagonal)

    def contains(self, point) -> bool:
        """Whether ``point`` lies within the image bounds."""
        bounds = self.image.GetBounds()
        return all(
            bounds[2 * i] - 1e-9 <= point[i] <= bounds[2 * i + 1] + 1e-9
            for i in range(3)
        )

    # ---- in-view handles ---------------------------------------------------

    def _on_drag_start(self, state):
        """Tilting or sliding asks for a plane the axis-aligned directions
        cannot express: go Custom from where the plane is (the desktop)."""
        if self.image is None:
            return
        if self.is_ortho and state in (ROTATING, MOVING):
            self._custom_center = self.PlaneCenter
            self._custom_normal = self.PlaneNormal
            self._slice_direction = CUSTOM
            self._update_plane()
            self._notify_model()
        self._drag_origin = self.PlaneCenter

    def _on_push(self, distance):
        """``distance`` along the plane's normal from where the drag began."""
        if self.image is None or self._drag_origin is None:
            return
        normal = self.PlaneNormal
        if self.is_ortho:
            axis = self.axis
            spacing = self.image.GetSpacing()[axis]
            position = self._drag_origin[axis] + distance * normal[axis]
            first = self.image.GetOrigin()[axis] + self.image.GetExtent()[2 * axis] * (
                spacing
            )
            index = round((position - first) / spacing) if spacing else 0
            index = min(max(index, 0), self.slice_count() - 1)
            if index == self._slice:
                return
            self._slice = index
        else:
            center = tuple(
                c + distance * n for c, n in zip(self._drag_origin, normal, strict=True)
            )
            if not self.contains(center):
                return
            self._custom_center = center
        self._update_plane()
        self._notify_model()

    def _on_rotate(self, normal):
        self.PlaneNormal = normal
        self._notify_model()

    def _on_move(self, center):
        if not self.contains(center):
            return
        self._custom_center = tuple(center)
        self._update_plane()
        self._notify_model()

    def _on_drag_end(self):
        self._drag_origin = None

    def _notify_model(self):
        if self.model is not None:
            self.model.pull_plane()
