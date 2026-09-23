"""trame module serving the built Vue components.

The bundle is built from ``vue-components/`` (``npm run build``), which
writes ``tomviz_widgets.umd.js`` and ``tomviz_widgets.css`` into ``serve/``.
The files are not under revision control."""

from pathlib import Path

from tomviz_trame import __version__

serve_path = str(Path(__file__).with_name("serve").resolve())

BASENAME = f"__tomviz_widgets_{__version__}"

serve = {BASENAME: serve_path}
scripts = [f"{BASENAME}/tomviz_widgets.umd.js"]
styles = [f"{BASENAME}/tomviz_widgets.css"]
vue_use = ["tomviz_widgets"]


def is_built() -> bool:
    """Whether the bundle exists (``npm run build`` in ``vue-components``)."""
    return (Path(serve_path) / "tomviz_widgets.umd.js").exists()
