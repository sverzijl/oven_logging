"""Regression test: manual sensor overrides must survive curve switching.

Pins current behaviour so the upcoming refactor (extracting
SensorAssignmentManager, decomposing app.py) does not silently drop
user-applied overrides when ``set_current_curve()`` swaps ``self.data``.
This test MUST pass on HEAD and stay passing through the refactor.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MULTI_CURVE_FIXTURE = os.path.join(
    REPO_ROOT, 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'
)


class TestCurveSwitchingSideEffects:
    """Overrides survive round-trip curve switching."""

    def _loader_with_two_curves(self):
        assert os.path.exists(MULTI_CURVE_FIXTURE), (
            f"fixture missing: {MULTI_CURVE_FIXTURE}"
        )
        loader = ThermalProfileLoader()
        loader.load_csv(file_path=MULTI_CURVE_FIXTURE)
        n = loader.get_curve_count()
        assert n >= 2, (
            f"fixture must have >= 2 curves, got {n}"
        )
        return loader

    def test_override_survives_curve_switch(self):
        loader = self._loader_with_two_curves()
        target_curve = 1  # any non-default curve
        override_sensor = 'T6'

        loader.set_sensor_override(target_curve, 'surface', override_sensor)
        loader.set_current_curve(0)
        loader.set_current_curve(target_curve)

        assignments = loader.get_sensor_assignments_with_overrides(target_curve)
        assert assignments['surface_sensor'] == override_sensor, (
            f"override lost across curve switch: expected "
            f"{override_sensor}, got {assignments['surface_sensor']}"
        )
        assert assignments['has_overrides'] is True
        assert assignments['overrides'].get('surface') == override_sensor

    def test_override_for_non_current_curve_round_trip(self):
        """Setting an override for curve B while curve A is current must
        still be visible after switching to B."""
        loader = self._loader_with_two_curves()
        loader.set_current_curve(0)
        loader.set_sensor_override(1, 'surface', 'T5')

        loader.set_current_curve(1)
        assignments = loader.get_sensor_assignments_with_overrides(1)
        assert assignments['surface_sensor'] == 'T5'
        assert assignments['has_overrides'] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
