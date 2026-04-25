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
    boundary_state_label,
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
