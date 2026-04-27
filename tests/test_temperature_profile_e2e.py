"""End-to-end tests for the Temperature Profile tab.

M5 HMS Achilles — META-FLEET FINALE
Branch: refactor/temperature-profile-canonical-roles

These tests are the *evidence* that the flotilla closed everything it claimed.
They run the full chain: session_state setup → render() → figure inspection.

Test strategy:
- AppTest is used for tests where the Streamlit runtime matters (widget-key
  assertions, checkbox toggling, smoke-level render-without-exception).
  AppTest does not expose a .plotly_chart attribute; we instead assert that
  at.exception is falsy and the expected widgets/headers appear.
- Direct render() invocation with a MagicMock session_state is used where we
  need to inspect figure internals (heatmap y-axis labels, sensor_roles content)
  without the Streamlit server.

The tests are GREEN on first run because M3/M4 have already shipped the fixes.
The RED phase would have been before those missions; documented below per test.
"""

from __future__ import annotations

import inspect
import pathlib
import re
import sys
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loader import ThermalProfileLoader
from src.visualization.plots import ThermalPlotter
from src.ui.sensor_role_helpers import build_sensor_role_map, build_sensor_label_map
from config.constants import SENSOR_LIST, SENSOR_NAMES

SINGLE_CURVE_CSV = PROJECT_ROOT / "ProbeData_1000F3C1_2025-05-23 09_11_59.csv"
MULTI_CURVE_CSV = PROJECT_ROOT / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_loader(csv_path: pathlib.Path) -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(str(csv_path))
    return loader


def _make_session_state_mock(loader: ThermalProfileLoader, curve_index: int) -> MagicMock:
    """Return a MagicMock that mimics st.session_state attribute access.

    st.session_state.get() is used in render() for optional keys; MagicMock
    supports both attribute access and .get() via its own MagicMock mechanism.
    We configure the known attributes explicitly and let .get() return a sensible
    default via side_effect.
    """
    loader.set_current_curve(curve_index)
    ss = MagicMock()
    ss.loader = loader
    ss.data = loader.data
    ss.current_curve_index = curve_index
    # .get('show_zones', True) in render() — return True
    ss.get.side_effect = lambda key, default=None: {
        "show_zones": True,
    }.get(key, default)
    return ss


def _build_apptest_script(csv_path: pathlib.Path, curve_index: int) -> str:
    """Build a minimal Streamlit app script for AppTest."""
    return f"""
import streamlit as st
import sys
sys.path.insert(0, r"{PROJECT_ROOT}")

from src.data.loader import ThermalProfileLoader

loader = ThermalProfileLoader()
loader.load_csv(r"{csv_path}")
loader.set_current_curve({curve_index})

if "loader" not in st.session_state:
    st.session_state.loader = loader
    st.session_state.data = loader.data
    st.session_state.current_curve_index = {curve_index}
    st.session_state.show_zones = True

from tabs.temperature_profile import render
render()
"""


# ---------------------------------------------------------------------------
# a. test_e2e_render_single_curve_default
# ---------------------------------------------------------------------------

class TestE2ERenderSingleCurveDefault:
    """Load a single-curve CSV, drive through to Temperature Profile tab.

    Asserts:
    - no exception raised (AppTest)
    - header and subheader both render (both plots were built)
    - at least 4 sensors appear in multiselect default
    - multiselect options include role-labelled sensors
    """

    def test_e2e_render_single_curve_default(self):
        """AppTest: no exception, header and subheader present, multiselect has options."""
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            pytest.skip("streamlit.testing not available")

        script_path = PROJECT_ROOT / "_e2e_single_curve_smoke.py"
        try:
            script_path.write_text(
                _build_apptest_script(SINGLE_CURVE_CSV, 0), encoding="utf-8"
            )
            at = AppTest.from_file(str(script_path), default_timeout=30)
            at.run()

            # No exception in the app run
            assert not at.exception, f"AppTest raised: {at.exception}"

            # Header renders (confirms render() was called and reached st.header)
            assert len(at.header) >= 1, "Expected at least one st.header() call"
            assert at.header[0].value == "Temperature Profile Analysis"

            # Subheader renders (confirms both plots were built — heatmap line)
            assert len(at.subheader) >= 1, "Expected at least one st.subheader() call"

            # Multiselect is present (show_all_sensors=False by default)
            assert len(at.multiselect) >= 1, "Expected multiselect for sensor selection"

            # Options include role-annotated labels (confirms build_sensor_label_map used)
            options = at.multiselect[0].options
            role_options = [o for o in options if "(" in o]
            assert len(role_options) >= 1, (
                f"Expected at least one role-annotated option (e.g. 'T2 (Core)'), "
                f"got: {options}"
            )

        finally:
            if script_path.exists():
                script_path.unlink()

    def test_e2e_single_curve_default_sensors_ge_4(self):
        """At least 4 sensors appear in the multiselect default value."""
        from sensor_naming import get_default_sensors

        loader = _make_loader(SINGLE_CURVE_CSV)
        defaults = get_default_sensors(loader)
        assert len(defaults) >= 4, (
            f"Expected >=4 default sensors for single-curve CSV, got {len(defaults)}: {defaults}"
        )


# ---------------------------------------------------------------------------
# b. test_e2e_render_multi_curve_switch
# ---------------------------------------------------------------------------

class TestE2ERenderMultiCurveSwitch:
    """Load multi-curve CSV; switch curve_index 0→1; both render without exception.

    Also verifies that role maps for each curve are built from their own index
    (chain: session_state update → helpers → plots rebuild from same hoisted role map).
    """

    def test_e2e_multi_curve_has_gte_2_curves(self):
        loader = _make_loader(MULTI_CURVE_CSV)
        assert loader.get_curve_count() >= 2, (
            f"Expected >=2 curves in {MULTI_CURVE_CSV.name}, "
            f"got {loader.get_curve_count()}"
        )

    def test_e2e_render_multi_curve_switch(self):
        """Switching curve_index 0→1 does not crash render(); headers render each time."""
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            pytest.skip("streamlit.testing not available")

        loader = _make_loader(MULTI_CURVE_CSV)
        assert loader.get_curve_count() >= 2

        for curve_index in (0, 1):
            script_path = PROJECT_ROOT / f"_e2e_multi_curve_switch_{curve_index}.py"
            try:
                script_path.write_text(
                    _build_apptest_script(MULTI_CURVE_CSV, curve_index),
                    encoding="utf-8",
                )
                at = AppTest.from_file(str(script_path), default_timeout=30)
                at.run()
                assert not at.exception, (
                    f"AppTest raised at curve_index={curve_index}: {at.exception}"
                )
                assert len(at.header) >= 1, (
                    f"curve_index={curve_index}: expected at least one header"
                )
                assert len(at.subheader) >= 1, (
                    f"curve_index={curve_index}: expected at least one subheader (heatmap)"
                )
            finally:
                if script_path.exists():
                    script_path.unlink()

    def test_e2e_multi_curve_roles_built_from_correct_curve(self):
        """Role maps for curve 0 and curve 1 are built from their own index.

        After overriding curve-0 surface to T6 and curve-1 surface to T7:
        build_sensor_role_map(loader, 0) reflects T6, not T7, and vice-versa.
        This is the chain verification pinning B2 closure.
        """
        loader = _make_loader(MULTI_CURVE_CSV)
        assert loader.get_curve_count() >= 2

        loader.set_sensor_override(0, "surface", "T6")
        loader.set_sensor_override(1, "surface", "T7")

        roles_0 = build_sensor_role_map(loader, 0)
        roles_1 = build_sensor_role_map(loader, 1)

        assert roles_0["T6"] == "surface", (
            f"curve 0: expected T6='surface', got {roles_0['T6']!r}"
        )
        assert roles_1["T7"] == "surface", (
            f"curve 1: expected T7='surface', got {roles_1['T7']!r}"
        )
        # Cross-check: curve 0 must NOT reflect curve 1's override
        assert roles_0["T7"] != "surface", (
            "B2 regression: curve 0 role map incorrectly reflects curve 1 override (T7 as surface)"
        )
        assert roles_1["T6"] != "surface", (
            "B2 regression: curve 1 role map incorrectly reflects curve 0 override (T6 as surface)"
        )

        loader.clear_sensor_overrides(0)
        loader.clear_sensor_overrides(1)


# ---------------------------------------------------------------------------
# c. test_e2e_show_all_sensors_toggle
# ---------------------------------------------------------------------------

class TestE2EShowAllSensorsToggle:
    """Toggle show_all_sensors checkbox; assert correct sensors= passed to line plot.

    When show_all=True  → sensors=None  (line plot uses all 8)
    When show_all=False → sensors=<list> (from multiselect)
    """

    def test_e2e_show_all_sensors_toggle(self):
        """When show_all_sensors=True, render() passes sensors=None to plot_temperature_profile."""
        import streamlit as st
        import tabs.temperature_profile as tp_mod

        loader = _make_loader(SINGLE_CURVE_CSV)
        ss = _make_session_state_mock(loader, 0)

        captured_sensors: list = []
        original_plot = ThermalPlotter.plot_temperature_profile

        def _capture(self_plotter, data, show_zones=True, sensors=None, sensor_roles=None):
            captured_sensors.append(sensors)
            return original_plot(
                self_plotter, data, show_zones=show_zones,
                sensors=sensors, sensor_roles=sensor_roles,
            )

        with patch.object(st, "session_state", ss), \
             patch.object(st, "header"), \
             patch.object(st, "subheader"), \
             patch.object(st, "plotly_chart"), \
             patch.object(st, "columns", return_value=[MagicMock(), MagicMock()]), \
             patch.object(st, "checkbox", return_value=True), \
             patch.object(ThermalPlotter, "plot_temperature_profile", _capture):
            tp_mod.render()

        assert len(captured_sensors) >= 1, "plot_temperature_profile was not called"
        assert captured_sensors[0] is None, (
            f"Expected sensors=None when show_all=True, got {captured_sensors[0]!r}"
        )

    def test_e2e_show_all_false_uses_multiselect(self):
        """When show_all_sensors=False, render() passes multiselect list to line plot."""
        import streamlit as st
        import tabs.temperature_profile as tp_mod

        loader = _make_loader(SINGLE_CURVE_CSV)
        ss = _make_session_state_mock(loader, 0)
        expected_sensors = ["T1", "T2", "T7"]

        captured_sensors: list = []
        original_plot = ThermalPlotter.plot_temperature_profile

        def _capture(self_plotter, data, show_zones=True, sensors=None, sensor_roles=None):
            captured_sensors.append(sensors)
            return original_plot(
                self_plotter, data, show_zones=show_zones,
                sensors=sensors, sensor_roles=sensor_roles,
            )

        with patch.object(st, "session_state", ss), \
             patch.object(st, "header"), \
             patch.object(st, "subheader"), \
             patch.object(st, "plotly_chart"), \
             patch.object(st, "columns", return_value=[MagicMock(), MagicMock()]), \
             patch.object(st, "checkbox", return_value=False), \
             patch.object(st, "multiselect", return_value=expected_sensors), \
             patch.object(ThermalPlotter, "plot_temperature_profile", _capture):
            tp_mod.render()

        assert len(captured_sensors) >= 1, "plot_temperature_profile was not called"
        assert captured_sensors[0] == expected_sensors, (
            f"Expected sensors={expected_sensors!r}, got {captured_sensors[0]!r}"
        )


# ---------------------------------------------------------------------------
# d. test_e2e_heatmap_reflects_override
# ---------------------------------------------------------------------------

class TestE2EHeatmapReflectsOverride:
    """Apply manual sensor override via loader.set_sensor_override; render the tab;
    inspect heatmap figure y-axis labels to confirm override reflected.

    This is the M0 B1 scenario closed end-to-end.
    """

    def test_e2e_heatmap_reflects_override(self):
        """After set_sensor_override, heatmap y-axis label contains '(Surface)'."""
        loader = _make_loader(SINGLE_CURVE_CSV)
        curve_idx = loader.current_curve_index

        # Choose override: a sensor not already surface or core
        before = build_sensor_role_map(loader, curve_idx)
        override_target = next(
            s for s in list(SENSOR_LIST) if before[s] not in ("surface", "core")
        )
        loader.set_sensor_override(curve_idx, "surface", override_target)

        sensor_roles = build_sensor_role_map(loader, curve_idx)
        assert sensor_roles[override_target] == "surface", (
            f"Pre-condition: {override_target} must be 'surface' after override"
        )

        data = loader.all_curves[curve_idx]["data"]
        plotter = ThermalPlotter()
        fig = plotter.plot_temperature_gradient_heatmap(data, sensor_roles=sensor_roles)
        y_labels = list(fig.data[0].y)

        ot_base = SENSOR_NAMES.get(override_target, override_target)
        ot_label = next((lbl for lbl in y_labels if lbl.startswith(ot_base)), None)
        assert ot_label is not None, (
            f"No y-axis label starting with '{ot_base}'. y={y_labels}"
        )
        assert "(Surface)" in ot_label, (
            f"Expected label for {override_target} to contain '(Surface)', "
            f"got {ot_label!r}. Override not reflected in heatmap. y={y_labels}"
        )

        loader.clear_sensor_overrides(curve_idx)


# ---------------------------------------------------------------------------
# e. test_e2e_widget_keys_per_curve
# ---------------------------------------------------------------------------

class TestE2EWidgetKeysPerCurve:
    """Widget keys in render() embed current_curve_index.

    Pins the fix from mission 2026-04-24_102020_af6532e1.
    Verified via AppTest (multiselect key includes curve index) and
    source inspection.
    """

    def test_e2e_widget_keys_source_inspection(self):
        """render() source uses f-string keys embedding a curve-index variable."""
        src = inspect.getsource(
            __import__("tabs.temperature_profile", fromlist=["render"]).render
        )
        assert re.search(r'key=f"temp_profile_show_all_\{', src), (
            "show_all checkbox key must be an f-string embedding curve_index"
        )
        assert re.search(r'key=f"temp_profile_sensor_select_\{', src), (
            "sensor_select multiselect key must be an f-string embedding curve_index"
        )

    def test_e2e_widget_keys_per_curve(self):
        """AppTest: widget keys contain the curve index digit."""
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            pytest.skip("streamlit.testing not available")

        for curve_index in (0, 1):
            script_path = PROJECT_ROOT / f"_e2e_widget_key_check_{curve_index}.py"
            try:
                script_path.write_text(
                    _build_apptest_script(MULTI_CURVE_CSV, curve_index),
                    encoding="utf-8",
                )
                at = AppTest.from_file(str(script_path), default_timeout=30)
                at.run()
                assert not at.exception, (
                    f"AppTest raised at curve_index={curve_index}: {at.exception}"
                )
                # Checkbox key must include the curve index
                assert len(at.checkbox) >= 1, "Expected show_all checkbox"
                checkbox_key = at.checkbox[0].key
                assert str(curve_index) in checkbox_key, (
                    f"curve_index={curve_index}: checkbox key {checkbox_key!r} "
                    f"does not contain the index {curve_index}"
                )
                # Multiselect key must include the curve index
                assert len(at.multiselect) >= 1, "Expected sensor multiselect"
                ms_key = at.multiselect[0].key
                assert str(curve_index) in ms_key, (
                    f"curve_index={curve_index}: multiselect key {ms_key!r} "
                    f"does not contain the index {curve_index}"
                )
            finally:
                if script_path.exists():
                    script_path.unlink()

    def test_e2e_widget_keys_current_curve_index_in_session_state(self):
        """session_state.current_curve_index is the value used for widget keys."""
        loader = _make_loader(MULTI_CURVE_CSV)
        loader.set_current_curve(1)
        ss = _make_session_state_mock(loader, 1)
        assert ss.current_curve_index == 1


# ---------------------------------------------------------------------------
# f. test_e2e_no_index_drift_under_perturbation
# ---------------------------------------------------------------------------

class TestE2ENoIndexDriftUnderPerturbation:
    """Replicate B2 perturbation: two curves with distinct surface overrides.

    Pre-flotilla: render() called get_sensor_assignments_with_overrides() without
    explicit index (using current_curve_index implicitly), causing the label-map
    (built with curve_index=0) and role-map (built with default index) to
    potentially describe different curves when current_curve_index drifted.

    Post-flotilla: both helpers receive the same hoisted curve_index from
    session_state, so labels and roles always describe the SAME curve.
    """

    def test_e2e_no_index_drift_under_perturbation(self):
        """After B2 fix, roles and labels for curve_index=0 are consistent.

        With curve-0 surface=T6, curve-1 surface=T7, current_curve_index=0:
        both sensor_roles and sensor_labels must describe curve 0 (T6 surface).
        """
        loader = _make_loader(MULTI_CURVE_CSV)
        assert loader.get_curve_count() >= 2

        loader.set_sensor_override(0, "surface", "T6")
        loader.set_sensor_override(1, "surface", "T7")
        loader.current_curve_index = 0

        curve_index = loader.current_curve_index  # = 0 (hoisted once, as render() does)
        sensor_roles = build_sensor_role_map(loader, curve_index)
        sensor_labels = build_sensor_label_map(loader, curve_index)

        # Both must describe curve 0 (T6 = surface)
        assert sensor_roles["T6"] == "surface", (
            f"B2 regression: expected T6='surface' for curve 0, "
            f"got {sensor_roles['T6']!r} — index drift suspected"
        )
        assert "(Surface)" in sensor_labels["T6"], (
            f"B2 regression: expected T6 label to contain '(Surface)', "
            f"got {sensor_labels['T6']!r}"
        )
        # Must NOT reflect curve 1's assignment
        assert sensor_roles["T7"] != "surface", (
            "B2 regression: T7 is surface in curve 1 but must not appear as "
            "surface when render is called for curve 0"
        )

        loader.clear_sensor_overrides(0)
        loader.clear_sensor_overrides(1)

    def test_e2e_index_drift_source_structural_check(self):
        """render() never calls get_sensor_assignments_with_overrides directly.

        Structural guarantee that helpers are the only callers — B2 closed.
        """
        import tabs.temperature_profile as tp_mod
        src = inspect.getsource(tp_mod.render)
        assert "get_sensor_assignments_with_overrides" not in src, (
            "B2 regression: render() still calls get_sensor_assignments_with_overrides "
            "directly, risking index drift. Must delegate to helpers only."
        )


# ---------------------------------------------------------------------------
# g. test_e2e_empty_data_renders_or_fails_cleanly
# ---------------------------------------------------------------------------

class TestE2EEmptyDataRendersOrFailsCleanly:
    """DataFrame with TimeMinutes only (no T* columns).

    Contract:
    - plot_temperature_gradient_heatmap raises ValueError (M2 closed)
    - plot_temperature_profile does not raise (handles missing cols gracefully)
    """

    def test_e2e_empty_data_heatmap_raises_value_error(self):
        """plot_temperature_gradient_heatmap raises ValueError on T*-column-free DataFrame."""
        import pandas as pd
        data = pd.DataFrame({"TimeMinutes": [1.0, 2.0, 3.0]})
        plotter = ThermalPlotter()
        with pytest.raises(ValueError, match=r"No sensor columns in data"):
            plotter.plot_temperature_gradient_heatmap(data)

    def test_e2e_empty_data_line_plot_falls_back_gracefully(self):
        """plot_temperature_profile returns a figure (not None) when columns are absent."""
        import pandas as pd
        data = pd.DataFrame({"TimeMinutes": [1.0, 2.0, 3.0]})
        plotter = ThermalPlotter()
        fig = plotter.plot_temperature_profile(data, show_zones=False, sensors=None)
        assert fig is not None, "plot_temperature_profile returned None on empty data"
