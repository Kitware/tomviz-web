import numpy as np
from tomviz_pipeline.dataset import Dataset
from tomviz_pipeline.molecule import Molecule
from tomviz_pipeline.table import Table

from tomviz_trame.app import data_model
from tomviz_trame.app.pipeline.representations import RepresentationType
from tomviz_trame.app.utils import data


def test_every_library_port_type_maps_to_a_payload_model():
    for port_type in data.IMAGE_PORT_TYPES:
        assert (
            data_model.port_data_model_for(port_type) is data_model.ImagePortDataModel
        )
    assert data_model.port_data_model_for("Table") is data_model.TablePortDataModel
    assert (
        data_model.port_data_model_for("Molecule") is data_model.MoleculePortDataModel
    )
    assert data_model.port_data_model_for("Unknown") is None


def test_registry_is_extensible():
    class CustomPortDataModel(data_model.PortDataModel):
        FAMILY = "custom"

    data_model.register_port_data_model(CustomPortDataModel, ["Custom"])
    assert data_model.port_data_model_for("Custom") is CustomPortDataModel


def test_representation_types_accept_their_family_only():
    for rep_type in RepresentationType:
        if rep_type is RepresentationType.MOLECULE:
            assert rep_type.accepts("Molecule")
            assert not rep_type.accepts("ImageData")
        else:
            assert rep_type.accepts("ImageData")
            assert rep_type.accepts("TiltSeries")
            assert not rep_type.accepts("Table")
            assert not rep_type.accepts("Molecule")


def test_image_description_round_trips_through_the_model():
    values = np.arange(24, dtype=np.float32).reshape((2, 3, 4), order="F")
    dataset = Dataset({"a": values, "b": values * 2}, active="b")
    description = data_model.ImagePortDataModel.describe(dataset, {"b"})

    model = data_model.ImagePortDataModel(None)
    model.apply(description)
    assert model.family == "image"
    assert model.scalars_names == ["a", "b"]
    assert model.dimensions == (2, 3, 4)
    assert model.extent == (0, 1, 0, 2, 0, 3)
    assert list(model.histograms) == ["b"]
    assert model.statistics_of("b").range == (0.0, 46.0)
    assert model.statistics_of("a") is None  # not requested: lazy
    assert model.can_compute("a")
    assert not model.can_compute("zzz")

    model.add_statistics(
        "a", data_model.ImagePortDataModel.compute_statistics(dataset, "a")
    )
    assert model.statistics_of("a").range == (0.0, 23.0)
    assert sum(model.histograms["a"]) == 24


def test_table_and_molecule_descriptions():
    table = Table(
        {"x": [1.0, 2.0, 4.0], "name": ["a", "b", "c"]}, axes_labels=("x", "y")
    )
    table_model = data_model.TablePortDataModel(None)
    table_model.apply(data_model.TablePortDataModel.describe(table))
    assert table_model.family == "table"
    assert table_model.column_names == ["x", "name"]
    assert table_model.num_rows == 3
    assert table_model.axes_labels == ["x", "y"]
    assert table_model.ranges == {"x": [1.0, 4.0]}  # string columns have no range

    molecule = Molecule(
        [1, 8, 1], [[0, 0, 0], [1, 0, 0], [2, 0, 0]], bonds=[[0, 1], [1, 2]]
    )
    molecule_model = data_model.MoleculePortDataModel(None)
    molecule_model.apply(data_model.MoleculePortDataModel.describe(molecule))
    assert molecule_model.family == "molecule"
    assert molecule_model.num_atoms == 3
    assert molecule_model.num_bonds == 2
    assert molecule_model.elements == ["H", "O"]
