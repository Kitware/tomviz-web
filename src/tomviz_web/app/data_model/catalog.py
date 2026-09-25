"""The catalog tree shown in the transform picker. These are not graph nodes:
an item becomes a ``TransformNodeModel`` (and a graph node) only once it is
added to a pipeline."""

from trame.app.dataclass import StateDataModel, Sync, watch


class CatalogFolder(StateDataModel):
    title = Sync(str)
    children = Sync(list, list, has_dataclass=True)
    count = Sync(int)

    def update_count(self):
        local_count = 0
        for child in self.children:
            local_count += child.update_count()
        self.count = local_count
        return local_count


class CatalogItem(StateDataModel):
    title = Sync(str)
    name = Sync(str)
    tags = Sync(list[str], list)
    favorite = Sync(bool, False)
    icon = Sync(str)
    meta = Sync(dict)

    def update_count(self):
        return 1

    @watch("favorite")
    def _on_fav(self, favorite):
        self.server.controller.update_favorite(self.name, favorite)
