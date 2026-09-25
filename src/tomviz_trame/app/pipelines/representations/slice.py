from __future__ import annotations

from trame_client.widgets.core import TrameComponent
from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkFiltersCore import vtkFlyingEdgesPlaneCutter
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
)

from tomviz_web.app import data_model
from tomviz_web.app.pipelines.core import RepresentationType
from tomviz_web.app.pipelines.representations.core import RepresentationBase

# Axis index for each entry of SliceProperties.SliceDirections
AXIS_BY_DIRECTION = {
    "YZ Plane": 0,
    "XZ Plane": 1,
    "XY Plane": 2,
}


class SliceRepresentation(TrameComponent, RepresentationBase):
    def __init__(
        self,
        pipeline_manager,
        source_proxy: data_model.SourceProxy,
        view: data_model.WindowInternalState,
    ):
        view_proxy = view.vtk_view
        super().__init__(server=pipeline_manager.server)

        self.source_proxy = source_proxy
        self._slice = 0
        self._slice_direction = "XY Plane"

        self.plane = vtkPlane()
        self.extract = vtkFlyingEdgesPlaneCutter(plane=self.plane)
        self.mapper = vtkPolyDataMapper()
        self.actor = vtkActor(mapper=self.mapper)
        source_proxy.algo.algo >> self.extract >> self.mapper
        view_proxy.add_representation(self)

        self._update_plane()

        self.props = data_model.SliceProperties(
            self.server,
            input=source_proxy,
            view=view,
            representation=self,
            **RepresentationType.SLICE.props,
        )

    @property
    def input_extent(self):
        dataset = self.source_proxy.algo.dataset
        if dataset is None:
            return [0, 0, 0, 0, 0, 0]

        return list(dataset.GetExtent())

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
        dataset = self.source_proxy.algo.dataset
        if dataset is None:
            return

        axis = AXIS_BY_DIRECTION[self._slice_direction]
        extent = dataset.GetExtent()
        spacing = dataset.GetSpacing()
        data_origin = dataset.GetOrigin()

        origin = list(dataset.GetCenter())
        origin[axis] = (
            data_origin[axis] + (extent[axis * 2] + self._slice) * spacing[axis]
        )

        normal = [0, 0, 0]
        normal[axis] = 1

        self.plane.origin = origin
        self.plane.normal = normal


RepresentationType.SLICE.register_class(SliceRepresentation)
