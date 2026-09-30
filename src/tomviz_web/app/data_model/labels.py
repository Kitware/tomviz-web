"""The label table of a label map, after the desktop's ``LabelTable``.

A ``LabelMap`` port owns one (``OutputPortModel.label_table``), shared by
every sink reading the port and projected onto the port's color map, so a
Slice or a Volume next to the Label Map shows the same colors. A Label Map
sink reading a plain integer volume adopts the voxels with a table of its
own. Edits go through the methods here, which tell the ``on_change``
listeners at once."""

from __future__ import annotations

from collections.abc import Callable

from trame.app.dataclass import StateDataModel, Sync

from tomviz_web.app.utils import labels


class LabelTableModel(StateDataModel):
    """``labels`` are ``utils.labels`` entries, ascending by value.
    ``truncated``: the data held more than ``labels.MAX_LABELS`` values;
    ``supported``: False for floating point data, which has no labels.
    ``scanned``: the data has been seen (a restored table has names and
    colors but no counts until then)."""

    labels = Sync(list, list)
    truncated = Sync(bool, False)
    supported = Sync(bool, True)
    scanned = Sync(bool, False)

    def __init__(self, server, **kwargs):
        self._listeners: list[Callable[[], None]] = []
        super().__init__(server, **kwargs)

    def on_change(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Call ``callback()`` after every change; returns the unsubscriber."""
        self._listeners.append(callback)

        def unsubscribe():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return unsubscribe

    def _changed(self, entries: list[dict] | None = None):
        if entries is not None:
            self.labels = entries
        for callback in list(self._listeners):
            callback()

    # ---- data ------------------------------------------------------------------

    def reconcile(self, scan):
        """Take a scan (``(pairs, truncated, supported)``, see
        ``scan_image_labels``): the labels present, keeping what the user
        set on those that survive."""
        pairs, truncated, supported = scan
        self.truncated = bool(truncated)
        self.supported = bool(supported)
        self.scanned = True
        self._changed(labels.reconcile(self.labels, pairs))

    # ---- edits -------------------------------------------------------------------

    def _edit(self, value, **fields):
        entries = [
            {**entry, **fields} if entry["value"] == value else entry
            for entry in self.labels
        ]
        if entries != self.labels:
            self._changed(entries)

    def set_visible(self, value, visible: bool):
        self._edit(float(value), visible=bool(visible))

    def set_color(self, value, color: str):
        if isinstance(color, str) and color.startswith("#") and len(color) >= 7:
            self._edit(float(value), color=color[:7].lower())

    def set_name(self, value, name: str):
        self._edit(float(value), name=str(name or "").strip())

    def set_visibility(self, values, visible: bool):
        """Show or hide the labels ``values`` (what a filtered list's Show
        All / Hide All reach)."""
        chosen = {float(v) for v in values}
        entries = [
            {**e, "visible": bool(visible)} if e["value"] in chosen else e
            for e in self.labels
        ]
        if entries != self.labels:
            self._changed(entries)

    def invert_visibility(self, values):
        chosen = {float(v) for v in values}
        self._changed(
            [
                {**e, "visible": not e["visible"]} if e["value"] in chosen else e
                for e in self.labels
            ]
        )

    # ---- state files ---------------------------------------------------------------

    def serialize(self) -> dict:
        return labels.serialize(self.labels)

    def load(self, table: dict):
        """A saved table: names, colors and visibility until the data is
        scanned and reconciles it."""
        entries = labels.deserialize(table or {})
        if entries:
            self._changed(entries)


def scan_image_labels(dataset, name: str):
    """The labels of array ``name`` of a ``Dataset`` (worker thread):
    ``(pairs, truncated, supported)`` for ``LabelTableModel.reconcile``."""
    if name not in dataset.scalars_names:
        return [], False, True
    values = dataset.scalars(name)
    if not labels.is_label_dtype(values.dtype):
        return [], False, False
    pairs, truncated = labels.scan_labels(values)
    return pairs, truncated, True
