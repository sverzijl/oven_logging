"""Pure-helper tests for the Boundary Review tab (M3 HMS Indomitable).

The Streamlit widget integration is verified by browser smoke (M5 HMS
Achilles) — tests here cover the tab module's pure helpers:

- session-state key construction for manual override widgets
- hint-window computation from the detector config (mirrors what the
  detail plot draws)
- precedence helper that decides whether a curve is showing
  detector / hint / override boundaries
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tabs.boundary_review import (
    boundary_state_label,
    compute_hint_window_seconds,
    manual_end_key,
    manual_start_key,
)


# ---------------------------------------------------------------------------
# Tests: widget-key shapes
# ---------------------------------------------------------------------------


class TestWidgetKeyShapes:
    """Manual override widgets must use per-(filename, curve_number) keys
    so swapping the currently-viewed curve does not bleed widget state.
    """

    def test_manual_start_key_includes_filename_and_curve_number(self):
        k = manual_start_key("foo.csv", 2)
        assert "foo.csv" in k
        assert "2" in k

    def test_manual_end_key_includes_filename_and_curve_number(self):
        k = manual_end_key("foo.csv", 2)
        assert "foo.csv" in k
        assert "2" in k

    def test_start_and_end_keys_differ_for_same_curve(self):
        s = manual_start_key("foo.csv", 1)
        e = manual_end_key("foo.csv", 1)
        assert s != e

    def test_keys_for_different_files_differ(self):
        a = manual_start_key("a.csv", 1)
        b = manual_start_key("b.csv", 1)
        assert a != b

    def test_keys_for_different_curves_differ(self):
        a = manual_start_key("foo.csv", 1)
        b = manual_start_key("foo.csv", 2)
        assert a != b


# ---------------------------------------------------------------------------
# Tests: compute_hint_window_seconds
# ---------------------------------------------------------------------------


class TestComputeHintWindowSeconds:
    """The detail plot draws the hint band at
    ``[end_time - hint*(1+tol), end_time - hint*(1-tol)]`` so the
    operator can see "where the bake would END if it took the hinted
    duration".  The helper centralises this calculation so the plot
    and the detector agree.
    """

    def test_returns_none_when_hint_missing(self):
        assert compute_hint_window_seconds(
            end_time_s=1000.0, hint_seconds=None, tolerance_frac=0.15
        ) is None

    def test_returns_centered_band_around_end_minus_hint(self):
        """Hint = 600 s, end_time = 1000 s → expected start ≈ 400 s.
        ±15 % of hint = 90 s → window [310, 490]."""
        out = compute_hint_window_seconds(
            end_time_s=1000.0, hint_seconds=600.0, tolerance_frac=0.15
        )
        assert out is not None
        lo, hi = out
        assert lo == pytest.approx(310.0)
        assert hi == pytest.approx(490.0)

    def test_min_tolerance_seconds_floor_applies(self):
        """Tiny hint → tolerance band would be < 60 s; floor lifts it."""
        out = compute_hint_window_seconds(
            end_time_s=200.0,
            hint_seconds=120.0,
            tolerance_frac=0.15,
            min_tolerance_seconds=60.0,
        )
        lo, hi = out
        # band centre = 200 - 120 = 80 s; ±60 floor → [20, 140]
        assert lo == pytest.approx(20.0)
        assert hi == pytest.approx(140.0)

    def test_negative_hint_treated_as_no_hint(self):
        """Defensive: an upstream bug that produces a negative hint
        must not crash."""
        assert (
            compute_hint_window_seconds(
                end_time_s=1000.0, hint_seconds=-1.0, tolerance_frac=0.15
            )
            is None
        )

    def test_zero_hint_treated_as_no_hint(self):
        """0.0 minutes is the empty-input sentinel from M6 widgets."""
        assert (
            compute_hint_window_seconds(
                end_time_s=1000.0, hint_seconds=0.0, tolerance_frac=0.15
            )
            is None
        )


# ---------------------------------------------------------------------------
# Tests: boundary_state_label
# ---------------------------------------------------------------------------


class TestBoundaryStateLabel:
    """Maps a curve dict to a one-word state label shown in the UI:
    'override' / 'hint' / 'auto'.  Drives the badge colour next to the
    curve number in the detail panel.
    """

    def _curve(self, kind: str | None) -> dict:
        return {"exit_candidate_kind": kind, "curve_number": 1}

    def test_manual_override_kind_returns_override(self):
        assert boundary_state_label(self._curve("manual_override")) == "override"

    def test_other_kinds_with_hint_returns_hint(self):
        assert (
            boundary_state_label(
                self._curve("probe_pull_cliff"), hint_active=True
            )
            == "hint"
        )

    def test_other_kinds_without_hint_returns_auto(self):
        assert (
            boundary_state_label(
                self._curve("probe_pull_cliff"), hint_active=False
            )
            == "auto"
        )

    def test_unknown_kind_falls_back_to_auto(self):
        assert boundary_state_label(self._curve(None), hint_active=False) == "auto"
