"""Node types the application adds on top of the tomviz_pipeline built-ins."""

from tomviz_pipeline import NodeFactory
from tomviz_pipeline.nodes import register_builtins

from tomviz_web.app.pipeline.representations import RepresentationType

from .reader import SUPPORTED_EXTENSIONS, ReaderSourceNode
from .sinks import INPUT_PORT, RepresentationSinkNode
from .sources import build_source_node
from .transforms import build_transform_node

# A type the library registers as its inert sink placeholder
INERT_SINK_TYPE = "sink.volume"


def register_nodes():
    """Populate the tomviz_pipeline ``NodeFactory``: the library's built-in
    types first, then the application's overrides. Idempotent.

    Representation sinks are not registered yet. ``NodeFactory`` builds nodes
    from a bare type string, while a sink needs a view and a data node model;
    wiring that up is part of loading state files, which does not exist yet.
    """
    register_builtins()
    NodeFactory.register(ReaderSourceNode.type_name, ReaderSourceNode)
    # Sink types the library has no placeholder for (sink.labelMap) load
    # as the same inert sink as the others.
    known = set(NodeFactory.known_types())
    for representation_type in RepresentationType:
        if representation_type.sink_type not in known:
            NodeFactory.register(representation_type.sink_type, _inert_sink)


def _inert_sink():
    return NodeFactory.create(INERT_SINK_TYPE)


__all__ = [
    "INPUT_PORT",
    "SUPPORTED_EXTENSIONS",
    "ReaderSourceNode",
    "RepresentationSinkNode",
    "build_source_node",
    "build_transform_node",
    "register_nodes",
]
