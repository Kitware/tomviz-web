JSON = {
    "name": "NormalizeTiltSeries",
    "label": "Normalize Average Image Intensity",
    "description": "Normalize tilt series so that each tilt image has the same total intensity.",
    "tags": ["normalize", "intensity", "tilt series", "average", "pre-processing"],
    "path": ["Tomography", "Pre-processing"],
    "parameters": [],
}


def transform(dataset):
    """
    Normalize tilt series so that each tilt image has the same total intensity.
    """

    import numpy as np

    data = dataset.active_scalars  # Get data as numpy array

    if data is None:  # Check if data exists
        raise RuntimeError("No data array found!")

    data = data.astype(np.float32)  # Change tilt series type to float.

    # Calculate average intensity of tilt series.
    intensity = np.sum(np.average(data, 2))

    for i in range(data.shape[2]):
        # Normalize each tilt image.
        data[:, :, i] = data[:, :, i] / np.sum(data[:, :, i]) * intensity

    dataset.active_scalars = data
