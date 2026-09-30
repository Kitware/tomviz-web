"""Label maps: volumes whose voxel values are labels, not samples. After
the desktop's ``LabelTable`` and ``LabelMapData``; pure NumPy, safe on any
thread.

A label table is the list of labels present in the data, in ascending
value order, each an entry dict: ``value``, ``name`` (empty until named),
``color`` (``#rrggbb``), ``visible`` and ``count`` (voxels). It is the
authoritative record of per-label color and visibility; the transfer
functions are derived from it (``band_points``), never the other way
round.
"""

from __future__ import annotations

import colorsys
import math

import numpy as np

from tomviz_web.app.utils.colors import hex_to_rgb, rgb_to_hex

# Labels tracked at most; past this a scan stops admitting new ones and
# reports the table truncated (the desktop's bound).
MAX_LABELS = 65536
# The conventional background label: hidden by default, never a region.
BACKGROUND = 0.0
# Half-width of each label's flat band in the transfer functions: two nodes
# per label at value -/+ this give every integer label its own color, with
# the ramps in between at values no voxel holds (the desktop's).
BAND_HALF_WIDTH = 0.25
# Values per bincount call when scanning, to bound the temporary copy.
SCAN_CHUNK = 16_000_000


def label_color(value) -> str:
    """The desktop's segmentation palette: golden-angle hues by label value,
    so a label keeps its color in every label map that holds it."""
    index = round(value)
    hue = math.fmod(index * 137.508, 360.0) / 360.0
    saturation = 0.65 + 0.35 * ((index % 3) / 2.0)
    brightness = 0.75 + 0.25 * ((index + 1) % 2)
    return rgb_to_hex(colorsys.hsv_to_rgb(hue, saturation, brightness))


# ---- what can be a label map ---------------------------------------------------


def is_label_dtype(dtype) -> bool:
    """Integers can be labels; floating point values are samples of a
    continuous quantity, and enumerating them is meaningless."""
    return np.issubdtype(np.dtype(dtype), np.integer)


def can_interpret_as_label_map(dtype, value_range=None) -> bool:
    """Whether a plain volume could be shown as labels (a segmentation read
    from a file arrives untyped). Integers spanning at most ``MAX_LABELS``
    values: 8- and 16-bit ones always do; wider ones need their range."""
    if not is_label_dtype(dtype):
        return False
    if np.dtype(dtype).itemsize <= 2:
        return True
    if value_range is None:
        return False
    low, high = value_range
    return high - low + 1 <= MAX_LABELS


# ---- scanning ------------------------------------------------------------------


def scan_labels(values: np.ndarray) -> tuple[list[tuple[float, int]], bool]:
    """The distinct values of an integer array with their voxel counts,
    ascending, and whether there were more than ``MAX_LABELS`` of them (the
    table then keeps the lowest). Empty for floating point arrays."""
    flat = values.ravel(order="K")
    if flat.size == 0 or not is_label_dtype(flat.dtype):
        return [], False
    low, high = int(flat.min()), int(flat.max())
    if high - low < 1 << 24:
        # Counting beats sorting: a pass per chunk, over the value range
        counts = np.zeros(high - low + 1, dtype=np.int64)
        for start in range(0, flat.size, SCAN_CHUNK):
            chunk = flat[start : start + SCAN_CHUNK].astype(np.int64) - low
            counts += np.bincount(chunk, minlength=counts.size)
        present = np.flatnonzero(counts)
        pairs = list(
            zip((present + low).tolist(), counts[present].tolist(), strict=True)
        )
    else:
        unique, counts = np.unique(flat, return_counts=True)
        pairs = list(zip(unique.tolist(), counts.tolist(), strict=True))
    truncated = len(pairs) > MAX_LABELS
    return [(float(v), int(c)) for v, c in pairs[:MAX_LABELS]], truncated


def reconcile(entries: list[dict], scanned) -> list[dict]:
    """``scanned`` (value, count) pairs as table entries, carrying over the
    name, color and visibility of every label that survives. New labels get
    their palette color and are visible, but for the background."""
    known = {entry["value"]: entry for entry in entries}
    updated = []
    for value, count in scanned:
        entry = known.get(value)
        if entry is not None:
            updated.append({**entry, "count": count})
            continue
        updated.append(
            {
                "value": value,
                "name": "",
                "color": label_color(value),
                "visible": value != BACKGROUND,
                "count": count,
            }
        )
    return updated


def region_labels(entries: list[dict]) -> list[float]:
    """The labels drawn as surfaces, hidden ones included (so hiding a
    label does not reshape its neighbours): all but the background."""
    return [e["value"] for e in entries if e["value"] != BACKGROUND]


def visible_labels(entries: list[dict]) -> list[float]:
    return [e["value"] for e in entries if e["visible"] and e["value"] != BACKGROUND]


# ---- transfer functions --------------------------------------------------------


def band_points(entries: list[dict]):
    """The color and opacity points giving every label a flat band: two
    nodes per label at value -/+ ``BAND_HALF_WIDTH``, the outermost pinned
    to the first and last label so rescaling to the data range changes
    nothing. Returns ``([[x, r, g, b], ...], [[x, opacity, 0.5, 0], ...])``;
    hidden labels are transparent."""
    colors, opacities = [], []
    last = len(entries) - 1
    for i, entry in enumerate(entries):
        value = entry["value"]
        rgb = list(hex_to_rgb(entry["color"]))
        alpha = 1.0 if entry["visible"] else 0.0
        low = value if i == 0 else value - BAND_HALF_WIDTH
        high = value if i == last else value + BAND_HALF_WIDTH
        for x in (low, high):
            if colors and colors[-1][0] == x:
                continue  # a single label: both pins land on its value
            colors.append([x, *rgb])
            opacities.append([x, alpha, 0.5, 0.0])
    return colors, opacities


# ---- state files (the desktop's LabelTable JSON) -------------------------------


def serialize(entries: list[dict]) -> dict:
    labels = []
    for entry in entries:
        item = {
            "value": entry["value"],
            "color": list(hex_to_rgb(entry["color"])),
            "visible": entry["visible"],
        }
        if entry.get("name"):
            item["name"] = entry["name"]
        labels.append(item)
    return {"labels": labels, "nextColorIndex": len(labels)}


def deserialize(table: dict) -> list[dict]:
    """Entries from a saved table, without voxel counts (the next scan
    supplies them and reconciles the labels against the data)."""
    entries = []
    for item in table.get("labels", []) or []:
        if "value" not in item:
            continue
        value = float(item["value"])
        color = item.get("color")
        entries.append(
            {
                "value": value,
                "name": str(item.get("name", "")),
                "color": (
                    rgb_to_hex(tuple(float(c) for c in color))
                    if isinstance(color, list) and len(color) == 3
                    else label_color(value)
                ),
                "visible": bool(item.get("visible", True)),
                "count": 0,
            }
        )
    entries.sort(key=lambda e: e["value"])
    return entries
