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

from .color_opacity import ColorOpacityModel, create_color_opacity
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
    # Color/Opacity properties
    color_opacity = Sync(ColorOpacityModel, has_dataclass=True)
    use_internal_color_opacity = Sync(bool, False)

    # Volume specific
    InterpolationType = Sync(str, "Nearest")  # Nearest, Linear, Cubic
    Shade = Sync(bool, False)
    GlobalIlluminationReach = Sync(float, 0)  # [0-1]
    VolumetricScatteringBlending = Sync(float, 0)  # [0-2]
    VolumeAnisotropy = Sync(float, 0)  # [-1,1]

    def __init__(self, server, **kwargs):
        self.pre_init_color_opacity()
        super().__init__(server, **kwargs)
        self.post_init_color_opacity()

    def pull(self):
        super().pull()
        if self.representation is None:
            return

        self.InterpolationType = str(self.representation.InterpolationType)
        self.Shade = bool(self.representation.Shade)
        self.GlobalIlluminationReach = float(
            self.representation.GlobalIlluminationReach
        )
        self.VolumetricScatteringBlending = float(
            self.representation.VolumetricScatteringBlending
        )
        self.VolumeAnisotropy = float(self.representation.VolumeAnisotropy)

    def push(self):
        if self.representation is None:
            return

        self.representation.InterpolationType = self.InterpolationType
        self.representation.Shade = int(self.Shade)
        self.representation.GlobalIlluminationReach = self.GlobalIlluminationReach
        self.representation.VolumetricScatteringBlending = (
            self.VolumetricScatteringBlending
        )
        self.representation.VolumeAnisotropy = self.VolumeAnisotropy

    @watch(
        "InterpolationType",
        "Shade",
        "GlobalIlluminationReach",
        "VolumetricScatteringBlending",
        "VolumeAnisotropy",
    )
    def _on_prop_change(self, *_):
        self.push()
        self.render()


# -----------------------------------------------------------------------------
class SliceSinkNodeModel(ColorOpacityMixin, SinkNodeModel):
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

    @property
    def is_custom(self):
        return self.SliceDirection == "Custom"

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

    def push(self):
        if self.representation is None:
            return

        representation = self.representation
        if self.is_custom:
            representation.PlaneCenter = tuple(self.PlaneCenter)
            representation.PlaneNormal = tuple(self.PlaneNormal)
        representation.SliceDirection = self.SliceDirection
        representation.Slice = self.Slice
        representation.Interpolate = self.Interpolate
        representation.Opacity = self.Opacity
        representation.SliceThickness = self.SliceThickness
        representation.ThickSliceMode = self.ThickSliceMode
        representation.MapScalars = self.MapScalars
        representation.ShowArrow = self.ShowArrow

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
