"""The builtin catalog, the tomviz-kernels package, driven through the app:
v1 scripts and schema-v2 kernels run at the tip, the port types the
descriptions declare decide where a kernel can go, and a v1 script's extra
datasets are ports, as in the desktop app: ``dataset`` parameters are inputs,
``results`` and ``children`` outputs."""

import asyncio
import json

import numpy as np
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.writers import write_emd

from tomviz_web.app import data_model

SHAPE = (8, 8, 7)
ANGLES = np.linspace(-60.0, 60.0, SHAPE[2])


def ramp():
    size = int(np.prod(SHAPE))
    return np.arange(size, dtype=np.float32).reshape(SHAPE, order="F")


def write(tmp_path, name, array="scalars", tilt_angles=None):
    dataset = Dataset({array: ramp()})
    if tilt_angles is not None:
        dataset.tilt_angles = tilt_angles
        dataset.tilt_axis = 2
    path = tmp_path / name
    write_emd(dataset, path)
    return path


async def wait_idle(manager):
    for _ in range(200):
        if not manager.pipeline.is_executing():
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)


def scalars(model):
    return model.node.output_ports()[0].data().payload.active_scalars


def port_names(ports):
    return [port.name for port in ports]


async def run_session(volume_file, other_file, tilt_series_file):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server="kernels-session")
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await server.ready
    manager = app.ctx.pipeline

    try:
        manager.load_file(volume_file)
        await wait_idle(manager)
        # Like the desktop reader: no tilt angles, a Volume.
        assert manager.tip_port.port_type == "Volume"

        # A v1 script, hosted by LegacyScriptableTransformNode.
        blur = data_model.get_instance(
            manager.add_transform("GaussianFilter", parameters={"sigma": 1.0})
        )
        await wait_idle(manager)
        assert blur.state == "Current"
        blurred = scalars(blur)
        assert blurred.shape == SHAPE
        assert not np.allclose(blurred, ramp())

        # A schema-v2 kernel, hosted by ScriptableTransformNode.
        invert = data_model.get_instance(manager.add_transform("InvertData"))
        await wait_idle(manager)
        assert invert.state == "Current"
        np.testing.assert_allclose(
            scalars(invert), blurred.max() - blurred + blurred.min(), rtol=1e-5
        )

        # select_scalars has no widget yet: the kernel keeps the active array.
        keep = data_model.get_instance(manager.add_transform("RemoveArrays"))
        await wait_idle(manager)
        assert keep.state == "Current"
        np.testing.assert_allclose(scalars(keep), scalars(invert))

        # A result is an output port next to the volume.
        psd = data_model.get_instance(manager.add_transform("PowerSpectrumDensity"))
        await wait_idle(manager)
        assert psd.state == "Current"
        assert port_names(psd.outputs) == ["volume", "plot"]
        plot = psd.outputs[1]
        assert plot.port_type == "Table"
        assert isinstance(plot.data, data_model.TablePortDataModel)

        # A dataset parameter is an input port, not a parameter: the node
        # waits for it to be linked, then runs.
        combine = data_model.get_instance(manager.add_transform("combine_datasets"))
        await wait_idle(manager)
        assert port_names(combine.inputs) == ["volume", "second_dataset"]
        second = combine.inputs[1]
        assert second.link is None
        assert combine.state == "New"
        assert "second_dataset" not in combine.parameters.FIELD_NAMES

        other = data_model.get_instance(manager.load_file(other_file))
        await wait_idle(manager)
        assert manager.create_link(other.outputs[0]._id, second._id)
        await wait_idle(manager)
        assert combine.state == "Current"
        combined = combine.node.output_ports()[0].data().payload
        assert combined.scalars_names == ["scalars", "other"]

        # Kernels that declare a Volume input take a loaded file...
        assert app.ctx.catalog.entries["ClipEdges"].json["inputType"] == "Volume"
        clip = data_model.get_instance(manager.add_transform("ClipEdges"))
        await wait_idle(manager)
        assert clip.state == "Current"

        # ...tilt series kernels refuse it...
        assert app.ctx.catalog.entries["ReconstructWBP"].json["inputType"] == (
            "TiltSeries"
        )
        assert manager.add_transform("ReconstructWBP") is None

        # ...and take a file that has tilt angles.
        manager.load_file(tilt_series_file)
        await wait_idle(manager)
        assert manager.tip_port.port_type == "TiltSeries"
        # Nrecon has a data-default (num-voxels-y) the app does not fill yet.
        recon = data_model.get_instance(
            manager.add_transform("ReconstructWBP", parameters={"Nrecon": SHAPE[1]})
        )
        await wait_idle(manager)
        assert recon.state == "Current"
        # The child dataset is the primary output, named after it.
        assert port_names(recon.outputs) == ["reconstruction"]
        assert recon.outputs[0].port_type == "Volume"
        assert scalars(recon).shape == (SHAPE[0], SHAPE[1], SHAPE[1])
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


def test_builtin_kernels_in_a_session(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"directories": [], "modules": [], "favorites": []}))
    # Under pytest, trame only reads its arguments from TRAME_ARGS.
    monkeypatch.setenv(
        "TRAME_ARGS",
        f"--catalog {catalog} --settings {tmp_path / 'settings.json'} --read-only",
    )
    asyncio.run(
        run_session(
            write(tmp_path, "volume.emd"),
            write(tmp_path, "other.emd", array="other"),
            write(tmp_path, "tilt_series.emd", tilt_angles=ANGLES),
        )
    )
