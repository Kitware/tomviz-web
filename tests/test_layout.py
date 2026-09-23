"""The desktop's view layout tree turned into a dockview layout."""

from tomviz_trame.app.pipeline.layout import (
    HORIZONTAL,
    VERTICAL,
    dockview_layout,
    layout_view_ids,
)


def cell(view_id):
    return {"direction": 0, "fraction": 0.5, "viewId": view_id}


def split(direction, fraction):
    return {"direction": direction, "fraction": fraction, "viewId": 0}


def panels(*view_ids):
    return {v: {"id": f"panel{v}", "title": "3D View"} for v in view_ids}


def leaves(node):
    if node["type"] == "leaf":
        return [(node["data"]["views"][0], node.get("size"))]
    return [leaf for child in node["data"] for leaf in leaves(child)]


def test_a_single_view_fills_the_grid():
    layout = dockview_layout({"items": [[cell(7)]]}, panels(7), active_view_id=7)
    grid = layout["grid"]
    assert grid["orientation"] == "HORIZONTAL"
    assert grid["root"]["type"] == "branch"
    assert leaves(grid["root"]) == [("panel7", 1000.0)]
    assert layout["panels"] == {"panel7": {"id": "panel7", "title": "3D View"}}
    assert layout["activeGroup"] == "group-panel7"


def test_a_left_right_split_keeps_its_fraction():
    entry = {"items": [[split(HORIZONTAL, 0.3), cell(1), cell(2)]]}
    layout = dockview_layout(entry, panels(1, 2))
    grid = layout["grid"]
    assert grid["orientation"] == "HORIZONTAL"
    assert leaves(grid["root"]) == [("panel1", 300.0), ("panel2", 700.0)]
    assert "activeGroup" not in layout


def test_nested_splits_alternate_and_same_direction_ones_flatten():
    # Top/bottom, the bottom half split left/right, the right quarter split
    # top/bottom again: dockview nests HORIZONTAL inside VERTICAL, and the
    # innermost VERTICAL split becomes a branch of its own inside that.
    entry = {
        "items": [
            [
                split(VERTICAL, 0.5),
                cell(1),
                split(HORIZONTAL, 0.5),
                None,
                None,
                cell(2),
                split(VERTICAL, 0.25),
                None,
                None,
                None,
                None,
                None,
                None,
                cell(3),
                cell(4),
            ]
        ]
    }
    # Empty slots are padding in the flat tree.
    entry["items"][0] = [item or cell(0) for item in entry["items"][0]]
    layout = dockview_layout(entry, panels(1, 2, 3, 4))
    root = layout["grid"]["root"]
    assert layout["grid"]["orientation"] == "VERTICAL"
    top, bottom = root["data"]
    assert (top["type"], top["size"]) == ("leaf", 500.0)
    assert (bottom["type"], bottom["size"]) == ("branch", 500.0)
    left, right = bottom["data"]
    assert (left["data"]["views"], left["size"]) == (["panel2"], 500.0)
    assert (right["type"], right["size"]) == ("branch", 500.0)
    assert leaves(right) == [("panel3", 125.0), ("panel4", 375.0)]

    # The same direction twice in a row is one branch with three children.
    entry = {
        "items": [
            [
                split(VERTICAL, 0.5),
                cell(1),
                split(VERTICAL, 0.5),
                cell(0),
                cell(0),
                cell(2),
                cell(3),
            ]
        ]
    }
    layout = dockview_layout(entry, panels(1, 2, 3))
    assert layout["grid"]["orientation"] == "VERTICAL"
    assert leaves(layout["grid"]["root"]) == [
        ("panel1", 500.0),
        ("panel2", 250.0),
        ("panel3", 250.0),
    ]


def test_empty_cells_collapse():
    entry = {"items": [[split(HORIZONTAL, 0.5), cell(0), cell(1)]]}
    layout = dockview_layout(entry, panels(1))
    assert leaves(layout["grid"]["root"]) == [("panel1", 1000.0)]


def test_layouts_that_do_not_match_the_views_are_refused():
    entry = {"items": [[split(HORIZONTAL, 0.5), cell(1), cell(2)]]}
    assert dockview_layout(entry, panels(1)) is None  # a cell without a view
    assert dockview_layout(entry, panels(1, 2, 3)) is None  # a view without a cell
    assert dockview_layout({"items": [[]]}, panels(1)) is None
    assert layout_view_ids(entry) == [1, 2]
