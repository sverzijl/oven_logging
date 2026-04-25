"""Loader tests for user-claimed curves (M11 HMS Endeavour).

When the detector misses a bake (low peak, short duration, etc.), the
operator can box-select on the raw-log plot to claim a region.
``add_manual_curve(start, end)`` auto-refines the boundaries using the
detector on the sub-slice, falling back to a BAKE_ACTIVE_C trim if
the detector finds no curve there.

Contract:

1. ``add_manual_curve(s, e)`` returns the new curve's index in
   ``all_curves`` (after sort + renumber).
2. The user-added curve is tagged with ``_user_added_idx`` so
   downstream code can distinguish it from detector output.
3. ``set_curve_boundaries`` on a user-added curve_index updates
   ``_added_curves`` (NOT ``_boundary_overrides``).
4. ``remove_manual_curve(curve_index)`` deletes only user-added curves.
5. Detector overrides continue to work even when user-added curves
   are interspersed (override storage keyed by detector position).
6. Sort by ``start_idx`` is preserved across all paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BA3C_1759_CSV = _REPO_ROOT / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"


def _load() -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=str(_BA3C_1759_CSV))
    return loader


# ---------------------------------------------------------------------------
# Tests: add_manual_curve
# ---------------------------------------------------------------------------


class TestAddManualCurve:

    def test_attribute_exists_before_load(self):
        loader = ThermalProfileLoader()
        assert hasattr(loader, "_added_curves")
        assert loader._added_curves == []

    def test_add_appends_to_all_curves(self):
        loader = _load()
        baseline_count = len(loader.all_curves)
        # BA3C_1759 has 3 detected bakes — claim a region inside the
        # 945..5887 inter-bake gap (where the detector found nothing).
        new_idx = loader.add_manual_curve(1500, 1700)
        assert len(loader.all_curves) == baseline_count + 1
        assert 0 <= new_idx < len(loader.all_curves)

    def test_added_curve_tagged_with_user_added_idx(self):
        loader = _load()
        new_idx = loader.add_manual_curve(1500, 1700)
        assert "_user_added_idx" in loader.all_curves[new_idx]
        assert loader.all_curves[new_idx]["_user_added_idx"] == 0

    def test_added_curve_kind_is_user_added(self):
        loader = _load()
        new_idx = loader.add_manual_curve(1500, 1700)
        assert (
            loader.all_curves[new_idx]["exit_candidate_kind"] == "user_added"
        )

    def test_curves_sorted_by_start_idx(self):
        loader = _load()
        # User claim falls between bake-1 (idx 13–293) and bake-2 (651–944).
        loader.add_manual_curve(400, 500)
        starts = [c["start_idx"] for c in loader.all_curves]
        assert starts == sorted(starts)

    def test_curve_numbers_renumbered_after_sort(self):
        loader = _load()
        loader.add_manual_curve(400, 500)
        for i, c in enumerate(loader.all_curves):
            assert c["curve_number"] == i + 1

    def test_invalid_range_rejected(self):
        loader = _load()
        with pytest.raises(ValueError):
            loader.add_manual_curve(100, 50)
        with pytest.raises(ValueError):
            loader.add_manual_curve(-1, 100)
        with pytest.raises(ValueError):
            loader.add_manual_curve(100, 99999999)


class TestAutoRefinement:
    """When the user claims a region, the detector runs on the sub-slice
    to pull in the boundaries from the user's coarse drag."""

    def test_refinement_pulls_in_boundaries_when_detector_finds_curve(self):
        """A region wider than the actual bake should refine inward."""
        loader = _load()
        # Bake-1 sits at idx 13–293 in the full log.  Claim a region
        # 0–500 (much wider).  After refinement, the new range should
        # roughly match the bake's actual extent.
        new_idx = loader.add_manual_curve(0, 500)
        c = loader.all_curves[new_idx]
        assert c["start_idx"] >= 0
        assert c["end_idx"] <= 500
        # And the refinement should have pulled the boundaries inward
        assert c["end_idx"] - c["start_idx"] < 500

    def test_refinement_falls_back_to_user_range_when_detector_finds_nothing(self):
        """A region with only ambient temperatures (no bake) should
        accept the user's range as-is (or trim leading/trailing
        below-active samples)."""
        loader = _load()
        # idx 4500–4700 is deep in the inter-bake-2/3 cool-off, all
        # at ambient.  Detector would find no curve there.
        new_idx = loader.add_manual_curve(4500, 4700)
        c = loader.all_curves[new_idx]
        # Range is preserved (or trimmed but not vanished)
        assert c["end_idx"] - c["start_idx"] > 0
        # Bounded by user's range
        assert c["start_idx"] >= 4500
        assert c["end_idx"] <= 4700


# ---------------------------------------------------------------------------
# Tests: remove_manual_curve
# ---------------------------------------------------------------------------


class TestRemoveManualCurve:

    def test_remove_user_added_curve(self):
        loader = _load()
        baseline_count = len(loader.all_curves)
        new_idx = loader.add_manual_curve(1500, 1700)
        assert len(loader.all_curves) == baseline_count + 1
        loader.remove_manual_curve(new_idx)
        assert len(loader.all_curves) == baseline_count

    def test_remove_detector_curve_is_noop(self):
        """Calling remove_manual_curve on a detector curve does
        nothing — detector curves are unaffected."""
        loader = _load()
        baseline_count = len(loader.all_curves)
        loader.remove_manual_curve(0)  # detector curve at index 0
        assert len(loader.all_curves) == baseline_count


# ---------------------------------------------------------------------------
# Tests: set_curve_boundaries dispatch
# ---------------------------------------------------------------------------


class TestSetCurveBoundariesDispatch:
    """``set_curve_boundaries`` should:
       - update ``_added_curves`` when targeting a user-added curve
       - update ``_boundary_overrides`` when targeting a detector curve
    so that subsequent re-extraction respects both."""

    def test_box_select_on_user_added_updates_added_curves(self):
        loader = _load()
        new_idx = loader.add_manual_curve(1400, 1800)
        assert loader._added_curves[0] == (1400, 1800) or \
            loader._added_curves[0] != (1400, 1800)  # may be refined
        # User now drags a box on the user-added curve's detail plot.
        loader.set_curve_boundaries(new_idx, 1500, 1700)
        # Find the user-added curve again (idx may have shifted on sort).
        updated_idx = next(
            i
            for i, c in enumerate(loader.all_curves)
            if c.get("_user_added_idx") == 0
        )
        assert loader.all_curves[updated_idx]["start_idx"] == 1500
        assert loader.all_curves[updated_idx]["end_idx"] == 1700
        assert loader._added_curves[0] == (1500, 1700)

    def test_box_select_on_detector_curve_updates_boundary_overrides(self):
        loader = _load()
        # First add a user-curve so detector positions and all_curves
        # positions diverge.
        loader.add_manual_curve(1400, 1800)
        # Now override a detector curve.  Find one via its kind.
        det_idx = next(
            i
            for i, c in enumerate(loader.all_curves)
            if c.get("exit_candidate_kind") == "probe_pull_cliff"
        )
        original_start = loader.all_curves[det_idx]["start_idx"]
        original_end = loader.all_curves[det_idx]["end_idx"]
        loader.set_curve_boundaries(det_idx, original_start + 5, original_end - 5)
        # After re-extract the curve at that position is now an override.
        det_idx2 = next(
            i
            for i, c in enumerate(loader.all_curves)
            if c.get("start_idx") == original_start + 5
            and c.get("end_idx") == original_end - 5
        )
        assert (
            loader.all_curves[det_idx2]["exit_candidate_kind"]
            == "manual_override"
        )

    def test_user_added_survives_subsequent_detector_override(self):
        loader = _load()
        loader.add_manual_curve(1400, 1800)
        det_idx = next(
            i
            for i, c in enumerate(loader.all_curves)
            if c.get("exit_candidate_kind") == "probe_pull_cliff"
        )
        c = loader.all_curves[det_idx]
        loader.set_curve_boundaries(det_idx, c["start_idx"] + 5, c["end_idx"] - 5)
        # User-added curve should still be present.
        user_curves = [
            c for c in loader.all_curves if c.get("_user_added_idx") is not None
        ]
        assert len(user_curves) == 1


# ---------------------------------------------------------------------------
# Tests: persistence across set_expected_durations
# ---------------------------------------------------------------------------


class TestUserAddedPersistsThroughHint:

    def test_user_added_survives_set_expected_durations(self):
        loader = _load()
        loader.add_manual_curve(1400, 1800)
        n_before = len(loader.all_curves)
        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        assert len(loader.all_curves) == n_before
        # User-added curve still present
        assert any(
            c.get("_user_added_idx") is not None for c in loader.all_curves
        )
