"""Load tomviz state files (``.tvsm`` JSON, ``.tvh5`` HDF5 bundles) into a
session.

The library builds the graph: ``tomviz_pipeline.load_state`` returns a
``Pipeline`` with readers, transforms and, for ``.tvh5``, the stored port
payloads already in place. Everything the library treats as opaque is read
here from the raw state dict (``read_state_json``): the ``views`` section,
the settings the desktop app stores at the top level of each sink entry,
and the ``metadata`` of output ports (color maps, active scalars).

Desktop specifics handled here:

- Sinks hang off a passthrough ``sinkGroup`` node between the chain end
  and the visualizations; the library builds it as a real ``SinkGroupNode``
  and ``build_node_models`` mirrors it like any node.
- Every sink type collapses to an inert placeholder in the library;
  ``replace_sinks`` swaps the supported ones for real
  ``RepresentationSinkNode``s (same node id, same link) and applies their
  settings. Unsupported types stay in the graph as inert nodes with a plain
  ``NodeModel``, so the pipeline widget lists them but nothing shows them.
- Slice ``direction`` is XY 0, YZ 1, XZ 2, Custom 3 (``planeCenter`` and
  ``planeNormal`` place a Custom plane); ``activeScalars`` may be the
  sentinel ``tomviz::DefaultScalars``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from tomviz_pipeline import Pipeline, SinkGroupNode, SinkNode, TransformNode
from tomviz_pipeline.state import load_state, read_state_json

from tomviz_web.app import data_model
from tomviz_web.app.parameters_gui import to_parameters_model
from tomviz_web.app.pipeline.graph import data_port_of, is_data_node, primary_upstream
from tomviz_web.app.pipeline.layout import dockview_layout
from tomviz_web.app.pipeline.nodes import INPUT_PORT, RepresentationSinkNode
from tomviz_web.app.pipeline.representations import RepresentationType
from tomviz_web.app.pipeline.representations.slice import THICK_SLICE_MODES
from tomviz_web.app.pipeline.representations.volume import BLEND_MODES
from tomviz_web.app.utils.colors import rgb_to_hex
from tomviz_web.app.utils.volume import EXPLODED_AXES

if TYPE_CHECKING:
    from tomviz_web.app.pipeline.manager import PipelineManager

STATE_EXTENSIONS = (".tvsm", ".tvh5")

DEFAULT_SCALARS = "tomviz::DefaultScalars"
SLICE_DIRECTIONS = {0: "XY Plane", 1: "YZ Plane", 2: "XZ Plane", 3: "Custom"}
VOLUME_INTERPOLATION = {0: "Nearest", 1: "Linear"}
REPRESENTATION_BY_SINK_TYPE = {t.sink_type: t for t in RepresentationType}


# ---- state helpers (pure, no trame) -----------------------------------------


def node_description(entry: dict) -> dict:
    """The JSON description a Python node entry carries, parsed."""
    description = entry.get("description")
    if not description:
        return {}
    try:
        return (
            json.loads(description)
            if isinstance(description, str)
            else dict(description)
        )
    except json.JSONDecodeError:
        logger.warning("Node {} has an unreadable description", entry.get("id"))
        return {}


def background_of(view_entry: dict, raw: dict):
    if view_entry.get("useColorPaletteForBackground") and raw.get("paletteColor"):
        color = raw["paletteColor"]
    else:
        color = view_entry.get("backgroundColor")
    while isinstance(color, list) and color and isinstance(color[0], list):
        color = color[0]  # the desktop nests the triple once
    if not isinstance(color, list) or len(color) < 3:
        return None
    return (float(color[0]), float(color[1]), float(color[2]))


def outline_settings(entry: dict) -> dict:
    settings = {}
    color = entry.get("gridColor")
    if isinstance(color, list) and len(color) == 3:
        settings["Color"] = rgb_to_hex(tuple(float(c) for c in color))
    for key, field in (
        ("gridVisibility", "ShowGridAxes"),
        ("gridLines", "ShowGrid"),
        ("useCustomAxesTitles", "UseCustomAxesTitles"),
    ):
        if key in entry:
            settings[field] = bool(entry[key])
    for axis in "XYZ":
        key = f"custom{axis}Title"
        if key in entry:
            settings[f"{axis}Title"] = str(entry[key])
    return settings


def vector3(value):
    """A saved ``[x, y, z]`` as a float triple, or None."""
    if isinstance(value, list) and len(value) == 3:
        try:
            return tuple(float(c) for c in value)
        except (TypeError, ValueError):
            return None
    return None


def slice_settings(entry: dict) -> dict:
    settings = {}
    direction = SLICE_DIRECTIONS.get(entry.get("direction"))
    if direction is None and entry.get("direction") is not None:
        logger.warning("Slice direction {} not supported, using XY", entry["direction"])
    if direction is not None:
        settings["SliceDirection"] = direction
    if "slice" in entry:
        settings["Slice"] = int(entry["slice"])
    for key, field in (
        ("interpolate", "Interpolate"),
        ("showArrow", "ShowArrow"),
        ("mapScalars", "MapScalars"),
    ):
        if key in entry:
            settings[field] = bool(entry[key])
    if "opacity" in entry:
        settings["Opacity"] = float(entry["opacity"])
    if "sliceThickness" in entry:
        settings["SliceThickness"] = max(int(entry["sliceThickness"]), 1)
    mode = entry.get("thickSliceMode")
    if isinstance(mode, int) and 0 <= mode < len(THICK_SLICE_MODES):
        settings["ThickSliceMode"] = THICK_SLICE_MODES[mode]
    # A Custom plane; origin / point1 / point2 describe the same plane.
    for key, field in (("planeCenter", "PlaneCenter"), ("planeNormal", "PlaneNormal")):
        value = vector3(entry.get(key))
        if value is not None:
            settings[field] = value
    return settings


def volume_settings(entry: dict) -> dict:
    settings = {}
    interpolation = VOLUME_INTERPOLATION.get(entry.get("interpolation"))
    if interpolation is not None:
        settings["InterpolationType"] = interpolation
    mode = entry.get("blendingMode")
    if isinstance(mode, int) and 0 <= mode < len(BLEND_MODES):
        settings["BlendMode"] = BLEND_MODES[mode]
    if "rayJittering" in entry:
        settings["Jittering"] = bool(entry["rayJittering"])
    if "solidity" in entry:
        settings["Solidity"] = float(entry["solidity"])

    lighting = entry.get("lighting") or {}
    for key, field, kind in LIGHTING_SETTINGS:
        if key in lighting:
            settings[field] = kind(lighting[key])

    cut_out = entry.get("cutOut") or {}
    if "enabled" in cut_out:
        settings["CutOutEnabled"] = bool(cut_out["enabled"])
    if "corner" in cut_out:
        settings["CutOutCorner"] = min(max(int(cut_out["corner"]), 0), 7)
    position = vector3(cut_out.get("position"))
    if position is not None:
        settings["CutOutPosition"] = position

    exploded = entry.get("exploded") or {}
    axis = exploded.get("axis")
    if isinstance(axis, int) and 0 <= axis < len(EXPLODED_AXES):
        settings["ExplodedAxis"] = EXPLODED_AXES[axis]
    direction = vector3(exploded.get("direction"))
    if direction is not None:
        settings["ExplodedDirection"] = direction
    for key, field, kind in EXPLODED_SETTINGS:
        if key in exploded:
            settings[field] = kind(exploded[key])
    if settings.get("ExplodedEnabled"):
        settings["CutOutEnabled"] = False  # the desktop's precedence
    return settings


# (state key, model field, type) of the volume's "lighting" and "exploded"
LIGHTING_SETTINGS = (
    ("enabled", "Shade", bool),
    ("ambient", "Ambient", float),
    ("diffuse", "Diffuse", float),
    ("specular", "Specular", float),
    ("specularPower", "SpecularPower", float),
    ("scattering", "VolumetricScattering", float),
    ("shadowsEnabled", "ShadowsEnabled", bool),
    ("shadowReach", "ShadowReach", float),
    ("anisotropy", "ScatteringAnisotropy", float),
    ("smoothNormals", "SmoothNormals", bool),
)
EXPLODED_SETTINGS = (
    ("enabled", "ExplodedEnabled", bool),
    ("showArrow", "ExplodedShowArrow", bool),
    ("chunks", "ExplodedChunks", int),
    ("gap", "ExplodedGap", float),
    ("offset", "ExplodedOffset", int),
)


SURFACE_MODES = ("Surface", "Wireframe", "Points")


def surface_settings(entry: dict, floats: tuple[tuple[str, str], ...]) -> dict:
    """The appearance keys contour and threshold share."""
    settings = {}
    for key, field in floats:
        if key in entry:
            settings[field] = float(entry[key])
    if entry.get("representation") in SURFACE_MODES:
        settings["Mode"] = entry["representation"]
    if "mapScalars" in entry:
        settings["MapScalars"] = bool(entry["mapScalars"])
    return settings


def contour_settings(entry: dict) -> dict:
    settings = surface_settings(
        entry,
        (
            ("contourValue", "IsoValue"),
            ("opacity", "Opacity"),
            ("ambient", "Ambient"),
            ("diffuse", "Diffuse"),
            ("specular", "Specular"),
            ("specularPower", "SpecularPower"),
        ),
    )
    if "useSolidColor" in entry:
        settings["UseSolidColor"] = bool(entry["useSolidColor"])
    color = entry.get("color")
    if isinstance(color, str) and len(color) == 7 and color.startswith("#"):
        settings["Color"] = color.lower()  # QColor::name(), #rrggbb
    active = entry.get("activeScalars")
    if isinstance(active, str) and active != DEFAULT_SCALARS:
        settings["ContourBy"] = active
    return settings


def threshold_settings(entry: dict) -> dict:
    settings = surface_settings(
        entry, (("opacity", "Opacity"), ("specular", "Specular"))
    )
    # The desktop saves both bounds or neither.
    if "minimum" in entry and "maximum" in entry:
        settings["Minimum"] = float(entry["minimum"])
        settings["Maximum"] = float(entry["maximum"])
    index = entry.get("scalarArray")
    if isinstance(index, int) and index >= 0:
        settings["ThresholdBy"] = index  # resolved to a name once data comes
    return settings


def plane_of_points(entry: dict):
    """The (center, normal) of the plane the desktop's plane widget saves as
    ``origin``, ``point1`` and ``point2``, or None. The normal is theirs,
    inverted or not."""
    corners = [vector3(entry.get(key)) for key in ("origin", "point1", "point2")]
    if any(c is None for c in corners):
        return None
    origin, point1, point2 = corners
    u = [a - o for a, o in zip(point1, origin, strict=True)]
    v = [b - o for b, o in zip(point2, origin, strict=True)]
    normal = (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )
    if not any(normal):
        return None
    center = tuple(o + (a + b) / 2 for o, a, b in zip(origin, u, v, strict=True))
    return center, normal


def clip_settings(entry: dict) -> dict:
    settings = {}
    direction = SLICE_DIRECTIONS.get(entry.get("direction"))
    if direction is not None:
        settings["SliceDirection"] = direction
    if "plane" in entry:
        settings["Slice"] = int(entry["plane"])
    if "opacity" in entry:
        settings["Opacity"] = float(entry["opacity"])
    for key, field in (
        ("showPlane", "ShowPlane"),
        ("showArrow", "ShowArrow"),
        ("invertPlane", "InvertPlane"),
    ):
        if key in entry:
            settings[field] = bool(entry[key])
    color = vector3(entry.get("selectedColor"))
    if color is not None:
        settings["Color"] = rgb_to_hex(color)
    plane = plane_of_points(entry)
    if plane is not None and direction == "Custom":
        settings["PlaneCenter"], settings["PlaneNormal"] = plane
    return settings


def molecule_settings(entry: dict) -> dict:
    settings = {}
    for key, field in (("ballRadius", "BallRadius"), ("stickRadius", "StickRadius")):
        if key in entry:
            settings[field] = float(entry[key])
    return settings


SINK_SETTINGS = {
    RepresentationType.CLIP: clip_settings,
    RepresentationType.MOLECULE: molecule_settings,
    RepresentationType.CONTOUR: contour_settings,
    RepresentationType.THRESHOLD: threshold_settings,
    RepresentationType.OUTLINE: outline_settings,
    RepresentationType.SLICE: slice_settings,
    RepresentationType.VOLUME: volume_settings,
}

# Entry keys the loader restores (or that carry no setting), per sink type;
# anything else is reported so a user knows why the view differs from the
# desktop's.
COMMON_SINK_KEYS = {
    "id",
    "type",
    "label",
    "state",
    "inputPorts",
    "viewId",
    "visible",
    "colorOpacityMap",
    "useDetachedColorMap",
}
SINK_KEYS = {
    RepresentationType.MOLECULE: {"ballRadius", "stickRadius"},
    RepresentationType.CLIP: {
        "direction",
        "plane",
        "opacity",
        "showPlane",
        "showArrow",
        "invertPlane",
        "selectedColor",
        "origin",
        "point1",
        "point2",
    },
    RepresentationType.CONTOUR: {
        "contourValue",
        "opacity",
        "ambient",
        "diffuse",
        "specular",
        "specularPower",
        "representation",
        "mapScalars",
        "useSolidColor",
        "color",
        "activeScalars",
        # the sink's own color map's array, see apply_sink_settings
        "colorByArray",
        "colorByArrayName",
    },
    RepresentationType.THRESHOLD: {
        "minimum",
        "maximum",
        "opacity",
        "specular",
        "representation",
        "mapScalars",
        "scalarArray",
        "colorByArray",
        "colorByArrayName",
    },
    RepresentationType.OUTLINE: {
        "gridColor",
        "gridVisibility",
        "gridLines",
        "useCustomAxesTitles",
        "customXTitle",
        "customYTitle",
        "customZTitle",
    },
    RepresentationType.SLICE: {
        "direction",
        "slice",
        "interpolate",
        "opacity",
        "sliceThickness",
        "thickSliceMode",
        "showArrow",
        "mapScalars",
        "planeCenter",
        "planeNormal",
        "origin",
        "point1",
        "point2",
    },
    RepresentationType.VOLUME: {
        "interpolation",
        "blendingMode",
        "rayJittering",
        "solidity",
        "lighting",
        "cutOut",
        "exploded",
        "labelMapDefaultsApplied",  # label maps have no sink here yet
    },
}
LIGHTING_KEYS = {key for key, _field, _kind in LIGHTING_SETTINGS}
PORT_METADATA_KEYS = {"colorOpacityMap", "activeScalars", "label"}


def unrestored_sink_settings(entry: dict, representation_type) -> list[str]:
    handled = COMMON_SINK_KEYS | SINK_KEYS.get(representation_type, set())
    ignored = [k for k in entry if k not in handled]
    if entry.get("activeScalars") in (None, DEFAULT_SCALARS):
        ignored = [k for k in ignored if k != "activeScalars"]
    if representation_type is RepresentationType.VOLUME:
        lighting = entry.get("lighting") or {}
        ignored += [f"lighting.{k}" for k in lighting if k not in LIGHTING_KEYS]
    return sorted(ignored)


# ---- session builder (event loop) ------------------------------------------


async def load_state_file(manager: PipelineManager, path: str | Path):
    """Replace the session with the state file at ``path``. Reading the
    graph (and a ``.tvh5``'s payloads) happens in a thread; the session is
    built on the event loop."""
    path = Path(path)
    raw = read_state_json(path)
    loop = asyncio.get_running_loop()
    pipeline = await loop.run_in_executor(None, load_state, path)
    apply_state(manager, pipeline, raw)


def apply_state(manager: PipelineManager, pipeline: Pipeline, raw: dict):
    """Build the session from a loaded graph and its raw state dict."""
    entries = {entry["id"]: entry for entry in raw.get("pipeline", {}).get("nodes", [])}

    manager.reset()
    views = create_views(manager, raw)
    manager.attach_pipeline(pipeline)
    build_node_models(manager, pipeline, entries)
    replace_sinks(manager, pipeline, entries, views)

    roots = manager.model.roots
    manager.model.active_node = [roots[0]._id] if roots else []
    manager.execute()


def create_views(
    manager: PipelineManager, raw: dict
) -> dict[int, data_model.ViewModel]:
    """One render window per saved view, camera and settings applied.
    Returns the saved view id -> ``ViewModel`` map."""
    views = {}
    active_view_id = None
    for entry in raw.get("views", []) or [{}]:
        view_id = manager.add_view()
        view: data_model.ViewModel = data_model.get_instance(view_id)
        if "interactionMode" in entry:
            view.interactive_3d = entry["interactionMode"] != "2D"
        if "orientationAxesVisible" in entry:
            view.orientation_axes_visibility = bool(entry["orientationAxesVisible"])
        if "centerAxesVisible" in entry:
            view.center_axes_visibility = bool(entry["centerAxesVisible"])
        background = background_of(entry, raw)
        if background is not None:
            view.background = background
        camera = entry.get("camera")
        if camera:
            view.set_camera(
                {**camera, "parallelProjection": entry.get("isOrthographic")}
            )
        if "id" in entry:
            views[entry["id"]] = view
        if entry.get("active") or active_view_id is None:
            active_view_id = view_id
    manager.state.active_view_id = active_view_id
    restore_layout(manager, raw, views, active_view_id)
    return views


def restore_layout(
    manager: PipelineManager,
    raw: dict,
    views: dict[int, data_model.ViewModel],
    active_view_id: str | None,
):
    """Arrange the render windows like the state file's first layout (the
    desktop's ``layouts``); without one, or when it does not account for
    every view, the windows stay where ``add_view`` put them."""
    entries = raw.get("layouts") or []
    if not entries or not views:
        return
    panels = {
        saved_id: manager.panel_entry(view._id) for saved_id, view in views.items()
    }
    active_saved_id = next(
        (saved_id for saved_id, view in views.items() if view._id == active_view_id),
        None,
    )
    layout = dockview_layout(entries[0], panels, active_saved_id)
    if layout is None:
        logger.info("View layout not restored: it does not match the views")
        return
    manager.restore_layout(layout)


def build_node_models(manager: PipelineManager, pipeline: Pipeline, entries: dict):
    """Mirror every source, transform and sink group, in topological order so
    a node's upstream models exist first (sinks are ``replace_sinks``'s)."""
    server = manager.server
    catalog = manager.ctx.catalog
    for node in pipeline.execution_order():
        if isinstance(node, SinkGroupNode):
            manager._track(
                data_model.SinkGroupNodeModel(
                    server, node=node, label=node.label, type_name=node.type_name
                )
            )
            continue
        if not is_data_node(node):
            continue
        entry = entries.get(node.id, {})
        description = node_description(entry)
        name = description.get("name") or node.type_name
        upstream = primary_upstream(node)
        parent = manager.node_models.get(upstream.node.id) if upstream else None

        if isinstance(node, TransformNode) and isinstance(
            parent, data_model.DataNodeModel
        ):
            catalog_entry = catalog.entries.get(name)
            model = data_model.TransformNodeModel(
                server,
                node=node,
                label=node.label,
                type_name=node.type_name,
                entry_name=name,
                icon=catalog_entry.icon if catalog_entry else "mdi-function-variant",
                input=parent,
                parameters=to_parameters_model(
                    server, description or {"name": name, "parameters": []}
                ),
            )
            model.bind_parameters()
            manager._track(model)
        else:
            if isinstance(node, TransformNode):
                logger.warning(
                    "Transform '{}' (id={}) has no upstream data node; shown as a root",
                    node.label,
                    node.id,
                )
            # A Python source carries its description (and so parameters to
            # edit); a file reader does not.
            catalog_entry = catalog.entries.get(name) if description else None
            model = data_model.SourceNodeModel(
                server,
                node=node,
                label=node.label,
                type_name=node.type_name,
                entry_name=name if description else "",
                icon=catalog_entry.icon if catalog_entry else "",
                parameters=(
                    to_parameters_model(server, description) if description else None
                ),
            )
            model.bind_parameters()
            manager._track(model)

        apply_port_metadata(model, entry)
        manager.describe_ports(model)


def apply_port_metadata(model: data_model.DataNodeModel, entry: dict):
    """Color maps and active scalars saved on the node's output ports."""
    ports = entry.get("outputPorts", {}) or {}
    for port_model in model.outputs:
        metadata = (ports.get(port_model.name) or {}).get("metadata") or {}
        ignored = sorted(k for k in metadata if k not in PORT_METADATA_KEYS)
        if ignored:
            logger.info(
                "Port '{}' of '{}': metadata not restored: {}",
                port_model.name,
                model.label,
                ", ".join(ignored),
            )
        color_opacity = port_model.color_opacity
        if color_opacity is None:
            continue
        color_map = metadata.get("colorOpacityMap")
        if color_map:
            color_opacity.load_map(
                color_map.get("colors", []),
                color_map.get("points", []),
                color_map.get("colorSpace", "RGB"),
            )
        active = metadata.get("activeScalars")
        if active and active != DEFAULT_SCALARS:
            color_opacity.active_data_array = active


def replace_sinks(
    manager: PipelineManager,
    pipeline: Pipeline,
    entries: dict,
    views: dict[int, data_model.ViewModel],
):
    """Swap the library's inert sink placeholders for real sinks where a
    representation exists, keeping node ids and links (to the group's
    passthrough, or straight to a data port). The others get a plain model."""
    for placeholder in [n for n in pipeline.nodes if isinstance(n, SinkNode)]:
        if isinstance(placeholder, RepresentationSinkNode):
            continue
        entry = entries.get(placeholder.id, {})
        representation_type = REPRESENTATION_BY_SINK_TYPE.get(placeholder.type_name)
        if (
            representation_type is None
            or representation_type.representation_class is None
        ):
            logger.info(
                "Sink '{}' ({}) is not supported yet; kept in the graph, not shown",
                placeholder.label,
                placeholder.type_name,
            )
            manager._track(
                data_model.NodeModel(
                    manager.server,
                    node=placeholder,
                    label=placeholder.label,
                    type_name=placeholder.type_name,
                )
            )
            continue

        upstream = primary_upstream(placeholder)
        data_port = data_port_of(upstream)
        port_model = manager.port_model_of(data_port)
        if port_model is None:
            logger.warning(
                "Sink '{}' has no data node to display; dropped", placeholder.label
            )
            pipeline.remove_node(placeholder)
            continue
        if not representation_type.accepts(data_port.port_type):
            logger.warning(
                "Sink '{}' cannot display {} data; dropped",
                placeholder.label,
                data_port.port_type,
            )
            pipeline.remove_node(placeholder)
            continue

        view = views.get(entry.get("viewId")) or data_model.get_instance(
            manager.state.active_view_id
        )
        sink = RepresentationSinkNode(
            representation_type, manager, port_model, view, manager.run_on_loop
        )
        sink.id = placeholder.id
        pipeline.remove_node(placeholder)
        pipeline.add_node(sink)
        pipeline.create_link(upstream, sink.input_port(INPUT_PORT))
        manager._track(sink.model)
        apply_sink_settings(sink.model, representation_type, entry)


def apply_sink_settings(model, representation_type: RepresentationType, entry: dict):
    ignored = unrestored_sink_settings(entry, representation_type)
    if ignored:
        logger.info(
            "Sink '{}': settings not restored: {}", model.label, ", ".join(ignored)
        )
    model.Visibility = bool(entry.get("visible", True))
    settings = SINK_SETTINGS.get(representation_type)
    if settings is not None:
        for field, value in settings(entry).items():
            setattr(model, field, value)

    detached = (
        entry.get("colorOpacityMap") if entry.get("useDetachedColorMap") else None
    )
    internal = getattr(model, "_internal_color_opacity", None)
    if detached and internal is not None:
        internal.load_map(
            detached.get("colors", []),
            detached.get("points", []),
            detached.get("colorSpace", "RGB"),
        )
        model.use_internal_color_opacity = True

    # The desktop colors a contour or threshold by its own "color by" array
    # through the port's map; here a color map carries its array, so that
    # array goes on the sink's own map.
    color_by = entry.get("colorByArrayName") if entry.get("colorByArray") else None
    if color_by and internal is not None:
        internal.active_data_array = str(color_by)
        model.use_internal_color_opacity = True
