def transform(dataset, sigma=2.0):
    """Apply a Gaussian filter to volume dataset."""
    """Gaussian Filter blurs the image and reduces the noise and details."""

    import numpy as np
    import scipy.ndimage

    array = dataset.active_scalars

    # Transform the dataset.
    result = np.empty_like(array)
    scipy.ndimage.filters.gaussian_filter(array, sigma, output=result)

    # Set the result as the new scalars.
    dataset.active_scalars = result
