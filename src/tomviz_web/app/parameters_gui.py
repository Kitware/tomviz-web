"""Parameter models and panels generated from a catalog entry's JSON
``parameters`` list: one ``StateDataModel`` subclass per entry name (one
synced field per parameter) and the Vuetify HTML that edits it."""

from loguru import logger
from trame.app import dataclass
from trame.widgets import vuetify3 as v3

PARAMETERS_MODEL_CLASSES = {}


def gui_bool(parameter):
    name = parameter.get("name")
    label = parameter.get("label", name)

    if name is None:
        logger.warning("Parameter {} has no name. Skipping.", parameter)
        return False

    return v3.VSwitch(
        label=label,
        v_model=f"self.{name}",
        hide_details=True,
    ).html


def gui_number(parameter):
    name = parameter.get("name")
    label = parameter.get("label", name)

    if name is None:
        logger.warning("Parameter {} has no name. Skipping.", parameter)
        return False

    # handling of default/data-default
    default_values = []
    if "default" in parameter:
        d_value = parameter.get("default")
        if isinstance(d_value, list | tuple):
            default_values.extend(d_value)
        else:
            default_values.append(d_value)
    elif "data-default" in parameter:
        # !! data-default needs datasource !!
        logger.critical("Need datasource for {}", parameter)
        # https://github.com/OpenChemistry/tomviz/blob/master/tomviz/InterfaceBuilder.cxx#L257C37-L257C51
        return False

    # handling minimum
    minimum = parameter.get("minimum")
    min_values = [min(default_values) for _ in default_values]
    if "minimum" in parameter:
        min_value = parameter.get("minimum")
        if isinstance(min_value, list | tuple):
            for idx, v in enumerate(min_value):
                min_values[idx] = v
        else:
            size = len(min_values)
            for i in range(size):
                min_values[i] = min_value

    # handling maximum
    maximum = parameter.get("maximum")
    max_values = [max(default_values) for _ in default_values]
    if "maximum" in parameter:
        max_value = parameter.get("maximum")
        if isinstance(max_value, list | tuple):
            for idx, v in enumerate(max_value):
                max_values[idx] = v
        else:
            size = len(max_values)
            for i in range(size):
                max_values[i] = max_value

    # handling precision / step
    py_type = parameter.get("type")
    precision = parameter.get("precision", -1)
    step = parameter.get("step", -1)
    if py_type == "double" and precision < 0:
        precision = 6

    size = len(default_values)
    if size == 1:
        with v3.VNumberInput(
            label=label,
            v_model=f"self.{name}",
            control_variant="stacked",
            variant="outlined",
            density="compact",
            hide_details=True,
            classes="my-2",
        ) as root:
            if precision > 0:
                root.precision = precision
            if step > 0:
                root.step = (step,)
            if minimum is not None:
                root.min = (minimum,)
            if maximum is not None:
                root.max = (maximum,)

            return root.html

    # Need to display an array of widget
    with v3.VCol(classes="px-0 pb-3 pt-0") as root:
        v3.VLabel(label)
        with v3.VRow(no_gutters=True):
            for i in range(size):
                with v3.VCol():
                    with v3.VNumberInput(
                        v_model=f"self.{name}[{i}]",
                        control_variant="hidden",
                        variant="outlined",
                        density="compact",
                        hide_details=True,
                    ) as item:
                        if precision > 0:
                            item.precision = precision
                        if step > 0:
                            item.step = (step,)
                        item.min = (min_values[i],)
                        item.max = (max_values[i],)

        return root.html


def gui_enumeration(parameter):
    name = parameter.get("name")
    label = parameter.get("label", name)

    if name is None:
        logger.warning("Parameter {} has no name. Skipping.", parameter)
        return False

    options = parameter.get("options")
    items = [
        {"title": next(iter(entry.keys())), "value": idx}
        for idx, entry in enumerate(options)
    ]

    return v3.VSelect(
        label=label,
        v_model=f"self.{name}",
        items=(str(items),),
        variant="outlined",
        hide_details=True,
        density="compact",
        classes="my-2",
    ).html


def gui_xyz_header(_):
    with v3.VRow(no_gutters=True) as root:
        for label in ["X", "Y", "Z"]:
            with v3.VCol():
                v3.VLabel(label, classes="d-block text-center")

        return root.html


def gui_string(parameter):
    name = parameter.get("name")
    label = parameter.get("label", name)

    if name is None:
        logger.warning("Parameter {} has no name. Skipping.", parameter)
        return False

    return v3.VTextField(
        label=label,
        v_model=f"self.{name}",
        variant="outlined",
        hide_details=True,
        density="compact",
        classes="my-2",
    ).html


def gui_scalars(parameter):
    logger.critical("Need to implement GUI for select_scalars: {}", parameter)
    return False


def gui_dataset(parameter):
    name = parameter.get("name")
    label = parameter.get("label", name)

    if name is None:
        logger.warning("Parameter {} has no name. Skipping.", parameter)
        return False

    return v3.VSelect(
        label=label,
        v_model=f"self.{name}",
        items=("self.dataset_items",),
        variant="outlined",
        hide_details=True,
        density="compact",
        classes="my-2",
    ).html


PATH_TYPES = {"file", "save_file", "directory"}
TYPE_MAPPING = {
    "bool": gui_bool,
    "int": gui_number,
    "double": gui_number,
    "enumeration": gui_enumeration,
    "xyz_header": gui_xyz_header,
    "file": gui_string,
    "save_file": gui_string,
    "directory": gui_string,
    "string": gui_string,
    "dataset": gui_dataset,  # can't find example
    "select_scalars": gui_scalars,  # can't find example
    # finding: reconstruction / label_map / table
}


def param_to_gui(parameter) -> str:
    fn = TYPE_MAPPING.get(parameter.get("type"))
    return fn(parameter) if fn else False


def to_gui(params) -> str:
    return "".join(
        [
            '<v-col class="pa-0">',
            *[param_to_gui(p) for p in params if param_to_gui(p)],
            "</v-col>",
        ]
    )


def to_param(name, param):
    name = param.get("name")
    param_type = param.get("type")
    param_default = param.get("default")
    add_on_fields = {}

    if name is None:
        return {}

    core_py_type = None
    if param_type == "bool":
        core_py_type = bool
        if param_default is None:
            param_default = False
    elif param_type == "int":
        core_py_type = int
    elif param_type == "double":
        core_py_type = float
    elif param_type == "enumeration":
        core_py_type = int
    elif param_type == "xyz_header":
        return {}
    elif param_type in PATH_TYPES or param_type == "string":
        core_py_type = str
    elif param_type == "dataset":
        core_py_type = int
        add_on_fields["dataset_items"] = dataclass.Sync(list, list)

    if core_py_type is None:
        msg = f"Invalid parameter type::{param_type} for {name}::{param.get('name')}"
        raise ValueError(msg)

    py_type = core_py_type
    py_default = param_default
    add_on = {}
    if isinstance(param_default, list | tuple):
        py_type = list[core_py_type]
        py_default = list(py_default)
        add_on["client_deep_reactive"] = True

    return {name: dataclass.Sync(py_type, py_default, **add_on), **add_on_fields}


def parameters_model_class(meta):
    name = meta.get("name")
    parameters = meta.get("parameters", [])
    klass = PARAMETERS_MODEL_CLASSES.get(name)

    if klass:
        return klass

    # print("=" * 60)
    # print("meta", meta)
    # for p in parameters:
    #     print(p)
    # print("=" * 60)

    # Generate klass
    namespace = {}
    all_fields = [
        to_param(name, p) for p in parameters if TYPE_MAPPING.get(p.get("type"))
    ]
    for fields in all_fields:
        namespace.update(fields)

    # Generate UI
    tpl = to_gui(parameters)

    @classmethod
    def generate_gui(*_):
        return tpl

    namespace["generate_gui"] = generate_gui

    # Create class
    klass = type(name, (dataclass.StateDataModel,), namespace)
    _ensure_field_registries(klass)
    PARAMETERS_MODEL_CLASSES[name] = klass
    return klass


def _ensure_field_registries(klass):
    """trame-dataclass creates a model class's field registries when its
    first ``Sync`` field registers itself; a parameter-less transform has no
    field, so create the (empty) registries here."""
    for key in (
        "FIELD_NAMES",
        "DATACLASS_NAMES",
        "CLIENT_NAMES",
        "CLIENT_ONLY_NAMES",
        "CLIENT_DEEP_REACTIVE",
    ):
        if key not in klass.__dict__:
            setattr(klass, key, set(getattr(klass, key, set())))
    for key in ("ENCODERS", "TYPE_CHECKING"):
        if key not in klass.__dict__:
            setattr(klass, key, dict(getattr(klass, key, {})))


def to_parameters_model(server, meta):
    klass = parameters_model_class(meta)
    return klass(server)
