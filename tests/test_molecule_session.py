"""The molecule sink in a headless app session: a kernel's molecule port,
the toolbar offering only what can show it, ball and stick."""

import asyncio
import json

import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.writers import write_emd
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

from tomviz_web.app import data_model


@pytest.fixture
def volume_file(tmp_path):
    path = tmp_path / "volume.emd"
    write_emd(Dataset({"values": np.ones((8, 8, 8), dtype=np.float32)}), path)
    return path


@pytest.fixture
def app_args(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"directories": [], "modules": [], "favorites": []}))
    monkeypatch.setenv(
        "TRAME_ARGS",
        f"--catalog {catalog} --settings {tmp_path / 'settings.json'} --read-only",
    )


def lit_pixels(vtk_view, size=200):
    window = vtk_view.render_window
    window.SetSize(size, size)
    window.Render()
    grab = vtkWindowToImageFilter()
    grab.SetInput(window)
    grab.Update()
    pixels = vtk_to_numpy(grab.GetOutput().GetPointData().GetScalars())[:, :3]
    background = np.array(vtk_view.background) * 255
    return int((np.abs(pixels - background).sum(1) > 30).sum())


async def wait_idle(manager):
    for _ in range(200):
        if not manager.pipeline.is_executing():
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)


async def run_session(path):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server="molecule-session")
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await server.ready
    manager, state = app.ctx.pipeline, server.state

    try:
        manager.load_file(path)
        await wait_idle(manager)
        # an image tip: the image visualizations, none unimplemented
        assert "SLICE" in state.tip_representations
        assert "MOLECULE" not in state.tip_representations
        assert "RULER" not in state.tip_representations

        # the builtin kernel emits a benzene next to its image output
        transform = data_model.get_instance(manager.add_transform("DummyMolecule"))
        await wait_idle(manager)
        port = next(p for p in transform.outputs if p.port_type == "Molecule")
        assert port.data.num_atoms == 12

        manager.model.active_node = [port._id]
        await asyncio.sleep(0.1)
        assert state.tip_representations == ["MOLECULE"]

        model = data_model.get_instance(
            manager.add_sink(state.active_view_id, "MOLECULE")
        )
        await wait_idle(manager)
        representation = model.representation
        molecule = representation.image
        assert (molecule.GetNumberOfAtoms(), molecule.GetNumberOfBonds()) == (12, 12)
        assert representation.actor.GetVisibility()
        assert (model.BallRadius, model.StickRadius) == pytest.approx((0.3, 0.075))

        model.BallRadius = 1.5
        model.StickRadius = 0.2
        await asyncio.sleep(0.1)
        assert representation.mapper.GetAtomicRadiusScaleFactor() == 1.5
        assert representation.mapper.GetBondRadius() == pytest.approx(0.2)

        # it draws: looking at the benzene alone (the kernel puts it at
        # (150, 150, 40), well away from the volume)
        for sink in manager._sink_models():
            if sink is not model:
                sink.Visibility = False
        await asyncio.sleep(0.1)
        vtk_view = model.view.vtk_view
        vtk_view.orientation_axes_visibility = False
        camera = vtk_view.renderer.GetActiveCamera()
        camera.SetFocalPoint(150, 150, 40)
        camera.SetPosition(154, 144, 48)
        camera.SetViewUp(0, 0, 1)
        vtk_view.renderer.ResetCameraClippingRange()
        assert lit_pixels(vtk_view) > 1000
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


def test_molecule(volume_file, app_args):  # noqa: ARG001
    asyncio.run(run_session(volume_file))
