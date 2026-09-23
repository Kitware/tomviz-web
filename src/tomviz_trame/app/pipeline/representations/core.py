"""Catalog of visualization types and the VTK plumbing they share."""

from __future__ import annotations

from enum import Enum

from vtkmodules.vtkCommonDataModel import vtkImageData
from vtkmodules.vtkCommonExecutionModel import vtkTrivialProducer

from tomviz_trame.app import module
from tomviz_trame.app.utils.data import IMAGE_PORT_TYPES, MOLECULE_PORT_TYPES


class RepresentationType(Enum):
    """One entry per visualization the application knows about.

    ``sink_type`` is the schema-v2 node type string the desktop tomviz uses
    for the matching sink node, so state files written by either application
    describe the same graph. ``port_types`` are the library port types the
    visualization can display (``accepts``); ``add_sink`` refuses the rest.
    A type is only usable once a module in this package has called
    ``register_class`` on it.
    """

    def __new__(cls, icon_file: str, label: str, sink_type: str, port_types):
        obj = object.__new__(cls)
        obj._value_ = icon_file
        obj.label = label
        obj.sink_type = sink_type
        obj.port_types = tuple(port_types)
        obj.representation_class = None
        return obj

    CLIP = ("clip.svg", "Clip", "sink.clip", IMAGE_PORT_TYPES)
    CONTOUR = ("contour.svg", "Contour", "sink.contour", IMAGE_PORT_TYPES)
    MOLECULE = ("molecule.svg", "Molecule", "sink.molecule", MOLECULE_PORT_TYPES)
    OUTLINE = ("outline.svg", "Outline", "sink.outline", IMAGE_PORT_TYPES)
    RULER = ("ruler.svg", "Ruler", "sink.ruler", IMAGE_PORT_TYPES)
    SCALE_CUBE = ("scale-cube.svg", "Scale Cube", "sink.scaleCube", IMAGE_PORT_TYPES)
    SLICE = ("slice.svg", "Slice", "sink.slice", IMAGE_PORT_TYPES)
    THRESHOLD = ("threshold.svg", "Threshold", "sink.threshold", IMAGE_PORT_TYPES)
    VOLUME = ("volume.png", "Volume", "sink.volume", IMAGE_PORT_TYPES)

    def accepts(self, port_type: str) -> bool:
        return port_type in self.port_types

    @property
    def icon(self):
        return f"{module.BASENAME}/assets/representations/{self.value}"

    @property
    def model_kwargs(self):
        """The ``SinkNodeModel`` fields that describe this type."""
        return {
            "label": self.label,
            "representation_type": self.name,
            "icon": self.icon,
        }

    def register_class(self, klass):
        self.representation_class = klass

    def create_representation(self, pipeline_manager, source_port, view):
        if self.representation_class is None:
            msg = f"No representation found for {self.label}"
            raise ValueError(msg)

        return self.representation_class(pipeline_manager, source_port, view)


class Representation:
    """VTK plumbing for one visualization of a dataset in one view.

    Subclasses assemble ``self.producer >> filters >> self.mapper`` and an
    ``actor``, call ``attach``, and create ``self.model`` (the
    ``SinkNodeModel`` the UI binds to). The producer is a
    ``vtkTrivialProducer`` so the VTK pipeline exists before any data does;
    the owning sink node calls ``set_input`` whenever the graph delivers a new
    image. Until then the actor stays hidden so VTK never tries to execute an
    empty pipeline.
    """

    def __init__(self, server):
        self.server = server
        self.producer = vtkTrivialProducer()
        self._image: vtkImageData | None = None
        self.mapper = None
        self.actor = None
        self.model = None

    @property
    def image(self) -> vtkImageData | None:
        return self._image

    def set_input(self, image: vtkImageData):
        self._image = image
        self.producer.SetOutput(image)

    def clear_input(self):
        """Forget the image: the actor hides until data arrives again (the
        producer keeps the last image so VTK never executes empty)."""
        self._image = None
        if self.actor is not None:
            self.actor.visibility = False

    def attach(self, view):
        """Add the actor to a ``vtk.view.View``, hidden until data arrives."""
        self.actor.visibility = False
        view.add_representation(self)

    def detach(self, view):
        view.remove_representation(self)

    def use_lut(self, lut):
        if lut is None:
            return

        self.mapper.SetLookupTable(lut.table)
        self.mapper.SetUseLookupTableScalarRange(True)
        self.mapper.SetScalarVisibility(True)

    def use_pwf(self, pwf):
        """Surface representations ignore the opacity function: slices stay
        opaque, as on the desktop. (Baking it into the lookup table would
        only last until the table is rebuilt, so it showed up only after a
        sink was rebound to a port whose map was already built.) The volume
        overrides this."""

    @property
    def ColorArrayName(self):
        return getattr(self, "_color_array_name", (None, None))

    @ColorArrayName.setter
    def ColorArrayName(self, value):
        self._color_array_name = value
        association, name = value

        if not name:
            self.mapper.SetScalarVisibility(False)
            return

        if association == "CELLS":
            self.mapper.SetScalarModeToUseCellFieldData()
        else:
            self.mapper.SetScalarModeToUsePointFieldData()

        self.mapper.SelectColorArray(name)
        self.mapper.SetColorModeToMapScalars()
        self.mapper.SetScalarVisibility(True)
