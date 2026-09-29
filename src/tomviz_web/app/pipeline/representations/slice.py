"""Slice: a plane through the volume, resliced and colored per pixel.

``vtkImageResliceMapper`` samples the image on an arbitrary ``vtkPlane`` at
screen resolution, with nearest or linear interpolation, and colors it
through the lookup table on its ``vtkImageProperty``. The model drives the
plane: an axis-aligned direction and slice index place it on a voxel plane;
a Custom direction takes any center and normal. Like every image mapper it
displays the image's *active* scalars, so the displayed array is selected by
making it active on this sink's own ``vtkImageData`` (each sink converts its
own copy, see ``RepresentationSinkNode.consume``), the way the desktop's
slice does with its active scalars producer.

As on the desktop, a thick slice combines several slices along the normal
(minimum, maximum, mean or sum; the mapper's slab), the slice can be
translucent, and "map scalars" off shows the raw values in gray instead of
through the color map. ``SlicePlaneWidget`` provides the desktop's handles
in the view: push the slice, tilt it by its arrow, slide it by its center.
"""

from __future__ import annotations

import math

from vtkmodules.vtkCommonCore import VTK_DOUBLE, VTK_FLOAT
from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkRenderingCore import vtkImageProperty, vtkImageSlice
from vtkmodules.vtkRenderingImage import vtkImageResliceMapper

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.representations.core import (
    Representation,
    RepresentationType,
)
from tomviz_web.app.pipeline.vtk.slice_widget import (
    MOVING,
    ROTATING,
    SlicePlaneWidget,
)

CUSTOM = "Custom"

# Axis index for each axis-aligned entry of SliceSinkNodeModel.SliceDirections
AXIS_BY_DIRECTION = {
    "YZ Plane": 0,
    "XZ Plane": 1,
    "XY Plane": 2,
}

# The desktop's aggregation names, in vtkImageResliceMapper's SlabType order
THICK_SLICE_MODES = ("Minimum", "Maximum", "Mean", "Summation")


def slab_step(normal, spacing) -> float:
    """The distance between samples along ``normal`` that the reslice
    mapper uses for a slab: the input spacing weighted by the normal."""
    x, y, z = normal
    length = math.sqrt(x * x + y * y + z * z) or 1.0
    return (x * x * spacing[0] + y * y * spacing[1] + z * z * spacing[2]) / length


class SliceRepresentation(Representation):
    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server)

        self._slice = -1  # the middle slice once the extent is known
        self._slice_direction = "XY Plane"
        self._custom_center = None  # the data center until set
        self._custom_normal = (0.0, 0.0, 1.0)
        self._slice_thickness = 1
        self._map_scalars = True
        self._lut = None
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
        self.property.SetInterpolationTypeToNearest()  # the desktop's default
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
        self.attach(vtk_view)

        self.model = data_model.SliceSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.SLICE.model_kwargs,
        )

    @property
    def props(self):
        return (self.actor, *self.widget.props)

    def set_visible(self, visible: bool):
        self._visible = bool(visible)
        self.actor.visibility = self._visible
        self.widget.set_visible(self._visible and self._show_arrow)

    def detach(self, view):
        super().detach(view)
        self.widget.finalize()

    def set_input(self, image):
        super().set_input(image)
        self._apply_color_array()
        self._apply_map_scalars()
        self._update_plane()

    # ---- color -------------------------------------------------------------

    def use_lut(self, lut):
        if lut is None:
            return

        self._lut = lut
        self._apply_map_scalars()

    @property
    def MapScalars(self):
        return self._map_scalars

    @MapScalars.setter
    def MapScalars(self, value):
        self._map_scalars = bool(value)
        self._apply_map_scalars()

    def _apply_map_scalars(self):
        """Color through the map, or show the raw values in gray the way
        VTK's direct scalars do: [0, 255] for integers, [0, 1] for floats."""
        if self._map_scalars:
            if self._lut is not None:
                self.property.SetLookupTable(self._lut.table)
                self.property.UseLookupTableScalarRangeOn()
            return

        self.property.SetLookupTable(None)
        self.property.UseLookupTableScalarRangeOff()
        scalars = self.image.GetPointData().GetScalars() if self.image else None
        floating = scalars is not None and scalars.GetDataType() in (
            VTK_FLOAT,
            VTK_DOUBLE,
        )
        top = 1.0 if floating else 255.0
        self.property.SetColorWindow(top)
        self.property.SetColorLevel(top / 2)

    @property
    def ColorArrayName(self):
        return getattr(self, "_color_array_name", (None, None))

    @ColorArrayName.setter
    def ColorArrayName(self, value):
        self._color_array_name = value
        self._apply_color_array()
        self._apply_map_scalars()

    def _apply_color_array(self):
        """Make the displayed array the active scalars of the current image,
        the only array the mapper shows. An array the image lacks leaves the
        image's own choice in place."""
        image = self.image
        _association, name = self.ColorArrayName
        if image is None or not name:
            return
        point_data = image.GetPointData()
        scalars = point_data.GetScalars()
        if scalars is not None and scalars.GetName() == name:
            return
        if point_data.GetAbstractArray(name) is None:
            return
        point_data.SetActiveScalars(name)

    # ---- appearance ----------------------------------------------------------

    @property
    def Interpolate(self) -> bool:
        return self.property.GetInterpolationTypeAsString() != "Nearest"

    @Interpolate.setter
    def Interpolate(self, value):
        if value:
            self.property.SetInterpolationTypeToLinear()
        else:
            self.property.SetInterpolationTypeToNearest()

    @property
    def Opacity(self) -> float:
        return self.property.GetOpacity()

    @Opacity.setter
    def Opacity(self, value):
        self.property.SetOpacity(float(value))

    @property
    def SliceThickness(self) -> int:
        return self._slice_thickness

    @SliceThickness.setter
    def SliceThickness(self, value):
        self._slice_thickness = max(int(value), 1)
        self._update_slab()

    @property
    def ThickSliceMode(self) -> str:
        return THICK_SLICE_MODES[self.mapper.GetSlabType()]

    @ThickSliceMode.setter
    def ThickSliceMode(self, value):
        self.mapper.SetSlabType(THICK_SLICE_MODES.index(value))

    def _update_slab(self):
        """``SliceThickness`` slices: a slab spanning that many voxel planes
        along the normal (the desktop hands vtkImageReslice one fewer)."""
        image = self.image
        if image is None:
            return
        step = slab_step(self.plane.GetNormal(), image.GetSpacing())
        self.mapper.SetSlabThickness((self._slice_thickness - 1) * step)

    @property
    def ShowArrow(self) -> bool:
        return self._show_arrow

    @ShowArrow.setter
    def ShowArrow(self, value):
        """The handles show and respond only with the arrow on."""
        self._show_arrow = bool(value)
        self.widget.interactive = self._show_arrow
        self.widget.set_visible(self._visible and self._show_arrow)

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
        """The axis an axis-aligned slice is normal to; None when Custom."""
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
            normal[axis] = 1.0
        else:
            origin = self._custom_center or image.GetCenter()
            normal = self._custom_normal

        self.plane.SetOrigin(*origin)
        self.plane.SetNormal(*normal)
        self._update_slab()
        self._place_widget()

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
        if self.image is None or self._drag_origin is None:
            return
        if self.is_ortho:
            axis = self.axis
            spacing = self.image.GetSpacing()[axis]
            position = self._drag_origin[axis] + distance
            first = self.image.GetOrigin()[axis] + self.image.GetExtent()[2 * axis] * (
                spacing
            )
            index = round((position - first) / spacing) if spacing else 0
            index = min(max(index, 0), self.slice_count() - 1)
            if index == self._slice:
                return
            self._slice = index
        else:
            normal = self.PlaneNormal
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


RepresentationType.SLICE.register_class(SliceRepresentation)
