"""Tests for B1 (heatmap role-blindness) and S3 (empty-input fragility).

TDD failing-first: tests written BEFORE the implementation changes.
Red -> Green sequence documented in mission damage report.

Tests empirically verify that plot_temperature_gradient_heatmap:
  - accepts a sensor_roles dict and reflects per-curve overrides on the y-axis
  - falls back to firmware-default SENSOR_NAMES when sensor_roles=None
  - raises ValueError with a clear message when no T* columns are present
  - handles partial sensors (missing T5/T6) without crashing
  - the call site in tabs/temperature_profile.py uses build_sensor_role_map

Empty-input contract choice: raise ValueError with message
  "No sensor columns in data; expected at least one of T1..T8."
Rationale: a caller passing an empty DataFrame is a programming error. Returning
a silent empty figure would hide bugs silently; a ValueError with a clear message
surfaces the problem immediately and is testable without inspecting figure internals.
"""
import sys
import os
import re
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import pathlib

from src.data.loader import ThermalProfileLoader
from src.visualization.plots import ThermalPlotter
from src.ui.sensor_role_helpers import build_sensor_role_map
from config.constants import SENSOR_NAMES

REPO = pathlib.Path(__file__).resolve().parents[1]
SINGLE_CURVE_CSV = REPO / 'ProbeData_1000F3C1_2025-05-23 09_11_59.csv'


def make_loader(csv_path: pathlib.Path) -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(str(csv_path))
    return loader


def make_full_dataframe() -> pd.DataFrame:
    """Minimal DataFrame with TimeMinutes and T1..T8 columns."""
    import numpy as np
    rng = range(10)
    data = {'TimeMinutes': list(rng)}
    for i in range(1, 9):
        data[f'T{i}'] = [float(100 + i + t) for t in rng]
    return pd.DataFrame(data)


class TestHeatmapRoleAware:
    """Tests for B1 fix: heatmap reflects per-curve role overrides on y-axis."""

    def test_heatmap_y_axis_reflects_role_override(self):
        """After a manual surface override, the heatmap y-axis label for the overridden
        sensor includes 'Surface', and the previously-assigned surface sensor no longer
        has '(Surface)' in its label.

        Empirical proof: apply the override, build roles via build_sensor_role_map,
        call plotter, inspect fig.data[0].y directly.
        Mirrors Astute evidence (M0 astute-evidence.md §b).
        """
        loader = make_loader(SINGLE_CURVE_CSV)
        curve_idx = loader.current_curve_index

        # Discover the current surface sensor and a candidate for override that is
        # not already the surface or core (to avoid priority-collision).
        before = build_sensor_role_map(loader, curve_idx)
        current_surface = next(
            (s for s in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
             if before[s] == 'surface'),
            None
        )
        # Pick override target: a sensor that is neither surface nor core
        override_target = next(
            s for s in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
            if before[s] not in ('surface', 'core')
        )

        # Apply manual surface override
        loader.set_sensor_override(curve_idx, 'surface', override_target)

        sensor_roles = build_sensor_role_map(loader, curve_idx)
        assert sensor_roles[override_target] == 'surface', (
            f"Pre-condition failed: {override_target} role is "
            f"{sensor_roles[override_target]!r}, expected 'surface'"
        )

        # Build data and call plotter (loader.all_curves[idx]['data'] is the per-curve DataFrame)
        data = loader.all_curves[curve_idx]['data']
        plotter = ThermalPlotter()
        fig = plotter.plot_temperature_gradient_heatmap(data, sensor_roles=sensor_roles)

        y_labels = list(fig.data[0].y)

        # override_target's y-axis label must be the role-known form "T# (Surface)".
        # When a role is known, the shared formatter prefixes with the sensor ID,
        # not the firmware-default SENSOR_NAMES position label, so the heatmap and
        # the multiselect read identically.
        ot_label = next(
            (lbl for lbl in y_labels if lbl.startswith(f"{override_target} ")),
            None,
        )
        assert ot_label is not None, (
            f"No y-axis label starting with '{override_target} ' found. y={y_labels}"
        )
        assert '(Surface)' in ot_label, (
            f"Expected {override_target}'s y-axis label to contain '(Surface)', "
            f"got {ot_label!r}. y={y_labels}"
        )

        # After override, exactly one label should mention '(Surface)' — the
        # override target's. Any prior surface sensor must no longer carry the
        # surface suffix (its role moved or became 'unknown').
        surface_labels = [lbl for lbl in y_labels if '(Surface)' in lbl]
        assert surface_labels == [ot_label], (
            f"Expected exactly one '(Surface)' label after override "
            f"({ot_label!r}); got {surface_labels!r}. y={y_labels}"
        )

        # Cleanup
        loader.clear_sensor_overrides(curve_idx)

    def test_heatmap_y_axis_default_no_roles(self):
        """When sensor_roles=None, y-axis uses firmware-default SENSOR_NAMES labels.

        Backwards compatibility: callers that haven't migrated still get the same
        behaviour as before the fix.
        """
        data = make_full_dataframe()
        plotter = ThermalPlotter()

        fig = plotter.plot_temperature_gradient_heatmap(data, sensor_roles=None)

        y_labels = list(fig.data[0].y)
        expected_labels = [SENSOR_NAMES.get(f'T{i}', f'T{i}') for i in range(1, 9)]

        assert y_labels == expected_labels, (
            f"With sensor_roles=None, expected firmware-default labels:\n"
            f"  expected={expected_labels}\n  got={y_labels}"
        )

        # No role suffix should appear in any label
        for lbl in y_labels:
            assert '(' not in lbl, (
                f"Unexpected role suffix in label {lbl!r} when sensor_roles=None"
            )

    def test_heatmap_empty_input_raises_clear_error(self):
        """DataFrame with TimeMinutes but zero T* columns raises ValueError with a clear message.

        Contract: raise ValueError("No sensor columns in data; expected at least one of T1..T8.")
        Rationale: empty input is a programming error — a clear ValueError surfaces bugs
        immediately instead of silently returning an empty/broken figure.
        """
        data = pd.DataFrame({'TimeMinutes': [1.0, 2.0, 3.0]})
        plotter = ThermalPlotter()

        with pytest.raises(ValueError, match=r"No sensor columns in data"):
            plotter.plot_temperature_gradient_heatmap(data)

    def test_heatmap_partial_sensors(self):
        """DataFrame missing T5 and T6 renders the 6 present sensors without crashing.

        y-axis labels still respect roles for present sensors.
        """
        # Build partial DataFrame: T1-T4, T7, T8 only (T5 and T6 absent)
        import numpy as np
        rng = range(10)
        present_sensors = ['T1', 'T2', 'T3', 'T4', 'T7', 'T8']
        data = pd.DataFrame({'TimeMinutes': list(rng)})
        for s in present_sensors:
            data[s] = [float(100 + t) for t in rng]

        # Build a role map via a fake loader stub so we can test role rendering
        # Without a CSV, we supply a simple role map manually
        sensor_roles = {
            'T1': 'core',
            'T2': 'internal',
            'T3': 'internal',
            'T4': 'internal',
            'T5': 'ambient',   # T5 absent from data — must be skipped gracefully
            'T6': 'ambient',   # T6 absent from data — must be skipped gracefully
            'T7': 'surface',
            'T8': 'unknown',
        }

        plotter = ThermalPlotter()
        # Must not raise
        fig = plotter.plot_temperature_gradient_heatmap(data, sensor_roles=sensor_roles)

        y_labels = list(fig.data[0].y)

        # Exactly 6 labels for the 6 present sensors
        assert len(y_labels) == 6, (
            f"Expected 6 y-axis labels (present sensors only), got {len(y_labels)}: {y_labels}"
        )

        # T1 is core -> label is the role-known form "T1 (Core)"
        assert 'T1 (Core)' in y_labels, (
            f"Expected 'T1 (Core)' in y-axis labels, got {y_labels}"
        )

        # T7 is surface -> label is "T7 (Surface)"
        assert 'T7 (Surface)' in y_labels, (
            f"Expected 'T7 (Surface)' in y-axis labels, got {y_labels}"
        )

        # T8 is 'unknown' -> falls back to SENSOR_NAMES (firmware-default position)
        t8_fallback = SENSOR_NAMES.get('T8', 'T8')
        assert t8_fallback in y_labels, (
            f"Expected unknown-role T8 to fall back to {t8_fallback!r}, got {y_labels}"
        )

        # T5 and T6 are absent from data — neither sensor ID nor SENSOR_NAMES
        # fallback should appear in any label.
        for absent_sensor in ['T5', 'T6']:
            for marker in (absent_sensor, SENSOR_NAMES.get(absent_sensor, absent_sensor)):
                assert not any(lbl.startswith(marker) for lbl in y_labels), (
                    f"Label for absent sensor {absent_sensor} (marker {marker!r}) "
                    f"must not appear in y-axis: {y_labels}"
                )

    def test_heatmap_call_site_uses_helper(self):
        """tabs/temperature_profile.py heatmap call passes sensor_roles= and uses build_sensor_role_map.

        Mirrors the regex-on-source style of tests/test_widget_key_per_curve.py.
        """
        import tabs.temperature_profile as tp_module

        src = inspect.getsource(tp_module.render)

        # 1. build_sensor_role_map must be called in the render function
        assert re.search(r'build_sensor_role_map\s*\(', src), (
            "render() must call build_sensor_role_map() for the heatmap roles. "
            "Not found in source."
        )

        # 2. plot_temperature_gradient_heatmap call must include sensor_roles= keyword arg
        assert re.search(r'plot_temperature_gradient_heatmap\s*\([^)]*sensor_roles\s*=', src), (
            "plot_temperature_gradient_heatmap() call must pass sensor_roles= keyword argument. "
            "Not found in source."
        )

        # 3. build_sensor_role_map must be imported at module level
        module_src = inspect.getsource(tp_module)
        assert re.search(r'from\s+src\.ui\.sensor_role_helpers\s+import\s+.*build_sensor_role_map', module_src), (
            "tabs/temperature_profile.py must import build_sensor_role_map from "
            "src.ui.sensor_role_helpers. Not found in module source."
        )
