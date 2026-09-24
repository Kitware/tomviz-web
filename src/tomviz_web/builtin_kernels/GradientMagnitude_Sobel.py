JSON = {
    "name": "GradientMagnitude_Sobel",
    "label": "Gradient Magnitude",
    "description": "Calculate 3D gradient magnitude using the Sobel operator.",
    "tags": ["gradient", "magnitude", "sobel", "3D", "edge detection", "filter"],
    "path": ["Data Transforms", "Filters & Smoothing"],
    "parameters": [],
}


def transform(dataset):
    """Calculate 3D gradient magnitude using Sobel operator"""

    import numpy as np
    import scipy.ndimage

    array = dataset.active_scalars.astype(np.float32)

    # Transform the dataset
    result = np.empty_like(array)
    scipy.ndimage.filters.generic_gradient_magnitude(
        array, scipy.ndimage.filters.sobel, output=result
    )

    # Set the result as the new scalars.
    dataset.active_scalars = result
