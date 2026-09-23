from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

NAME = "data_info"
TEMPLATE = NAME

# Rows per payload family: (row label, PortDataModel field)
ROWS = {
    "image": [
        ("Type", "port_type"),
        ("Dimensions", "dimensions"),
        ("Spacing", "spacing"),
        ("Bounds", "bounds"),
        ("Memory", "memory"),
    ],
    "table": [
        ("Type", "port_type"),
        ("Columns", "column_names"),
        ("Rows", "num_rows"),
    ],
    "molecule": [
        ("Type", "port_type"),
        ("Atoms", "num_atoms"),
        ("Bonds", "num_bonds"),
        ("Elements", "elements"),
    ],
}


class DataInformation(DivLayout):
    """What is on the active output port, with rows for its payload
    family. ``port`` is the ``OutputPortModel``, ``info`` its ``data``."""

    def __init__(self, server, template_name=NAME):
        super().__init__(server, template_name=template_name)

        with (
            self,
            dataclass.Provider(name="port", instance=("active_port_id",)),
            dataclass.Provider(
                name="info", instance=("port?.data?._id ?? port?.data ?? null",)
            ),
        ):
            with html.Div(v_if="port?.has_data"):
                with v3.VTable(
                    striped="even",
                    density="compact",
                ):
                    with html.Tbody():
                        for family, rows in ROWS.items():
                            with v3.Template(v_if=f"info?.family === '{family}'"):
                                for label, field in rows:
                                    with html.Tr():
                                        html.Td(label)
                                        html.Td("{{ info.%s }}" % (field))  # noqa: UP031


UI = DataInformation
