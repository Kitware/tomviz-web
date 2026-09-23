from trame_colormaps.core import presets

from tomviz_trame.app import data_model
from tomviz_trame.app.utils.colors import Color

COLOR_PALETTE = [
    "#4CAF50",
    "#FB8C00",
    "#E82D2D",
    "#2196F3",
    "#ffffff",
    "#000000",
]


def color_to_float_rgb(color: str) -> Color:
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    return (red / 255, green / 255, blue / 255)


def generate_colormaps(server):
    color_maps = {}
    for name, imgs in presets.COLORBAR_CACHE.items():
        color_maps[name] = {
            "name": name,
            "imgs": tuple(imgs.values()),
        }

    server.state.palette = COLOR_PALETTE

    return data_model.ColorMaps(
        server,
        presets={k: data_model.ColorPreset(server, **v) for k, v in color_maps.items()},
    )
