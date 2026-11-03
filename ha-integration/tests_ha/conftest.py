"""Runs the integration inside a real Home Assistant core (pytest-homeassistant-custom-component)."""
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def no_frontend(hass):
    """The editor panel needs HA's frontend package; register it as loaded and stub the panel calls."""
    hass.config.components.add("frontend")
    with patch("homeassistant.components.panel_custom.async_register_panel") as register, \
            patch("homeassistant.components.frontend.async_remove_panel"):
        yield register
