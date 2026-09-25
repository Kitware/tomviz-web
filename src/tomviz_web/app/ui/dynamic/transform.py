from trame.app.dataclass import get_instance
from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

NAME = "transform"
TEMPLATE = "transform"


class TransformUI(DivLayout):
    """Parameter panel of the active transform node: the generated GUI of
    its ``parameters`` model. Edits are staged in the mirror until Apply
    pushes them to the node (Reset drops them)."""

    def __init__(self, server, template_name=TEMPLATE):
        super().__init__(server, template_name=template_name)

        with (
            self,
            html.Div(classes="pa-2"),
            dataclass.Provider(name="transform", instance=("active_data_id",)),
        ):
            dataclass.Gui(instance=("transform.parameters._id",))
            with html.Div(classes="d-flex ga-2 mt-1"):
                v3.VSpacer()
                v3.VBtn(
                    "Reset",
                    classes="text-none",
                    density="compact",
                    variant="text",
                    disabled=("!transform.parameters_dirty",),
                    click=(self.reset, "[transform._id]"),
                )
                v3.VBtn(
                    "Apply",
                    classes="text-none",
                    density="compact",
                    variant="tonal",
                    color="primary",
                    disabled=("!transform.parameters_dirty",),
                    click=(self.apply, "[transform._id]"),
                )

    def apply(self, model_id):
        model = get_instance(model_id)
        if model is not None:
            model.apply_parameters()

    def reset(self, model_id):
        model = get_instance(model_id)
        if model is not None:
            model.reset_parameters()


UI = TransformUI
