import numpy as np
import pytest
from tomviz_pipeline.dataset import Dataset

from tomviz_web.app.utils import data


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


def test_threshold_seed_starts_at_the_brightest_voxels():
    # 95 % of the voxels above the minimum lie below the seed
    ramp = np.arange(1000, dtype=np.float32)
    assert data.threshold_seed(ramp) == pytest.approx(0.95 * 999 + 1, abs=1)
    # the background at the minimum does not count
    background = np.zeros(1_000_000, dtype=np.uint16)
    background[:1000] = np.arange(1000)
    assert data.threshold_seed(background) == pytest.approx(950, abs=1)
    # 5 % of 2 M voxels is under the budget; of 10 M, the budget governs
    two = np.arange(1, 2_000_001, dtype=np.float64)
    assert data.threshold_seed(two) == pytest.approx(1_900_000, rel=1e-3)
    ten = np.arange(1, 10_000_001, dtype=np.float32)
    assert data.threshold_seed(ten) == pytest.approx(9_750_000, rel=1e-3)
    # NaNs are ignored; a constant array is its own seed
    with_nan = np.append(ramp, np.nan)
    assert data.threshold_seed(with_nan) == data.threshold_seed(ramp)
    assert data.threshold_seed(np.full(10, 7.0)) == 7.0
