"""Regression test: temperature_profile tab widget keys must be qualified by curve index.

Streamlit persists widget state keyed by the `key` parameter across reruns. A
fixed key causes selections from one curve to bleed into another when the user
switches curves. Each widget must use an f-string key that embeds a curve-index
variable so Streamlit tracks state per-curve independently.
"""
import inspect
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tabs.temperature_profile


class TestWidgetKeyPerCurve:
    """Widget keys in temperature_profile.render() must be curve-index qualified."""

    def _source(self):
        return inspect.getsource(tabs.temperature_profile.render)

    def test_sensor_select_key_is_fstring_per_curve(self):
        src = self._source()
        assert re.search(r'key=f"temp_profile_sensor_select_\{', src), (
            "temp_profile_sensor_select key must be an f-string with an embedded "
            "curve-index variable (e.g. key=f\"temp_profile_sensor_select_{...}\")"
        )

    def test_show_all_key_is_fstring_per_curve(self):
        src = self._source()
        assert re.search(r'key=f"temp_profile_show_all_\{', src), (
            "temp_profile_show_all key must be an f-string with an embedded "
            "curve-index variable (e.g. key=f\"temp_profile_show_all_{...}\")"
        )

    def test_old_fixed_sensor_select_key_is_gone(self):
        src = self._source()
        assert 'key="temp_profile_sensor_select"' not in src, (
            "Old fixed key 'temp_profile_sensor_select' must be removed"
        )

    def test_old_fixed_show_all_key_is_gone(self):
        src = self._source()
        assert 'key="temp_profile_show_all"' not in src, (
            "Old fixed key 'temp_profile_show_all' must be removed"
        )
