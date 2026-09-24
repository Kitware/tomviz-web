"""Load synthetic state files into a headless app session.

One session for both formats: the second load also exercises
``PipelineManager.reset``.
"""

import asyncio
import json

import numpy as np
import pytest
from tomviz_pipeline import DefaultExecutor, SinkGroupNode
from tomviz_pipeline.core.state import pipeline_from_state_dict
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.state import write_state_tvh5
from vtkmodules.vtkIOImage import vtkTIFFWriter

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.nodes import RepresentationSinkNode, register_nodes
from tomviz_web.app.pipeline.vtk import convert

SHAPE = (3, 4, 5)
VIEW_ID = 42
CAMERA = {
    "position": [1.0, 2.0, 30.0],
    "focalPoint": [1.0, 2.0, 2.0],
    "viewUp": [0.0, 1.0, 0.0],
    "viewAngle": 30.0,
    "parallelScale": 5.0,
}
COLOR_MAP = {
    "colorSpace": "CIELAB",
    "colors": [10.0, 0.0, 0.0, 1.0, 20.0, 1.0, 0.0, 0.0],
    "points": [10.0, 0.0, 0.5, 0.0, 20.0, 1.0, 0.5, 0.0],
}


def state_dict(tiff_path):
    return {
        "schemaVersion": 2,
        "paletteColor": [0.9, 0.9, 0.9],
        "pipeline": {
            "nextNodeId": 5,
            "nodes": [
                {
                    "id": 1,
                    "type": "source.reader",
                    "label": "volume",
                    "fileNames": [str(tiff_path)],
                    "outputPorts": {
                        "volume": {
                            "type": "ImageData",
                            "persistent": True,
                            "metadata": {"colorOpacityMap": COLOR_MAP},
                        }
                    },
                },
                {
                    "id": 2,
                    "type": "sinkGroup",
                    "label": "Visualizations",
                    "inputPorts": {"volume": {"type": ["ImageData"]}},
                    "outputPorts": {
                        "volume": {"persistent": False, "type": "ImageData"}
                    },
                    "typeInferenceSources": {"volume": "volume"},
                },
                {
                    "id": 3,
                    "type": "sink.slice",
                    "label": "Slice",
                    "inputPorts": {"volume": {"type": ["ImageData"]}},
                    "direction": 1,
                    "slice": 2,
                    "interpolate": True,
                    "viewId": VIEW_ID,
                },
                {
                    "id": 4,
                    "type": "sink.outline",
                    "label": "Outline",
                    "inputPorts": {"volume": {"type": ["ImageData"]}},
                    "visible": False,
                    "viewId": VIEW_ID,
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
                {
                    "from": {"node": 2, "port": "volume"},
                    "to": {"node": 4, "port": "volume"},
                },
            ],
        },
        "views": [
            {
                "id": VIEW_ID,
                "active": True,
                "interactionMode": "3D",
                "backgroundColor": [[0.1, 0.2, 0.3]],
                "camera": CAMERA,
                "isOrthographic": False,
            },
            {"id": VIEW_ID + 1, "interactionMode": "2D"},
        ],
        # The desktop's layout: the two views side by side, 40 / 60.
        "layouts": [
            {
                "id": 1,
                "items": [
                    [
                        {"direction": 2, "fraction": 0.4, "viewId": 0},
                        {"direction": 0, "fraction": 0.5, "viewId": VIEW_ID},
                        {"direction": 0, "fraction": 0.5, "viewId": VIEW_ID + 1},
                    ]
                ],
            }
        ],
    }


@pytest.fixture
def state_files(tmp_path):
    values = np.arange(np.prod(SHAPE), dtype=np.uint16).reshape(SHAPE, order="F")
    tiff_path = tmp_path / "volume.tif"
    writer = vtkTIFFWriter()
    writer.SetFileName(str(tiff_path))
    writer.SetInputData(convert.to_vtk_image(Dataset({"scalars": values})))
    writer.Write()

    raw = state_dict(tiff_path)
    tvsm = tmp_path / "session.tvsm"
    tvsm.write_text(json.dumps(raw))

    # A .tvh5 bundles the executed reader's payload.
    register_nodes()
    pipeline = pipeline_from_state_dict(raw)
    assert DefaultExecutor(pipeline).execute()
    tvh5 = tmp_path / "session.tvh5"
    write_state_tvh5(tvh5, raw, pipeline)
    return tvsm, tvh5


async def wait_idle(manager):
    for _ in range(200):
        if not manager.pipeline.is_executing():
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)  # loop callbacks and background statistics


def sinks_of(manager):
    return {
        m.node.id: m
        for m in manager.model.nodes
        if isinstance(m, data_model.SinkNodeModel)
    }


async def run_session(tvsm, tvh5):
    from tomviz_web.app.core import Tomviz

    app = Tomviz()
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await server.ready
    manager = app.ctx.pipeline
    executed = []
    manager.executor.node_execution_started.connect(lambda n: executed.append(n.id))
    layouts = []
    manager.restore_layout = layouts.append  # what would reach dockview

    try:
        # ---- .tvsm: everything re-executes
        await manager.load_state_file(tvsm)
        await wait_idle(manager)
        check_session(manager, server)
        check_layout(manager, server, layouts[-1])
        assert executed[0] == 1  # the reader ran first
        assert set(executed) == {1, 2, 3, 4}

        # ---- .tvh5 in the same session: reset, then only the sinks run
        executed.clear()
        await manager.load_state_file(tvh5)
        await wait_idle(manager)
        check_session(manager, server)
        assert set(executed) == {2, 3, 4}  # the group runs (trivially) too
        assert len(manager.views) == 2
        assert len(layouts) == 2  # one restore per load
        assert len(manager.model.nodes) == 4
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


def check_session(manager, server):
    pipeline = manager.pipeline
    sinks = sinks_of(manager)
    assert set(sinks) == {3, 4}
    assert all(
        isinstance(pipeline.node_by_id(i), RepresentationSinkNode) for i in sinks
    )

    source = manager.model.roots[0]
    assert source.label == "volume"
    assert manager.model.active_node == [source._id]
    port = source.primary_output_model
    assert port.has_data
    assert port.image.dimensions == SHAPE
    assert port.data_location == "memory"
    assert server.state.tip_port_id == port._id
    assert server.state.active_port_id == port._id

    # The desktop's sink group survives: the sinks read the reader's port
    # through its passthrough, and the models mirror the links.
    group = manager.node_models[2]
    assert isinstance(group, data_model.SinkGroupNodeModel)
    assert isinstance(pipeline.node_by_id(2), SinkGroupNode)
    assert group.inputs[0].link is port
    assert group.state == "Current"
    for sink in sinks.values():
        assert sink.inputs[0].link is group.outputs[0]
        assert sink.source_port is port
        assert sink.state == "Current"

    slice_model, outline = sinks[3], sinks[4]
    assert (slice_model.SliceDirection, slice_model.Slice) == ("YZ Plane", 2)
    assert slice_model.SliceMax == SHAPE[0] - 1
    assert slice_model.Interpolate is True
    representation = slice_model.representation
    assert representation.property.GetInterpolationTypeAsString() == "Linear"
    assert representation.actor.visibility
    assert outline.Visibility is False
    assert not outline.representation.actor.visibility

    color_map = port.color_opacity
    assert color_map.color_space == "Lab"
    assert color_map.color_range == [10.0, 20.0]  # kept from the file
    assert color_map.data_range[:2] == (0.0, float(np.prod(SHAPE) - 1))

    view = slice_model.view
    assert server.state.active_view_id == view._id
    assert view.background == (0.1, 0.2, 0.3)
    assert view.camera_initialized
    camera = view.vtk_view.camera
    assert camera["position"] == CAMERA["position"]  # not refit by the data
    assert camera["parallelProjection"] is False


def check_layout(manager, server, layout):
    """The two windows side by side, 40 / 60, the first one active."""
    active = manager.views[server.state.active_view_id]
    other = next(v for v in manager.views.values() if v is not active)
    grid = layout["grid"]
    assert grid["orientation"] == "HORIZONTAL"
    left, right = grid["root"]["data"]
    assert (left["data"]["views"], left["size"]) == ([active.vtk_id], 400.0)
    assert (right["data"]["views"], right["size"]) == ([other.vtk_id], 600.0)
    assert layout["activeGroup"] == left["data"]["id"]
    entry = layout["panels"][active.vtk_id]
    assert entry["contentComponent"] == "DockPanel"
    assert entry["tabComponent"] == "tomviz-dockview-tab"
    assert entry["params"] == {
        "templateName": active.tpl_name,
        "viewState": active.local_state._id,
    }
    assert other.local_state.interactive_3d is False


def test_state_files_load_into_a_session(state_files, tmp_path, monkeypatch):
    # The app reads its catalog configuration from the command line (default:
    # the user's home); keep the test off the developer's own files.
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"directories": [], "modules": [], "favorites": []}))
    # Under pytest, trame only reads its arguments from TRAME_ARGS.
    monkeypatch.setenv(
        "TRAME_ARGS",
        f"--catalog {catalog} --settings {catalog.parent / 'settings.json'} --read-only",
    )
    asyncio.run(run_session(*state_files))
