from trame.app import TrameApp
from trame.decorators import life_cycle
from trame.ui.vuetify3 import VAppLayout
from trame.widgets import dockview, html
from trame.widgets import vtk as vtkw
from trame.widgets import vuetify3 as v3

from tomviz_trame.app import cli, module, ui
from tomviz_trame.app.catalog import Catalog
from tomviz_trame.app.pipeline import PipelineManager
from tomviz_trame.app.settings import Settings
from tomviz_trame.app.ui.colormaps import generate_colormaps

DRAWER_WIDTH = 350
# The .tomviz-drawer padding and column gap in style.css, so the two-column
# drawer gives each column exactly the single column's content width.
DRAWER_PADDING = 8
DRAWER_COLUMN_GAP = 8
DRAWER_CONTENT_WIDTH = DRAWER_WIDTH - 2 * DRAWER_PADDING
DRAWER_WIDTH_COLUMNS = 2 * DRAWER_CONTENT_WIDTH + 2 * DRAWER_PADDING + DRAWER_COLUMN_GAP


class Tomviz(TrameApp):
    def __init__(self, server=None):
        super().__init__(server, client_type="vue3", ctx_name="tomviz")
        self.server.enable_module(module)
        args = cli.configure(self.server.cli)

        # Global helper
        self.ctx.pipeline = PipelineManager(server=self.server)
        self.ctx.colormaps = generate_colormaps(self.server)
        self.state.colormaps_id = self.ctx.colormaps._id
        self.state.show_color_opacity = True
        # Remembered preferences (drawer_columns, ...): ~/.tomviz/settings.json
        self.ctx.settings = Settings(
            server=self.server, config_file=args.settings, read_only=args.read_only
        )
        self.ctx.catalog = Catalog(
            server=self.server,
            config_file=args.catalog,
            read_only=args.read_only,
        )

        # --hot-reload arg optional logic
        if self.server.hot_reload:
            self.server.controller.on_server_reload.add(self._build_ui)

        # build ui
        self._build_ui()

    @life_cycle.client_connected
    def on_client_connected(self, **_):
        self.ctx.pipeline.refresh_views()

    def _build_ui(self, **_):
        self.state.trame__title = "tomviz"
        self.state.trame__favicon = f"{module.BASENAME}/assets/tomviz/favicon.png"

        if self.server.hot_reload:
            ui.reload(ui)

        # Create UI for all representation types

        ui.initialize_dynamic_ui(self.server)
        vtkw.initialize(self.server)

        with VAppLayout(
            self.server,
            full_height=True,
            theme=("theme", "light"),
        ) as self.ui:
            if self.server.hot_reload:
                v3.VBtn(
                    icon="mdi-refresh",
                    classes="position-absolute rounded",
                    density="comfortable",
                    style="right:1rem;bottom:1rem;z-index:10;",
                    click=self.server.controller.on_server_reload,
                )

            # Dialogs
            ui.FileLoader()
            ui.SettingsDialog()

            # Toolbar
            ui.Toolbar()

            # Left Drawer. `drawer_columns` (settings dialog, remembered in the
            # settings file) picks the layout: stacked sections, or two
            # columns with the pipeline on the left and the color map and
            # properties on the right. Both share the same widgets; only CSS
            # (style.css, .tomviz-drawer) differs.
            with v3.VNavigationDrawer(
                v_model=("show_drawer", True),
                width=(
                    f"drawer_columns ? {DRAWER_WIDTH_COLUMNS} : {DRAWER_WIDTH}",
                    DRAWER_WIDTH_COLUMNS if self.state.drawer_columns else DRAWER_WIDTH,
                ),
                floating=True,
                disable_resize_watcher=True,
                permanent=True,
            ):
                with html.Div(
                    v_if=("select_transform", False),
                    classes="px-2 pt-2 d-flex flex-column",
                    style="max-height: calc(100vh - 48px)",
                ):
                    ui.TransformSelection()
                with html.Div(
                    classes=(
                        "drawer_columns ? 'tomviz-drawer tomviz-drawer--columns' : 'tomviz-drawer'",
                    ),
                    v_else=True,
                ):
                    ui.PipelineSection()
                    ui.ColorOpacitySection()
                    ui.PropertiesSections()

            # Main content
            with v3.VMain():
                dockview.DockView(
                    ctx_name="dock_view",
                    theme=("theme === 'light' ? 'Light' : 'Dark'",),
                    active_panel=(self.ctx.pipeline.activate_panel, "[$event]"),
                )

        # Add a view if none defined
        if not self.ctx.pipeline.views:
            self.ctx.pipeline.add_view()
