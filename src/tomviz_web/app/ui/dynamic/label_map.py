"""The Label Map panel, after the desktop's: the representation, the label
table (show, color and name each label; filter the list, then show, hide or
invert what it lists), the surface's smoothing and opacity, and, for the
Volume representation, the volume panel without interpolation and blending
(pinned for labels)."""

from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app import data_model
from tomviz_web.app.pipeline import RepresentationType
from tomviz_web.app.pipeline.representations.label_map import REPRESENTATIONS
from tomviz_web.app.pipeline.vtk.label_surface import MAX_SMOOTHING
from tomviz_web.app.ui.dynamic._widgets import COMPACT, FILLED, slider
from tomviz_web.app.ui.dynamic.volume import VolumeRepresentationUI
from tomviz_web.app.utils.labels import MAX_LABELS

NAME = RepresentationType.LABEL_MAP.name
TEMPLATE = f"rep_{NAME}"

ROW_HEIGHT = 36
# What the filter matches: the value and the name shown (the default names
# are the desktop's).
SHOWN_NAME = "(l.name || (l.value === 0 ? 'Background' : `Label ${l.value}`))"
LISTED = (
    "(labels?.labels || []).filter((l) => !label_filter || "
    f"`${{l.value}} ${{{SHOWN_NAME}}}`.toLowerCase()"
    ".includes(label_filter.toLowerCase()))"
)
LISTED_VALUES = f"{LISTED}.map((l) => l.value)"


def _table(table_id):
    return data_model.get_instance(table_id)


def set_visible(table_id, value, visible):
    _table(table_id).set_visible(value, visible)


def set_color(table_id, value, color):
    _table(table_id).set_color(value, color)


def set_name(table_id, value, name):
    _table(table_id).set_name(value, name)


def set_visibility(table_id, values, visible):
    _table(table_id).set_visibility(values or [], visible)


def invert_visibility(table_id, values):
    _table(table_id).invert_visibility(values or [])


class LabelMapRepresentationUI(VolumeRepresentationUI):
    CATEGORICAL = True

    def __init__(self, server, template_name=TEMPLATE):
        super().__init__(server, template_name=template_name)

    def _content(self):
        v3.VSelect(
            label="Representation",
            v_model="rep.Representation",
            items=("label_map_representations", list(REPRESENTATIONS)),
            **FILLED,
        )
        with dataclass.Provider(
            name="labels",
            instance=("rep?.label_table?._id ?? rep?.label_table ?? null",),
        ):
            self._labels()
        with html.Div(v_if="rep.Representation === 'Surface'"):
            self._surface()
        with html.Div(v_else=True):
            super()._content()

    def _labels(self):
        with v3.VCard(classes="mt-2 pa-2 border-thin", flat=True):
            with html.Div(classes="d-flex align-center"):
                v3.VLabel("Labels", classes="text-subtitle-2")
                v3.VSpacer()
                html.Span(
                    "{{ labels?.labels?.length ?? 0 }} labels"
                    "{{ labels?.truncated"
                    f" ? ' (the lowest {MAX_LABELS:,}; there are more)' : '' }}}}",
                    classes="text-caption",
                )
            with html.Div(v_if="!labels || !labels.supported", classes="text-caption"):
                html.Span(
                    "{{ rep.LabelsUnsupportedReason || "
                    "(labels && !labels.supported ? 'Floating point values are "
                    "not labels: a label map needs integers.' : 'No data yet.') }}"
                )
            with html.Div(v_else=True):
                html.Div(
                    "Read from a plain volume: these colors and names belong to "
                    "this visualization.",
                    v_if="rep.LabelsAdopted",
                    classes="text-caption mb-1",
                )
                v3.VTextField(
                    label="Filter",
                    v_model=("label_filter", ""),
                    prepend_inner_icon="mdi-magnify",
                    clearable=True,
                    **FILLED,
                )
                with html.Div(classes="d-flex ga-1 my-1"):
                    for title, callback, args, tooltip in (
                        ("Show All", set_visibility, "true", "Show the labels listed"),
                        ("Hide All", set_visibility, "false", "Hide the labels listed"),
                        ("Invert", invert_visibility, None, "Swap shown and hidden"),
                    ):
                        extra = f", {args}" if args else ""
                        v3.VBtn(
                            title,
                            click=(
                                callback,
                                f"[labels._id, {LISTED_VALUES}{extra}]",
                            ),
                            title=tooltip,
                            size="small",
                            variant="tonal",
                            classes="flex-grow-1 text-none",
                        )
                with v3.VVirtualScroll(
                    items=(LISTED,),
                    item_height=ROW_HEIGHT,
                    max_height=8 * ROW_HEIGHT,
                    item_key="value",
                ):
                    with v3.Template(v_slot_default="{ item }"):
                        self._row()

    def _row(self):
        with html.Div(
            classes="d-flex align-center ga-2 pr-1",
            style=f"height: {ROW_HEIGHT}px",
        ):
            v3.VCheckboxBtn(
                model_value=("item.visible",),
                update_modelValue=(set_visible, "[labels._id, item.value, $event]"),
                density="compact",
                classes="flex-grow-0",
            )
            with v3.VMenu(close_on_content_click=False):
                with v3.Template(v_slot_activator="{ props }"):
                    html.Div(
                        v_bind="props",
                        title="Change the color",
                        classes="border-thin rounded flex-shrink-0",
                        style=(
                            "{ background: item.color, width: '20px', "
                            "height: '20px', cursor: 'pointer' }",
                        ),
                    )
                v3.VColorPicker(
                    model_value=("item.color",),
                    update_modelValue=(set_color, "[labels._id, item.value, $event]"),
                    modes=("['rgb', 'hex']",),
                    mode="hex",
                    show_swatches=False,
                )
            html.Span(
                "{{ item.value }}",
                classes="text-caption text-right flex-shrink-0",
                style="min-width: 2.5em",
            )
            v3.VTextField(
                model_value=("item.name",),
                placeholder=(
                    "item.value === 0 ? 'Background' : `Label ${item.value}`",
                ),
                change=(set_name, "[labels._id, item.value, $event.target.value]"),
                **FILLED,
            )
            html.Span(
                "{{ item.count.toLocaleString() }}",
                title="Voxels",
                classes="text-caption text-right flex-shrink-0",
                style="min-width: 4em",
            )

    def _surface(self):
        with v3.VCard(classes="mt-2 pa-2 border-thin", flat=True):
            v3.VLabel("Surface", classes="text-subtitle-2")
            v3.VNumberInput(
                label="Smoothing",
                v_model="rep.SurfaceSmoothing",
                # Bound, not literal: literals reach Vuetify as strings.
                min=("0",),
                max=(f"{MAX_SMOOTHING}",),
                control_variant="split",
                title="Smoothing iterations; 0 shows the raw voxel faces. The "
                "smoothing is shrink-free and never moves the surface more than "
                "half a voxel, so regions keep their size at any setting.",
                classes="mt-2",
                **FILLED,
            )
            slider("Opacity", "SurfaceOpacity", 0, 1, 0.01, 2)
            v3.VCheckbox(
                label="Custom Color Opacity",
                v_model="rep.use_internal_color_opacity",
                title="Color the other visualizations of this port with the "
                "shared map, and this one with its own (the labels go on both).",
                disabled=("rep.LabelsAdopted",),
                **COMPACT,
            )


UI = LabelMapRepresentationUI
