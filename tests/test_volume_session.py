"""The volume sink in a headless app session: the desktop's settings reach
the mappers, lighting presets, the cut-out, the exploded view, volumes
rendered together, and bricking."""

import asyncio
import json

import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.writers import write_emd

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.vtk import convert
from tomviz_web.app.utils.volume import cut_out_flags

SHAPE = (10, 12, 14)
SPACING = (1.0, 1.0, 2.0)
BOUNDS = (0.0, 9.0, 0.0, 11.0, 0.0, 26.0)


@pytest.fixture
def volume_file(tmp_path):
    x, y, z = np.meshgrid(*(np.linspace(-1, 1, n) for n in SHAPE), indexing="ij")
    values = np.asfortranarray(np.exp(-4 * (x**2 + y**2 + z**2)).astype(np.float32))
    dataset = Dataset({"values": values})
    dataset.spacing = list(SPACING)
    path = tmp_path / "volume.emd"
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


def in_renderer(renderer, prop) -> bool:
    return bool(renderer.GetViewProps().IsItemPresent(prop))


async def run_session(path):
    from tomviz_web.app.core import Tomviz

    app = Tomviz(server="volume-session")
    server = app.server
    serve = asyncio.create_task(
        server.start(exec_mode="coroutine", port=0, open_browser=False, timeout=0)
    )
    await server.ready
    manager = app.ctx.pipeline
    state = server.state

    try:
        manager.load_file(path)
        await wait_idle(manager)
        model = data_model.get_instance(
            manager.add_sink(state.active_view_id, "VOLUME")
        )
        await wait_idle(manager)
        representation = model.representation
        mapper, volume_property = representation.mapper, representation.property
        renderer = model.view.vtk_view.renderer
        render_window = model.view.vtk_view.render_window
        render_window.SetSize(200, 200)
        model.view.vtk_view.reset_camera()

        # ---- the desktop's defaults: the Simple lighting
        assert (model.LightingPreset, model.Shade, model.InterpolationType) == (
            "Simple",
            True,
            "Linear",
        )
        assert volume_property.GetShade() == 1
        assert mapper.GetUseJittering()
        assert mapper.GetBlendMode() == 0
        assert (model.ScatteringAvailable, model.MultiVolumeActive) == (True, False)

        # ---- rendering settings reach the mapper and the property
        model.BlendMode = "Max"
        model.Solidity = 0.5
        model.Jittering = False
        model.InterpolationType = "Nearest"
        await settle()
        assert mapper.GetBlendMode() == 1
        assert volume_property.GetScalarOpacityUnitDistance() == 2.0
        assert not mapper.GetUseJittering()
        assert volume_property.GetInterpolationType() == 0  # nearest
        model.BlendMode = "Composite"
        await settle()

        # ---- presets: Full casts shadows; the switch keeps the strength
        model.apply_lighting_preset("Full")
        await settle()
        assert model.LightingPreset == "Full"
        assert mapper.GetVolumetricScatteringBlending() == 1.5
        assert mapper.GetComputeNormalFromOpacity()
        assert volume_property.GetScatteringAnisotropy() == -0.25
        model.ShadowsEnabled = False
        await settle()
        assert mapper.GetVolumetricScatteringBlending() == 0
        assert (model.VolumetricScattering, model.LightingPreset) == (1.5, "Full")
        model.Ambient = 0.3
        await settle()
        assert model.LightingPreset == "Custom"

        # ---- saved presets: the strength saved is the one rendering
        model.save_user_lighting_preset("Mine")
        await settle()
        assert [p["name"] for p in state.volume_lighting_presets] == ["Mine"]
        assert state.volume_lighting_presets[0]["scattering"] == 0.0
        assert model.UserLightingPreset == "Mine"
        model.apply_lighting_preset("Simple")
        await settle()
        assert model.UserLightingPreset == ""
        model.apply_user_lighting_preset("Mine")
        await settle()
        assert (model.Ambient, model.UserLightingPreset) == (0.3, "Mine")
        assert not model.rename_user_lighting_preset("Mine", " ")
        assert model.rename_user_lighting_preset("Mine", "Yours")
        assert model.UserLightingPreset == "Yours"
        model.delete_user_lighting_preset("Yours")
        assert state.volume_lighting_presets == []
        model.apply_lighting_preset("Simple")
        await settle()

        # ---- cut out: one octant cropped away
        model.CutOutEnabled = True
        model.CutOutCorner = 7
        model.CutOutPosition = [0.5, 0.5, 0.25]  # the panel sends arrays
        await settle()
        assert mapper.GetCropping()
        assert mapper.GetCroppingRegionFlags() == cut_out_flags(7)
        assert mapper.GetCroppingRegionPlanes() == (4.5, 9.0, 5.5, 11.0, 6.5, 26.0)
        render_window.Render()

        # ---- exploded view: it takes the cropping over from the cut-out
        model.set_exploded(ExplodedEnabled=True)
        await settle()
        assert (model.ExplodedEnabled, model.CutOutEnabled) == (True, False)
        slabs = representation.volumes
        assert len(slabs) == 4
        assert all(in_renderer(renderer, slab) for slab in slabs)
        z_ranges = [m.GetCroppingRegionPlanes()[4:] for m in representation.mappers]
        assert z_ranges == [(0.0, 6.5), (6.5, 13.0), (13.0, 19.5), (19.5, 26.0)]
        assert [s.GetPosition()[2] for s in slabs] == [0.0, 6.5, 13.0, 19.5]
        # no shadows while exploded
        assert not model.ScatteringAvailable
        assert "exploded" in model.ScatteringUnavailableReason
        model.ExplodedOffset = 100  # clamped to keep a voxel per slab
        await settle()
        assert model.ExplodedOffsetLimit == 2  # (6.5 - 2) // 2
        assert representation.mappers[1].GetCroppingRegionPlanes()[4] == 10.5
        model.ExplodedOffset = 0
        model.ExplodedChunks = 2
        await settle()
        assert len(representation.volumes) == 2
        assert not in_renderer(renderer, slabs[2])

        # a custom direction: each slab clipped by a pair of planes, the
        # arrow shown
        model.set_exploded(ExplodedAxis="Custom")
        await settle()
        assert not mapper.GetCropping()
        assert [
            m.GetClippingPlanes().GetNumberOfItems() for m in representation.mappers
        ] == [2, 2]
        assert all(actor.GetVisibility() for actor in representation.widget.props)
        render_window.Render()

        model.set_exploded(ExplodedEnabled=False)
        await settle()
        assert len(representation.volumes) == 1
        assert mapper.GetClippingPlanes().GetNumberOfItems() == 0
        assert not mapper.GetCropping()
        assert representation.actor.GetPosition() == (0.0, 0.0, 0.0)
        assert not any(actor.GetVisibility() for actor in representation.widget.props)
        assert model.ScatteringAvailable

        # ---- a second volume in the view: both are drawn together
        other = data_model.get_instance(
            manager.add_sink(state.active_view_id, "VOLUME")
        )
        await wait_idle(manager)
        coordinator = model.view.vtk_view.multi_volume
        assert coordinator.active
        assert coordinator.members == [representation, other.representation]
        assert in_renderer(renderer, coordinator.multi_volume)
        assert not in_renderer(renderer, representation.actor)
        assert not in_renderer(renderer, other.representation.actor)
        assert (model.MultiVolumeActive, model.MultiVolumeLead) == (True, True)
        assert (other.MultiVolumeLead, other.MultiVolumeLeadLabel) == (False, "Volume")
        assert not model.ScatteringAvailable
        render_window.Render()

        # hidden, it leaves the set; the first renders on its own again
        other.Visibility = False
        await settle()
        assert not coordinator.active
        assert in_renderer(renderer, representation.actor)
        assert not in_renderer(renderer, coordinator.multi_volume)
        assert model.MultiVolumeActive is False
        render_window.Render()

        # shown again it rejoins; deleted, it leaves for good
        other.Visibility = True
        await settle()
        assert coordinator.active
        manager.run_menu_action("delete", "node", other._id)
        await settle()
        assert not coordinator.active
        assert coordinator.members == [representation]
        assert in_renderer(renderer, representation.actor)
        assert not in_renderer(renderer, other.representation.actor)
        render_window.Render()

        # ---- bricking: a volume beyond the texture limit
        representation.texture_size_limit = 8
        model.node.apply(convert.to_vtk_image(model.source_port.payload))
        await settle()
        assert representation.bricked
        assert model.Bricked
        assert representation.actor.GetMapper() is representation.brick_mapper
        blocks = representation.brick_mapper.GetInputDataObject(0, 0)
        assert blocks.GetNumberOfBlocks() == 8  # 2 bricks along each axis
        assert not model.ScatteringAvailable
        model.set_exploded(ExplodedEnabled=True)
        await settle()
        assert model.ExplodedEnabled is False  # refused on bricks
        render_window.Render()
        representation.texture_size_limit = None
        model.node.apply(convert.to_vtk_image(model.source_port.payload))
        await settle()
        assert representation.actor.GetMapper() is mapper
        assert not model.Bricked
    finally:
        manager.shutdown()
        await server.stop()
        serve.cancel()


def test_volume_settings_and_modes(volume_file, app_args):  # noqa: ARG001
    asyncio.run(run_session(volume_file))
