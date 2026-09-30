"""Pure helpers of the volume visualization, after the desktop's
``VolumeSink``, ``ExplodedGeometry`` and ``LightingPresetStore``: the
lighting presets, the geometry of the exploded view and the cut-out's crop
regions. No VTK, no trame."""

from __future__ import annotations

import math

# ---- lighting ----------------------------------------------------------------

# The model fields a lighting preset sets, in the desktop's preset order.
LIGHTING_FIELDS = (
    "Shade",
    "Ambient",
    "Diffuse",
    "Specular",
    "SpecularPower",
    "VolumetricScattering",
    "ShadowReach",
    "ScatteringAnisotropy",
    "SmoothNormals",
)


def _preset(shade, ambient, diffuse, specular, power, scattering, reach, aniso, smooth):
    return dict(
        zip(
            LIGHTING_FIELDS,
            (
                shade,
                ambient,
                diffuse,
                specular,
                power,
                scattering,
                reach,
                aniso,
                smooth,
            ),
            strict=True,
        )
    )


# The desktop's presets, in increasing render cost. Flat is unlit; its other
# values are Simple's so that turning shading back on looks sensible. The
# desktop's notes on how they were tuned apply here unchanged: ambient does
# nothing once scattering is on, and anisotropy must not be positive.
LIGHTING_PRESETS = {
    "Flat": _preset(False, 0.1, 0.9, 0.3, 30.0, 0.0, 0.0, 0.0, False),
    "Simple": _preset(True, 0.1, 0.9, 0.3, 30.0, 0.0, 0.0, 0.0, False),
    "Gentle": _preset(True, 0.35, 0.75, 0.0, 30.0, 0.0, 0.0, 0.0, True),
    "Soft": _preset(True, 0.1, 1.0, 0.0, 30.0, 1.0, 0.08, 0.0, True),
    "Full": _preset(True, 0.1, 1.0, 0.3, 40.0, 1.5, 0.08, -0.25, True),
}
CUSTOM_PRESET = "Custom"

# A user preset as the desktop stores it (LightingPresetStore), and the
# model field each key maps to.
USER_PRESET_KEYS = {
    "shade": "Shade",
    "ambient": "Ambient",
    "diffuse": "Diffuse",
    "specular": "Specular",
    "specularPower": "SpecularPower",
    "scattering": "VolumetricScattering",
    "reach": "ShadowReach",
    "anisotropy": "ScatteringAnisotropy",
    "smoothNormals": "SmoothNormals",
}


def lighting_matches(a: dict, b: dict) -> bool:
    """Every lighting field equal, numbers within 1e-3 (the desktop's)."""
    for field in LIGHTING_FIELDS:
        x, y = a[field], b[field]
        if isinstance(x, bool) or isinstance(y, bool):
            if bool(x) != bool(y):
                return False
        elif abs(float(x) - float(y)) >= 1e-3:
            return False
    return True


def matching_preset(values: dict) -> str:
    """The built-in preset ``values`` match, or ``CUSTOM_PRESET``. Unlit
    values are always Flat: no other setting shows without shading."""
    if not values["Shade"]:
        return "Flat"
    for name, preset in LIGHTING_PRESETS.items():
        if name != "Flat" and lighting_matches(values, preset):
            return name
    return CUSTOM_PRESET


def user_preset_values(preset: dict) -> dict:
    """A stored user preset as model field values (missing keys take
    Simple's values, as the desktop's defaults do)."""
    values = dict(LIGHTING_PRESETS["Simple"])
    for key, field in USER_PRESET_KEYS.items():
        if key in preset:
            values[field] = preset[key]
    return values


def user_preset(name: str, values: dict) -> dict:
    """Model field values as a stored user preset called ``name``."""
    preset = {"name": name}
    for key, field in USER_PRESET_KEYS.items():
        value = values[field]
        preset[key] = bool(value) if isinstance(value, bool) else float(value)
    return preset


def matching_user_preset(presets: list, values: dict) -> str:
    """The name of the first saved preset ``values`` match, or ``""``."""
    for preset in presets:
        if lighting_matches(user_preset_values(preset), values):
            return str(preset.get("name", ""))
    return ""


# ---- cut out -----------------------------------------------------------------

# Corner labels, by corner bits: 1 = high X, 2 = high Y, 4 = high Z.
CUT_OUT_CORNERS = (
    "-X -Y -Z",
    "+X -Y -Z",
    "-X +Y -Z",
    "+X +Y -Z",
    "-X -Y +Z",
    "+X -Y +Z",
    "-X +Y +Z",
    "+X +Y +Z",
)


def cut_out_planes(bounds, position) -> tuple[float, ...]:
    """The mapper's six cropping planes for a cut at ``position`` (0-1 per
    axis): two per axis, the second on the far face, so VTK's 27 regions
    collapse to the 8 octants around the cut."""
    planes = []
    for axis in range(3):
        lo, hi = bounds[2 * axis], bounds[2 * axis + 1]
        planes += [lo + position[axis] * (hi - lo), hi]
    return tuple(planes)


def cut_out_flags(corner: int) -> int:
    """Cropping region flags keeping every region but the removed octant.
    Region bits run x fastest, then y, then z."""
    i, j, k = corner & 1, (corner >> 1) & 1, (corner >> 2) & 1
    return 0x7FFFFFF & ~(1 << (i + 3 * j + 9 * k))


# ---- exploded view -----------------------------------------------------------

EXPLODED_AXES = ("X", "Y", "Z", "Custom")
CUSTOM_AXIS = 3


def exploded_direction(axis: int, custom) -> tuple[float, float, float]:
    """The unit direction the slabs are cut and pulled apart along: the axis
    for 0-2, else ``custom`` normalized (+Z for a zero vector)."""
    if 0 <= axis < 3:
        direction = [0.0, 0.0, 0.0]
        direction[axis] = 1.0
        return tuple(direction)
    length = math.sqrt(sum(c * c for c in custom))
    if length <= 0:
        return (0.0, 0.0, 1.0)
    return tuple(c / length for c in custom)


def exploded_extent(bounds, direction) -> tuple[float, float]:
    """How far the box reaches along ``direction`` from its center: the
    (non-positive) signed distance ``lo`` of the nearest corner and the full
    span ``length``; slab boundaries lie at ``lo + length * k / chunks``."""
    half = sum(
        abs(direction[a]) * (bounds[2 * a + 1] - bounds[2 * a]) / 2 for a in range(3)
    )
    return -half, 2 * half


def exploded_voxel_step(direction, spacing) -> float:
    """The length of one voxel along ``direction``."""
    return math.sqrt(sum((direction[a] * spacing[a]) ** 2 for a in range(3)))


def exploded_offset_limit(length: float, chunks: int, step: float) -> int:
    """The largest offset, in voxels, leaving every slab a voxel thick."""
    if chunks < 1 or step <= 0:
        return 0
    return max(0, math.floor((length / chunks - step) / step))


def exploded_shift(voxels: int, length: float, chunks: int, step: float) -> float:
    """The cut planes' shift for an offset of ``voxels``, clamped to the
    limit, in data units."""
    limit = exploded_offset_limit(length, chunks, step)
    return max(-limit, min(limit, voxels)) * step
