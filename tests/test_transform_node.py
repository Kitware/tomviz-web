import json

import numpy as np
import pytest
import tomviz_kernels
from tomviz_pipeline import NodeState, Pipeline, PortData, SinkNode, SourceNode
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.nodes.transforms.legacy_scriptable import (
    LegacyScriptableTransformNode,
)
from trame.app import get_server
from trame.ui.html import DivLayout

from tomviz_web.app.pipeline.nodes import INPUT_PORT, build_transform_node

pytest.importorskip("scipy")

KERNELS = tomviz_kernels.directory()


@pytest.fixture(autouse=True, scope="module")
def html_context():
    """The parameter panels are generated as widgets without a server; like
    in the app, they take the one of the layout being built."""
    server = get_server("transform-node", client_type="vue3")
    with DivLayout(server):
        yield


@pytest.fixture
def gaussian():
    description = json.loads((KERNELS / "GaussianFilter.json").read_text())
    return description, KERNELS / "GaussianFilter.py"


class ConstantSource(SourceNode):
    """A source node that emits a fixed dataset."""

    type_name = "test.constant"

    def __init__(self, values):
        super().__init__()
        self.values = values
        self.add_output("volume", "ImageData")

    def execute(self):
        dataset = Dataset({"scalars": self.values.copy()})
        self.output_port("volume").set_data(PortData(dataset, "ImageData"))
        return True


class RecordingSink(SinkNode):
    executable = True

    def __init__(self):
        super().__init__()
        self.add_input(INPUT_PORT, ["ImageData"])
        self.received = []

    def consume(self, inputs):
        self.received.append(inputs[INPUT_PORT].payload.active_scalars.copy())
        return True


def test_build_transform_node_from_a_v1_script(gaussian):
    description, script = gaussian
    node = build_transform_node(description, script, {"sigma": 0.0})

    assert isinstance(node, LegacyScriptableTransformNode)
    assert node.type_name == "transform.legacyPython"
    assert node.label == "Gaussian Blur"
    assert node.parameter("sigma") == 0.0
    assert node.input_port(INPUT_PORT) is not None
    assert node.output_port("volume") is not None


def test_gaussian_chain_reexecutes_on_parameter_change(gaussian):
    description, script = gaussian
    values = np.zeros((9, 9, 9), dtype=np.float32, order="F")
    values[4, 4, 4] = 1.0  # a single spike; blur spreads it

    graph = Pipeline()
    source = graph.add_node(ConstantSource(values))
    blur = graph.add_node(build_transform_node(description, script, {"sigma": 0.0}))
    sink = graph.add_node(RecordingSink())
    graph.create_link(source.output_port("volume"), blur.input_port(INPUT_PORT))
    graph.create_link(blur.output_port("volume"), sink.input_port(INPUT_PORT))

    assert graph.execute().succeeded()
    assert blur.state == NodeState.Current
    np.testing.assert_array_equal(sink.received[0], values)  # sigma 0 is a no-op

    graph.auto_execute = True
    blur.set_parameters(sigma=1.0)  # re-runs blur + sink, not the source

    assert len(sink.received) == 2
    blurred = sink.received[1]
    assert blurred.shape == values.shape
    assert blurred[4, 4, 4] < 1.0
    assert blurred[4, 4, 5] > 0.0
    assert np.isclose(blurred.sum(), 1.0, atol=1e-3)


def test_parameterless_description_still_makes_a_model():
    from tomviz_web.app.parameters_gui import to_parameters_model

    model = to_parameters_model(None, {"name": "NoParams", "parameters": []})
    assert set() == model.FIELD_NAMES
    assert "<v-" in model.generate_gui()  # an empty column, no controls


def test_dataset_parameters_are_ports_not_controls():
    from tomviz_web.app.parameters_gui import to_parameters_model

    description = {
        "name": "TwoInputs",
        "parameters": [
            {"name": "second_dataset", "label": "Second", "type": "dataset"},
            {"name": "weight", "type": "double", "default": 0.5},
        ],
    }
    model = to_parameters_model(None, description)
    assert {"weight"} == model.FIELD_NAMES
    assert "second_dataset" not in model.generate_gui()

    node = build_transform_node(description, KERNELS / "CombineDatasets.py")
    assert [port.name for port in node.input_ports()] == [INPUT_PORT, "second_dataset"]
    assert "second_dataset" not in node.parameters


@pytest.mark.parametrize("name", tomviz_kernels.names())
def test_every_kernel_makes_a_parameters_model(name):
    from tomviz_web.app.parameters_gui import to_parameters_model

    description = json.loads((KERNELS / f"{name}.json").read_text())
    model = to_parameters_model(None, description)
    assert "<v-" in model.generate_gui()


def test_parameter_edits_are_staged_until_applied(gaussian):
    from tomviz_web.app import data_model
    from tomviz_web.app.parameters_gui import to_parameters_model

    description, script = gaussian
    node = build_transform_node(description, script, {"sigma": 1.0})
    model = data_model.TransformNodeModel(
        None,
        node=node,
        label=node.label,
        type_name=node.type_name,
        entry_name="GaussianFilter",
        parameters=to_parameters_model(None, description),
    )
    model.bind_parameters()
    assert model.parameters.sigma == 1.0
    assert model.parameters_dirty is False

    # Typing in the panel edits the mirror; the watcher (called directly:
    # watchers need a loop) only flags it, the node is untouched.
    model.parameters.sigma = 2.5
    model._on_parameters_change(2.5)
    assert model.parameters_dirty is True
    assert node.parameter("sigma") == 1.0

    model.reset_parameters()
    assert model.parameters.sigma == 1.0
    assert model.parameters_dirty is False

    model.parameters.sigma = 3.0
    model._on_parameters_change(3.0)
    model.apply_parameters()
    assert node.parameter("sigma") == 3.0
    assert model.parameters_dirty is False
