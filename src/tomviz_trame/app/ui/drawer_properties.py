from trame.widgets import client, html
from trame.widgets import vuetify3 as v3


class PropertiesSections(html.Div):
    """Options and information about the selected pipeline element: the
    dynamic templates the manager lists in ``property_templates`` (a
    transform's parameters, a sink's settings, an output port's data)."""

    def __init__(self):
        super().__init__(classes="tomviz-drawer__properties")

        with self:
            v3.VBtn(
                prepend_icon=(
                    "show_properties ? 'mdi-chevron-down' : 'mdi-chevron-up'",
                ),
                text="Properties",
                click="show_properties = !show_properties",
                classes="w-100 text-none mb-1",
                variant="tonal",
                spaced="end",
            )
            with v3.VExpandTransition():
                with v3.VCard(
                    classes="border-thin overflow-auto flex-fill mb-2",
                    flat=True,
                    variant="flat",
                    v_show=("show_properties", True),
                ):
                    client.ServerTemplate(
                        v_for="tpl in property_templates",
                        key="tpl",
                        name=("tpl",),
                    )
