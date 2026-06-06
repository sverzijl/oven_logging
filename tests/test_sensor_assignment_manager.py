"""Characterisation tests for automatic sensor getters and validator.

These tests pin the contract of the four methods targeted by the
SensorAssignmentManager extraction:

  - _get_automatic_core_sensors
  - _get_automatic_surface_sensors
  - _get_automatic_ambient_sensors
  - _validate_sensor_assignments

They are written to pass on the pre-extraction loader (calling the
underscore methods on ThermalProfileLoader directly) AND on the
post-extraction loader (where the loader delegates to
SensorAssignmentManager). Any behavioural drift fails these tests.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

from src.data.loader import ThermalProfileLoader


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_CSV = os.path.join(REPO_ROOT, 'ProbeData_100098DE_2025-05-30 13_51_07.csv')


@pytest.fixture
def loaded_loader():
    """Load a real fixture so curve_sensor_assignments is populated."""
    assert os.path.isfile(FIXTURE_CSV), f"fixture missing: {FIXTURE_CSV}"
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=FIXTURE_CSV)
    return loader


@pytest.fixture
def bare_loader():
    """Loader with no CSV loaded — exercises fallback heuristics."""
    return ThermalProfileLoader()


class TestAutomaticCoreSensors:
    def test_returns_list_of_strings(self, loaded_loader):
        result = loaded_loader._get_automatic_core_sensors(0)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)
        assert len(result) >= 1

    def test_every_item_starts_with_T(self, loaded_loader):
        result = loaded_loader._get_automatic_core_sensors(0)
        assert all(s.startswith('T') for s in result)

    def test_fallback_when_no_curve_assignments(self, bare_loader):
        # No curve_sensor_assignments populated → position-based heuristic.
        result = bare_loader._get_automatic_core_sensors(0)
        assert result == ['T1', 'T2', 'T3', 'T4']

    def test_fallback_when_curve_index_unknown(self, loaded_loader):
        # Curve index not present in assignments → fallback.
        result = loaded_loader._get_automatic_core_sensors(999)
        assert result == ['T1', 'T2', 'T3', 'T4']


class TestAutomaticSurfaceSensors:
    def test_returns_list_of_strings(self, loaded_loader):
        result = loaded_loader._get_automatic_surface_sensors(0)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_every_item_starts_with_T(self, loaded_loader):
        result = loaded_loader._get_automatic_surface_sensors(0)
        assert all(s.startswith('T') for s in result)

    def test_fallback_when_no_curve_assignments(self, bare_loader):
        result = bare_loader._get_automatic_surface_sensors(0)
        assert result == ['T7']

    def test_fallback_when_curve_index_unknown(self, loaded_loader):
        result = loaded_loader._get_automatic_surface_sensors(999)
        assert result == ['T7']

    def test_unknown_assignment_returns_fallback(self):
        loader = ThermalProfileLoader()
        loader.curve_sensor_assignments = {0: {'surface': 'Unknown'}}
        assert loader._get_automatic_surface_sensors(0) == ['T7']

    def test_explicit_assignment_wraps_in_list(self):
        loader = ThermalProfileLoader()
        loader.curve_sensor_assignments = {0: {'surface': 'T5'}}
        assert loader._get_automatic_surface_sensors(0) == ['T5']


class TestAutomaticAmbientSensors:
    def test_returns_list_of_strings(self, loaded_loader):
        result = loaded_loader._get_automatic_ambient_sensors(0)
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    def test_every_item_starts_with_T(self, loaded_loader):
        result = loaded_loader._get_automatic_ambient_sensors(0)
        assert all(s.startswith('T') for s in result)

    def test_fallback_when_no_curve_assignments(self, bare_loader):
        result = bare_loader._get_automatic_ambient_sensors(0)
        assert result == ['T8']

    def test_fallback_when_curve_index_unknown(self, loaded_loader):
        result = loaded_loader._get_automatic_ambient_sensors(999)
        assert result == ['T8']

    def test_explicit_assignment_wraps_in_list(self):
        loader = ThermalProfileLoader()
        loader.curve_sensor_assignments = {0: {'ambient': 'T8'}}
        assert loader._get_automatic_ambient_sensors(0) == ['T8']


class TestCoreInfoAllSensors:
    """After M3a HMS Royal Sovereign the manager is a thin adapter over
    ``curve_sensor_assignments[i]['core']``; the legacy ``core_info``
    histogram and comma-separated multi-sensor strings are gone.
    """

    def test_returns_single_classifier_pick(self):
        loader = ThermalProfileLoader()
        loader.curve_sensor_assignments = {0: {'core': 'T2'}}
        result = loader._get_automatic_core_sensors(0)
        assert result == ['T2']

    def test_falls_back_when_unknown(self):
        loader = ThermalProfileLoader()
        loader.curve_sensor_assignments = {0: {'core': 'Unknown'}}
        result = loader._get_automatic_core_sensors(0)
        # Default neutral fallback when classifier returned nothing useful.
        assert result == ['T1', 'T2', 'T3', 'T4']


class TestValidateSensorAssignments:
    """The validator is side-effect only (prints warnings); it returns None."""

    def test_returns_none_on_empty_df(self, bare_loader):
        df = pd.DataFrame({'TimeMinutes': [0.0, 1.0, 2.0]})
        # Fewer than 3 temp cols → early return.
        assert bare_loader._validate_sensor_assignments(df) is None

    def test_returns_none_with_valid_assignments(self, bare_loader, capsys):
        # Build a DF with sensible ordering: core<surface<ambient.
        n = 20
        times = np.linspace(0, 10, n)
        df = pd.DataFrame({
            'TimeMinutes': times,
            'T1': 20 + 70 * times / 10,   # core: 20→90, ~7°C/min
            'T2': 20 + 70 * times / 10,
            'T3': 20 + 70 * times / 10,
            'T4': 20 + 100 * times / 10,  # surface: 20→120, 10°C/min
            'T5': 20 + 180 * times / 10,  # ambient: 20→200, 18°C/min
        })
        bare_loader.sensor_assignments = {
            'core': 'T1',
            'surface': 'T4',
            'ambient': 'T5',
        }
        # Should not raise.
        result = bare_loader._validate_sensor_assignments(df)
        assert result is None

    def test_runs_on_real_fixture(self, loaded_loader):
        # Just ensure calling on a real curve DataFrame does not raise.
        df = loaded_loader.data
        assert loaded_loader._validate_sensor_assignments(df) is None
