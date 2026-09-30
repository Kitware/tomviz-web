from trame.ui.html import DivLayout
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app import data_model
from tomviz_web.app.pipeline import RepresentationType
from tomviz_web.app.pipeline.representations.volume import BLEND_MODES
from tomviz_web.app.ui.dynamic._widgets import COMPACT, FILLED, slider, vector_fields
from tomviz_web.app.utils.volume import (
    CUT_OUT_CORNERS,
    EXPLODED_AXES,
    LIGHTING_PRESETS,
)

NAME = RepresentationType.VOLUME.name
TEMPLATE = f"rep_{NAME}"

LIGHTING_TIPS = {
    "Flat": "No shading: colors come straight from the color map. Fastest.",
    "Simple": "Classic directional shading. Fast and interactive.",
    "Gentle": "Matte, low-contrast shading with no highlight: reads the shape "
    "without turning reconstruction noise into glitter.",
    "Soft": "Soft ambient look with gentle volumetric shadows and smooth "
    "normals. Slower.",
    "Full": "Full volumetric scattering with long-range shadows. Slowest.",
}

# Where the volume is drawn decides what applies (the desktop greys the same)
COMPOSITED = "rep.MultiVolumeActive"
LIGHTING_OFF = (
    "rep.BlendMode !== 'Composite' || (rep.MultiVolumeActive && !rep.MultiVolumeLead)"
)
NO_CROPPING = "rep.MultiVolumeActive || rep.Bricked"


def _model(representation_id):
    return data_model.get_instance(representation_id)


def apply_preset(representation_id, name):
    _model(representation_id).apply_lighting_preset(name)


def apply_user_preset(representation_id, name):
    if name:
        _model(representation_id).apply_user_lighting_preset(name)


def save_user_preset(representation_id, name):
    _model(representation_id).save_user_lighting_preset(name or "")


def rename_user_preset(representation_id, name, new_name):
    _model(representation_id).rename_user_lighting_preset(name or "", new_name or "")


def delete_user_preset(representation_id, name):
    if name:
        _model(representation_id).delete_user_lighting_preset(name)


def set_exploded(representation_id, field, value):
    _model(representation_id).set_exploded(**{field: value})


def component_slider(label, field, index):
    """A 0-1 slider editing one component of ``rep.<field>``."""
    with html.Div(classes="d-flex align-center mt-1 mx-1"):
        v3.VLabel(label, classes="text-body-2")
        v3.VSpacer()
        v3.VLabel(f"{{{{ rep.{field}[{index}].toFixed(2) }}}}", classes="text-body-2")
    v3.VSlider(
        model_value=(f"rep.{field}[{index}]",),
        update_modelValue=(
            f"rep.{field} = rep.{field}.map((v, i) => i === {index} ? $event : v)"
        ),
        min=0,
        max=1,
        step=0.01,
        **COMPACT,
    )


def section(title, field, tooltip, update=None):
    """A checkable section header, like the desktop's group boxes."""
    kwargs = (
        {"model_value": (f"rep.{field}",), "update_modelValue": update}
        if update
        else {"v_model": f"rep.{field}"}
    )
    v3.VCheckbox(
        label=title,
        disabled=(NO_CROPPING,),
        title=tooltip,
        classes="mt-2",
        **kwargs,
        **COMPACT,
    )
    with html.Div(v_if=f"{NO_CROPPING}", classes="text-caption mx-1"):
        html.Span(
            "{{ rep.MultiVolumeActive"
            " ? 'Not available while the volumes in this view are rendered"
            " together, which VTK cannot crop.'"
            " : 'Not available for a volume rendered in bricks.' }}"
        )


class VolumeRepresentationUI(DivLayout):
    # A label map's panel (the desktop's categorical mode): interpolation
    # and blending are pinned, as any other choice mixes label numbers.
    CATEGORICAL = False

    def __init__(self, server, template_name=TEMPLATE):
        super().__init__(server, template_name=template_name)

        with (
            self,
            dataclass.Provider(name="rep", instance=("active_representation_id",)),
        ):
            with html.Div(classes="pa-2"):
                self._content()

    def _content(self):
        self._rendering()
        self._lighting()
        self._cut_out()
        self._exploded()

    def _rendering(self):
        v3.VCheckbox(
            label="Custom Color Opacity",
            v_model="rep.use_internal_color_opacity",
            # adopted labels have no other map to go on
            disabled=("rep.LabelsAdopted",) if self.CATEGORICAL else False,
            **COMPACT,
        )
        if not self.CATEGORICAL:
            self._interpolation_and_blending()
        self._solidity_and_jittering()

    def _interpolation_and_blending(self):
        v3.VSelect(
            label="Interpolation",
            v_model="rep.InterpolationType",
            items=(
                "volume_interpolation_types",
                [
                    {"title": "Nearest Neighbor", "value": "Nearest"},
                    {"title": "Linear", "value": "Linear"},
                ],
            ),
            classes="mt-2",
            **FILLED,
        )
        # Rendered together, the view's volumes always composite with
        # jittering: show that, and keep the sink's own choice underneath.
        v3.VSelect(
            label="Blending Mode",
            model_value=(f"{COMPOSITED} ? 'Composite' : rep.BlendMode",),
            update_modelValue="rep.BlendMode = $event",
            items=("volume_blend_modes", list(BLEND_MODES)),
            disabled=(COMPOSITED,),
            classes="mt-2",
            **FILLED,
        )

    def _solidity_and_jittering(self):
        slider(
            "Solidity",
            "Solidity",
            0,
            1,
            0.01,
            2,
            tooltip="Adjusts the unit distance the opacity is defined over: at "
            "1, a given opacity accumulates over one unit of distance.",
        )
        v3.VCheckbox(
            label="Ray jittering",
            model_value=(f"{COMPOSITED} || rep.Jittering",),
            update_modelValue="rep.Jittering = $event",
            disabled=(COMPOSITED,),
            **COMPACT,
        )

    def _lighting(self):
        with v3.VCard(
            classes="mt-2 pa-2 border-thin",
            flat=True,
            disabled=(LIGHTING_OFF,),
        ):
            v3.VLabel("Lighting", classes="text-subtitle-2")
            with html.Div(v_if=COMPOSITED, classes="text-caption"):
                html.Span(
                    "{{ rep.MultiVolumeLead"
                    " ? 'Applies to every volume rendered together in this view.'"
                    " : `Shared by the volumes rendered together in this view"
                    " and set on '${rep.MultiVolumeLeadLabel}'.` }}"
                )
            with v3.VBtnToggle(
                model_value=("rep.LightingPreset",),
                update_modelValue=(
                    apply_preset,
                    "[active_representation_id, $event]",
                ),
                density="compact",
                divided=True,
                variant="outlined",
                classes="d-flex mt-1",
            ):
                for name in LIGHTING_PRESETS:
                    v3.VBtn(
                        name,
                        value=name,
                        title=LIGHTING_TIPS[name],
                        classes="flex-grow-1 text-none px-1",
                        size="small",
                    )

            # The user's saved presets
            with html.Div(classes="d-flex align-center ga-1 mt-2"):
                v3.VSelect(
                    label="Saved presets",
                    model_value=("rep.UserLightingPreset || null",),
                    update_modelValue=(
                        apply_user_preset,
                        "[active_representation_id, $event]",
                    ),
                    items=("volume_lighting_presets.map((p) => p.name)",),
                    no_data_text="No saved presets",
                    **FILLED,
                )
                taken = (
                    "(volume_lighting_presets || []).some("
                    "(p) => p.name === volume_preset_name.trim())"
                )
                self._preset_menu(
                    "mdi-content-save-outline",
                    "Save the lighting under a name",
                    f"{taken} ? 'Replace' : 'Save'",
                    save_user_preset,
                    "[active_representation_id, volume_preset_name]",
                    "volume_preset_name = rep.UserLightingPreset || "
                    "`Lighting ${(volume_lighting_presets || []).length + 1}`",
                )
                self._preset_menu(
                    "mdi-rename-outline",
                    "Rename the selected preset",
                    "'Rename'",
                    rename_user_preset,
                    "[active_representation_id, rep.UserLightingPreset,"
                    " volume_preset_name]",
                    "volume_preset_name = rep.UserLightingPreset",
                    disabled="!rep.UserLightingPreset",
                    refuse=taken,  # the name of another preset
                )
                v3.VBtn(
                    icon="mdi-delete-outline",
                    title="Delete the selected preset",
                    size="small",
                    variant="text",
                    disabled=("!rep.UserLightingPreset",),
                    click=(
                        delete_user_preset,
                        "[active_representation_id, rep.UserLightingPreset]",
                    ),
                )

            v3.VBtn(
                "Advanced",
                prepend_icon=(
                    "volume_lighting_advanced ? 'mdi-chevron-down'"
                    " : 'mdi-chevron-right'",
                ),
                click="volume_lighting_advanced = !volume_lighting_advanced",
                variant="text",
                size="small",
                classes="text-none mt-1 px-1",
            )
            with html.Div(v_show=("volume_lighting_advanced", False)):
                self._advanced_lighting()

    def _preset_menu(
        self, icon, tooltip, label, callback, args, on_open, disabled=None, refuse=None
    ):
        """A button opening a name field and a confirm button, which calls
        ``callback`` with ``args`` and closes the menu."""
        trigger = self.server.trigger_name(callback)
        with v3.VMenu(close_on_content_click=False):
            with v3.Template(v_slot_activator="{ props }"):
                v3.VBtn(
                    v_bind="props",
                    icon=icon,
                    title=tooltip,
                    size="small",
                    variant="text",
                    disabled=(disabled,) if disabled else False,
                    click=on_open,
                )
            with (
                v3.Template(v_slot_default="{ isActive }"),
                v3.VCard(classes="pa-2 d-flex ga-2 align-center", min_width=260),
            ):
                v3.VTextField(
                    label="Preset name",
                    v_model=("volume_preset_name", ""),
                    **FILLED,
                )
                blocked = "!volume_preset_name.trim()"
                if refuse:
                    blocked += f" || {refuse}"
                v3.VBtn(
                    f"{{{{ {label} }}}}",
                    disabled=(blocked,),
                    click=f"trigger('{trigger}', {args}); isActive.value = false",
                    size="small",
                    variant="tonal",
                    classes="text-none",
                )

    def _advanced_lighting(self):
        v3.VCheckbox(
            label="Shading",
            v_model="rep.Shade",
            title="Enable lighting. When off, the volume is rendered unlit (Flat).",
            **COMPACT,
        )
        unlit = "!rep.Shade"
        slider("Ambient", "Ambient", 0, 1, 0.01, 2, disabled=unlit)
        slider("Diffuse", "Diffuse", 0, 1, 0.01, 2, disabled=unlit)
        slider("Specular", "Specular", 0, 1, 0.01, 2, disabled=unlit)
        slider("Sp. Power", "SpecularPower", 1, 150, 1, 0, disabled=unlit)
        v3.VCheckbox(
            label="Shadows",
            v_model="rep.ShadowsEnabled",
            disabled=("!rep.ScatteringAvailable",),
            title="Cast volumetric shadows. Off keeps the preset but renders it "
            "without shadows, which is much faster.",
            **COMPACT,
        )
        no_shadows = "!rep.ShadowsEnabled || !rep.ScatteringAvailable"
        slider(
            "Shadow Strength",
            "VolumetricScattering",
            0,
            2,
            0.01,
            2,
            disabled=no_shadows,
            tooltip="Blend between surface shading (0) and volumetric scattering "
            "with shadows (2).",
        )
        slider(
            "Shadow Reach",
            "ShadowReach",
            0,
            1,
            0.01,
            2,
            disabled=no_shadows,
            tooltip="How far shadows travel: 0 local only (faster), 1 across "
            "the whole volume (slower).",
        )
        slider(
            "Anisotropy",
            "ScatteringAnisotropy",
            -1,
            1,
            0.01,
            2,
            disabled=no_shadows,
            tooltip="Direction light scatters in. Negative values brighten the "
            "volume; beyond about +0.5 it goes nearly black.",
        )
        v3.VCheckbox(
            label="Smooth Normals",
            v_model="rep.SmoothNormals",
            title="Shading normals from the opacity function instead of the raw "
            "gradient: less shading noise on experimental data.",
            **COMPACT,
        )
        with html.Div(v_if="!rep.ScatteringAvailable", classes="text-caption mx-1"):
            html.Span("{{ rep.ScatteringUnavailableReason }}")

    def _cut_out(self):
        section(
            "Cut Out",
            "CutOutEnabled",
            "Remove one octant of the volume so the interior can be seen.",
        )
        with html.Div(v_if="rep.CutOutEnabled", classes="ml-2"):
            v3.VSelect(
                label="Corner",
                v_model="rep.CutOutCorner",
                items=(
                    "volume_cut_out_corners",
                    [{"title": t, "value": i} for i, t in enumerate(CUT_OUT_CORNERS)],
                ),
                **FILLED,
            )
            for index, axis in enumerate("XYZ"):
                component_slider(axis, "CutOutPosition", index)

    def _exploded(self):
        section(
            "Exploded View",
            "ExplodedEnabled",
            "Render the volume as slabs pulled apart along one axis. The data "
            "is not modified.",
            update=(
                set_exploded,
                "[active_representation_id, 'ExplodedEnabled', $event]",
            ),
        )
        with html.Div(v_if="rep.ExplodedEnabled", classes="ml-2"):
            v3.VSelect(
                label="Axis",
                model_value=("rep.ExplodedAxis",),
                update_modelValue=(
                    set_exploded,
                    "[active_representation_id, 'ExplodedAxis', $event]",
                ),
                items=("volume_exploded_axes", list(EXPLODED_AXES)),
                **FILLED,
            )
            with html.Div(v_if="rep.ExplodedAxis === 'Custom'"):
                vector_fields("ExplodedDirection", "Direction")
                v3.VCheckbox(
                    label="Show Arrow",
                    v_model="rep.ExplodedShowArrow",
                    title="Draw an arrow along the direction at the center of the "
                    "volume; drag its tip to turn it.",
                    **COMPACT,
                )
            v3.VNumberInput(
                label="Slabs",
                v_model="rep.ExplodedChunks",
                # Bound, not literal: literals reach Vuetify as strings.
                min=("2",),
                max=("16",),
                control_variant="split",
                classes="mt-2",
                **FILLED,
            )
            slider(
                "Gap",
                "ExplodedGap",
                0,
                1,
                0.01,
                2,
                tooltip="Space between slabs, as a fraction of the volume's "
                "length along the axis.",
            )
            v3.VNumberInput(
                label="Offset (voxels)",
                v_model="rep.ExplodedOffset",
                min=("-rep.ExplodedOffsetLimit",),
                max=("rep.ExplodedOffsetLimit",),
                control_variant="split",
                title="Slide every cut along the direction to put the gaps where "
                "you want them; every slab stays at least one voxel thick.",
                classes="mt-2",
                **FILLED,
            )


UI = VolumeRepresentationUI
