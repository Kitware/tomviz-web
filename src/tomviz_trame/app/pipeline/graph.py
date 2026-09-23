"""Graph helpers the manager's editing policy is built on: where new nodes
attach (the *tip* output port), which port carries the data behind a sink
group's passthrough, and port type compatibility. Pure functions on
``tomviz_pipeline`` objects, mirroring the desktop's ``PipelineUtils``."""

from __future__ import annotations

from collections.abc import Iterable

from tomviz_pipeline import (
    InputPort,
    Node,
    OutputPort,
    PassthroughOutputPort,
    Pipeline,
    SinkGroupNode,
    SinkNode,
    SourceNode,
    TransformNode,
    is_port_type_compatible,
)

from tomviz_trame.app.utils.data import IMAGE_PORT_TYPES

__all__ = [
    "compatible_output",
    "data_port_of",
    "find_branch_tip",
    "find_tip_output_port",
    "group_output_for",
    "is_data_node",
    "is_port_type_compatible",
    "is_terminal",
    "passthrough_type",
    "primary_upstream",
]


def is_terminal(node: Node) -> bool:
    """Sinks and sink groups: nodes that produce no data of their own."""
    return isinstance(node, SinkNode | SinkGroupNode)


def is_data_node(node: Node) -> bool:
    return isinstance(node, SourceNode | TransformNode)


def compatible_output(node: Node, input_port: InputPort) -> OutputPort | None:
    """The first output of ``node`` that may feed ``input_port``."""
    for port in node.output_ports():
        if is_port_type_compatible(port.port_type, input_port.accepted_types):
            return port
    return None


def data_port_of(port: OutputPort | None) -> OutputPort | None:
    """The port that owns the data ``port`` carries: ``port`` itself, or the
    source of a passthrough (through nested groups). None when a passthrough
    is disconnected."""
    seen = 0
    while isinstance(port, PassthroughOutputPort):
        port = port.source
        seen += 1
        if seen > 100:  # a cycle cannot exist, but never loop forever
            return None
    return port


def primary_upstream(node: Node) -> OutputPort | None:
    """The output port feeding ``node``'s first linked input, or None."""
    for port in node.input_ports():
        if port.link is not None:
            return port.link.from_port
    return None


def find_branch_tip(node: Node | None) -> OutputPort | None:
    """The end of ``node``'s branch: from a sink or group, step upstream to
    the node feeding it; then follow transforms downstream (sink groups are
    terminal) and return the first output of the last one."""
    if node is None:
        return None

    start = node
    while is_terminal(start):
        upstream = start.upstream_nodes()
        if not upstream:
            return None
        start = upstream[0]

    outputs = start.output_ports()
    if not outputs:
        return None
    tip = outputs[0]

    current = start
    while True:
        next_transform = None
        for downstream in current.downstream_nodes():
            if isinstance(downstream, SinkGroupNode):
                continue
            if isinstance(downstream, TransformNode):
                next_transform = downstream
                break
        if next_transform is None or not next_transform.output_ports():
            return tip
        tip = next_transform.output_ports()[0]
        current = next_transform


def find_tip_output_port(
    pipeline: Pipeline, context: Node | None = None
) -> OutputPort | None:
    """The output port new nodes attach to: the branch tip of ``context``
    when it is in the graph, else the first source's."""
    if context is not None and any(n is context for n in pipeline.nodes):
        tip = find_branch_tip(context)
        if tip is not None:
            return tip
    for node in pipeline.nodes:
        if isinstance(node, SourceNode):
            return find_branch_tip(node)
    return None


def group_output_for(
    target: OutputPort, accepted_types: Iterable[str]
) -> OutputPort | None:
    """The passthrough port a new sink reading ``target`` should link to:
    ``target`` itself when it belongs to a group, else the matching output
    of a group already linked to ``target`` that accepts the sink. None
    when a group has to be created."""
    if isinstance(target.node, SinkGroupNode):
        return target
    for link in target.outgoing_links:
        group = link.to_port.node
        if not isinstance(group, SinkGroupNode):
            continue
        output = group.passthrough_output(link.to_port)
        if output is not None and is_port_type_compatible(
            output.port_type, accepted_types
        ):
            return output
    return None


def passthrough_type(port_type: str) -> str:
    """The type a new group's passthrough is declared with: image-like
    ports widen to ``ImageData`` so every image sink can share the group."""
    return "ImageData" if port_type in IMAGE_PORT_TYPES else port_type
