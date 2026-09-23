from pathlib import Path

from trame.widgets import html
from trame.widgets import vuetify3 as v3

from tomviz_trame.app.pipeline.nodes import SUPPORTED_EXTENSIONS
from tomviz_trame.app.pipeline.state import STATE_EXTENSIONS

# -----------------------------------------------------------------------------
# Utils
# -----------------------------------------------------------------------------

DIRECTORY = {"icon": "mdi-folder", "type": "directory"}
GROUP = {"icon": "mdi-file-document-multiple-outline", "type": "group"}
FILE = {"icon": "mdi-file-document-outline", "type": "file"}

HEADERS = [
    {"title": "Name", "align": "start", "key": "name", "sortable": False},
    {"title": "Size", "align": "end", "key": "size", "sortable": False},
    {"title": "Date", "align": "end", "key": "modified", "sortable": False},
]


def sort_by_name(e):
    return e.get("name")


def to_type(e):
    return e.get("type", "")


def to_suffix(e):
    return Path(e.get("name", "")).suffix


# -----------------------------------------------------------------------------


class FileBrowser:
    def __init__(self, home=None, current=None):
        self._enable_groups = True
        self._home_path = Path(home).resolve() if home else Path.home()
        self._current_path = Path(current).resolve() if current else self._home_path

    @property
    def enable_groups(self):
        return self._enable_groups

    @enable_groups.setter
    def enable_groups(self, v):
        self._enable_groups = v

    @property
    def listing(self):
        directories = []
        files = []
        for f in self._current_path.iterdir():
            if f.name[0] == ".":
                continue
            entry = {"name": f.name, "modified": f.stat().st_mtime}
            if f.is_dir():
                directories.append({**entry, **DIRECTORY})
            elif f.is_file():
                files.append({**entry, **FILE, "size": f.stat().st_size})

        # Sort content
        directories.sort(key=sort_by_name)
        files.sort(key=sort_by_name)

        return [{**e, "index": i} for i, e in enumerate([*directories, *files])]

    def open_entry(self, entry):
        entry_type = entry.get("type")
        if entry_type in ["directory", "file"]:
            self._current_path = self._current_path / entry.get("name")
            return entry_type, str(self._current_path)
        if entry_type == "group":
            files = entry.get("files", [])
            return entry, [str(self._current_path / f) for f in files]
        return None

    def goto_home(self):
        self._current_path = self._home_path

    def goto_parent(self):
        self._current_path = self._current_path.parent

    def to_file(self, entry):
        return self._current_path / entry.get("name")

    def open_dataset(self, entry):
        return self._current_path / entry.get("name")

    def open_state(self, entry):
        return self._current_path / entry.get("name")


class FileLoader(v3.VDialog):
    def __init__(
        self,
        **_,
    ):
        super().__init__(v_model=("tomviz_file_loader", False))

        # What the reader node can open, plus state files
        self._file_ext = (*SUPPORTED_EXTENSIONS, *STATE_EXTENSIONS)

        # Initialize file browser
        self._file_browser = FileBrowser(current=Path.cwd())

        # Fill content
        self._update_listing()
        self.selected_entry = None

        # Define UI
        with self, v3.VCard(rounded="lg"):
            style_align_center = "d-flex align-center "
            with v3.VToolbar(density="compact", classes="bg-surface"):
                v3.VToolbarTitle("Open Data File", style="flex: none;")
                v3.VDivider(classes="mx-3", vertical=True)
                v3.VBtn(
                    icon="mdi-home",
                    classes="rounded",
                    variant="tonal",
                    density="comfortable",
                    click=self.goto_home,
                )
                v3.VBtn(
                    icon="mdi-folder-upload-outline",
                    classes="rounded mx-3",
                    variant="tonal",
                    density="comfortable",
                    click=self.goto_parent,
                )
                v3.VTextField(
                    v_model=("tomviz_file_filter", ""),
                    hide_details=True,
                    color="primary",
                    placeholder="filter",
                    density="compact",
                    variant="outlined",
                    classes="mx-2",
                    prepend_inner_icon="mdi-magnify",
                    clearable=True,
                )
            v3.VDivider()
            with v3.VDataTable(
                density="compact",
                fixed_header=True,
                classes="bg-surface-light",
                headers=("tomviz_file_headers", HEADERS),
                items=("tomviz_file_listing", []),
                height="50vh",
                style="user-select: none; cursor: pointer;",
                hover=True,
                search=("tomviz_file_filter",),
                items_per_page=-1,
            ):
                v3.Template(raw_attrs=["v-slot:bottom"])
                with v3.Template(raw_attrs=['v-slot:item="{ index, item }"']):
                    with v3.VDataTableRow(
                        index=("index",),
                        item=("item",),
                        click=(self.select_entry, "[item]"),
                        dblclick=(self.open_entry, "[item]"),
                        classes=(
                            "{ 'bg-grey': item.index === tomviz_file_active, 'cursor-pointer': 1 }",
                        ),
                    ):
                        with v3.Template(raw_attrs=["v-slot:item.name"]):
                            with html.Div(classes=style_align_center):
                                v3.VIcon(
                                    "{{ item.icon }}",
                                    size="small",
                                    classes="mr-2",
                                )
                                html.Div("{{ item.name }}")

                        with v3.Template(raw_attrs=["v-slot:item.size"]):
                            with html.Div(
                                classes=style_align_center + " justify-end",
                            ):
                                html.Div(
                                    "{{ utils.fmt.bytes(item.size, 0) }}",
                                    v_if="item.size",
                                )
                                html.Div(" - ", v_else=True)

                        with v3.Template(raw_attrs=["v-slot:item.modified"]):
                            with html.Div(
                                classes=style_align_center + " justify-end",
                            ):
                                html.Div(
                                    "{{ new Date(item.modified * 1000).toDateString() }}"
                                )

            with v3.VCardActions(classes="pt-3"):
                v3.VBtn(
                    "Load",
                    prepend_icon="mdi-file-upload-outline",
                    color="primary",
                    variant="flat",
                    classes="mr-3 text-none",
                    disabled=("tomviz_file_open_disabled", True),
                    click=(
                        self.open_dataset,
                        "[tomviz_file_listing[tomviz_file_active]]",
                    ),
                )
                v3.VBtn(
                    "Cancel",
                    classes="text-none",
                    color="accent",
                    variant="tonal",
                    click="tomviz_file_loader = false",
                )
                v3.VSpacer()

    def _update_listing(self):
        self.selected_entry = None
        self.state.tomviz_file_active = -1
        self.state.tomviz_file_listing = self._file_browser.listing

    def goto_home(self):
        self._file_browser.goto_home()
        self._update_listing()

    def goto_parent(self):
        self._file_browser.goto_parent()
        self._update_listing()

    def select_entry(self, entry):
        self.selected_entry = entry
        self.state.tomviz_file_active = entry.get("index", 0) if entry else -1
        self.state.tomviz_file_open_disabled = True

        # Update button state
        if (
            entry
            and to_type(entry) in ["file", "group"]
            and to_suffix(entry) in self._file_ext
        ):
            self.state.tomviz_file_open_disabled = False

    def open_entry(self, entry):
        if to_type(entry) == "directory":
            self._file_browser.open_entry(entry)
            self._update_listing()
        else:
            self.open_dataset(entry)

    def open_dataset(self, entry):
        self.state.tomviz_file_loader = False
        file_to_load = self._file_browser.to_file(entry)
        if self.ctx.pipeline.is_state_file(file_to_load):
            self.ctx.pipeline.load_state_file_later(file_to_load)
        else:
            self.ctx.pipeline.load_file(file_to_load)
