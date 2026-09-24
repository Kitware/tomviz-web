JSON = {
    "name": "ConstantDataset",
    "label": "Constant Dataset",
    "description": "Fill array with a constant value.",
    "tags": ["constant", "fill", "generate", "dataset"],
    "path": ["Data Transforms", "Data Management"],
    "parameters": [
        {
            "name": "CONSTANT",
            "label": "Constant Value",
            "description": "The constant value to fill the array with.",
            "type": "double",
            "default": 0.0,
        },
    ],
}


def generate_dataset(array, CONSTANT=0.0):
    array.fill(CONSTANT)
