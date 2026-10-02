"""Build transform nodes from catalog entries.

An entry is a JSON description plus a Python script (the upstream tomviz
``Name.json`` / ``Name.py`` pair, or a single ``.py`` exposing ``JSON``).
The library's ``ScriptableNode`` picks the node class from the
description's ``schemaVersion``:

- schema-v2 kernels: the description declares ``inputs``/``outputs`` and
  the script defines a ``TransformKernel`` subclass; a
  ``ScriptableTransformNode`` hosts them.
- v1 scripts: no ``schemaVersion``, a module-level
  ``transform(dataset, **params)`` function or an ``Operator`` subclass in
  the script; a ``LegacyScriptableTransformNode`` hosts them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tomviz_pipeline import ScriptableNode, TransformNode

INPUT_PORT = "volume"


def build_transform_node(
    description: dict[str, Any],
    script_path: str | Path,
    parameters: dict[str, Any] | None = None,
) -> TransformNode:
    """Create the transform node for a catalog entry. ``parameters``
    override the description's defaults."""
    return ScriptableNode(description, kernel=Path(script_path), parameters=parameters)
