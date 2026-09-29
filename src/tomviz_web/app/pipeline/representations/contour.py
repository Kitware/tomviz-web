"""Contour: an isosurface of one array, after the desktop's ContourSink.

``vtkFlyingEdges3D`` extracts the surface at ``IsoValue`` of the "contour
by" array (the image's active array unless another is picked); a new
contour starts two thirds of the way up that array's range, as on the
desktop. The surface is colored by its color map's array: the contoured
one gives the single color of the iso value, any other is interpolated
onto the surface (the desktop probes it). Desktop defaults: surface mode,
no ambient, full diffuse and specular, specular power 100.
"""

from __future__ import annotations

from vtkmodules.vtkCommonDataModel import vtkDataObject
from vtkmodules.vtkFiltersCore import vtkFlyingEdges3D

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.representations._surface import SurfaceRepresentation
from tomviz_web.app.pipeline.representations.core import RepresentationType


class ContourRepresentation(SurfaceRepresentation):
    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server)

        self._contour_by = ""  # the image's active array
        self._iso_value: float | None = None  # set from the range with data

        self.property.SetAmbient(0.0)
        self.property.SetDiffuse(1.0)
        self.property.SetSpecular(1.0)
        self.property.SetSpecularPower(100.0)
        self.property.SetRepresentationToSurface()

        self.contour = vtkFlyingEdges3D()
        self.contour.ComputeScalarsOn()
        self.contour.ComputeNormalsOn()
        self.producer >> self.contour >> self.mapper
        self.attach(view.vtk_view)

        self.model = data_model.ContourSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.CONTOUR.model_kwargs,
        )

    def set_input(self, image, prepared=None):
        super().set_input(image, prepared)
        self._apply_contour()

    @property
    def contour_array(self) -> str:
        return self.resolve_array(self._contour_by)

    @property
    def ContourBy(self):
        """The array contoured, ``""`` for the image's active one."""
        return self._contour_by

    @ContourBy.setter
    def ContourBy(self, value):
        self._contour_by = value or ""
        self._apply_contour()

    @property
    def IsoValue(self):
        return self._iso_value

    @IsoValue.setter
    def IsoValue(self, value):
        """None (the model before data) keeps the value data gave."""
        if value is not None:
            self._iso_value = float(value)
            self._apply_contour()

    @property
    def iso_range(self) -> tuple[float, float]:
        return self.array_range(self.contour_array)

    def _apply_contour(self):
        if self.image is None:
            return
        name = self.contour_array
        self.contour.SetInputArrayToProcess(
            0, 0, 0, vtkDataObject.FIELD_ASSOCIATION_POINTS, name
        )
        if self._iso_value is None:
            low, high = self.iso_range
            self._iso_value = low + (high - low) * 2 / 3
        self.contour.SetValue(0, self._iso_value)
        self._update_coloring()

    def _carry_color_array(self, name: str):
        """The surface has the contoured array's (iso) values; any other
        array is interpolated onto it."""
        self.contour.SetInterpolateAttributes(name != self.contour_array)


RepresentationType.CONTOUR.register_class(ContourRepresentation)
