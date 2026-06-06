"""Multi-curve switching invariant: LidTemperature column lifecycle.

CLAUDE.md flags curve switching as a fragile area. This test pins the
behaviour: when one curve has lid contact and another does not, switching
back-and-forth must add/remove the ``LidTemperature`` column on the *current*
curve's DataFrame correctly. No NaN columns; no stale columns.

Approach
--------
We run ``_apply_standard_columns`` directly on synthetic per-curve DataFrames
because constructing a multi-curve loader fixture with one lidded + one
non-lidded bake is expensive and orthogonal to the column-lifecycle invariant
under test. The synthetic ``_build_lid_touch`` builder from
``tests/fixtures/curve_boundary_cases.py`` produces a clean lidded profile;
``_build_full_immersion`` produces a no-lid profile.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader
from src.data.spatial_reconstruction import classify
from tests.fixtures.curve_boundary_cases import (
    _lid_touch_df,
    _full_immersion_df,
)


def _populate_loader_two_curves(lidded_first: bool = True) -> ThermalProfileLoader:
    """Build a ThermalProfileLoader with two synthetic curves: one lidded,
    one full-immersion (no lid). Bypasses CSV loading.
    """
    loader = ThermalProfileLoader()
    loader.metadata = {'sample_period_ms': 5000}

    # Slice down to active-bake regions per fixture annotations.
    lidded_df = _lid_touch_df.iloc[35:130].reset_index(drop=True).copy()
    immersion_df = _full_immersion_df.iloc[44:130].reset_index(drop=True).copy()

    if lidded_first:
        curves = [lidded_df, immersion_df]
    else:
        curves = [immersion_df, lidded_df]

    for i, df in enumerate(curves):
        a = classify(df, sample_period_ms=5000)
        loader.curve_sensor_assignments[i] = {
            'core': a.core,
            'surface': a.surface,
            'ambient': list(a.ambient),
            'lid': a.lid,
            'firmware_diagnostic': a.firmware_diagnostic,
            'core_position_normalised': a.core_assignment.position_normalised
            if a.core_assignment else None,
            'surface_position_normalised': a.surface_assignment.position_normalised
            if a.surface_assignment is not None else None,
            'ambient_position_normalised': [
                p.position_normalised for p in a.ambient_assignments
            ],
            'lid_position_normalised': a.lid_assignment.position_normalised
            if a.lid_assignment is not None else None,
            'model_used': a.model_used,
            'assignment': a,
        }
        loader.all_curves.append({
            'data': df,
            'start_idx': 0,
            'end_idx': len(df) - 1,
            'samples': len(df),
            'duration': float(df['Timestamp'].iloc[-1] - df['Timestamp'].iloc[0]),
            'max_temp': float(df[['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']]
                              .max().max()),
            'curve_number': i + 1,
            'start_time': float(df['Timestamp'].iloc[0]),
            'end_time': float(df['Timestamp'].iloc[-1]),
        })

    return loader


class TestLidColumnAddsAndRemovesOnSwitching:
    """Column lifecycle: appears on lidded, disappears on unlidded."""

    def test_lidded_curve_has_column_and_unlidded_does_not(self):
        loader = _populate_loader_two_curves(lidded_first=True)

        # Apply standard columns to each curve.
        loader._apply_standard_columns(loader.all_curves[0]['data'], 0)
        loader._apply_standard_columns(loader.all_curves[1]['data'], 1)

        # Curve 0 = lidded synthetic — must have LidTemperature.
        assert 'LidTemperature' in loader.all_curves[0]['data'].columns, (
            "Lidded curve missing LidTemperature column"
        )

        # Curve 1 = full immersion — must NOT have LidTemperature.
        assert 'LidTemperature' not in loader.all_curves[1]['data'].columns, (
            "Unlidded curve unexpectedly has LidTemperature column"
        )

    def test_switching_curves_three_times_keeps_column_state_correct(self):
        loader = _populate_loader_two_curves(lidded_first=True)

        for round_idx in range(3):
            for ci in (0, 1):
                df = loader.all_curves[ci]['data']
                loader._apply_standard_columns(df, ci)
                if ci == 0:
                    assert 'LidTemperature' in df.columns, (
                        f"Round {round_idx}: lidded curve missing LidTemperature"
                    )
                else:
                    assert 'LidTemperature' not in df.columns, (
                        f"Round {round_idx}: unlidded curve has LidTemperature"
                    )


class TestColumnDropsAfterStaleCarryOver:
    """If a DataFrame already carries LidTemperature from a prior curve and
    the current curve has no lid, the column must be dropped (no stale data).
    """

    def test_existing_lid_column_dropped_when_no_lid_in_assignment(self):
        loader = _populate_loader_two_curves(lidded_first=True)

        # Manually plant a stale LidTemperature column on curve 1 (unlidded).
        unlidded_df = loader.all_curves[1]['data']
        unlidded_df['LidTemperature'] = 99.0  # garbage stale value

        # Re-apply standard columns — the stale column must be dropped.
        loader._apply_standard_columns(unlidded_df, 1)
        assert 'LidTemperature' not in unlidded_df.columns, (
            "_apply_standard_columns must drop stale LidTemperature column"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
