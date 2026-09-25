from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path

from loguru import logger
from trame.app import TrameComponent
from trame.decorators import trigger

from tomviz_web.app import data_model, module, ui
from tomviz_web.app.pipelines.vtk import io
from tomviz_web.app.ui.dynamic import DYNAMIC_TEMPLATES


class RepresentationType(Enum):
    def __new__(cls, name: str, label: str):
        obj = object.__new__(cls)
        obj._value_ = name
        obj.label = label
        obj.representation_class = None
        return obj

    CLIP = ("clip.svg", "Clip")
    CONTOUR = ("contour.svg", "Contour")
    MOLECULE = ("molecule.svg", "Molecule")
    OUTLINE = ("outline.svg", "Outline")
    RULER = ("ruler.svg", "Ruler")
    SCALE_CUBE = ("scale-cube.svg", "Scale Cube")
    SLICE = ("slice.svg", "Slice")
    THRESHOLD = ("threshold.svg", "Threshold")
    VOLUME = ("volume.png", "Volume")

    @property
    def icon(self):
        return f"{module.BASENAME}/assets/representations/{self.value}"

    @property
    def props(self):
        return {
            "label": self.label,
            "name": self.name,
            "icon": self.icon,
        }

    def register_class(self, klass):
        self.representation_class = klass

    def create_representation(
        self,
        pipeline_manager,
        source_proxy: data_model.SourceProxy,
        view: data_model.WindowInternalState,
    ):
        if self.representation_class is None:
            msg = f"No representation found for {self.label}"
            raise ValueError(msg)

        return self.representation_class(pipeline_manager, source_proxy, view)


class PipelineManager(TrameComponent):
    def __init__(self, server=None):
        super().__init__(server=server)
        self.representations = {}  # { view_id: [rep, ...] }
        self.views = {}
        self.pending_tasks = set()
        self.tree = data_model.Pipeline(self.server)
        self.state.property_templates = []
        self.state.active_view_id = None
        self.state.active_data_id = None
        self.state.active_representation_id = None
        self.state.active_color_opacity_id = None

        self.tree.watch(["active_node"], self._on_active_change)

        if self.server.hot_reload:
            self.server.controller.on_server_reload.add(self.refresh_views_later)

    def __del__(self):
        self.tree.clear_watchers()

    def load_file(self, file_path: str | Path) -> str | None:
        file_path = Path(file_path).resolve()

        if not file_path.exists():
            return None

        # Create reader and track it
        reader = io.Reader(file_path)
        dataset = data_model.SourceProxy(self.server, name=file_path.stem)
        dataset.algo = reader
        dataset.update_info()

        self.add_default_color_opacity(dataset._id)
        self.add_default_representations(dataset._id, self.state.active_view_id)

        data_model.get_instance(self.state.active_view_id).widget_view.reset_camera()

        # Update tracking
        self.tree.children = [*self.tree.children, dataset]

        # make new data node active by default
        self.tree.active_node = [dataset._id]

        return dataset._id

    def add_view(self) -> str:
        view = ui.RenderWindow(self.server)
        logger.debug("Add view {} vs {}", view.local_state._id, view.vtk_id)
        self.views[view.local_state._id] = view
        self.ctx.dock_view.add_panel(
            view.vtk_id,
            "3D View",
            view.tpl_name,
            tabComponent="tomviz-dockview-tab",
            params={
                "templateName": view.tpl_name,
                "viewState": view.local_state._id,
            },
        )
        return view.local_state._id

    @trigger("remove_view")
    def remove_view(self, view_id: str):
        logger.debug("remove view {}", view_id)
        # FIXME need more
        # - remove representations of view
        # - remove view in self.views
        view = self.views.get(view_id)
        if view:
            view.vtk_view.clear()
            self.ctx.dock_view.remove_panel(view.vtk_id)
            self.state.active_view_id = None
            del self.representations[view_id]
            del self.views[view.local_state._id]

    def activate_panel(self, panel_id):
        logger.debug("activate_panel {}", panel_id)
        found = False
        for view_id, view in self.views.items():
            if view.vtk_id == panel_id:
                self.state.active_view_id = view_id
                found = True

        if not found:
            self.state.active_view_id = None

    def refresh_views_later(self, **_):
        task = asyncio.create_task(self._refresh_views())
        self.pending_tasks.add(task)
        task.add_done_callback(self.pending_tasks.discard)

    async def _refresh_views(self):
        await asyncio.sleep(0.1)
        self.refresh_views()

    def refresh_views(self, **_):
        """Register all views into dockview"""
        for view in self.views.values():
            self.ctx.dock_view.add_panel(
                view.vtk_id,
                "3D View",
                view.tpl_name,
                tabComponent="tomviz-dockview-tab",
                params={
                    "templateName": view.tpl_name,
                    "viewState": view.local_state._id,
                },
            )

    def add_default_color_opacity(self, data_id: str):
        logger.debug("data_id: {}", data_id)
        data_obj: data_model.SourceProxy = data_model.get_instance(data_id)

        if not data_obj.color_opacity:
            data_obj.color_opacity = data_model.create_default_color_opacity(data_obj)

    def add_default_representations(self, data_id: str, view_id: str):
        self.add_representation(data_id, view_id, RepresentationType.OUTLINE.name)
        self.add_representation(data_id, view_id, RepresentationType.SLICE.name)

    def add_representation(self, data_id: str, view_id: str, type: str) -> str | None:
        logger.debug("data_id: {}, view_id: {}, type: {}", data_id, view_id, type)
        data_obj = data_model.get_instance(data_id)
        view_obj = data_model.get_instance(view_id)

        if view_id not in data_obj.expand_representations:
            data_obj.expand_representations = [
                *data_obj.expand_representations,
                view_id,
            ]

        if data_obj.representations is None:
            data_obj.representations = {}

        if view_id not in data_obj.representations:
            data_obj.representations[view_id] = []

        new_reps = {**data_obj.representations}
        rep = RepresentationType[type].create_representation(self, data_obj, view_obj)
        if rep:
            self.representations.setdefault(view_id, []).append(rep)
            new_reps[view_id] = [
                *new_reps[view_id],
                rep.props._id,
            ]
            data_obj.representations = new_reps

            return rep.props._id

        return None

    def add_operator(
        self,
        data_id: str,
        operator_name: str,
        icon: str,
        meta: dict,
        **_,
    ):
        logger.critical(
            "Add Operator: {}, {}, {}, {}", data_id, operator_name, icon, meta
        )
        # input = data_model.get_instance(data_id)
        # operator_proxy = simple.TomvizVolumeTransform(Input=input.proxy)
        # operator_filter = data_model.Operator(
        #     self.server,
        #     name=operator_name,
        #     proxy=operator_proxy,
        #     color_opacity=data_model.create_default_color_opacity(input),
        #     icon=icon,
        #     data=operators.to_operator_data(self.server, meta),
        # )

        # input.pipelines = [*input.pipelines, operator_filter]

    def _on_active_change(self, active_node: list[str]):
        logger.debug("active_node: {}", active_node)
        with self.state as s:
            if active_node:
                obj = data_model.get_instance(active_node[0])
                color_opacity = getattr(obj, "color_opacity", None)
                s.active_color_opacity_id = color_opacity._id if color_opacity else ""
                if isinstance(obj, data_model.Operator):
                    rep_tpl = DYNAMIC_TEMPLATES.get("operator")
                    s.active_data_id = active_node[0]
                    s.active_representation_id = None
                    s.property_templates = [rep_tpl] if rep_tpl else []
                elif isinstance(obj, data_model.SourceProxy):
                    s.active_data_id = active_node[0]
                    s.active_representation_id = None
                    s.property_templates = []
                elif isinstance(obj, data_model.REPRESENTATIONS):
                    rep_tpl = DYNAMIC_TEMPLATES.get(obj.name)
                    s.active_data_id = obj.input._id
                    s.active_representation_id = active_node[0]
                    s.active_view_id = obj.view._id
                    s.property_templates = [rep_tpl] if rep_tpl else []
            else:
                s.active_data_id = None
                s.active_representation_id = None
                s.active_view_id = None
                s.property_templates = []
                s.active_color_opacity_id = ""

    def reset_color_range(self, rep_id):
        data_model.get_instance(rep_id).reset_color_range()

    def use_color_range_as_bounds(self, rep_id):
        data_model.get_instance(rep_id).use_color_range_as_bounds()
