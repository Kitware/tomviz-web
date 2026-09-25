from __future__ import annotations

import vtkmodules.vtkRenderingVolumeOpenGL2  # noqa: F401 (register GPU volume mapper)
from trame_client.widgets.core import TrameComponent
from vtkmodules.vtkRenderingCore import vtkVolume, vtkVolumeProperty
from vtkmodules.vtkRenderingVolume import vtkGPUVolumeRayCastMapper

from tomviz_web.app import data_model
from tomviz_web.app.pipelines.core import RepresentationType
from tomviz_web.app.pipelines.representations.core import RepresentationBase

# VTK only has Nearest(0)/Linear(1) volume interpolation, "Cubic" from the UI
# falls back to Linear.
_INTERPOLATION_FROM_VTK = {0: "Nearest", 1: "Linear"}


class VolumeRepresentation(TrameComponent, RepresentationBase):
    def __init__(
        self,
        pipeline_manager,
        source_proxy: data_model.SourceProxy,
        view: data_model.WindowInternalState,
    ):
        view_proxy = view.vtk_view
        super().__init__(server=pipeline_manager.server)

        self.property = vtkVolumeProperty()
        self.property.SetInterpolationTypeToLinear()
        self.property.ShadeOff()
        self.property.SetIndependentComponents(True)

        self.mapper = vtkGPUVolumeRayCastMapper()
        self.actor = vtkVolume(mapper=self.mapper, property=self.property)

        source_proxy.algo.algo >> self.mapper
        view_proxy.add_representation(self)

        self.props = data_model.VolumeProperties(
            self.server,
            input=source_proxy,
            view=view,
            representation=self,
            **RepresentationType.VOLUME.props,
        )

    @property
    def Visibility(self):
        return bool(self.actor.visibility)

    @Visibility.setter
    def Visibility(self, value):
        self.actor.visibility = bool(value)

    @property
    def InterpolationType(self):
        return _INTERPOLATION_FROM_VTK.get(
            self.property.GetInterpolationType(), "Nearest"
        )

    @InterpolationType.setter
    def InterpolationType(self, value):
        if value == "Nearest":
            self.property.SetInterpolationTypeToNearest()
        else:
            self.property.SetInterpolationTypeToLinear()

    @property
    def Shade(self):
        return bool(self.property.GetShade())

    @Shade.setter
    def Shade(self, value):
        self.property.SetShade(bool(value))

    @property
    def GlobalIlluminationReach(self):
        return self.mapper.GetGlobalIlluminationReach()

    @GlobalIlluminationReach.setter
    def GlobalIlluminationReach(self, value):
        self.mapper.SetGlobalIlluminationReach(value)

    @property
    def VolumetricScatteringBlending(self):
        return self.mapper.GetVolumetricScatteringBlending()

    @VolumetricScatteringBlending.setter
    def VolumetricScatteringBlending(self, value):
        self.mapper.SetVolumetricScatteringBlending(value)

    @property
    def VolumeAnisotropy(self):
        return self.property.GetScatteringAnisotropy()

    @VolumeAnisotropy.setter
    def VolumeAnisotropy(self, value):
        self.property.SetScatteringAnisotropy(value)

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
        association, name = value

        if not name:
            return

        if association == "CELLS":
            self.mapper.SetScalarModeToUseCellFieldData()
        else:
            self.mapper.SetScalarModeToUsePointFieldData()

        self.mapper.SelectScalarArray(name)


RepresentationType.VOLUME.register_class(VolumeRepresentation)
