"""The slice sink in a headless app session: the desktop's settings reach
the reslice mapper, and the in-view handles move the plane."""

import asyncio
import json
import math

import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.writers import write_emd
from vtkmodules.vtkRenderingCore import vtkCoordinate

from tomviz_web.app import data_model

SHAPE = (10, 12, 14)
SPACING = (1.0, 1.0, 2.0)


@pytest.fixture
def volume(tmp_path):
    values = np.arange(np.prod(SHAPE), dtype=np.uint16).reshape(SHAPE, order="F")
    dataset = Dataset({"values": values})
    dataset.spacing = list(SPACING)
    path = tmp_path / "volume.emd"
    write_emd(dataset, path)
    return path


@pytest.fixture
def app_args(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"directories": [], "modules": [], "favorites": []}))
    # Under pytest, trame only reads its arguments from TRAME_ARGS.
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


def display_point(renderer, point):
    coordinate = vtkCoordinate()
    coordinate.SetCoordinateSystemToWorld()
    coordinate.SetValue(*point)
    return coordinate.GetComputedDoubleDisplayValue(renderer)


def drag(interactor, start, end, steps=10):
    """A left-button drag from ``start`` to ``end`` (display pixels)."""
    interactor.SetEventInformation(round(start[0]), round(start[1]))
    interactor.InvokeEvent("LeftButtonPressEvent")
    for i in range(1, steps + 1):
        x = start[0] + (end[0] - start[0]) * i / steps
        y = start[1] + (end[1] - start[1]) * i / steps
        interactor.SetEventInformation(round(x), round(y))
        interactor.InvokeEvent("MouseMoveEvent")
    interactor.InvokeEvent("LeftButtonReleaseEvent")


async def run_session(path):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server="slice-session")
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await server.ready
    manager = app.ctx.pipeline

    try:
        manager.load_file(path)
        await wait_idle(manager)
        model = next(
            m
            for m in manager.model.nodes
            if isinstance(m, data_model.SliceSinkNodeModel)
        )
        representation = model.representation
        mapper, image_property = representation.mapper, representation.property

        # ---- a new slice starts in the middle, as on the desktop
        assert (model.SliceDirection, model.Slice, model.SliceMax) == (
            "XY Plane",
            SHAPE[2] // 2,
            SHAPE[2] - 1,
        )
        assert representation.plane.GetOrigin()[2] == SHAPE[2] // 2 * SPACING[2]

        # ---- a new direction starts from its own middle (the panel sends -1)
        model.SliceDirection = "YZ Plane"
        model.Slice = -1
        await settle()
        assert (model.Slice, model.SliceMax) == (SHAPE[0] // 2, SHAPE[0] - 1)
        assert model.PlaneNormal == (1.0, 0.0, 0.0)
        assert model.PlaneCenter[0] == SHAPE[0] // 2 * SPACING[0]

        # ---- thick slicing: N slices span N voxel planes along the normal
        model.SliceThickness = 3
        model.ThickSliceMode = "Maximum"
        await settle()
        assert mapper.GetSlabThickness() == 2 * SPACING[0]
        assert mapper.GetSlabTypeAsString() == "Max"
        model.SliceDirection = "XY Plane"
        await settle()
        assert mapper.GetSlabThickness() == 2 * SPACING[2]

        # ---- opacity and the raw values in gray
        model.Opacity = 0.25
        model.MapScalars = False
        await settle()
        assert image_property.GetOpacity() == 0.25
        assert image_property.GetLookupTable() is None
        assert image_property.GetColorWindow() == 255  # integers: [0, 255]
        model.MapScalars = True
        await settle()
        assert image_property.GetLookupTable() is model.color_opacity.lut.table

        # ---- a Custom plane takes its center and normal from the model
        model.PlaneCenter = [2.0, 3.0, 4.0]  # the panel sends JSON arrays
        model.PlaneNormal = [0.0, 1.0, 1.0]
        model.SliceDirection = "Custom"
        await settle()
        assert representation.plane.GetOrigin() == (2.0, 3.0, 4.0)
        assert np.allclose(representation.plane.GetNormal(), (0, 0.5**0.5, 0.5**0.5))
        assert model.PlaneCenter == (2.0, 3.0, 4.0)
        assert model.PlaneNormal == representation.plane.GetNormal()  # unit

        # ---- Set Normal to View: along the camera's direction of projection
        vtk_view = model.view.vtk_view
        vtk_view.render_window.SetSize(300, 300)
        vtk_view.reset_camera()
        model.set_normal_to_view()
        await settle()
        direction = vtk_view.renderer.GetActiveCamera().GetDirectionOfProjection()
        normal = representation.plane.GetNormal()
        assert math.isclose(np.dot(direction, normal), 1)

        # ---- the handles: an oblique view of an axis-aligned slice
        model.SliceDirection = "XY Plane"
        model.Slice = -1
        model.SliceThickness = 1
        model.Opacity = 1.0
        await settle()
        vtk_view.look_along("isometric")
        vtk_view.render_window.Render()
        renderer, interactor = vtk_view.renderer, vtk_view.interactor
        camera = renderer.GetActiveCamera()
        camera_before = camera.GetPosition()

        # dragging the slice pushes it along its normal, index by index: the
        # motion counts in the view plane at the picked depth, as on the
        # desktop, so 6 units up z seen isometrically push 6 * (1 - 1/3) = 4
        start = display_point(renderer, (7.0, 9.0, model.Slice * SPACING[2]))
        up = display_point(renderer, (7.0, 9.0, model.Slice * SPACING[2] + 6.0))
        drag(interactor, start, up)
        await settle()
        assert model.SliceDirection == "XY Plane"
        assert model.Slice == SHAPE[2] // 2 + 2  # 4 units, spacing 2
        assert camera.GetPosition() == camera_before  # the camera did not turn

        # grabbing the arrow tilts the plane: it goes Custom where it was
        center = representation.plane.GetOrigin()
        tip = representation.widget.lines[0].GetPoint2()
        tip_display = display_point(renderer, tip)
        drag(
            interactor,
            tip_display,
            (tip_display[0] + 40, tip_display[1]),
        )
        await settle()
        assert model.SliceDirection == "Custom"
        assert model.PlaneCenter == center
        assert model.PlaneNormal != (0.0, 0.0, 1.0)
        assert camera.GetPosition() == camera_before

        # the sphere slides the center across the plane
        normal = np.array(representation.plane.GetNormal())
        center = np.array(representation.plane.GetOrigin())
        sphere = display_point(renderer, center)
        drag(interactor, sphere, (sphere[0] + 15, sphere[1] - 10))
        await settle()
        moved = np.array(model.PlaneCenter)
        assert np.linalg.norm(moved - center) > 0.5
        assert math.isclose(np.dot(moved - center, normal), 0, abs_tol=1e-9)
        assert tuple(model.PlaneNormal) == tuple(normal)

        # missing the handles leaves the event to the camera
        drag(interactor, (5, 5), (60, 5))
        assert camera.GetPosition() != camera_before

        # without the arrow the handles neither show nor respond
        model.ShowArrow = False
        await settle()
        assert not any(actor.GetVisibility() for actor in representation.widget.props)
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


def test_slice_settings_and_handles(volume, app_args):  # noqa: ARG001
    asyncio.run(run_session(volume))
