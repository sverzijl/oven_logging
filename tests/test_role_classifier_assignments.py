"""Pin the new spatial-reconstruction assignment contract end-to-end via the loader.

Replaces the old ``test_physics_flag_regression.py`` (which tracked the
soon-to-be-killed ``physics_corrected`` / ``core_physics_corrected`` flag race).
After M3a HMS Royal Sovereign the loader's
``_identify_sensor_roles_for_curve`` is a single-call wrapper around
``src.data.spatial_reconstruction.classify`` and the ``physics_corrected``
flag system is deleted entirely.

Contract pinned here:
* Each curve's ``curve_sensor_assignments[i]`` carries the classifier's pick
  for ``core``, ``surface``, ``ambient`` (list), ``lid`` (str | None) and
  exposes the full ``SpatialAssignment`` under ``assignment``.
* No ``physics_corrected`` or ``core_physics_corrected`` keys exist anywhere.
* Manual overrides via ``set_sensor_override(curve, role, sensor)`` win over
  the classifier and propagate into the standardised columns.
* ``clear_sensor_overrides`` reverts to the classifier pick.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHYSICS_FIXTURE = os.path.join(
    REPO_ROOT, 'ProbeData_100098DE_2025-05-30 13_51_07.csv'
)


@pytest.fixture
def loaded_loader():
    assert os.path.exists(PHYSICS_FIXTURE), f"fixture missing: {PHYSICS_FIXTURE}"
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=PHYSICS_FIXTURE)
    return loader


class TestPhysicsCorrectedFlagsAreDeleted:
    """The physics_corrected / core_physics_corrected flag system is gone."""

    def test_no_physics_corrected_key(self, loaded_loader):
        for curve_index in range(loaded_loader.get_curve_count()):
            assigns = loaded_loader.curve_sensor_assignments.get(curve_index, {})
            assert 'physics_corrected' not in assigns, (
                f"Curve {curve_index}: stale physics_corrected key present"
            )
            assert 'core_physics_corrected' not in assigns, (
                f"Curve {curve_index}: stale core_physics_corrected key present"
            )


class TestClassifierAssignmentsStored:
    """The loader stores SpatialAssignment-derived fields per curve."""

    def test_assignment_dict_has_role_keys(self, loaded_loader):
        ci = loaded_loader.current_curve_index
        assigns = loaded_loader.curve_sensor_assignments[ci]
        for key in ('core', 'surface', 'ambient', 'lid'):
            assert key in assigns, f"Curve {ci}: missing {key!r}"
        # ambient is a list (possibly empty); lid is str or None.
        assert isinstance(assigns['ambient'], list)
        assert assigns['lid'] is None or isinstance(assigns['lid'], str)

    def test_assignment_object_preserved(self, loaded_loader):
        ci = loaded_loader.current_curve_index
        assigns = loaded_loader.curve_sensor_assignments[ci]
        assert 'assignment' in assigns, "full SpatialAssignment object missing"
        from src.data.spatial_reconstruction import SpatialAssignment
        assert isinstance(assigns['assignment'], SpatialAssignment)

    def test_core_matches_classifier(self, loaded_loader):
        ci = loaded_loader.current_curve_index
        assigns = loaded_loader.curve_sensor_assignments[ci]
        # Classifier picked T4 on this fixture (per fixture annotation).
        assert assigns['core'] == 'T4', (
            f"Expected T4 from classifier, got {assigns['core']!r}"
        )

    def test_surface_matches_classifier(self, loaded_loader):
        ci = loaded_loader.current_curve_index
        assigns = loaded_loader.curve_sensor_assignments[ci]
        assert assigns['surface'] == 'T7', (
            f"Expected T7 surface, got {assigns['surface']!r}"
        )

    def test_ambient_is_T8(self, loaded_loader):
        ci = loaded_loader.current_curve_index
        assigns = loaded_loader.curve_sensor_assignments[ci]
        assert sorted(assigns['ambient']) == ['T8'], (
            f"Expected ['T8'] ambient, got {assigns['ambient']!r}"
        )


class TestManualOverridesWinOverClassifier:
    """Manual overrides override the classifier and propagate into columns."""

    def test_core_override_wins(self, loaded_loader):
        loader = loaded_loader
        ci = loader.current_curve_index
        # Classifier picks T4; override to T5.
        loader.set_sensor_override(ci, 'core', 'T5')
        assert loader.get_core_sensor(ci) == 'T5'
        # CoreTemperature column reflects override.
        assert np.array_equal(
            loader.data['CoreTemperature'].values,
            loader.data['T5'].values,
        )

    def test_surface_override_wins(self, loaded_loader):
        loader = loaded_loader
        ci = loader.current_curve_index
        loader.set_sensor_override(ci, 'surface', 'T6')
        assert loader.get_surface_sensor(ci) == 'T6'
        assert np.array_equal(
            loader.data['SurfaceTemperature'].values,
            loader.data['T6'].values,
        )

    def test_clear_override_reverts_to_classifier(self, loaded_loader):
        loader = loaded_loader
        ci = loader.current_curve_index
        loader.set_sensor_override(ci, 'core', 'T5')
        loader.clear_sensor_overrides(ci)
        # Reverts to classifier pick (T4 on this fixture).
        assert loader.get_core_sensor(ci) == 'T4'
        # CoreTemperature reverts to T4 series.
        assert np.array_equal(
            loader.data['CoreTemperature'].values,
            loader.data['T4'].values,
        )

    def test_regenerate_columns_is_idempotent(self, loaded_loader):
        loader = loaded_loader
        before = loader.data['SurfaceTemperature'].copy()
        loader._regenerate_standard_columns()
        loader._regenerate_standard_columns()
        after = loader.data['SurfaceTemperature']
        # Surface should still match T7 (classifier pick).
        assert np.array_equal(before.values, after.values)
        assert np.array_equal(
            after.values, loader.data['T7'].values
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
