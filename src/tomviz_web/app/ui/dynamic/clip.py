from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app import data_model
from tomviz_web.app.pipeline import RepresentationType
from tomviz_web.app.ui.dynamic._widgets import (
    COMPACT,
    color_picker,
    plane_direction,
    plane_fields,
    slider,
)

NAME = RepresentationType.CLIP.name
TEMPLATE = f"rep_{NAME}"


def invert(representation_id, value):
    model = data_model.get_instance(representation_id)
    if model is not None:
        model.invert(value)


class ClipRepresentationUI(DivLayout):
    def __init__(self, server, template_name=TEMPLATE):
        super().__init__(server, template_name=template_name)

        with (
            self,
            dataclass.Provider(name="rep", instance=("active_representation_id",)),
        ):
            with html.Div(classes="pa-2"):
                html.Div(
                    "Cuts away the other visualizations of its group, in every "
                    "view, keeping the side the arrow points to.",
                    classes="text-caption mx-1",
                )
                slider("Opacity", "Opacity", 0, 1, 0.01, 2)
                color_picker("Select Color", "Color")
                with html.Div(classes="d-flex"):
                    v3.VCheckbox(
                        label="Show Plane",
                        v_model="rep.ShowPlane",
                        title="Hide the plane; it still clips.",
                        **COMPACT,
                    )
                    v3.VCheckbox(
                        label="Show Arrow",
                        v_model="rep.ShowArrow",
                        disabled=("!rep.ShowPlane",),
                        **COMPACT,
                    )
                v3.VCheckbox(
                    label="Invert Plane Direction",
                    model_value=("rep.InvertPlane",),
                    update_modelValue=(invert, "[active_representation_id, $event]"),
                    **COMPACT,
                )
                v3.VDivider(classes="my-2")
                plane_direction("Plane")
                plane_fields()


UI = ClipRepresentationUI
