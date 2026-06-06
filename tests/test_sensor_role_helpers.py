"""Tests for src/ui/sensor_role_helpers.py

TDD failing-first: tests written BEFORE the helper module exists.
Red -> Green sequence documented in mission damage report.

Mirrors the inline loops at tabs/temperature_profile.py:22-38 (Pattern A,
label-building) and :52-67 (Pattern B, role-building).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pathlib

from src.data.loader import ThermalProfileLoader
from src.ui.sensor_role_helpers import (
    build_sensor_role_map,
    build_sensor_label_map,
    format_sensor_label,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
SINGLE_CURVE_CSV = REPO / 'ProbeData_1000F3C1_2025-05-23 09_11_59.csv'
MULTI_CURVE_CSV = REPO / 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'

VALID_ROLES = {'core', 'surface', 'internal', 'ambient', 'unknown'}
SENSOR_KEYS = ('T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8')


def make_loader(csv_path: pathlib.Path) -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(str(csv_path))
    return loader


class TestBuildSensorRoleMap:
    """Tests for build_sensor_role_map()."""

    def test_build_sensor_role_map_with_real_csv(self):
        """Returned dict has exactly 8 keys T1..T8, each value in valid role set."""
        loader = make_loader(SINGLE_CURVE_CSV)
        result = build_sensor_role_map(loader)
        assert set(result.keys()) == set(SENSOR_KEYS), (
            f"Expected keys {{T1..T8}}, got {set(result.keys())}"
        )
        for sensor, role in result.items():
            assert role in VALID_ROLES, (
                f"Sensor {sensor} has invalid role {role!r}; expected one of {VALID_ROLES}"
            )

    def test_build_sensor_role_map_respects_override(self):
        """Helper output reflects a manual override, not the firmware default."""
        loader = make_loader(SINGLE_CURVE_CSV)
        curve_idx = loader.current_curve_index

        # Find a sensor that is NOT currently the surface sensor so the override is meaningful
        before = build_sensor_role_map(loader, curve_idx)
        # Pick the first sensor whose role is not 'surface' to use as the override target
        override_target = next(s for s in SENSOR_KEYS if before[s] != 'surface')

        loader.set_sensor_override(curve_idx, 'surface', override_target)
        after = build_sensor_role_map(loader, curve_idx)
        assert after[override_target] == 'surface', (
            f"Expected {override_target} to be 'surface' after override, got {after[override_target]!r}"
        )
        # Clean up
        loader.clear_sensor_overrides(curve_idx)

    def test_build_sensor_role_map_per_curve(self):
        """Distinct per-curve surface overrides yield distinct per-curve results."""
        loader = make_loader(MULTI_CURVE_CSV)
        assert loader.get_curve_count() >= 2, "Expected at least 2 curves in multi-curve CSV"

        # Override surface assignments to known distinct sensors for curve 0 and curve 1
        loader.set_sensor_override(0, 'surface', 'T6')
        loader.set_sensor_override(1, 'surface', 'T7')

        result_0 = build_sensor_role_map(loader, curve_index=0)
        result_1 = build_sensor_role_map(loader, curve_index=1)

        assert result_0['T6'] == 'surface', (
            f"curve 0: expected T6='surface', got {result_0['T6']!r}"
        )
        assert result_1['T7'] == 'surface', (
            f"curve 1: expected T7='surface', got {result_1['T7']!r}"
        )
        # Clean up
        loader.clear_sensor_overrides(0)
        loader.clear_sensor_overrides(1)

    def test_build_sensor_role_map_default_index_uses_loader_state(self):
        """When called with no curve_index, result must match explicit call with current_curve_index."""
        loader = make_loader(MULTI_CURVE_CSV)
        assert loader.get_curve_count() >= 2, "Expected at least 2 curves"

        loader.current_curve_index = 1
        result_default = build_sensor_role_map(loader)
        result_explicit = build_sensor_role_map(loader, 1)

        assert result_default == result_explicit, (
            f"Default index call differs from explicit(1):\n  default={result_default}\n  explicit={result_explicit}"
        )


class TestFormatSensorLabel:
    """Tests for format_sensor_label() — the shared single-sensor formatter.

    This is the canonical "T5 (Core)" string builder used by the multiselect,
    line-plot legend, and heatmap y-axis. Centralising the format pins behaviour
    so all three surfaces stay in lock-step.
    """

    @pytest.mark.parametrize(
        "sensor,role,expected",
        [
            ('T1', 'core', 'T1 (Core)'),
            ('T5', 'core', 'T5 (Core)'),
            ('T7', 'surface', 'T7 (Surface)'),
            ('T2', 'internal', 'T2 (Internal)'),
            ('T8', 'ambient', 'T8 (Ambient)'),
        ],
    )
    def test_known_role_uses_sensor_id_prefix(self, sensor, role, expected):
        """When role is known, label is '{sensor_id} ({Role})' regardless of SENSOR_NAMES."""
        assert format_sensor_label(sensor, role) == expected

    def test_unknown_role_with_no_fallback_returns_sensor_id(self):
        """Unknown role + no fallback → bare sensor ID (multiselect convention)."""
        assert format_sensor_label('T5', 'unknown') == 'T5'

    def test_unknown_role_with_fallback_returns_fallback(self):
        """Unknown role + fallback → fallback (plot-legend convention with SENSOR_NAMES)."""
        assert format_sensor_label('T5', 'unknown', fallback='Middle 1') == 'Middle 1'

    def test_known_role_ignores_fallback(self):
        """A provided fallback never overrides a known role's '{sensor} (Role)' form."""
        assert format_sensor_label('T5', 'core', fallback='Middle 1') == 'T5 (Core)'

    def test_custom_role_format_token(self):
        """role_format placeholder substitutes the capitalised role token."""
        assert format_sensor_label('T1', 'core', role_format='[{role}]') == 'T1 [Core]'
        assert format_sensor_label('T7', 'surface', role_format='- {role}') == 'T7 - Surface'

    def test_label_map_uses_format_sensor_label(self):
        """build_sensor_label_map delegates per-sensor formatting to format_sensor_label.

        Pinning this guards the DRY refactor — any future divergence between the
        two helpers is caught here.
        """
        loader = make_loader(SINGLE_CURVE_CSV)
        curve_idx = loader.current_curve_index
        role_map = build_sensor_role_map(loader, curve_idx)
        label_map = build_sensor_label_map(loader, curve_idx)
        for sensor, role in role_map.items():
            expected = format_sensor_label(sensor, role)
            assert label_map[sensor] == expected, (
                f"build_sensor_label_map[{sensor!r}] == {label_map[sensor]!r} "
                f"diverges from format_sensor_label({sensor!r}, {role!r}) == {expected!r}"
            )


class TestBuildSensorLabelMap:
    """Tests for build_sensor_label_map()."""

    def test_build_sensor_label_map_default_format(self):
        """Labels follow '(Role)' format: 'T1 (Core)', 'T7 (Surface)', etc."""
        # Construct a loader with a fixed assignments dict via override
        loader = make_loader(SINGLE_CURVE_CSV)
        curve_idx = loader.current_curve_index

        # Set up known assignments: T1=core, T7=surface
        loader.set_sensor_override(curve_idx, 'core', 'T1')
        loader.set_sensor_override(curve_idx, 'surface', 'T7')

        labels = build_sensor_label_map(loader, curve_idx)

        assert labels['T1'] == 'T1 (Core)', f"Expected 'T1 (Core)', got {labels['T1']!r}"
        assert labels['T7'] == 'T7 (Surface)', f"Expected 'T7 (Surface)', got {labels['T7']!r}"

        loader.clear_sensor_overrides(curve_idx)

    def test_build_sensor_label_map_internal_and_ambient(self):
        """Internal and Ambient roles also get parenthetical labels."""
        loader = make_loader(SINGLE_CURVE_CSV)
        curve_idx = loader.current_curve_index

        # Get the actual assignments to find what internal/ambient sensors exist
        role_map = build_sensor_role_map(loader, curve_idx)
        labels = build_sensor_label_map(loader, curve_idx)

        # For every sensor with 'internal' or 'ambient' role, label must be "Tx (Role)"
        for sensor, role in role_map.items():
            if role == 'internal':
                expected = f"{sensor} (Internal)"
                assert labels[sensor] == expected, f"Expected {expected!r}, got {labels[sensor]!r}"
            elif role == 'ambient':
                expected = f"{sensor} (Ambient)"
                assert labels[sensor] == expected, f"Expected {expected!r}, got {labels[sensor]!r}"

    def test_build_sensor_label_map_unknown_has_no_suffix(self):
        """Sensors with role 'unknown' map to plain sensor name with no parenthetical.

        After M3a HMS Royal Sovereign the spatial classifier assigns *every*
        sensor a role on real CSVs, so we exercise the unknown-suffix
        contract via a synthetic loader rather than a real file.
        """
        from src.ui.sensor_role_helpers import format_sensor_label

        # Direct unit test of format_sensor_label — guarantees the
        # unknown-role contract regardless of fixture.
        assert format_sensor_label('T9', 'unknown') == 'T9'
        # And via build_sensor_label_map with a contrived loader.
        class _StubLoader:
            def get_sensor_assignments_with_overrides(self, curve_index=None):
                return {
                    'core_sensor': 'T1',
                    'surface_sensor': 'T7',
                    'internal_sensors': ['T1'],
                    'ambient_sensors': ['T8'],
                }
        labels = build_sensor_label_map(_StubLoader())
        # T2..T6 get role 'unknown' under this stub — labels are plain.
        for sensor in ('T2', 'T3', 'T4', 'T5', 'T6'):
            assert labels[sensor] == sensor, (
                f"Expected plain {sensor!r} for unknown role, got {labels[sensor]!r}"
            )

    def test_build_sensor_label_map_custom_format(self):
        """Custom role_format='[{role}]' produces 'T1 [Core]' style labels."""
        loader = make_loader(SINGLE_CURVE_CSV)
        curve_idx = loader.current_curve_index

        loader.set_sensor_override(curve_idx, 'core', 'T1')
        labels = build_sensor_label_map(loader, curve_idx, role_format='[{role}]')

        assert labels['T1'] == 'T1 [Core]', f"Expected 'T1 [Core]', got {labels['T1']!r}"

        loader.clear_sensor_overrides(curve_idx)


class TestHelpersMatchTemperatureProfileLoops:
    """Golden test: helpers must match the inline loops at tabs/temperature_profile.py:22-38 and :52-67.

    Replicates those loops directly against representative assignments dicts
    and asserts helper output is byte-identical.
    """

    # Representative scenarios: (description, assignments_dict)
    # Shapes match get_sensor_assignments_with_overrides() output keys:
    #   core_sensor (str), surface_sensor (str),
    #   internal_sensors (list[str]), ambient_sensors (list[str])
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

    def _inline_role_loop(self, assignments: dict) -> dict:
        """Exact replica of tabs/temperature_profile.py:52-67 (Pattern B)."""
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
            # Note: temperature_profile.py:52-67 does NOT set 'unknown' — helper adds it
        return sensor_roles

    def _inline_label_loop(self, assignments: dict) -> dict:
        """Exact replica of tabs/temperature_profile.py:22-38 (Pattern A)."""
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

    class _FakeLoader:
        """Minimal stub that satisfies build_sensor_role_map's interface."""

        def __init__(self, assignments: dict):
            self._assignments = assignments
            self.current_curve_index = 0

        def get_sensor_assignments_with_overrides(self, curve_index=None):
            return self._assignments.copy()

    @pytest.mark.parametrize("description,assignments", SCENARIOS)
    def test_role_map_matches_inline_loop(self, description, assignments):
        """build_sensor_role_map output agrees with Pattern B for assigned sensors."""
        loader = self._FakeLoader(assignments)
        helper_result = build_sensor_role_map(loader)
        inline_result = self._inline_role_loop(assignments)

        # Check all sensors that the inline loop explicitly assigns
        for sensor, expected_role in inline_result.items():
            assert helper_result[sensor] == expected_role, (
                f"[{description}] sensor {sensor}: helper={helper_result[sensor]!r}, "
                f"inline={expected_role!r}"
            )

        # Sensors NOT in any list must be 'unknown' in helper (helper is more complete)
        for sensor in SENSOR_KEYS:
            if sensor not in inline_result:
                assert helper_result[sensor] == 'unknown', (
                    f"[{description}] unmapped sensor {sensor}: expected 'unknown', "
                    f"got {helper_result[sensor]!r}"
                )

    @pytest.mark.parametrize("description,assignments", SCENARIOS)
    def test_label_map_matches_inline_loop(self, description, assignments):
        """build_sensor_label_map output agrees with Pattern A for all sensors."""
        loader = self._FakeLoader(assignments)
        helper_result = build_sensor_label_map(loader)
        inline_result = self._inline_label_loop(assignments)

        assert helper_result == inline_result, (
            f"[{description}] label maps differ:\n  helper={helper_result}\n  inline={inline_result}"
        )
