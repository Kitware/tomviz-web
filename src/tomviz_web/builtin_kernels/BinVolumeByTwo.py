from tomviz.utils import apply_to_each_array

JSON = {
    "name": "BinVolumeByTwo",
    "label": "Bin Volume x2",
    "description": "Downsample volume by a factor of 2.",
    "tags": ["bin", "downsample", "volume", "2x", "resize"],
    "path": ["Data Transforms", "Volume Manipulation"],
    "parameters": [],
}


@apply_to_each_array
def transform(dataset):
    """Downsample volume by a factor of 2"""

    import numpy as np
    import scipy.ndimage

    from tomviz import utils

    array = dataset.active_scalars

    # Downsample the dataset x2 using order 1 spline (linear)
    # Calculate out array shape
    zoom = (0.5, 0.5, 0.5)
    result_shape = utils.zoom_shape(array, zoom)
    result = np.empty(result_shape, array.dtype, order="F")
    scipy.ndimage.interpolation.zoom(
        array, zoom, output=result, order=1, mode="constant", cval=0.0, prefilter=False
    )

    # Set the result as the new scalars.
    dataset.active_scalars = result

    # Update tilt angles if dataset is a tilt series.
    try:
        tilt_angles = dataset.tilt_angles
        result_shape = utils.zoom_shape(tilt_angles, 0.5)
        result = np.empty(result_shape, array.dtype, order="F")
        tilt_angles = scipy.ndimage.interpolation.zoom(tilt_angles, 0.5, output=result)
        dataset.tilt_angles = result
    except:  # noqa
        # TODO What exception are we ignoring?
        pass
