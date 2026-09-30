"""The clip sink in a headless app session: its plane cuts the other
visualizations of its group, in any view, and follows the graph."""

import asyncio
import json

import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.writers import write_emd
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

from tomviz_web.app import data_model

SHAPE = (12, 12, 12)
PIXELS = 100


@pytest.fixture
def volume_file(tmp_path):
    values = np.ones(SHAPE, dtype=np.float32, order="F")
    values[0, 0, 0] = 0.0  # a range to color and threshold over
    path = tmp_path / "volume.emd"
    write_emd(Dataset({"values": values}), path)
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


async def settle():
    await asyncio.sleep(0.1)


def planes_of(mapper):
    planes = mapper.GetClippingPlanes()
    if planes is None:
        return []
    return [planes.GetItem(i) for i in range(planes.GetNumberOfItems())]


def lit_halves(vtk_view):
    """Lit pixels in the (lower, upper) half of the view."""
    window = vtk_view.render_window
    window.SetSize(PIXELS, PIXELS)
    window.Render()
    grab = vtkWindowToImageFilter()
    grab.SetInput(window)
    grab.Update()
    pixels = vtk_to_numpy(grab.GetOutput().GetPointData().GetScalars())
    background = np.array(vtk_view.background) * 255
    lit = np.abs(pixels.reshape(PIXELS, PIXELS, -1)[..., :3] - background).sum(-1) > 30
    half = PIXELS // 2
    return int(lit[:half].sum()), int(lit[half:].sum())  # row 0 is the bottom


async def run_session(path):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server="clip-session")
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await server.ready
    manager = app.ctx.pipeline
    state = server.state

    def add(kind, view_id=None):
        return data_model.get_instance(
            manager.add_sink(view_id or state.active_view_id, kind)
        )

    try:
        manager.load_file(path)
        await wait_idle(manager)
        sinks = {m.representation_type: m for m in manager._sink_models()}
        outline, slice_model = sinks["OUTLINE"], sinks["SLICE"]
        threshold = add("THRESHOLD")
        volume = add("VOLUME")
        clip = add("CLIP")
        await wait_idle(manager)
        plane = clip.representation.clip_plane

        # ---- the desktop's defaults: an XY plane in the middle
        assert (clip.SliceDirection, clip.Slice, clip.Opacity) == ("XY Plane", 6, 0.5)
        assert clip.Color == "#ffffff"
        assert plane.GetNormal() == (0.0, 0.0, 1.0)
        assert plane.GetOrigin()[2] == 6.0

        # ---- it cuts the other sinks of its group, not the outline nor itself
        assert planes_of(slice_model.representation.mapper) == [plane]
        assert planes_of(threshold.representation.mapper) == [plane]
        assert planes_of(volume.representation.mapper) == [plane]
        assert planes_of(outline.representation.mapper) == []
        assert planes_of(clip.representation.mapper) == []

        # it keeps the side the normal points to: seen from the side, the
        # threshold (every voxel) is only above the plane
        for model in (outline, slice_model, volume):
            model.Visibility = False
        clip.ShowPlane = False
        threshold.Minimum, threshold.Maximum = 0.0, 1.0
        await settle()
        vtk_view = clip.view.vtk_view
        vtk_view.orientation_axes_visibility = False  # it sits bottom right
        vtk_view.reset_camera()
        vtk_view.look_along("x")
        lower, upper = lit_halves(vtk_view)
        assert upper > 0
        assert lower == 0
        assert clip.representation.clipping  # a hidden plane still clips

        # ---- inverted, the other side
        clip.invert(True)
        await settle()
        assert plane.GetNormal() == (0.0, 0.0, -1.0)
        lower, upper = lit_halves(vtk_view)
        # the view's middle is z = 5.5 and the plane z = 6: a thin band of
        # what is kept (z < 6) shows in the upper half
        assert lower > 4 * upper > 0

        # ---- moving it moves the cut: the plane is shared, not copied
        clip.Slice = 9
        await settle()
        assert plane.GetOrigin()[2] == 9.0
        assert planes_of(threshold.representation.mapper) == [plane]

        # a Custom plane: Invert flips its own normal
        clip.PlaneNormal = [0.0, 1.0, 1.0]
        clip.SliceDirection = "Custom"
        await settle()
        clip.invert(False)
        await settle()
        assert np.allclose(plane.GetNormal(), (0, -(0.5**0.5), -(0.5**0.5)))

        # ---- hidden, it stops cutting; shown, it cuts again
        clip.Visibility = False
        await settle()
        assert planes_of(threshold.representation.mapper) == []
        clip.Visibility = True
        await settle()
        assert planes_of(threshold.representation.mapper) == [plane]

        # ---- volumes drawn together share their clips on the one mapper
        volume.Visibility = True
        add("VOLUME")
        await wait_idle(manager)
        coordinator = clip.view.vtk_view.multi_volume
        assert coordinator.active
        assert planes_of(coordinator.mapper) == [plane]
        clip.view.vtk_view.render_window.Render()

        # ---- membership follows the graph: newcomers join, leavers leave,
        # whatever the view
        other_view = manager.add_view()
        contour = add("CONTOUR", other_view)
        await wait_idle(manager)
        assert contour.view is not clip.view
        assert planes_of(contour.representation.mapper) == [plane]
        manager.leave_group(threshold._id)
        await wait_idle(manager)
        assert planes_of(threshold.representation.mapper) == []

        # ---- deleted, it cuts nothing
        manager.run_menu_action("delete", "node", clip._id)
        await settle()
        assert planes_of(contour.representation.mapper) == []
        assert planes_of(volume.representation.mapper) == []
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


def test_clip_cuts_its_group(volume_file, app_args):  # noqa: ARG001
    asyncio.run(run_session(volume_file))
