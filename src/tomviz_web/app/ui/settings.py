from trame.widgets import html
from trame.widgets import vuetify3 as v3


class SettingsDialog(v3.VDialog):
    def __init__(self):
        super().__init__(
            v_model=("show_settings", False),
            contained=True,
        )

        with self:
            with v3.VCard(
                classes="mx-auto",
                rounded="lg",
                max_height="80vh",
                max_width="800px",
                width="80vw",
            ):
                with v3.VCardItem(title="Settings", classes=""):
                    with v3.Template(v_slot_prepend=True):
                        v3.VSwitch(
                            # label=("`Theme ${theme}`",),
                            v_model="theme",
                            true_value="light",
                            true_icon="mdi-weather-sunny",
                            false_value="dark",
                            false_icon="mdi-weather-night",
                            inset=True,
                            density="comfortable",
                            hide_details=True,
                        )
                    with v3.Template(v_slot_append=True):
                        if self.server.hot_reload:
                            v3.VBtn(
                                icon="mdi-refresh",
                                click=self.ctrl.on_server_reload,
                                density="compact",
                                variant="plain",
                                classes="mx-2",
                            )

                        v3.VBtn(
                            icon="mdi-close",
                            density="compact",
                            variant="plain",
                            click="show_settings = false",
                        )
                v3.VDivider()
                with v3.VCardText():
                    v3.VSwitch(
                        v_model=("drawer_columns", True),
                        label="Two-column drawer (pipeline left, color map and properties right)",
                        inset=True,
                        density="comfortable",
                        hide_details=True,
                        classes="mb-2",
                    )
                    html.Label("Catalog search paths", classes="text-subtitle-2")

                    with v3.VList(
                        density="compact",
                        items=("settings_catalog_paths", ["~/.tomviz/catalog"]),
                        border="thin",
                        rounded=True,
                        classes="my-1",
                    ):
                        with v3.Template(v_slot_item="{ props }"):
                            with v3.VListItem(title=("props.title",)):
                                with v3.Template(v_slot_append=True):
                                    v3.VBtn(
                                        icon="mdi-trash-can-outline",
                                        density="compact",
                                        variant="plain",
                                        click="settings_catalog_paths = settings_catalog_paths.filter(v => v !== props.title)",
                                    )
                    v3.VTextField(
                        v_model=("settings_catalog_path", ""),
                        append_inner_icon="mdi-plus",
                        variant="outlined",
                        density="compact",
                        hide_details=True,
                        click_appendInner="settings_catalog_paths = [...settings_catalog_paths, settings_catalog_path]; settings_catalog_path = '';",
                    )
