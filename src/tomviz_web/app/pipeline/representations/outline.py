"""Outline: the bounding box of the data, with optional grid axes.

As on the desktop, a ``vtkGridAxesActor3D`` over the data bounds adds axis
titles, tick labels and, optionally, grid lines on its faces. The box and
the axes share one ``vtkProperty``, so one color drives both, and every
title and label is drawn in that color too.
"""

from __future__ import annotations

import vtkmodules.vtkRenderingFreeType  # noqa: F401 (text for the axes titles)
from vtkmodules.vtkFiltersModeling import vtkOutlineFilter
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkProperty,
    vtkTextProperty,
)
from vtkmodules.vtkRenderingGridAxes import vtkGridAxesActor3D, vtkGridAxesHelper

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.representations.core import (
    Representation,
    RepresentationType,
)

DEFAULT_COLOR = (0.9, 0.9, 0.9)  # the desktop's off-white
DEFAULT_TITLES = ("X", "Y", "Z")

ALL_LABELS = (
    vtkGridAxesHelper.MIN_X
    | vtkGridAxesHelper.MIN_Y
    | vtkGridAxesHelper.MIN_Z
    | vtkGridAxesHelper.MAX_X
    | vtkGridAxesHelper.MAX_Y
    | vtkGridAxesHelper.MAX_Z
)
ALL_FACES = (
    vtkGridAxesHelper.MIN_XY
    | vtkGridAxesHelper.MIN_YZ
    | vtkGridAxesHelper.MIN_ZX
    | vtkGridAxesHelper.MAX_XY
    | vtkGridAxesHelper.MAX_YZ
    | vtkGridAxesHelper.MAX_ZX
)


class OutlineRepresentation(Representation):
    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server)

        self._visible = False
        self._titles = DEFAULT_TITLES

        self.property = vtkProperty()
        self.extract = vtkOutlineFilter()
        self.mapper = vtkPolyDataMapper()
        self.actor = vtkActor(mapper=self.mapper, property=self.property)
        self.producer >> self.extract >> self.mapper

        # vtkGridAxesActor3D.GetProperty() only reaches one face: give it the
        # outline's property so every face follows the color (the desktop's
        # workaround).
        self.property.SetFrontfaceCulling(True)
        self.property.SetBackfaceCulling(False)
        self.grid_axes = vtkGridAxesActor3D()
        self.grid_axes.SetProperty(self.property)
        self.grid_axes.SetGenerateGrid(False)
        self.grid_axes.SetLabelMask(ALL_LABELS)
        self.grid_axes.SetFaceMask(ALL_FACES)
        self.grid_axes.SetVisibility(False)
        self._show_grid_axes = False

        self.Color = DEFAULT_COLOR
        self.Titles = DEFAULT_TITLES
        self.attach(view.vtk_view)

        self.model = data_model.OutlineSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.OUTLINE.model_kwargs,
        )

    @property
    def props(self):
        return (self.actor, self.grid_axes)

    def set_visible(self, visible: bool):
        self._visible = bool(visible)
        self.actor.visibility = self._visible
        self.grid_axes.SetVisibility(self._visible and self._show_grid_axes)

    def set_input(self, image):
        super().set_input(image)
        self.grid_axes.SetGridBounds(image.GetBounds())

    @property
    def Color(self):
        return tuple(self.property.GetColor())

    @Color.setter
    def Color(self, rgb):
        self.property.SetColor(*rgb)
        for axis in range(6):
            for setter in (
                self.grid_axes.SetTitleTextProperty,
                self.grid_axes.SetLabelTextProperty,
            ):
                text = vtkTextProperty()
                text.SetColor(*rgb)
                setter(axis, text)

    @property
    def ShowGridAxes(self):
        return self._show_grid_axes

    @ShowGridAxes.setter
    def ShowGridAxes(self, show):
        self._show_grid_axes = bool(show)
        self.grid_axes.SetVisibility(self._visible and self._show_grid_axes)

    @property
    def ShowGrid(self):
        return bool(self.grid_axes.GetGenerateGrid())

    @ShowGrid.setter
    def ShowGrid(self, show):
        self.grid_axes.SetGenerateGrid(bool(show))

    @property
    def Titles(self):
        return self._titles

    @Titles.setter
    def Titles(self, titles):
        self._titles = tuple(titles)
        x, y, z = self._titles
        self.grid_axes.SetXTitle(x)
        self.grid_axes.SetYTitle(y)
        self.grid_axes.SetZTitle(z)


RepresentationType.OUTLINE.register_class(OutlineRepresentation)
