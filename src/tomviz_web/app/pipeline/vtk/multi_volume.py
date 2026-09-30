"""Render the volumes of one view together, after the desktop's
``MultiVolumeCoordinator``.

A ``vtkVolume`` composites into the frame on its own, so where two overlap
the second is drawn over a finished picture of the first and the overlap
comes out wrong. VTK's answer is ``vtkMultiVolume``: one GPU ray cast
mapper with an input port per volume, marching all of them along the same
ray. Each view has one coordinator; volume representations join it while
they have a volume on screen, and from the second member on it takes their
props out of the renderer and draws them through the multi-volume. With
one member left it hands the props back.

What VTK's multi-volume path supports decides what a member keeps. Color,
opacity, interpolation and solidity stay per volume. Blending (composite),
jittering (on), sampling and smooth normals are shared, the last taken from
the lead, the member on port 0, whose property also decides shading for the
whole set. Cropping (cut-out, exploded view) and volumetric shadows are not
available on this path; the members' panels say so.

The path shades under a single headlight only, which is what a view's
renderer creates when it has no lights of its own (the web views add
none), so unlike the desktop no light kit needs swapping. The mapper is
replaced at each activation: deactivating removes the prop from the
renderer, which releases the mapper's resources, and a released multi-input
mapper would otherwise re-upload every volume on every frame.

Each member's input reaches the mapper as a shallow copy whose active
scalars are the array the member displays: the mapper has one array
selection for all its ports.

Fine sampling (a label map's half-voxel step) is a property of the march:
one member asking for it sets it for the set.
"""

from __future__ import annotations

import vtkmodules.vtkRenderingVolumeOpenGL2  # noqa: F401 (the GPU mapper's backend)
from loguru import logger
from vtkmodules.vtkCommonDataModel import vtkImageData
from vtkmodules.vtkRenderingVolume import vtkGPUVolumeRayCastMapper, vtkMultiVolume

MINIMUM_MEMBERS = 2  # from this many on, the view renders through the set
MAXIMUM_MEMBERS = 10  # vtkGPUVolumeRayCastMapper's input ports
MAXIMUM_CLIPPING_PLANES = 6  # what its shader takes


class MultiVolumeCoordinator:
    """The volumes rendered together in one ``vtk.view.View``.

    Members are volume representations exposing ``actor`` (their
    ``vtkVolume``), ``rendered_image`` and ``rendered_array`` (what their
    own mapper draws), ``smooth_normals``, ``clip_planes``, ``fine_step``
    (None, or the ray step they need), ``label`` and
    ``apply_multi_volume_state()``, called whenever their place changes."""

    @classmethod
    def for_view(cls, view) -> MultiVolumeCoordinator:
        coordinator = getattr(view, "multi_volume", None)
        if coordinator is None:
            coordinator = cls(view)
            view.multi_volume = coordinator
        return coordinator

    @classmethod
    def find(cls, view) -> MultiVolumeCoordinator | None:
        return getattr(view, "multi_volume", None)

    def __init__(self, view):
        self.view = view
        self.multi_volume = vtkMultiVolume()
        self.mapper = self._make_mapper()
        self.members: list = []  # earliest first
        self._ports: dict = {}
        self._inputs: dict = {}  # member -> (source, array, geometry, copy)
        self.active = False

    @staticmethod
    def _make_mapper():
        mapper = vtkGPUVolumeRayCastMapper()
        mapper.SetBlendModeToComposite()
        mapper.UseJitteringOn()
        # Each port's input carries its own active scalars (see _attach).
        mapper.SetScalarModeToUsePointData()
        mapper.AutoAdjustSampleDistancesOn()
        return mapper

    # ---- membership --------------------------------------------------------

    def is_member(self, representation) -> bool:
        return representation in self._ports

    @property
    def lead(self):
        for member, port in self._ports.items():
            if port == 0:
                return member
        return None

    def is_composited(self, representation) -> bool:
        return self.active and self.is_member(representation)

    def add_member(self, representation) -> bool:
        """Bring ``representation`` into the set (a member has its input
        refreshed). False when the set is full: it renders on its own."""
        if self.is_member(representation):
            self.refresh_input(representation)
            return True
        port = self._lowest_free_port()
        if port is None:
            logger.warning(
                "A view renders at most {} volumes together; '{}' is drawn on "
                "its own and may not composite correctly where it overlaps",
                MAXIMUM_MEMBERS,
                representation.label,
            )
            return False

        self.members.append(representation)
        self._ports[representation] = port
        self._attach(representation)
        self.refresh_settings()
        if not self.active and len(self.members) >= MINIMUM_MEMBERS:
            self._activate()
        self._notify()
        return True

    def remove_member(self, representation):
        if not self.is_member(representation):
            return
        port = self._ports.pop(representation)
        self.members.remove(representation)
        self._inputs.pop(representation, None)
        self._detach(port)

        # Port 0 must stay occupied: its property shades the set and its
        # input decides whether there is anything to draw.
        if port == 0 and self.members:
            successor = self.members[0]
            self._detach(self._ports[successor])
            self._ports[successor] = 0
            self._inputs.pop(successor, None)
            self._attach(successor)

        if self.active and len(self.members) < MINIMUM_MEMBERS:
            self._deactivate()
        self.refresh_settings()
        self._notify(also=representation)
        if not self.members and getattr(self.view, "multi_volume", None) is self:
            self.view.multi_volume = None

    def _lowest_free_port(self):
        taken = set(self._ports.values())
        return next((p for p in range(MAXIMUM_MEMBERS) if p not in taken), None)

    # ---- inputs and settings -----------------------------------------------

    def refresh_input(self, representation):
        """The member's data or displayed array may have changed."""
        if self.is_member(representation):
            self._attach(representation)

    def _attach(self, representation):
        source: vtkImageData | None = representation.rendered_image
        if source is None:
            return
        port = self._ports[representation]
        array = representation.rendered_array
        geometry = (source.GetOrigin(), source.GetSpacing(), source.GetExtent())
        cached = self._inputs.get(representation)
        # A shallow copy shares the arrays but not the geometry, so a new
        # copy is due whenever the source, the array or the geometry moved.
        if cached is None or cached[:3] != (source, array, geometry):
            copy = vtkImageData()
            copy.ShallowCopy(source)
            if array:
                copy.GetPointData().SetActiveScalars(array)
            self._inputs[representation] = (source, array, geometry, copy)
            self.mapper.SetInputDataObject(port, copy)
        self.multi_volume.SetVolume(representation.actor, port)

    def _detach(self, port):
        self.multi_volume.RemoveVolume(port)
        if self.mapper.GetNumberOfInputConnections(port) > 0:
            self.mapper.RemoveInputConnection(port, 0)

    def refresh_settings(self):
        """Something mapper-level changed on a member: the lead's normals,
        the clips. One mapper has one set of planes, so a plane clipping
        any member clips them all (the desktop's rule); the shader takes at
        most six, and a plane two members share goes in once."""
        lead = self.lead
        self.mapper.SetComputeNormalFromOpacity(
            bool(lead is not None and lead.smooth_normals)
        )
        planes = []
        for member in self.members:
            planes += [p for p in member.clip_planes if p not in planes]
        self.mapper.RemoveAllClippingPlanes()
        for plane in planes[:MAXIMUM_CLIPPING_PLANES]:
            self.mapper.AddClippingPlane(plane)
        steps = [m.fine_step for m in self.members if m.fine_step is not None]
        if steps:
            self.mapper.AutoAdjustSampleDistancesOff()
            self.mapper.SetSampleDistance(min(steps))
            self.mapper.SetImageSampleDistance(1.0)
        else:
            self.mapper.AutoAdjustSampleDistancesOn()

    # ---- activation --------------------------------------------------------

    def _activate(self):
        self.active = True
        # A fresh mapper: the previous one's resources were released.
        self.mapper = self._make_mapper()
        self.multi_volume.SetMapper(self.mapper)
        self._inputs.clear()
        for member in self.members:
            self._attach(member)
        self.refresh_settings()
        self.view.renderer.AddViewProp(self.multi_volume)

    def _deactivate(self):
        self.active = False
        self.view.renderer.RemoveViewProp(self.multi_volume)

    def _notify(self, also=None):
        for member in list(self.members):
            member.apply_multi_volume_state()
        if also is not None and also not in self.members:
            also.apply_multi_volume_state()
