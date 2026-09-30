"""Label maps without an app: the table helpers, the transfer function
bands, the lookup table's per-label entries and the label surfaces."""

import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
from vtkmodules.vtkCommonDataModel import vtkImageData

from tomviz_web.app.pipeline.vtk import label_surface
from tomviz_web.app.pipeline.vtk.core import LookupTable
from tomviz_web.app.utils import data, labels


def blocks(shape=(24, 24, 24), dtype=np.uint8):
    """Background, two touching cubes (1, 2) and a separate one (5)."""
    values = np.zeros(shape, dtype=dtype, order="F")
    values[2:8, 2:8, 2:8] = 1
    values[8:14, 2:8, 2:8] = 2
    values[14:22, 14:22, 14:22] = 5
    return values


def image_of(values, spacing=(1.0, 1.0, 1.0)):
    image = vtkImageData()
    image.SetDimensions(*values.shape)
    image.SetSpacing(*spacing)
    array = numpy_to_vtk(values.ravel(order="F"), deep=True)
    array.SetName("labels")
    image.GetPointData().SetScalars(array)
    return image


# ---- table ------------------------------------------------------------------------


def test_scan_counts_every_label():
    pairs, truncated = labels.scan_labels(blocks())
    assert pairs == [
        (0.0, 24**3 - 2 * 6**3 - 8**3),
        (1.0, 6**3),
        (2.0, 6**3),
        (5.0, 8**3),
    ]
    assert not truncated
    # sparse values over a wide range take the sorting path
    wide = np.array([0, 3, 3, 1 << 30], dtype=np.int64)
    assert labels.scan_labels(wide) == (
        [(0.0, 1), (3.0, 2), (float(1 << 30), 1)],
        False,
    )
    assert labels.scan_labels(np.ones(4, dtype=np.float32)) == ([], False)


def test_scan_keeps_the_lowest_labels(monkeypatch):
    monkeypatch.setattr(labels, "MAX_LABELS", 2)
    pairs, truncated = labels.scan_labels(np.arange(5, dtype=np.uint8))
    assert [v for v, _ in pairs] == [0.0, 1.0]
    assert truncated


def test_what_can_be_labels():
    assert labels.can_interpret_as_label_map(np.uint8)
    assert labels.can_interpret_as_label_map(np.int16)
    assert not labels.can_interpret_as_label_map(np.float32, (0, 3))
    assert not labels.can_interpret_as_label_map(np.int32)  # range unknown
    assert labels.can_interpret_as_label_map(np.int32, (10, 10 + 65535))
    assert not labels.can_interpret_as_label_map(np.int32, (0, 65536))


def test_reconcile_keeps_what_the_user_set():
    entries = labels.reconcile([], [(0.0, 10), (1.0, 5), (2.0, 1)])
    assert [e["visible"] for e in entries] == [False, True, True]  # background
    assert entries[1]["color"] == labels.label_color(1)
    # the palette depends on the value alone
    assert entries[2]["color"] == labels.label_color(2.0) != entries[1]["color"]

    entries[1] = {**entries[1], "name": "grain", "color": "#123456", "visible": False}
    updated = labels.reconcile(entries, [(1.0, 7), (3.0, 2)])
    assert [e["value"] for e in updated] == [1.0, 3.0]
    assert updated[0] == {
        "value": 1.0,
        "name": "grain",
        "color": "#123456",
        "visible": False,
        "count": 7,
    }
    assert updated[1]["visible"]


def test_state_files_use_the_desktop_format():
    entries = labels.reconcile([], [(0.0, 1), (4.0, 1)])
    entries[1]["name"] = "pore"
    saved = labels.serialize(entries)
    assert saved["labels"][0] == {
        "value": 0.0,
        "color": list(labels.hex_to_rgb(entries[0]["color"])),
        "visible": False,
    }
    assert saved["labels"][1]["name"] == "pore"
    restored = labels.deserialize(saved)
    assert [{**e, "count": 1} for e in restored] == entries
    # a desktop table: 0-1 colors, a missing color gets the palette's
    loaded = labels.deserialize(
        {"labels": [{"value": 7}, {"value": 2, "color": [1, 0, 0]}]}
    )
    assert [e["value"] for e in loaded] == [2.0, 7.0]
    assert loaded[0]["color"] == "#ff0000"
    assert loaded[1]["color"] == labels.label_color(7)


def test_bands_give_every_label_its_color():
    entries = labels.reconcile([], [(0.0, 1), (1.0, 1), (3.0, 1)])
    colors, opacities = labels.band_points(entries)
    assert [row[0] for row in colors] == [0.0, 0.25, 0.75, 1.25, 2.75, 3.0]
    assert [row[1] for row in opacities] == [0.0, 0.0, 1.0, 1.0, 1.0, 1.0]
    single = labels.band_points(labels.reconcile([], [(3.0, 1)]))
    assert [row[0] for row in single[0]] == [3.0]


def test_lookup_table_holds_one_entry_per_label():
    entries = labels.reconcile([], [(float(v), 1) for v in (0, 1, 2, 7, 300)])
    lut = LookupTable()
    lut.set_points(labels.band_points(entries)[0], "RGB", (0, 300))
    assert lut.table.GetNumberOfTableValues() == 301
    rgb = [0.0, 0.0, 0.0]
    for entry in entries:
        lut.table.GetColor(entry["value"], rgb)
        assert labels.rgb_to_hex(rgb) == entry["color"]
    # without the range, a fixed number of samples
    lut.set_points(labels.band_points(entries)[0])
    assert lut.table.GetNumberOfTableValues() == 255


def test_descriptions_list_the_arrays_labels_fit():
    dataset = Dataset(
        {
            "labels": blocks(),
            "density": blocks().astype(np.float32),
            "ids": blocks().astype(np.int32) * 1000,
            "wide": blocks().astype(np.int64) * 100_000,
        }
    )
    description = data.describe_dataset(dataset)
    assert description.label_arrays == ["labels", "ids"]


# ---- surfaces ------------------------------------------------------------------------


def test_surface_faces_follow_visibility_and_colors():
    image = image_of(blocks())
    entries = labels.reconcile([], labels.scan_labels(blocks())[0])
    mesh = label_surface.extract_label_mesh(
        image, "labels", labels.region_labels(entries)
    )
    sides = label_surface.boundary_labels(mesh)
    # the faces between 1 and 2 are there once, tagged with both
    assert {tuple(row) for row in sides.tolist()} == {(1, 0), (1, 2), (2, 0), (5, 0)}

    everything = label_surface.select_label_faces(mesh, labels.visible_labels(entries))
    assert everything.GetNumberOfCells() == mesh.GetNumberOfCells()

    entries[3]["visible"] = False  # 5
    entries[1]["color"] = "#00ff00"
    surface = label_surface.select_label_faces(mesh, labels.visible_labels(entries))
    kept = label_surface.boundary_labels(surface)
    assert surface.GetNumberOfCells() == int((sides != 5).all(axis=1).sum())
    assert 5 not in kept
    label_surface.color_label_surface(surface, entries)
    colors = vtk_to_numpy(surface.GetCellData().GetArray("LabelColors"))
    first = kept[:, 0] == 1
    assert (colors[first] == (0, 255, 0)).all()  # the 1|2 faces take 1's
    assert surface.GetCellData().GetScalars().GetName() == "LabelColors"
    assert label_surface.select_label_faces(mesh, []).GetNumberOfCells() == 0


def test_smoothing_stays_within_half_a_voxel():
    spacing = (0.5, 0.5, 2.0)
    image = image_of(blocks(), spacing)
    regions = [1.0, 2.0, 5.0]
    raw = label_surface.extract_label_mesh(image, "labels", regions, 0)
    smooth = label_surface.extract_label_mesh(image, "labels", regions, 32)
    assert smooth.GetPointData().GetNormals() is not None
    before = vtk_to_numpy(raw.GetPoints().GetData())
    after = vtk_to_numpy(smooth.GetPoints().GetData())
    assert before.shape == after.shape
    moved = np.linalg.norm(after - before, axis=1)
    assert moved.max() > 0.1
    # float32 points: rounding of coordinates around 20
    assert moved.max() <= 0.5 * np.linalg.norm(spacing) + 1e-4


def test_no_surface_without_regions_or_depth():
    assert (
        label_surface.extract_label_mesh(
            image_of(blocks()), "labels", []
        ).GetNumberOfCells()
        == 0
    )
    flat = image_of(blocks()[:, :, 3:4])
    assert (
        label_surface.extract_label_mesh(flat, "labels", [1.0]).GetNumberOfCells() == 0
    )


@pytest.mark.parametrize("dtype", [np.uint16, np.int32])
def test_surfaces_of_wider_labels(dtype):
    image = image_of(blocks(dtype=dtype))
    mesh = label_surface.extract_label_mesh(image, "labels", [1.0, 2.0, 5.0])
    assert mesh.GetNumberOfCells() > 0
