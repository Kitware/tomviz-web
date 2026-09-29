import json

import pytest
from tomviz_pipeline import SinkGroupNode, SinkNode
from tomviz_pipeline.core.state import pipeline_from_state_dict
from tomviz_pipeline.nodes import register_builtins

from tomviz_web.app.pipeline import state
from tomviz_web.app.pipeline.graph import data_port_of, primary_upstream
from tomviz_web.app.pipeline.representations import RepresentationType

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
    assert state.slice_settings(
        {
            "direction": 3,
            "planeCenter": [1, 2, 3],
            "planeNormal": [0, 1, 1],
            "opacity": 0.5,
            "sliceThickness": 3,
            "thickSliceMode": 1,
            "showArrow": False,
            "mapScalars": False,
        }
    ) == {
        "SliceDirection": "Custom",
        "PlaneCenter": (1.0, 2.0, 3.0),
        "PlaneNormal": (0.0, 1.0, 1.0),
        "Opacity": 0.5,
        "SliceThickness": 3,
        "ThickSliceMode": "Maximum",
        "ShowArrow": False,
        "MapScalars": False,
    }
    assert state.volume_settings(
        {
            "interpolation": 1,
            "lighting": {"enabled": True, "shadowReach": 0.4, "scattering": 1.5},
        }
    ) == {
        "InterpolationType": "Linear",
        "Shade": True,
        "ShadowReach": 0.4,
        "VolumetricScattering": 1.5,
    }
    assert state.volume_settings(
        {
            "blendingMode": 1,
            "rayJittering": False,
            "solidity": 0.5,
            "lighting": {"shadowsEnabled": False, "smoothNormals": True},
            "cutOut": {"enabled": True, "corner": 5, "position": [0.2, 0.4, 0.6]},
            "exploded": {
                "enabled": True,
                "axis": 3,
                "direction": [0, 1, 1],
                "chunks": 6,
                "gap": 0.5,
                "offset": -2,
                "showArrow": False,
            },
        }
    ) == {
        "BlendMode": "Max",
        "Jittering": False,
        "Solidity": 0.5,
        "ShadowsEnabled": False,
        "SmoothNormals": True,
        # the exploded view wins over the cut-out, as on the desktop
        "CutOutEnabled": False,
        "CutOutCorner": 5,
        "CutOutPosition": (0.2, 0.4, 0.6),
        "ExplodedEnabled": True,
        "ExplodedAxis": "Custom",
        "ExplodedDirection": (0.0, 1.0, 1.0),
        "ExplodedChunks": 6,
        "ExplodedGap": 0.5,
        "ExplodedOffset": -2,
        "ExplodedShowArrow": False,
    }


def test_outline_settings_take_the_desktop_grid_keys():
    assert state.outline_settings(
        {
            "gridColor": [0.9, 0.9, 0.9],
            "gridVisibility": True,
            "gridLines": False,
            "useCustomAxesTitles": True,
            "customXTitle": "Width",
        }
    ) == {
        "Color": "#e6e6e6",
        "ShowGridAxes": True,
        "ShowGrid": False,
        "UseCustomAxesTitles": True,
        "XTitle": "Width",
    }
    assert state.outline_settings({"gridColor": [1, 2]}) == {}


def test_contour_settings_take_the_desktop_keys():
    entry = {
        "contourValue": 12.5,
        "opacity": 0.5,
        "specularPower": 20,
        "representation": "Wireframe",
        "mapScalars": False,
        "useSolidColor": True,
        "color": "#FF8000",
        "activeScalars": "ramp",
        "colorByArray": True,
        "colorByArrayName": "other",
    }
    assert state.contour_settings(entry) == {
        "IsoValue": 12.5,
        "Opacity": 0.5,
        "SpecularPower": 20.0,
        "Mode": "Wireframe",
        "MapScalars": False,
        "UseSolidColor": True,
        "Color": "#ff8000",
        "ContourBy": "ramp",
    }
    assert state.contour_settings({"activeScalars": state.DEFAULT_SCALARS}) == {}
    # the "color by" array goes on the sink's own map (apply_sink_settings)
    assert state.unrestored_sink_settings(entry, RepresentationType.CONTOUR) == []


def test_threshold_settings_take_the_desktop_keys():
    entry = {
        "minimum": 10,
        "maximum": 20,
        "scalarArray": 1,
        "specular": 0.5,
        "representation": "Points",
        "colorByArray": False,
        "colorByArrayName": "ramp",
    }
    assert state.threshold_settings(entry) == {
        "Minimum": 10.0,
        "Maximum": 20.0,
        "ThresholdBy": 1,  # an index, named once data comes
        "Specular": 0.5,
        "Mode": "Points",
    }
    # both bounds or neither; -1 is the default array
    assert state.threshold_settings({"minimum": 1, "scalarArray": -1}) == {}
    assert state.unrestored_sink_settings(entry, RepresentationType.THRESHOLD) == []


def test_clip_settings_take_the_desktop_keys():
    # A Custom clip, inverted: the saved corners already carry the inverted
    # normal (the widget flipped it), so it is taken as is.
    entry = {
        "direction": 3,
        "plane": 4,
        "opacity": 0.25,
        "showPlane": False,
        "showArrow": False,
        "invertPlane": True,
        "selectedColor": [1.0, 0.0, 0.0],
        "origin": [0, 10, 5],
        "point1": [10, 10, 5],
        "point2": [0, 0, 5],
        "linked": True,
    }
    assert state.clip_settings(entry) == {
        "SliceDirection": "Custom",
        "Slice": 4,
        "Opacity": 0.25,
        "ShowPlane": False,
        "ShowArrow": False,
        "InvertPlane": True,
        "Color": "#ff0000",
        "PlaneCenter": (5.0, 5.0, 5.0),
        "PlaneNormal": (0.0, 0.0, -100.0),
    }
    # an axis-aligned clip ignores the corners
    assert state.clip_settings(
        {"direction": 1, **{k: entry[k] for k in ("origin", "point1", "point2")}}
    ) == {"SliceDirection": "YZ Plane"}
    assert state.unrestored_sink_settings(entry, RepresentationType.CLIP) == ["linked"]


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
        "linked": False,
    }
    assert state.unrestored_sink_settings(slice_entry, RepresentationType.SLICE) == [
        "linked",
    ]

    volume_entry = {
        "interpolation": 1,
        "activeScalars": "Other",
        "lighting": {"enabled": True, "ambient": 0.1, "glow": 1.0},
        "cutOut": {"enabled": False},
    }
    assert state.unrestored_sink_settings(volume_entry, RepresentationType.VOLUME) == [
        "activeScalars",
        "lighting.glow",
    ]
