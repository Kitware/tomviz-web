import json
from pathlib import Path

import numpy as np
import pytest
from tomviz_pipeline import NodeState, Pipeline, PortData, SinkNode, SourceNode
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.nodes.transforms.legacy_python import LegacyPythonTransform

from tomviz_trame.app.pipeline.nodes import INPUT_PORT, build_transform_node

pytest.importorskip("scipy")

BUILTIN = Path(__file__).parent.parent / "src" / "tomviz_trame" / "builtin_kernels"


@pytest.fixture
def gaussian():
    description = json.loads((BUILTIN / "GaussianFilter.json").read_text())
    return description, BUILTIN / "GaussianFilter.py"


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

    assert isinstance(node, LegacyPythonTransform)
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
    from tomviz_trame.app.parameters_gui import to_parameters_model

    model = to_parameters_model(None, {"name": "NoParams", "parameters": []})
    assert set() == model.FIELD_NAMES
    assert "<v-" in model.generate_gui()  # an empty column, no controls


def test_parameter_edits_are_staged_until_applied(gaussian):
    from tomviz_trame.app import data_model
    from tomviz_trame.app.parameters_gui import to_parameters_model

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
