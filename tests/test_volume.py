"""Pure helpers of the volume visualization: lighting presets, the cut-out's
crop regions, the exploded view's geometry and bricking."""

import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset

from tomviz_web.app.pipeline.vtk import bricking, convert
from tomviz_web.app.utils import volume


def test_presets_are_recognized_and_flat_is_any_unlit_look():
    for name, preset in volume.LIGHTING_PRESETS.items():
        assert volume.matching_preset(preset) == name
    unlit = {**volume.LIGHTING_PRESETS["Full"], "Shade": False}
    assert volume.matching_preset(unlit) == "Flat"
    nearly = {**volume.LIGHTING_PRESETS["Soft"], "Ambient": 0.1004}
    assert volume.matching_preset(nearly) == "Soft"  # within 1e-3
    changed = {**volume.LIGHTING_PRESETS["Soft"], "Ambient": 0.2}
    assert volume.matching_preset(changed) == volume.CUSTOM_PRESET


def test_user_presets_use_the_desktop_keys():
    values = {**volume.LIGHTING_PRESETS["Gentle"], "SpecularPower": 12.0}
    stored = volume.user_preset("Mine", values)
    assert stored == {
        "name": "Mine",
        "shade": True,
        "ambient": 0.35,
        "diffuse": 0.75,
        "specular": 0.0,
        "specularPower": 12.0,
        "scattering": 0.0,
        "reach": 0.0,
        "anisotropy": 0.0,
        "smoothNormals": True,
    }
    assert volume.user_preset_values(stored) == values
    assert volume.matching_user_preset([stored], values) == "Mine"
    assert volume.matching_user_preset([stored], volume.LIGHTING_PRESETS["Full"]) == ""
    # a preset saved by an older desktop lacks keys: Simple fills them in
    assert volume.user_preset_values({"name": "Old", "ambient": 0.5})["Diffuse"] == 0.9


def test_cut_out_removes_one_octant():
    assert volume.cut_out_flags(0) == 0x7FFFFFF & ~1
    # +X +Y +Z: region (1, 1, 1), bit 1 + 3 + 9
    assert volume.cut_out_flags(7) == 0x7FFFFFF & ~(1 << 13)
    assert volume.cut_out_planes((0, 10, 0, 20, 0, 40), (0.5, 0.25, 1.0)) == (
        5,
        10,
        5,
        20,
        40,
        40,
    )


def test_exploded_geometry():
    assert volume.exploded_direction(1, (5, 5, 5)) == (0.0, 1.0, 0.0)
    assert volume.exploded_direction(3, (0, 3, 4)) == (0.0, 0.6, 0.8)
    assert volume.exploded_direction(3, (0, 0, 0)) == (0.0, 0.0, 1.0)

    bounds = (0, 10, 0, 20, 0, 40)
    assert volume.exploded_extent(bounds, (0, 0, 1)) == (-20, 40)
    lo, length = volume.exploded_extent(bounds, (0, 0.6, 0.8))
    assert length == pytest.approx(0.6 * 20 + 0.8 * 40)
    assert lo == pytest.approx(-length / 2)

    assert volume.exploded_voxel_step((0, 0, 1), (1, 1, 2)) == 2
    # 4 slabs of 10 voxels: offsets up to 9 keep every slab a voxel thick
    assert volume.exploded_offset_limit(40, 4, 1.0) == 9
    assert volume.exploded_shift(12, 40, 4, 1.0) == 9
    assert volume.exploded_shift(-3, 40, 4, 2.0) == -6
    assert volume.exploded_offset_limit(3, 4, 1.0) == 0


def test_bricks_share_their_boundaries():
    assert bricking.block_count(2048, 2048) == 1
    assert bricking.block_count(2049, 2048) == 2
    assert bricking.block_count(10, 4) == 3  # 4 + 3 + 3 points, shared ends
    assert bricking.axis_cuts(0, 9, 3) == [0, 3, 6, 9]

    values = np.arange(10 * 6 * 3, dtype=np.float32).reshape((10, 6, 3), order="F")
    image = convert.to_vtk_image(Dataset({"v": values}))
    assert bricking.exceeds_texture_limit(image, 8)
    assert not bricking.exceeds_texture_limit(image, 10)
    blocks = bricking.brick_volume(image, 8)
    extents = [
        blocks.GetBlock(i).GetExtent() for i in range(blocks.GetNumberOfBlocks())
    ]
    assert extents == [(0, 4, 0, 5, 0, 2), (4, 9, 0, 5, 0, 2)]
    assert blocks.GetBlock(1).GetPointData().GetArray("v").GetValue(0) == 4
