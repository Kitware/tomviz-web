import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk
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


# Entries at most in a table with one entry per integer value (a label
# map's): 4 MiB of colors.
MAX_INTEGER_ENTRIES = 1 << 20


class LookupTable:
    """A ``vtkColorTransferFunction`` (volume rendering) and the
    ``vtkLookupTable`` sampled from it (surface mappers), both rebuilt from
    explicit control points.

    The table samples ``n_colors`` values across the points' range, or,
    given an ``integer_range``, holds one entry per integer in it: a label
    map's bands are half a unit wide, and a few hundred labels would fall
    between the samples of a fixed-size table."""

    def __init__(self, n_colors=255):
        self.n_colors = n_colors
        self.ctf = vtkColorTransferFunction()
        self.table = vtkLookupTable()

    def set_points(self, points, color_space="RGB", integer_range=None):
        """``points``: ``[x, r, g, b]`` rows in data units; ``color_space``
        picks the interpolation (RGB, HSV, Lab, Diverging);
        ``integer_range``, ``(first, last)``, the integers to give one table
        entry each (ignored past ``MAX_INTEGER_ENTRIES`` of them)."""
        self.ctf.RemoveAllPoints()
        COLOR_SPACES.get(color_space, COLOR_SPACES["RGB"])(self.ctf)
        for x, r, g, b in points:
            self.ctf.AddRGBPoint(x, r, g, b)
        if integer_range is not None:
            first, last = (round(v) for v in integer_range)
            if 0 <= last - first < MAX_INTEGER_ENTRIES:
                self._build_integer_table(first, last)
                return
        self._build_table()

    def _build_integer_table(self, first: int, last: int):
        """Entry ``i`` is the color at ``first + i``; the range reaches half
        a unit past either end so every integer lands on its own entry."""
        n = last - first + 1
        rgb = np.empty(3 * n, dtype=np.float64)
        self.ctf.GetTable(first, last, n, rgb)
        rgba = np.empty((n, 4), dtype=np.uint8)
        rgba[:, :3] = np.clip(np.rint(rgb.reshape(n, 3) * 255), 0, 255)
        rgba[:, 3] = 255
        self.table.SetNumberOfTableValues(n)
        self.table.SetRange(first - 0.5, last + 0.5)
        self.table.SetTable(numpy_to_vtk(rgba, deep=True))
        self.table.BuildSpecialColors()

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
