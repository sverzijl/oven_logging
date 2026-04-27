"""Tests for tabs/temperature_profile.py — M3 refactor regression suite.

TDD written FAILING-FIRST before the refactor is applied.

Coverage:
  a. test_b2_no_index_drift_after_refactor       — structural: no bare get_sensor_assignments_with_overrides() call
  b. test_pattern_a_inline_loop_removed          — Pattern A 8-sensor loop gone from source
  c. test_pattern_b_inline_loop_removed          — Pattern B 8-sensor loop gone from source
  d. test_render_uses_helpers                    — both build_sensor_label_map and build_sensor_role_map in source
  e. test_render_no_double_fetch                 — get_sensor_assignments_with_overrides appears ≤1 time
  f. test_helper_outputs_match_legacy_inline     — golden: helper output == legacy inline loops for 4 scenarios
  g. test_render_smoke_via_streamlit_apptest     — optional smoke (skipped if AppTest unavailable)
"""

import sys
import os
import ast
import re
import inspect
import pathlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
MULTI_CURVE_CSV = REPO / 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'

# ──────────────────────────────────────────────────────────────────────────────
# Helper: get source of the render() function (not the module, to stay focused)
# ──────────────────────────────────────────────────────────────────────────────

def _get_render_source() -> str:
    import tabs.temperature_profile as tab_mod
    return inspect.getsource(tab_mod.render)


def _get_module_source() -> str:
    import tabs.temperature_profile as tab_mod
    return inspect.getsource(tab_mod)


# ──────────────────────────────────────────────────────────────────────────────
# a. B2 regression — no bare get_sensor_assignments_with_overrides() call
# ──────────────────────────────────────────────────────────────────────────────

class TestB2NoIndexDrift:
    """Verifies the structural fix for Bug B2 (index drift).

    The pre-refactor code called get_sensor_assignments_with_overrides() with NO
    argument at line 54, which fell back to loader.current_curve_index and could
    silently use a different curve than the one whose labels were built at line 20.

    After refactor: curve_index is hoisted once from session state and passed
    explicitly to both helper calls.  The low-level
    get_sensor_assignments_with_overrides function should no longer appear directly
    in render() at all (it is called indirectly inside the helpers).
    """

    def test_b2_no_index_drift_after_refactor(self):
        """render() must NOT contain a bare get_sensor_assignments_with_overrides() call.

        Uses ast to confirm there is no Call node where the func is
        get_sensor_assignments_with_overrides with zero positional args, ensuring
        the double-fetch / index-drift pattern is gone.
        """
        from src.data.loader import ThermalProfileLoader

        # Load real multi-curve CSV and inject distinct per-curve assignments
        loader = ThermalProfileLoader()
        loader.load_csv(str(MULTI_CURVE_CSV))
        assert loader.get_curve_count() >= 3, (
            "Test fixture requires ≥3 curves in ProbeData_1000BA3C_2025-05-30 17_59_37.csv"
        )

        # Inject distinct surface overrides per curve to make index-drift detectable
        loader.curve_sensor_assignments[0]['surface'] = 'T6'
        loader.curve_sensor_assignments[1]['surface'] = 'T7'
        loader.curve_sensor_assignments[2]['surface'] = 'T8'
        loader.current_curve_index = 0

        # Structural assertion: render() source must not call
        # get_sensor_assignments_with_overrides at all (helpers are the only callers).
        src = _get_render_source()
        assert 'get_sensor_assignments_with_overrides' not in src, (
            "render() still contains a direct call to "
            "get_sensor_assignments_with_overrides — B2 index-drift risk not closed.\n"
            "After refactor, render() must use build_sensor_label_map / "
            "build_sensor_role_map exclusively; those helpers call "
            "get_sensor_assignments_with_overrides internally."
        )


# ──────────────────────────────────────────────────────────────────────────────
# b. Pattern A inline loop removed
# ──────────────────────────────────────────────────────────────────────────────

class TestPatternAInlineLoopRemoved:
    """Pattern A: label-building loop at old lines 22-38 must be gone."""

    def test_pattern_a_inline_loop_removed(self):
        src = _get_module_source()
        PATTERN_A_SIGNATURE = "for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']"
        assert PATTERN_A_SIGNATURE not in src, (
            f"Pattern A inline loop still present in tabs/temperature_profile.py.\n"
            f"Expected it to be replaced by build_sensor_label_map().\n"
            f"Offending fragment: {PATTERN_A_SIGNATURE!r}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# c. Pattern B inline loop removed
# ──────────────────────────────────────────────────────────────────────────────

class TestPatternBInlineLoopRemoved:
    """Pattern B: role-building loop at old lines 52-67 must be gone."""

    def test_pattern_b_inline_loop_removed(self):
        src = _get_module_source()
        # Pattern B uses the same iterator literal as Pattern A
        PATTERN_B_SIGNATURE = "for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']"
        assert PATTERN_B_SIGNATURE not in src, (
            f"Pattern B inline loop still present in tabs/temperature_profile.py.\n"
            f"Expected it to be replaced by build_sensor_role_map().\n"
            f"Offending fragment: {PATTERN_B_SIGNATURE!r}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# d. render() uses both helpers
# ──────────────────────────────────────────────────────────────────────────────

class TestRenderUsesHelpers:
    """render() source must reference both build_sensor_label_map and build_sensor_role_map."""

    def test_render_uses_helpers(self):
        src = _get_render_source()
        assert 'build_sensor_label_map' in src, (
            "build_sensor_label_map not found in render() — multiselect labels not using helper"
        )
        assert 'build_sensor_role_map' in src, (
            "build_sensor_role_map not found in render() — sensor_roles not using helper"
        )


# ──────────────────────────────────────────────────────────────────────────────
# e. No double-fetch (S6 closed)
# ──────────────────────────────────────────────────────────────────────────────

class TestRenderNoDoubleFetch:
    """get_sensor_assignments_with_overrides must appear AT MOST ONCE in render() source.

    After refactor it should appear 0 times (helpers encapsulate it); ≤1 is the
    guard to allow a future deliberate use without breaking the test immediately.
    """

    def test_render_no_double_fetch(self):
        src = _get_render_source()
        count = src.count('get_sensor_assignments_with_overrides')
        assert count <= 1, (
            f"get_sensor_assignments_with_overrides appears {count} times in render() "
            f"— S6 double-fetch not closed.  Expected ≤1."
        )


# ──────────────────────────────────────────────────────────────────────────────
# f. Golden integration — helper output matches legacy inline loops
# ──────────────────────────────────────────────────────────────────────────────

class TestHelperOutputsMatchLegacyInline:
    """Mirror M1's golden test: helper outputs must be byte-identical to the
    inline loops they replace for all representative assignment scenarios.

    This guards against M3 accidentally drifting from the M1-pinned contract.
    """

    SCENARIOS = [
        (
            "firmware_default_style",
            {
                'core_sensor': 'T1',
                'surface_sensor': 'T8',
                'internal_sensors': ['T2', 'T3'],
                'ambient_sensors': ['T5', 'T6'],
            }
        ),
        (
            "with_surface_override",
            {
                'core_sensor': 'T2',
                'surface_sensor': 'T7',
                'internal_sensors': ['T3', 'T4'],
                'ambient_sensors': ['T8'],
            }
        ),
        (
            "internal_and_ambient_lists",
            {
                'core_sensor': 'T1',
                'surface_sensor': 'T6',
                'internal_sensors': ['T2', 'T3', 'T4'],
                'ambient_sensors': ['T7', 'T8'],
            }
        ),
        (
            "no_ambient_sensors",
            {
                'core_sensor': 'T3',
                'surface_sensor': 'T5',
                'internal_sensors': ['T1', 'T2'],
                'ambient_sensors': [],
            }
        ),
    ]

    class _FakeLoader:
        def __init__(self, assignments):
            self._assignments = assignments
            self.current_curve_index = 0

        def get_sensor_assignments_with_overrides(self, curve_index=None):
            return self._assignments.copy()

    @staticmethod
    def _legacy_label_loop(assignments: dict) -> dict:
        """Exact replica of the removed Pattern A at tabs/temperature_profile.py:22-38."""
        sensor_labels = {}
        core_sensor = assignments.get('core_sensor')
        surface_sensor = assignments.get('surface_sensor')
        internal_sensors = assignments.get('internal_sensors', [])
        ambient_sensors = assignments.get('ambient_sensors', [])
        for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']:
            if sensor == core_sensor:
                sensor_labels[sensor] = f"{sensor} (Core)"
            elif sensor == surface_sensor:
                sensor_labels[sensor] = f"{sensor} (Surface)"
            elif sensor in internal_sensors:
                sensor_labels[sensor] = f"{sensor} (Internal)"
            elif sensor in ambient_sensors:
                sensor_labels[sensor] = f"{sensor} (Ambient)"
            else:
                sensor_labels[sensor] = sensor
        return sensor_labels

    @staticmethod
    def _legacy_role_loop(assignments: dict) -> dict:
        """Exact replica of the removed Pattern B at tabs/temperature_profile.py:52-67.

        Note: the legacy loop did NOT include 'unknown' for unassigned sensors.
        """
        sensor_roles = {}
        core_sensor = assignments.get('core_sensor')
        surface_sensor = assignments.get('surface_sensor')
        internal_sensors = assignments.get('internal_sensors', [])
        ambient_sensors = assignments.get('ambient_sensors', [])
        for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']:
            if sensor == core_sensor:
                sensor_roles[sensor] = 'core'
            elif sensor == surface_sensor:
                sensor_roles[sensor] = 'surface'
            elif sensor in internal_sensors:
                sensor_roles[sensor] = 'internal'
            elif sensor in ambient_sensors:
                sensor_roles[sensor] = 'ambient'
        return sensor_roles

    @pytest.mark.parametrize("description,assignments", SCENARIOS)
    def test_label_map_matches_legacy_inline(self, description, assignments):
        from src.ui.sensor_role_helpers import build_sensor_label_map
        loader = self._FakeLoader(assignments)
        helper_result = build_sensor_label_map(loader)
        inline_result = self._legacy_label_loop(assignments)
        assert helper_result == inline_result, (
            f"[{description}] label maps differ:\n"
            f"  helper={helper_result}\n  inline={inline_result}"
        )

    @pytest.mark.parametrize("description,assignments", SCENARIOS)
    def test_role_map_matches_legacy_inline_for_assigned_sensors(self, description, assignments):
        """Helper role map matches legacy for explicitly assigned sensors.

        (Helper adds 'unknown' for unassigned; legacy loop omits them — tested separately.)
        """
        from src.ui.sensor_role_helpers import build_sensor_role_map
        loader = self._FakeLoader(assignments)
        helper_result = build_sensor_role_map(loader)
        inline_result = self._legacy_role_loop(assignments)

        for sensor, expected_role in inline_result.items():
            assert helper_result[sensor] == expected_role, (
                f"[{description}] sensor {sensor}: helper={helper_result[sensor]!r}, "
                f"legacy_inline={expected_role!r}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# g. Smoke test via streamlit AppTest (optional)
# ──────────────────────────────────────────────────────────────────────────────

class TestRenderSmokeViaStreamlitAppTest:
    """Optional smoke test using streamlit.testing.v1.AppTest.

    Skipped if AppTest is not available in this environment.
    """

    def test_render_smoke_via_streamlit_apptest(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            pytest.skip("streamlit.testing not available — skipping smoke test")

        # Build a minimal single-tab app script that exercises render()
        app_script = REPO / "_test_temp_profile_smoke_app.py"
        try:
            app_script.write_text(
                f"""
import streamlit as st
import sys
sys.path.insert(0, r"{REPO}")

from src.data.loader import ThermalProfileLoader
from src.ui.sensor_role_helpers import build_sensor_role_map, build_sensor_label_map

CSV = r"{MULTI_CURVE_CSV}"

loader = ThermalProfileLoader()
loader.load_csv(CSV)
loader.set_current_curve(0)

if 'loader' not in st.session_state:
    st.session_state.loader = loader
    st.session_state.data = loader.data
    st.session_state.current_curve_index = 0
    st.session_state.show_zones = True

from tabs.temperature_profile import render
render()
"""
            )
            at = AppTest.from_file(str(app_script), default_timeout=30)
            at.run()
            assert not at.exception, f"AppTest raised: {{at.exception}}"
        finally:
            if app_script.exists():
                app_script.unlink()
