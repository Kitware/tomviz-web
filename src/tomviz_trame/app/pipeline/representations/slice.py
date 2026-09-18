"""Slice: a plane through the volume, resliced and colored per pixel.

``vtkImageResliceMapper`` samples the image on an arbitrary ``vtkPlane`` at
screen resolution, with nearest or linear interpolation, and colors it
through the lookup table on its ``vtkImageProperty``. The model drives the
plane: an axis-aligned direction and slice index place it on a voxel plane;
a custom origin and normal work the same way. Like every image mapper it
displays the image's *active* scalars, so the displayed array is selected by
making it active on this sink's own ``vtkImageData`` (each sink converts its
own copy, see ``RepresentationSinkNode.consume``), the way the desktop's
slice does with its active scalars producer.
"""

from __future__ import annotations

from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkRenderingCore import vtkImageProperty, vtkImageSlice
from vtkmodules.vtkRenderingImage import vtkImageResliceMapper

from tomviz_trame.app import data_model
from tomviz_trame.app.pipeline.representations.core import (
    Representation,
    RepresentationType,
)

# Axis index for each entry of SliceSinkNodeModel.SliceDirections
AXIS_BY_DIRECTION = {
    "YZ Plane": 0,
    "XZ Plane": 1,
    "XY Plane": 2,
}


class SliceRepresentation(Representation):
    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server)

        self._slice = 0
        self._slice_direction = "XY Plane"

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
        self.attach(view.vtk_view)

        self.model = data_model.SliceSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.SLICE.model_kwargs,
        )

    def set_input(self, image):
        super().set_input(image)
        self._apply_color_array()
        self._update_plane()

    def use_lut(self, lut):
        if lut is None:
            return

        self.property.SetLookupTable(lut.table)
        self.property.UseLookupTableScalarRangeOn()

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
    def ColorArrayName(self):
        return getattr(self, "_color_array_name", (None, None))

    @ColorArrayName.setter
    def ColorArrayName(self, value):
        self._color_array_name = value
        self._apply_color_array()

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

    @property
    def Slice(self):
        return self._slice

    @Slice.setter
    def Slice(self, value):
        self._slice = value
        self._update_plane()

    @property
    def SliceDirection(self):
        return self._slice_direction

    @SliceDirection.setter
    def SliceDirection(self, value):
        self._slice_direction = value
        self._update_plane()

    def _update_plane(self):
        image = self.image
        if image is None:
            return

        axis = AXIS_BY_DIRECTION[self._slice_direction]
        extent = image.GetExtent()
        spacing = image.GetSpacing()
        data_origin = image.GetOrigin()

        origin = list(image.GetCenter())
        origin[axis] = (
            data_origin[axis] + (extent[axis * 2] + self._slice) * spacing[axis]
        )

        normal = [0, 0, 0]
        normal[axis] = 1

        self.plane.origin = origin
        self.plane.normal = normal


RepresentationType.SLICE.register_class(SliceRepresentation)
