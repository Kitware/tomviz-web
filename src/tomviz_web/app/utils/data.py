"""Descriptions of pipeline payloads: what the UI shows about the data on an
output port, per payload family (image datasets, tables, molecules), and the
per-array value ranges and histograms of image data.

Everything here is pure numpy and safe to run on any thread. Histograms are
exact: ``np.histogram`` releases the GIL and costs ~8 ns per value, so large
arrays are split across a few threads rather than subsampled."""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.molecule import Molecule, element_symbol
from tomviz_pipeline.table import Table

from tomviz_web.app.utils import labels

# Port type strings (tomviz_pipeline) grouped by payload family.
IMAGE_PORT_TYPES = ("ImageData", "Volume", "TiltSeries", "LabelMap", "Image")
TABLE_PORT_TYPES = ("Table",)
MOLECULE_PORT_TYPES = ("Molecule",)

HISTOGRAM_BINS = 128
# Values per thread when a histogram is split; below this a single call wins.
HISTOGRAM_CHUNK = 4_000_000

Shape = tuple[int, int, int]
Spacing = tuple[float, float, float]
Extent = tuple[int, int, int, int, int, int]
Bounds = tuple[float, float, float, float, float, float]

EMPTY_EXTENT: Extent = (0, -1, 0, -1, 0, -1)
EMPTY_BOUNDS: Bounds = (0.0, -1.0, 0.0, -1.0, 0.0, -1.0)


def log10(v):
    if v > 0:
        return math.log10(v)
    return 0


def shape_3d(array: np.ndarray) -> Shape:
    """The ``(nx, ny, nz)`` dimensions of an array, padding 1D and 2D data
    with unit-length trailing axes."""
    if array.ndim > 3:
        msg = f"Expected an array with at most 3 dimensions, got {array.ndim}"
        raise ValueError(msg)
    shape = [int(n) for n in array.shape]
    while len(shape) < 3:
        shape.append(1)
    return (shape[0], shape[1], shape[2])


def spacing_3d(dataset: Dataset) -> Spacing:
    spacing = list(dataset.spacing) if dataset.spacing is not None else []
    while len(spacing) < 3:
        spacing.append(1.0)
    return (float(spacing[0]), float(spacing[1]), float(spacing[2]))


def value_range(array: np.ndarray) -> tuple[float, float]:
    """Exact min/max of the whole array (vectorized, a few ms per 100 MB)."""
    return float(array.min()), float(array.max())


def histogram(
    array: np.ndarray,
    n_bins: int = HISTOGRAM_BINS,
    data_range: tuple[float, float] | None = None,
) -> list[int]:
    """Exact histogram of ``array`` over ``data_range`` (its min/max when
    omitted). Large arrays are split across threads."""
    flat = array.ravel(order="K")  # a view for contiguous arrays
    if data_range is None:
        data_range = value_range(flat)

    n_chunks = min(max(1, flat.size // HISTOGRAM_CHUNK), os.cpu_count() or 1)
    if n_chunks <= 1:
        counts = np.histogram(flat, bins=n_bins, range=data_range)[0]
    else:
        with ThreadPoolExecutor(n_chunks) as pool:
            parts = pool.map(
                lambda chunk: np.histogram(chunk, bins=n_bins, range=data_range)[0],
                np.array_split(flat, n_chunks),
            )
            counts = sum(parts)
    return [int(c) for c in counts]


# A new threshold keeps about this many voxels at most (the desktop's budget)
THRESHOLD_BUDGET = 250_000
THRESHOLD_BINS = 4096


def threshold_seed(array: np.ndarray) -> float:
    """Where a new threshold starts, as on the desktop (thresholdSeed): the
    value above which the brightest voxels lie, at most the budget of them
    and at most 5 %, among the voxels above the minimum (most of a
    reconstruction is dim background, and thresholding into that noise
    makes a huge surface). A 4096-bin histogram, interpolated in its bin."""
    flat = array.ravel(order="K")
    if flat.size == 0:
        return 0.0
    finite = np.issubdtype(flat.dtype, np.integer) or bool(np.isfinite(flat).all())
    low = float(flat.min() if finite else np.nanmin(flat))
    high = float(flat.max() if finite else np.nanmax(flat))
    if not high > low:
        return low
    counts = np.asarray(histogram(flat, THRESHOLD_BINS, (low, high)))
    counts[0] -= int(np.count_nonzero(flat == low))  # the minimum is excluded
    total = int(counts.sum())
    if total <= 0:
        return low
    fraction = max(0.95, 1.0 - THRESHOLD_BUDGET / flat.size)
    target = fraction * total
    below = np.concatenate(([0], np.cumsum(counts)[:-1]))
    index = int(np.argmax(below + counts >= target))
    within = (target - below[index]) / counts[index] if counts[index] else 0.0
    return low + (index + within) * (high - low) / THRESHOLD_BINS


@dataclass
class ArrayStatistics:
    range: tuple[float, float]
    histogram: list[int]


def array_statistics(array: np.ndarray, n_bins: int = HISTOGRAM_BINS):
    data_range = value_range(array)
    return ArrayStatistics(data_range, histogram(array, n_bins, data_range))


@dataclass
class ImageDescription:
    """What the UI shows about an image dataset. ``statistics`` only holds
    the arrays it was asked for."""

    scalars_names: list[str] = field(default_factory=list)
    active_scalars: str = ""
    dimensions: Shape = (0, 0, 0)
    spacing: Spacing = (1.0, 1.0, 1.0)
    extent: Extent = EMPTY_EXTENT
    bounds: Bounds = EMPTY_BOUNDS
    memory: int = 0  # KiB, like vtkDataObject::GetActualMemorySize
    statistics: dict[str, ArrayStatistics] = field(default_factory=dict)
    # Arrays a Label Map could show: integers spanning at most MAX_LABELS
    # values (utils.labels.can_interpret_as_label_map).
    label_arrays: list[str] = field(default_factory=list)
    # A label map port's scan of its active array (data_model.labels)
    labels: tuple | None = None


def describe_dataset(dataset: Dataset, arrays=()) -> ImageDescription:
    """Describe ``dataset`` and compute statistics for the named ``arrays``
    (unknown names are ignored)."""
    names = list(dataset.scalars_names)
    active = dataset.active_name if dataset.active_name in names else ""
    description = ImageDescription(
        scalars_names=names, active_scalars=active or (names[0] if names else "")
    )
    if not names:
        return description

    nx, ny, nz = shape_3d(dataset.scalars(names[0]))
    sx, sy, sz = spacing_3d(dataset)
    description.dimensions = (nx, ny, nz)
    description.spacing = (sx, sy, sz)
    description.extent = (0, nx - 1, 0, ny - 1, 0, nz - 1)
    description.bounds = (0.0, (nx - 1) * sx, 0.0, (ny - 1) * sy, 0.0, (nz - 1) * sz)
    description.memory = sum(dataset.scalars(name).nbytes for name in names) // 1024

    for name in arrays:
        if name in names:
            description.statistics[name] = array_statistics(dataset.scalars(name))

    for name in names:
        values = dataset.scalars(name)
        if not labels.is_label_dtype(values.dtype):
            continue
        if values.dtype.itemsize > 2:
            stats = description.statistics.get(name)
            span = stats.range if stats is not None else value_range(values)
        else:
            span = None
        if labels.can_interpret_as_label_map(values.dtype, span):
            description.label_arrays.append(name)

    return description


@dataclass
class TableDescription:
    """What the UI shows about a table: its columns and, for the numeric
    ones, their value range (tables are small, so all are computed)."""

    column_names: list[str] = field(default_factory=list)
    num_rows: int = 0
    axes_labels: list[str] = field(default_factory=list)
    axes_log_scale: list[bool] = field(default_factory=list)
    ranges: dict[str, tuple[float, float]] = field(default_factory=dict)


def describe_table(table: Table) -> TableDescription:
    description = TableDescription(
        column_names=list(table.column_names),
        num_rows=int(table.num_rows),
        axes_labels=[str(x) for x in (table.axes_labels or [])],
        axes_log_scale=[bool(x) for x in (table.axes_log_scale or [])],
    )
    for name in description.column_names:
        column = table.column(name)
        if (
            isinstance(column, np.ndarray)
            and column.dtype.kind in "biuf"
            and column.size
        ):
            description.ranges[name] = value_range(column)
    return description


@dataclass
class MoleculeDescription:
    num_atoms: int = 0
    num_bonds: int = 0
    elements: list[str] = field(default_factory=list)  # symbols present, sorted


def describe_molecule(molecule: Molecule) -> MoleculeDescription:
    atomic_numbers = np.asarray(molecule.atomic_numbers)
    bonds = np.asarray(molecule.bonds)
    return MoleculeDescription(
        num_atoms=int(atomic_numbers.size),
        num_bonds=int(bonds.shape[0]) if bonds.ndim == 2 else 0,
        elements=sorted({element_symbol(int(z)) for z in np.unique(atomic_numbers)}),
    )
