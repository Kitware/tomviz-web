import numpy as np
from tomviz_pipeline.dataset import Dataset
from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkCommonDataModel import vtkImageData

from tomviz_trame.app.pipeline.vtk import convert


def make_dataset(shape=(4, 5, 6), dtype=np.uint16):
    values = np.arange(np.prod(shape), dtype=dtype).reshape(shape, order="F")
    dataset = Dataset({"a": values, "b": values * 2}, active="b")
    dataset.spacing = [1.0, 2.0, 3.0]
    return dataset


def test_to_vtk_image_shares_memory_and_keeps_metadata():
    dataset = make_dataset()
    image = convert.to_vtk_image(dataset)

    assert image.GetDimensions() == (4, 5, 6)
    assert image.GetSpacing() == (1.0, 2.0, 3.0)
    point_data = image.GetPointData()
    assert point_data.GetNumberOfArrays() == 2
    assert point_data.GetScalars().GetName() == "b"

    # x varies fastest in VTK: point 1 is (1, 0, 0)
    array = point_data.GetArray("a")
    assert array.GetValue(1) == dataset.scalars("a")[1, 0, 0]
    assert array.GetValue(4) == dataset.scalars("a")[0, 1, 0]

    back = convert.from_vtk_image(image)
    assert np.shares_memory(back.scalars("a"), dataset.scalars("a"))


def test_round_trip_preserves_values_and_layout():
    dataset = make_dataset(dtype=np.float32)
    back = convert.from_vtk_image(convert.to_vtk_image(dataset))

    assert back.scalars_names == ["a", "b"]
    assert back.active_name == "b"
    assert back.spacing == [1.0, 2.0, 3.0]
    for name in ("a", "b"):
        assert back.scalars(name).flags.f_contiguous
        np.testing.assert_array_equal(back.scalars(name), dataset.scalars(name))


def test_c_ordered_arrays_are_converted_once():
    values = np.arange(24, dtype=np.int32).reshape((2, 3, 4))  # C order
    dataset = Dataset({"c": values})
    back = convert.from_vtk_image(convert.to_vtk_image(dataset))
    np.testing.assert_array_equal(back.scalars("c"), values)


def test_two_dimensional_data_gets_a_unit_z_axis():
    values = np.zeros((3, 2), dtype=np.uint8, order="F")
    image = convert.to_vtk_image(Dataset({"img": values}))
    assert image.GetDimensions() == (3, 2, 1)


def test_multi_component_arrays_become_luminance():
    rgb = np.zeros((6, 3), dtype=np.uint8)
    rgb[:, 0] = 255  # pure red
    image = vtkImageData()
    image.SetDimensions(3, 2, 1)
    vtk_array = numpy_to_vtk(rgb, deep=True)
    vtk_array.SetName("rgb")
    image.GetPointData().SetScalars(vtk_array)

    dataset = convert.from_vtk_image(image)
    luma = dataset.scalars("rgb")
    assert luma.shape == (3, 2, 1)
    assert luma.dtype == np.uint8
    assert luma.flat[0] == round(0.299 * 255)
