"""Mirrors of ``tomviz_pipeline`` ports for the reactive UI."""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from loguru import logger
from tomviz_pipeline import InputPort, OutputPort
from trame.app.dataclass import ServerOnly, StateDataModel, Sync

from .color_opacity import ColorOpacityModel
from .node import NodeModel
from .port_data import ImagePortDataModel, PortDataModel, port_data_model_for

if TYPE_CHECKING:
    from .color_opacity import ColorOpacityModel as _Consumer


class OutputPortModel(StateDataModel):
    """One output port of a data node.

    The port is the stable identity sinks and links hang off: the library
    port, its owner ``node``, ``name`` and ``port_type``. What is *on* the
    port is mirrored by ``data``, a ``PortDataModel`` for the payload's
    family (image, table, molecule; see ``port_data.py``), updated in place
    after every execution and replaced only when the family changes.
    ``data_version`` increments on every refresh so stale lazy results are
    dropped.

    Image ports carry per-array statistics lazily: only the arrays some
    enabled color map displays (``requested_keys``). The eager refresh
    computes those on the executor's worker (``PipelineManager``); a color
    map asking for an uncached array triggers a background computation
    (``statistics``) and is notified through ``on_port_statistics``.

    ``color_opacity`` is the shared color map of an image port, the one sinks
    use unless they switch to their own. It stays on the port, not on the
    data, so presets and opacity nodes survive re-execution.

    ``persistent``, ``persistence_mode`` and ``data_location`` mirror the
    port's persistence policy and where its payload currently is
    (``pull_location`` refreshes the latter from the port's
    ``data_location_changed`` signal); the widget shows them as badges.
    """

    port = ServerOnly(OutputPort | None)
    node = Sync(NodeModel, has_dataclass=True)
    name = Sync(str, "")
    port_type = Sync(str, "")

    has_data = Sync(bool, False)
    data_version = Sync(int, 0)
    data = Sync(PortDataModel, has_dataclass=True)

    persistent = Sync(bool, True)
    persistence_mode = Sync(str, "memory")  # PersistenceMode value
    data_location = Sync(str, "none")  # DataLocation value

    color_opacity = Sync(ColorOpacityModel, has_dataclass=True)

    def __init__(self, server, **kwargs):
        self._consumers: list[weakref.ref] = []
        self._pending: set[str] = set()
        super().__init__(server, **kwargs)
        self.pull_location()

    def pull_location(self):
        """Copy the port's persistence policy and data location (event loop
        only)."""
        port = self.port
        if port is None:
            return
        self.persistent = bool(port.persistent)
        self.persistence_mode = port.persistence_mode.value
        self.data_location = port.data_location().value
        self.has_data = port.has_data()

    # ---- payload --------------------------------------------------------

    @property
    def payload(self) -> Any | None:
        """The payload on the library port, if the node has run
        (non-loading peek)."""
        if self.port is None:
            return None
        port_data = self.port.data()
        return None if port_data is None else port_data.payload

    @property
    def image(self) -> ImagePortDataModel | None:
        """``data`` when the port carries image data, else None."""
        return self.data if isinstance(self.data, ImagePortDataModel) else None

    def _current_model_class(self) -> type[PortDataModel] | None:
        port_type = self.port.port_type if self.port is not None else self.port_type
        return port_data_model_for(port_type)

    # ---- consumers ------------------------------------------------------

    def add_consumer(self, consumer: _Consumer):
        self._consumers = [r for r in self._consumers if r() is not None]
        if not any(r() is consumer for r in self._consumers):
            self._consumers.append(weakref.ref(consumer))

    def remove_consumer(self, consumer: _Consumer):
        self._consumers = [
            r for r in self._consumers if r() is not None and r() is not consumer
        ]

    def consumers(self) -> list[_Consumer]:
        return [c for c in (r() for r in list(self._consumers)) if c is not None]

    def requested_keys(self) -> set[str]:
        """Statistics keys (array names) some enabled color map displays."""
        return {
            c.active_data_array
            for c in self.consumers()
            if c.enabled and c.active_data_array
        }

    # ---- description ----------------------------------------------------

    def describe(self, requested: set[str] | None = None):
        """Describe the current payload (with statistics for ``requested``,
        default: the requested keys). Pure computation, safe on any thread;
        None when the port has no data or an unknown family."""
        payload = self.payload
        model_class = self._current_model_class()
        if payload is None or model_class is None:
            return None
        if requested is None:
            requested = self.requested_keys()
        return model_class.describe(payload, requested)

    def apply_description(self, description):
        """Install a description (event loop only): update ``data`` in
        place, or replace it when the payload family changed, then notify
        consumers."""
        if self.port is not None:
            self.port_type = self.port.port_type
        model_class = self._current_model_class()
        if model_class is None:
            logger.warning("No payload model for port type '{}'", self.port_type)
            return

        if not isinstance(self.data, model_class):
            self.data = model_class(self.server)
        self.data.port_type = self.port_type
        self.data.apply(description)

        self.has_data = True
        self.data_version = self.data_version + 1
        self._pending.clear()

        for consumer in self.consumers():
            consumer.on_port_data_changed()

    # ---- lazy statistics ------------------------------------------------

    def statistics(self, key: str):
        """Cached statistics for ``key``, or None after scheduling their
        computation; consumers get ``on_port_statistics(key)`` when done."""
        data = self.data
        if data is None or not self.has_data:
            return None
        cached = data.statistics_of(key)
        if cached is not None:
            return cached
        if data.can_compute(key):
            self._request(key)
        return None

    def _request(self, key: str):
        if key in self._pending:
            return
        payload = self.payload
        data = self.data
        if payload is None or data is None:
            return

        self._pending.add(key)
        version = self.data_version
        model_class = type(data)

        def done(stats):
            self._pending.discard(key)
            if version != self.data_version or self.data is not data:
                return  # the data changed meanwhile; a new request will follow
            data.add_statistics(key, stats)
            for consumer in self.consumers():
                consumer.on_port_statistics(key)

        logger.debug("Computing statistics of '{}' on port '{}'", key, self.name)
        run_in_background(lambda: model_class.compute_statistics(payload, key), done)


class InputPortModel(StateDataModel):
    """Mirror of a ``tomviz_pipeline.InputPort``: its owner ``node``,
    ``name``, ``accepted_types`` and ``link``, the ``OutputPortModel`` feeding
    it (None while unlinked). An input holds at most one link, so the widget
    identifies a link by its input port."""

    port = ServerOnly(InputPort | None)
    node = Sync(NodeModel, has_dataclass=True)
    name = Sync(str, "")
    accepted_types = Sync(list[str], list)
    link = Sync(OutputPortModel | None, None, has_dataclass=True)
    # Whether the link's effective type still suits this input (the widget
    # crosses out an input whose upstream changed type).
    link_valid = Sync(bool, True)

    def pull_link(self):
        """Mirror the port's link validity (event loop only)."""
        link = None if self.port is None else self.port.link
        self.link_valid = True if link is None else bool(link.valid)


def run_in_background(compute: Callable[[], object], done: Callable[[object], None]):
    """Run ``compute`` in the event loop's thread pool and ``done(result)``
    back on the loop. Without a running loop both run inline."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        done(compute())
        return

    future = loop.run_in_executor(None, compute)

    def finished(f):
        try:
            result = f.result()
        except Exception:
            logger.exception("Background computation failed")
            return
        done(result)

    future.add_done_callback(finished)
