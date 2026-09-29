from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app.pipeline import RepresentationType
from tomviz_web.app.pipeline.representations.slice import THICK_SLICE_MODES
from tomviz_web.app.ui.dynamic._widgets import (
    COMPACT,
    plane_direction,
    plane_fields,
)

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
                v3.VCheckbox(
                    label="Color Map Data",
                    v_model="rep.MapScalars",
                    **COMPACT,
                )
                v3.VCheckbox(
                    label="Custom Color Opacity",
                    v_model="rep.use_internal_color_opacity",
                    **COMPACT,
                )
                v3.VDivider(classes="my-2")

                plane_direction("Slice")

                v3.VNumberInput(
                    label="Slice Thickness",
                    v_model="rep.SliceThickness",
                    # Bound, not literal: a literal reaches Vuetify as a string
                    # and the step buttons would concatenate it.
                    min=("1",),
                    max=("Math.max(rep.SliceMax, 1)",),
                    step=("2",),
                    control_variant="split",
                    variant="solo-filled",
                    flat=True,
                    classes="mt-2",
                    **COMPACT,
                )
                v3.VSelect(
                    label="Aggregation",
                    v_model="rep.ThickSliceMode",
                    items=("slice_thick_slice_modes", list(THICK_SLICE_MODES)),
                    variant="solo-filled",
                    flat=True,
                    classes="mt-2",
                    **COMPACT,
                )

                with html.Div(classes="d-flex justify-space-between mt-2 mx-1"):
                    v3.VLabel("Opacity")
                    v3.VLabel("{{ rep.Opacity.toFixed(2) }}")
                v3.VSlider(
                    v_model="rep.Opacity",
                    min=0,
                    max=1,
                    step=0.01,
                    hide_details=True,
                    density="comfortable",
                )
                v3.VCheckbox(
                    label="Interpolate Texture",
                    v_model="rep.Interpolate",
                    **COMPACT,
                )
                v3.VCheckbox(
                    label="Show Arrow",
                    v_model="rep.ShowArrow",
                    **COMPACT,
                )

                plane_fields()


UI = SliceRepresentationUI
