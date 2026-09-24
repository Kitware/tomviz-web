from __future__ import annotations

from tomviz_pipeline import Node, Pipeline
from trame.app.dataclass import ServerOnly, StateDataModel, Sync

from .node import NodeModel


class PipelineModel(StateDataModel):
    """Mirror of ``tomviz_pipeline.Pipeline`` for the reactive UI.

    ``nodes`` lists one ``NodeModel`` per graph node, like ``Pipeline.nodes``.
    ``roots`` is the ``Pipeline.roots()`` subset (nodes with no linked input)
    the drawer starts its tree from. ``active_node`` holds the id of the
    selected model (a list, as the Vuetify activation model wants).
    """

    pipeline = ServerOnly(Pipeline | None)
    nodes = Sync(list[NodeModel], list, has_dataclass=True)
    roots = Sync(list[NodeModel], list, has_dataclass=True)
    active_node = Sync(list[str], list)

    def add(self, model: NodeModel):
        self.nodes = [*self.nodes, model]
        self.refresh_roots()

    def remove(self, model: NodeModel):
        self.nodes = [m for m in self.nodes if m is not model]
        self.refresh_roots()

    def refresh_roots(self):
        """Recompute ``roots`` after nodes or links changed."""
        self.roots = [m for m in self.nodes if m.node is not None and is_root(m.node)]


def is_root(node: Node) -> bool:
    return not any(port.link is not None for port in node.input_ports())
