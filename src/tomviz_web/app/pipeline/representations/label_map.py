"""Label Map: the regions of a label volume, after the desktop's
``LabelMapSink``.

Two representations of the same labels. Surface (the default) draws every
region's boundary, extracted by Surface Nets and optionally smoothed without
shrinking (``pipeline/vtk/label_surface.py``), each face in its label's
color. Volume is the volume rendering, with the settings a label map needs
pinned: nearest interpolation (linear interpolation between labels 2 and 6
samples a 4, another label's color), composite blending (the other modes
compute label numbers no voxel carries) and a half-voxel ray step.

The labels come from a label table. A ``LabelMap`` port has one, shared by
every sink reading it and projected onto the port's color map (see
``OutputPortModel``). A plain integer volume (a segmentation read from a
file) is adopted: the sink scans it into a table of its own and colors
through its own color map, so the other sinks on the port keep their look.
A sink coloring through its own map gets the table projected onto it too.

Hiding a label only re-selects faces of the extracted mesh and a color edit
only rewrites face colors; the volume is read again (in the background)
only for new data, a new smoothing or a switch to Surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkCommonDataModel import vtkPolyData
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkProperty

from tomviz_web.app import data_model
from tomviz_web.app.pipeline.representations.core import (
    RepresentationType,
    set_mapper_clipping_planes,
)
from tomviz_web.app.pipeline.representations.volume import VolumeRepresentation
from tomviz_web.app.pipeline.vtk.label_surface import (
    MAX_SMOOTHING,
    color_label_surface,
    extract_label_mesh,
    select_label_faces,
)
from tomviz_web.app.utils import labels

if TYPE_CHECKING:
    from tomviz_web.app.data_model import LabelTableModel

REPRESENTATIONS = ("Surface", "Volume")
DEFAULT_SMOOTHING = 16
# Samples missing a label's boundary shell are lit by ambient light alone;
# a floor keeps them a dimmer shade of their label rather than black.
AMBIENT_FLOOR = 0.3


FLOATING_POINT = "Floating point values are not labels: a label map needs integers."
TOO_WIDE = (
    f"The values span more than {labels.MAX_LABELS:,} integers, too many to be labels."
)


@dataclass
class PreparedLabels:
    """What the worker found in new data: the array read, its labels
    (``(pairs, truncated, supported)``), whether a plain volume could be
    adopted, and the surface when it was due."""

    array: str
    scan: tuple
    adoptable: bool
    mesh: vtkPolyData | None = None
    smoothing: int = 0


class LabelMapRepresentation(VolumeRepresentation):
    TYPE = RepresentationType.LABEL_MAP

    def __init__(self, pipeline_manager, source_port, view):
        # Set up before the volume's constructor, which attaches the props
        # and hides them through set_visible.
        self._representation = "Surface"
        self._shown = False
        self._smoothing = DEFAULT_SMOOTHING
        self.surface_property = vtkProperty()
        self.surface_property.SetAmbient(0.1)
        self.surface_property.SetDiffuse(0.9)
        self.surface_property.SetSpecular(0.2)
        self.surface_property.SetSpecularPower(30.0)
        self.surface_property.SetRepresentationToSurface()
        # Colors are written per face (color_label_surface), taken as is.
        self.surface_mapper = vtkPolyDataMapper()
        self.surface_mapper.SetScalarModeToUseCellData()
        self.surface_mapper.SetColorModeToDirectScalars()
        self.surface_mapper.ScalarVisibilityOn()
        self.surface_actor = vtkActor(
            mapper=self.surface_mapper, property=self.surface_property
        )
        self.surface_actor.SetVisibility(False)

        self.label_array = ""
        self.unsupported_reason = ""  # why the data has no labels to show
        self.label_table: LabelTableModel | None = None
        self.adopted = False  # the table is the sink's own
        self.adopted_table: LabelTableModel | None = None
        self._restored_adopted: dict | None = None  # a state file's
        self._table_unsubscribe = None
        self._mesh: vtkPolyData | None = None
        self._mesh_key = None  # (image, array, smoothing)
        self._pending_mesh = None  # the key being extracted
        self._surface: vtkPolyData | None = None
        self._surface_visible = None  # the labels it shows

        super().__init__(pipeline_manager, source_port, view)
        self.fine_sampling = True
        self.property.SetInterpolationTypeToNearest()

    def create_model(self, source_port, view):
        return data_model.LabelMapSinkNodeModel(
            self.server,
            source_port=source_port,
            view=view,
            representation=self,
            **self.TYPE.model_kwargs,
        )

    @property
    def label(self) -> str:
        return self.model.label if self.model is not None else "Label Map"

    # ---- props -------------------------------------------------------------------

    @property
    def props(self):
        return (*super().props, self.surface_actor)

    def set_visible(self, visible: bool):
        """The volume props show in Volume, the surface in Surface."""
        self._shown = bool(visible)
        super().set_visible(self._shown and self._representation == "Volume")
        self._show_surface()

    def _show_surface(self):
        surface = self._surface
        self.surface_actor.SetVisibility(
            self._shown
            and self._representation == "Surface"
            and surface is not None
            and surface.GetNumberOfCells() > 0
        )

    def set_clipping_planes(self, planes) -> bool:
        planes = list(planes)
        changed = super().set_clipping_planes(planes)
        return set_mapper_clipping_planes(self.surface_mapper, planes) or changed

    # ---- pinned volume settings ------------------------------------------------------

    @property
    def InterpolationType(self):
        return "Nearest"

    @InterpolationType.setter
    def InterpolationType(self, _value):
        self.property.SetInterpolationTypeToNearest()

    @property
    def BlendMode(self):
        return "Composite"

    @BlendMode.setter
    def BlendMode(self, _value):
        VolumeRepresentation.BlendMode.fset(self, "Composite")

    # ---- settings ----------------------------------------------------------------------

    @property
    def Representation(self):
        return self._representation

    @Representation.setter
    def Representation(self, value):
        value = value if value in REPRESENTATIONS else "Surface"
        if value == self._representation:
            return
        self._representation = value
        self.set_visible(self._shown)
        self.update_surface()

    @property
    def SurfaceSmoothing(self):
        return self._smoothing

    @SurfaceSmoothing.setter
    def SurfaceSmoothing(self, value):
        smoothing = min(max(int(value), 0), MAX_SMOOTHING)
        if smoothing != self._smoothing:
            self._smoothing = smoothing
            self.update_surface()

    @property
    def SurfaceOpacity(self):
        return self.surface_property.GetOpacity()

    @SurfaceOpacity.setter
    def SurfaceOpacity(self, value):
        self.surface_property.SetOpacity(min(max(float(value), 0.0), 1.0))

    # ---- data ------------------------------------------------------------------------

    def _array_of(self, image) -> str:
        """The array the labels are read from: the one the color map shows
        (what the volume renders), else the active scalars."""
        point_data = image.GetPointData()
        name = self.rendered_array
        if name and point_data.GetArray(name) is not None:
            return name
        scalars = point_data.GetScalars()
        if scalars is not None:
            return scalars.GetName() or ""
        return point_data.GetArrayName(0) or ""

    def prepare(self, image):
        """Worker thread: scan the labels, and extract the surface when it
        is showing."""
        array = self._array_of(image)
        vtk_array = image.GetPointData().GetArray(array) if array else None
        if vtk_array is None or vtk_array.GetNumberOfComponents() != 1:
            return PreparedLabels(array, ([], False, vtk_array is None), False)
        values = vtk_to_numpy(vtk_array)
        if not labels.is_label_dtype(values.dtype):
            return PreparedLabels(array, ([], False, False), False)
        pairs, truncated = labels.scan_labels(values)
        span = (pairs[0][0], pairs[-1][0]) if pairs and not truncated else None
        adoptable = labels.can_interpret_as_label_map(values.dtype, span)
        prepared = PreparedLabels(array, (pairs, truncated, True), adoptable)
        if self._representation == "Surface":
            regions = [value for value, _ in pairs if value != labels.BACKGROUND]
            prepared.smoothing = self._smoothing
            prepared.mesh = extract_label_mesh(image, array, regions, self._smoothing)
        return prepared

    def set_input(self, image, prepared=None):
        super().set_input(image, prepared)
        if prepared is None:
            prepared = self.prepare(image)
        self.label_array = prepared.array
        # The worker's mesh first: reconciling the table redraws the surface
        if prepared.mesh is not None:
            self._mesh = prepared.mesh
            self._mesh_key = (image, prepared.array, prepared.smoothing)
            self._pending_mesh = None
            self._surface = None
        self._take_labels(prepared)
        self._apply_volume_look()
        self.update_surface()

    def clear_input(self):
        super().clear_input()
        self._show_surface()

    def _take_labels(self, prepared: PreparedLabels):
        """Use the port's table, or adopt a plain integer volume."""
        port = self.model.source_port if self.model is not None else None
        supported = prepared.scan[2]
        self.unsupported_reason = "" if supported else FLOATING_POINT
        if port is not None and port.is_label_map:
            table = port.ensure_label_table()
            if not table.scanned:  # data that reached the sink undescribed
                table.reconcile(prepared.scan)
            self._use_table(table, adopted=False)
        elif prepared.adoptable:
            if self.adopted_table is None:
                self.adopted_table = data_model.LabelTableModel(self.server)
                if self._restored_adopted:
                    self.adopted_table.load(self._restored_adopted)
                    self._restored_adopted = None
            self._use_table(self.adopted_table, adopted=True)
            self.adopted_table.reconcile(prepared.scan)
            # The bands go on the sink's own map, not the one the port's
            # plain volume shares with every other sink reading it.
            if not self.model.use_internal_color_opacity:
                self.model.use_internal_color_opacity = True
        else:
            # Nothing to show; an adopted table waits for integer data
            # again with the user's names and colors.
            if supported:
                self.unsupported_reason = TOO_WIDE
            self._use_table(None, adopted=False)

    def _use_table(self, table: LabelTableModel | None, adopted: bool):
        self.adopted = adopted
        if table is not self.label_table:
            if self._table_unsubscribe is not None:
                self._table_unsubscribe()
                self._table_unsubscribe = None
            self.label_table = table
            if table is not None:
                self._table_unsubscribe = table.on_change(self._on_labels_changed)
            self._surface = None
        self.project_labels()
        if self.model is not None:
            self.model.pull_status()

    def restore_adopted_labels(self, table: dict):
        """A state file's adopted table: names, colors and visibility for
        when the data arrives."""
        if self.adopted_table is not None:
            self.adopted_table.load(table)
        else:
            self._restored_adopted = table

    def _apply_volume_look(self):
        """The ambient floor, once, so the user's own lighting survives
        later executions; through the model, which pushes right after."""
        model = self.model
        if model is None or model.volume_look_applied:
            return
        model.Ambient = max(model.Ambient, AMBIENT_FLOOR)
        model.volume_look_applied = True

    # ---- labels ------------------------------------------------------------------------

    def project_labels(self):
        """Show the table through the sink's own color map when it colors
        through it (the port projects onto its shared map itself)."""
        model = self.model
        table = self.label_table
        if model is None or table is None or not table.labels:
            return
        internal = getattr(model, "_internal_color_opacity", None)
        if model.use_internal_color_opacity and internal is not None:
            internal.load_labels(table.labels)

    def _on_labels_changed(self):
        self.project_labels()
        self.update_surface()
        if self.model is not None:
            self.model.render()

    # ---- surface ----------------------------------------------------------------------

    def update_surface(self):
        """Bring the surface up to date: a new mesh (in the background) for
        new data or smoothing, new faces for a visibility change, new
        colors always."""
        table = self.label_table
        image = self.image
        if (
            self._representation != "Surface"
            or table is None
            or image is None
            or not table.supported
        ):
            self._show_surface()
            return
        key = (image, self.label_array, self._smoothing)
        if key != self._mesh_key:
            self._request_mesh(key, labels.region_labels(table.labels))
            return
        visible = labels.visible_labels(table.labels)
        if self._surface is None or visible != self._surface_visible:
            self._surface = select_label_faces(self._mesh, visible)
            self._surface_visible = visible
            self.surface_mapper.SetInputData(self._surface)
        color_label_surface(self._surface, table.labels)
        self._show_surface()

    def _request_mesh(self, key, regions):
        if key == self._pending_mesh:
            return
        self._pending_mesh = key
        image, array, smoothing = key

        def done(mesh):
            if key != self._pending_mesh:
                return  # superseded by newer data or another smoothing
            self._pending_mesh = None
            self._mesh, self._mesh_key, self._surface = mesh, key, None
            self.update_surface()
            if self.model is not None:
                self.model.render()

        # data_model imports this package: reach the helper at call time
        data_model.port.run_in_background(
            lambda: extract_label_mesh(image, array, regions, smoothing), done
        )

    @property
    def surface(self) -> vtkPolyData | None:
        """The faces showing (None until extracted)."""
        return self._surface


RepresentationType.LABEL_MAP.register_class(LabelMapRepresentation)
