import importlib.util
from pathlib import Path

DYNAMIC_TEMPLATES = {}
DYNAMIC_UI_PATHS = Path(__file__).parent


def load_gui(server, name):
    module_path = DYNAMIC_UI_PATHS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    DYNAMIC_TEMPLATES[module.NAME] = module.TEMPLATE
    module.UI(server)


def initialize_dynamic_ui(server):
    for file_path in DYNAMIC_UI_PATHS.glob("*.py"):
        if file_path.stem[0] == "_":
            continue
        load_gui(server, file_path.stem)
