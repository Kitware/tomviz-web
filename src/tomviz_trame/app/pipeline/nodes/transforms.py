"""Build transform nodes from catalog entries.

An entry is a JSON description plus a Python script (the upstream tomviz
``Name.json`` / ``Name.py`` pair, or a single ``.py`` exposing ``JSON``).
Two flavours exist:

- schema-v2 kernels: the description declares ``inputs``/``outputs`` and
  the script defines a ``TransformKernel`` subclass; the library's
  ``PythonNode`` hosts them.
- v1 scripts (the desktop app's "operators"): no ``inputs`` in the
  description, a module-level ``transform(dataset, **params)`` function or
  an ``Operator`` subclass in the script; the library's
  ``LegacyPythonTransform`` hosts them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tomviz_pipeline import PythonNode, TransformNode
from tomviz_pipeline.nodes.transforms.legacy_python import LegacyPythonTransform

INPUT_PORT = "volume"


def build_transform_node(
    description: dict[str, Any],
    script_path: str | Path,
    parameters: dict[str, Any] | None = None,
) -> TransformNode:
    """Create the transform node for a catalog entry. ``parameters``
    override the description's defaults."""
    script_path = Path(script_path)

    if description.get("inputs"):
        node = PythonNode(description, kernel=script_path)
    else:
        node = LegacyPythonTransform()
        node.deserialize(
            {
                "description": json.dumps(description),
                "script": script_path.read_text(),
            }
        )

    if parameters:
        # Write into the store directly: the node is not in a graph yet, so
        # there is nothing to mark stale or re-execute.
        node._parameter_store().update(parameters)

    if not node.label:
        node.label = description.get("label") or description.get("name", "")
    return node
