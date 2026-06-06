"""Multi-curve state-isolation regression tests (fix/deep-review).

These pin the contract that per-curve state which is keyed by the volatile
``all_curves`` position — sensor overrides (``_sensor_overrides``), bake
metadata (``_bake_metadata``), and boundary overrides
(``_boundary_overrides``) — stays bound to the PHYSICAL curve it was set on
even after ``_extract_all_baking_curves`` re-sorts and renumbers the curve
list (e.g. when ``add_manual_curve`` inserts a region that sorts before an
existing bake).

Before the fix, overrides/metadata bound to the wrong curve after a
re-extract: a manual curve inserted ahead of a physical bake would steal
that bake's override/metadata while the bake itself lost both. The boundary
clearer was also a silent no-op once a user-added curve preceded a detector
curve.
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


def _load_three_bake_loader() -> ThermalProfileLoader:
    """3-bake CSV: curves at idx (13-293), (651-944), (5888-6185)."""
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=str(_BA3C_1759_CSV))
    assert len(loader.all_curves) == 3, (
        f"sanity: BA3C_1759 should produce 3 curves, got {len(loader.all_curves)}"
    )
    return loader


class TestSensorOverrideFollowsPhysicalCurve:
    """Finding 1: ``_sensor_overrides`` must re-key onto the physical curve
    after a manual-curve insertion shifts indices."""

    def test_core_override_survives_manual_curve_insert(self):
        loader = _load_three_bake_loader()
        # Physical bake-2 is at curve index 1 (idx 651-944).
        loader.set_sensor_override(1, "core", "T2")
        assert loader.get_core_sensor(1) == "T2"

        # Insert a manual curve in the inter-bake cool region (idx 320-360),
        # which sorts BEFORE the physical bake at index 1.
        new_idx = loader.add_manual_curve(320, 360)
        assert new_idx == 1, "the new user-added curve should sort to index 1"

        # The physical bake formerly at index 1 is now at index 2.
        phys = next(
            i for i, c in enumerate(loader.all_curves)
            if c.get("_user_added_idx") is None and c["start_idx"] == 651
        )
        assert phys == 2
        assert loader.get_core_sensor(phys) == "T2", (
            "core override must follow the physical bake to its new index"
        )
        # And the new user-added curve must NOT inherit the override.
        assert loader.get_core_sensor(new_idx) != "T2"

    def test_bake_metadata_survives_manual_curve_insert(self):
        loader = _load_three_bake_loader()
        meta = {"loaf_thickness_mm": 100.0, "insertion_depth_mm": 60.0}
        loader.set_bake_metadata(1, meta)
        assert loader.get_bake_metadata(1) == meta

        new_idx = loader.add_manual_curve(320, 360)

        phys = next(
            i for i, c in enumerate(loader.all_curves)
            if c.get("_user_added_idx") is None and c["start_idx"] == 651
        )
        assert loader.get_bake_metadata(phys) == meta, (
            "bake metadata must follow the physical bake to its new index"
        )
        # The new user-added curve must NOT inherit the metadata.
        assert loader.get_bake_metadata(new_idx) == {}

    def test_override_and_metadata_drop_with_manual_curve_removal(self):
        """Removing the inserted manual curve shifts the bake back to
        index 1; its override + metadata must still resolve there."""
        loader = _load_three_bake_loader()
        loader.set_sensor_override(1, "core", "T2")
        loader.set_bake_metadata(1, {"loaf_thickness_mm": 90.0,
                                     "insertion_depth_mm": 55.0})
        new_idx = loader.add_manual_curve(320, 360)
        loader.remove_manual_curve(new_idx)
        # Back to 3 curves; physical bake-2 is at index 1 again.
        assert len(loader.all_curves) == 3
        assert loader.all_curves[1]["start_idx"] == 651
        assert loader.get_core_sensor(1) == "T2"
        assert loader.get_bake_metadata(1)["loaf_thickness_mm"] == 90.0


class TestClearBoundaryFollowsPhysicalCurve:
    """Finding 2: ``clear_curve_boundaries`` must translate the all_curves
    position to the stable detector key the setter used."""

    def test_clear_removes_pin_after_user_curve_precedes_detector(self):
        loader = _load_three_bake_loader()
        # Insert a user curve that sorts to the front so detector curves
        # are pushed to higher all_curves positions.
        loader.add_manual_curve(320, 360)
        # Detector bake-2 is now at index 2.
        phys = next(
            i for i, c in enumerate(loader.all_curves)
            if c.get("_user_added_idx") is None and c["start_idx"] == 651
        )
        original_start = loader.all_curves[phys]["start_idx"]
        original_end = loader.all_curves[phys]["end_idx"]

        loader.set_curve_boundaries(phys, original_start + 5, original_end - 5)
        assert loader.all_curves[phys]["start_idx"] == original_start + 5

        loader.clear_curve_boundaries(phys)
        # Re-resolve phys (count is unchanged, position stable).
        phys2 = next(
            i for i, c in enumerate(loader.all_curves)
            if c.get("_user_added_idx") is None and c["start_idx"] == original_start
        )
        assert loader.all_curves[phys2]["start_idx"] == original_start, (
            "clear must actually remove the pin even when a user curve "
            "precedes the detector curve"
        )
        assert loader.all_curves[phys2]["end_idx"] == original_end


class TestSelfDataPointsAtCurrentCurve:
    """Finding 4: after a boundary edit re-extracts curves, ``self.data``
    must point at the current curve's fresh DataFrame, not an orphan."""

    def test_self_data_is_current_curve_after_boundary_edit(self):
        loader = _load_three_bake_loader()
        loader.set_current_curve(1)
        c = loader.all_curves[1]
        loader.set_curve_boundaries(1, c["start_idx"] + 3, c["end_idx"] - 3)
        assert loader.data is loader.all_curves[loader.current_curve_index]["data"]

    def test_self_data_is_current_curve_after_set_expected_durations(self):
        loader = _load_three_bake_loader()
        loader.set_current_curve(2)
        loader.set_expected_durations([1400.0, 1465.0, 1485.0])
        assert loader.data is loader.all_curves[loader.current_curve_index]["data"]
