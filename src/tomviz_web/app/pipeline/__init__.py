"""The application's data pipeline.

The graph itself (nodes, links, planning, execution) comes from the
``tomviz_pipeline`` library. This package adds the application-specific
pieces: the node types that read files through VTK and display data in
render views (``nodes``), the VTK rendering pipelines those sinks drive
(``representations``), the VTK helpers they share (``vtk``), and the
``PipelineManager`` that owns the graph and mirrors it into the trame data
model."""

from .manager import PipelineManager
from .representations import RepresentationType

__all__ = [
    "PipelineManager",
    "RepresentationType",
]
