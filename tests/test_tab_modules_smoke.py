"""Smoke tests for the decomposed app.py modules.

Confirms that each planned tab module and helper module exists, is importable
without raising, and exposes the required callable entry point. These tests
fail fast if a decomposition step breaks an import or forgets to expose the
contract-carrying callable (`render`, `initialize_session_state`, etc.).
"""
import importlib
import sys
from pathlib import Path

import pytest

# Make the oven_logging project root importable so `tabs.*`, `sidebar`, etc.
# resolve when running `pytest` from any directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


TAB_MODULES = [
    "tabs.temperature_profile",
    "tabs.s_curve_analysis",
    "tabs.zone_analysis",
    "tabs.quality_metrics",
    "tabs.heating_analysis",
    "tabs.bakeout_analysis",
    "tabs.recommendations",
    "tabs.curve_comparison",
]


@pytest.mark.parametrize("module_name", TAB_MODULES)
def test_tab_module_exposes_render(module_name):
    mod = importlib.import_module(module_name)
    assert callable(getattr(mod, "render", None)), (
        f"{module_name}.render must be callable"
    )


def test_sidebar_module_exposes_render():
    from sidebar import render as sidebar_render
    assert callable(sidebar_render)


def test_session_state_module_exposes_init():
    from session_state import initialize_session_state
    assert callable(initialize_session_state)


def test_sensor_naming_module_exposes_helpers():
    import sensor_naming
    assert callable(getattr(sensor_naming, "get_dynamic_sensor_names", None))
    assert callable(getattr(sensor_naming, "get_default_sensors", None))
