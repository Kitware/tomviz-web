from __future__ import annotations

from trame_client.widgets.core import TrameComponent
from vtkmodules.vtkFiltersModeling import vtkOutlineFilter
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
)

from tomviz_web.app import data_model
from tomviz_web.app.pipelines.core import RepresentationType
from tomviz_web.app.pipelines.representations.core import RepresentationBase


class OutlineRepresentation(TrameComponent, RepresentationBase):
    def __init__(
        self,
        pipeline_manager,
        source_proxy: data_model.SourceProxy,
        view: data_model.WindowInternalState,
    ):
        view_proxy = view.vtk_view
        super().__init__(server=pipeline_manager.server)

        self.extract = vtkOutlineFilter()
        self.mapper = vtkPolyDataMapper()
        self.actor = vtkActor(mapper=self.mapper)
        source_proxy.algo.algo >> self.extract >> self.mapper
        view_proxy.add_representation(self)

        self.props = data_model.OutlineProperties(
            self.server,
            input=source_proxy,
            view=view,
            representation=self,
            **RepresentationType.OUTLINE.props,
        )


RepresentationType.OUTLINE.register_class(OutlineRepresentation)
