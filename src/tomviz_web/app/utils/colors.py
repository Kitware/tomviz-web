import math
from typing import TypeVar

T = TypeVar("T")

Color = tuple[float, float, float]
Node = tuple[float, T]
ColorNode = Node[Color]
OpacityNode = Node[float]


def make_linear_nodes(values: list[T], range: tuple[float, float]) -> list[Node[T]]:
    span = range[1] - range[0]
    dx = span / max(len(values) - 1, 1)

    nodes: list[Node[T]] = []

    for i, value in enumerate(values):
        nodes.append((range[0] + i * dx, value))

    return nodes


def rescale_nodes(nodes: list[Node[T]], range: tuple[float, float]) -> list[Node[T]]:
    curr_range = [math.inf, -math.inf]

    for s, _ in nodes:
        curr_range[0] = min(s, curr_range[0])

        curr_range[1] = max(s, curr_range[1])

    curr_delta = curr_range[1] - curr_range[0]
    new_delta = range[1] - range[0]

    new_nodes = []

    for s, v in nodes:
        f = (s - curr_range[0]) / curr_delta
        new_s = range[0] + f * new_delta
        new_nodes.append((new_s, v))

    return new_nodes


def rgb_to_hex(rgb: Color) -> str:
    """``(r, g, b)`` in [0, 1] as the ``#rrggbb`` a color picker edits."""
    return "#" + "".join(f"{round(min(max(c, 0.0), 1.0) * 255):02x}" for c in rgb)


def hex_to_rgb(value: str) -> Color:
    """``#rrggbb`` (a trailing alpha byte is ignored) as ``(r, g, b)`` in
    [0, 1]."""
    digits = value.lstrip("#")
    return tuple(int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))
