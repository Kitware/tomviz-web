import json

from loguru import logger
from trame.decorators import change
from trame.widgets import dataclass, html
from trame.widgets import vuetify3 as v3

from tomviz_web.app import data_model


class TransformSelection(html.Div):
    """The picker that appends a catalog transform to the active data node's
    chain, or starts a pipeline with a catalog source. Shown in the drawer
    while ``select_transform`` is set, with or without data: before any data
    is loaded, only a source can be added."""

    def __init__(self):
        super().__init__()

        self.state.setdefault("transform_favorites", False)
        # The activated item is a source (addable without a tip port).
        self.state.setdefault("transform_activated_source", False)

        with self:
            v3.VBtn(
                prepend_icon="mdi-chevron-left",
                text="Transforms",
                click="select_transform = false",
                classes="w-100 text-none mb-1",
                variant="tonal",
                spaced="end",
            )

            with (
                # always: the picker shows without an active data node too
                # (nothing loaded yet, or a link selected); the provider
                # would otherwise render none of its content.
                dataclass.Provider(
                    name="active_input", instance=("active_data_id",), always=True
                ),
                v3.VCard(
                    classes="border-thin overflow-auto flex-fill mb-2",
                    flat=True,
                    variant="flat",
                ),
            ):
                v3.VLabel(
                    "{{ active_input.label }}",
                    v_if="active_input_available",
                    classes="text-subtitle-2 text-truncate mx-2 mt-2",
                )
                v3.VLabel(
                    "No data loaded: add a source, or open a file first",
                    v_else_if="!tip_port_id",
                    classes="text-caption text-wrap mx-2 mt-2",
                )
                with html.Div(classes="d-flex pa-2 ga-2 align-center"):
                    v3.VTextField(
                        placeholder="Search transforms...",
                        v_model=("transform_filter", ""),
                        prepend_inner_icon="mdi-magnify",
                        variant="outlined",
                        density="compact",
                        hide_details=True,
                        clearable=True,
                    )
                    v3.VBtn(
                        # A transform needs a tip port to attach to.
                        disabled=(
                            "transform_activated.length === 0"
                            " || (!tip_port_id && !transform_activated_source)",
                        ),
                        classes="rounded",
                        icon="mdi-plus",
                        color="primary",
                        density="comfortable",
                        flat=True,
                        click=(
                            self.add_entry,
                            "[transform_activated[0]]",
                        ),
                    )
                with html.Div(
                    classes="d-flex mx-2 pa-1 ga-2 align-center justify-space-around bg-surface-light rounded",
                ):
                    v3.VBtn(
                        "All Transforms",
                        variant=("transform_favorites ? 'plain' : 'flat'",),
                        classes="text-none flex-fill",
                        click="transform_favorites = false",
                        density="comfortable",
                    )
                    v3.VBtn(
                        "Favorites ({{ catalog_favorite_count }})",
                        prepend_icon="mdi-star",
                        variant=("transform_favorites ? 'flat' : 'plain'",),
                        classes="text-none flex-fill",
                        click="transform_favorites = true",
                        density="comfortable",
                    )

                with (
                    self.ctx.catalog.root.provide_as("catalog_root"),
                    html.Div(
                        style="height: calc(100vh - 14.8rem)",
                        classes="overflow-scroll mt-2",
                    ),
                    v3.VTreeview(
                        v_model_opened=("transform_opened", []),
                        v_model_activated=("transform_activated", []),
                        items=("catalog_root.children",),
                        density="compact",
                        item_value="_id",
                        activatable=True,
                        open_on_click=True,
                        indent=20,
                        hide_actions=True,
                        open_all=(
                            "transform_favorites || (transform_filter|| '').length",
                        ),
                        search=(
                            "transform_favorites ? `${transform_filter} ::fav::` : transform_filter",
                        ),
                        custom_filter=("utils.tomviz.treeFilter",),
                    ),
                ):
                    with v3.Template(v_slot_prepend="{ item, isOpen }"):
                        v3.VIcon(
                            v_if="item.children",
                            icon=("isOpen ? 'mdi-folder-open' : 'mdi-folder'",),
                        )
                        v3.VIcon(v_else=True, icon=("item.icon",))
                    with v3.Template(v_slot_append="{ item }"):
                        v3.VChip(
                            "{{ item.count }}",
                            v_if="item.children && item.count",
                            size="x-small",
                        )
                        v3.VIcon(
                            icon=("item.favorite ? 'mdi-heart':'mdi-heart-outline'",),
                            color=("item.favorite ? 'red' : null",),
                            v_if="!item.children",
                            v_on_click_prevent="item.favorite = !item.favorite",
                        )

    def add_entry(self, item_id):
        """Add the catalog item: a source starts a new pipeline, a transform
        goes at the tip."""
        item = data_model.get_instance(item_id)
        entry = self.ctx.catalog.entries.get(item.name)
        # Held until the editor confirms it (desktop parity); a transform
        # with inputs left to link gets its editor once they are.
        if entry is not None and entry.is_source:
            model_id = self.ctx.pipeline.add_source(
                item.name, icon=item.icon, meta=item.meta, pending=True
            )
        else:
            model_id = self.ctx.pipeline.add_transform(
                item.name, icon=item.icon, meta=item.meta, pending=True
            )
        self.state.select_transform = False
        if model_id and self.ctx.pipeline.is_pending(model_id):
            self.ctrl.open_transform_editor(model_id)

    @change("transform_activated")
    def _on_active(self, transform_activated, **_):
        source = False
        if transform_activated:
            item = data_model.get_instance(transform_activated[0])
            if isinstance(item, data_model.CatalogItem):
                logger.debug("Catalog entry:\n{}", json.dumps(item.meta, indent=2))
                entry = self.ctx.catalog.entries.get(item.name)
                source = entry is not None and entry.is_source
        self.state.transform_activated_source = source
