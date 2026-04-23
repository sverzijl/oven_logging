"""Regression test for the physics-flag race in ThermalProfileLoader.

The bug: physics-based surface corrections set ``curve_sensor_assignments[ci]
['physics_corrected'] = True`` and rewrite ``SurfaceTemperature`` to the
physics-chosen sensor (e.g. T7 instead of the firmware's T6). Any subsequent
call to ``_generate_standard_columns_for_df()`` on the corrected DataFrame
unconditionally copies ``VirtualSurfaceTemperature`` back into
``SurfaceTemperature``, silently undoing the correction.

This test loads a real CSV known to trigger physics correction, snapshots the
corrected ``SurfaceTemperature`` column, runs the column-regeneration path,
and asserts the corrected values still match. It MUST FAIL on HEAD and pass
once Captain Resolute (T4) fixes the race.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# This fixture is known to trigger a physics correction that swaps the
# firmware's surface pick (T6, max ~100.8 C) for T8 (max ~139.2 C).
PHYSICS_FIXTURE = os.path.join(
    REPO_ROOT, 'ProbeData_100098DE_2025-05-30 13_51_07.csv'
)


class TestPhysicsFlagRegression:
    """The physics-corrected SurfaceTemperature column must survive
    any column regeneration that happens afterwards."""

    def _load_corrected(self):
        assert os.path.exists(PHYSICS_FIXTURE), (
            f"fixture missing: {PHYSICS_FIXTURE}"
        )
        loader = ThermalProfileLoader()
        loader.load_csv(file_path=PHYSICS_FIXTURE)
        # Sanity: physics correction must actually have fired. If this
        # breaks in the future the fixture needs revisiting.
        ci = loader.current_curve_index
        assignments = loader.curve_sensor_assignments.get(ci, {})
        assert assignments.get('physics_corrected') is True, (
            "fixture no longer triggers physics correction - test is toothless"
        )
        assert 'SurfaceTemperature' in loader.data.columns
        assert 'VirtualSurfaceTemperature' in loader.data.columns
        # The correction must have actually changed the column.
        assert not np.array_equal(
            loader.data['SurfaceTemperature'].values,
            loader.data['VirtualSurfaceTemperature'].values,
        ), "physics correction did not diverge from firmware - fixture weak"
        return loader

    def test_generate_standard_columns_for_df_preserves_physics(self):
        """_generate_standard_columns_for_df must not clobber the
        physics-corrected SurfaceTemperature with VirtualSurfaceTemperature."""
        loader = self._load_corrected()
        corrected_surface = loader.data['SurfaceTemperature'].copy()

        loader._generate_standard_columns_for_df(loader.data)

        after = loader.data['SurfaceTemperature']
        assert np.array_equal(corrected_surface.values, after.values), (
            "physics-corrected SurfaceTemperature was overwritten by "
            "_generate_standard_columns_for_df (physics-flag race)"
        )

    def test_regenerate_standard_columns_preserves_physics(self):
        """_regenerate_standard_columns must preserve physics corrections
        even when _sensor_overrides is empty for the current curve."""
        loader = self._load_corrected()
        corrected_surface = loader.data['SurfaceTemperature'].copy()

        loader._regenerate_standard_columns()

        after = loader.data['SurfaceTemperature']
        assert np.array_equal(corrected_surface.values, after.values), (
            "physics-corrected SurfaceTemperature was overwritten by "
            "_regenerate_standard_columns (physics-flag race)"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
