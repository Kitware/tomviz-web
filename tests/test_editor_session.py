"""The transform editor, driven through the app: it stages a copy of a
catalog node's name, definition and script; Cancel drops every edit
(the parameter panel's too), Apply commits them all through the library
(rebuilding the parameters panel when the declared parameters change) and
re-executes; an edit the library refuses leaves the node untouched.

A new node waits for the editor before it runs: OK runs it, Cancel removes
it and puts the graph back without re-running anything. A node with more
inputs waits once its last input is linked, and Cancel removes that link."""

import asyncio
import json

import numpy as np
from tomviz_pipeline import SinkGroupNode
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.writers import write_emd

from tomviz_web.app import data_model

SHAPE = (4, 4, 3)

SCALE_DEFINITION = {
    "schemaVersion": 2,
    "name": "Scale",
    "label": "Scale",
    "inputs": [{"name": "volume", "type": "ImageData"}],
    "outputs": [{"name": "volume", "type": "ImageData"}],
    "parameters": [{"name": "factor", "type": "double", "default": 2.0}],
}

SCALE_SCRIPT = """\
from tomviz_pipeline.kernels import TransformKernel


class Scale(TransformKernel):
    def transform(self, inputs, factor=2.0, **_):
        dataset = inputs["volume"]
        dataset.active_scalars = dataset.active_scalars * factor
        return {"volume": dataset}
"""

OFFSET_SCRIPT = SCALE_SCRIPT.replace("* factor", "* factor + _.get('offset', 0.0)")


def ramp():
    size = int(np.prod(SHAPE))
    return np.arange(size, dtype=np.float32).reshape(SHAPE, order="F")


async def wait_idle(manager):
    for _ in range(200):
        if not manager.pipeline.is_executing():
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)


def scalars(model):
    return model.node.output_ports()[0].data().payload.active_scalars


def with_parameters(definition, *parameters):
    return {**definition, "parameters": list(parameters)}


async def run_session(volume_file):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server="editor-session")
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await asyncio.sleep(0.5)
    manager = app.ctx.pipeline
    dialog = app.ctx.transform_editor
    editor = dialog.editor

    try:
        manager.load_file(volume_file)
        await wait_idle(manager)

        # A v1 script is editable too.
        blur = data_model.get_instance(
            manager.add_transform("GaussianFilter", parameters={"sigma": 1.0})
        )
        await wait_idle(manager)
        dialog.open(blur._id)
        assert editor.definition["name"] == "GaussianFilter"
        assert editor.script
        assert editor.script == blur.node.script
        dialog.cancel()
        blurred = scalars(blur)

        scale = data_model.get_instance(manager.add_transform("Scale"))
        await wait_idle(manager)
        assert scale.state == "Current"
        np.testing.assert_allclose(scalars(scale), blurred * 2.0)

        # Opening stages a copy of the node's name, definition and script.
        dialog.open(scale._id)
        assert editor.show
        assert (editor.label, editor.definition, editor.script) == (
            "Scale",
            SCALE_DEFINITION,
            SCALE_SCRIPT,
        )

        # Cancel drops every edit, the parameter panel's included.
        editor.label = "Renamed"
        editor.script = OFFSET_SCRIPT
        editor.definition = with_parameters(SCALE_DEFINITION)
        scale.parameters.factor = 3.0
        dialog.cancel()
        assert not editor.show
        assert scale.node.label == "Scale"
        assert scale.node.script == SCALE_SCRIPT
        assert json.loads(scale.node.json_description) == SCALE_DEFINITION
        assert scale.node.parameter("factor") == 2.0
        assert scale.parameters.factor == 2.0
        assert scale.node.state.value == "Current"

        # Apply commits them all and runs once: a new parameter gets a
        # field, and the panel value typed before carries over to it.
        dialog.open(scale._id)
        assert editor.script == SCALE_SCRIPT
        panel = scale.parameters
        scale.parameters.factor = 3.0
        editor.label = "Scaled"
        editor.script = OFFSET_SCRIPT
        editor.definition = with_parameters(
            SCALE_DEFINITION,
            *SCALE_DEFINITION["parameters"],
            {"name": "offset", "type": "double", "default": 1.0},
        )
        assert dialog.apply()
        assert editor.message_type == "success"
        assert scale.node.label == scale.label == "Scaled"
        assert scale.parameters is not panel
        assert scale.parameters.offset == 1.0
        assert scale.node.parameter("factor") == 3.0
        assert scale.definition == editor.definition
        await wait_idle(manager)
        assert scale.state == "Current"
        np.testing.assert_allclose(scalars(scale), blurred * 3.0 + 1.0)

        # Retyping a parameter resets its value, and says so.
        retyped = with_parameters(
            SCALE_DEFINITION,
            {"name": "factor", "type": "int", "default": 4},
            {"name": "offset", "type": "double", "default": 1.0},
        )
        editor.definition = retyped
        assert dialog.apply()
        assert editor.message_type == "warning"
        assert "factor" in editor.message
        assert scale.node.parameter("factor") == 4
        await wait_idle(manager)

        # An edit changing the ports is refused, and OK stays open on it.
        before = scale.node.json_description
        panel = scale.parameters
        editor.definition = {
            **retyped,
            "outputs": [{"name": "other", "type": "ImageData"}],
        }
        dialog.ok()
        assert editor.show
        assert editor.message_type == "error"
        assert "outputs" in editor.message
        assert scale.node.json_description == before
        assert scale.parameters is panel

        # OK applies and closes.
        editor.definition = retyped
        editor.label = "Final"
        dialog.ok()
        assert not editor.show
        assert scale.node.label == "Final"
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


async def run_pending_session(volume_file, other_file):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server="pending-session")
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await asyncio.sleep(0.5)
    manager = app.ctx.pipeline
    dialog = app.ctx.transform_editor

    def group_feed():
        group = next(n for n in manager.pipeline.nodes if isinstance(n, SinkGroupNode))
        return group, group.input_ports()[0].link.from_port

    def sinks():
        return [
            m for m in manager.model.nodes if isinstance(m, data_model.SinkNodeModel)
        ]

    try:
        source = data_model.get_instance(manager.load_file(volume_file))
        await wait_idle(manager)
        group, feed = group_feed()
        assert feed is source.node.output_ports()[0]
        selection = list(manager.model.active_node)

        # A new node is held: the visualizations move to it, nothing runs.
        scale = data_model.get_instance(manager.add_transform("Scale", pending=True))
        assert manager.is_pending(scale._id)
        assert scale.node.breakpoint
        assert scale.breakpoint
        assert group_feed()[1] is scale.node.output_ports()[0]
        manager.execute()
        await wait_idle(manager)
        assert scale.node.state.value == "New"

        # Cancel: the graph as it was, nothing stale, the pictures kept.
        dialog.open(scale._id)
        dialog.cancel()
        await wait_idle(manager)
        assert scale.node not in manager.pipeline.nodes
        assert group_feed()[1] is feed
        assert group.state.value == "Current"
        for sink in sinks():
            assert sink.node.state.value == "Current"
            assert sink.source_port is source.outputs[0]
            assert sink.node._has_data
        assert manager.model.active_node == selection
        assert not manager.pipeline.is_executing()

        # OK releases it and runs it.
        scale = data_model.get_instance(manager.add_transform("Scale", pending=True))
        dialog.open(scale._id)
        dialog.ok()
        await wait_idle(manager)
        assert not manager.is_pending(scale._id)
        assert not scale.node.breakpoint
        assert scale.state == "Current"
        np.testing.assert_allclose(scalars(scale), ramp() * 2.0)

        # After an Apply the node is committed: Cancel only closes.
        again = data_model.get_instance(manager.add_transform("Scale", pending=True))
        dialog.open(again._id)
        assert dialog.apply()
        await wait_idle(manager)
        dialog.cancel()
        assert again.node in manager.pipeline.nodes
        assert again.state == "Current"

        # A node with more inputs is not held while some are unlinked...
        combine = data_model.get_instance(
            manager.add_transform("combine_datasets", pending=True)
        )
        assert not manager.is_pending(combine._id)
        assert not combine.node.breakpoint
        second = combine.inputs[1]
        other = data_model.get_instance(manager.load_file(other_file))
        await wait_idle(manager)

        # ...but once the last one is linked; Cancel removes that link and
        # leaves the user's own breakpoint alone.
        manager.toggle_breakpoint(combine._id)
        assert manager.create_link(other.outputs[0]._id, second._id)
        assert manager.is_pending(combine._id)
        dialog.open(combine._id)
        dialog.cancel()
        assert combine.node in manager.pipeline.nodes
        assert second.port.link is None
        assert combine.node.breakpoint
        manager.toggle_breakpoint(combine._id)

        assert manager.create_link(other.outputs[0]._id, second._id)
        await wait_idle(manager)
        assert manager.is_pending(combine._id)
        assert combine.state != "Current"
        dialog.open(combine._id)
        dialog.ok()
        await wait_idle(manager)
        assert combine.state == "Current"

        # A catalog source is held too, and gets its visualizations once
        # confirmed; Cancel removes it.
        count = len(sinks())
        selection = list(manager.model.active_node)
        constant = data_model.get_instance(
            manager.add_source("ConstantDataset", pending=True)
        )
        assert manager.is_pending(constant._id)
        assert len(sinks()) == count
        manager.execute()
        await wait_idle(manager)
        assert constant.node.state.value == "New"
        dialog.open(constant._id)
        dialog.cancel()
        assert constant.node not in manager.pipeline.nodes
        assert manager.model.active_node == selection

        constant = data_model.get_instance(
            manager.add_source("ConstantDataset", pending=True)
        )
        dialog.open(constant._id)
        dialog.ok()
        await wait_idle(manager)
        assert constant.state == "Current"
        added = sinks()[count:]
        assert len(added) == 2
        assert all(s.source_port is constant.outputs[0] for s in added)
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


def test_new_nodes_wait_for_the_editor(tmp_path, monkeypatch):
    kernels = tmp_path / "kernels"
    kernels.mkdir()
    (kernels / "Scale.json").write_text(json.dumps(SCALE_DEFINITION))
    (kernels / "Scale.py").write_text(SCALE_SCRIPT)

    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({"directories": [str(kernels)], "modules": [], "favorites": []})
    )
    monkeypatch.setenv(
        "TRAME_ARGS",
        f"--catalog {catalog} --settings {tmp_path / 'settings.json'} --read-only",
    )
    volume = tmp_path / "volume.emd"
    write_emd(Dataset({"scalars": ramp()}), volume)
    other = tmp_path / "other.emd"
    write_emd(Dataset({"other": ramp()}), other)
    asyncio.run(run_pending_session(volume, other))


def test_editing_a_catalog_node(tmp_path, monkeypatch):
    kernels = tmp_path / "kernels"
    kernels.mkdir()
    (kernels / "Scale.json").write_text(json.dumps(SCALE_DEFINITION))
    (kernels / "Scale.py").write_text(SCALE_SCRIPT)

    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps({"directories": [str(kernels)], "modules": [], "favorites": []})
    )
    # Under pytest, trame only reads its arguments from TRAME_ARGS.
    monkeypatch.setenv(
        "TRAME_ARGS",
        f"--catalog {catalog} --settings {tmp_path / 'settings.json'} --read-only",
    )
    volume = tmp_path / "volume.emd"
    write_emd(Dataset({"scalars": ramp()}), volume)
    asyncio.run(run_session(volume))
