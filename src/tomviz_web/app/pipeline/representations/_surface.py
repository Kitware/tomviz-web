"""What the surface visualizations (contour, threshold) share: an actor
drawn as a surface, wireframe or points, with Phong lighting and opacity,
colored by the array of the sink's color map through its lookup table, by
the raw values ("Color Map Data" off), or in one solid color."""

from __future__ import annotations

from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkProperty

from tomviz_web.app.pipeline.representations.core import Representation
from tomviz_web.app.utils.colors import hex_to_rgb, rgb_to_hex

SURFACE_MODES = ("Points", "Wireframe", "Surface")  # vtkProperty's order


class SurfaceRepresentation(Representation):
    """Subclasses feed ``self.mapper`` and say where the colored array
    lives (``ASSOCIATION``) and whether the surface carries it
    (``_carry_color_array``)."""

    ASSOCIATION = "POINTS"

    def __init__(self, server):
        super().__init__(server)
        self._use_solid_color = False
        self._map_scalars = True
        self.property = vtkProperty()
        self.mapper = vtkPolyDataMapper()
        self.mapper.SetColorModeToMapScalars()
        self.actor = vtkActor(mapper=self.mapper, property=self.property)

    # ---- appearance --------------------------------------------------------

    @property
    def Mode(self):
        return SURFACE_MODES[self.property.GetRepresentation()]

    @Mode.setter
    def Mode(self, value):
        if value in SURFACE_MODES:
            self.property.SetRepresentation(SURFACE_MODES.index(value))

    @property
    def Opacity(self):
        return self.property.GetOpacity()

    @Opacity.setter
    def Opacity(self, value):
        self.property.SetOpacity(float(value))

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

    # ---- color -------------------------------------------------------------

    @property
    def Color(self):
        """The solid color, as ``#rrggbb``."""
        return rgb_to_hex(self.property.GetDiffuseColor())

    @Color.setter
    def Color(self, value):
        self.property.SetDiffuseColor(*hex_to_rgb(value))

    @property
    def UseSolidColor(self):
        return self._use_solid_color

    @UseSolidColor.setter
    def UseSolidColor(self, value):
        self._use_solid_color = bool(value)
        self._update_coloring()

    @property
    def MapScalars(self):
        return self._map_scalars

    @MapScalars.setter
    def MapScalars(self, value):
        """Off: the values as colors (gray for one component), as VTK's
        direct scalars."""
        self._map_scalars = bool(value)
        self._update_coloring()

    @property
    def ColorArrayName(self):
        return getattr(self, "_color_array_name", (None, None))

    @ColorArrayName.setter
    def ColorArrayName(self, value):
        self._color_array_name = value
        self._update_coloring()

    @property
    def color_array(self) -> str:
        return self.ColorArrayName[1] or ""

    def _carry_color_array(self, name: str):
        """Make sure the surface carries array ``name`` (subclasses)."""

    def _update_coloring(self):
        name = self.color_array
        if self._use_solid_color or not name:
            self.mapper.ScalarVisibilityOff()
            return
        self._carry_color_array(name)
        if self.ASSOCIATION == "CELLS":
            self.mapper.SetScalarModeToUseCellFieldData()
        else:
            self.mapper.SetScalarModeToUsePointFieldData()
        self.mapper.SelectColorArray(name)
        if self._map_scalars:
            self.mapper.SetColorModeToMapScalars()
        else:
            self.mapper.SetColorModeToDirectScalars()
        self.mapper.ScalarVisibilityOn()

    # ---- arrays ------------------------------------------------------------

    def array_names(self) -> list[str]:
        image = self.image
        if image is None:
            return []
        point_data = image.GetPointData()
        return [
            point_data.GetArrayName(i) for i in range(point_data.GetNumberOfArrays())
        ]

    def resolve_array(self, name) -> str:
        """``name`` when the image has it (an index from an old state file
        is looked up), else the image's active scalars."""
        names = self.array_names()
        if isinstance(name, int) and 0 <= name < len(names):
            return names[name]
        if isinstance(name, str) and name in names:
            return name
        image = self.image
        scalars = image.GetPointData().GetScalars() if image is not None else None
        return scalars.GetName() if scalars is not None else ""

    def array_range(self, name: str) -> tuple[float, float]:
        image = self.image
        array = image.GetPointData().GetArray(name) if image is not None else None
        if array is None:
            return (0.0, 1.0)
        return tuple(float(v) for v in array.GetRange())
