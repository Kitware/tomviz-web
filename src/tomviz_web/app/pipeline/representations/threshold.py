"""Threshold: the voxels whose value lies in a range, after the desktop's
ThresholdSink.

A voxel is a cell, not a point: thresholding the point-centered image
would keep a hexahedron only when all eight voxels around it pass, erasing
thin features and isolated voxels. So, as on the desktop, the image is
rebuilt one cell per voxel (sharing the arrays) and ``vtkThreshold`` keeps
exactly the voxels in range; the outer faces of what it keeps are drawn,
colored per voxel by the color map's array. A new threshold starts at the
brightest voxels (``threshold_seed``, computed on the worker) up to the
maximum. Desktop defaults: surface mode, no specular.
"""

from __future__ import annotations

import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkCommonDataModel import vtkDataObject, vtkImageData
from vtkmodules.vtkCommonExecutionModel import vtkTrivialProducer
from vtkmodules.vtkFiltersCore import vtkThreshold
from vtkmodules.vtkFiltersGeometry import vtkDataSetSurfaceFilter

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.representations._surface import SurfaceRepresentation
from tomviz_web.app.pipeline.representations.core import RepresentationType
from tomviz_web.app.utils.data import threshold_seed


def cell_centered(image: vtkImageData) -> vtkImageData:
    """``image`` rebuilt with one cell per voxel, its point arrays becoming
    cell arrays (shared, not copied)."""
    cells = vtkImageData()
    nx, ny, nz = image.GetDimensions()
    cells.SetDimensions(nx + 1, ny + 1, nz + 1)
    cells.SetSpacing(image.GetSpacing())
    cells.SetDirectionMatrix(image.GetDirectionMatrix())
    # Half a voxel back along the image's own axes: cell centers on voxels
    origin = [0.0, 0.0, 0.0]
    image.TransformContinuousIndexToPhysicalPoint(-0.5, -0.5, -0.5, origin)
    cells.SetOrigin(origin)
    point_data, cell_data = image.GetPointData(), cells.GetCellData()
    for i in range(point_data.GetNumberOfArrays()):
        cell_data.AddArray(point_data.GetAbstractArray(i))
    scalars = point_data.GetScalars()
    if scalars is not None:
        cell_data.SetActiveScalars(scalars.GetName())
    return cells


class ThresholdRepresentation(SurfaceRepresentation):
    ASSOCIATION = "CELLS"

    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server)

        # The array thresholded: "" for the image's active one (an index
        # from a desktop state file until data arrives)
        self._threshold_by: str | int = ""
        # None until data: the seed and the maximum
        self._minimum: float | None = None
        self._maximum: float | None = None

        self.property.SetSpecular(0.0)
        self.property.SetRepresentationToSurface()

        self.cells = vtkTrivialProducer()
        self.threshold = vtkThreshold()
        self.threshold.SetThresholdFunction(vtkThreshold.THRESHOLD_BETWEEN)
        self.surface = vtkDataSetSurfaceFilter()
        self.cells >> self.threshold >> self.surface >> self.mapper
        self.attach(view.vtk_view)

        self.model = data_model.ThresholdSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.THRESHOLD.model_kwargs,
        )

    def prepare(self, image):
        """The starting range, while there is none: the seed and the
        maximum of the thresholded array."""
        if self._minimum is not None and self._maximum is not None:
            return None
        name = self.resolve_array(self._threshold_by, image)
        array = image.GetPointData().GetArray(name) if name else None
        if array is None:
            return None
        values = vtk_to_numpy(array)
        return {"seed": threshold_seed(values), "maximum": float(np.nanmax(values))}

    def set_input(self, image, prepared=None):
        super().set_input(image, prepared)
        self.cells.SetOutput(cell_centered(image))
        if prepared:
            if self._minimum is None:
                self._minimum = prepared["seed"]
            if self._maximum is None:
                self._maximum = prepared["maximum"]
        self._apply_threshold()

    @property
    def threshold_array(self) -> str:
        return self.resolve_array(self._threshold_by)

    @property
    def ThresholdBy(self):
        """The array thresholded, ``""`` for the image's active one."""
        if isinstance(self._threshold_by, int) and self.image is not None:
            self._threshold_by = self.threshold_array
        return self._threshold_by

    @ThresholdBy.setter
    def ThresholdBy(self, value):
        self._threshold_by = value if isinstance(value, int) else value or ""
        self._apply_threshold()

    @property
    def Minimum(self):
        return self._minimum

    @Minimum.setter
    def Minimum(self, value):
        """None (the model before data) keeps the value data gave."""
        if value is not None:
            self._minimum = float(value)
            self._apply_threshold()

    @property
    def Maximum(self):
        return self._maximum

    @Maximum.setter
    def Maximum(self, value):
        if value is not None:
            self._maximum = float(value)
            self._apply_threshold()

    @property
    def scalar_range(self) -> tuple[float, float]:
        return self.array_range(self.threshold_array)

    def _apply_threshold(self):
        if self.image is None:
            return
        self.threshold.SetInputArrayToProcess(
            0, 0, 0, vtkDataObject.FIELD_ASSOCIATION_CELLS, self.threshold_array
        )
        low, high = self.scalar_range
        self.threshold.SetLowerThreshold(
            low if self._minimum is None else self._minimum
        )
        self.threshold.SetUpperThreshold(
            high if self._maximum is None else self._maximum
        )
        self._update_coloring()


RepresentationType.THRESHOLD.register_class(ThresholdRepresentation)
