from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkCommonDataModel import vtkPiecewiseFunction
from vtkmodules.vtkRenderingCore import vtkColorTransferFunction

COLOR_SPACES = {
    "RGB": vtkColorTransferFunction.SetColorSpaceToRGB,
    "HSV": vtkColorTransferFunction.SetColorSpaceToHSV,
    "Lab": vtkColorTransferFunction.SetColorSpaceToLab,
    "Diverging": vtkColorTransferFunction.SetColorSpaceToDiverging,
}


class PiecewiseFunction:
    def __init__(self):
        self.function = vtkPiecewiseFunction()
        self._points = []

    @property
    def Points(self):
        return self._points

    @Points.setter
    def Points(self, points):
        self._points = points

        self.function.RemoveAllPoints()
        for i in range(0, len(points), 4):
            self.function.AddPoint(*points[i : i + 4])


class LookupTable:
    """A ``vtkColorTransferFunction`` (volume rendering) and the
    ``vtkLookupTable`` sampled from it (surface mappers), both rebuilt from
    explicit control points."""

    def __init__(self, n_colors=255):
        self.n_colors = n_colors
        self.ctf = vtkColorTransferFunction()
        self.table = vtkLookupTable()

    def set_points(self, points, color_space="RGB"):
        """``points``: ``[x, r, g, b]`` rows in data units; ``color_space``
        picks the interpolation (RGB, HSV, Lab, Diverging)."""
        self.ctf.RemoveAllPoints()
        COLOR_SPACES.get(color_space, COLOR_SPACES["RGB"])(self.ctf)
        for x, r, g, b in points:
            self.ctf.AddRGBPoint(x, r, g, b)
        self._build_table()

    def _build_table(self):
        n = self.n_colors
        v_min, v_max = self.ctf.GetRange()

        self.table.SetNumberOfTableValues(n)
        self.table.SetRange(v_min, v_max)
        self.table.Build()

        rgb = [0.0, 0.0, 0.0]
        for i in range(n):
            t = v_min + (v_max - v_min) * i / (n - 1) if n > 1 else v_min
            self.ctf.GetColor(t, rgb)
            self.table.SetTableValue(i, rgb[0], rgb[1], rgb[2], 1.0)

        self.table.BuildSpecialColors()
