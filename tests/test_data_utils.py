import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset

from tomviz_trame.app.utils import data


def test_histogram_matches_numpy_exactly():
    values = np.random.default_rng(0).random((30, 20, 10)).astype(np.float32)
    expected = np.histogram(values, bins=128)[0].tolist()
    assert data.histogram(values) == expected


def test_histogram_is_exact_when_split_across_threads(monkeypatch):
    monkeypatch.setattr(data, "HISTOGRAM_CHUNK", 1000)
    values = np.random.default_rng(1).integers(0, 1000, (50, 40, 30)).astype(np.uint16)
    data_range = data.value_range(values)
    expected = np.histogram(values, bins=64, range=data_range)[0].tolist()
    assert data.histogram(values, 64, data_range) == expected
    assert sum(expected) == values.size


def test_histogram_bins_span_the_given_range():
    values = np.array([0.0, 5.0, 10.0], dtype=np.float32)
    # bins [0, 10) and [10, 20]
    assert data.histogram(values, 2, (0.0, 20.0)) == [2, 1]
    assert data.value_range(values) == (0.0, 10.0)


def test_describe_dataset_geometry_and_requested_statistics_only():
    a = np.arange(24, dtype=np.float32).reshape((2, 3, 4), order="F")
    dataset = Dataset({"a": a, "b": a * 2}, active="b")
    dataset.spacing = [1.0, 2.0, 0.5]

    description = data.describe_dataset(dataset, arrays=["b", "missing"])

    assert description.scalars_names == ["a", "b"]
    assert description.active_scalars == "b"
    assert description.dimensions == (2, 3, 4)
    assert description.spacing == (1.0, 2.0, 0.5)
    assert description.extent == (0, 1, 0, 2, 0, 3)
    assert description.bounds == (0.0, 1.0, 0.0, 4.0, 0.0, 1.5)
    assert description.memory == (2 * a.nbytes) // 1024
    assert list(description.statistics) == ["b"]
    assert description.statistics["b"].range == (0.0, 46.0)
    assert sum(description.statistics["b"].histogram) == 24


def test_describe_empty_dataset():
    description = data.describe_dataset(Dataset({}), arrays=["x"])
    assert description.scalars_names == []
    assert description.dimensions == (0, 0, 0)
    assert description.statistics == {}


@pytest.mark.parametrize(("value", "expected"), [(0, 0), (1, 0), (100, 2)])
def test_log10_maps_empty_bins_to_zero(value, expected):
    assert data.log10(value) == expected
