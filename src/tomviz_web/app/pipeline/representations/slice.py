"""Slice: a plane through the volume, resliced and colored per pixel.

``vtkImageResliceMapper`` samples the image on the plane
(``PlaneRepresentation``: axis-aligned or Custom, with the desktop's
handles) at screen resolution, with nearest or linear interpolation, and
colors it through the lookup table on its ``vtkImageProperty``. Like every
image mapper it displays the image's *active* scalars, so the displayed
array is selected by making it active on this sink's own ``vtkImageData``
(each sink converts its own copy, see ``RepresentationSinkNode.consume``),
the way the desktop's slice does with its active scalars producer.

As on the desktop, a thick slice combines several slices along the normal
(minimum, maximum, mean or sum; the mapper's slab), the slice can be
translucent, and "map scalars" off shows the raw values in gray instead of
through the color map. Clips of its group cut it.
"""

from __future__ import annotations

import math

from vtkmodules.vtkCommonCore import VTK_DOUBLE, VTK_FLOAT

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.representations._plane import PlaneRepresentation
from tomviz_web.app.pipeline.representations.core import (
    RepresentationType,
    set_mapper_clipping_planes,
)

# The desktop's aggregation names, in vtkImageResliceMapper's SlabType order
THICK_SLICE_MODES = ("Minimum", "Maximum", "Mean", "Summation")


def slab_step(normal, spacing) -> float:
    """The distance between samples along ``normal`` that the reslice
    mapper uses for a slab: the input spacing weighted by the normal."""
    x, y, z = normal
    length = math.sqrt(x * x + y * y + z * z) or 1.0
    return (x * x * spacing[0] + y * y * spacing[1] + z * z * spacing[2]) / length


class SliceRepresentation(PlaneRepresentation):
    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server, view)

        self._slice_thickness = 1
        self._map_scalars = True
        self._lut = None
        self.property.SetInterpolationTypeToNearest()  # the desktop's default
        self.attach(view.vtk_view)

        self.model = data_model.SliceSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.SLICE.model_kwargs,
        )

    def set_input(self, image, prepared=None):
        super().set_input(image, prepared)
        self._apply_color_array()
        self._apply_map_scalars()

    def set_clipping_planes(self, planes) -> bool:
        """Be cut by ``planes`` (the clips of its group). True if changed."""
        return set_mapper_clipping_planes(self.mapper, planes)

    def _plane_changed(self):
        self._update_slab()

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


RepresentationType.SLICE.register_class(SliceRepresentation)
