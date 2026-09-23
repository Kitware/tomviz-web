JSON = {
    "name": "Subtract_TiltSer_Background_Auto",
    "label": "Background Subtraction (Auto)",
    "description": "Subtract background from tilt images by finding the histogram peak as background level.",
    "tags": [
        "background",
        "subtraction",
        "automatic",
        "histogram",
        "tilt series",
        "pre-processing",
    ],
    "path": ["Tomography", "Pre-processing"],
    "parameters": [],
}


def transform(dataset):
    """
    For each tilt image, the method calculates its histogram
    and then chooses the highest peak as the background level and subtracts it
    from the image.
    It does NOT set negative pixels to zero.
    """

    import numpy as np

    data = dataset.active_scalars  # Get data as numpy array.

    if data is None:  # Check if data exists
        raise RuntimeError("No data array found!")

    data_bs = data.astype(np.float32)  # Change tilt series type to float.

    for i in range(data.shape[2]):
        (hist, bins) = np.histogram(data[:, :, i].flatten(), 256)
        data_bs[:, :, i] = data_bs[:, :, i] - bins[np.argmax(hist)]

    dataset.active_scalars = data_bs
