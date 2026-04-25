"""Loader-level tests for raw_data preservation and manual boundary
overrides (M1 HMS Ardent, branch ``refactor/curve-boundary-review``).

Two new capabilities:

1. ``loader.raw_data`` — preserves the full pre-curve-extraction
   DataFrame so the new Curve Boundary Review tab can plot the raw CSV
   with detected windows overlaid.  Today ``loader.data`` is overwritten
   with the first curve's slice immediately after extraction (loader.py
   line 87), discarding the full log; the new attribute keeps it.

2. ``set_curve_boundaries(curve_index, start_idx, end_idx)`` — pins a
   curve's boundary regardless of the detector's decision.  Allows the
   operator to manually override when the hint can't reach the desired
   boundary.  Mirrors the cache-invalidation semantics of
   :meth:`set_expected_durations` (M5 mission).

3. ``clear_curve_boundaries(curve_index)`` — removes the override and
   reverts to detector output.

Latent bug fixed as a side effect of (1): after ``load_csv``,
``set_expected_durations`` was re-running detection on ``self.data``
(the first curve's slice) instead of the full log.  Fixed by
re-detecting on ``self.raw_data``.  Test
``test_set_expected_durations_re_detects_on_raw_log`` anchors this.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader
from tests.fixtures.curve_boundary_cases import CASES


_REPO_ROOT = Path(__file__).resolve().parent.parent
_BA3C_1759_CSV = _REPO_ROOT / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"


def _load_real_csv() -> ThermalProfileLoader:
    """Realistic loader after ``load_csv`` — 3-bake CSV with full log retained."""
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=str(_BA3C_1759_CSV))
    return loader


def _ba3c_1759_full_df() -> pd.DataFrame:
    case = next(c for c in CASES if c["name"] == "real_1000BA3C_1759")
    return case["df"].copy()


# ---------------------------------------------------------------------------
# Tests: raw_data preservation
# ---------------------------------------------------------------------------


class TestRawDataPreservation:

    def test_loader_exposes_raw_data_attribute(self):
        loader = ThermalProfileLoader()
        assert hasattr(loader, "raw_data")
        assert loader.raw_data is None  # not loaded yet

    def test_raw_data_populated_after_load_csv(self):
        loader = _load_real_csv()
        assert loader.raw_data is not None
        assert isinstance(loader.raw_data, pd.DataFrame)
        # BA3C_1759 has 6,214 raw rows.  Check we still have a multi-bake
        # row count and that self.data is a STRICT subset (the first curve).
        assert len(loader.raw_data) > len(loader.data)
        assert len(loader.raw_data) >= 6000, (
            f"raw_data appears truncated: {len(loader.raw_data)} rows"
        )

    def test_raw_data_not_mutated_by_curve_extraction(self):
        loader = _load_real_csv()
        n_before = len(loader.raw_data)
        # Trigger a re-detection — must not shorten raw_data.
        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        assert len(loader.raw_data) == n_before

    def test_raw_data_independent_of_self_data(self):
        """Mutating ``self.data`` must not propagate to ``raw_data``."""
        loader = _load_real_csv()
        n_raw_before = len(loader.raw_data)
        # Simulate a downstream tab dropping rows from self.data.
        loader.data = loader.data.iloc[:10].copy()
        assert len(loader.raw_data) == n_raw_before


# ---------------------------------------------------------------------------
# Tests: set_expected_durations re-detection now uses raw_data
# ---------------------------------------------------------------------------


class TestSetExpectedDurationsUsesRawLog:
    """Latent-bug regression guard.

    Pre-M1, ``set_expected_durations`` re-ran detection on ``self.data``
    which had been overwritten with the first curve's slice — the
    re-detection saw a single-bake DataFrame and produced 1 curve,
    silently dropping bakes 2 and 3 of BA3C_1759.

    Fixed in M1: re-detection runs on ``self.raw_data``.
    """

    def test_set_expected_durations_preserves_all_three_bakes(self):
        loader = _load_real_csv()
        assert len(loader.all_curves) == 3, (
            f"sanity: BA3C_1759 should produce 3 curves, got {len(loader.all_curves)}"
        )

        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        assert len(loader.all_curves) == 3, (
            "set_expected_durations must re-detect on the full raw log; "
            f"got {len(loader.all_curves)} curves (expected 3)"
        )


# ---------------------------------------------------------------------------
# Tests: set_curve_boundaries / clear_curve_boundaries
# ---------------------------------------------------------------------------


class TestSetCurveBoundaries:

    def test_set_curve_boundaries_overrides_detector(self):
        loader = _load_real_csv()
        detected_start = loader.all_curves[0]["start_idx"]
        detected_end = loader.all_curves[0]["end_idx"]

        # Pin curve-1 to a deliberately tight window.
        new_start = detected_start + 5
        new_end = detected_end - 5
        loader.set_curve_boundaries(0, new_start, new_end)

        assert loader.all_curves[0]["start_idx"] == new_start
        assert loader.all_curves[0]["end_idx"] == new_end

    def test_set_curve_boundaries_marks_kind_manual_override(self):
        loader = _load_real_csv()
        loader.set_curve_boundaries(
            0,
            loader.all_curves[0]["start_idx"] + 1,
            loader.all_curves[0]["end_idx"] - 1,
        )
        assert loader.all_curves[0]["exit_candidate_kind"] == "manual_override"

    def test_set_curve_boundaries_updates_derived_fields(self):
        loader = _load_real_csv()
        new_start = loader.all_curves[0]["start_idx"] + 10
        new_end = loader.all_curves[0]["end_idx"] - 10
        loader.set_curve_boundaries(0, new_start, new_end)

        c = loader.all_curves[0]
        # samples count
        assert c["samples"] == new_end - new_start + 1
        # data slice length
        assert len(c["data"]) == new_end - new_start + 1
        # start_time / end_time match raw_data timestamps
        assert c["start_time"] == float(loader.raw_data["Timestamp"].iloc[new_start])
        assert c["end_time"] == float(loader.raw_data["Timestamp"].iloc[new_end])

    def test_set_curve_boundaries_rejects_inverted_range(self):
        loader = _load_real_csv()
        with pytest.raises(ValueError):
            loader.set_curve_boundaries(0, 100, 10)

    def test_set_curve_boundaries_rejects_out_of_range(self):
        loader = _load_real_csv()
        n = len(loader.raw_data)
        with pytest.raises(ValueError):
            loader.set_curve_boundaries(0, -1, 10)
        with pytest.raises(ValueError):
            loader.set_curve_boundaries(0, 0, n + 1)

    def test_set_curve_boundaries_rejects_unknown_curve_index(self):
        loader = _load_real_csv()
        with pytest.raises((IndexError, ValueError)):
            loader.set_curve_boundaries(99, 10, 20)


class TestClearCurveBoundaries:

    def test_clear_reverts_to_detector_output(self):
        loader = _load_real_csv()
        original_start = loader.all_curves[0]["start_idx"]
        original_end = loader.all_curves[0]["end_idx"]
        original_kind = loader.all_curves[0]["exit_candidate_kind"]

        loader.set_curve_boundaries(0, original_start + 5, original_end - 5)
        assert loader.all_curves[0]["start_idx"] != original_start

        loader.clear_curve_boundaries(0)
        assert loader.all_curves[0]["start_idx"] == original_start
        assert loader.all_curves[0]["end_idx"] == original_end
        assert loader.all_curves[0]["exit_candidate_kind"] == original_kind

    def test_clear_unknown_index_is_noop(self):
        loader = _load_real_csv()
        loader.clear_curve_boundaries(99)  # must not raise


# ---------------------------------------------------------------------------
# Tests: override × hint precedence
# ---------------------------------------------------------------------------


class TestOverridePrecedence:
    """Manual override has precedence over hint: when both are set,
    the boundary is the manually-pinned range.  Hint still applies to
    *other* curves whose boundaries are not overridden.
    """

    def test_override_persists_through_set_expected_durations(self):
        loader = _load_real_csv()
        new_start = loader.all_curves[0]["start_idx"] + 10
        new_end = loader.all_curves[0]["end_idx"] - 10
        loader.set_curve_boundaries(0, new_start, new_end)

        # Hint applies — but curve-0's manual override must survive.
        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        assert loader.all_curves[0]["start_idx"] == new_start
        assert loader.all_curves[0]["end_idx"] == new_end
        assert loader.all_curves[0]["exit_candidate_kind"] == "manual_override"

    def test_hint_still_applies_to_non_overridden_curves(self):
        loader = _load_real_csv()
        # Override curve-0 only.
        loader.set_curve_boundaries(
            0,
            loader.all_curves[0]["start_idx"] + 5,
            loader.all_curves[0]["end_idx"] - 5,
        )
        # Capture curve-1 detected boundaries before hint.
        c1_pre = (
            loader.all_curves[1]["start_idx"],
            loader.all_curves[1]["end_idx"],
        )
        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        # Curve-1 must still be free to refine via the hint path.
        assert loader.all_curves[1]["exit_candidate_kind"] != "manual_override"
        # Curve-0's override survived.
        assert loader.all_curves[0]["exit_candidate_kind"] == "manual_override"
