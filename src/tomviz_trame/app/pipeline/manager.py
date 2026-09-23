from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from pathlib import Path

from loguru import logger
from tomviz_pipeline import (
    AsyncioDispatcher,
    InputPort,
    Link,
    Node,
    OutputPort,
    PassthroughOutputPort,
    PersistenceMode,
    Pipeline,
    PipelineSettings,
    SinkGroupNode,
    ThreadedExecutor,
    TransformPersistenceDefault,
)
from trame.app import TrameComponent, asynchronous
from trame.decorators import change, trigger

from tomviz_trame.app import data_model
from tomviz_trame.app.parameters_gui import to_parameters_model
from tomviz_trame.app.pipeline import graph
from tomviz_trame.app.pipeline.nodes import (
    INPUT_PORT,
    ReaderSourceNode,
    RepresentationSinkNode,
    build_transform_node,
    register_nodes,
)
from tomviz_trame.app.pipeline.representations import RepresentationType
from tomviz_trame.app.pipeline.state import STATE_EXTENSIONS, load_state_file


class PipelineManager(TrameComponent):
    """Owns the tomviz_pipeline graph and mirrors it into the trame data model.

    Graph side: ``pipeline`` is a ``tomviz_pipeline.Pipeline`` run by a
    ``ThreadedExecutor``. File sources are ``ReaderSourceNode`` roots,
    catalog transforms are chained after them, and visualizations are
    ``RepresentationSinkNode`` leaves hanging off a ``SinkGroupNode`` (one
    per output port they display). Whatever the worker thread reports comes
    back through an ``AsyncioDispatcher`` or ``run_on_loop``, so every
    handler here runs on trame's event loop, the only thread allowed to
    touch trame state and VTK rendering. The one exception is
    ``_describe_outputs``, connected directly on purpose: it runs on the
    worker right after a data node, does the numpy statistics there, and
    only posts the result to the loop.

    Editing policy (desktop tomviz parity): new nodes attach to the *tip*
    output port, derived from the selection (``graph.find_tip_output_port``):
    a selected data node's first output, a selected port itself, a selected
    link's source, or the end of the branch of a selected sink; a newly added
    node is selected, so the tip advances while building. ``add_transform``
    links the tip to the transform and moves the sinks and groups reading the
    tip to the transform's output; ``add_sink`` joins the group already on
    the tip or creates one.

    UI side: ``model`` (a ``PipelineModel``) holds one ``NodeModel`` per graph
    node; ``node_models`` indexes them by node id. Every node carries one
    ``InputPortModel`` / ``OutputPortModel`` per port (an input's ``link``
    mirrors the graph's links) and its state and progress, refreshed from the
    node's signals. Data ports also carry their shared color map.
    ``state.tip_port_id`` is the tip's port model id, for the widget.
    """

    def __init__(self, server=None):
        super().__init__(server=server)
        register_nodes()

        # No executor progress reporter: kernel progress then reaches each
        # node's own progress signals (progress_step_changed, ...), which
        # the node models mirror.
        self.executor = ThreadedExecutor()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._dispatcher: AsyncioDispatcher | None = None
        self._pipeline_connections = []  # through the dispatcher
        self._graph_connections = []  # direct: graph edits happen on the loop
        self._node_connections: dict[int, list] = {}
        self.pipeline: Pipeline | None = None

        self.node_models: dict[int, data_model.NodeModel] = {}  # node.id -> model
        self.views = {}  # view_id -> ui.RenderWindow

        self.tip_port: OutputPort | None = None
        self._selected_node: Node | None = None

        self.model = data_model.PipelineModel(self.server)
        self.attach_pipeline(Pipeline())
        self.state.property_templates = []
        self.state.active_view_id = None
        self.state.active_data_id = None
        self.state.active_port_id = None
        self.state.active_representation_id = None
        self.state.active_color_opacity_id = None
        self.state.tip_port_id = None
        self.state.pipeline_executing = False
        self.state.pipeline_paused = False
        self.state.pipeline_stopping = False
        self.state.transform_persistence_default = (
            PipelineSettings.instance().transform_persistence_default.value
        )
        self._ui_color_opacity_id: str | None = None

        self.model.watch(["active_node"], self._on_active_change)

        # Direct connection: runs on the executor's thread (see class doc).
        self.executor.node_execution_finished.connect(self._describe_outputs)

        self.ctrl.on_server_ready.add(self._on_server_ready)
        self.ctrl.on_server_exited.add(self.shutdown)

        if self.server.hot_reload:
            self.ctrl.on_server_reload.add(self.refresh_views_later)

    def __del__(self):
        self.model.clear_watchers()

    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------

    def _on_server_ready(self, **_):
        self._ensure_dispatcher()

    def _ensure_dispatcher(self):
        """Bind the graph's signals to the running event loop. Deferred until
        a loop exists because trame starts it after this object is built."""
        if self._dispatcher is not None:
            return

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("No running event loop yet; pipeline signals not bound")
            return

        self._dispatcher = AsyncioDispatcher(loop=self._loop)
        self.executor.node_execution_finished.connect(
            self._on_node_finished, self._dispatcher
        )
        self._connect_pipeline_signals()

    def _connect_pipeline_signals(self):
        """Bind the current pipeline's signals through the dispatcher (the
        executor's are bound once; pipelines come and go)."""
        for connection in self._pipeline_connections:
            connection.disconnect()
        self._pipeline_connections = []
        if self._dispatcher is None or self.pipeline is None:
            return
        self._pipeline_connections = [
            self.pipeline.execution_started.connect(
                self._on_execution_started, self._dispatcher
            ),
            self.pipeline.execution_finished.connect(
                self._on_execution_finished, self._dispatcher
            ),
            self.pipeline.breakpoint_reached.connect(
                self._on_breakpoint_reached, self._dispatcher
            ),
            self.pipeline.paused_changed.connect(
                self._on_paused_changed, self._dispatcher
            ),
        ]

    def _connect_graph_signals(self):
        """Mirror link changes into the port models. Direct connections: the
        graph is only edited on the event loop."""
        for connection in self._graph_connections:
            connection.disconnect()
        self._graph_connections = []
        if self.pipeline is None:
            return
        self._graph_connections = [
            self.pipeline.link_created.connect(self._on_link_created),
            self.pipeline.link_removed.connect(self._on_link_removed),
            self.pipeline.link_validity_changed.connect(self._on_link_validity),
        ]

    def attach_pipeline(self, pipeline: Pipeline):
        """Adopt ``pipeline`` as the graph, replacing the current one. The
        models are the caller's business: ``reset()`` first to drop the old
        ones, then mirror the new graph."""
        if self.pipeline is not None:
            self.pipeline.set_executor(None)
        self.pipeline = pipeline
        pipeline.auto_execute = True
        pipeline.set_executor(self.executor)
        self.model.pipeline = pipeline
        self._connect_graph_signals()
        self._connect_pipeline_signals()

    def reset(self):
        """Back to an empty session: stop executing, drop every sink (and
        its actors), every view and every model, and empty the graph."""
        self.executor.cancel_and_wait(timeout=5)
        for sink_model in [
            m
            for m in self.node_models.values()
            if isinstance(m, data_model.SinkNodeModel)
        ]:
            self.remove_sink(sink_model.node.id)
        for view_id in list(self.views):
            self.remove_view(view_id)
        for model in list(self.node_models.values()):
            unbind = getattr(model, "unbind_parameters", None)
            if unbind is not None:
                unbind()
            self._untrack(model)
        self.model.active_node = []
        self._selected_node = None
        self.set_tip_port(None)
        self.pipeline.clear()

    def run_on_loop(self, callback: Callable[[], None]):
        """Run ``callback`` on the application's event loop from any thread.
        Without a loop (tests, blocking executors) it runs inline."""
        loop = self._loop
        if loop is None or not loop.is_running():
            callback()
        else:
            loop.call_soon_threadsafe(callback)

    def execute(self, target: Node | None = None):
        """Bring the graph (or just ``target``) up to date. Returns the
        library's ``ExecutionFuture``."""
        self._ensure_dispatcher()
        return self.pipeline.execute(target)

    def execute_when_idle(self):
        self._ensure_dispatcher()
        self.pipeline.execute_when_idle()

    def shutdown(self, **_):
        self.executor.cancel_and_wait(timeout=5)

    def _describe_outputs(self, node: Node, success: bool):
        """Worker thread, right after ``node`` ran and before the next node.
        Describes each output port (geometry plus statistics of the arrays
        some color map displays) and posts it to the loop, so the description
        is installed before the sinks' own updates arrive."""
        if not success:
            return
        model = self.node_models.get(node.id)
        if not isinstance(model, data_model.DataNodeModel):
            return

        for port_model in list(model.outputs):
            description = port_model.describe()
            if description is None:
                continue
            self.run_on_loop(
                functools.partial(port_model.apply_description, description)
            )

    def describe_ports(self, model: data_model.DataNodeModel):
        """Install the geometry of every output port that already carries
        data (a node loaded from a ``.tvh5``): nothing ran, so no
        ``_describe_outputs`` will. Statistics stay lazy."""
        for port_model in list(model.outputs):
            description = port_model.describe(requested=set())
            if description is not None:
                port_model.apply_description(description)

    def _on_node_finished(self, node: Node, success: bool):
        # Event loop, queued behind whatever the loop is doing: the node
        # itself finished on the worker some time ago.
        logger.debug("Node '{}' (id={}) finished, ok={}", node.label, node.id, success)

    def _on_execution_started(self, _future):
        logger.debug("Pipeline execution started")
        self.state.pipeline_executing = True

    def _on_execution_finished(self, future):
        logger.debug(
            "Pipeline execution finished, succeeded={} canceled={}",
            future.succeeded(),
            future.was_canceled(),
        )
        self.state.pipeline_executing = False
        self.state.pipeline_stopping = False

    def _on_paused_changed(self, paused: bool):
        self.state.pipeline_paused = bool(paused)

    def _on_breakpoint_reached(self, node: Node):
        model = self.node_models.get(node.id)
        if model is not None:
            model.at_breakpoint = True

    # -------------------------------------------------------------------------
    # Node bookkeeping
    # -------------------------------------------------------------------------

    def _track(self, model: data_model.NodeModel):
        """Register a model whose node is already in the graph and linked:
        mirror its ports, pull its state, and follow its signals. Consumers
        tracked earlier get their ``link`` resolved now."""
        node = model.node
        if not model.outputs:
            model.outputs = [
                self._create_port_model(model, port) for port in node.output_ports()
            ]
        if not model.inputs:
            model.inputs = [
                self._create_input_model(model, port) for port in node.input_ports()
            ]
        model.pull_state()
        self._connect_node(model)
        self.node_models[node.id] = model
        self.model.add(model)

        for port_model in model.outputs:
            for link in port_model.port.outgoing_links:
                input_model = self.input_model_of(link.to_port)
                if input_model is not None and input_model.link is None:
                    input_model.link = port_model

    def _untrack(self, model: data_model.NodeModel):
        for connection in self._node_connections.pop(model.node.id, []):
            connection.disconnect()
        self.node_models.pop(model.node.id, None)
        self.model.remove(model)

    def _connect_node(self, model: data_model.NodeModel):
        """Follow the node's state, execution and progress signals, and each
        output's data location. They may fire on the worker: the models are
        refreshed on the loop."""
        node = model.node

        def refresh(*_):
            self.run_on_loop(model.pull_state)

        def refresh_types(*_):
            # Effective types (inferred from upstream, or set by a reader
            # when it runs): the port models follow.
            def apply():
                for port_model in model.outputs:
                    if port_model.port is not None:
                        port_model.port_type = port_model.port.port_type

            self.run_on_loop(apply)

        connections = [
            node.state_changed.connect(refresh),
            node.exec_state_changed.connect(refresh),
            node.progress_maximum_changed.connect(refresh),
            node.progress_step_changed.connect(refresh),
            node.progress_message_changed.connect(refresh),
            node.output_type_changed.connect(refresh_types),
        ]
        for port_model in model.outputs:

            def refresh_location(*_, port_model=port_model):
                self.run_on_loop(port_model.pull_location)

            connections.append(
                port_model.port.data_location_changed.connect(refresh_location)
            )
        self._node_connections[node.id] = connections

    def _create_port_model(
        self, model: data_model.NodeModel, port: OutputPort
    ) -> data_model.OutputPortModel:
        port_model = data_model.OutputPortModel(
            self.server,
            port=port,
            node=model,
            name=port.name,
            port_type=port.port_type,
        )
        # Only image data is colored through a lookup table; a passthrough
        # forwards its source's data and color map.
        if not isinstance(port, PassthroughOutputPort) and (
            data_model.port_data_model_for(port.port_type)
            is data_model.ImagePortDataModel
        ):
            color_opacity = data_model.create_color_opacity(port_model)
            # A new node's output starts from the map of the port feeding
            # it (desktop parity), stretched to its own range once it runs.
            upstream = self.port_model_of(
                graph.data_port_of(graph.primary_upstream(model.node))
            )
            if upstream is not None and upstream.color_opacity is not None:
                color_opacity.inherit_from(upstream.color_opacity)
            port_model.color_opacity = color_opacity
        return port_model

    def _create_input_model(
        self, model: data_model.NodeModel, port: InputPort
    ) -> data_model.InputPortModel:
        link = port.link
        return data_model.InputPortModel(
            self.server,
            port=port,
            node=model,
            name=port.name,
            accepted_types=list(port.accepted_types),
            link=self.port_model_of(link.from_port) if link is not None else None,
        )

    def port_model_of(
        self, port: OutputPort | None
    ) -> data_model.OutputPortModel | None:
        """The ``OutputPortModel`` mirroring ``port``, if its node is tracked."""
        if port is None or port.node is None:
            return None
        owner = self.node_models.get(port.node.id)
        return None if owner is None else owner.output_model(port)

    def input_model_of(
        self, port: InputPort | None
    ) -> data_model.InputPortModel | None:
        if port is None or port.node is None:
            return None
        owner = self.node_models.get(port.node.id)
        return None if owner is None else owner.input_model(port)

    def _on_link_created(self, link: Link):
        input_model = self.input_model_of(link.to_port)
        if input_model is not None:
            input_model.link = self.port_model_of(link.from_port)
            input_model.pull_link()
        self.model.refresh_roots()

    def _on_link_removed(self, link: Link):
        input_model = self.input_model_of(link.to_port)
        if input_model is not None:
            input_model.link = None
            input_model.link_valid = True
        self.model.refresh_roots()

    def _on_link_validity(self, link: Link, _valid: bool):
        # May fire on the worker (a reader re-typing its output mid-run).
        input_model = self.input_model_of(link.to_port)
        if input_model is not None:
            self.run_on_loop(input_model.pull_link)

    def _sink_models(self) -> list[data_model.SinkNodeModel]:
        return [
            m
            for m in self.node_models.values()
            if isinstance(m, data_model.SinkNodeModel)
        ]

    def _refresh_sink_sources(self):
        """Point every sink model at the data port now feeding it (through
        its group), after links moved; a sink left without data hides."""
        for sink_model in self._sink_models():
            data_port = graph.data_port_of(graph.primary_upstream(sink_model.node))
            port_model = self.port_model_of(data_port)
            if port_model is None:
                sink_model.node.clear_input()
            elif port_model is not sink_model.source_port:
                sink_model.set_source_port(port_model)

    def _forget_node(self, node: Node):
        """Selection bookkeeping before ``node`` leaves the graph. Returns
        whether the tip has to be re-derived once it is gone."""
        if self._selected_node is node:
            self._selected_node = None
        model = self.node_models.get(node.id)
        active = self.model.active_node
        if model is not None and active:
            selected = data_model.get_instance(active[0])
            owner = getattr(selected, "node", None)
            if selected is model or owner is model:
                self.model.active_node = []
        return self.tip_port is not None and self.tip_port.node is node

    # -------------------------------------------------------------------------
    # Sources
    # -------------------------------------------------------------------------

    def load_file(self, file_path: str | Path) -> str | None:
        file_path = Path(file_path).resolve()

        if not file_path.exists():
            return None

        node = ReaderSourceNode.for_file(file_path)
        self.pipeline.add_node(node)

        source = data_model.SourceNodeModel(
            self.server, node=node, label=node.label, type_name=node.type_name
        )
        self._track(source)
        self.set_tip_port(source.primary_output)

        if self.state.active_view_id:
            self.add_default_sinks(self.state.active_view_id)

        # make new data node active by default
        self.model.active_node = [source._id]

        self.execute()

        return source._id

    # -------------------------------------------------------------------------
    # State files
    # -------------------------------------------------------------------------

    def is_state_file(self, file_path: str | Path) -> bool:
        return Path(file_path).suffix.lower() in STATE_EXTENSIONS

    async def load_state_file(self, file_path: str | Path):
        """Replace the session with a ``.tvsm`` / ``.tvh5`` state file."""
        try:
            await load_state_file(self, file_path)
        except Exception:
            logger.exception("Cannot load state file {}", file_path)

    def load_state_file_later(self, file_path: str | Path):
        """Schedule ``load_state_file`` from synchronous code (UI callbacks)."""
        asynchronous.create_task(self.load_state_file(file_path))

    # -------------------------------------------------------------------------
    # Views
    # -------------------------------------------------------------------------

    PANEL_TITLE = "3D View"
    PANEL_TAB = "tomviz-dockview-tab"

    def add_view(self) -> str:
        # Imported here: `ui` imports this package at module level.
        from tomviz_trame.app import ui

        view = ui.RenderWindow(self.server)
        logger.debug("Add view {} vs {}", view.local_state._id, view.vtk_id)
        self.views[view.local_state._id] = view
        self._add_panel(view)
        return view.local_state._id

    def _add_panel(self, view):
        self.ctx.dock_view.add_panel(
            view.vtk_id,
            self.PANEL_TITLE,
            view.tpl_name,
            tabComponent=self.PANEL_TAB,
            params=self._panel_params(view),
        )

    @staticmethod
    def _panel_params(view) -> dict:
        return {"templateName": view.tpl_name, "viewState": view.local_state._id}

    def panel_entry(self, view_id: str) -> dict | None:
        """The dockview description of ``view_id``'s panel, what a restored
        layout (``pipeline/layout.py``) lists under ``panels``."""
        view = self.views.get(view_id)
        if view is None:
            return None
        return {
            "id": view.vtk_id,
            "title": self.PANEL_TITLE,
            "contentComponent": "DockPanel",
            "tabComponent": self.PANEL_TAB,
            "params": self._panel_params(view),
        }

    def restore_layout(self, layout: dict):
        """Arrange the existing panels as ``layout`` says (a dockview
        layout; the panels are reused by id)."""
        self.ctx.dock_view.restore_layout(layout)

    @trigger("remove_view")
    def remove_view(self, view_id: str):
        logger.debug("remove view {}", view_id)
        view = self.views.get(view_id)
        if view is None:
            return

        for sink_model in [m for m in self._sink_models() if m.view._id == view_id]:
            self.remove_sink(sink_model.node.id)

        view.vtk_view.finalize()
        self.ctx.dock_view.remove_panel(view.vtk_id)
        self.state.active_view_id = None
        del self.views[view_id]

    def _show_view(self, view_id: str):
        """Bring the dock panel of ``view_id`` to the front (the dockview
        reports it back through ``activate_panel``)."""
        view = self.views.get(view_id)
        dock = getattr(self.ctx, "dock_view", None)
        if view is not None and dock is not None:
            dock.active_panel(view.vtk_id)

    def activate_panel(self, panel_id):
        logger.debug("activate_panel {}", panel_id)
        found = False
        for view_id, view in self.views.items():
            if view.vtk_id == panel_id:
                self.state.active_view_id = view_id
                found = True

        if not found:
            self.state.active_view_id = None

    def refresh_views_later(self, **_):
        asynchronous.create_task(self._refresh_views())

    async def _refresh_views(self):
        await asyncio.sleep(0.1)
        self.refresh_views()

    def refresh_views(self, **_):
        """Register all views into dockview"""
        for view in self.views.values():
            self._add_panel(view)

    # -------------------------------------------------------------------------
    # Transforms
    # -------------------------------------------------------------------------

    def add_transform(
        self,
        entry_name: str,
        icon: str | None = None,
        meta: dict | None = None,
        parameters: dict | None = None,
        execute: bool = True,
        target: OutputPort | None = None,
        **_,
    ) -> str | None:
        """Append the catalog transform ``entry_name`` at ``target`` (default:
        the tip port; a group's passthrough resolves to the port feeding it).
        The sinks and groups reading the port move to a compatible output of
        the transform; downstream transforms stay, so inserting mid-chain
        branches. The new node becomes the selection. Returns the id of the
        new model."""
        entry = self.ctx.catalog.entries.get(entry_name)
        if entry is None:
            logger.error("Unknown catalog entry '{}'", entry_name)
            return None

        target = graph.data_port_of(target or self.tip_port)
        if target is None:
            logger.error("No output port to transform: load data first")
            return None

        description = meta or entry.json
        node = build_transform_node(description, entry.file, parameters)
        input_port = node.input_port(INPUT_PORT) or next(iter(node.input_ports()), None)
        if input_port is None:
            logger.error("Transform '{}' has no input port", entry.name)
            return None
        if not graph.is_port_type_compatible(
            target.port_type, input_port.accepted_types
        ):
            logger.error("'{}' does not accept {} data", entry.name, target.port_type)
            return None

        self.pipeline.add_node(node)
        self.pipeline.create_link(target, input_port)
        self._move_terminal_consumers(target, node)

        parent = self.node_models.get(target.node.id) if target.node else None
        model = data_model.TransformNodeModel(
            self.server,
            node=node,
            label=node.label,
            type_name=node.type_name,
            entry_name=entry.name,
            icon=icon or entry.icon,
            input=parent if isinstance(parent, data_model.DataNodeModel) else None,
            parameters=to_parameters_model(self.server, description),
        )
        model.bind_parameters()
        self._track(model)
        self._refresh_sink_sources()
        self.model.active_node = [model._id]

        if execute:
            self.execute_when_idle()

        return model._id

    def _move_terminal_consumers(self, target: OutputPort, node: Node):
        """Move every sink and group reading ``target`` to the first output
        of ``node`` that accepts it (desktop parity: transforms downstream of
        ``target`` keep reading it)."""
        moves = []
        for link in list(target.outgoing_links):
            consumer = link.to_port.node
            if consumer is None or consumer is node or not graph.is_terminal(consumer):
                continue
            new_output = graph.compatible_output(node, link.to_port)
            if new_output is not None:
                moves.append((link, new_output))
        for link, new_output in moves:
            to_port = link.to_port
            self.pipeline.remove_link(link)
            self.pipeline.create_link(new_output, to_port)

    # -------------------------------------------------------------------------
    # Sinks
    # -------------------------------------------------------------------------

    def add_default_sinks(self, view_id: str):
        self.add_sink(view_id, RepresentationType.OUTLINE.name, execute=False)
        self.add_sink(view_id, RepresentationType.SLICE.name, execute=False)

    def add_sink(
        self,
        view_id: str,
        type: str,
        execute: bool = True,
        target: OutputPort | None = None,
    ) -> str | None:
        """Add a sink of the given ``RepresentationType`` name showing
        ``target`` (default: the tip port) in ``view_id``, through the sink
        group on that port (created when there is none, or when the existing
        one does not accept the sink). With ``execute`` the graph runs right
        away (once the in-flight run, if any, ends) so the new sink gets
        data. Returns the id of the sink's model."""
        target = target or self.tip_port
        view = data_model.get_instance(view_id) if view_id else None
        if target is None or not isinstance(view, data_model.ViewModel):
            logger.error("Nothing to display: load data and pick a view first")
            return None
        logger.debug(
            "target: {}.{}, view: {}, type: {}",
            target.node.label,
            target.name,
            view_id,
            type,
        )

        representation_type = RepresentationType[type]
        if not representation_type.accepts(target.port_type):
            logger.error(
                "A {} cannot display '{}' ({} data)",
                representation_type.label,
                target.node.label,
                target.port_type,
            )
            return None

        output = graph.group_output_for(target, representation_type.port_types)
        if output is None:
            output = self._create_group(target)
        port_model = self.port_model_of(graph.data_port_of(output))
        if port_model is None:
            logger.error("'{}' has no data node to display", target.node.label)
            return None

        sink = RepresentationSinkNode(
            representation_type, self, port_model, view, self.run_on_loop
        )
        self.pipeline.add_node(sink)
        self.pipeline.create_link(output, sink.input_port(INPUT_PORT))
        self._track(sink.model)

        if execute:
            self.execute_when_idle()

        return sink.model._id

    def _create_group(self, target: OutputPort) -> OutputPort:
        """A new sink group on ``target``; returns its passthrough output."""
        group = SinkGroupNode()
        output = group.add_passthrough(
            target.name, graph.passthrough_type(target.port_type)
        )
        self.pipeline.add_node(group)
        self.pipeline.create_link(target, group.input_port(target.name))
        self._track(
            data_model.SinkGroupNodeModel(
                self.server, node=group, label=group.label, type_name=group.type_name
            )
        )
        return output

    def remove_sink(self, node_id: int):
        sink_model = self.node_models.get(node_id)
        if not isinstance(sink_model, data_model.SinkNodeModel):
            return
        sink: RepresentationSinkNode = sink_model.node

        owned_tip = self._forget_node(sink)
        self.pipeline.remove_node(sink)
        sink.detach()
        release = getattr(sink_model, "release_color_opacity", None)
        if release is not None:
            release()
        self._untrack(sink_model)
        if owned_tip:
            self.set_tip_port(graph.find_tip_output_port(self.pipeline))

    # -------------------------------------------------------------------------
    # Graph editing (desktop parity: plain removals, links move consumers)
    # -------------------------------------------------------------------------

    def remove_node(self, model_id: str) -> bool:
        """Remove the node of model ``model_id`` and every link touching it.
        Consumers keep their place and lose their input: sinks reading it
        hide until relinked, downstream transforms become roots."""
        model = data_model.get_instance(model_id)
        if not isinstance(model, data_model.NodeModel) or model.node is None:
            return False
        if isinstance(model, data_model.SinkNodeModel):
            self.remove_sink(model.node.id)
            return True

        node = model.node
        owned_tip = self._forget_node(node)
        unbind = getattr(model, "unbind_parameters", None)
        if unbind is not None:
            unbind()
        self.pipeline.remove_node(node)
        self._untrack(model)
        self._refresh_sink_sources()
        if owned_tip:
            self.set_tip_port(graph.find_tip_output_port(self.pipeline))
        return True

    def remove_link(self, input_id: str) -> bool:
        """Remove the link into the input port of model ``input_id``."""
        input_model = data_model.get_instance(input_id)
        if not isinstance(input_model, data_model.InputPortModel):
            return False
        port = input_model.port
        if port is None or port.link is None:
            return False
        if self.model.active_node == [input_model._id]:
            self.model.active_node = []
        self.pipeline.remove_link(port.link)
        self._refresh_sink_sources()
        return True

    def create_link(self, output_id: str, input_id: str) -> bool:
        """Link the output port of model ``output_id`` to the input port of
        model ``input_id`` (drag-to-link), replacing the input's link. The
        desktop's rules: different nodes, compatible types, and what the
        output accepts (a group's passthrough takes only sinks). The graph
        runs once every input of the consumer is linked."""
        output_model = data_model.get_instance(output_id)
        input_model = data_model.get_instance(input_id)
        if not isinstance(output_model, data_model.OutputPortModel) or not isinstance(
            input_model, data_model.InputPortModel
        ):
            return False
        from_port, to_port = output_model.port, input_model.port
        if from_port is None or to_port is None or to_port.node is None:
            return False
        if from_port.node is to_port.node:
            logger.error("A node cannot feed itself")
            return False
        if not graph.is_port_type_compatible(
            from_port.port_type, to_port.accepted_types
        ):
            logger.error(
                "'{}' does not accept {} data", to_port.node.label, from_port.port_type
            )
            return False
        if not from_port.can_accept_link(to_port):
            logger.error("Only sinks can join a group")
            return False
        try:
            self.pipeline.create_link(from_port, to_port)
        except ValueError as error:
            logger.error("Cannot link: {}", error)
            return False
        self._refresh_sink_sources()
        if all(p.link is not None for p in to_port.node.input_ports()):
            self.execute()
        return True

    def set_port_persistence(self, port_id: str, choice: str):
        """``choice``: ``memory``, ``disk`` (persistent, on that medium) or
        ``transient``. A port asked to keep data it no longer has re-runs
        its node."""
        port_model = data_model.get_instance(port_id)
        if not isinstance(port_model, data_model.OutputPortModel):
            return
        port = port_model.port
        if port is None or isinstance(port, PassthroughOutputPort):
            return
        if choice == "transient":
            port.persistent = False
        else:
            # Mode first, so the single reconcile runs with the target mode.
            port.persistence_mode = PersistenceMode(choice)
            port.persistent = True
        port_model.pull_location()
        if choice != "transient" and not port.has_data() and port.node is not None:
            # The planner only re-runs nodes that are not Current: mark the
            # producer (and what reads it) stale so the data comes back.
            port.node.mark_stale()
            self.execute()

    @staticmethod
    def _sink_group_of(sink: Node) -> SinkGroupNode | None:
        upstream = graph.primary_upstream(sink)
        node = None if upstream is None else upstream.node
        return node if isinstance(node, SinkGroupNode) else None

    def create_group_for(self, sink_id: str):
        """Route a sink linked straight to a data port through a new group
        on that port."""
        sink_model = data_model.get_instance(sink_id)
        if not isinstance(sink_model, data_model.SinkNodeModel):
            return
        sink = sink_model.node
        input_port = sink.input_port(INPUT_PORT) or next(iter(sink.input_ports()), None)
        if input_port is None or input_port.link is None:
            return
        upstream = input_port.link.from_port
        if isinstance(upstream, PassthroughOutputPort):
            return  # already in a group
        output = self._create_group(upstream)
        self.pipeline.create_link(output, input_port)
        self._refresh_sink_sources()
        self.execute_when_idle()

    def leave_group(self, sink_id: str):
        """Link a grouped sink straight to the port feeding its group."""
        sink_model = data_model.get_instance(sink_id)
        if not isinstance(sink_model, data_model.SinkNodeModel):
            return
        sink = sink_model.node
        input_port = sink.input_port(INPUT_PORT) or next(iter(sink.input_ports()), None)
        link = None if input_port is None else input_port.link
        if link is None or not isinstance(link.from_port, PassthroughOutputPort):
            return
        source = link.from_port.source
        self.pipeline.remove_link(link)
        if source is not None:
            self.pipeline.create_link(source, input_port)
        self._refresh_sink_sources()
        self.execute_when_idle()

    # -------------------------------------------------------------------------
    # Execution controls and settings
    # -------------------------------------------------------------------------

    def set_paused(self, paused: bool):
        """Pause (or resume) automatic execution; resuming runs whatever is
        not current."""
        self.pipeline.set_paused(bool(paused))

    def cancel_execution(self):
        if self.pipeline.is_executing():
            self.state.pipeline_stopping = True
            self.pipeline.cancel_execution()

    def set_transform_persistence_default(self, value: str):
        """``memory``, ``disk`` or ``transient``: applied to the outputs of
        transforms added from now on."""
        PipelineSettings.instance().transform_persistence_default = (
            TransformPersistenceDefault(value)
        )
        self.state.transform_persistence_default = value

    # -------------------------------------------------------------------------
    # Widget actions
    # -------------------------------------------------------------------------

    def menu_actions(self, kind: str, target_id: str) -> list[dict]:
        """The context menu of the widget's ``kind`` (``node``, ``port``,
        ``link``) target ``target_id`` (a model id): a list of
        ``{id, title, icon, disabled, checked}``; empty when there is
        nothing to offer."""
        target = data_model.get_instance(target_id) if target_id else None
        executing = self.pipeline.is_executing()

        def action(action_id, title, icon, disabled=False, checked=False):
            return {
                "id": action_id,
                "title": title,
                "icon": icon,
                "disabled": bool(disabled),
                "checked": bool(checked),
            }

        delete = action("delete", "Delete", "mdi-delete-outline", disabled=executing)
        if kind == "node":
            if isinstance(target, data_model.SinkNodeModel):
                grouped = self._sink_group_of(target.node) is not None
                membership = (
                    action("leave_group", "Leave group", "mdi-exit-to-app")
                    if grouped
                    else action(
                        "create_group", "Create group", "mdi-layers-triple-outline"
                    )
                )
                return [membership, delete]
            if isinstance(
                target, data_model.DataNodeModel | data_model.SinkGroupNodeModel
            ):
                return [
                    action(
                        "add_transform", "Add transform...", "mdi-shape-plus-outline"
                    ),
                    delete,
                ]
            if isinstance(target, data_model.NodeModel):
                return [delete]
        if kind == "port" and isinstance(target, data_model.OutputPortModel):
            port = target.port
            if port is None or isinstance(port, PassthroughOutputPort):
                return []
            persistent = port.persistent
            mode = port.persistence_mode
            return [
                action(
                    "persist_memory",
                    "Persist in memory",
                    "mdi-memory",
                    checked=persistent and mode == PersistenceMode.InMemory,
                ),
                action(
                    "persist_disk",
                    "Persist on disk",
                    "mdi-harddisk",
                    checked=persistent and mode == PersistenceMode.OnDisk,
                ),
                action(
                    "transient", "Transient", "mdi-timer-sand", checked=not persistent
                ),
            ]
        if kind == "link" and isinstance(target, data_model.InputPortModel):
            return [action("delete", "Delete link", "mdi-link-off", disabled=executing)]
        return []

    def run_menu_action(self, action_id: str, kind: str, target_id: str):
        target = data_model.get_instance(target_id) if target_id else None
        if action_id == "add_transform":
            # Select the node (the tip follows) and open the picker.
            if isinstance(target, data_model.NodeModel):
                self.model.active_node = [target._id]
            self.state.select_transform = True
        elif action_id == "delete":
            if kind == "node":
                self.remove_node(target_id)
            elif kind == "link":
                self.remove_link(target_id)
            else:
                logger.error("Nothing to delete for a {}", kind)
        elif action_id == "create_group":
            self.create_group_for(target_id)
        elif action_id == "leave_group":
            self.leave_group(target_id)
        elif action_id in ("persist_memory", "persist_disk", "transient"):
            choice = {"persist_memory": "memory", "persist_disk": "disk"}.get(
                action_id, "transient"
            )
            self.set_port_persistence(target_id, choice)
        else:
            logger.error("Unknown pipeline action '{}'", action_id)

    def toggle_breakpoint(self, node_id: str):
        """Flip the breakpoint of the node model ``node_id`` (resuming when
        execution is paused there)."""
        model = data_model.get_instance(node_id)
        if not isinstance(model, data_model.NodeModel) or model.node is None:
            return
        if model.at_breakpoint:
            model.node.breakpoint = False
            model.at_breakpoint = False
            model.pull_state()
            self.execute()
            return
        model.node.breakpoint = not model.node.breakpoint
        model.pull_state()

    def edit_node(self, node_id: str):
        """Double click on a node: select it (its properties show in the
        drawer)."""
        model = data_model.get_instance(node_id)
        if isinstance(model, data_model.NodeModel):
            self.model.active_node = [model._id]

    # -------------------------------------------------------------------------
    # Selection
    # -------------------------------------------------------------------------

    def set_tip_port(self, port: OutputPort | None):
        """Make ``port`` the tip: where the next transform or sink attaches."""
        self.tip_port = port
        port_model = self.port_model_of(port)
        self.state.tip_port_id = None if port_model is None else port_model._id

    def _on_active_change(self, active_node: list[str]):
        # Imported here: `ui` imports this package at module level.
        from tomviz_trame.app.ui.dynamic import DYNAMIC_TEMPLATES

        logger.debug("active_node: {}", active_node)
        obj = data_model.get_instance(active_node[0]) if active_node else None

        # The tip follows the selection (desktop ActiveObjects rules): a
        # node's first output, a port itself, a link's source, the branch end
        # of a sink; deselecting a node re-derives it from that node.
        previous = self._selected_node
        tip = self.tip_port
        self._selected_node = None
        if isinstance(obj, data_model.NodeModel) and obj.node is not None:
            self._selected_node = obj.node
            outputs = obj.node.output_ports()
            tip = (
                outputs[0]
                if outputs
                else graph.find_tip_output_port(self.pipeline, obj.node)
            )
        elif isinstance(obj, data_model.OutputPortModel) and obj.port is not None:
            tip = obj.port
        elif isinstance(obj, data_model.InputPortModel):
            if obj.port is not None and obj.port.link is not None:
                tip = obj.port.link.from_port
        elif previous is not None:
            tip = graph.find_tip_output_port(self.pipeline, previous)
        self.set_tip_port(tip)

        data_port_model = self.port_model_of(graph.data_port_of(tip))
        color_opacity = (
            None if data_port_model is None else data_port_model.color_opacity
        )
        data_node = None if data_port_model is None else data_port_model.node

        with self.state as s:
            s.active_port_id = None if data_port_model is None else data_port_model._id
            s.active_representation_id = None
            s.property_templates = []
            if isinstance(obj, data_model.DataNodeModel):
                s.active_data_id = obj._id
                if isinstance(obj, data_model.TransformNodeModel):
                    s.property_templates = [DYNAMIC_TEMPLATES.get("transform")]
            elif isinstance(obj, data_model.SinkNodeModel):
                s.active_data_id = obj.data_node._id if obj.data_node else None
                s.active_representation_id = obj._id
                s.active_view_id = obj.view._id
                self._show_view(obj.view._id)
                color_opacity = getattr(obj, "color_opacity", None) or color_opacity
                template = DYNAMIC_TEMPLATES.get(obj.representation_type)
                s.property_templates = [template] if template else []
            elif isinstance(obj, data_model.OutputPortModel):
                # A port's properties are what is on it (the data_info panel
                # reads active_port_id, the port's data port).
                s.active_data_id = (
                    data_node._id
                    if isinstance(data_node, data_model.DataNodeModel)
                    else None
                )
                s.property_templates = [DYNAMIC_TEMPLATES.get("data_info")]
            else:
                s.active_data_id = (
                    data_node._id
                    if isinstance(data_node, data_model.DataNodeModel)
                    else None
                )
            s.active_color_opacity_id = color_opacity._id if color_opacity else ""

    @change("active_color_opacity_id")
    def _on_active_color_opacity_change(self, active_color_opacity_id, **_):
        """The color editor counts as a user of the map it shows, so a port
        nobody displays still gets statistics when selected. Tracked on the
        state key itself because sinks also update it when they rebind."""
        previous_id = self._ui_color_opacity_id
        if previous_id == active_color_opacity_id:
            return
        self._ui_color_opacity_id = active_color_opacity_id

        ui_user = data_model.ColorOpacityModel.UI_USER
        previous = data_model.get_instance(previous_id) if previous_id else None
        if isinstance(previous, data_model.ColorOpacityModel):
            previous.release(ui_user)
        current = (
            data_model.get_instance(active_color_opacity_id)
            if active_color_opacity_id
            else None
        )
        if isinstance(current, data_model.ColorOpacityModel):
            current.acquire(ui_user)
