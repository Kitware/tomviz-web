from __future__ import annotations

from vtkmodules.vtkFiltersModeling import vtkOutlineFilter
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
)

from tomviz_trame.app import data_model
from tomviz_trame.app.pipeline.representations.core import (
    Representation,
    RepresentationType,
)


class OutlineRepresentation(Representation):
    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server)

        self.extract = vtkOutlineFilter()
        self.mapper = vtkPolyDataMapper()
        self.actor = vtkActor(mapper=self.mapper)
        self.producer >> self.extract >> self.mapper
        self.attach(view.vtk_view)

        self.model = data_model.OutlineSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.OUTLINE.model_kwargs,
        )


RepresentationType.OUTLINE.register_class(OutlineRepresentation)
