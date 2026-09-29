from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app.pipeline import RepresentationType
from tomviz_web.app.ui.dynamic._widgets import (
    COMPACT,
    FILLED,
    array_select,
    slider,
    surface_mode_select,
)

NAME = RepresentationType.THRESHOLD.name
TEMPLATE = f"rep_{NAME}"


def bound(label, field):
    """An exact value and a slider over the thresholded array's range."""
    step = "(rep.ScalarRange[1] - rep.ScalarRange[0]) / 1000 || 1"
    v3.VNumberInput(
        label=label,
        v_model=f"rep.{field}",
        min=("rep.ScalarRange[0]",),
        max=("rep.ScalarRange[1]",),
        step=(step,),
        precision=("null",),  # no rounding
        control_variant="hidden",
        classes="mt-2",
        **FILLED,
    )
    v3.VSlider(
        v_model=f"rep.{field}",
        min=("rep.ScalarRange[0]",),
        max=("rep.ScalarRange[1]",),
        step=(step,),
        **COMPACT,
    )


class ThresholdRepresentationUI(DivLayout):
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
                    **COMPACT,
                )
                array_select(
                    "Threshold by",
                    "ThresholdBy",
                    tooltip="The array whose range selects the voxels. The color "
                    "map's array colors them.",
                )
                bound("Minimum", "Minimum")
                bound("Maximum", "Maximum")
                surface_mode_select(label="Representation")
                slider("Opacity", "Opacity", 0, 1, 0.01, 2)
                slider("Specular", "Specular", 0, 1, 0.01, 2)


UI = ThresholdRepresentationUI
