from __future__ import annotations

from trame.ui.html import DivLayout
from trame.widgets import html
from trame.widgets import vtk as vtkw
from trame.widgets import vuetify3 as v3

from tomviz_trame.app.data_model import ViewModel
from tomviz_trame.app.pipeline.vtk.view import View

VIEW_COLORS = [
    "#2196F3",  # blue
    "#4CAF50",  # green
    # "#009688",  # teal
    "#FF9800",  # orange
    "#FFEB3B",  # yellow
    "#607D8B",  # blue-gray
]


def color_generator():
    while True:
        yield from VIEW_COLORS


COLOR_GENERTOR = color_generator()


def next_color():
    return next(COLOR_GENERTOR)


class RenderWindow(DivLayout):
    def __init__(self, server, **kwargs):
        self.vtk_view = View()

        super().__init__(server, template_name=f"view_{self.vtk_view.id}")
        self.local_state = ViewModel(self.server, color=next_color())
        self.style = f"background: {self.local_state.color};"

        # Make new view active by default
        self.state.active_view_id = self.local_state._id

        self.root.classes = "h-100"

        with (
            self,
            v3.VCard(tile=True, classes="w-100 h-100 position-relative", **kwargs),
        ):
            with self.local_state.provide_as("rw_data"):
                self.window = vtkw.VtkRemoteView(
                    self.vtk_view.render_window,
                    interactive_ratio=1,
                    interactor_events=("['EndAnimation', 'LeftButtonPress']",),
                    LeftButtonPress="active_view_id = rw_data._id",
                )
                # The active view wears a frame in its color (the color the
                # pipeline widget shows on the sinks drawing in it).
                html.Div(
                    v_show=(f"active_view_id === '{self.local_state._id}'",),
                    classes="position-absolute",
                    style=(
                        f"inset: 0; border: 3px solid {self.local_state.color}; "
                        "pointer-events: none; z-index: 1;"
                    ),
                )
                with v3.VCard(
                    style=(
                        "`right:1rem;top:1rem;z-index:1;width:${rw_data.expanded ? '4.5' : '2.25'}rem;`",  # background:${rw_data.color}
                    ),
                    classes="position-absolute",
                    rounded="lg",
                ):
                    with v3.VRow(
                        dense=True,
                        classes="pa-1",
                        v_if="rw_data_available",
                    ):
                        for icon, action, add_on, add_on_btn in self.tools:
                            with v3.VCol(
                                cols=("rw_data.expanded ? 6 : 12",),
                                align_self="center",
                                classes="d-flex justify-center",
                                **add_on,
                            ):
                                v3.VBtn(
                                    icon=icon,
                                    density="compact",
                                    click=action,
                                    **{
                                        "classes": "rounded",
                                        "variant": "plain",
                                        **add_on_btn,
                                    },
                                )

                    v3.VBtn(
                        icon=(
                            "rw_data.expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'",
                        ),
                        block=True,
                        tile=True,
                        variant="plain",
                        density="compact",
                        size="x-small",
                        click="rw_data.expanded = !rw_data.expanded",
                    )

        # Attach pv + widget on state
        self.local_state.vtk_view = self.vtk_view
        self.local_state.widget_view = self.window

    @property
    def tools(self):
        ALWAYS = EMPTY = {}
        EXPANDED = {"v_if": "rw_data.expanded"}
        return [
            ("mdi-crop-free", self.reset_camera, ALWAYS, EMPTY),
            (
                ("rw_data?.interactive_3d ? 'mdi-rotate-orbit' : 'mdi-pan'",),
                "rw_data.interactive_3d = !rw_data.interactive_3d",
                EXPANDED,
                EMPTY,
            ),
            (
                "mdi-axis",
                "rw_data.orientation_axes_visibility = !rw_data.orientation_axes_visibility",
                EXPANDED,
                {
                    "classes": "rounded border-thin",
                    "variant": (
                        "rw_data.orientation_axes_visibility ? 'tonal' : 'plain'",
                    ),
                },
            ),
            (
                "mdi-image-filter-center-focus",
                "rw_data.center_axes_visibility = !rw_data.center_axes_visibility",
                EXPANDED,
                {
                    "classes": "rounded border-thin",
                    "variant": ("rw_data.center_axes_visibility ? 'tonal' : 'plain'",),
                },
            ),
            ("mdi-rotate-left", (self.rotate, "[90]"), EXPANDED, EMPTY),
            ("mdi-rotate-right", (self.rotate, "[-90]"), EXPANDED, EMPTY),
            (
                "mdi-axis-arrow",
                (self.reset_camera_orientation, "['apply_isometric_view']"),
                EXPANDED,
                EMPTY,
            ),
            (
                "mdi-axis-x-arrow",
                (
                    self.reset_camera_orientation,
                    "['reset_active_camera_to_positive_x']",
                ),
                EXPANDED,
                EMPTY,
            ),
            (
                "mdi-axis-y-arrow",
                (
                    self.reset_camera_orientation,
                    "['reset_active_camera_to_positive_y']",
                ),
                EXPANDED,
                EMPTY,
            ),
            (
                "mdi-axis-z-arrow",
                (
                    self.reset_camera_orientation,
                    "['reset_active_camera_to_positive_z']",
                ),
                EXPANDED,
                EMPTY,
            ),
        ]

    def reset_camera(self):
        self.window.reset_camera()

    def render(self):
        self.window.update()

    def rotate(self, angle):
        self.vtk_view.adjust_roll(angle)
        self.render()

    def reset_camera_orientation(self, action):
        getattr(self.vtk_view, action)()
        self.reset_camera()

    @property
    def tpl_name(self):
        return f"view_{self.vtk_id}"

    @property
    def vtk_id(self):
        return self.vtk_view.id
