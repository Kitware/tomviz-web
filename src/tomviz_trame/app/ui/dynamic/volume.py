from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_trame.app.pipeline import RepresentationType

NAME = RepresentationType.VOLUME.name
TEMPLATE = f"rep_{NAME}"


class VolumeRepresentationUI(DivLayout):
    def __init__(self, server, template_name=TEMPLATE):
        super().__init__(server, template_name=template_name)

        with (
            self,
            dataclass.Provider(name="rep", instance=("active_representation_id",)),
        ):
            with html.Div(classes="pa-2"):
                # Volume settings

                with v3.VRow():
                    with v3.VCol():
                        v3.VSelect(
                            label="Interpolation",
                            v_model="rep.InterpolationType",
                            hide_details=True,
                            density="comfortable",
                            items=(
                                "volume_interpolation_types",
                                [
                                    "Nearest",
                                    "Linear",
                                    "Cubic",
                                ],
                            ),
                            variant="solo-filled",
                            flat=True,
                        )
                    with v3.VCol():
                        v3.VSwitch(
                            v_model="rep.Shade",
                            hide_details=True,
                            density="comfortable",
                            label=("`Shade ${rep.Shade ? 'On' : 'Off'}`",),
                            true_icon="mdi-brightness-6",
                            false_icon="mdi-white-balance-sunny",
                            inset=True,
                        )
                with html.Div(classes="d-flex align-center mt-1"):
                    v3.VLabel("Global Illumination Reach")
                    v3.VSpacer()
                    v3.VLabel("{{ rep.GlobalIlluminationReach.toFixed(2) }}")
                v3.VSlider(
                    v_model="rep.GlobalIlluminationReach",
                    hide_details=True,
                    density="comfortable",
                    min=0,
                    max=1,
                    step=0.01,
                )

                with html.Div(classes="d-flex align-center mt-1"):
                    v3.VLabel("Volumetric Scattering Blending")
                    v3.VSpacer()
                    v3.VLabel("{{ rep.VolumetricScatteringBlending.toFixed(1) }}")
                v3.VSlider(
                    v_model="rep.VolumetricScatteringBlending",
                    hide_details=True,
                    density="comfortable",
                    min=0,
                    max=2,
                    step=0.1,
                )

                with html.Div(classes="d-flex align-center mt-1"):
                    v3.VLabel("Volume Anisotropy")
                    v3.VSpacer()
                    v3.VLabel("{{ rep.VolumeAnisotropy.toFixed(1) }}")
                v3.VSlider(
                    v_model="rep.VolumeAnisotropy",
                    hide_details=True,
                    density="comfortable",
                    min=-1,
                    max=1,
                    step=0.1,
                )

                v3.VCheckbox(
                    label="Custom Color Opacity",
                    v_model="rep.use_internal_color_opacity",
                    density="comfortable",
                    hide_details=True,
                    flat=True,
                )


UI = VolumeRepresentationUI
