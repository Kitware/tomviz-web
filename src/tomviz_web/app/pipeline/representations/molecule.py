"""Molecule: the atoms and bonds of a Molecule port, ball and stick, after
the desktop's MoleculeSink.

The payload becomes a ``vtkMolecule`` on the worker (``to_vtk``) and
``vtkMoleculeMapper`` draws it: atoms as spheres colored by element, bonds
as cylinders. The balls are the elements' radii scaled by ``BallRadius``;
the sticks ``StickRadius`` thick. Clips do not cut molecules (nor do they
on the desktop).
"""

from __future__ import annotations

import vtkmodules.vtkDomainsChemistryOpenGL2  # noqa: F401 (the mapper's backend)
from vtkmodules.vtkDomainsChemistry import vtkMoleculeMapper
from vtkmodules.vtkRenderingCore import vtkActor

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.representations.core import (
    Representation,
    RepresentationType,
)
from tomviz_web.app.pipeline.vtk import convert


class MoleculeRepresentation(Representation):
    def __init__(
        self,
        pipeline_manager,
        source_port: data_model.OutputPortModel,
        view: data_model.ViewModel,
    ):
        super().__init__(pipeline_manager.server)

        self.mapper = vtkMoleculeMapper()
        self.mapper.UseBallAndStickSettings()
        self.actor = vtkActor(mapper=self.mapper)
        self.producer >> self.mapper
        self.attach(view.vtk_view)

        self.model = data_model.MoleculeSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **RepresentationType.MOLECULE.model_kwargs,
        )

    def to_vtk(self, payload):
        return convert.to_vtk_molecule(payload)

    @property
    def BallRadius(self):
        """The scale applied to each element's atomic radius."""
        return self.mapper.GetAtomicRadiusScaleFactor()

    @BallRadius.setter
    def BallRadius(self, value):
        self.mapper.SetAtomicRadiusScaleFactor(float(value))

    @property
    def StickRadius(self):
        return self.mapper.GetBondRadius()

    @StickRadius.setter
    def StickRadius(self, value):
        self.mapper.SetBondRadius(float(value))


RepresentationType.MOLECULE.register_class(MoleculeRepresentation)
