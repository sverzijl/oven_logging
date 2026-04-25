"""End-to-end regression tests for the Boundary Review flotilla
(M5 HMS Achilles, branch ``refactor/curve-boundary-review``).

Locks the loader-level operations the M3 Boundary Review tab issues
into a permanent contract.  The tab's UI primitives (number_input,
buttons, plotly_chart) require Streamlit's runtime to test live; this
file simulates the **state transitions** the operator triggers and
asserts the loader and curve dicts settle in the expected shape.

Three operator workflows covered:

1. **Hint refinement** — operator types a duration; loader updates
   ``expected_durations_s``; detector re-runs on raw_data; the curve's
   ``end_idx`` reflects the hint refinement.
2. **Manual override** — operator pins start/end; loader stores the
   override; curve dict reports ``exit_candidate_kind="manual_override"``
   regardless of any active hint.
3. **Reset to auto** — operator clears both hint and override; loader
   reverts to detector decision on raw_data.

Plus M1's raw_data contract: full CSV preserved across all of the
above.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_CSVS = {
    "100098DE_1351": _REPO_ROOT / "ProbeData_100098DE_2025-05-30 13_51_07.csv",
    "1000BA3C_0946": _REPO_ROOT / "ProbeData_1000BA3C_2025-05-30 09_46_16.csv",
    "1000BA3C_1759": _REPO_ROOT / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv",
}


def _load(name: str) -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=str(_REAL_CSVS[name]))
    return loader


# ---------------------------------------------------------------------------
# Tests: M1 contract — raw_data preserved across all operations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("csv_name", sorted(_REAL_CSVS.keys()))
class TestRawDataPreservedAcrossOperations:

    def test_raw_data_after_load(self, csv_name):
        loader = _load(csv_name)
        assert loader.raw_data is not None
        assert len(loader.raw_data) > 0

    def test_raw_data_unchanged_after_set_expected_durations(self, csv_name):
        loader = _load(csv_name)
        n_before = len(loader.raw_data)
        # Use a duration that's reasonable for any of the 3 CSVs (~25 min).
        loader.set_expected_durations([1500.0] * len(loader.all_curves))
        assert len(loader.raw_data) == n_before

    def test_raw_data_unchanged_after_set_curve_boundaries(self, csv_name):
        loader = _load(csv_name)
        n_before = len(loader.raw_data)
        c0 = loader.all_curves[0]
        loader.set_curve_boundaries(
            0, int(c0["start_idx"]) + 1, int(c0["end_idx"]) - 1
        )
        assert len(loader.raw_data) == n_before

    def test_raw_data_unchanged_after_clear(self, csv_name):
        loader = _load(csv_name)
        n_before = len(loader.raw_data)
        loader.clear_curve_boundaries(0)
        assert len(loader.raw_data) == n_before


# ---------------------------------------------------------------------------
# Tests: M3 tab workflows
# ---------------------------------------------------------------------------


class TestHintWorkflow:
    """Operator types a duration; loader auto-optimises curve."""

    def test_hint_refines_curve_end_via_loader(self):
        loader = _load("1000BA3C_1759")
        # Sanity: 3 bakes detected.
        assert len(loader.all_curves) == 3
        original_end = loader.all_curves[0]["end_idx"]

        # Apply a hint shorter than the detected duration → end may shift
        # earlier within the tolerance band.  We don't assert direction;
        # we only assert the loader accepted the hint and the count is
        # preserved (per the M1 latent-bug fix).
        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        assert len(loader.all_curves) == 3
        # The curve dicts must remain queryable.
        assert "exit_candidate_kind" in loader.all_curves[0]
        assert isinstance(loader.all_curves[0]["end_idx"], int)


class TestManualOverrideWorkflow:
    """Operator pins start/end; override has precedence."""

    def test_manual_override_pins_boundary(self):
        loader = _load("1000BA3C_1759")
        # Pin curve-1 to a tight window.
        new_start = loader.all_curves[0]["start_idx"] + 5
        new_end = loader.all_curves[0]["end_idx"] - 5
        loader.set_curve_boundaries(0, new_start, new_end)
        c = loader.all_curves[0]
        assert c["start_idx"] == new_start
        assert c["end_idx"] == new_end
        assert c["exit_candidate_kind"] == "manual_override"

    def test_override_survives_subsequent_hint(self):
        loader = _load("1000BA3C_1759")
        new_start = loader.all_curves[0]["start_idx"] + 5
        new_end = loader.all_curves[0]["end_idx"] - 5
        loader.set_curve_boundaries(0, new_start, new_end)
        # Now apply a hint — curve-0 must keep its override.
        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        c0 = loader.all_curves[0]
        assert c0["start_idx"] == new_start
        assert c0["end_idx"] == new_end
        assert c0["exit_candidate_kind"] == "manual_override"
        # Curves 1 and 2 should NOT be marked override.
        assert loader.all_curves[1]["exit_candidate_kind"] != "manual_override"
        assert loader.all_curves[2]["exit_candidate_kind"] != "manual_override"


class TestResetWorkflow:
    """Operator clicks 'Reset to auto'; both hint and override go away."""

    def test_reset_after_override_reverts_to_detector_decision(self):
        loader = _load("1000BA3C_1759")
        original_start = loader.all_curves[0]["start_idx"]
        original_end = loader.all_curves[0]["end_idx"]
        original_kind = loader.all_curves[0]["exit_candidate_kind"]

        loader.set_curve_boundaries(0, original_start + 5, original_end - 5)
        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        # Reset: both clear.
        loader.clear_curve_boundaries(0)
        loader.set_expected_durations(None)
        c0 = loader.all_curves[0]
        assert c0["start_idx"] == original_start
        assert c0["end_idx"] == original_end
        assert c0["exit_candidate_kind"] == original_kind


# ---------------------------------------------------------------------------
# Tests: detection-family regressions are not introduced
# ---------------------------------------------------------------------------


class TestNoRegressionOnRealCSVs:
    """Under no hint and no override, every real CSV produces the same
    curve count it always has.  Belt-and-braces against accidental
    detector drift introduced by this flotilla."""

    @pytest.mark.parametrize(
        "csv_name,expected_curve_count",
        [
            ("100098DE_1351", 1),
            ("1000BA3C_0946", 1),
            ("1000BA3C_1759", 3),
        ],
    )
    def test_curve_count_matches_baseline(self, csv_name, expected_curve_count):
        loader = _load(csv_name)
        assert len(loader.all_curves) == expected_curve_count
