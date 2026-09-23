from __future__ import annotations

import vtkmodules.vtkRenderingVolumeOpenGL2  # noqa: F401 (register GPU volume mapper)
from vtkmodules.vtkRenderingCore import vtkVolume, vtkVolumeProperty
from vtkmodules.vtkRenderingVolume import vtkGPUVolumeRayCastMapper

from tomviz_trame.app import data_model
from tomviz_trame.app.pipeline.representations.core import (
    Representation,
    RepresentationType,
)

# VTK only has Nearest(0)/Linear(1) volume interpolation, "Cubic" from the UI
# falls back to Linear.
_INTERPOLATION_FROM_VTK = {0: "Nearest", 1: "Linear"}


class VolumeRepresentation(Representation):
    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server)

        self.property = vtkVolumeProperty()
        self.property.SetInterpolationTypeToLinear()
        self.property.ShadeOff()
        self.property.SetIndependentComponents(True)

        self.mapper = vtkGPUVolumeRayCastMapper()
        self.actor = vtkVolume(mapper=self.mapper, property=self.property)

        self.producer >> self.mapper
        self.attach(view.vtk_view)

        self.model = data_model.VolumeSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.VOLUME.model_kwargs,
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
