"""Volume: GPU ray casting of the image, with the desktop's settings.

After the desktop's ``VolumeSink``: interpolation, blending, solidity, ray
jittering and lighting (Phong shading plus volumetric scattering, "shadows",
behind a switch that keeps the requested strength), and two ways of seeing
inside: the cut-out, which crops one octant away, and the exploded view,
which renders the volume as slabs pulled apart along an axis or any
direction (the slabs share the image and the property; each has its own
mapper, cropped to its share, or clipped by a pair of planes for a custom
direction, and they are drawn back to front).

A volume too large for one GPU 3D texture is split into bricks and drawn by
a ``vtkMultiBlockVolumeMapper`` (no cropping, exploded view nor shadows
there). Volumes sharing a view are drawn together by the view's
``MultiVolumeCoordinator`` from the second one on.

The representation holds every setting; ``VolumeSinkNodeModel`` pushes the
panel's values here and reads the outcome back (a switch the data refused,
the cut-out the exploded view turned off, where the volume is rendered).

On a label map port the first data switches to nearest interpolation and
shading, once (the desktop's ``labelMapDefaultsApplied``): linear
interpolation between labels 2 and 6 samples a 4.
"""

from __future__ import annotations

import math

from loguru import logger
from vtkmodules.vtkCommonDataModel import vtkPlane
from vtkmodules.vtkRenderingCore import vtkVolume, vtkVolumeProperty
from vtkmodules.vtkRenderingVolume import vtkGPUVolumeRayCastMapper

# Also registers the OpenGL GPU volume mapper behind vtkGPUVolumeRayCastMapper
from vtkmodules.vtkRenderingVolumeOpenGL2 import vtkMultiBlockVolumeMapper

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.representations.core import (
    Representation,
    RepresentationType,
    set_mapper_clipping_planes,
)
from tomviz_web.app.pipeline.vtk.bricking import (
    brick_volume,
    exceeds_texture_limit,
    maximum_texture_size,
)
from tomviz_web.app.pipeline.vtk.multi_volume import MultiVolumeCoordinator
from tomviz_web.app.pipeline.vtk.slice_widget import SlicePlaneWidget
from tomviz_web.app.utils.volume import (
    CUSTOM_AXIS,
    EXPLODED_AXES,
    LIGHTING_PRESETS,
    cut_out_flags,
    cut_out_planes,
    exploded_direction,
    exploded_extent,
    exploded_offset_limit,
    exploded_shift,
    exploded_voxel_step,
)

# vtkVolumeMapper's blend modes, in its order
BLEND_MODES = ("Composite", "Max", "Min", "Average", "Additive")
# vtkVolumeProperty's interpolation types, in their order
INTERPOLATION_TYPES = ("Nearest", "Linear")
# What vtkGPUVolumeRayCastMapper's shader takes
MAX_CLIPPING_PLANES = 6


def _noop(*_):
    pass


class VolumeRepresentation(Representation):
    TYPE = RepresentationType.VOLUME

    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server)
        self.vtk_view = view.vtk_view

        self._visible = False
        # A half-voxel ray step (a label map's), see _apply_sampling
        self.fine_sampling = False
        # Mapper-level settings, applied to every mapper (slabs, bricks)
        self._blend_mode = 0
        self._jittering = True
        self._shadow_reach = 0.0
        self._smooth_normals = False
        # Shadows: the requested strength, and the switch in front of it
        self._scattering = 0.0
        self._shadows_enabled = True
        self._cut_out_enabled = False
        self._cut_out_corner = 0
        self._cut_out_position = (0.5, 0.5, 0.5)
        self._exploded_enabled = False
        self._exploded_axis = 2
        self._exploded_direction = (1.0, 1.0, 1.0)
        self._exploded_show_arrow = True
        self._exploded_chunks = 4
        self._exploded_gap = 0.25
        self._exploded_offset = 0

        # None: ask the GPU for its 3D texture size limit
        self.texture_size_limit: int | None = None
        self.bricked = False
        # Drawn by the view's multi-volume, and whether as its lead
        self.composited = False
        self.multi_volume_lead = False
        self.multi_volume_lead_label = ""

        self.property = vtkVolumeProperty()
        self.property.SetInterpolationTypeToLinear()
        self.property.SetIndependentComponents(True)

        # Exploded slabs 1..n-1 (slab 0 is the actor), and one pair of
        # bounding planes per slab while the direction is custom.
        self.slabs: list[tuple[vtkVolume, vtkGPUVolumeRayCastMapper]] = []
        self.slab_planes: list[tuple[vtkPlane, vtkPlane]] = []
        self._slab_clipping = False
        self._clip_planes: list[vtkPlane] = []  # the clips of the group
        self._order_reversed = False
        self._order_dirty = True

        self.mapper = self._make_mapper()
        self.brick_mapper = vtkMultiBlockVolumeMapper()
        self.brick_mapper.SetScalarModeToUsePointFieldData()
        self.actor = vtkVolume(mapper=self.mapper, property=self.property)
        self.producer >> self.mapper
        self.set_lighting(LIGHTING_PRESETS["Simple"])  # the desktop's default

        renderer = self.vtk_view.renderer
        # The desktop's direction arrow for a custom exploded view: drag its
        # tip to turn the direction.
        self.widget = SlicePlaneWidget(
            self.vtk_view.interactor,
            renderer,
            None,
            on_start=_noop,
            on_push=_noop,
            on_rotate=self._on_direction_drag,
            on_move=_noop,
            on_end=_noop,
            show_sphere=False,
        )
        # Slabs composite in prop order: sort them before every render.
        self._sort_observer = renderer.AddObserver("StartEvent", self._sort_slabs)
        self.attach(self.vtk_view)
        self.model = self.create_model(source_port, view)

    def create_model(self, source_port, view):
        return data_model.VolumeSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **self.TYPE.model_kwargs,
        )

    @property
    def label(self) -> str:
        return self.model.label if self.model is not None else "Volume"

    # ---- props ---------------------------------------------------------------

    @property
    def volumes(self) -> list[vtkVolume]:
        return [self.actor, *(volume for volume, _ in self.slabs)]

    @property
    def mappers(self) -> list[vtkGPUVolumeRayCastMapper]:
        return [self.mapper, *(mapper for _, mapper in self.slabs)]

    @property
    def props(self):
        return (*self.volumes, *self.widget.props)

    def set_visible(self, visible: bool):
        self._visible = bool(visible)
        for volume in self.volumes:
            volume.SetVisibility(self._visible)
        self._sync_membership()
        self._update_widget()

    def set_input(self, image, prepared=None):
        super().set_input(image, prepared)
        self._apply_label_map_defaults()
        self._update_mapper_for_input(image)
        self._apply_sampling()
        self._apply_color_array()
        self._apply_cut_out()
        self._apply_exploded()
        self._apply_scattering()
        self._sync_membership()

    def clear_input(self):
        super().clear_input()
        self._update_widget()

    def detach(self, view):
        coordinator = MultiVolumeCoordinator.find(self.vtk_view)
        if coordinator is not None:
            coordinator.remove_member(self)
        self.vtk_view.renderer.RemoveObserver(self._sort_observer)
        self.widget.finalize()
        super().detach(view)

    def _make_mapper(self):
        mapper = vtkGPUVolumeRayCastMapper()
        mapper.SetScalarModeToUsePointFieldData()
        self._configure_mapper(mapper)
        return mapper

    def _configure_mapper(self, mapper):
        mapper.SetBlendMode(self._blend_mode)
        mapper.SetUseJittering(self._jittering)
        mapper.SetGlobalIlluminationReach(self._shadow_reach)
        mapper.SetComputeNormalFromOpacity(self._smooth_normals)
        self._sample_mapper(mapper)
        name = self.rendered_array
        if name:
            mapper.SelectScalarArray(name)

    # ---- sampling ----------------------------------------------------------------

    @property
    def fine_step(self) -> float | None:
        """The ray step fine sampling pins, half the smallest voxel side
        (None when off): a label has no shading normal past its one-voxel
        boundary shell, and the first hit should land in it."""
        image = self.image
        if not self.fine_sampling or image is None:
            return None
        smallest = min(abs(s) for s in image.GetSpacing())
        return 0.5 * (smallest if smallest > 0 else 1.0)

    def _sample_mapper(self, mapper):
        step = self.fine_step
        if step is None:
            mapper.AutoAdjustSampleDistancesOn()
            return
        mapper.AutoAdjustSampleDistancesOff()
        mapper.SetSampleDistance(step)
        mapper.SetImageSampleDistance(1.0)

    def _apply_sampling(self):
        for mapper in self.mappers:
            self._sample_mapper(mapper)
        coordinator = MultiVolumeCoordinator.find(self.vtk_view)
        if coordinator is not None:
            coordinator.refresh_settings()

    def _apply_label_map_defaults(self):
        """Nearest interpolation and shading on a label map port's first
        data; through the model, which pushes its fields right after."""
        model = self.model
        if model is None or model.label_map_defaults_applied:
            return
        port = model.source_port
        if port is None or not port.is_label_map:
            return
        model.InterpolationType = "Nearest"
        model.Shade = True
        model.label_map_defaults_applied = True

    def _all_mappers(self):
        """Every mapper, including the bricked one, for shared settings."""
        return [*self.mappers, self.brick_mapper]

    # ---- bricking --------------------------------------------------------------

    def _update_mapper_for_input(self, image):
        limit = self.texture_size_limit or maximum_texture_size(
            self.vtk_view.render_window
        )
        if exceeds_texture_limit(image, limit):
            self.brick_mapper.SetInputDataObject(brick_volume(image, limit))
            if not self.bricked:
                logger.info(
                    "'{}' exceeds the GPU's {} voxel texture limit: rendered in "
                    "bricks, without cropping, exploded view or shadows",
                    self.label,
                    limit,
                )
            self.actor.SetMapper(self.brick_mapper)
            self.bricked = True
        elif self.bricked:
            self.actor.SetMapper(self.mapper)
            self.brick_mapper.RemoveAllInputConnections(0)
            self.bricked = False

    # ---- color -------------------------------------------------------------------

    def use_lut(self, lut):
        if lut is None:
            return

        self.property.SetColor(lut.ctf)

    def use_pwf(self, pwf):
        if pwf is None:
            return

        self.property.SetScalarOpacity(pwf.function)

    @property
    def ColorArrayName(self):
        return getattr(self, "_color_array_name", (None, None))

    @ColorArrayName.setter
    def ColorArrayName(self, value):
        self._color_array_name = value
        self._apply_color_array()
        self._refresh_membership_input()

    @property
    def rendered_array(self) -> str:
        return self.ColorArrayName[1] or ""

    @property
    def rendered_image(self):
        """The image the volume's own mapper draws (None when bricked)."""
        return None if self.bricked else self.image

    def _apply_color_array(self):
        association, name = self.ColorArrayName
        if not name:
            return
        for mapper in self._all_mappers():
            if association == "CELLS":
                mapper.SetScalarModeToUseCellFieldData()
            else:
                mapper.SetScalarModeToUsePointFieldData()
            mapper.SelectScalarArray(name)

    # ---- rendering settings --------------------------------------------------------

    @property
    def InterpolationType(self):
        return INTERPOLATION_TYPES[self.property.GetInterpolationType()]

    @InterpolationType.setter
    def InterpolationType(self, value):
        if value == "Nearest":
            self.property.SetInterpolationTypeToNearest()
        else:
            self.property.SetInterpolationTypeToLinear()

    @property
    def BlendMode(self):
        return BLEND_MODES[self._blend_mode]

    @BlendMode.setter
    def BlendMode(self, value):
        self._blend_mode = BLEND_MODES.index(value) if value in BLEND_MODES else 0
        for mapper in self._all_mappers():
            mapper.SetBlendMode(self._blend_mode)

    @property
    def Jittering(self):
        return self._jittering

    @Jittering.setter
    def Jittering(self, value):
        """Ray jittering; the bricked mapper always jitters its bricks."""
        self._jittering = bool(value)
        for mapper in self.mappers:
            mapper.SetUseJittering(self._jittering)

    @property
    def Solidity(self):
        return 1.0 / self.property.GetScalarOpacityUnitDistance()

    @Solidity.setter
    def Solidity(self, value):
        """The inverse of the opacity unit distance (0 is ignored)."""
        if value > 0:
            self.property.SetScalarOpacityUnitDistance(1.0 / value)

    # ---- lighting ------------------------------------------------------------------

    def set_lighting(self, values: dict):
        for field, value in values.items():
            setattr(self, field, value)

    @property
    def Shade(self):
        return bool(self.property.GetShade())

    @Shade.setter
    def Shade(self, value):
        self.property.SetShade(bool(value))

    @property
    def Ambient(self):
        return self.property.GetAmbient()

    @Ambient.setter
    def Ambient(self, value):
        self.property.SetAmbient(float(value))

    @property
    def Diffuse(self):
        return self.property.GetDiffuse()

    @Diffuse.setter
    def Diffuse(self, value):
        self.property.SetDiffuse(float(value))

    @property
    def Specular(self):
        return self.property.GetSpecular()

    @Specular.setter
    def Specular(self, value):
        self.property.SetSpecular(float(value))

    @property
    def SpecularPower(self):
        return self.property.GetSpecularPower()

    @SpecularPower.setter
    def SpecularPower(self, value):
        self.property.SetSpecularPower(float(value))

    @property
    def ScatteringAnisotropy(self):
        return self.property.GetScatteringAnisotropy()

    @ScatteringAnisotropy.setter
    def ScatteringAnisotropy(self, value):
        self.property.SetScatteringAnisotropy(float(value))

    @property
    def ShadowReach(self):
        return self._shadow_reach

    @ShadowReach.setter
    def ShadowReach(self, value):
        self._shadow_reach = float(value)
        for mapper in self._all_mappers():
            mapper.SetGlobalIlluminationReach(self._shadow_reach)

    @property
    def SmoothNormals(self):
        return self._smooth_normals

    @SmoothNormals.setter
    def SmoothNormals(self, value):
        """Shading normals from the opacity function, not the raw gradient."""
        self._smooth_normals = bool(value)
        for mapper in self._all_mappers():
            mapper.SetComputeNormalFromOpacity(self._smooth_normals)
        coordinator = MultiVolumeCoordinator.find(self.vtk_view)
        if coordinator is not None:
            coordinator.refresh_settings()

    @property
    def smooth_normals(self):
        return self._smooth_normals

    @property
    def VolumetricScattering(self):
        """The requested shadow strength, kept while shadows are off."""
        return self._scattering

    @VolumetricScattering.setter
    def VolumetricScattering(self, value):
        self._scattering = min(max(float(value), 0.0), 2.0)
        self._apply_scattering()

    @property
    def ShadowsEnabled(self):
        return self._shadows_enabled

    @ShadowsEnabled.setter
    def ShadowsEnabled(self, value):
        self._shadows_enabled = bool(value)
        self._apply_scattering()

    @property
    def effective_scattering(self) -> float:
        return self._scattering if self._shadows_enabled else 0.0

    @property
    def scattering_supported(self) -> bool:
        """Bricks cannot be bounded, and every exploded slab would cast its
        own shadows: neither renders them (the desktop's rules)."""
        return not self.bricked and not self._exploded_enabled

    @property
    def scattering_available(self) -> bool:
        return self.scattering_supported and not self.composited

    @property
    def scattering_unavailable_reason(self) -> str:
        if self.scattering_available:
            return ""
        if self.composited:
            return (
                "Volumetric shadows are unavailable while the volumes in this "
                "view are rendered together, which VTK cannot shadow."
            )
        if self.bricked:
            return (
                "This volume is larger than the GPU's 3D texture size limit and "
                "is rendered in bricks, where shadows are unavailable."
            )
        return (
            "Volumetric shadows are unavailable while the exploded view is on, "
            "since every slab would render its own shadow pass."
        )

    def _apply_scattering(self):
        """Only the volume's own mapper ever shadows; the extra slabs, the
        bricks and the view's multi-volume never do."""
        scattering = self.effective_scattering if self.scattering_supported else 0.0
        self.mapper.SetVolumetricScatteringBlending(scattering)
        for _, mapper in self.slabs:
            mapper.SetVolumetricScatteringBlending(0.0)

    # ---- cut out -------------------------------------------------------------------

    @property
    def CutOutEnabled(self):
        return self._cut_out_enabled

    @CutOutEnabled.setter
    def CutOutEnabled(self, value):
        """The cut-out and the exploded view both crop: turning one on turns
        the other off."""
        self._cut_out_enabled = bool(value)
        if self._cut_out_enabled and self._exploded_enabled:
            self._exploded_enabled = False
            self._apply_exploded()
            self._apply_scattering()
        self._apply_cut_out()

    @property
    def CutOutCorner(self):
        return self._cut_out_corner

    @CutOutCorner.setter
    def CutOutCorner(self, value):
        self._cut_out_corner = min(max(int(value), 0), 7)
        self._apply_cut_out()

    @property
    def CutOutPosition(self):
        return self._cut_out_position

    @CutOutPosition.setter
    def CutOutPosition(self, value):
        self._cut_out_position = tuple(min(max(float(v), 0.0), 1.0) for v in value)
        self._apply_cut_out()

    def _apply_cut_out(self):
        image = self.image
        if image is None or self._exploded_enabled:
            return  # the exploded view owns the cropping
        if not self._cut_out_enabled:
            self.mapper.CroppingOff()
            return
        self.mapper.SetCroppingRegionPlanes(
            *cut_out_planes(image.GetBounds(), self._cut_out_position)
        )
        self.mapper.SetCroppingRegionFlags(cut_out_flags(self._cut_out_corner))
        self.mapper.CroppingOn()

    # ---- exploded view -----------------------------------------------------------------

    @property
    def ExplodedEnabled(self):
        return self._exploded_enabled

    @ExplodedEnabled.setter
    def ExplodedEnabled(self, value):
        enabled = bool(value)
        if enabled and self.bricked:
            logger.warning(
                "The exploded view is not supported for '{}': it is rendered "
                "in bricks, being larger than the GPU's 3D texture limit",
                self.label,
            )
            enabled = False
        if enabled == self._exploded_enabled:
            return
        self._exploded_enabled = enabled
        if enabled:
            self._cut_out_enabled = False
        self._apply_exploded()
        self._apply_cut_out()
        self._apply_scattering()

    @property
    def ExplodedAxis(self):
        return EXPLODED_AXES[self._exploded_axis]

    @ExplodedAxis.setter
    def ExplodedAxis(self, value):
        axis = EXPLODED_AXES.index(value) if value in EXPLODED_AXES else 2
        if axis != self._exploded_axis:
            self._exploded_axis = axis
            self._apply_exploded()

    @property
    def ExplodedDirection(self):
        return self._exploded_direction

    @ExplodedDirection.setter
    def ExplodedDirection(self, value):
        """The custom direction as given (used normalized); a zero vector
        is ignored."""
        direction = tuple(float(v) for v in value)
        if direction == self._exploded_direction or not any(direction):
            return
        self._exploded_direction = direction
        if self._exploded_axis == CUSTOM_AXIS:
            self._apply_exploded()

    @property
    def ExplodedShowArrow(self):
        return self._exploded_show_arrow

    @ExplodedShowArrow.setter
    def ExplodedShowArrow(self, value):
        self._exploded_show_arrow = bool(value)
        self._update_widget()

    @property
    def ExplodedChunks(self):
        return self._exploded_chunks

    @ExplodedChunks.setter
    def ExplodedChunks(self, value):
        chunks = min(max(int(value), 2), 16)
        if chunks != self._exploded_chunks:
            self._exploded_chunks = chunks
            self._apply_exploded()

    @property
    def ExplodedGap(self):
        return self._exploded_gap

    @ExplodedGap.setter
    def ExplodedGap(self, value):
        gap = min(max(float(value), 0.0), 1.0)
        if gap != self._exploded_gap:
            self._exploded_gap = gap
            self._place_slabs()

    @property
    def ExplodedOffset(self):
        return self._exploded_offset

    @ExplodedOffset.setter
    def ExplodedOffset(self, value):
        """Every cut plane's shift along the direction, in voxels (clamped
        where used so no slab gets thinner than a voxel)."""
        if int(value) != self._exploded_offset:
            self._exploded_offset = int(value)
            self._apply_exploded()

    @property
    def unit_direction(self):
        return exploded_direction(self._exploded_axis, self._exploded_direction)

    @property
    def exploded_offset_limit(self) -> int:
        image = self.image
        if image is None:
            return 0
        direction = self.unit_direction
        _lo, length = exploded_extent(image.GetBounds(), direction)
        return exploded_offset_limit(
            length,
            self._exploded_chunks,
            exploded_voxel_step(direction, image.GetSpacing()),
        )

    def _apply_exploded(self):
        image = self.image
        if image is None or not self._exploded_enabled or self.bricked:
            if self._exploded_enabled and self.bricked:
                logger.warning(
                    "'{}' is now rendered in bricks: exploded view turned off",
                    self.label,
                )
                self._exploded_enabled = False
                self._apply_scattering()
            if self.slabs or self.mapper.GetCropping():
                self._teardown_slabs()
                self.mapper.CroppingOff()
                self._apply_cut_out()
            self._update_widget()
            return

        chunks = self._exploded_chunks
        while len(self.slabs) < chunks - 1:
            self._add_slab()
        while len(self.slabs) > chunks - 1:
            self._remove_slab()

        bounds = image.GetBounds()
        custom = self._exploded_axis == CUSTOM_AXIS
        axis = 0 if custom else self._exploded_axis
        lo = bounds[2 * axis]
        length = bounds[2 * axis + 1] - lo
        shift = (
            0.0
            if custom
            else exploded_shift(
                self._exploded_offset, length, chunks, image.GetSpacing()[axis]
            )
        )
        for k, mapper in enumerate(self.mappers):
            if custom:
                mapper.CroppingOff()  # clipped by its pair of planes instead
                continue
            planes = list(bounds)
            planes[2 * axis] = lo if k == 0 else lo + shift + length * k / chunks
            planes[2 * axis + 1] = (
                lo + length
                if k == chunks - 1
                else lo + shift + length * (k + 1) / chunks
            )
            mapper.SetCroppingRegionPlanes(*planes)
            mapper.SetCroppingRegionFlagsToSubVolume()
            mapper.CroppingOn()
        self._sync_slab_planes(custom)
        self._place_slabs()
        self._update_widget()

    def _add_slab(self):
        mapper = self._make_mapper()
        mapper.SetVolumetricScatteringBlending(0.0)
        self.producer >> mapper
        volume = vtkVolume(mapper=mapper, property=self.property)
        volume.SetVisibility(self._visible)
        if not self.composited:
            self.vtk_view.renderer.AddViewProp(volume)
        self.slabs.append((volume, mapper))
        self._order_dirty = True

    def _remove_slab(self):
        volume, _mapper = self.slabs.pop()
        self.vtk_view.renderer.RemoveViewProp(volume)
        self._order_dirty = True

    def _teardown_slabs(self):
        self._sync_slab_planes(custom=False)
        while self.slabs:
            self._remove_slab()
        self.slab_planes = []
        self.actor.SetPosition(0.0, 0.0, 0.0)

    def _sync_slab_planes(self, custom: bool):
        """A custom direction cuts each slab with a pair of clipping planes;
        an axis leaves it to the mappers' cropping."""
        mappers = self.mappers
        del self.slab_planes[len(mappers) :]
        while len(self.slab_planes) < len(mappers):
            self.slab_planes.append((vtkPlane(), vtkPlane()))
        self._slab_clipping = custom
        self._apply_clipping()

    # ---- clips ---------------------------------------------------------------

    @property
    def clip_planes(self) -> list:
        return self._clip_planes

    def set_clipping_planes(self, planes) -> bool:
        """Be cut by ``planes`` (the clips of its group). True if changed.
        The bricked mapper is handed them too, though the desktop found
        they have no effect there."""
        planes = list(planes)
        if planes == self._clip_planes:
            return False
        self._clip_planes = planes
        self._apply_clipping()
        coordinator = MultiVolumeCoordinator.find(self.vtk_view)
        if coordinator is not None:
            coordinator.refresh_settings()
        return True

    def _apply_clipping(self):
        """Each mapper: the clips' planes, then its slab's pair for a custom
        exploded direction; the GPU mapper takes at most six."""
        for k, mapper in enumerate(self.mappers):
            planes = list(self._clip_planes)
            if self._slab_clipping and k < len(self.slab_planes):
                planes += self.slab_planes[k]
            set_mapper_clipping_planes(mapper, planes[:MAX_CLIPPING_PLANES])
        set_mapper_clipping_planes(
            self.brick_mapper, self._clip_planes[:MAX_CLIPPING_PLANES]
        )

    def _place_slabs(self):
        """Slab k sits ``k * gap * length`` along the direction; a custom
        direction's planes are written where their slab sits, since the
        mappers read clipping planes in world coordinates."""
        image = self.image
        if image is None or not self.slabs:
            return
        bounds = image.GetBounds()
        direction = self.unit_direction
        lo, length = exploded_extent(bounds, direction)
        chunks = len(self.slabs) + 1
        shift = exploded_shift(
            self._exploded_offset,
            length,
            chunks,
            exploded_voxel_step(direction, image.GetSpacing()),
        )
        center = [(bounds[2 * a] + bounds[2 * a + 1]) / 2 for a in range(3)]
        custom = self._exploded_axis == CUSTOM_AXIS
        for k, volume in enumerate(self.volumes):
            offset = [d * k * self._exploded_gap * length for d in direction]
            volume.SetPosition(*offset)
            if not custom:
                continue
            for side, plane in enumerate(self.slab_planes[k]):
                # The cuts move by the offset; the volume's own faces do not
                face = (k == 0 and side == 0) or (k == chunks - 1 and side == 1)
                d = lo + length * (k + side) / chunks + (0.0 if face else shift)
                plane.SetOrigin(
                    *(center[a] + direction[a] * d + offset[a] for a in range(3))
                )
                # The lower plane keeps what is beyond it, the upper what is
                # before it.
                sign = 1.0 if side == 0 else -1.0
                plane.SetNormal(*(sign * c for c in direction))

    def _sort_slabs(self, renderer, _event):
        """Draw the slabs back to front along the view direction."""
        if not self.slabs or self.composited:
            return
        direction = self.unit_direction
        view = renderer.GetActiveCamera().GetDirectionOfProjection()
        reversed_order = sum(v * d for v, d in zip(view, direction, strict=True)) > 0
        if not self._order_dirty and reversed_order == self._order_reversed:
            return
        self._order_reversed = reversed_order
        self._order_dirty = False
        volumes = self.volumes
        if reversed_order:
            volumes.reverse()
        # Reorder in place: removing a prop from the renderer would release
        # its GPU texture.
        props = renderer.GetViewProps()
        for volume in volumes:
            props.RemoveItem(volume)
            props.AddItem(volume)

    def _update_widget(self):
        image = self.image
        show = (
            image is not None
            and self._visible
            and self._exploded_enabled
            and self._exploded_axis == CUSTOM_AXIS
            and self._exploded_show_arrow
            and not self.bricked
            and not self.composited
        )
        if show:
            bounds = image.GetBounds()
            center = [(bounds[2 * a] + bounds[2 * a + 1]) / 2 for a in range(3)]
            half_diagonal = 0.5 * math.sqrt(
                sum((bounds[2 * a + 1] - bounds[2 * a]) ** 2 for a in range(3))
            )
            self.widget.place(center, self.unit_direction, half_diagonal)
        self.widget.set_visible(show)

    def _on_direction_drag(self, normal):
        self._exploded_direction = tuple(normal)
        self._apply_exploded()
        self._notify_model("ExplodedDirection")

    # ---- multi-volume --------------------------------------------------------------------

    def _eligible(self) -> bool:
        return self._visible and self.image is not None and not self.bricked

    def _sync_membership(self):
        if self._eligible():
            MultiVolumeCoordinator.for_view(self.vtk_view).add_member(self)
        else:
            coordinator = MultiVolumeCoordinator.find(self.vtk_view)
            if coordinator is not None:
                coordinator.remove_member(self)

    def _refresh_membership_input(self):
        coordinator = MultiVolumeCoordinator.find(self.vtk_view)
        if coordinator is not None:
            coordinator.refresh_input(self)

    def apply_multi_volume_state(self):
        """The coordinator changed this volume's place: swap its own props
        for the shared multi-volume or back."""
        coordinator = MultiVolumeCoordinator.find(self.vtk_view)
        composited = coordinator is not None and coordinator.is_composited(self)
        lead = composited and coordinator.lead is self
        if composited != self.composited:
            self.composited = composited
            renderer = self.vtk_view.renderer
            for volume in self.volumes:
                if composited:
                    renderer.RemoveViewProp(volume)
                else:
                    renderer.AddViewProp(volume)
            self._order_dirty = True
        self.multi_volume_lead = lead
        self.multi_volume_lead_label = (
            coordinator.lead.label if composited and not lead else ""
        )
        self._update_widget()
        self._notify_model()

    def _notify_model(self, *fields):
        """Tell the model what changed here on its own: where the volume is
        rendered, and ``fields`` the handles edited. A full pull could undo
        panel edits the model has yet to push."""
        if self.model is None:
            return
        for field in fields:
            setattr(self.model, field, getattr(self, field))
        self.model.pull_status()


RepresentationType.VOLUME.register_class(VolumeRepresentation)
