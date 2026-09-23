"""Mirrors of ``tomviz_pipeline.PortData``: the payload on an output port.

The library types a port with a string (``ImageData``, ``TiltSeries``,
``Table``, ``Molecule``, ...) and hands a ``PortData(payload, port_type)``
to consumers after every execution. The payload families map to one
``PortDataModel`` subclass each, looked up through a registry keyed by the
type string like the library's writers. An ``OutputPortModel`` holds one of
these in its ``data`` slot, updates it in place across executions and
replaces it only when the family changes.

Each subclass knows how to ``describe`` its payload (pure, any thread) and
how to ``apply`` the result on the loop. Image data additionally caches
per-array statistics lazily (see ``OutputPortModel.statistics``)."""

from __future__ import annotations

from typing import Any

from trame.app.dataclass import StateDataModel, Sync

from tomviz_trame.app.utils import data


class PortDataModel(StateDataModel):
    """Base mirror of ``PortData``: the payload family and type string."""

    FAMILY = ""

    family = Sync(str, "")
    port_type = Sync(str, "")

    def __init__(self, server, **kwargs):
        super().__init__(server, family=self.FAMILY, **kwargs)

    # ---- description (pure computation, any thread) --------------------

    @classmethod
    def describe(cls, payload: Any, requested: set[str] | None = None):
        """Describe ``payload``; ``requested`` names the statistics keys
        consumers want (ignored by families without lazy statistics)."""
        raise NotImplementedError

    def apply(self, description):
        """Install a description (event loop only)."""
        raise NotImplementedError

    # ---- lazy statistics (image data only, no-ops elsewhere) -------------

    def statistics_of(self, key: str):  # noqa: ARG002 (interface)
        return None

    def can_compute(self, key: str) -> bool:  # noqa: ARG002 (interface)
        return False

    @classmethod
    def compute_statistics(cls, payload: Any, key: str):
        raise NotImplementedError

    def add_statistics(self, key: str, stats):
        """Merge a lazily computed result."""


class ImagePortDataModel(PortDataModel):
    """A numpy ``Dataset`` (every image-like port type): geometry, array
    names, and per-array ranges and exact histograms for the arrays some
    color map displays."""

    FAMILY = "image"

    scalars_names = Sync(list[str], list)
    active_scalars = Sync(str, "")
    dimensions = Sync(data.Shape, (0, 0, 0))
    spacing = Sync(data.Spacing, (1.0, 1.0, 1.0))
    extent = Sync(data.Extent, data.EMPTY_EXTENT)
    bounds = Sync(data.Bounds, data.EMPTY_BOUNDS)
    memory = Sync(int, 0)  # KiB
    ranges = Sync(dict, dict)  # array name -> [min, max]
    histograms = Sync(dict, dict)  # array name -> counts (data.HISTOGRAM_BINS)

    @classmethod
    def describe(cls, payload, requested=None) -> data.ImageDescription:
        return data.describe_dataset(payload, requested or ())

    def apply(self, description: data.ImageDescription):
        self.scalars_names = list(description.scalars_names)
        self.active_scalars = description.active_scalars
        self.dimensions = description.dimensions
        self.spacing = description.spacing
        self.extent = description.extent
        self.bounds = description.bounds
        self.memory = description.memory
        self.ranges = {
            name: list(stats.range) for name, stats in description.statistics.items()
        }
        self.histograms = {
            name: list(stats.histogram)
            for name, stats in description.statistics.items()
        }

    def statistics_of(self, key: str) -> data.ArrayStatistics | None:
        if key in self.ranges and key in self.histograms:
            return data.ArrayStatistics(
                (self.ranges[key][0], self.ranges[key][1]), self.histograms[key]
            )
        return None

    def can_compute(self, key: str) -> bool:
        return key in self.scalars_names

    @classmethod
    def compute_statistics(cls, payload, key: str) -> data.ArrayStatistics:
        return data.array_statistics(payload.scalars(key))

    def add_statistics(self, key: str, stats: data.ArrayStatistics):
        self.ranges = {**self.ranges, key: list(stats.range)}
        self.histograms = {**self.histograms, key: list(stats.histogram)}


class TablePortDataModel(PortDataModel):
    """A ``tomviz_pipeline.table.Table``: columns, row count, chart hints
    and the range of every numeric column."""

    FAMILY = "table"

    column_names = Sync(list[str], list)
    num_rows = Sync(int, 0)
    axes_labels = Sync(list[str], list)
    axes_log_scale = Sync(list[bool], list)
    ranges = Sync(dict, dict)  # column name -> [min, max]

    @classmethod
    def describe(cls, payload, requested=None) -> data.TableDescription:  # noqa: ARG003
        return data.describe_table(payload)

    def apply(self, description: data.TableDescription):
        self.column_names = list(description.column_names)
        self.num_rows = description.num_rows
        self.axes_labels = list(description.axes_labels)
        self.axes_log_scale = list(description.axes_log_scale)
        self.ranges = {name: list(r) for name, r in description.ranges.items()}


class MoleculePortDataModel(PortDataModel):
    """A ``tomviz_pipeline.molecule.Molecule``: atom and bond counts and
    the elements present."""

    FAMILY = "molecule"

    num_atoms = Sync(int, 0)
    num_bonds = Sync(int, 0)
    elements = Sync(list[str], list)

    @classmethod
    def describe(cls, payload, requested=None) -> data.MoleculeDescription:  # noqa: ARG003
        return data.describe_molecule(payload)

    def apply(self, description: data.MoleculeDescription):
        self.num_atoms = description.num_atoms
        self.num_bonds = description.num_bonds
        self.elements = list(description.elements)


# ---- registry: port type string -> payload model --------------------------

_FAMILIES: dict[str, type[PortDataModel]] = {}


def register_port_data_model(model_class: type[PortDataModel], port_types):
    """Map port type strings onto a ``PortDataModel`` subclass, like the
    library's ``register_writer``. Later registrations win."""
    for port_type in port_types:
        _FAMILIES[port_type] = model_class


def port_data_model_for(port_type: str) -> type[PortDataModel] | None:
    return _FAMILIES.get(port_type)


register_port_data_model(ImagePortDataModel, data.IMAGE_PORT_TYPES)
register_port_data_model(TablePortDataModel, data.TABLE_PORT_TYPES)
register_port_data_model(MoleculePortDataModel, data.MOLECULE_PORT_TYPES)
