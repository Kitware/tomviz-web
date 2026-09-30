"""The label map sink in a headless app session: a plain integer volume is
adopted with a table of its own; a label map port's table is shared by its
sinks and colors them all."""

import asyncio
import json

import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.writers import write_emd
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

from tomviz_web.app import data_model
from tomviz_web.app.pipeline import state as state_module
from tomviz_web.app.utils.colors import rgb_to_hex

SHAPE = (24, 24, 24)
LABELS = (0.0, 50.0, 60.0, 200.0)


@pytest.fixture
def labels_file(tmp_path):
    """Background, two touching cubes (50, 60) and a separate one (200),
    as a segmentation read from a file: a plain uint8 volume."""
    values = np.zeros(SHAPE, dtype=np.uint8, order="F")
    values[2:8, 2:8, 2:8] = 50
    values[8:14, 2:8, 2:8] = 60
    values[14:22, 14:22, 14:22] = 200
    path = tmp_path / "labels.emd"
    write_emd(Dataset({"labels": values}), path)
    return path


@pytest.fixture
def app_args(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"directories": [], "modules": [], "favorites": []}))
    monkeypatch.setenv(
        "TRAME_ARGS",
        f"--catalog {catalog} --settings {tmp_path / 'settings.json'} --read-only",
    )


async def wait_idle(manager):
    for _ in range(200):
        if not manager.pipeline.is_executing():
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)


async def wait_mesh(representation):
    """The surface is extracted in the background after a new smoothing."""
    for _ in range(100):
        await asyncio.sleep(0.05)
        if representation._pending_mesh is None:
            return
    pytest.fail("the surface was never extracted")


def lut_color(color_opacity, value):
    rgb = [0.0, 0.0, 0.0]
    color_opacity.lut.table.GetColor(value, rgb)
    return rgb_to_hex(rgb)


def face_colors(representation):
    colors = representation.surface.GetCellData().GetArray("LabelColors")
    return {rgb_to_hex(c / 255) for c in vtk_to_numpy(colors)}


def shows_color(vtk_view, color, size=100):
    window = vtk_view.render_window
    window.SetSize(size, size)
    window.Render()
    grab = vtkWindowToImageFilter()
    grab.SetInput(window)
    grab.Update()
    pixels = vtk_to_numpy(grab.GetOutput().GetPointData().GetScalars())[:, :3]
    target = np.array([int(color[i : i + 2], 16) for i in (1, 3, 5)])
    # lit, not exact: a hue match on the brightest pixels near the color
    normalized = pixels / np.maximum(pixels.max(axis=1, keepdims=True), 1)
    return int((np.abs(normalized - target / target.max()).sum(axis=1) < 0.15).sum())


async def run_session(path):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server="label-map-session")
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await server.ready
    manager, state = app.ctx.pipeline, server.state

    def add(kind):
        return data_model.get_instance(manager.add_sink(state.active_view_id, kind))

    try:
        manager.load_file(path)
        await wait_idle(manager)
        # integers few enough to be labels: offered
        assert "LABEL_MAP" in state.tip_representations
        sinks = {m.representation_type: m for m in manager._sink_models()}
        reader_port = sinks["SLICE"].source_port
        assert not reader_port.is_label_map

        model = add("LABEL_MAP")
        await wait_idle(manager)
        representation = model.representation
        table = model.label_table

        # ---- adopted: a table and a color map of its own
        assert model.LabelsAdopted
        assert [e["value"] for e in table.labels] == list(LABELS)
        assert [e["count"] for e in table.labels][1:] == [216, 216, 512]
        assert [e["visible"] for e in table.labels] == [False, True, True, True]
        assert model.use_internal_color_opacity
        own = model.color_opacity
        assert own is not reader_port.color_opacity
        assert own.label_range == (0.0, 200.0)
        assert own.lut.table.GetNumberOfTableValues() == 201
        for entry in table.labels:
            assert lut_color(own, entry["value"]) == entry["color"]
        # the port's map, which the slice shows, is left alone
        assert reader_port.color_opacity.label_range is None
        assert reader_port.label_table is None

        # ---- the desktop's defaults: a smoothed surface, the volume look
        assert (model.Representation, model.SurfaceSmoothing) == ("Surface", 16)
        assert representation.surface_actor.GetVisibility()
        assert not representation.actor.GetVisibility()
        assert representation.surface.GetPointData().GetNormals() is not None
        assert face_colors(representation) == {e["color"] for e in table.labels[1:]}
        assert model.InterpolationType == "Nearest"
        assert model.BlendMode == "Composite"
        assert model.Ambient == pytest.approx(0.3)  # the floor over Simple's 0.1

        # ---- edits: hiding re-selects faces, colors rewrite them and the map
        cells = representation.surface.GetNumberOfCells()
        table.set_visible(200, False)
        assert representation.surface.GetNumberOfCells() < cells
        assert own.pwf.function.GetValue(200.0) == 0.0
        table.set_color(50, "#0000ff")
        assert "#0000ff" in face_colors(representation)
        assert lut_color(own, 50) == "#0000ff"
        table.set_name(60, "  pore ")
        assert table.labels[2]["name"] == "pore"
        table.invert_visibility([0.0, 50.0, 60.0, 200.0])
        assert [e["visible"] for e in table.labels] == [True, False, False, True]
        table.set_visibility([50.0, 200.0], True)
        table.set_visible(0, False)
        assert [e["visible"] for e in table.labels] == [False, True, False, True]

        # it draws, in the label's color
        for sink in manager._sink_models():
            if sink is not model:
                sink.Visibility = False
        await asyncio.sleep(0.1)
        vtk_view = model.view.vtk_view
        vtk_view.orientation_axes_visibility = False
        vtk_view.reset_camera()
        assert shows_color(vtk_view, "#0000ff") > 20

        # ---- raw voxel faces: extracted again in the background
        model.SurfaceSmoothing = 0
        await wait_mesh(representation)
        assert representation.surface.GetPointData().GetNormals() is None
        assert representation.surface_actor.GetVisibility()

        # ---- the volume: nearest, composite and a half-voxel step, pinned
        model.Representation = "Volume"
        await asyncio.sleep(0.1)
        assert representation.actor.GetVisibility()
        assert not representation.surface_actor.GetVisibility()
        model.InterpolationType = "Linear"
        model.BlendMode = "Max"
        await asyncio.sleep(0.1)
        assert (model.InterpolationType, model.BlendMode) == ("Nearest", "Composite")
        assert representation.property.GetInterpolationType() == 0
        assert representation.mapper.GetBlendMode() == 0
        assert not representation.mapper.GetAutoAdjustSampleDistances()
        assert representation.mapper.GetSampleDistance() == pytest.approx(0.5)
        # its own map cannot be switched off: the labels have nowhere else
        model.use_internal_color_opacity = False
        await asyncio.sleep(0.1)
        assert model.use_internal_color_opacity
        assert shows_color(vtk_view, "#0000ff") > 20
        model.Representation = "Surface"
        await asyncio.sleep(0.1)

        # ---- a label map port: the kernel's output, where the sinks move
        manager.model.active_node = [reader_port.node._id]
        await asyncio.sleep(0.1)
        transform = data_model.get_instance(manager.add_transform("BinaryThreshold"))
        await wait_idle(manager)
        port = transform.outputs[0]
        assert port.is_label_map
        assert [e["value"] for e in port.label_table.labels] == [0.0, 1.0]
        # its shared map shows the table, one entry per label
        shared = port.color_opacity
        assert shared.label_range == (0.0, 1.0)
        assert lut_color(shared, 1) == port.label_table.labels[1]["color"]

        # the moved label map now shows the port's table
        await wait_mesh(representation)
        assert model.source_port is port
        assert not model.LabelsAdopted
        assert model.label_table is port.label_table
        assert face_colors(representation) == {port.label_table.labels[1]["color"]}

        # a slice on the port colors through the shared map
        slice_model = sinks["SLICE"]
        assert slice_model.source_port is port
        assert slice_model.color_opacity is shared

        # a volume there switches to nearest interpolation, once
        manager.model.active_node = [port._id]
        await asyncio.sleep(0.1)
        assert "LABEL_MAP" in state.tip_representations
        volume = add("VOLUME")
        await wait_idle(manager)
        assert volume.InterpolationType == "Nearest"
        assert volume.label_map_defaults_applied

        # an edit of the port's table reaches every sink on it
        port.label_table.set_color(1, "#ff0000")
        assert lut_color(shared, 1) == "#ff0000"
        assert face_colors(representation) == {"#ff0000"}
        # and survives the next execution
        manager.execute()
        await wait_idle(manager)
        assert port.label_table.labels[1]["color"] == "#ff0000"
        assert lut_color(shared, 1) == "#ff0000"

        # a table saved on the port (a state file's metadata) is taken, and
        # reconciled with the data once described (as a .tvh5 load does)
        saved = {"labels": [{"value": 1, "name": "grain", "color": [0, 0, 1]}]}
        state_module.apply_port_metadata(
            transform, {"outputPorts": {port.name: {"metadata": {"labelMap": saved}}}}
        )
        assert [e["value"] for e in port.label_table.labels] == [1.0]
        manager.describe_ports(transform)
        assert [e["value"] for e in port.label_table.labels] == [0.0, 1.0]
        assert port.label_table.labels[1]["name"] == "grain"
        assert lut_color(shared, 1) == "#0000ff"
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


def test_label_map(labels_file, app_args):  # noqa: ARG001
    asyncio.run(run_session(labels_file))


# ---- state files ---------------------------------------------------------------


def state_dict(path):
    """A plain volume a label map sink adopted, with its table."""
    return {
        "schemaVersion": 2,
        "pipeline": {
            "nextNodeId": 4,
            "nodes": [
                {
                    "id": 1,
                    "type": "source.reader",
                    "label": "labels",
                    "fileNames": [str(path)],
                    "outputPorts": {"volume": {"type": "Volume", "persistent": True}},
                },
                {
                    "id": 2,
                    "type": "sinkGroup",
                    "label": "Visualizations",
                    "inputPorts": {"volume": {"type": ["Volume"]}},
                    "outputPorts": {"volume": {"persistent": False, "type": "Volume"}},
                    "typeInferenceSources": {"volume": "volume"},
                },
                {
                    "id": 3,
                    "type": "sink.labelMap",
                    "label": "Label Map",
                    "inputPorts": {"volume": {"type": ["ImageData"]}},
                    "viewId": 1,
                    "adoptedLabelMap": {
                        "labels": [
                            {"value": 50, "name": "grain", "color": [0, 1, 0]},
                            {"value": 200, "color": [0, 0, 1], "visible": False},
                        ]
                    },
                    "volumeLookApplied": False,
                    "surfaceOpacity": 0.5,
                },
            ],
            "links": [
                {
                    "from": {"node": 1, "port": "volume"},
                    "to": {"node": 2, "port": "volume"},
                },
                {
                    "from": {"node": 2, "port": "volume"},
                    "to": {"node": 3, "port": "volume"},
                },
            ],
        },
        "views": [{"id": 1, "active": True, "interactionMode": "3D"}],
    }


async def run_state_session(tvsm):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server="label-map-state")
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await server.ready
    manager = app.ctx.pipeline

    try:
        await manager.load_state_file(tvsm)
        await wait_idle(manager)
        (model,) = manager._sink_models()
        assert model.representation_type == "LABEL_MAP"

        # the saved table, reconciled with the data
        assert model.LabelsAdopted
        by_value = {e["value"]: e for e in model.label_table.labels}
        assert list(by_value) == list(LABELS)
        assert by_value[50.0]["name"] == "grain"
        assert by_value[50.0]["color"] == "#00ff00"
        assert not by_value[200.0]["visible"]
        assert by_value[60.0]["visible"]  # not in the file: a new label
        assert lut_color(model.color_opacity, 50) == "#00ff00"
        # a file from before the surface existed was showing a volume
        assert model.Representation == "Volume"
        assert model.SurfaceOpacity == 0.5
        # the ambient floor was not applied yet when the file was saved
        assert model.Ambient == pytest.approx(0.3)
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


def test_label_map_state(labels_file, app_args, tmp_path):  # noqa: ARG001
    tvsm = tmp_path / "labels.tvsm"
    tvsm.write_text(json.dumps(state_dict(labels_file)))
    asyncio.run(run_state_session(tvsm))
