"""VTK rendering pipelines, one module per visualization type.

Each module builds a ``Representation`` subclass and registers it with its
``RepresentationType`` entry; ``load_representations`` imports every module
in this package so the catalog is complete."""

import importlib
from pathlib import Path

from .core import Representation, RepresentationType

REPRESENTATIONS_PATH = Path(__file__).parent


def load_representations():
    """Import every representation module in this package. Importing is
    idempotent, so calling this more than once is harmless."""
    for module_path in sorted(REPRESENTATIONS_PATH.glob("*.py")):
        name = module_path.stem
        if name.startswith("_") or name == "core":
            continue
        importlib.import_module(f"{__name__}.{name}")


load_representations()

__all__ = [
    "Representation",
    "RepresentationType",
    "load_representations",
]
