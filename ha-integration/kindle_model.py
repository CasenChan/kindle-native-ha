"""Load the HA-independent integration modules (protocol, display, render) without Home Assistant."""
import importlib
from pathlib import Path
import sys
import types

PACKAGE_DIR = Path(__file__).parent / "custom_components/kindle_panel"


def load():
    if "kindle_panel" not in sys.modules:
        package = types.ModuleType("kindle_panel")
        package.__path__ = [str(PACKAGE_DIR)]
        sys.modules["kindle_panel"] = package
    return tuple(importlib.import_module(f"kindle_panel.{name}") for name in ("protocol", "display", "render"))
