"""The settings file: defaults, overrides, writes on change, read-only."""

import json

from trame.app import get_server

from tomviz_trame.app.settings import PERSISTED, Settings


def make_server(name):
    server = get_server(name, client_type="vue3")
    # Change listeners only run once the state is ready (a started server).
    server.state.ready()
    return server


def test_defaults_without_a_file(tmp_path):
    server = make_server("settings-defaults")
    settings = Settings(server=server, config_file=tmp_path / "missing.json")
    assert server.state.drawer_columns is PERSISTED["drawer_columns"]
    assert not settings.file.exists()


def test_file_values_override_defaults_and_changes_are_written(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"drawer_columns": False, "other": 42}))
    server = make_server("settings-file")
    Settings(server=server, config_file=path)
    assert server.state.drawer_columns is False

    with server.state:
        server.state.drawer_columns = True
    server.state.flush()
    saved = json.loads(path.read_text())
    assert saved["drawer_columns"] is True
    assert saved["other"] == 42  # unknown keys survive


def test_wrong_types_fall_back_to_the_default(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"drawer_columns": "yes"}))
    server = make_server("settings-types")
    Settings(server=server, config_file=path)
    assert server.state.drawer_columns is PERSISTED["drawer_columns"]


def test_read_only_never_writes(tmp_path):
    path = tmp_path / "settings.json"
    server = make_server("settings-readonly")
    Settings(server=server, config_file=path, read_only=True)
    with server.state:
        server.state.drawer_columns = not PERSISTED["drawer_columns"]
    server.state.flush()
    assert not path.exists()


def test_unreadable_file_is_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    server = make_server("settings-broken")
    Settings(server=server, config_file=path)
    assert server.state.drawer_columns is PERSISTED["drawer_columns"]
