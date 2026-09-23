import asyncio

import pytest

from tomviz_trame.app.data_model.color_opacity import (
    ECHO_WINDOW,
    ColorOpacityModel,
    normalize_color_space,
)
from tomviz_trame.app.pipeline.vtk.core import LookupTable, PiecewiseFunction

# A three-point map over [10, 20] in the state-file vocabulary.
COLORS = [10.0, 0.0, 0.0, 1.0, 15.0, 0.0, 1.0, 0.0, 20.0, 1.0, 0.0, 0.0]
POINTS = [10.0, 0.0, 0.5, 0.0, 20.0, 1.0, 0.5, 0.0]


def make_model():
    return ColorOpacityModel(None, lut=LookupTable(), pwf=PiecewiseFunction())


def test_new_map_comes_from_the_default_preset():
    model = make_model()
    assert model.active_color_preset == "Fast"
    assert len(model.color_points) > 2
    assert model.color_space == "Lab"  # the "Fast" preset's space
    xs = [row[0] for row in model.color_points]
    assert (min(xs), max(xs)) == (0.0, 1.0)
    assert model.opacity_points == [[0.0, 0.0, 0.5, 0.0], [1.0, 1.0, 0.5, 0.0]]
    assert model.lut.ctf.GetRange() == (0.0, 1.0)


def test_load_map_round_trips_and_keeps_its_range():
    model = make_model()
    model.load_map(COLORS, POINTS, "CIELAB")

    assert model.active_color_preset == ""
    assert model.color_space == "Lab"
    assert model.color_range == [10.0, 20.0]
    assert model.to_state() == {"colorSpace": "Lab", "colors": COLORS, "points": POINTS}
    assert model.lut.ctf.GetRange() == (10.0, 20.0)
    assert model.pwf.function.GetValue(15.0) == 0.5


def test_color_range_rescales_both_point_sets():
    model = make_model()
    model.load_map(COLORS, POINTS, "RGB")
    # Watchers need an event loop; drive the range change handler directly.
    model._on_color_range_change([0.0, 100.0])  # a JS array, like the client

    assert [row[0] for row in model.color_points] == [0.0, 50.0, 100.0]
    assert [row[1:] for row in model.color_points] == [
        [0.0, 0.0, 1.0],
        [0.0, 1.0, 0.0],
        [1.0, 0.0, 0.0],
    ]
    assert [row[0] for row in model.opacity_points] == [0.0, 100.0]


def test_editor_nodes_are_normalized_over_the_data_range():
    model = make_model()
    model.load_map(COLORS, POINTS, "RGB")
    model.data_range = (0.0, 40.0, 1.0)
    model._update_pwf()
    model._update_lut()

    assert model.scaled_opacities == [(0.25, 0.0), (0.5, 1.0)]
    assert model.scaled_colors[0][0] == 0.0
    assert model.scaled_colors[-1][0] == 1.0
    # Below the map's range the gradient clamps to the first color (blue).
    assert model.scaled_colors[0][1] == (0.0, 0.0, 1.0)

    # The editor moving a node (a client write) comes back in data units.
    model.update_from_client_state({"scaled_opacities": [(0.25, 0.0), (0.75, 1.0)]})
    assert model.opacity_points == [[10.0, 0.0, 0.5, 0.0], [30.0, 1.0, 0.5, 0.0]]


def test_server_side_opacity_syncs_never_write_back():
    """Rescaling to a new data range pushes normalized nodes to the editor;
    that push must not be mistaken for an edit, or the points snap back
    to the old range (the bug seen on every file open)."""
    model = make_model()
    model.load_map(COLORS, POINTS, "RGB")
    model.data_range = (0.0, 250.0, 1.0)
    model._update_pwf()  # nodes now at 0.04 and 0.08 of the data range
    model._on_color_range_change([0.0, 250.0])
    model._update_pwf()

    assert [row[0] for row in model.opacity_points] == [0.0, 250.0]
    assert model.scaled_opacities == [(0.0, 0.0), (1.0, 1.0)]
    # A stale echo of the earlier push, applied the old way, is inert.
    model.scaled_opacities = [(0.04, 0.0), (0.08, 1.0)]
    assert [row[0] for row in model.opacity_points] == [0.0, 250.0]


def test_color_space_aliases():
    assert normalize_color_space("CIELAB") == "Lab"
    assert normalize_color_space("Diverging") == "Diverging"
    assert normalize_color_space("") == "RGB"


class FakePort:
    """Just enough of an OutputPortModel for statistics to land."""

    def __init__(self, port_type="Volume", value_range=(0.0, 100.0)):
        self.port_type = port_type
        self.data_version = 1
        self.image = None  # pull() returns early: no arrays to read
        self._range = value_range

    def add_consumer(self, _):
        pass

    def statistics(self, _name):
        from types import SimpleNamespace

        return SimpleNamespace(range=self._range, histogram=[1.0, 2.0, 1.0])


def inherited(port_type="Volume"):
    source = make_model()
    source.load_map(COLORS, POINTS, "RGB")
    model = ColorOpacityModel(
        None, port=FakePort(port_type), lut=LookupTable(), pwf=PiecewiseFunction()
    )
    model.inherit_from(source)
    return source, model


def test_a_new_port_inherits_the_upstream_map():
    source, model = inherited()
    assert model.color_points == source.color_points
    assert model.opacity_points == source.opacity_points
    assert model.color_space == "RGB"
    assert model.active_color_preset == ""
    assert model.color_range == [10.0, 20.0]
    assert model.lut.ctf.GetRange() == (10.0, 20.0)
    # A copy: editing one leaves the other alone.
    model.color_points[0][1] = 0.5
    assert source.color_points[0][1] == 0.0


def test_an_inherited_map_stretches_to_the_new_data_range():
    _source, model = inherited()
    model.acquire("sink")
    model.active_data_array = "scalars"
    model._apply_statistics()
    assert model.data_range[:2] == (0.0, 100.0)
    assert model.color_range == [0.0, 100.0]
    model._on_color_range_change(model.color_range)  # the watcher, by hand
    assert [row[0] for row in model.color_points] == [0.0, 50.0, 100.0]
    assert [row[0] for row in model.opacity_points] == [0.0, 100.0]


def test_an_inherited_label_map_keeps_its_range():
    _source, model = inherited("LabelMap")
    model.acquire("sink")
    model.active_data_array = "labels"
    model._apply_statistics()
    assert model.data_range[:2] == (0.0, 100.0)
    assert model.color_range == [10.0, 20.0]  # label ids are data coordinates


def test_editor_edits_are_not_echoed_back():
    """A node the editor moved must not come back from the server: the
    echo lands while the user is still dragging and snaps the node to a
    stale position. Server-side changes still reach the editor."""

    async def run():
        model = make_model()
        model.data_range = (0.0, 100.0, 1.0)
        await model.completion()
        pushed = []
        model.register_flush_implementation(lambda msg: pushed.append(msg["state"]))

        # The client sends JS arrays, one message per mouse move.
        model.update_from_client_state(
            {"scaled_opacities": [[0.0, 0.0], [0.37, 0.61], [1.0, 1.0]]}
        )
        await model.completion()
        assert [row[0] for row in model.opacity_points] == pytest.approx(
            [0.0, 37.0, 100.0]
        )
        assert model.pwf.function.GetValue(37.0) == pytest.approx(0.61)
        assert not any("scaled_opacities" in state for state in pushed)

        # A new data range renormalizes the nodes: that is news.
        model.data_range = (0.0, 200.0, 1.0)
        await model.completion()
        echoes = [s["scaled_opacities"] for s in pushed if "scaled_opacities" in s]
        assert len(echoes) == 1
        assert echoes[0] == [
            pytest.approx((0.0, 0.0)),
            pytest.approx((0.185, 0.61)),
            pytest.approx((0.5, 1.0)),
        ]

    asyncio.run(run())


def test_a_stale_echo_of_pushed_nodes_does_not_move_the_points():
    """The trame-dataclass client (<= 2.2.0) writes an *older* server push
    back when two pushes of a field land during one in-flight request.
    While the range slider drags, such an echo of ``scaled_opacities`` used
    to land as an edit and drag the points back to a range the slider had
    left, so they drifted out of step with the color range."""

    async def run():
        model = make_model()
        model.data_range = (0.0, 100.0, 1.0)
        await model.completion()
        pushed = []
        model.register_flush_implementation(lambda msg: pushed.append(msg["state"]))

        # Two slider ticks: the server pushes the nodes for each.
        model.update_from_client_state({"color_range": [0, 50]})
        await model.completion()
        model.update_from_client_state({"color_range": [0, 25]})
        await model.completion()
        echoes = [s["scaled_opacities"] for s in pushed if "scaled_opacities" in s]
        assert echoes == [[(0.0, 0.0), (0.5, 1.0)], [(0.0, 0.0), (0.25, 1.0)]]

        # The next tick carries the client's echo of the first push.
        model.update_from_client_state(
            {"color_range": [0, 20], "scaled_opacities": [[0, 0], [0.5, 1]]}
        )
        await model.completion()
        assert [row[0] for row in model.opacity_points] == [0.0, 20.0]
        assert model.scaled_opacities == [(0.0, 0.0), (0.2, 1.0)]
        assert model.pwf.function.GetValue(20.0) == 1.0

    asyncio.run(run())


def test_server_owned_fields_ignore_client_writes():
    """The editor never writes the points, ranges or samples: a client
    write of those is an echo of an older push and must not become the
    truth."""
    model = make_model()
    model.load_map(COLORS, POINTS, "RGB")
    model.update_from_client_state(
        {
            "opacity_points": [[10.0, 0.0, 0.5, 0.0], [15.0, 1.0, 0.5, 0.0]],
            "color_points": [[10.0, 0.0, 0.0, 0.0], [15.0, 1.0, 1.0, 1.0]],
            "data_range": (0.0, 1.0, 1.0),
            "scaled_colors": [(0.0, (0.0, 0.0, 0.0))],
        }
    )
    assert model.to_state()["points"] == POINTS
    assert model.to_state()["colors"] == COLORS
    assert model.data_range == (0, 255, 1)
    assert len(model.scaled_colors) > 1


def test_an_old_push_becomes_an_edit_again_after_the_echo_window():
    """Echoes arrive within a couple of client messages of the push; a
    matching write later on is the user moving nodes to those positions."""
    model = make_model()
    model.data_range = (0.0, 100.0, 1.0)
    model._update_pwf()  # pushes [(0, 0), (0.01, 1)]
    old_push = [(0.0, 0.0), (0.01, 1.0)]
    model.update_from_client_state({"scaled_opacities": [[0, 0], [0.5, 1]]})
    assert [row[0] for row in model.opacity_points] == [0.0, 50.0]

    model.update_from_client_state({"scaled_opacities": old_push})  # an echo
    assert [row[0] for row in model.opacity_points] == [0.0, 50.0]

    for _ in range(ECHO_WINDOW):
        model.update_from_client_state({"color_range": [0.0, 50.0]})
    model.update_from_client_state({"scaled_opacities": old_push})  # an edit
    assert [row[0] for row in model.opacity_points] == [0.0, 1.0]
