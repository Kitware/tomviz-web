"""Sink nodes that turn pipeline data into something visible in a view."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger
from tomviz_pipeline import PortData, SinkNode

from tomviz_trame.app.pipeline.representations import RepresentationType
from tomviz_trame.app.pipeline.vtk import convert

if TYPE_CHECKING:
    from tomviz_trame.app import data_model

INPUT_PORT = "volume"

Dispatch = Callable[[Callable[[], None]], None]


class RepresentationSinkNode(SinkNode):
    """A leaf of the graph that displays its input in one render view.

    One sink exists per (output port, view, visualization type). It owns the
    VTK ``Representation`` and the ``SinkNodeModel`` the UI binds to. Its node
    type string is the one the desktop tomviz uses for the same visualization
    (``sink.outline``, ``sink.slice``, ...).

    ``consume`` runs on the executor's worker thread. It only converts the
    numpy payload to a ``vtkImageData`` there; applying it to the actors and
    updating trame state happens in ``apply``, which the ``dispatch`` callable
    schedules on the application's event loop.
    """

    executable = True

    def __init__(
        self,
        representation_type: RepresentationType,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
        dispatch: Dispatch,
    ):
        super().__init__()
        self.type_name = representation_type.sink_type
        self.label = representation_type.label
        self.representation_type = representation_type
        self.view = view
        self._dispatch = dispatch
        self._has_data = False
        self.add_input(INPUT_PORT, list(representation_type.port_types))

        self.representation = representation_type.create_representation(
            pipeline_manager, source_port, view
        )
        self.model: data_model.SinkNodeModel = self.representation.model
        self.model.node = self
        self.model.type_name = self.type_name

    def consume(self, inputs: dict[str, PortData]) -> bool:
        data = inputs[INPUT_PORT]
        try:
            image = convert.to_vtk_image(data.payload)
        except Exception:
            logger.exception("Cannot display the output feeding '{}'", self.label)
            return False

        self._dispatch(lambda: self.apply(image))
        return True

    def apply(self, image):
        """Push a converted image into the VTK representation. Runs on the
        application's event loop."""
        first_data = not self._has_data
        self._has_data = True

        self.representation.set_input(image)
        # Settings made before any data (a loaded state) live only in the
        # model: assert them on the representation, then read the derived
        # values (extents, ranges) back.
        self.model.push()
        self.model.pull()
        if first_data:
            self.model.apply_visibility()

        # The first data placed in a view fits the camera; a camera set from
        # a state file (or an earlier dataset) is left alone.
        if first_data and not self.view.camera_initialized:
            self.view.camera_initialized = True
            self.model.reset_camera()
        self.model.render()

    def clear_input(self):
        """The input is gone (link or upstream node removed): hide the
        visualization until data flows again. Event loop only."""
        if not self._has_data:
            return
        self._has_data = False
        self.representation.clear_input()
        self.model.apply_visibility()
        self.model.render()

    def detach(self):
        """Remove the representation from its view; called when the sink is
        removed from the graph."""
        self.representation.detach(self.view.vtk_view)
        self.view.render()
