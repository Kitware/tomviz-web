"""The graph policy behind editing: tip port, data ports behind groups,
type compatibility."""

from tomviz_pipeline import (
    Pipeline,
    PortData,
    SinkGroupNode,
    SinkNode,
    SourceNode,
    TransformNode,
)

from tomviz_trame.app.pipeline import graph


class Const(SourceNode):
    type_name = "gtest.const"

    def __init__(self, port_type="ImageData"):
        super().__init__()
        self.add_output("volume", port_type)

    def execute(self):
        self.output_port("volume").set_data(PortData(1, "ImageData"))
        return True


class Identity(TransformNode):
    type_name = "gtest.identity"

    def __init__(self, outputs=("volume:ImageData",)):
        super().__init__()
        self.add_input("volume", "ImageData")
        for spec in outputs:
            name, port_type = spec.split(":")
            self.add_output(name, port_type)

    def transform(self, inputs):
        return {p.name: inputs["volume"] for p in self.output_ports()}


class Sink(SinkNode):
    type_name = "gtest.sink"

    def __init__(self, accepted=("ImageData",)):
        super().__init__()
        self.add_input("volume", list(accepted))


def grouped_chain():
    """source -> transform -> group -> 2 sinks"""
    p = Pipeline()
    src = p.add_node(Const())
    xf = p.add_node(Identity())
    group = p.add_node(SinkGroupNode())
    group.add_passthrough("volume", "ImageData")
    sinks = [p.add_node(Sink()) for _ in range(2)]
    p.create_link(src.output_port("volume"), xf.input_port("volume"))
    p.create_link(xf.output_port("volume"), group.input_port("volume"))
    for sink in sinks:
        p.create_link(group.output_port("volume"), sink.input_port("volume"))
    return p, src, xf, group, sinks


def test_port_type_compatibility_uses_the_image_base_type():
    assert graph.is_port_type_compatible("TiltSeries", ["ImageData"])
    assert graph.is_port_type_compatible("Table", ["Table"])
    assert not graph.is_port_type_compatible("Table", ["ImageData"])
    assert not graph.is_port_type_compatible("ImageData", ["Volume"])


def test_compatible_output_picks_the_first_matching_port():
    node = Identity(("stats:Table", "labels:LabelMap"))
    assert graph.compatible_output(node, Sink().input_port("volume")).name == "labels"
    assert graph.compatible_output(node, Sink(["Table"]).input_port("volume")).name == (
        "stats"
    )
    assert (
        graph.compatible_output(node, Sink(["Molecule"]).input_port("volume")) is None
    )


def test_data_port_looks_through_groups():
    p, _src, xf, group, _sinks = grouped_chain()
    passthrough = group.output_port("volume")
    assert graph.data_port_of(passthrough) is xf.output_port("volume")
    assert graph.data_port_of(xf.output_port("volume")) is xf.output_port("volume")
    p.remove_link(group.input_port("volume").link)
    assert graph.data_port_of(passthrough) is None
    assert graph.data_port_of(None) is None


def test_branch_tip_climbs_out_of_sinks_and_follows_transforms():
    p, src, xf, group, sinks = grouped_chain()
    tip = xf.output_port("volume")
    assert graph.find_branch_tip(sinks[0]) is tip
    assert graph.find_branch_tip(group) is tip
    assert graph.find_branch_tip(src) is tip
    assert graph.find_branch_tip(xf) is tip

    # A second transform after the group's transform: the tip moves on, and
    # groups hanging off intermediate ports are not followed.
    later = p.add_node(Identity())
    p.create_link(xf.output_port("volume"), later.input_port("volume"))
    assert graph.find_branch_tip(src) is later.output_port("volume")
    assert graph.find_branch_tip(sinks[1]) is later.output_port("volume")


def test_tip_output_port_falls_back_to_the_first_source():
    p, src, xf, _group, sinks = grouped_chain()
    assert graph.find_tip_output_port(p, sinks[0]) is xf.output_port("volume")
    assert graph.find_tip_output_port(p, None) is xf.output_port("volume")
    other = Identity()  # not in the graph
    assert graph.find_tip_output_port(p, other) is xf.output_port("volume")
    assert graph.find_tip_output_port(Pipeline()) is None
    lonely = Pipeline()
    lonely.add_node(SinkGroupNode())
    assert graph.find_tip_output_port(lonely) is None


def test_group_output_for_reuses_a_compatible_group():
    p, _src, xf, group, _sinks = grouped_chain()
    target = xf.output_port("volume")
    assert graph.group_output_for(target, ["ImageData"]) is group.output_port("volume")
    # The group is selected itself: attach to its passthrough directly.
    assert graph.group_output_for(
        group.output_port("volume"), ["ImageData"]
    ) is group.output_port("volume")
    # No group accepting tables: one has to be created.
    assert graph.group_output_for(target, ["Table"]) is None
    p.remove_node(group)
    assert graph.group_output_for(target, ["ImageData"]) is None


def test_passthrough_type_widens_image_like_ports():
    assert graph.passthrough_type("TiltSeries") == "ImageData"
    assert graph.passthrough_type("Table") == "Table"
