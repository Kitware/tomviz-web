import time

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from tomviz_trame.app import module, ui
from tomviz_trame.app.pipeline import RepresentationType


class Toolbar(v3.VAppBar):
    def __init__(self):
        super().__init__(density="compact")

        with self:
            v3.VProgressLinear(
                v_show="trame__busy",
                indeterminate=True,
                absolute=True,
                height=3,
                color="red-darken-1",
                location="bottom",
            )
            with html.Div(
                classes="position-absolute",
                style="pointer-events: none; left: -5px;",
            ):
                v3.VIcon("mdi-chevron-left", v_if="show_drawer")
                v3.VIcon("mdi-chevron-right", v_else=True)
            html.Img(
                v_if="theme === 'dark'",
                src=f"{module.BASENAME}/assets/tomviz/logo-dark.png",
                height="100%",
                classes="pa-2 ml-1",
                click="show_drawer = !show_drawer",
            )
            html.Img(
                v_else=True,
                src=f"{module.BASENAME}/assets/tomviz/logo.png",
                height="100%",
                classes="pa-2 ml-1",
                click="show_drawer = !show_drawer",
            )
            v3.VSpacer()

            # Data open
            ui.toolbar_btn(
                f"{module.BASENAME}/assets/data/open.svg",
                v_tooltip_bottom="'Open data file'",
                click="tomviz_file_loader = true",
            )

            v3.VDivider(vertical=True, classes="mr-2")

            # Transform picker (appends at the tip port)
            ui.toolbar_btn(
                icon="mdi-shape-plus-outline",
                v_tooltip_bottom="'Add transform'",
                disabled=("!tip_port_id",),
                click="select_transform = true",
            )

            v3.VDivider(vertical=True, classes="mr-2")

            # Representations
            for rep_type in RepresentationType:
                ui.toolbar_btn(
                    rep_type.icon,
                    v_tooltip_bottom=f"'{rep_type.label}'",
                    disabled=("!active_view_id || !tip_port_id",),
                    click=(
                        self.ctx.pipeline.add_sink,
                        f"[active_view_id, '{rep_type.name}']",
                    ),
                )

            v3.VDivider(vertical=True, classes="mr-2")

            # Settings
            ui.toolbar_btn(
                f"{module.BASENAME}/assets/icons/Settings.svg",
                v_tooltip_bottom="'Edit settings'",
                click="show_settings = true",
            )

            v3.VSpacer()

            ui.toolbar_btn(
                icon="mdi-plus",
                v_tooltip_bottom="'Add View'",
                click=self.ctx.pipeline.add_view,
            )

    def fake_busy(self):
        time.sleep(2)
