"""trame bindings of the application's Vue components (``vue-components/``
at the root of the repository, built into ``widgets/module/serve``).

Depends only on trame and tomviz_pipeline, not on the application, so the
widgets could move to their own package."""

from .pipeline_widget import PipelineWidget

__all__ = ["PipelineWidget"]
