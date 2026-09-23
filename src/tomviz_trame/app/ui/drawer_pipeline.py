"""The pipeline section of the drawer: the desktop's controls row (execution
status, pause and cancel, focus mode, default persistence), the pipeline
widget and its context menu. The widget renders the ``PipelineModel``; its
events either write the models directly (selection, expansion, visibility)
or call the manager."""

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from tomviz_trame.widgets import PipelineWidget

PERSISTENCE_CHOICES = (
    ("memory", "Persist in memory", "mdi-memory"),
    ("disk", "Persist on disk", "mdi-harddisk"),
    ("transient", "Transient", "mdi-timer-sand"),
)
PERSISTENCE_ICON = (
    "transform_persistence_default === 'disk' ? 'mdi-harddisk' : "
    "transform_persistence_default === 'transient' ? 'mdi-timer-sand' : 'mdi-memory'"
)
EXECUTION_ICON = (
    "pipeline_executing ? 'mdi-stop' : pipeline_paused ? 'mdi-play' : 'mdi-pause'"
)
EXECUTION_TOOLTIP = (
    "pipeline_executing ? 'Cancel execution' : pipeline_paused ? "
    "'Resume automatic execution' : 'Pause automatic execution'"
)
STATUS_TEXT = (
    "pipeline_stopping ? 'Stopping...' : "
    "pipeline_paused ? 'Automatic execution paused' : ''"
)


class PipelineSection(html.Div):
    def __init__(self):
        super().__init__(classes="tomviz-drawer__pipeline")

        self.state.setdefault("pipeline_menu", None)
        self.state.setdefault("pipeline_menu_show", False)
        self.state.setdefault("pipeline_dimming", False)

        with self:
            v3.VBtn(
                prepend_icon=("show_pipeline ? 'mdi-chevron-down' : 'mdi-chevron-up'",),
                text="Pipelines",
                click="show_pipeline = !show_pipeline",
                classes="w-100 text-none mb-1",
                variant="tonal",
                spaced="end",
            )
            with v3.VExpandTransition():
                # A flex column so the widget fills the card: a click on any
                # empty spot of the card lands on the widget and clears the
                # selection.
                with v3.VCard(
                    classes="border-thin overflow-auto flex-fill mb-2 d-flex flex-column",
                    flat=True,
                    variant="flat",
                    v_show=("show_pipeline", True),
                ):
                    self._controls()
                    with self.ctx.pipeline.model.provide_as("pipeline"):
                        PipelineWidget(
                            nodes=("pipeline.nodes",),
                            active_node=("pipeline.active_node",),
                            tip_port=("tip_port_id",),
                            locked=("pipeline_executing", False),
                            dimming=("pipeline_dimming", False),
                            update_active_node="pipeline.active_node = $event",
                            toggle_expanded="$event.expanded = !$event.expanded",
                            toggle_visibility="$event.Visibility = !$event.Visibility",
                            toggle_breakpoint=(self.toggle_breakpoint, "[$event._id]"),
                            leave_group=(self.ctx.pipeline.leave_group, "[$event._id]"),
                            link_request=(
                                self.ctx.pipeline.create_link,
                                "[$event.output._id, $event.input._id]",
                            ),
                            contextmenu=(
                                self.open_menu,
                                "[$event.kind, $event.id, $event.x, $event.y]",
                            ),
                            delete=(self.delete, "[$event.kind, $event.id]"),
                            dblclick=(self.ctx.pipeline.edit_node, "[$event._id]"),
                        )

            # The context menu the widget asks for: the manager decides the
            # actions, the menu only shows them.
            with v3.VMenu(
                v_model=("pipeline_menu_show", False),
                target=("[pipeline_menu?.x ?? 0, pipeline_menu?.y ?? 0]",),
                location="bottom start",
                close_on_content_click=True,
            ):
                with v3.VList(density="compact", slim=True):
                    v3.VListItem(
                        v_for="action in pipeline_menu?.actions ?? []",
                        key="action.id",
                        title=("action.title",),
                        prepend_icon=("action.icon",),
                        append_icon=("action.checked ? 'mdi-check' : undefined",),
                        disabled=("action.disabled",),
                        click=(self.run_action, "[action.id]"),
                    )

    def _controls(self):
        """The row above the widget, after the desktop's controls widget."""
        manager = self.ctx.pipeline
        with html.Div(
            classes="d-flex align-center px-1 ga-1 border-b-thin flex-grow-0",
            style="min-height: 32px",
        ):
            v3.VProgressCircular(
                v_show=("pipeline_executing", False),
                indeterminate=True,
                size=14,
                width=2,
                classes="mx-1",
            )
            html.Span(
                f"{{{{ {STATUS_TEXT} }}}}",
                classes="text-caption text-medium-emphasis text-truncate",
            )
            v3.VSpacer()
            v3.VBtn(
                icon=(EXECUTION_ICON,),
                size="small",
                variant="text",
                density="comfortable",
                v_tooltip_bottom=(EXECUTION_TOOLTIP,),
                click=self.execution_button,
            )
            v3.VDivider(vertical=True, classes="mx-1 my-1")
            v3.VBtn(
                icon=("pipeline_dimming ? 'mdi-filter' : 'mdi-filter-off-outline'",),
                size="small",
                variant="text",
                density="comfortable",
                v_tooltip_bottom="'Focus mode: fade what is far from the selection'",
                click="pipeline_dimming = !pipeline_dimming",
            )
            v3.VDivider(vertical=True, classes="mx-1 my-1")
            with v3.VMenu():
                with v3.Template(v_slot_activator="{ props }"):
                    v3.VBtn(
                        v_bind="props",
                        icon=(PERSISTENCE_ICON,),
                        size="small",
                        variant="text",
                        density="comfortable",
                        v_tooltip_bottom="'Default persistence of transform outputs'",
                    )
                with v3.VList(density="compact", slim=True):
                    for value, title, icon in PERSISTENCE_CHOICES:
                        v3.VListItem(
                            title=title,
                            prepend_icon=icon,
                            append_icon=(
                                f"transform_persistence_default === '{value}' ? 'mdi-check' : undefined",
                            ),
                            click=(
                                manager.set_transform_persistence_default,
                                f"['{value}']",
                            ),
                        )

    def execution_button(self):
        manager = self.ctx.pipeline
        if manager.pipeline.is_executing():
            manager.cancel_execution()
        else:
            manager.set_paused(not manager.pipeline.paused)

    def open_menu(self, kind, target_id, x, y):
        actions = self.ctx.pipeline.menu_actions(kind, target_id)
        if not actions:
            return
        with self.state as s:
            s.pipeline_menu = {
                "kind": kind,
                "id": target_id,
                "x": x,
                "y": y,
                "actions": actions,
            }
            s.pipeline_menu_show = True

    def run_action(self, action_id):
        menu = self.state.pipeline_menu or {}
        self.state.pipeline_menu_show = False
        self.ctx.pipeline.run_menu_action(action_id, menu.get("kind"), menu.get("id"))

    def delete(self, kind, target_id):
        self.ctx.pipeline.run_menu_action("delete", kind, target_id)

    def toggle_breakpoint(self, node_id):
        self.ctx.pipeline.toggle_breakpoint(node_id)
