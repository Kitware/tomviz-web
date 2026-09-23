"""``PipelineWidget``: the tomviz pipeline strip (``tomviz-pipeline-widget``
in ``vue-components/src/components/PipelineWidget.vue``)."""

from __future__ import annotations

from loguru import logger
from trame_client.widgets.core import AbstractElement

from . import module


class HtmlElement(AbstractElement):
    def __init__(self, _elem_name, children=None, **kwargs):
        super().__init__(_elem_name, children, **kwargs)
        if self.server:
            if not module.is_built():
                logger.error(
                    "The tomviz widgets bundle is missing: run `npm install && "
                    "npm run build` in vue-components/"
                )
            self.server.enable_module(module)


class PipelineWidget(HtmlElement):
    """The pipeline graph as a vertical strip of node cards.

    Properties:

    - ``nodes``: the ``NodeModel`` instances to draw, a list of dataclass
      objects (``pipeline.nodes`` under a ``PipelineModel`` provider).
    - ``active_node``: the selection, a list holding the id of a node model,
      an output port model, or an input port model (a link).
    - ``tip_port``: the id of the output port model new nodes attach to,
      drawn with a red ring.
    - ``locked``: suppresses deletions, double clicks and link dragging
      (while executing).
    - ``dimming`` / ``dim_level``: focus mode, fading everything more than one
      hop from the selection.
    - ``animate_links_on_hover`` / ``animate_links_on_selection``: marching
      ants along the hovered / selected link.

    Events, each with the widget's payload as ``$event``:

    - ``update_active_node``: a new ``active_node`` list.
    - ``toggle_expanded`` / ``toggle_visibility`` / ``toggle_breakpoint``: the
      node model whose ``expanded`` / ``Visibility`` / breakpoint should flip.
    - ``dblclick``: the node model double clicked.
    - ``contextmenu``: ``{kind, id, node, x, y}`` with ``kind`` one of
      ``node``, ``port``, ``link``, ``id`` the model id and ``x``/``y`` the
      client coordinates to show a menu at.
    - ``delete``: ``{kind, id}``, the selection the Delete key was pressed on.
    - ``link_request``: ``{output, input}``, the output and input port models
      a drag asks to link.
    - ``leave_group``: the sink model whose leave button was clicked.
    """

    def __init__(self, **kwargs):
        super().__init__("tomviz-pipeline-widget", **kwargs)
        self._attr_names += [
            "nodes",
            ("active_node", "activeNode"),
            ("tip_port", "tipPort"),
            "locked",
            "dimming",
            ("dim_level", "dimLevel"),
            ("animate_links_on_hover", "animateLinksOnHover"),
            ("animate_links_on_selection", "animateLinksOnSelection"),
        ]
        self._event_names += [
            ("update_active_node", "update:activeNode"),
            ("toggle_expanded", "toggle-expanded"),
            ("toggle_visibility", "toggle-visibility"),
            ("toggle_breakpoint", "toggle-breakpoint"),
            ("link_request", "link-request"),
            ("leave_group", "leave-group"),
            "dblclick",
            "contextmenu",
            "delete",
        ]
