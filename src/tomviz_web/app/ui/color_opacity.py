from trame.widgets import color_opacity_editor, dataclass, html
from trame.widgets import vuetify3 as v3

# CSS gradient of the map in use over the data range, from the colors sampled
# for the editor (``ColorOpacityModel.scaled_colors``: ``[t, [r, g, b]]``
# rows). The preset list keeps trame-colormaps' cached images: those preview
# static presets, not the current map.
CURRENT_MAP_GRADIENT = (
    "{ background: 'linear-gradient(to right,' + "
    "color_opacity.scaled_colors.map(([t, c]) => "
    "`rgb(${c[0] * 255},${c[1] * 255},${c[2] * 255}) ${t * 100}%`).join(',') + ')' }"
)


class ColorOpacityEditor(html.Div):
    def __init__(
        self,
        color_opacity_instance="active_color_opacity_id",
        colormaps_instance="",
    ):
        super().__init__()

        with self:
            with dataclass.Provider(
                v_if=color_opacity_instance,
                name="color_opacity",
                instance=(color_opacity_instance,),
            ):
                with dataclass.Provider(
                    v_if=colormaps_instance,
                    name="colormaps",
                    instance=(colormaps_instance,),
                ):
                    with v3.Template(
                        v_if="color_opacity && colormaps && color_opacity.scaled_colors && color_opacity.scaled_opacities",
                    ):
                        color_opacity_editor.ColorOpacityEditor(
                            style="height: 15rem;",
                            v_model_colorNodes=("color_opacity.scaled_colors",),
                            v_model_opacityNodes=("color_opacity.scaled_opacities",),
                            # Histogram nodes are normalized: x over the
                            # data range as [0, 1] (like the color and
                            # opacity nodes), y in histograms_range. With
                            # background_shape="histograms" the widget paints
                            # the preset gradient (scaled_colors) inside the
                            # histogram silhouette: colored histograms.
                            # show_histograms adds a flat overlay on top.
                            histograms=("color_opacity.scaled_histograms",),
                            histograms_range=("color_opacity.histograms_range",),
                            scalar_range=("default_scalar_range", [0, 1]),
                            show_histograms=("show_histograms", False),
                            show_color_editor=False,
                            histograms_color=("histograms_color", [0, 0, 0, 0.25]),
                            background_shape="histograms",
                            background_opacity=False,
                            # handle_radius=7,
                            # line_width=2,
                            # viewport_padding=("viewport_padding", [8, 8]),
                            # handle_color=("handle_color", [0.125, 0.125, 0.125, 1]),
                            # handle_border_color=("handle_border_color", [0.75, 0.75, 0.75, 1]),
                        )

                        with v3.Template(v_if="color_opacity.active_data_array"):
                            v3.VLabel(
                                "Color Range [{{ (color_opacity.color_range?.[0] || 0).toFixed(1) }}, {{ (color_opacity.color_range?.[1] || 1).toFixed(1) }}]"
                            )
                            v3.VRangeSlider(
                                v_model="color_opacity.color_range",
                                min=("color_opacity.data_range[0]",),
                                max=("color_opacity.data_range[1]",),
                                step=("color_opacity.data_range[2]",),
                                density="comfortable",
                                hide_details=True,
                            )

                            with html.Div(
                                classes="d-flex no-select position-relative align-center"
                            ):
                                with v3.VMenu(
                                    location="end",
                                    height="50vh",
                                    offset=5,
                                    close_on_content_click=False,
                                ):
                                    with v3.Template(v_slot_activator="{ props }"):
                                        with v3.VBtn(
                                            v_bind="props",
                                            classes="rounded flex-grow-1 mx-2 position-relative overflow-hidden",
                                            density="compact",
                                            hide_details=True,
                                            variant="outlined",
                                            size="small",
                                        ):
                                            # The map in use, whatever its origin
                                            # (preset, inverted, edited, loaded):
                                            # the same colors the editor shows.
                                            html.Div(
                                                classes="position-absolute w-100 h-100",
                                                style=(CURRENT_MAP_GRADIENT,),
                                            )
                                    with v3.VCard(style="width: 300px;"):
                                        v3.VTextField(
                                            autofocus=True,
                                            v_model=(
                                                "color_preset_filter",
                                                "",
                                            ),
                                            hide_details=True,
                                            density="comfortable",
                                            prepend_inner_icon="mdi-magnify",
                                            placeholder=(
                                                "color_opacity.active_color_preset || 'Custom'",
                                            ),
                                        )
                                        with v3.VList(density="comfortable"):
                                            with v3.VListItem(
                                                v_for="preset, name in colormaps.presets",
                                                key="idx",
                                                subtitle=("name",),
                                                click="color_opacity.active_color_preset = name;color_preset_filter='';",
                                                v_show="name.toLowerCase().includes(color_preset_filter.toLowerCase())",
                                            ):
                                                html.Img(
                                                    src=(
                                                        "preset.imgs[Number(color_opacity.invert_color_preset)]",
                                                    ),
                                                    classes="rounded",
                                                    style="height: 16px;max-width: 100%;",
                                                )
                                v3.VBtn(
                                    icon=(
                                        "color_opacity.invert_color_preset ? 'mdi-invert-colors' : 'mdi-invert-colors-off'",
                                    ),
                                    density="compact",
                                    size="small",
                                    hide_details=True,
                                    variant="plain",
                                    classes="rounded ml-2",
                                    click="color_opacity.invert_color_preset = !color_opacity.invert_color_preset",
                                    disabled=("!color_opacity.active_data_array",),
                                    v_tooltip_top="'Invert color preset'",
                                )

                                v3.VBtn(
                                    icon="mdi-arrow-expand-horizontal",
                                    density="compact",
                                    size="small",
                                    hide_details=True,
                                    variant="plain",
                                    classes="rounded ml-2",
                                    click="color_opacity.color_range = [color_opacity.data_range[0], color_opacity.data_range[1]]",
                                    disabled=("!color_opacity.active_data_array",),
                                    v_tooltip_top="'Reset color range to the full data range'",
                                )

                            with html.Div(classes="d-flex align-center"):
                                v3.VSelect(
                                    label="Color By",
                                    v_model="color_opacity.active_data_array",
                                    items=("color_opacity.data_arrays",),
                                    variant="solo-filled",
                                    flat=True,
                                    density="compact",
                                    hide_details=True,
                                    classes="my-1 mt-2",
                                )

                        with v3.VItemGroup(
                            v_else=True,
                            classes="d-inline-flex ga-1",
                            mandatory="force",
                            v_model="color_opacity.solid_color",
                        ):
                            with v3.VItem(v_for="(color, i) in palette", key="i"):
                                with v3.Template(
                                    v_slot_default="{ isSelected, toggle }"
                                ):
                                    with v3.VAvatar(
                                        color=("isSelected ? color : 'transparent'",),
                                        size=24,
                                    ):
                                        v3.VBtn(
                                            border="md surface opacity-100",
                                            color=("color",),
                                            size=18,
                                            flat=True,
                                            icon=True,
                                            ripple=False,
                                            click="toggle",
                                        )
