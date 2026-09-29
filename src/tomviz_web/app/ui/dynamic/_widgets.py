"""Controls the visualization panels share. Each writes into the model the
panel's ``dataclass.Provider`` exposes as ``rep``."""

from trame.widgets import html
from trame.widgets import vuetify3 as v3

COMPACT = {"density": "compact", "hide_details": True}
FILLED = {"variant": "solo-filled", "flat": True, **COMPACT}


def slider(label, field, lo, hi, step, digits, disabled=None, tooltip=None):
    """A labeled slider showing its value. ``lo``, ``hi`` and ``step`` are
    numbers or ``(expression,)`` tuples."""
    with html.Div(classes="d-flex align-center mt-1 mx-1", title=tooltip):
        v3.VLabel(label, classes="text-body-2")
        v3.VSpacer()
        v3.VLabel(
            f"{{{{ rep.{field} == null ? '' : rep.{field}.toFixed({digits}) }}}}",
            classes="text-body-2",
        )
    v3.VSlider(
        v_model=f"rep.{field}",
        min=lo,
        max=hi,
        step=step,
        disabled=(disabled,) if disabled else False,
        **COMPACT,
    )


def color_picker(label, field, disabled=None):
    """A swatch opening a color picker on ``rep.<field>`` (``#rrggbb``)."""
    with html.Div(classes="d-flex align-center mx-1 my-1"):
        v3.VLabel(label, classes="text-body-2")
        v3.VSpacer()
        with v3.VMenu(close_on_content_click=False):
            with v3.Template(v_slot_activator="{ props }"):
                v3.VBtn(
                    v_bind="props",
                    color=(f"rep.{field}",),
                    disabled=(disabled,) if disabled else False,
                    size="small",
                    variant="flat",
                    classes="border-thin",
                    width=48,
                )
            v3.VColorPicker(
                v_model=f"rep.{field}",
                modes=("['rgb', 'hex']",),
                mode="hex",
                show_swatches=False,
            )


def vector_fields(field, label, disabled=None):
    """Three number fields editing ``rep.<field>``, committed on Enter or
    blur like the desktop's line edits."""
    v3.VLabel(label, classes="text-caption mt-2 mx-1")
    with html.Div(classes="d-flex ga-1"):
        for index, axis in enumerate("XYZ"):
            value = "parseFloat($event.target.value)"
            v3.VTextField(
                label=axis,
                model_value=(f"Number(rep.{field}[{index}].toPrecision(6))",),
                change=(
                    f"Number.isFinite({value}) && (rep.{field} = rep.{field}"
                    f".map((v, i) => i === {index} ? {value} : v))"
                ),
                disabled=(disabled,) if disabled else False,
                **FILLED,
            )


def array_select(label, field, tooltip=None):
    """Pick one of ``rep.ArrayNames``, or Default (``""``): the data's
    active array."""
    v3.VSelect(
        label=label,
        v_model=f"rep.{field}",
        items=(
            "[{ title: 'Default', value: '' }, "
            "...rep.ArrayNames.map((n) => ({ title: n, value: n }))]",
        ),
        title=tooltip,
        classes="mt-2",
        **FILLED,
    )


def surface_mode_select(field="Mode", label="Mode"):
    v3.VSelect(
        label=label,
        v_model=f"rep.{field}",
        items=("['Surface', 'Wireframe', 'Points']",),
        classes="mt-2",
        **FILLED,
    )
