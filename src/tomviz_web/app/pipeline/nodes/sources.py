"""Build source nodes from catalog entries.

A catalog source is a schema-v2 kernel whose description declares no
``inputs``: the script defines a ``SourceNode`` (``SourceKernel``) subclass,
and the library's ``ScriptableNode`` hosts it as a ``ScriptableSourceNode``.
Like a file reader, it starts a pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tomviz_pipeline import ScriptableNode, SourceNode


def build_source_node(
    description: dict[str, Any],
    script_path: str | Path,
    parameters: dict[str, Any] | None = None,
) -> SourceNode:
    """Create the source node for a catalog entry. ``parameters`` override
    the description's defaults."""
    return ScriptableNode(description, kernel=Path(script_path), parameters=parameters)
