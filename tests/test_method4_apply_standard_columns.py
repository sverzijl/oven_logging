"""M26 HMS Bellerophon: Method 4 hotfix — `_apply_standard_columns` must
consult bake metadata so the geometric core series reaches `df['CoreTemperature']`.

Background
----------
Before this hotfix, `loader.get_core_temperature_series()` correctly layered
override → Method 4 (geometric) → classifier → fallback, but the
`_apply_standard_columns` writer at `loader.py:1525-1537` did NOT consult
`_geometric_core_series`. The result: when bake metadata was set, the
explicit-API reader returned the geometric series, but every Streamlit tab
and analyser reading `df['CoreTemperature']` got the classifier's
Method 1 result. Two sources of truth disagreed.

These tests pin the layering invariant per `CLAUDE.md` "Data transformation
pipeline" — override → Method 4 → classifier → fallback — across BOTH the
reader API and the standardised column. The DRY contract is enforced by
the new private `_resolve_core_series(curve_index, df)` helper.
"""

from __future__ import annotations

import os
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]
# Use 1000BA3C_1759 per Kent's M26 build plan acceptance-criterion fixture.
REAL_CSV = REPO / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"


def _make_loader() -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(str(REAL_CSV))
    return loader


def _regenerate_curve(loader: ThermalProfileLoader, curve_index: int) -> pd.DataFrame:
    """Trigger `_apply_standard_columns` for ``curve_index`` and return the per-curve DataFrame.

    `set_current_curve` swaps `loader.data` to the curve's slice; we then
    call `_regenerate_standard_columns` to re-run the writer. The per-curve
    DataFrame in `all_curves` is the SAME object as `loader.data` after
    the switch, so mutations are reflected in both.
    """
    loader.set_current_curve(curve_index)
    loader._regenerate_standard_columns()
    return loader.all_curves[curve_index]['data']


# ---------------------------------------------------------------------------
# Test 1 — no metadata, no regression (byte-identical refactor on no-meta path)
# ---------------------------------------------------------------------------


class TestNoMetadataNoRegression:
    """When bake_metadata is empty, the new layering path is byte-identical
    to the legacy path (override absent → classifier → fallback).
    """

    def test_no_metadata_writes_classifier_result(self):
        loader = _make_loader()
        df = _regenerate_curve(loader, 0)

        assert 'CoreTemperature' in df.columns
        # With no metadata and no override, df['CoreTemperature'] must equal
        # the classifier's interpolated core series (Method 1) — the legacy
        # behaviour that pre-existed the M26 hotfix.
        assignment = loader.curve_sensor_assignments[0].get('assignment')
        assert assignment is not None
        assert assignment.core_assignment is not None
        expected = loader._align_series(
            assignment.core_assignment.temperature_series, df
        )
        # The writer assigns to a column of the same df, so reset/align them
        # before comparison.
        actual = df['CoreTemperature'].reset_index(drop=True)
        expected = expected.reset_index(drop=True)
        pd.testing.assert_series_equal(
            actual, expected, check_names=False, check_dtype=False
        )

    def test_no_metadata_reader_matches_writer(self):
        """Consistency: with no metadata, `get_core_temperature_series`
        must agree with `df['CoreTemperature']`."""
        loader = _make_loader()
        df = _regenerate_curve(loader, 0)
        reader = loader.get_core_temperature_series(0).reset_index(drop=True)
        column = df['CoreTemperature'].reset_index(drop=True)
        pd.testing.assert_series_equal(
            reader, column, check_names=False, check_dtype=False
        )


# ---------------------------------------------------------------------------
# Test 2 — metadata set: Method 4 writes to df['CoreTemperature']
# ---------------------------------------------------------------------------


class TestMetadataSetMethod4WritesStandardColumn:
    def test_metadata_lands_core_on_t1(self):
        """`loaf_thickness_mm=120, insertion_depth_mm=60` →
        `pos_below_tip = 60 - 60 = 0` mm → core lands EXACTLY on T1.
        `df['CoreTemperature']` must equal `df['T1']`.
        """
        loader = _make_loader()
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 120.0,
            "insertion_depth_mm": 60.0,
        })
        df = _regenerate_curve(loader, 0)

        assert 'T1' in df.columns
        actual = df['CoreTemperature'].reset_index(drop=True)
        expected = df['T1'].reset_index(drop=True)
        pd.testing.assert_series_equal(
            actual, expected, check_names=False, check_dtype=False
        )

    def test_metadata_lands_core_halfway_between_t1_and_t2(self):
        """`loaf_thickness_mm=120, insertion_depth_mm=66.7857...` →
        `pos_below_tip = 66.7857 - 60 = 6.7857 mm` (half a sensor spacing,
        13.571/2). Core lands halfway between T1 and T2 → series is the
        equal-weight blend `(T1 + T2) / 2`.
        """
        half_spacing = 95.0 / 7.0 / 2.0  # ≈ 6.7857 mm
        loader = _make_loader()
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 120.0,
            "insertion_depth_mm": 60.0 + half_spacing,
        })
        df = _regenerate_curve(loader, 0)

        assert 'T1' in df.columns and 'T2' in df.columns
        actual = df['CoreTemperature'].reset_index(drop=True)
        expected = (
            (df['T1'].reset_index(drop=True) + df['T2'].reset_index(drop=True))
            / 2.0
        )
        np.testing.assert_allclose(
            actual.to_numpy(), expected.to_numpy(), rtol=1e-9, atol=1e-9
        )
        # Sanity: the geometric helper agrees with the column writer.
        geom = loader._geometric_core_series(0).reset_index(drop=True)
        np.testing.assert_allclose(
            actual.to_numpy(), geom.to_numpy(), rtol=1e-9, atol=1e-9
        )


# ---------------------------------------------------------------------------
# Test 3 — clearing metadata reverts to classifier
# ---------------------------------------------------------------------------


class TestMetadataClearRevertsToClassifier:
    def test_method4_active_then_cleared(self):
        loader = _make_loader()

        # Step 1: set bake_metadata to engage Method 4 with a non-T1 position.
        half_spacing = 95.0 / 7.0 / 2.0
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 120.0,
            "insertion_depth_mm": 60.0 + half_spacing,
        })
        df = _regenerate_curve(loader, 0)
        # Confirm Method 4 active: column equals geometric series.
        geom = loader._geometric_core_series(0).reset_index(drop=True)
        np.testing.assert_allclose(
            df['CoreTemperature'].reset_index(drop=True).to_numpy(),
            geom.to_numpy(),
            rtol=1e-9, atol=1e-9,
        )

        # Step 2: clear, regenerate, confirm column == classifier output.
        loader.clear_bake_metadata(0)
        df = _regenerate_curve(loader, 0)
        assignment = loader.curve_sensor_assignments[0].get('assignment')
        assert assignment is not None and assignment.core_assignment is not None
        expected = loader._align_series(
            assignment.core_assignment.temperature_series, df
        ).reset_index(drop=True)
        actual = df['CoreTemperature'].reset_index(drop=True)
        pd.testing.assert_series_equal(
            actual, expected, check_names=False, check_dtype=False
        )


# ---------------------------------------------------------------------------
# Test 4 — override beats Method 4 (per CLAUDE.md layering contract)
# ---------------------------------------------------------------------------


class TestOverrideBeatsMethod4:
    def test_manual_core_override_wins_over_bake_metadata(self):
        loader = _make_loader()

        # Set bake_metadata that would otherwise engage Method 4 ...
        half_spacing = 95.0 / 7.0 / 2.0
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 120.0,
            "insertion_depth_mm": 60.0 + half_spacing,
        })
        # ... but also pin a manual override directly on the dict, bypassing
        # topology validation (which would forbid core=T5 in a normal probe
        # geometry). The hotfix is about the writer's layering, not the
        # validator.
        loader._sensor_overrides[0] = dict(
            loader._sensor_overrides.get(0, {})
        )
        loader._sensor_overrides[0]['core'] = 'T5'

        df = _regenerate_curve(loader, 0)

        assert 'T5' in df.columns
        actual = df['CoreTemperature'].reset_index(drop=True)
        expected = df['T5'].reset_index(drop=True)
        pd.testing.assert_series_equal(
            actual, expected, check_names=False, check_dtype=False
        )


# ---------------------------------------------------------------------------
# Test 5 — reader/writer consistency contract (the M26 invariant)
# ---------------------------------------------------------------------------


class TestReaderMatchesWriter:
    """When bake_metadata is set, `get_core_temperature_series()` and
    `df['CoreTemperature']` must return equal series. This is the M26
    correctness invariant: two sources of truth must agree.
    """

    def test_consistency_when_method4_active(self):
        loader = _make_loader()
        half_spacing = 95.0 / 7.0 / 2.0
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 120.0,
            "insertion_depth_mm": 60.0 + half_spacing,
        })
        df = _regenerate_curve(loader, 0)

        reader = loader.get_core_temperature_series(0).reset_index(drop=True)
        column = df['CoreTemperature'].reset_index(drop=True)
        np.testing.assert_allclose(
            reader.to_numpy(), column.to_numpy(), rtol=1e-9, atol=1e-9
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
