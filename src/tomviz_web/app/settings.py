"""User settings that persist between runs: ``~/.tomviz/settings.json`` (or
``--settings``), the counterpart of the desktop's QSettings.

``PERSISTED`` lists the trame state keys that are remembered, with their
defaults. At startup the file's values override the defaults; every change
to one of the keys is written back, unless ``--read-only`` (shared with the
catalog) forbids writing. Keys the file holds that the app does not know are
kept as they are."""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from trame.app import TrameComponent

DEFAULT_FILE = Path.home() / ".tomviz" / "settings.json"

# State key -> default. Add an entry to remember another preference.
PERSISTED = {
    "drawer_columns": True,  # two-column drawer (pipeline left, the rest right)
}


class Settings(TrameComponent):
    def __init__(self, server=None, config_file=None, read_only=False):
        super().__init__(server)
        self.read_only = read_only
        self.file = Path(config_file).expanduser() if config_file else DEFAULT_FILE
        self._stored = self._read()

        for key, default in PERSISTED.items():
            value = self._stored.get(key, default)
            if not isinstance(value, type(default)):
                logger.warning(
                    "Setting '{}' in {} is not a {}; using the default",
                    key,
                    self.file,
                    type(default).__name__,
                )
                value = default
            setattr(self.state, key, value)

        self.state.change(*PERSISTED)(self._on_change)

    def _read(self) -> dict:
        try:
            data = json.loads(self.file.read_text())
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Cannot read settings from {}: {}", self.file, error)
            return {}
        if not isinstance(data, dict):
            logger.warning("Ignoring {}: not a JSON object", self.file)
            return {}
        return data

    def _on_change(self, **_):
        self.save({key: getattr(self.state, key) for key in PERSISTED})

    def save(self, values: dict):
        """Merge ``values`` into the file (a no-op under ``--read-only``)."""
        self._stored.update(values)
        if self.read_only:
            return
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text(json.dumps(self._stored, indent=2) + "\n")
        except OSError as error:
            logger.warning("Cannot write settings to {}: {}", self.file, error)
