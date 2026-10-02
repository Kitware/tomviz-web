"""Catalog sources (schema-v2 kernels without inputs) in a headless app
session: added like a loaded file (a new root, the tip, the default
visualizations), with a parameters panel, and restored from state files with
their parameters."""

import asyncio
import json
from types import SimpleNamespace

import numpy as np
import tomviz_kernels

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.nodes import build_source_node
from tomviz_web.app.ui.drawer_transforms import TransformSelection


async def wait_idle(manager):
    for _ in range(200):
        if not manager.pipeline.is_executing():
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)


async def start(server_name):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server=server_name)
    serve = asyncio.create_task(
        app.server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await app.server.ready
    return app, serve


async def stop(app, serve):
    app.ctx.pipeline.shutdown()
    await app.server.stop()
    serve.cancel()


def sinks_reading(manager, port_model):
    return {
        m.representation_type: m.state
        for m in manager.model.nodes
        if isinstance(m, data_model.SinkNodeModel) and m.source_port is port_model
    }


def scalars(model):
    return model.outputs[0].payload.active_scalars


async def run_session():
    app, serve = await start("sources-session")
    manager, state = app.ctx.pipeline, app.server.state
    try:
        # ---- before any data, the picker can add a source, not a transform
        assert not state.tip_port_id
        items = {item.name: item for item in catalog_items(app.ctx.catalog.root)}
        for name, is_source in (("ConstantDataset", True), ("GaussianFilter", False)):
            state.transform_activated = [items[name]._id]
            state.flush()  # runs the picker's change handler
            assert state.transform_activated_source is is_source
        state.transform_activated = []
        state.flush()
        assert state.transform_activated_source is False

        # ---- a source starts a pipeline, like loading a file
        constant = data_model.get_instance(
            manager.add_source(
                "ConstantDataset", parameters={"shape": [4, 5, 6], "value": 2.0}
            )
        )
        await wait_idle(manager)
        assert isinstance(constant, data_model.SourceNodeModel)
        assert constant.node.type_name == "source.python"
        assert constant.state == "Current"
        output = constant.outputs[0]
        assert state.tip_port_id == output._id
        assert sinks_reading(manager, output) == {
            "OUTLINE": "Current",
            "SLICE": "Current",
        }
        assert scalars(constant).shape == (4, 5, 6)
        assert np.all(scalars(constant) == 2.0)

        # ---- its parameters are in the panel; Apply re-runs it
        assert manager.model.active_node == [constant._id]
        assert state.property_templates == ["transform"]
        assert constant.entry_name == "ConstantDataset"
        assert {"shape", "value"} == constant.parameters.FIELD_NAMES
        assert constant.parameters.value == 2.0
        constant.parameters.value = 7.0
        constant._on_parameters_change(7.0)  # the watcher, called directly
        assert constant.parameters_dirty is True
        constant.apply_parameters()
        await wait_idle(manager)
        assert constant.node.parameter("value") == 7.0
        assert np.all(scalars(constant) == 7.0)

        # ---- transforms go at its tip
        invert = data_model.get_instance(manager.add_transform("InvertData"))
        await wait_idle(manager)
        assert invert.state == "Current"
        assert invert.input is constant

        # ---- another source is another root
        particles = data_model.get_instance(
            manager.add_source("RandomParticles", parameters={"shape": [8, 8, 8]})
        )
        await wait_idle(manager)
        assert particles.state == "Current"
        assert scalars(particles).shape == (8, 8, 8)
        assert state.tip_port_id == particles.outputs[0]._id
        assert invert.input is constant

        # ---- the drawer's add button sends a source to add_source, held
        # until its editor is confirmed
        item = next(
            i
            for i in catalog_items(app.ctx.catalog.root)
            if i.name == "ConstantDataset"
        )
        drawer = SimpleNamespace(ctx=app.ctx, state=app.state, ctrl=app.ctrl)
        TransformSelection.add_entry(drawer, item._id)
        await wait_idle(manager)
        sources = [
            m for m in manager.model.nodes if isinstance(m, data_model.SourceNodeModel)
        ]
        assert len(sources) == 3
        assert sources[-1].entry_name == "ConstantDataset"
        assert manager.is_pending(sources[-1]._id)
        assert sources[-1].state == "New"
        editor = app.ctx.transform_editor
        assert editor.editor.show
        assert editor.editor.transform_id == sources[-1]._id
        editor.ok()
        await wait_idle(manager)
        assert sources[-1].state == "Current"
    finally:
        await stop(app, serve)


def catalog_items(folder):
    for child in folder.children:
        if isinstance(child, data_model.CatalogFolder):
            yield from catalog_items(child)
        else:
            yield child


async def run_state_session(tvsm):
    app, serve = await start("sources-state-session")
    manager = app.ctx.pipeline
    try:
        await manager.load_state_file(tvsm)
        await wait_idle(manager)
        (source,) = [
            m for m in manager.model.nodes if isinstance(m, data_model.SourceNodeModel)
        ]
        assert source.entry_name == "ConstantDataset"
        assert {"shape", "value"} == source.parameters.FIELD_NAMES
        assert source.parameters.value == 3.0
        assert source.parameters_dirty is False
        assert source.state == "Current"
        assert np.all(scalars(source) == 3.0)
    finally:
        await stop(app, serve)


def session_args(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"directories": [], "modules": [], "favorites": []}))
    # Under pytest, trame only reads its arguments from TRAME_ARGS.
    monkeypatch.setenv(
        "TRAME_ARGS",
        f"--catalog {catalog} --settings {tmp_path / 'settings.json'} --read-only",
    )


def test_sources_in_a_session(tmp_path, monkeypatch):
    session_args(tmp_path, monkeypatch)
    asyncio.run(run_session())


def test_a_saved_source_keeps_its_parameters(tmp_path, monkeypatch):
    session_args(tmp_path, monkeypatch)
    kernels = tomviz_kernels.directory()
    description = json.loads((kernels / "ConstantDataset.json").read_text())
    node = build_source_node(
        description,
        kernels / "ConstantDataset.py",
        {"shape": [3, 4, 5], "value": 3.0},
    )
    tvsm = tmp_path / "source.tvsm"
    tvsm.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "pipeline": {
                    "nextNodeId": 2,
                    "nodes": [{"id": 1, "type": node.type_name, **node.serialize()}],
                    "links": [],
                },
            }
        )
    )
    asyncio.run(run_state_session(tvsm))
