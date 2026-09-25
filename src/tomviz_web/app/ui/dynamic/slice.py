from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app.pipeline import RepresentationType

NAME = RepresentationType.SLICE.name
TEMPLATE = f"rep_{NAME}"


class SliceRepresentationUI(DivLayout):
    def __init__(self, server, template_name=TEMPLATE):
        super().__init__(server, template_name=template_name)

        with (
            self,
            dataclass.Provider(name="rep", instance=("active_representation_id",)),
        ):
            with html.Div(classes="pa-2"):
                v3.VSelect(
                    label="Slice direction",
                    v_model="rep.SliceDirection",
                    items=("rep.SliceDirections",),
                    density="comfortable",
                    hide_details=True,
                    variant="solo-filled",
                    flat=True,
                )
                with html.Div(classes="d-flex justify-space-between mt-2 mx-1"):
                    v3.VLabel("Slice index")
                    v3.VLabel("{{ rep.Slice }}")
                v3.VSlider(
                    v_model="rep.Slice",
                    min=0,
                    step=1,
                    max=("rep.SliceMax",),
                    hide_details=True,
                    density="comfortable",
                )
                with html.Div(classes="d-flex justify-space-between mb-2 mx-1"):
                    v3.VLabel("0", classes="text-caption")
                    v3.VLabel("{{ rep.SliceMax }}", classes="text-caption")
                v3.VCheckbox(
                    label="Interpolate",
                    v_model="rep.Interpolate",
                    density="comfortable",
                    hide_details=True,
                    flat=True,
                )
                v3.VCheckbox(
                    label="Custom Color Opacity",
                    v_model="rep.use_internal_color_opacity",
                    density="comfortable",
                    hide_details=True,
                    flat=True,
                )


UI = SliceRepresentationUI
