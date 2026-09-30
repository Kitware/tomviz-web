"""The surface sinks (contour, threshold) in a headless app session."""

import asyncio
import json

import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.writers import write_emd
from vtkmodules.vtkCommonCore import VTK_COLOR_MODE_DIRECT_SCALARS

from tomviz_web.app import data_model

SHAPE = (16, 18, 20)


@pytest.fixture
def two_arrays(tmp_path):
    """``radius``: squared distance from the center (0 to 3); ``ramp``: x."""
    x, y, z = np.meshgrid(*(np.linspace(-1, 1, n) for n in SHAPE), indexing="ij")
    radius = np.asfortranarray((x**2 + y**2 + z**2).astype(np.float32))
    ramp = np.asfortranarray(((x + 1) * 50).astype(np.float32))
    dataset = Dataset({"radius": radius, "ramp": ramp})
    dataset.active_name = "radius"
    path = tmp_path / "two_arrays.emd"
    write_emd(dataset, path)
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


async def start(path, name):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server=name)
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await server.ready
    manager = app.ctx.pipeline
    manager.load_file(path)
    await wait_idle(manager)
    return app, serve


async def stop(app, serve):
    app.ctx.pipeline.shutdown()
    await app.server.stop()
    serve.cancel()


def surface(representation):
    """The polydata the mapper draws, brought up to date."""
    representation.mapper.Update()
    return representation.mapper.GetInput()


# ---- contour -------------------------------------------------------------------


async def run_contour(path):
    app, serve = await start(path, "contour-session")
    manager, state = app.ctx.pipeline, app.server.state
    try:
        model = data_model.get_instance(
            manager.add_sink(state.active_view_id, "CONTOUR")
        )
        await wait_idle(manager)
        representation = model.representation
        mapper, prop = representation.mapper, representation.property
        render_window = model.view.vtk_view.render_window

        # ---- a new contour: two thirds up the active array's range
        assert model.ArrayNames == ["radius", "ramp"]
        low, high = model.IsoRange
        assert high == pytest.approx(3.0)
        assert 0 < low < 0.02  # no voxel sits exactly at the center
        assert model.IsoValue == pytest.approx(low + (high - low) * 2 / 3)
        assert representation.contour.GetValue(0) == model.IsoValue
        assert surface(representation).GetNumberOfPoints() > 0
        # the desktop's lighting defaults
        assert (prop.GetAmbient(), prop.GetDiffuse(), prop.GetSpecular()) == (0, 1, 1)
        assert prop.GetSpecularPower() == 100
        # colored by its map's array, the contoured one: one iso color
        assert mapper.GetScalarVisibility()
        assert mapper.GetArrayName() == "radius"
        assert not representation.contour.GetInterpolateAttributes()
        render_window.Render()

        # ---- appearance
        model.IsoValue = 0.5
        model.Mode = "Wireframe"
        model.Opacity = 0.5
        model.SpecularPower = 20.0
        await settle()
        assert representation.contour.GetValue(0) == 0.5
        assert prop.GetRepresentationAsString() == "Wireframe"
        assert (prop.GetOpacity(), prop.GetSpecularPower()) == (0.5, 20.0)
        model.Color = "#ff0000"
        model.UseSolidColor = True
        await settle()
        assert not mapper.GetScalarVisibility()
        assert prop.GetDiffuseColor() == (1.0, 0.0, 0.0)
        model.UseSolidColor = False
        model.MapScalars = False
        await settle()
        assert mapper.GetScalarVisibility()
        assert mapper.GetColorMode() == VTK_COLOR_MODE_DIRECT_SCALARS
        model.MapScalars = True
        await settle()

        # ---- colored by another array: interpolated onto the surface
        model.color_opacity.active_data_array = "ramp"
        await settle()
        assert representation.contour.GetInterpolateAttributes()
        assert mapper.GetArrayName() == "ramp"
        values = surface(representation).GetPointData().GetArray("ramp")
        assert values is not None
        assert values.GetRange()[1] > values.GetRange()[0]
        render_window.Render()

        # ---- contoured by another array; the value is kept
        model.ContourBy = "ramp"
        model.IsoValue = 25.0
        await settle()
        assert model.IsoRange == pytest.approx((0.0, 100.0))
        contoured = surface(representation).GetPoints()
        xs = [contoured.GetPoint(i)[0] for i in range(contoured.GetNumberOfPoints())]
        assert np.allclose(xs, xs[0], atol=1e-3)  # a plane of constant x
        render_window.Render()
    finally:
        await stop(app, serve)


def test_contour(two_arrays, app_args):  # noqa: ARG001
    asyncio.run(run_contour(two_arrays))


# ---- threshold -----------------------------------------------------------------


def voxels(values, low, high):
    return int(np.count_nonzero((values >= low) & (values <= high)))


async def run_threshold(path):
    from tomviz_web.app.utils.data import threshold_seed

    app, serve = await start(path, "threshold-session")
    manager, state = app.ctx.pipeline, app.server.state
    try:
        model = data_model.get_instance(
            manager.add_sink(state.active_view_id, "THRESHOLD")
        )
        await wait_idle(manager)
        representation = model.representation
        mapper, prop = representation.mapper, representation.property
        render_window = model.view.vtk_view.render_window
        dataset = model.source_port.payload
        radius, ramp = dataset.scalars("radius"), dataset.scalars("ramp")

        # ---- a new threshold: the brightest voxels, up to the maximum
        assert model.Minimum == pytest.approx(threshold_seed(radius))
        assert model.Maximum == pytest.approx(float(radius.max()))
        assert model.ScalarRange == pytest.approx(
            (float(radius.min()), float(radius.max()))
        )
        assert prop.GetSpecular() == 0
        # one cell per voxel: exactly the voxels in range are kept
        representation.threshold.Update()
        kept = representation.threshold.GetOutput().GetNumberOfCells()
        assert kept == voxels(radius, model.Minimum, model.Maximum)
        assert kept > 0
        # colored per voxel by the map's array
        assert mapper.GetScalarModeAsString() == "UseCellFieldData"
        assert mapper.GetArrayName() == "radius"
        assert surface(representation).GetCellData().GetArray("radius") is not None
        render_window.Render()

        # ---- another range and another array
        model.ThresholdBy = "ramp"
        model.Minimum, model.Maximum = 20.0, 40.0
        model.Mode = "Points"
        model.Opacity = 0.5
        await settle()
        assert model.ScalarRange == pytest.approx((0.0, 100.0))
        representation.threshold.Update()
        kept = representation.threshold.GetOutput().GetNumberOfCells()
        assert kept == voxels(ramp, 20.0, 40.0)
        assert prop.GetRepresentationAsString() == "Points"
        model.color_opacity.active_data_array = "ramp"
        await settle()
        assert mapper.GetArrayName() == "ramp"
        render_window.Render()

        # ---- an array index from a desktop state file becomes its name
        model.ThresholdBy = 0
        await settle()
        assert model.ThresholdBy == "radius"
    finally:
        await stop(app, serve)


def test_threshold(two_arrays, app_args):  # noqa: ARG001
    asyncio.run(run_threshold(two_arrays))
