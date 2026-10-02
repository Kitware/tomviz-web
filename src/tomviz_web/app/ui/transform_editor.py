"""Dialog configuring a catalog node (a transform, or a catalog source): its
name, its definition (the entry's JSON description), its script and its
parameters. Every edit is staged until Apply or OK, which commit them all
and re-execute the graph once; Cancel (or the close button) drops them,
including the parameter panel's. For a node the manager holds until it is
confirmed (a new transform), Apply/OK also release it and Cancel removes it,
restoring the graph (see ``PipelineManager.is_pending``)."""

import copy

from loguru import logger
from trame.app.dataclass import StateDataModel, Sync, get_instance
from trame.widgets import code, dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app.data_model import DataNodeModel

# Parameter types the definition editor offers (the desktop app's list, but
# "dataset": in a v1 definition such a parameter is an input port of the
# node, and a node's ports are fixed once it exists).
PARAMETER_TYPES = [
    "double",
    "int",
    "bool",
    "string",
    "enumeration",
    "file",
    "save_file",
    "directory",
    "select_scalars",
    "xyz_header",
]
NUMBER_TYPES = "['int', 'double']"
TEXT_TYPES = "['string', 'file', 'save_file', 'directory']"


class TransformEditorModel(StateDataModel):
    """The dialog's own state: which node it configures, the staged name,
    definition and script, and the outcome of the last Apply (``message``,
    a ``v-alert`` type). ``definition`` is deep reactive, so the client's
    nested edits (a parameter's fields) reach the server."""

    show = Sync(bool, False)
    tab = Sync(str, "parameters")
    transform_id = Sync(str, "")  # the DataNodeModel being configured
    label = Sync(str, "")
    definition = Sync(dict, dict, client_deep_reactive=True)
    script = Sync(str, "")
    message = Sync(str, "")
    message_type = Sync(str, "info")


def json_field(label, key, **kwargs):
    """Text field editing ``param[key]`` as JSON: the value only changes
    while the text parses."""
    return v3.VTextField(
        label=label,
        model_value=(f"param.{key} === undefined ? '' : JSON.stringify(param.{key})",),
        update_modelValue=(
            "(e) => {"
            "  if(e === '') {"
            f"   delete param.{key};"
            "  } else {"
            "    try {"
            f"     param.{key} = JSON.parse(e);"
            "    } catch (error) {}"
            "  }"
            "}"
        ),
        variant="outlined",
        density="compact",
        hide_details=True,
        **kwargs,
    )


class TransformEditorDialog(html.Div):
    def __init__(self):
        super().__init__()
        self.editor = TransformEditorModel(self.server)
        self.ctrl.open_transform_editor = self.open
        self.ctx.transform_editor = self

        with (
            self,
            self.editor.provide_as("editor"),
            # Persistent: only Cancel, the close button and OK close it, so
            # a stray click outside cannot drop the edits.
            v3.VDialog(v_model="editor.show", contained=True, persistent=True),
            dataclass.Provider(name="transform", instance=("editor.transform_id",)),
        ):
            with v3.VCard(
                classes="mx-auto d-flex flex-column",
                rounded="lg",
                height="80vh",
                max_width="1000px",
                width="80vw",
            ):
                with v3.VCardItem(title=("`Configure - ${editor.label}`",)):
                    with v3.Template(v_slot_append=True):
                        v3.VBtn(
                            icon="mdi-close",
                            density="compact",
                            variant="plain",
                            click=self.cancel,
                        )
                v3.VDivider()
                with v3.VCardText(classes="flex-0-0 pb-0"):
                    v3.VTextField(
                        label="Name",
                        v_model="editor.label",
                        variant="outlined",
                        density="compact",
                        hide_details=True,
                    )
                with v3.VTabs(
                    v_model="editor.tab",
                    density="compact",
                    classes="flex-0-0 px-4 mt-2",
                ):
                    v3.VTab("Definition", value="definition", classes="text-none")
                    v3.VTab("Script", value="script", classes="text-none")
                    v3.VTab("Parameters", value="parameters", classes="text-none")
                    v3.VTab("Execution", value="execution", classes="text-none")
                v3.VDivider()
                v3.VAlert(
                    v_if="editor.message",
                    text=("editor.message",),
                    type=("editor.message_type",),
                    density="compact",
                    variant="tonal",
                    closable=True,
                    click_close="editor.message = ''",
                    classes="flex-0-0 mx-4 mt-2",
                )
                with v3.VTabsWindow(
                    v_model="editor.tab",
                    classes="flex-fill overflow-auto",
                ):
                    with v3.VTabsWindowItem(value="definition", classes="pa-4"):
                        self._definition()

                    with v3.VTabsWindowItem(value="script", classes="h-100"):
                        code.Editor(
                            v_model="editor.script",
                            language="python",
                            theme=("theme === 'light' ? 'vs' : 'vs-dark'",),
                            options=(
                                "{ automaticLayout: true, scrollBeyondLastLine: false }",
                            ),
                            style="height: 100%; min-height: 10px;",
                        )

                    with v3.VTabsWindowItem(value="parameters", classes="pa-4"):
                        self._parameters()
                    v3.VTabsWindowItem(value="execution", classes="pa-4")
                v3.VDivider()
                with v3.VCardActions(classes="flex-0-0 px-4"):
                    v3.VSpacer()
                    v3.VBtn("Cancel", classes="text-none", click=self.cancel)
                    v3.VBtn(
                        "Apply", classes="text-none", variant="tonal", click=self.apply
                    )
                    v3.VBtn(
                        "OK",
                        classes="text-none",
                        variant="flat",
                        color="primary",
                        click=self.ok,
                    )

    def _definition(self):
        with v3.VRow(dense=True):
            with v3.VCol(cols=6):
                v3.VTextField(
                    label="Name",
                    v_model="editor.definition.name",
                    variant="outlined",
                    density="compact",
                    hide_details=True,
                )
            with v3.VCol(cols=6):
                v3.VTextField(
                    label="Label",
                    v_model="editor.definition.label",
                    variant="outlined",
                    density="compact",
                    hide_details=True,
                )
            with v3.VCol(cols=12):
                v3.VTextarea(
                    label="Description",
                    v_model="editor.definition.description",
                    variant="outlined",
                    density="compact",
                    hide_details=True,
                    rows=2,
                    auto_grow=True,
                )

        with html.Div(classes="d-flex align-center mt-4 mb-2"):
            html.Div("Parameters", classes="text-subtitle-2")
            v3.VSpacer()
            v3.VBtn(
                "Add Parameter",
                prepend_icon="mdi-plus",
                classes="text-none",
                density="compact",
                variant="tonal",
                click=(
                    "editor.definition.parameters = [...(editor.definition.parameters || []), "
                    "{ name: `param_${(editor.definition.parameters || []).length}`, "
                    "type: 'double', default: 0 }]"
                ),
            )

        with v3.VExpansionPanels(
            variant="accordion", multiple=True, flat=True, rounded=True, static=True
        ):
            # dataset parameters are ports, not values: hidden, and kept as
            # they are (``idx`` still indexes the whole list).
            with v3.VExpansionPanel(
                v_for="(param, idx) in (editor.definition.parameters || [])",
                key="idx",
                v_show="param.type !== 'dataset'",
                rounded=True,
                classes="border-thin my-1",
            ):
                with v3.VExpansionPanelTitle():
                    html.Span("{{ param.label || param.name }}")
                    html.Span(
                        "{{ param.name }} · {{ param.type }}",
                        classes="text-caption text-medium-emphasis ml-2",
                    )
                    v3.VSpacer()
                    v3.VBtn(
                        icon="mdi-trash-can-outline",
                        density="compact",
                        variant="plain",
                        classes="mr-2",
                        click_stop="editor.definition.parameters.splice(idx, 1)",
                    )
                with v3.VExpansionPanelText(classes="border-t-thin pt-3"):
                    with v3.VRow(dense=True):
                        with v3.VCol(cols=4):
                            v3.VTextField(
                                label="Name",
                                v_model="param.name",
                                variant="outlined",
                                density="compact",
                                hide_details=True,
                            )
                        with v3.VCol(cols=4):
                            v3.VTextField(
                                label="Label",
                                v_model="param.label",
                                variant="outlined",
                                density="compact",
                                hide_details=True,
                            )
                        with v3.VCol(cols=4):
                            v3.VSelect(
                                label="Type",
                                v_model="param.type",
                                items=(str(PARAMETER_TYPES),),
                                variant="outlined",
                                density="compact",
                                hide_details=True,
                            )
                        with v3.VCol(cols=12):
                            v3.VTextField(
                                label="Description",
                                v_model="param.description",
                                variant="outlined",
                                density="compact",
                                hide_details=True,
                            )

                        # Default value, by type
                        with v3.VCol(cols=12, v_if="param.type === 'bool'"):
                            v3.VSwitch(
                                label="Default",
                                v_model="param.default",
                                density="compact",
                                hide_details=True,
                            )
                        with v3.VCol(
                            cols=12, v_else_if=f"{TEXT_TYPES}.includes(param.type)"
                        ):
                            v3.VTextField(
                                label="Default",
                                v_model="param.default",
                                variant="outlined",
                                density="compact",
                                hide_details=True,
                            )
                        with v3.VCol(
                            cols=12,
                            v_else_if="!['xyz_header', 'select_scalars'].includes(param.type)",
                        ):
                            json_field(
                                "Default (JSON)",
                                "default",
                                placeholder="1.0 or [128, 128, 128]",
                            )

                        # Numeric bounds
                        with v3.Template(v_if=f"{NUMBER_TYPES}.includes(param.type)"):
                            with v3.VCol(cols=3):
                                json_field("Minimum", "minimum")
                            with v3.VCol(cols=3):
                                json_field("Maximum", "maximum")
                            with v3.VCol(cols=3):
                                json_field("Step", "step")
                            with v3.VCol(cols=3):
                                json_field("Precision", "precision")

                        # Enumeration options
                        with v3.VCol(cols=12, v_if="param.type === 'enumeration'"):
                            json_field(
                                "Options (JSON)",
                                "options",
                                placeholder='[{"Linear": 0}, {"Cubic": 1}]',
                            )

    def _parameters(self):
        html.Div(
            "{{ editor.definition.description }}",
            v_if="editor.definition.description",
            classes="text-body-2 mb-4",
            style="white-space: pre-wrap;",
        )
        # Optional chaining: a canceled insertion removes the node this
        # still points at.
        dataclass.Gui(instance=("transform?.parameters?._id",))

    def open(self, model_id):
        """Show the dialog for the catalog node model ``model_id``, staging
        a copy of the node's name, definition and script."""
        model = get_instance(model_id)
        if not isinstance(model, DataNodeModel) or model.parameters is None:
            logger.warning("No catalog node to configure: {}", model_id)
            return

        model.pull_definition()
        self.editor.transform_id = model._id
        self.editor.label = model.label
        self.editor.definition = copy.deepcopy(model.definition)
        self.editor.script = model.node.script
        self.editor.message = ""
        self.editor.show = True

    def cancel(self):
        """Close, dropping the staged edits and the panel's; a node still
        waiting for confirmation is removed."""
        model = get_instance(self.editor.transform_id)
        if model is not None:
            model.reset_parameters()
            self.ctx.pipeline.cancel_pending(model._id)
        self.editor.show = False

    def apply(self) -> bool:
        """Commit every staged edit, then re-execute once. Returns whether
        the edits were applied."""
        model = get_instance(self.editor.transform_id)
        if model is None or model.node is None:
            return False
        try:
            # The definition and script first: they run nothing.
            reset = model.apply_edits(
                copy.deepcopy(self.editor.definition), self.editor.script
            )
        except ValueError as error:
            self.editor.message_type = "error"
            self.editor.message = f"Edits not applied: {error}."
            return False

        # The name only: the definition's label is the default name of
        # new nodes (desktop parity).
        model.node.label = self.editor.label
        model.label = self.editor.label
        self.ctx.pipeline.commit_pending(model._id)

        # The panel's values last: set_parameters re-executes the graph.
        if not model.apply_parameters():
            self.ctx.pipeline.execute()

        if reset:
            self.editor.message_type = "warning"
            self.editor.message = (
                "Edits applied. These parameters went back to their defaults: "
                + ", ".join(reset)
                + "."
            )
        else:
            self.editor.message_type = "success"
            self.editor.message = "Edits applied."
        return True

    def ok(self):
        """Apply, and close unless the edits were refused."""
        if self.apply():
            self.editor.show = False
