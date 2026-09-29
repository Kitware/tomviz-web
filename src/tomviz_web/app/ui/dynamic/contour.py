from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app.pipeline import RepresentationType
from tomviz_web.app.ui.dynamic._widgets import (
    COMPACT,
    FILLED,
    array_select,
    color_picker,
    slider,
    surface_mode_select,
)

NAME = RepresentationType.CONTOUR.name
TEMPLATE = f"rep_{NAME}"


class ContourRepresentationUI(DivLayout):
    def __init__(self, server, template_name=TEMPLATE):
        super().__init__(server, template_name=template_name)

        with (
            self,
            dataclass.Provider(name="rep", instance=("active_representation_id",)),
        ):
            with html.Div(classes="pa-2"):
                v3.VCheckbox(
                    label="Custom Color Opacity",
                    v_model="rep.use_internal_color_opacity",
                    **COMPACT,
                )
                v3.VCheckbox(
                    label="Color Map Data",
                    v_model="rep.MapScalars",
                    disabled=("rep.UseSolidColor",),
                    **COMPACT,
                )
                with html.Div(classes="d-flex align-center"):
                    v3.VCheckbox(
                        label="Select Color",
                        v_model="rep.UseSolidColor",
                        **COMPACT,
                    )
                    color_picker("", "Color", disabled="!rep.UseSolidColor")
                array_select(
                    "Contour by",
                    "ContourBy",
                    tooltip="The array the surface is extracted from. The "
                    "color map's array colors it.",
                )

                # The iso value: a slider over the contoured array's range,
                # and a field for an exact value
                step = "(rep.IsoRange[1] - rep.IsoRange[0]) / 1000 || 1"
                v3.VNumberInput(
                    label="Value",
                    v_model="rep.IsoValue",
                    min=("rep.IsoRange[0]",),
                    max=("rep.IsoRange[1]",),
                    step=(step,),
                    precision=("null",),  # no rounding
                    control_variant="hidden",
                    classes="mt-2",
                    **FILLED,
                )
                v3.VSlider(
                    v_model="rep.IsoValue",
                    min=("rep.IsoRange[0]",),
                    max=("rep.IsoRange[1]",),
                    step=(step,),
                    **COMPACT,
                )

                surface_mode_select()
                slider("Opacity", "Opacity", 0, 1, 0.01, 2)

                v3.VLabel("Lighting", classes="text-subtitle-2 mt-2 mx-1")
                slider("Ambient", "Ambient", 0, 1, 0.01, 2)
                slider("Diffuse", "Diffuse", 0, 1, 0.01, 2)
                slider("Specular", "Specular", 0, 1, 0.01, 2)
                slider("Sp. Power", "SpecularPower", 1, 150, 1, 0)


UI = ContourRepresentationUI
