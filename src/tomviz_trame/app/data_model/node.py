"""Mirrors of tomviz_pipeline graph nodes for the reactive UI.

One model instance exists per graph node the UI shows, and the class
hierarchy follows the library's: ``NodeModel`` mirrors ``Node``,
``SourceNodeModel`` mirrors ``SourceNode``, ``TransformNodeModel`` mirrors
``TransformNode``, ``SinkGroupNodeModel`` mirrors ``SinkGroupNode`` and
``SinkNodeModel`` (in ``sinks.py``) mirrors ``SinkNode``. ``DataNodeModel``
is the app's own intermediate base for the nodes that produce data (sources
and transforms); what the UI shows about the data itself lives on their
``OutputPortModel``s (``port.py``)."""

from __future__ import annotations

from tomviz_pipeline import Node, OutputPort
from trame.app.dataclass import ServerOnly, StateDataModel, Sync


def coerce_like(reference, value):
    """``value`` as the numeric type of ``reference``: state files store
    ``4`` for a double parameter whose field is a float."""
    if (
        isinstance(reference, float)
        and isinstance(value, int)
        and not isinstance(value, bool)
    ):
        return float(value)
    return value


class NodeModel(StateDataModel):
    """Mirror of ``tomviz_pipeline.Node``. ``node`` is the graph object; the
    synced fields copy what the UI displays about it.

    ``inputs`` and ``outputs`` mirror the node's ports with one
    ``InputPortModel`` / ``OutputPortModel`` each (created by the manager);
    an input's ``link`` is the output port model feeding it, which is how
    the pipeline widget finds the links. ``pull_state()`` refreshes the state,
    execution and progress fields from the node; the manager calls it from
    the node's signals. ``expanded`` is the widget's per-node toggle showing
    the output ports (or a group's members) as sub-cards."""

    node = ServerOnly(Node | None)
    node_id = Sync(int, -1)  # the graph id, assigned in creation order
    label = Sync(str, "")
    type_name = Sync(str, "")  # schema-v2 type string, e.g. "source.reader"
    icon = Sync(str, "")  # mdi-* name or image URL; empty: the kind's default

    state = Sync(str, "New")  # NodeState value
    exec_state = Sync(str, "Idle")  # NodeExecState value
    breakpoint = Sync(bool, False)
    at_breakpoint = Sync(bool, False)  # execution paused at this node
    progress_step = Sync(int, 0)
    progress_maximum = Sync(int, 0)
    progress_message = Sync(str, "")

    expanded = Sync(bool, False)
    inputs = Sync(list, list, has_dataclass=True)  # [InputPortModel]
    outputs = Sync(list, list, has_dataclass=True)  # [OutputPortModel]

    def pull_state(self):
        """Copy the node's identity, state and progress into the synced
        fields (event loop only)."""
        node = self.node
        if node is None:
            return
        self.node_id = node.id
        self.label = node.label
        self.state = node.state.value
        self.exec_state = node.exec_state.value
        self.breakpoint = bool(node.breakpoint)
        if node.exec_state.value == "Running" or node.state.value == "Current":
            self.at_breakpoint = False
        self.progress_step = node.progress_step()
        self.progress_maximum = node.total_progress_steps()
        self.progress_message = node.progress_message()

    def output_model(self, port: OutputPort):
        """The ``OutputPortModel`` mirroring ``port``, or None."""
        for model in self.outputs:
            if model.port is port:
                return model
        return None

    def input_model(self, port):
        """The ``InputPortModel`` mirroring ``port``, or None."""
        for model in self.inputs:
            if model.port is port:
                return model
        return None


class DataNodeModel(NodeModel):
    """A node that produces data: sources and transforms. The first output
    is the primary one sinks and downstream nodes read by default."""

    @property
    def primary_output(self) -> OutputPort | None:
        """The library port sinks and downstream nodes read from."""
        if self.node is None:
            return None
        ports = self.node.output_ports()
        return ports[0] if ports else None

    @property
    def primary_output_model(self):
        """The ``OutputPortModel`` of the primary output."""
        return self.outputs[0] if self.outputs else None

    @property
    def color_opacity(self):
        """The shared color map of the primary output."""
        port = self.primary_output_model
        return None if port is None else port.color_opacity


class SourceNodeModel(DataNodeModel):
    """Mirror of a ``SourceNode``: a file reader today."""


class TransformNodeModel(DataNodeModel):
    """Mirror of a ``TransformNode``: a catalog transform applied to
    ``input``. ``entry_name`` is the catalog entry it was built from.

    ``parameters`` mirrors ``Node.parameters``: it is the dataclass
    ``parameters_gui`` generates from the entry's JSON (one synced field per
    parameter). ``bind_parameters`` copies the node's values into it and
    watches it: edits only mark the mirror ``parameters_dirty``; the panel's
    Apply button calls ``apply_parameters``, which pushes them with
    ``set_parameters`` (re-executing the graph), and Reset calls
    ``reset_parameters``.
    """

    entry_name = Sync(str)
    input = Sync(DataNodeModel | None, None, has_dataclass=True)
    parameters = Sync(StateDataModel, has_dataclass=True)
    parameters_dirty = Sync(bool, False)  # the mirror differs from the node

    def __init__(self, server, **kwargs):
        self._parameter_names: list[str] = []
        self._unwatch_parameters = None
        super().__init__(server, **kwargs)

    def bind_parameters(self):
        """Mirror ``node.parameters`` into ``parameters`` and watch the
        mirror so edits reach the node."""
        self.unbind_parameters()
        if self.node is None or self.parameters is None:
            return

        names = [n for n in self.node.parameters if hasattr(self.parameters, n)]
        for name in names:
            current = getattr(self.parameters, name)
            setattr(
                self.parameters, name, coerce_like(current, self.node.parameters[name])
            )

        self._parameter_names = names
        if names:
            self._unwatch_parameters = self.parameters.watch(
                names, self._on_parameters_change
            )

    def unbind_parameters(self):
        if self._unwatch_parameters is not None:
            self._unwatch_parameters()
            self._unwatch_parameters = None
        self._parameter_names = []

    def _pending_parameters(self) -> dict:
        """The mirror's values that differ from the node's."""
        if self.node is None or self.parameters is None:
            return {}
        return {
            name: getattr(self.parameters, name)
            for name in self._parameter_names
            if self.node.parameter(name) != getattr(self.parameters, name)
        }

    def _on_parameters_change(self, *_values):
        # Watchers fire asynchronously, so the initial sync in
        # bind_parameters lands here too; nothing is pushed here, or typing
        # in the panel would re-execute the graph on every keystroke.
        self.parameters_dirty = bool(self._pending_parameters())

    def apply_parameters(self):
        """Push the edited parameters to the node (which re-executes the
        graph through ``auto_execute``)."""
        changed = self._pending_parameters()
        if changed:
            self.node.set_parameters(**changed)
        self.parameters_dirty = False

    def reset_parameters(self):
        """Drop the edits: copy the node's values back into the mirror."""
        if self.node is None or self.parameters is None:
            return
        for name in self._parameter_names:
            current = getattr(self.parameters, name)
            setattr(
                self.parameters, name, coerce_like(current, self.node.parameters[name])
            )
        self.parameters_dirty = False


class SinkGroupNodeModel(NodeModel):
    """Mirror of a ``SinkGroupNode``: the passthrough container between an
    output port and the sinks displaying it. Its ``outputs`` mirror the
    passthrough ports (no data, no color map of their own: sinks read the
    upstream port's through ``source_port``); the widget lists the sinks
    linked to them as the group's members."""
