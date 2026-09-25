from __future__ import annotations

from trame.app.dataclass import StateDataModel, Sync


class ColorPreset(StateDataModel):
    name = Sync(str)
    imgs = Sync(tuple[str, str], ("", ""))  # normal, inverted


class ColorMaps(StateDataModel):
    presets = Sync(dict[str, ColorPreset], dict, has_dataclass=True)
