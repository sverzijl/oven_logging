"""Pure-helper tests for the Boundary Review tab.

The Streamlit widget integration is verified by browser smoke
(M5 HMS Achilles, M9 HMS Lookout). Tests here cover the module's
pure helpers:

- ``boundary_state_label`` — UI badge state (override or auto)
- ``time_minutes_to_idx`` — minutes → raw_data idx (nearest-neighbour)
- ``extract_x_range_from_selection`` — Plotly selection event parser

History note: M10 HMS Vanguard removed the entry widgets (hint
number_input, manual range slider, Apply button) since drag-to-box-
select is the sole input mechanism. The associated helpers
(``manual_start_key``, ``manual_end_key``, ``manual_range_key``,
``compute_hint_window_seconds``) and their tests were retired.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tabs.boundary_review import (
    bake_time_session_key,
    boundary_state_label,
    build_detector_hint_list,
    consume_box_selection,
    describe_hint_outcome,
    extract_x_range_from_selection,
    time_minutes_to_idx,
)


# ---------------------------------------------------------------------------
# Tests: boundary_state_label
# ---------------------------------------------------------------------------


class TestBoundaryStateLabel:
    """Maps a curve dict to a one-word state label shown in the UI:
    ``override``, ``user_added``, or ``auto``.  Drives the badge
    colour next to the curve number in the detail panel.
    """

    def _curve(self, kind: str | None) -> dict:
        return {"exit_candidate_kind": kind, "curve_number": 1}

    def test_manual_override_kind_returns_override(self):
        assert boundary_state_label(self._curve("manual_override")) == "override"

    def test_user_added_kind_returns_user_added(self):
        assert boundary_state_label(self._curve("user_added")) == "user_added"

    def test_detector_kind_returns_auto(self):
        assert boundary_state_label(self._curve("probe_pull_cliff")) == "auto"

    def test_unknown_kind_returns_auto(self):
        assert boundary_state_label(self._curve(None)) == "auto"

    def test_expected_time_snap_kind_returns_snapped(self):
        assert boundary_state_label(self._curve("expected_time_snap")) == "snapped"


# ---------------------------------------------------------------------------
# Tests: consume_box_selection (dedup gate shared by both box paths)
# ---------------------------------------------------------------------------


class TestConsumeBoxSelection:
    """The stateful record-then-suppress gate that stops the same drag-box from
    re-applying on unrelated reruns (would otherwise spawn duplicate curves)."""

    def _event(self, lo, hi):
        return {"selection": {"box": [{"x": [lo, hi]}], "lasso": [], "points": []}}

    def test_first_call_returns_range_and_records_signature(self):
        store = {}
        assert consume_box_selection(self._event(1.0, 5.0), "k", store) == (1.0, 5.0)
        assert "k" in store  # signature recorded

    def test_repeat_same_box_returns_none(self):
        store = {}
        consume_box_selection(self._event(1.0, 5.0), "k", store)
        assert consume_box_selection(self._event(1.0, 5.0), "k", store) is None

    def test_different_box_after_first_returns_new_range(self):
        store = {}
        consume_box_selection(self._event(1.0, 5.0), "k", store)
        assert consume_box_selection(self._event(2.0, 6.0), "k", store) == (2.0, 6.0)

    def test_none_event_returns_none_without_mutation(self):
        store = {}
        assert consume_box_selection(None, "k", store) is None
        assert store == {}


# ---------------------------------------------------------------------------
# Tests: describe_hint_outcome
# ---------------------------------------------------------------------------


class TestDescribeHintOutcome:
    """Classifies how the actual-bake-time hint shaped a curve's end, driving
    the outcome message shown to the operator."""

    def _curve(
        self,
        kind,
        truncated: bool = False,
        start_time: float = 0.0,
        end_time: float = 0.0,
    ) -> dict:
        return {
            "exit_candidate_kind": kind,
            "truncated": truncated,
            "start_time": start_time,
            "end_time": end_time,
        }

    def test_override_wins_regardless_of_hint(self):
        assert describe_hint_outcome(self._curve("manual_override"), 1500.0) == "override"

    def test_snapped(self):
        assert describe_hint_outcome(self._curve("expected_time_snap"), 1500.0) == "snapped"

    def test_truncated_snap(self):
        assert (
            describe_hint_outcome(self._curve("expected_time_snap", truncated=True), 9999.0)
            == "truncated_snap"
        )

    def test_matched_exit_when_duration_within_tolerance(self):
        # Achieved 1490 s vs a 1500 s hint → inside the tolerance band.
        curve = self._curve("probe_pull_cliff", start_time=0.0, end_time=1490.0)
        assert describe_hint_outcome(curve, 1500.0) == "matched_exit"

    def test_hint_out_of_range_when_duration_far_from_hint(self):
        # Real end at 1500 s but the stated time was 6000 s → detector reverted.
        curve = self._curve("probe_pull_cliff", start_time=0.0, end_time=1500.0)
        assert describe_hint_outcome(curve, 6000.0) == "hint_out_of_range"

    def test_matched_exit_at_band_edge_is_inclusive(self):
        # band = max(1500*0.15, 60) = 225; achieved exactly at hint+band → matched.
        curve = self._curve("probe_pull_cliff", start_time=0.0, end_time=1725.0)
        assert describe_hint_outcome(curve, 1500.0) == "matched_exit"

    def test_out_of_range_just_beyond_band_edge(self):
        curve = self._curve("probe_pull_cliff", start_time=0.0, end_time=1726.0)
        assert describe_hint_outcome(curve, 1500.0) == "hint_out_of_range"

    def test_small_hint_floor_dominates_band(self):
        # hint=120 s → band floored at 60 s; achieved 175 s (diff 55) → matched.
        curve = self._curve("probe_pull_cliff", start_time=0.0, end_time=175.0)
        assert describe_hint_outcome(curve, 120.0) == "matched_exit"

    def test_hint_ineffective_when_no_exit_to_anchor(self):
        # kind=None (truncated bake, no confirmed exit) + a hint → ineffective.
        curve = self._curve(None, truncated=True, start_time=0.0, end_time=1200.0)
        assert describe_hint_outcome(curve, 1800.0) == "hint_ineffective"

    def test_no_hint_when_hint_absent(self):
        assert describe_hint_outcome(self._curve("probe_pull_cliff"), None) == "no_hint"

    def test_user_added_is_not_matched_exit(self):
        assert describe_hint_outcome(self._curve("user_added"), 1500.0) == "no_hint"


# ---------------------------------------------------------------------------
# Tests: time_minutes_to_idx
# ---------------------------------------------------------------------------


class TestTimeMinutesToIdx:
    """Operator-entered manual override times (in minutes) must convert
    cleanly to the raw_data sample index space the loader API expects.
    """

    def _ts_5s(self, n: int):
        return [i * 5.0 for i in range(n)]

    def test_zero_minutes_maps_to_zero_index(self):
        ts = self._ts_5s(100)
        assert time_minutes_to_idx(ts, 0.0) == 0

    def test_exact_minute_maps_to_corresponding_idx(self):
        ts = self._ts_5s(100)
        assert time_minutes_to_idx(ts, 1.0) == 12

    def test_between_samples_picks_nearest(self):
        ts = self._ts_5s(100)
        assert time_minutes_to_idx(ts, 0.05) == 1
        assert time_minutes_to_idx(ts, 0.03) == 0

    def test_beyond_last_sample_clamps(self):
        ts = self._ts_5s(100)
        assert time_minutes_to_idx(ts, 9999.0) == 99

    def test_empty_array_returns_zero_safely(self):
        assert time_minutes_to_idx([], 5.0) == 0


# ---------------------------------------------------------------------------
# Tests: extract_x_range_from_selection
# ---------------------------------------------------------------------------


class TestExtractXRangeFromSelection:
    """Streamlit's ``st.plotly_chart(on_select="rerun", selection_mode="box")``
    returns a dict-like event; the helper parses it into ``(lo, hi)``
    in minutes or ``None`` when no box is present.  Robust against the
    various shapes Streamlit/Plotly may emit across versions.
    """

    def test_none_event_returns_none(self):
        assert extract_x_range_from_selection(None) is None

    def test_empty_dict_returns_none(self):
        assert extract_x_range_from_selection({}) is None

    def test_no_selection_field_returns_none(self):
        assert extract_x_range_from_selection({"points": []}) is None

    def test_empty_box_list_returns_none(self):
        assert (
            extract_x_range_from_selection(
                {"selection": {"box": [], "lasso": [], "points": []}}
            )
            is None
        )

    def test_well_formed_box_returns_lo_hi(self):
        event = {
            "selection": {
                "box": [
                    {
                        "xref": "x",
                        "yref": "y",
                        "x": [12.5, 18.2],
                        "y": [20.0, 100.0],
                    }
                ],
                "lasso": [],
                "points": [],
            }
        }
        out = extract_x_range_from_selection(event)
        assert out == (12.5, 18.2)

    def test_reverse_order_x_normalised(self):
        event = {
            "selection": {
                "box": [{"x": [25.0, 10.0], "y": [0, 1]}],
                "lasso": [],
                "points": [],
            }
        }
        out = extract_x_range_from_selection(event)
        assert out == (10.0, 25.0)

    def test_zero_width_box_returns_none(self):
        event = {
            "selection": {
                "box": [{"x": [15.0, 15.0], "y": [0, 1]}],
                "lasso": [],
                "points": [],
            }
        }
        assert extract_x_range_from_selection(event) is None

    def test_missing_x_in_box_returns_none(self):
        event = {
            "selection": {
                "box": [{"y": [0, 1]}],
                "lasso": [],
                "points": [],
            }
        }
        assert extract_x_range_from_selection(event) is None


# ---------------------------------------------------------------------------
# Tests: build_detector_hint_list — hints map to the correct physical bake
# ---------------------------------------------------------------------------


class TestBuildDetectorHintList:
    """build_detector_hint_list must index hints by DETECTOR position (excluding
    user-added curves) so a stated bake time reaches the correct physical bake
    even when a user-added curve sorts ahead of the detected bakes."""

    def _loader(self):
        from pathlib import Path

        from src.data.loader import ThermalProfileLoader

        csv = (
            Path(__file__).resolve().parent.parent
            / "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"
        )
        ldr = ThermalProfileLoader()
        ldr.load_csv(file_path=str(csv))
        return ldr

    def test_hint_maps_to_correct_detected_bake_with_user_added_ahead(self):
        ldr = self._loader()
        assert [c["start_idx"] for c in ldr.all_curves] == [13, 651, 5888]
        ldr.add_manual_curve(350, 620)  # sorts to position 1, pushing detected to 2/3/4

        idx651 = next(i for i, c in enumerate(ldr.all_curves) if c["start_idx"] == 651)
        kind, key = ldr._curve_stable_key(idx651)
        assert kind == "detector"
        session = {bake_time_session_key("f", kind, key): 20.0}

        hints = build_detector_hint_list(ldr, "f", session)
        # Detector-position indexed, length == 3 detected curves; the 20-min
        # (1200 s) hint sits at detector position 1 (the physical start-651 bake).
        assert hints == [None, 1200.0, None]

        ldr.set_expected_durations(hints)
        assert len(ldr.all_curves) == 4  # no bake dropped, no length mismatch
        d3 = next(c for c in ldr.all_curves if c["start_idx"] == 5888)
        assert d3["end_idx"] == 6185  # the start-5888 bake is untouched (old bug moved it)

    def test_no_hint_returns_none(self):
        ldr = self._loader()
        assert build_detector_hint_list(ldr, "f", {}) is None
