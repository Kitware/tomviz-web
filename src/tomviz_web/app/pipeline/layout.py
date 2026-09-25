"""The desktop's view layout as a dockview layout.

On the desktop, a state file's ``layouts`` entries serialize ParaView's
``vtkSMViewLayoutProxy``: a binary tree stored as a flat list where item
``i`` has its children at ``2i + 1`` (left or top) and ``2i + 2``. Each item
has a ``direction`` (0: a cell holding ``viewId``, or empty when 0; 1: split
top/bottom; 2: split left/right), and a split's ``fraction`` is the first
child's share.

On the web, dockview describes the same thing as a tree of branches whose
orientation alternates with depth (``grid.orientation`` at the root), with
leaves holding panel ids and sizes in whatever units the grid is given: it
re-lays the grid out proportionally to its container, so sizes only need to
be relative. ``dockview_layout`` converts one into the other, flattening
nested splits of the same direction into one branch since dockview cannot
nest those."""

from __future__ import annotations

VERTICAL = 1  # split top/bottom (a horizontal line)
HORIZONTAL = 2  # split left/right (a vertical line)
GRID_SIZE = 1000.0  # relative units, see the module docstring

ORIENTATIONS = {VERTICAL: "VERTICAL", HORIZONTAL: "HORIZONTAL"}


def layout_items(entry: dict) -> list[dict]:
    """The tree of a state-file ``layouts`` entry: its first non-empty
    ``Layout`` element (the desktop writes one list per element)."""
    for items in entry.get("items") or []:
        if items:
            return list(items)
    return []


def layout_view_ids(entry: dict) -> list[int]:
    """The saved view ids the layout's cells hold, in tree order."""
    return [
        int(item.get("viewId", 0))
        for item in layout_items(entry)
        if not item.get("direction") and item.get("viewId")
    ]


def dockview_layout(
    entry: dict,
    panels: dict[int, dict],
    active_view_id: int | None = None,
    size: float = GRID_SIZE,
) -> dict | None:
    """The dockview layout arranging ``panels`` (saved view id -> the
    panel's dockview entry: ``id``, ``contentComponent``, ``title``, ...)
    like the state file's layout ``entry``. None when a cell refers to a
    view without a panel or a panel has no cell, in which case the caller
    keeps whatever arrangement it has."""
    items = layout_items(entry)
    if not items:
        return None
    placed: list[int] = []

    def group_id(view_id: int) -> str:
        return f"group-{panels[view_id]['id']}"

    def build(index: int, width: float, height: float):
        """A node in relative units, plus its own orientation for a branch,
        or None for an empty cell."""
        if index >= len(items):
            return None
        item = items[index]
        direction = int(item.get("direction") or 0)
        if direction not in ORIENTATIONS:
            view_id = int(item.get("viewId") or 0)
            if not view_id:
                return None
            if view_id not in panels:
                raise LookupError(view_id)
            placed.append(view_id)
            panel_id = panels[view_id]["id"]
            data = {
                "views": [panel_id],
                "activeView": panel_id,
                "id": group_id(view_id),
            }
            return {"type": "leaf", "data": data}

        orientation = ORIENTATIONS[direction]
        fraction = min(max(float(item.get("fraction", 0.5)), 0.0), 1.0)
        if direction == HORIZONTAL:
            extents = [(width * fraction, height), (width * (1 - fraction), height)]
        else:
            extents = [(width, height * fraction), (width, height * (1 - fraction))]
        children = []
        for offset, (w, h) in enumerate(extents, start=1):
            child = build(2 * index + offset, w, h)
            if child is None:
                continue
            along = w if direction == HORIZONTAL else h
            if child["type"] == "branch" and child["orientation"] == orientation:
                # dockview alternates orientations: a split in the same
                # direction becomes more children of this branch.
                children.extend(child["data"])
            else:
                child["size"] = along
                children.append(child)
        if not children:
            return None
        if len(children) == 1:
            child = children[0]
            child.pop("size", None)
            return child
        return {"type": "branch", "data": children, "orientation": orientation}

    try:
        root = build(0, size, size)
    except LookupError:
        return None
    if root is None or sorted(placed) != sorted(panels):
        return None

    if root["type"] == "leaf":
        root["size"] = size
        root = {"type": "branch", "data": [root], "orientation": "HORIZONTAL"}
    orientation = root.pop("orientation")
    root["size"] = size
    _strip_orientation(root)

    layout = {
        "grid": {
            "root": root,
            "width": size,
            "height": size,
            "orientation": orientation,
        },
        "panels": {panel["id"]: panel for panel in panels.values()},
    }
    if active_view_id in panels:
        layout["activeGroup"] = group_id(active_view_id)
    return layout


def _strip_orientation(node: dict):
    node.pop("orientation", None)
    if node["type"] == "branch":
        for child in node["data"]:
            _strip_orientation(child)
