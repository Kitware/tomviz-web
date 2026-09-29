from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app.pipeline import RepresentationType

NAME = RepresentationType.OUTLINE.name
TEMPLATE = f"rep_{NAME}"


class OutlineRepresentationUI(DivLayout):
    def __init__(self, server, template_name=TEMPLATE):
        super().__init__(server, template_name=template_name)

        with (
            self,
            dataclass.Provider(name="rep", instance=("active_representation_id",)),
        ):
            with html.Div(classes="pa-2"):
                with html.Div(classes="d-flex align-center mx-1"):
                    v3.VLabel("Color")
                    v3.VSpacer()
                    with v3.VMenu(close_on_content_click=False):
                        with v3.Template(v_slot_activator="{ props }"):
                            v3.VBtn(
                                v_bind="props",
                                color=("rep.Color",),
                                size="small",
                                variant="flat",
                                classes="border-thin",
                                width=48,
                            )
                        v3.VColorPicker(
                            v_model="rep.Color",
                            modes=("['rgb', 'hex']",),
                            mode="hex",
                            show_swatches=False,
                        )
                v3.VCheckbox(
                    label="Show Axes",
                    v_model="rep.ShowGridAxes",
                    density="comfortable",
                    hide_details=True,
                )
                v3.VCheckbox(
                    label="Show Grid",
                    v_model="rep.ShowGrid",
                    disabled=("!rep.ShowGridAxes",),
                    density="comfortable",
                    hide_details=True,
                )
                v3.VCheckbox(
                    label="Custom Axes Titles",
                    v_model="rep.UseCustomAxesTitles",
                    disabled=("!rep.ShowGridAxes",),
                    density="comfortable",
                    hide_details=True,
                )
                with html.Div(
                    v_if="rep.ShowGridAxes && rep.UseCustomAxesTitles",
                    classes="d-flex flex-column ga-2 mt-1",
                ):
                    for axis in "XYZ":
                        v3.VTextField(
                            label=axis,
                            v_model=f"rep.{axis}Title",
                            density="compact",
                            hide_details=True,
                            variant="solo-filled",
                            flat=True,
                        )


UI = OutlineRepresentationUI
