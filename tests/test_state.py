import json

import pytest
from tomviz_pipeline import SinkGroupNode, SinkNode
from tomviz_pipeline.core.state import pipeline_from_state_dict
from tomviz_pipeline.nodes import register_builtins

from tomviz_trame.app.pipeline import state
from tomviz_trame.app.pipeline.graph import data_port_of, primary_upstream
from tomviz_trame.app.pipeline.representations import RepresentationType

# A reader feeding a sink group that fans out to two sinks, the desktop
# app's layout.
STATE = {
    "schemaVersion": 2,
    "pipeline": {
        "nextNodeId": 5,
        "nodes": [
            {"id": 1, "type": "source.reader", "label": "data", "fileNames": ["x.tif"]},
            {
                "id": 2,
                "type": "sinkGroup",
                "label": "Visualizations",
                "inputPorts": {"volume": {"type": ["ImageData"]}},
                "outputPorts": {"volume": {"persistent": False, "type": "ImageData"}},
                "typeInferenceSources": {"volume": "volume"},
            },
            {
                "id": 3,
                "type": "sink.slice",
                "label": "Slice",
                "inputPorts": {"volume": {"type": ["ImageData"]}},
                "direction": 1,
                "slice": 7,
                "viewId": 42,
            },
            {
                "id": 4,
                "type": "sink.outline",
                "label": "Outline",
                "inputPorts": {"volume": {"type": ["ImageData"]}},
                "visible": False,
            },
        ],
        "links": [
            {
                "from": {"node": 1, "port": "volume"},
                "to": {"node": 2, "port": "volume"},
            },
            {
                "from": {"node": 2, "port": "volume"},
                "to": {"node": 3, "port": "volume"},
            },
            {
                "from": {"node": 2, "port": "volume"},
                "to": {"node": 4, "port": "volume"},
            },
        ],
    },
}


@pytest.fixture(autouse=True)
def _builtins():
    register_builtins()


def test_the_library_builds_the_sink_group_the_desktop_saves():
    pipeline = pipeline_from_state_dict(STATE)
    reader = pipeline.node_by_id(1)
    group = pipeline.node_by_id(2)
    assert isinstance(group, SinkGroupNode)
    assert group.output_port("volume").source is reader.output_port("volume")
    for sink_id in (3, 4):
        sink = pipeline.node_by_id(sink_id)
        assert isinstance(sink, SinkNode)
        assert primary_upstream(sink) is group.output_port("volume")
        assert data_port_of(primary_upstream(sink)) is reader.output_port("volume")
    assert len(pipeline.links) == 3


def test_sink_settings_translate_desktop_enums():
    assert state.slice_settings({"direction": 1, "slice": 7, "interpolate": True}) == {
        "SliceDirection": "YZ Plane",
        "Slice": 7,
        "Interpolate": True,
    }
    assert state.slice_settings({"direction": 3}) == {}  # Custom: unsupported
    assert state.volume_settings(
        {
            "interpolation": 1,
            "lighting": {"enabled": True, "shadowReach": 0.4, "scattering": 1.5},
        }
    ) == {
        "InterpolationType": "Linear",
        "Shade": True,
        "GlobalIlluminationReach": 0.4,
        "VolumetricScatteringBlending": 1.5,
    }


def test_every_desktop_sink_type_has_a_representation_type():
    for sink_type in ("sink.outline", "sink.slice", "sink.volume"):
        rep_type = state.REPRESENTATION_BY_SINK_TYPE[sink_type]
        assert rep_type.representation_class is not None
    assert (
        state.REPRESENTATION_BY_SINK_TYPE["sink.contour"] is RepresentationType.CONTOUR
    )


def test_background_prefers_the_palette_and_unnests_the_triple():
    raw = {"paletteColor": [0.1, 0.2, 0.3]}
    assert state.background_of({"backgroundColor": [[0.5, 0.5, 0.5]]}, raw) == (
        0.5,
        0.5,
        0.5,
    )
    assert state.background_of(
        {"backgroundColor": [[0.5, 0.5, 0.5]], "useColorPaletteForBackground": 1}, raw
    ) == (0.1, 0.2, 0.3)
    assert state.background_of({}, {}) is None


def test_node_description_parses_the_embedded_json():
    description = {"name": "GaussianFilter", "parameters": []}
    assert (
        state.node_description({"description": json.dumps(description)}) == description
    )
    assert state.node_description({}) == {}
    assert state.node_description({"description": "{not json"}) == {}


def test_unrestored_settings_report_only_what_the_loader_skips():
    slice_entry = {
        "id": 7,
        "type": "sink.slice",
        "label": "Slice",
        "inputPorts": {},
        "state": "Current",
        "viewId": 1,
        "visible": True,
        "direction": 0,
        "slice": 3,
        "interpolate": True,
        "activeScalars": "tomviz::DefaultScalars",
        "thickSliceMode": 2,
        "opacity": 1,
    }
    assert state.unrestored_sink_settings(slice_entry, RepresentationType.SLICE) == [
        "opacity",
        "thickSliceMode",
    ]

    volume_entry = {
        "interpolation": 1,
        "activeScalars": "Other",
        "lighting": {"enabled": True, "ambient": 0.1},
    }
    assert state.unrestored_sink_settings(volume_entry, RepresentationType.VOLUME) == [
        "activeScalars",
        "lighting.ambient",
    ]
