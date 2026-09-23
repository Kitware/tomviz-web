from tomviz_trame.app.catalog import _drop_retired, _prune_stale


def test_prune_stale_drops_what_no_longer_resolves(tmp_path):
    directories, modules = _prune_stale(
        [str(tmp_path), str(tmp_path / "gone")],
        ["tomviz_trame.builtin_kernels", "tomviz_trame.operators"],
    )
    assert directories == [str(tmp_path)]
    assert modules == ["tomviz_trame.builtin_kernels"]


def test_retired_defaults_are_dropped_but_user_entries_kept(tmp_path):
    """A config written by an older app lists the defaults of its day; those
    go, whatever the user added stays (and warns as usual if broken)."""
    directories, modules = _drop_retired(
        [str(tmp_path / "mine"), str(_home() / ".tomviz" / "operators")],
        ["tomviz_trame.builtin", "tomviz.operators.builtin", "mylab.kernels"],
    )
    assert directories == [str(tmp_path / "mine")]
    assert modules == ["mylab.kernels"]


def _home():
    from pathlib import Path

    return Path.home()
