from trame.ui.html import DivLayout
from trame.widgets import dataclass, html

from tomviz_web.app.pipeline import RepresentationType
from tomviz_web.app.ui.dynamic._widgets import slider

NAME = RepresentationType.MOLECULE.name
TEMPLATE = f"rep_{NAME}"


class MoleculeRepresentationUI(DivLayout):
    def __init__(self, server, template_name=TEMPLATE):
        super().__init__(server, template_name=template_name)

        with (
            self,
            dataclass.Provider(name="rep", instance=("active_representation_id",)),
        ):
            with html.Div(classes="pa-2"):
                slider(
                    "Ball Radius",
                    "BallRadius",
                    0,
                    4,
                    0.01,
                    2,
                    tooltip="Scale of each element's atomic radius.",
                )
                slider("Stick Radius", "StickRadius", 0, 2, 0.005, 3)


UI = MoleculeRepresentationUI
