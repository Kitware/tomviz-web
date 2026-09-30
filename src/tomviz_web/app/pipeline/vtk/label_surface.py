"""Surfaces of the regions of a label map, after the desktop's
``LabelMapSurface``.

``extract_label_mesh`` runs Surface Nets over every region at once (worker
thread: it is a pass over the volume), optionally relaxed by a shrink-free
smoothing. Each face carries the two labels on its sides
(``BoundaryLabels``), so showing or hiding a label only re-selects faces
(``select_label_faces``) and a color edit only rewrites the face colors
(``color_label_surface``); neither touches the volume again.
"""

from __future__ import annotations

import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkIdTypeArray
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkImageData, vtkPolyData
from vtkmodules.vtkFiltersCore import (
    vtkPolyDataNormals,
    vtkSurfaceNets3D,
    vtkWindowedSincPolyDataFilter,
)

from tomviz_web.app.utils.colors import hex_to_rgb
from tomviz_web.app.utils.labels import BACKGROUND

BOUNDARY_LABELS = "BoundaryLabels"  # what Surface Nets tags faces with
LABEL_COLORS = "LabelColors"
MAX_SMOOTHING = 32
# The windowed sinc pass band: lower is smoother. At this value the
# staircase is gone by 16 iterations and a sphere a few voxels across keeps
# its volume to within a percent or two (the desktop's).
PASS_BAND = 0.05
# The color of a face whose sides are both hidden (seen only when a caller
# skipped the selection).
UNLABELED = (128, 128, 128)


def extract_label_mesh(
    image: vtkImageData,
    array: str,
    regions,
    smoothing: int = 0,
) -> vtkPolyData:
    """Every face bounding one of ``regions`` (label values) in ``array``
    of ``image``, background excluded. ``smoothing`` iterations of a
    windowed sinc relaxation held within half a voxel diagonal of the voxel
    faces, so regions keep their size; 0 keeps the voxel faces."""
    surface = vtkPolyData()
    if image is None or not len(regions):
        return surface
    if min(image.GetDimensions()) < 2:
        return surface  # a single slice has no closed surface
    scalars = image.GetPointData().GetArray(array)
    if scalars is None or scalars.GetNumberOfComponents() != 1:
        return surface

    # A shallow copy owns its attribute bookkeeping, so the active array
    # cannot change under the filter while another sink reads the image.
    source = vtkImageData()
    source.ShallowCopy(image)
    source.GetPointData().SetActiveScalars(array)

    nets = vtkSurfaceNets3D()
    nets.SetInputData(source)
    nets.SetBackgroundLabel(BACKGROUND)
    nets.SetNumberOfLabels(len(regions))
    for index, value in enumerate(regions):
        nets.SetLabel(index, value)
    # Surface Nets' own smoother may move a point a whole voxel diagonal and
    # shrinks convex regions; the relaxation below does not.
    nets.SetSmoothing(False)
    smoothing = min(max(int(smoothing), 0), MAX_SMOOTHING)
    if smoothing:
        nets.SetOutputMeshTypeToTriangles()  # relaxed quads are not planar
    nets.Update()
    if not smoothing:
        surface.ShallowCopy(nets.GetOutput())
        return surface

    smoother = vtkWindowedSincPolyDataFilter()
    smoother.SetInputConnection(nets.GetOutputPort())
    smoother.SetNumberOfIterations(smoothing)
    smoother.SetPassBand(PASS_BAND)
    # Where three labels meet the edge is non-manifold; pinned, every
    # contact between regions would keep its staircase.
    smoother.NonManifoldSmoothingOn()
    smoother.FeatureEdgeSmoothingOff()
    smoother.NormalizeCoordinatesOn()
    smoother.Update()
    relaxed = smoother.GetOutput()
    hold_near(nets.GetOutput().GetPoints(), relaxed.GetPoints(), image.GetSpacing())

    # Smooth point normals; the mesh is non-manifold wherever three labels
    # meet, so consistency is enforced without traversing those edges.
    normals = vtkPolyDataNormals()
    normals.SetInputData(relaxed)
    normals.SplittingOff()
    normals.ConsistencyOn()
    normals.NonManifoldTraversalOff()
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOff()
    normals.Update()
    surface.ShallowCopy(normals.GetOutput())
    return surface


def hold_near(original, relaxed, spacing):
    """Pull every relaxed point back within half a voxel diagonal of where
    the voxel faces put it: the constraint the smoother lacks."""
    if original is None or relaxed is None:
        return
    if original.GetNumberOfPoints() != relaxed.GetNumberOfPoints():
        return
    before = vtk_to_numpy(original.GetData()).astype(np.float64)
    after = vtk_to_numpy(relaxed.GetData())
    limit = 0.5 * float(np.linalg.norm(spacing))
    moved = after - before
    length = np.linalg.norm(moved, axis=1)
    far = length > limit
    if not far.any():
        return
    scale = (limit / length[far])[:, None]
    after[far] = before[far] + moved[far] * scale
    relaxed.Modified()


def boundary_labels(mesh: vtkPolyData) -> np.ndarray | None:
    """The ``(faces, 2)`` labels on either side of each face, or None for
    a mesh Surface Nets did not make."""
    array = mesh.GetCellData().GetArray(BOUNDARY_LABELS)
    if array is None or array.GetNumberOfComponents() != 2:
        return None
    if array.GetNumberOfTuples() != mesh.GetNumberOfCells():
        return None
    return vtk_to_numpy(array)


def select_label_faces(mesh: vtkPolyData, visible) -> vtkPolyData:
    """The faces of ``mesh`` bounding a ``visible`` label, sharing its
    points (and normals)."""
    surface = vtkPolyData()
    count = mesh.GetNumberOfCells() if mesh is not None else 0
    if not count or not len(visible):
        return surface
    sides = boundary_labels(mesh)
    if sides is None:
        surface.ShallowCopy(mesh)
        return surface

    shown = np.asarray(sorted(visible), dtype=np.float64)
    kept = np.isin(sides[:, 0], shown) | np.isin(sides[:, 1], shown)
    if kept.all():
        surface.ShallowCopy(mesh)
        return surface
    if not kept.any():
        return surface

    # Surface Nets writes polygons of one size only, so the legacy layout
    # (n, p0, .., pn-1 per cell) is a table to take rows from, whatever
    # the cell array's storage.
    legacy = vtkIdTypeArray()
    mesh.GetPolys().ExportLegacyFormat(legacy)
    rows = vtk_to_numpy(legacy)
    width = rows.size // count
    if width * count != rows.size or width < 2:
        surface.ShallowCopy(mesh)
        return surface
    selected = np.ascontiguousarray(rows.reshape(count, width)[kept]).ravel()
    polys = vtkCellArray()
    polys.ImportLegacyFormat(
        numpy_to_vtk(selected, deep=True, array_type=legacy.GetDataType())
    )

    surface.SetPoints(mesh.GetPoints())
    surface.GetPointData().PassData(mesh.GetPointData())
    surface.SetPolys(polys)
    cell_data = mesh.GetCellData()
    for index in range(cell_data.GetNumberOfArrays()):
        source = cell_data.GetArray(index)
        if source is None:
            continue
        values = vtk_to_numpy(source)[kept]
        array = numpy_to_vtk(np.ascontiguousarray(values), deep=True)
        array.SetName(source.GetName())
        surface.GetCellData().AddArray(array)
    return surface


def color_label_surface(surface: vtkPolyData, entries):
    """Write each face's color as a ``LabelColors`` cell array: the color of
    the visible label it bounds, the first side's when both are (a face
    between two visible regions only shows through a translucent
    surface)."""
    count = surface.GetNumberOfCells()
    colors = np.empty((count, 3), dtype=np.uint8)
    colors[:] = UNLABELED
    sides = boundary_labels(surface) if count else None
    if sides is not None:
        shown = [e for e in entries if e["visible"] and e["value"] != BACKGROUND]
        values = np.asarray([e["value"] for e in shown], dtype=np.float64)
        palette = np.asarray(
            [[round(255 * c) for c in hex_to_rgb(e["color"])] for e in shown],
            dtype=np.uint8,
        ).reshape(-1, 3)
        assigned = np.zeros(count, dtype=bool)
        for side in range(2):
            index, found = _lookup(values, sides[:, side])
            take = found & ~assigned
            colors[take] = palette[index[take]]
            assigned |= take
    array = numpy_to_vtk(colors, deep=True)
    array.SetName(LABEL_COLORS)
    surface.GetCellData().AddArray(array)
    surface.GetCellData().SetActiveScalars(LABEL_COLORS)


def _lookup(values: np.ndarray, keys: np.ndarray):
    """Where each of ``keys`` sits in the sorted ``values``, and whether it
    is there at all."""
    if not values.size:
        return np.zeros(keys.shape, dtype=np.intp), np.zeros(keys.shape, dtype=bool)
    keys = keys.astype(np.float64)
    index = np.clip(np.searchsorted(values, keys), 0, values.size - 1)
    return index, values[index] == keys
