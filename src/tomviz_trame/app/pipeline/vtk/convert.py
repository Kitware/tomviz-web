"""Bridge between the numpy-backed ``tomviz_pipeline.dataset.Dataset`` that
flows through the pipeline graph and the ``vtkImageData`` the VTK rendering
pipelines consume.

Arrays are shared, not copied, whenever the memory layout allows it. A
Dataset holds Fortran-ordered ``(nx, ny, nz)`` arrays, where x varies fastest,
which is exactly VTK's point ordering, so a raveled view of the array can back
a VTK array directly. The VTK arrays keep a reference to their numpy buffer,
so a payload stays alive as long as an actor still displays it, and the numpy
arrays produced from a VTK reader keep the VTK buffer alive the same way.
"""

from __future__ import annotations

import numpy as np
from tomviz_pipeline.dataset import Dataset
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
from vtkmodules.vtkCommonCore import vtkDataArray
from vtkmodules.vtkCommonDataModel import vtkImageData

from tomviz_trame.app.utils.data import shape_3d, spacing_3d

# Rec. 601 luma weights, the same ones vtkImageLuminance applies.
LUMA_WEIGHTS = (0.299, 0.587, 0.114)


def to_vtk_image(dataset: Dataset) -> vtkImageData:
    """Wrap every scalar array of ``dataset`` in a ``vtkImageData``.

    The image shares memory with the dataset's arrays when they are
    Fortran-contiguous, and copies them once otherwise.
    """
    image = vtkImageData()
    names = list(dataset.scalars_names)
    if not names:
        return image

    shape = shape_3d(dataset.scalars(names[0]))
    image.SetDimensions(*shape)
    image.SetSpacing(*spacing_3d(dataset))
    image.SetOrigin(0.0, 0.0, 0.0)

    point_data = image.GetPointData()
    for name in names:
        array = dataset.scalars(name)
        if shape_3d(array) != shape:
            msg = f"Array '{name}' has shape {array.shape}, expected {shape}"
            raise ValueError(msg)
        # ravel(order="F") is a view when the array is Fortran-contiguous,
        # which is what every reader and transform in tomviz produces.
        flat = np.asfortranarray(array).ravel(order="F")
        vtk_array = numpy_to_vtk(flat, deep=False)
        vtk_array.SetName(name)
        point_data.AddArray(vtk_array)

    active = dataset.active_name if dataset.active_name in names else names[0]
    point_data.SetActiveScalars(active)
    return image


def from_vtk_image(image: vtkImageData) -> Dataset:
    """Build a Dataset from the point-data arrays of ``image``.

    Single-component arrays are shared with the image. Multi-component arrays
    (RGB or RGBA images from a TIFF, typically) are reduced to one luminance
    component of the same dtype, since tomviz operators expect scalar volumes.
    """
    dims = tuple(int(n) for n in image.GetDimensions())
    point_data = image.GetPointData()

    arrays: dict[str, np.ndarray] = {}
    for index in range(point_data.GetNumberOfArrays()):
        vtk_array = point_data.GetAbstractArray(index)
        if not isinstance(vtk_array, vtkDataArray):
            continue
        name = vtk_array.GetName() or f"Scalars{index}"
        values = vtk_to_numpy(vtk_array)
        if vtk_array.GetNumberOfComponents() > 1:
            values = to_luminance(values)
        arrays[name] = values.reshape(dims, order="F")

    dataset = Dataset(arrays)
    active = point_data.GetScalars()
    if active is not None and active.GetName() in arrays:
        dataset.active_name = active.GetName()
    dataset.spacing = [float(s) for s in image.GetSpacing()]
    return dataset


def to_luminance(values: np.ndarray) -> np.ndarray:
    """Reduce an ``(n, components)`` array to ``(n,)`` keeping its dtype.
    Three or more components are treated as RGB(A); two as value + alpha."""
    if values.ndim != 2:
        msg = f"Expected an (n, components) array, got shape {values.shape}"
        raise ValueError(msg)
    if values.shape[1] < 3:
        return np.ascontiguousarray(values[:, 0])

    luma = values[:, :3].astype(np.float64) @ np.asarray(LUMA_WEIGHTS)
    if np.issubdtype(values.dtype, np.integer):
        luma = np.rint(luma)
    return luma.astype(values.dtype, copy=False)
