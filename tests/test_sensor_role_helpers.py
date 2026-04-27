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
from src.ui.sensor_role_helpers import build_sensor_role_map, build_sensor_label_map

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
        """Sensors with role 'unknown' map to plain sensor name with no parenthetical."""
        loader = make_loader(SINGLE_CURVE_CSV)
        curve_idx = loader.current_curve_index

        role_map = build_sensor_role_map(loader, curve_idx)
        labels = build_sensor_label_map(loader, curve_idx)

        unknown_sensors = [s for s, r in role_map.items() if r == 'unknown']
        assert len(unknown_sensors) > 0, (
            "No 'unknown' sensors found — adjust fixture or use a loader with fewer assignments"
        )
        for sensor in unknown_sensors:
            assert labels[sensor] == sensor, (
                f"Expected plain '{sensor}' for unknown role, got {labels[sensor]!r}"
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
