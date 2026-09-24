from trame.app.dev import reload as dev_reload

from . import (
    color_opacity,
    drawer_color_opacity,
    drawer_pipeline,
    drawer_properties,
    drawer_transforms,
    open_data,
    render_view,
    settings,
    toolbar,
    utils,
)
from .color_opacity import ColorOpacityEditor
from .drawer_color_opacity import ColorOpacitySection
from .drawer_pipeline import PipelineSection
from .drawer_properties import PropertiesSections
from .drawer_transforms import TransformSelection
from .dynamic import initialize_dynamic_ui
from .open_data import FileLoader
from .render_view import RenderWindow
from .settings import SettingsDialog
from .toolbar import Toolbar
from .utils import toolbar_btn


def reload(m=None):
    """Reload ui modules to help with the --hot-reload option of trame"""
    dev_reload(
        color_opacity,
        drawer_color_opacity,
        drawer_transforms,
        drawer_pipeline,
        drawer_properties,
        open_data,
        render_view,
        settings,
        toolbar,
        utils,
    )

    if m:
        m.__loader__.exec_module(m)


__all__ = [
    "ColorOpacityEditor",
    "ColorOpacitySection",
    "FileLoader",
    "PipelineSection",
    "PropertiesSections",
    "RenderWindow",
    "SettingsDialog",
    "Toolbar",
    "TransformSelection",
    "initialize_dynamic_ui",
    "toolbar_btn",
]
