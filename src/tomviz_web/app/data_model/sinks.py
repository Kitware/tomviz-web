"""Mirrors of the sink nodes that display data in a render view.

``SinkNodeModel`` mirrors a ``RepresentationSinkNode``; one subclass exists
per ``RepresentationType`` and carries the VTK properties its dynamic UI
panel edits. ``pull()`` copies the VTK side into the synced fields and
``push()`` writes them back."""

from __future__ import annotations

from collections.abc import Callable

from trame.app.dataclass import ServerOnly, Sync, TypeValidation, watch

from tomviz_web.app.pipeline.representations.core import Representation
from tomviz_web.app.utils.colors import hex_to_rgb, rgb_to_hex
from tomviz_web.app.utils.volume import (
    LIGHTING_FIELDS,
    LIGHTING_PRESETS,
    matching_preset,
    matching_user_preset,
    user_preset,
    user_preset_values,
)

from .color_opacity import ColorOpacityModel, create_color_opacity
from .labels import LabelTableModel
from .node import NodeModel
from .port import OutputPortModel
from .view import ViewModel


class SinkNodeModel(NodeModel):
    """Mirror of a sink node showing the data of ``source_port`` in ``view``."""

    representation = ServerOnly(Representation | None)
    representation_type = Sync(str, "")  # RepresentationType name, picks the UI
    # The data port displayed, resolved through the sink group the sink is
    # linked to (``inputs[0].link`` is the group's passthrough port).
    source_port = Sync(OutputPortModel, has_dataclass=True)
    view = Sync(ViewModel, has_dataclass=True)

    # Whether the user wants the sink shown. The actor is only shown once
    # data has arrived, see ``apply_visibility``.
    Visibility = Sync(bool, True)

    def __init__(self, server, **kwargs):
        super().__init__(server, **kwargs)
        self.pull()

    @property
    def data_node(self):
        """The data node owning ``source_port``."""
        return None if self.source_port is None else self.source_port.node

    def pull(self):
        """Copy the VTK side into the synced fields (subclasses extend)."""

    def push(self):
        """Write the synced fields back to the VTK representation."""

    def apply_visibility(self):
        """Show the actor when wanted and data is there."""
        representation = self.representation
        if representation is None:
            return
        representation.set_visible(self.Visibility and representation.image is not None)

    def set_source_port(self, port: OutputPortModel):
        """Display another port. Only the model side: the manager re-links
        the graph. Sinks with a color map rebind it to the new port."""
        self.source_port = port
        rebind = getattr(self, "_on_custom_color_opacity_change", None)
        if rebind is not None:
            rebind(self.use_internal_color_opacity)

    @watch("Visibility")
    def _on_visibility_change(self, _visibility):
        self.apply_visibility()
        self.render()

    def render(self, *_):
        self.view.render()

    def reset_camera(self, *_):
        self.view.reset_camera()


# -----------------------------------------------------------------------------
class ColorOpacityMixin:
    """
    color_opacity = Sync(ColorOpacityModel, has_dataclass=True)
    use_internal_color_opacity

    Switches between the port's shared color map and an internal one owned
    by this sink. The sink acquires the map it colors through and releases
    the other, so a map without users (the internal one while switched off,
    or a port's shared map once its sinks moved on) never asks the port for
    statistics.
    """

    def pre_init_color_opacity(self):
        self._color_opacity_unwatch_0: Callable | None = None
        self._color_opacity_unwatch_1: Callable | None = None

    def post_init_color_opacity(self):
        self._internal_color_opacity: ColorOpacityModel = create_color_opacity(
            self.source_port
        )

    def release_color_opacity(self):
        """Stop using any color map; called when the sink is removed."""
        if self.color_opacity is not None:
            self.color_opacity.release(self._id)

    @property
    def active_color_opacity_id(self):
        return self.server.state.active_color_opacity_id

    @active_color_opacity_id.setter
    def active_color_opacity_id(self, value):
        with self.server.state as s:
            s.active_color_opacity_id = value

    @watch("use_internal_color_opacity", eager=True)
    def _on_custom_color_opacity_change(self, use_internal):
        # unsubscribe from the current color_opacity
        if self._color_opacity_unwatch_0 is not None:
            self._color_opacity_unwatch_0()
            self._color_opacity_unwatch_0 = None

        if self._color_opacity_unwatch_1 is not None:
            self._color_opacity_unwatch_1()
            self._color_opacity_unwatch_1 = None

        # The eager first call happens inside __init__, before
        # post_init_color_opacity built the internal map.
        internal = getattr(self, "_internal_color_opacity", None)
        if use_internal:
            if internal is None:
                return
            active = internal
            if internal.port is not self.source_port:
                internal.bind(self.source_port)
        else:
            active = self.source_port.color_opacity

        previous = self.color_opacity
        if previous is not None and previous is not active:
            previous.release(self._id)
        active.acquire(self._id)

        if previous and self.active_color_opacity_id == previous._id:
            self.active_color_opacity_id = active._id

        self.color_opacity = active

        self._color_opacity_unwatch_0 = active.watch(
            ["active_data_array"],
            self.on_color_opacity_active_array_change,
        )

        # can this rerender happen automatically when the lut/pwf is modified?
        self._color_opacity_unwatch_1 = active.watch(
            ["color_points", "opacity_points", "color_space"],
            self.render,
        )

        self.on_color_opacity_active_array_change(active.active_data_array)

        if self.representation is None:
            return

        # Apply colors
        self.representation.use_lut(active.lut)

        # Apply opacity (if available)
        self.representation.use_pwf(active.pwf)

        self.render()

    def on_color_opacity_active_array_change(self, active_data_array):
        if not active_data_array:
            return

        if self.representation is None:
            return

        self.representation.ColorArrayName = ("POINTS", active_data_array)


# -----------------------------------------------------------------------------
class FieldSyncMixin:
    """``push``/``pull`` for sinks whose representation has one property
    per synced field in ``FIELDS``; ``pull_status`` refreshes the
    read-only fields the panel shows."""

    FIELDS: tuple[str, ...] = ()

    def pull(self):
        super().pull()
        representation = self.representation
        if representation is None:
            return
        for field in self.FIELDS:
            setattr(self, field, getattr(representation, field))
        self.pull_status()

    def pull_status(self):
        """Read-only fields derived from the representation (subclasses)."""

    def push(self):
        representation = self.representation
        if representation is None:
            return
        for field in self.FIELDS:
            setattr(representation, field, getattr(self, field))


# -----------------------------------------------------------------------------
class PlaneModelMixin:
    """The plane fields of a slice or a clip (``PlaneRepresentation``):
    ``SliceDirection``, ``Slice`` (-1 for the middle), ``SliceMax``,
    ``PlaneCenter`` and ``PlaneNormal``. The plane fields follow the plane
    in every direction, but only a Custom plane takes them from the model.
    Dragging the handles updates them through ``pull_plane``."""

    @property
    def is_custom(self):
        return self.SliceDirection == "Custom"

    def pull_plane(self):
        """Read the plane back: the resolved slice index, the direction (the
        handles may have switched it to Custom) and the plane itself."""
        representation = self.representation
        if representation is None:
            return

        self.SliceDirection = representation.SliceDirection
        self.Slice = int(representation.Slice)
        if representation.is_ortho:
            self.SliceMax = max(representation.slice_count() - 1, 0)
        self.PlaneCenter = tuple(representation.PlaneCenter)
        self.PlaneNormal = tuple(representation.PlaneNormal)

    def push_plane(self):
        representation = self.representation
        if self.is_custom:
            representation.PlaneCenter = tuple(self.PlaneCenter)
            representation.PlaneNormal = tuple(self.PlaneNormal)
        representation.SliceDirection = self.SliceDirection
        representation.Slice = self.Slice

    def set_normal_to_view(self):
        """Make the plane face the camera (the desktop's button): a Custom
        plane through the current center along the view direction."""
        camera = self.view.vtk_view.renderer.GetActiveCamera()
        position, focal_point = camera.GetPosition(), camera.GetFocalPoint()
        normal = tuple(f - p for f, p in zip(focal_point, position, strict=True))
        if not any(normal):
            return
        self.PlaneNormal = normal
        self.SliceDirection = "Custom"


# -----------------------------------------------------------------------------
class OutlineSinkNodeModel(SinkNodeModel):
    """Bounding box of the input, with the desktop's optional grid axes.

    The axes are titled X, Y and Z unless custom titles are on (the desktop
    appends the data's units, which the pipeline does not carry). Turning
    the axes off turns the grid and the custom titles off with them, as the
    desktop's panel does."""

    Color = Sync(str, "#e6e6e6")  # box, axes and titles
    ShowGridAxes = Sync(bool, False)
    ShowGrid = Sync(bool, False)  # grid lines on the axes' faces
    UseCustomAxesTitles = Sync(bool, False)
    XTitle = Sync(str, "X")
    YTitle = Sync(str, "Y")
    ZTitle = Sync(str, "Z")

    DEFAULT_TITLES = ("X", "Y", "Z")

    def pull(self):
        super().pull()
        if self.representation is None:
            return

        self.Color = rgb_to_hex(self.representation.Color)
        self.ShowGridAxes = bool(self.representation.ShowGridAxes)
        self.ShowGrid = bool(self.representation.ShowGrid)

    def push(self):
        if self.representation is None:
            return

        self.representation.Color = hex_to_rgb(self.Color)
        self.representation.ShowGridAxes = self.ShowGridAxes
        self.representation.ShowGrid = self.ShowGrid
        self.representation.Titles = (
            (self.XTitle, self.YTitle, self.ZTitle)
            if self.UseCustomAxesTitles
            else self.DEFAULT_TITLES
        )

    @watch("ShowGridAxes")
    def _on_show_grid_axes_change(self, show):
        if not show:
            self.ShowGrid = False
            self.UseCustomAxesTitles = False

    @watch(
        "Color",
        "ShowGridAxes",
        "ShowGrid",
        "UseCustomAxesTitles",
        "XTitle",
        "YTitle",
        "ZTitle",
    )
    def _on_prop_change(self, *_):
        self.push()
        self.render()


# -----------------------------------------------------------------------------
class VolumeSinkNodeModel(ColorOpacityMixin, SinkNodeModel):
    """Volume rendering with the desktop's settings (see
    ``VolumeRepresentation``). The representation holds the outcome of every
    setting: ``push`` hands it the panel's values and ``pull`` reads back
    what it made of them. ``pull_status`` refreshes the read-only fields the
    panel explains itself with. Lighting presets set the lighting fields;
    the user's saved presets live in the ``volume_lighting_presets`` state
    key, remembered in the settings file."""

    # Color/Opacity properties
    color_opacity = Sync(ColorOpacityModel, has_dataclass=True)
    use_internal_color_opacity = Sync(bool, False)

    # Volume specific, defaults as on the desktop (the Simple lighting)
    InterpolationType = Sync(str, "Linear")  # Nearest, Linear
    BlendMode = Sync(str, "Composite")  # Composite, Max, Min, Average, Additive
    Solidity = Sync(float, 1.0)  # 1 / scalar opacity unit distance
    Jittering = Sync(bool, True)
    Shade = Sync(bool, True)
    Ambient = Sync(float, 0.1)
    Diffuse = Sync(float, 0.9)
    Specular = Sync(float, 0.3)
    SpecularPower = Sync(float, 30.0)
    ShadowsEnabled = Sync(bool, True)  # the switch in front of the strength
    VolumetricScattering = Sync(float, 0.0)  # shadow strength [0-2]
    ShadowReach = Sync(float, 0.0)  # [0-1]
    ScatteringAnisotropy = Sync(float, 0.0)  # [-1, 1]
    SmoothNormals = Sync(bool, False)
    CutOutEnabled = Sync(bool, False)
    CutOutCorner = Sync(int, 0)  # bits: 1 high X, 2 high Y, 4 high Z
    CutOutPosition = Sync(
        tuple[float, float, float],
        (0.5, 0.5, 0.5),
        type_checking=TypeValidation.SKIP,  # edited by the panel as an array
    )
    ExplodedEnabled = Sync(bool, False)
    ExplodedAxis = Sync(str, "Z")  # X, Y, Z, Custom
    ExplodedDirection = Sync(
        tuple[float, float, float],
        (1.0, 1.0, 1.0),
        type_checking=TypeValidation.SKIP,
    )
    ExplodedShowArrow = Sync(bool, True)
    ExplodedChunks = Sync(int, 4)  # [2-16]
    ExplodedGap = Sync(float, 0.25)  # [0-1] of the length along the axis
    ExplodedOffset = Sync(int, 0)  # voxels

    # Read-only: what the panel shows about where the volume is rendered
    LightingPreset = Sync(str, "Simple")  # the preset matching, or Custom
    UserLightingPreset = Sync(str, "")  # the saved preset matching
    ScatteringAvailable = Sync(bool, True)
    ScatteringUnavailableReason = Sync(str, "")
    Bricked = Sync(bool, False)
    MultiVolumeActive = Sync(bool, False)
    MultiVolumeLead = Sync(bool, False)
    MultiVolumeLeadLabel = Sync(str, "")
    ExplodedOffsetLimit = Sync(int, 0)

    # A label map port's first data switched to nearest interpolation and
    # shading (the desktop's labelMapDefaultsApplied), see the representation
    label_map_defaults_applied = ServerOnly(bool, False)

    FIELDS = (
        "InterpolationType",
        "BlendMode",
        "Solidity",
        "Jittering",
        *LIGHTING_FIELDS,
        "ShadowsEnabled",
        "CutOutCorner",
        "CutOutPosition",
        "ExplodedAxis",
        "ExplodedDirection",
        "ExplodedShowArrow",
        "ExplodedChunks",
        "ExplodedGap",
        "ExplodedOffset",
    )
    TUPLE_FIELDS = ("CutOutPosition", "ExplodedDirection")

    def __init__(self, server, **kwargs):
        self.pre_init_color_opacity()
        super().__init__(server, **kwargs)
        self.post_init_color_opacity()

    def pull(self):
        super().pull()
        representation = self.representation
        if representation is None:
            return

        for field in (*self.FIELDS, "CutOutEnabled", "ExplodedEnabled"):
            value = getattr(representation, field)
            setattr(self, field, tuple(value) if field in self.TUPLE_FIELDS else value)
        self.pull_status()

    def pull_status(self):
        representation = self.representation
        if representation is None:
            return

        self.Bricked = bool(representation.bricked)
        self.ScatteringAvailable = bool(representation.scattering_available)
        self.ScatteringUnavailableReason = representation.scattering_unavailable_reason
        self.MultiVolumeActive = bool(representation.composited)
        self.MultiVolumeLead = bool(representation.multi_volume_lead)
        self.MultiVolumeLeadLabel = representation.multi_volume_lead_label
        self.ExplodedOffsetLimit = int(representation.exploded_offset_limit)
        self.pull_presets()

    def pull_presets(self):
        """Which built-in preset the lighting matches (by the requested
        shadow strength) and which saved one (by the strength rendering,
        which is what saving stores), as on the desktop."""
        self.LightingPreset = matching_preset(self.lighting_values())
        self.UserLightingPreset = matching_user_preset(
            self.user_presets, self.rendered_lighting_values()
        )

    def push(self):
        representation = self.representation
        if representation is None:
            return

        for field in self.FIELDS:
            value = getattr(self, field)
            setattr(
                representation,
                field,
                tuple(value) if field in self.TUPLE_FIELDS else value,
            )
        # The cut-out and the exploded view exclude each other: when both
        # are asked for, the one just switched on wins.
        cut_out, exploded = self.CutOutEnabled, self.ExplodedEnabled
        if cut_out and exploded:
            if representation.CutOutEnabled:
                cut_out = False
            else:
                exploded = False
        representation.CutOutEnabled = cut_out
        representation.ExplodedEnabled = exploded

    @watch(
        *FIELDS,
        "CutOutEnabled",
        "ExplodedEnabled",
    )
    def _on_prop_change(self, *_):
        self.push()
        self.pull()
        self.render()

    # ---- lighting presets ------------------------------------------------------

    def lighting_values(self) -> dict:
        return {field: getattr(self, field) for field in LIGHTING_FIELDS}

    def rendered_lighting_values(self) -> dict:
        """The lighting with the shadow strength actually rendering: none
        while shadows are off."""
        values = self.lighting_values()
        if not self.ShadowsEnabled:
            values["VolumetricScattering"] = 0.0
        return values

    def apply_lighting(self, values: dict):
        """Set the lighting fields. A preset that casts shadows is a request
        to see them, so it switches shadows back on."""
        if values["VolumetricScattering"] > 0:
            self.ShadowsEnabled = True
        for field in LIGHTING_FIELDS:
            setattr(self, field, values[field])
        self.pull_presets()

    def apply_lighting_preset(self, name: str):
        preset = LIGHTING_PRESETS.get(name)
        if preset is not None:
            self.apply_lighting(preset)

    @property
    def user_presets(self) -> list:
        return list(self.server.state.volume_lighting_presets or [])

    def apply_user_lighting_preset(self, name: str):
        for preset in self.user_presets:
            if preset.get("name") == name:
                self.apply_lighting(user_preset_values(preset))
                return

    def save_user_lighting_preset(self, name: str):
        """Save the lighting as ``name``, replacing a preset of that name.
        The shadow strength saved is the one rendering (none while shadows
        are off), so applying the preset never turns them back on."""
        name = name.strip()
        if not name:
            return
        presets = [p for p in self.user_presets if p.get("name") != name]
        presets.append(user_preset(name, self.rendered_lighting_values()))
        self.server.state.volume_lighting_presets = presets
        self.pull_presets()

    def rename_user_lighting_preset(self, name: str, new_name: str) -> bool:
        """False, changing nothing, when there is no such preset, the new
        name is blank, or another preset has it."""
        new_name = new_name.strip()
        names = [p.get("name") for p in self.user_presets]
        if name not in names or not new_name or new_name in names:
            return False
        self.server.state.volume_lighting_presets = [
            {**p, "name": new_name} if p.get("name") == name else p
            for p in self.user_presets
        ]
        self.pull_presets()
        return True

    def delete_user_lighting_preset(self, name: str):
        self.server.state.volume_lighting_presets = [
            p for p in self.user_presets if p.get("name") != name
        ]
        self.pull_presets()

    # ---- exploded view -----------------------------------------------------------

    def set_exploded(self, **fields):
        """Set exploded view fields and refit the camera around the result,
        as the desktop does when the user turns it on or changes its axis
        (a loaded state keeps its camera)."""
        for field, value in fields.items():
            setattr(self, field, value)
        self.push()
        self.pull()
        self.reset_camera()
        self.render()


# -----------------------------------------------------------------------------
class LabelMapSinkNodeModel(VolumeSinkNodeModel):
    """A label map as surfaces or a volume (``LabelMapRepresentation``):
    the volume's fields (interpolation and blending pinned) plus the
    representation and the surface's smoothing and opacity.
    ``label_table`` is the table the sink shows, the port's or its own
    (``LabelsAdopted``), which the panel edits."""

    Representation = Sync(str, "Surface")  # Surface, Volume
    SurfaceSmoothing = Sync(int, 16)  # iterations [0-32]
    SurfaceOpacity = Sync(float, 1.0)

    # Read-only
    label_table = Sync(LabelTableModel | None, None, has_dataclass=True)
    LabelsAdopted = Sync(bool, False)
    LabelsUnsupportedReason = Sync(str, "")

    # The ambient floor was applied once (the desktop's volumeLookApplied)
    volume_look_applied = ServerOnly(bool, False)

    LABEL_FIELDS = ("Representation", "SurfaceSmoothing", "SurfaceOpacity")

    def pull(self):
        super().pull()
        representation = self.representation
        if representation is None:
            return
        for field in self.LABEL_FIELDS:
            setattr(self, field, getattr(representation, field))

    def pull_status(self):
        super().pull_status()
        representation = self.representation
        if representation is None:
            return
        self.label_table = representation.label_table
        self.LabelsAdopted = bool(representation.adopted)
        self.LabelsUnsupportedReason = representation.unsupported_reason

    def push(self):
        super().push()
        representation = self.representation
        if representation is None:
            return
        for field in self.LABEL_FIELDS:
            setattr(representation, field, getattr(self, field))

    @watch(*LABEL_FIELDS)
    def _on_label_prop_change(self, *_):
        self.push()
        self.pull()
        self.render()

    @watch("use_internal_color_opacity")
    def _on_label_color_map_change(self, use_internal):
        """The sink's own map shows the labels too. Adopted labels have no
        other map to go on: the port's belongs to a plain volume."""
        representation = self.representation
        if representation is None:
            return
        if representation.adopted and not use_internal:
            # Set back inside the flush that brought the change, the field
            # would not notify again: rebind by hand.
            self.use_internal_color_opacity = True
            self._on_custom_color_opacity_change(True)
        representation.project_labels()
        self.render()


# -----------------------------------------------------------------------------
class SliceSinkNodeModel(PlaneModelMixin, ColorOpacityMixin, SinkNodeModel):
    """A slice through the data: axis-aligned, or Custom (any center and
    normal), with the desktop's thick slicing, opacity, "map scalars" and
    in-view handles (``ShowArrow``).

    ``Slice`` -1 stands for the middle slice. A new sink starts there, and
    the panel resets it when the direction changes, which re-centers the
    slice as the desktop does. The representation resolves it once the
    extent is known and the resolved index is read back.
    ``PlaneCenter`` and ``PlaneNormal`` follow the plane in every direction
    (the panel shows them), but only a Custom plane takes them from the
    model. Dragging the handles in the view updates the fields through
    ``pull_plane``."""

    # Color/Opacity properties
    color_opacity = Sync(ColorOpacityModel, has_dataclass=True)
    use_internal_color_opacity = Sync(bool, False)

    # Slice specific
    SliceDirection = Sync(str, "XY Plane", type_checking=TypeValidation.SKIP)
    SliceDirections = Sync(
        tuple[str, str, str, str], ("XY Plane", "YZ Plane", "XZ Plane", "Custom")
    )
    Slice = Sync(int, -1)
    SliceMax = Sync(int, 0)
    # Edited by the panel as JSON arrays: no tuple validation.
    PlaneCenter = Sync(
        tuple[float, float, float],
        (0.0, 0.0, 0.0),
        type_checking=TypeValidation.SKIP,
    )
    PlaneNormal = Sync(
        tuple[float, float, float],
        (0.0, 0.0, 1.0),
        type_checking=TypeValidation.SKIP,
    )
    Interpolate = Sync(bool, False)  # linear (on) or nearest sampling
    Opacity = Sync(float, 1.0)
    SliceThickness = Sync(int, 1)  # slices combined along the normal
    ThickSliceMode = Sync(str, "Mean")  # Minimum, Maximum, Mean, Summation
    MapScalars = Sync(bool, True)  # off: raw values in gray
    ShowArrow = Sync(bool, True)  # the in-view handles

    def __init__(self, server, **kwargs):
        self.pre_init_color_opacity()
        super().__init__(server, **kwargs)
        self.post_init_color_opacity()

    def pull(self):
        super().pull()
        if self.representation is None:
            return

        representation = self.representation
        self.Interpolate = bool(representation.Interpolate)
        self.Opacity = float(representation.Opacity)
        self.SliceThickness = int(representation.SliceThickness)
        self.ThickSliceMode = str(representation.ThickSliceMode)
        self.MapScalars = bool(representation.MapScalars)
        self.ShowArrow = bool(representation.ShowArrow)
        self.pull_plane()

    def push(self):
        if self.representation is None:
            return

        self.push_plane()
        representation = self.representation
        representation.Interpolate = self.Interpolate
        representation.Opacity = self.Opacity
        representation.SliceThickness = self.SliceThickness
        representation.ThickSliceMode = self.ThickSliceMode
        representation.MapScalars = self.MapScalars
        representation.ShowArrow = self.ShowArrow

    @watch(
        "SliceDirection",
        "Slice",
        "PlaneCenter",
        "PlaneNormal",
        "Interpolate",
        "Opacity",
        "SliceThickness",
        "ThickSliceMode",
        "MapScalars",
        "ShowArrow",
    )
    def _on_prop_change(self, *_):
        self.push()
        self.pull_plane()
        self.render()


# -----------------------------------------------------------------------------
class ContourSinkNodeModel(FieldSyncMixin, ColorOpacityMixin, SinkNodeModel):
    """An isosurface (see ``ContourRepresentation``), with the desktop's
    settings. ``IsoValue`` None: two thirds up the range once data comes.
    The surface is colored by its color map's array."""

    # Color/Opacity properties
    color_opacity = Sync(ColorOpacityModel, has_dataclass=True)
    use_internal_color_opacity = Sync(bool, False)

    IsoValue = Sync(float, None, type_checking=TypeValidation.SKIP)
    ContourBy = Sync(str, "")  # "" = the data's active array
    Mode = Sync(str, "Surface")  # Surface, Wireframe, Points
    Opacity = Sync(float, 1.0)
    Ambient = Sync(float, 0.0)
    Diffuse = Sync(float, 1.0)
    Specular = Sync(float, 1.0)
    SpecularPower = Sync(float, 100.0)
    Color = Sync(str, "#ffffff")  # the solid color
    UseSolidColor = Sync(bool, False)
    MapScalars = Sync(bool, True)

    # Read-only
    IsoRange = Sync(tuple[float, float], (0.0, 1.0))
    ArrayNames = Sync(list[str], list)

    FIELDS = (
        "ContourBy",
        "IsoValue",
        "Mode",
        "Opacity",
        "Ambient",
        "Diffuse",
        "Specular",
        "SpecularPower",
        "Color",
        "UseSolidColor",
        "MapScalars",
    )

    def __init__(self, server, **kwargs):
        self.pre_init_color_opacity()
        super().__init__(server, **kwargs)
        self.post_init_color_opacity()

    def pull_status(self):
        self.IsoRange = self.representation.iso_range
        self.ArrayNames = self.representation.array_names()

    @watch(*FIELDS)
    def _on_prop_change(self, *_):
        self.push()
        self.pull()
        self.render()


# -----------------------------------------------------------------------------
class ThresholdSinkNodeModel(FieldSyncMixin, ColorOpacityMixin, SinkNodeModel):
    """The voxels in a range (see ``ThresholdRepresentation``), with the
    desktop's settings. ``Minimum`` and ``Maximum`` None: the brightest
    voxels once data comes. Colored per voxel by its color map's array."""

    # Color/Opacity properties
    color_opacity = Sync(ColorOpacityModel, has_dataclass=True)
    use_internal_color_opacity = Sync(bool, False)

    # "" = the data's active array; an index from a desktop state file
    # until data arrives
    ThresholdBy = Sync(str, "", type_checking=TypeValidation.SKIP)
    Minimum = Sync(float, None, type_checking=TypeValidation.SKIP)
    Maximum = Sync(float, None, type_checking=TypeValidation.SKIP)
    Mode = Sync(str, "Surface")  # Surface, Wireframe, Points
    Opacity = Sync(float, 1.0)
    Specular = Sync(float, 0.0)
    MapScalars = Sync(bool, True)

    # Read-only
    ScalarRange = Sync(tuple[float, float], (0.0, 1.0))
    ArrayNames = Sync(list[str], list)

    FIELDS = (
        "ThresholdBy",
        "Minimum",
        "Maximum",
        "Mode",
        "Opacity",
        "Specular",
        "MapScalars",
    )

    def __init__(self, server, **kwargs):
        self.pre_init_color_opacity()
        super().__init__(server, **kwargs)
        self.post_init_color_opacity()

    def pull_status(self):
        self.ScalarRange = self.representation.scalar_range
        self.ArrayNames = self.representation.array_names()

    @watch(*FIELDS)
    def _on_prop_change(self, *_):
        self.push()
        self.pull()
        self.render()


# -----------------------------------------------------------------------------
class ClipSinkNodeModel(PlaneModelMixin, SinkNodeModel):
    """A plane cutting the other visualizations of its group (see
    ``ClipRepresentation``): placed like a slice, drawn translucent."""

    SliceDirection = Sync(str, "XY Plane", type_checking=TypeValidation.SKIP)
    SliceDirections = Sync(
        tuple[str, str, str, str], ("XY Plane", "YZ Plane", "XZ Plane", "Custom")
    )
    Slice = Sync(int, -1)  # -1: the middle
    SliceMax = Sync(int, 0)
    # Edited by the panel as JSON arrays: no tuple validation.
    PlaneCenter = Sync(
        tuple[float, float, float],
        (0.0, 0.0, 0.0),
        type_checking=TypeValidation.SKIP,
    )
    PlaneNormal = Sync(
        tuple[float, float, float],
        (0.0, 0.0, 1.0),
        type_checking=TypeValidation.SKIP,
    )
    ShowArrow = Sync(bool, True)
    ShowPlane = Sync(bool, True)
    InvertPlane = Sync(bool, False)
    Opacity = Sync(float, 0.5)
    Color = Sync(str, "#ffffff")

    FIELDS = ("ShowArrow", "ShowPlane", "InvertPlane", "Opacity", "Color")

    def pull(self):
        super().pull()
        representation = self.representation
        if representation is None:
            return
        for field in self.FIELDS:
            setattr(self, field, getattr(representation, field))
        self.pull_plane()

    def push(self):
        representation = self.representation
        if representation is None:
            return
        self.push_plane()
        for field in self.FIELDS:
            setattr(representation, field, getattr(self, field))

    def invert(self, value: bool):
        """The panel's Invert: an axis-aligned plane flips through
        ``InvertPlane``; a Custom one flips its own normal (a saved Custom
        normal is already the inverted one, so loading never flips it)."""
        if bool(value) == self.InvertPlane:
            return
        self.InvertPlane = bool(value)
        if self.is_custom:
            self.PlaneNormal = tuple(-c for c in self.PlaneNormal)

    @watch(
        "SliceDirection",
        "Slice",
        "PlaneCenter",
        "PlaneNormal",
        *FIELDS,
    )
    def _on_prop_change(self, *_):
        self.push()
        self.pull()
        self.render()


# -----------------------------------------------------------------------------
class MoleculeSinkNodeModel(FieldSyncMixin, SinkNodeModel):
    """Ball-and-stick atoms and bonds (see ``MoleculeRepresentation``). The
    defaults are vtkMoleculeMapper's ball-and-stick ones, as on the
    desktop."""

    BallRadius = Sync(float, 0.3)  # scale of the atomic radii [0-4]
    StickRadius = Sync(float, 0.075)  # [0-2]

    FIELDS = ("BallRadius", "StickRadius")

    @watch(*FIELDS)
    def _on_prop_change(self, *_):
        self.push()
        self.pull()
        self.render()
