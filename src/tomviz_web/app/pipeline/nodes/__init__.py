"""Node types the application adds on top of the tomviz_pipeline built-ins."""

from tomviz_pipeline import NodeFactory
from tomviz_pipeline.nodes import register_builtins

from .reader import SUPPORTED_EXTENSIONS, ReaderSourceNode
from .sinks import INPUT_PORT, RepresentationSinkNode
from .transforms import build_transform_node


def register_nodes():
    """Populate the tomviz_pipeline ``NodeFactory``: the library's built-in
    types first, then the application's overrides. Idempotent.

    Representation sinks are not registered yet. ``NodeFactory`` builds nodes
    from a bare type string, while a sink needs a view and a data node model;
    wiring that up is part of loading state files, which does not exist yet.
    """
    register_builtins()
    NodeFactory.register(ReaderSourceNode.type_name, ReaderSourceNode)


__all__ = [
    "INPUT_PORT",
    "SUPPORTED_EXTENSIONS",
    "ReaderSourceNode",
    "RepresentationSinkNode",
    "build_transform_node",
    "register_nodes",
]
