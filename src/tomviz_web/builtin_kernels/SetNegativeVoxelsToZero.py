JSON = {
    "name": "SetNegativeVoxelsToZero",
    "label": "Set Negative Voxels To Zero",
    "description": "Set all negative voxel values to zero.",
    "tags": ["negative", "zero", "clamp", "threshold", "voxel", "math"],
    "path": ["Data Transforms", "Math Operations"],
    "parameters": [],
}


def transform(dataset):
    """Set negative voxels to zero"""

    data = dataset.active_scalars

    data[data < 0] = 0  # Set negative voxels to zero

    # Set the result as the new scalars.
    dataset.active_scalars = data
