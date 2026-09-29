"""trame-dataclass models: the reactive mirror of the tomviz_pipeline graph
(``PipelineModel``, the ``*NodeModel`` classes, ``InputPortModel``,
``OutputPortModel`` and the ``PortDataModel`` payload mirrors) plus the
UI-only models (views, color maps, the catalog)."""

from __future__ import annotations

from trame.app.dataclass import get_instance

from .catalog import CatalogFolder, CatalogItem
from .color_opacity import ColorOpacityModel, create_color_opacity
from .color_presets import ColorMaps, ColorPreset
from .node import (
    DataNodeModel,
    NodeModel,
    SinkGroupNodeModel,
    SourceNodeModel,
    TransformNodeModel,
)
from .pipeline import PipelineModel
from .port import InputPortModel, OutputPortModel
from .port_data import (
    ImagePortDataModel,
    MoleculePortDataModel,
    PortDataModel,
    TablePortDataModel,
    port_data_model_for,
    register_port_data_model,
)
from .sinks import (
    ContourSinkNodeModel,
    OutlineSinkNodeModel,
    SinkNodeModel,
    SliceSinkNodeModel,
    ThresholdSinkNodeModel,
    VolumeSinkNodeModel,
)
from .view import ViewModel

__all__ = [
    "CatalogFolder",
    "CatalogItem",
    "ColorMaps",
    "ColorOpacityModel",
    "ColorPreset",
    "ContourSinkNodeModel",
    "DataNodeModel",
    "ImagePortDataModel",
    "InputPortModel",
    "MoleculePortDataModel",
    "NodeModel",
    "OutlineSinkNodeModel",
    "OutputPortModel",
    "PipelineModel",
    "PortDataModel",
    "SinkGroupNodeModel",
    "SinkNodeModel",
    "SliceSinkNodeModel",
    "SourceNodeModel",
    "TablePortDataModel",
    "ThresholdSinkNodeModel",
    "TransformNodeModel",
    "ViewModel",
    "VolumeSinkNodeModel",
    "create_color_opacity",
    "get_instance",
    "port_data_model_for",
    "register_port_data_model",
]
