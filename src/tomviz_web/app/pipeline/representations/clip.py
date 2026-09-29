"""Clip: a plane that cuts away half of the other visualizations of its
group, after the desktop's ClipSink.

The plane is placed like a slice's (``PlaneRepresentation``: axis-aligned
or Custom, with the desktop's handles) and drawn translucent in one color.
Its ``clip_plane`` keeps the side its normal points to; Invert flips an
axis-aligned plane's normal (the panel flips a Custom one's). While the
clip is visible and has data, the pipeline manager hands ``clip_plane`` to
every clippable sink fed by the same port as the clip, in any view
(``PipelineManager.refresh_clipping``), as the desktop does with a clip's
siblings. Half opaque by default, as on the desktop, but white.
"""

from __future__ import annotations

from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkCommonDataModel import vtkPlane

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.representations._plane import PlaneRepresentation
from tomviz_web.app.pipeline.representations.core import RepresentationType
from tomviz_web.app.utils.colors import hex_to_rgb, rgb_to_hex

# The desktop's off-white (#cccccc) is the web view's background: half
# opaque, the plane would vanish against it.
DEFAULT_COLOR = "#ffffff"
DEFAULT_OPACITY = 0.5


class ClipRepresentation(PlaneRepresentation):
    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server, view)
        self.manager = pipeline_manager

        self._show_plane = True
        self._invert = False
        self._clipping = False
        self.clip_plane = vtkPlane()

        # Every value in the plane's color: one entry, clamped to
        self.lut = vtkLookupTable()
        self.lut.SetNumberOfTableValues(1)
        self.lut.SetTableRange(0.0, 1.0)
        self.property.SetLookupTable(self.lut)
        self.property.UseLookupTableScalarRangeOn()
        self.property.SetInterpolationTypeToLinear()
        self.property.SetOpacity(DEFAULT_OPACITY)
        self.Color = DEFAULT_COLOR
        self.attach(view.vtk_view)

        self.model = data_model.ClipSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.CLIP.model_kwargs,
        )

    # ---- clipping ----------------------------------------------------------

    @property
    def clipping(self) -> bool:
        """Whether the clip cuts its group: visible, with data."""
        return self._clipping

    def _update_clipping(self):
        clipping = self._visible and self.image is not None
        if clipping != self._clipping:
            self._clipping = clipping
            self.manager.refresh_clipping()

    def set_visible(self, visible: bool):
        super().set_visible(visible)
        self._update_clipping()

    def set_input(self, image, prepared=None):
        super().set_input(image, prepared)
        self._update_clipping()

    def clear_input(self):
        super().clear_input()
        self._update_clipping()

    def _plane_changed(self):
        self.clip_plane.SetOrigin(self.plane.GetOrigin())
        self.clip_plane.SetNormal(self.plane.GetNormal())
        if self._clipping:
            self.manager.render_clip_targets(self)

    # ---- appearance --------------------------------------------------------

    @property
    def plane_shown(self) -> bool:
        return self._show_plane

    @property
    def handles_shown(self) -> bool:
        """A hidden plane hides its arrow too, whatever Show Arrow says."""
        return self._visible and self._show_plane and self._show_arrow

    @property
    def ShowPlane(self):
        return self._show_plane

    @ShowPlane.setter
    def ShowPlane(self, value):
        """The plane can be hidden; it still clips."""
        self._show_plane = bool(value)
        self.actor.visibility = self._visible and self._show_plane
        self._update_widget_visibility()

    @property
    def InvertPlane(self):
        return self._invert

    @InvertPlane.setter
    def InvertPlane(self, value):
        """Keep the other side: flips an axis-aligned plane's normal."""
        self._invert = bool(value)
        self.normal_sign = -1.0 if self._invert else 1.0
        self._update_plane()

    @property
    def Opacity(self):
        return self.property.GetOpacity()

    @Opacity.setter
    def Opacity(self, value):
        self.property.SetOpacity(float(value))

    @property
    def Color(self):
        return rgb_to_hex(self.lut.GetTableValue(0)[:3])

    @Color.setter
    def Color(self, value):
        self.lut.SetTableValue(0, *hex_to_rgb(value), 1.0)


RepresentationType.CLIP.register_class(ClipRepresentation)
