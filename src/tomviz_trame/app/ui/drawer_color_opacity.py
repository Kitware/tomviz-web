from trame.widgets import html
from trame.widgets import vuetify3 as v3

from tomviz_trame.app.ui.color_opacity import ColorOpacityEditor


class ColorOpacitySection(html.Div):
    def __init__(self):
        super().__init__(classes="tomviz-drawer__color")

        with self:
            with v3.VBtn(
                prepend_icon=(
                    "show_color_opacity ? 'mdi-chevron-down' : 'mdi-chevron-up'",
                ),
                text="Color Opacity Map",
                click="show_color_opacity = !show_color_opacity",
                classes="w-100 text-none mb-1",
                variant="tonal",
                spaced="end",
            ):
                pass

            with v3.VExpandTransition():
                with v3.VCard(
                    classes="border-thin overflow-hidden flex-fill pa-2 mb-2",
                    flat=True,
                    variant="flat",
                    v_show=("show_color_opacity", True),
                ):
                    with html.Div(v_show=("active_color_opacity_id",)):
                        ColorOpacityEditor(
                            color_opacity_instance="active_color_opacity_id",
                            colormaps_instance="colormaps_id",
                        )
