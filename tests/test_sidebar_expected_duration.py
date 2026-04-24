"""Sidebar UI helper tests for the expected-bake-time widgets (M6 HMS Spartan).

Introduced by flotilla mission M6 on branch ``refactor/expected-bake-time``.
Covers the pure helper functions that translate between:
  - UI widget values (minutes, `None` for empty)
  - Detector-frame hint lists (seconds, `list[float | None] | None`)
  - Session-state storage keys (per-file, per-curve_number)

Full Streamlit widget integration is verified manually (see captain's
log §Validation).  The helpers here are pure enough to unit-test and
pin the conversion contract before a user ever interacts with the UI.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ui.expected_duration_widgets import (
    minutes_to_seconds,
    seconds_to_minutes,
    build_hint_list_from_session,
    session_key_for_curve,
)


# ---------------------------------------------------------------------------
# Tests: unit conversion
# ---------------------------------------------------------------------------


class TestUnitConversion:

    def test_minutes_to_seconds_roundtrip(self):
        for m in [1.0, 15.5, 25.25, 60.0]:
            assert seconds_to_minutes(minutes_to_seconds(m)) == pytest.approx(m)

    def test_none_passthrough_minutes_to_seconds(self):
        assert minutes_to_seconds(None) is None

    def test_none_passthrough_seconds_to_minutes(self):
        assert seconds_to_minutes(None) is None

    def test_zero_minutes_returns_none_not_zero_seconds(self):
        """Streamlit ``st.number_input`` with ``value=None`` and
        ``min_value>0`` requires a sentinel; we use 0.0 → None to avoid
        the widget complaining about the None default.
        """
        assert minutes_to_seconds(0.0) is None


# ---------------------------------------------------------------------------
# Tests: session-state key shape
# ---------------------------------------------------------------------------


class TestSessionKey:

    def test_key_includes_filename_and_curve_number(self):
        """Widget key must scope by filename AND curve_number (1-indexed).

        By filename: different files get independent hints — M5's
        per-file loader contract mirrors this.
        By curve_number (NOT by `current_curve_index`): switching the
        currently-viewed curve must not bleed widget state between
        curves.  Precedent: mission 2026-04-24_102020_af6532e1 fix to
        temperature_profile tab.
        """
        k = session_key_for_curve("my_file.csv", curve_number=2)
        assert "my_file.csv" in k
        assert "2" in k
        # Negative control: curve_number differs → key differs
        k_other = session_key_for_curve("my_file.csv", curve_number=3)
        assert k != k_other

    def test_keys_for_different_files_differ(self):
        a = session_key_for_curve("a.csv", curve_number=1)
        b = session_key_for_curve("b.csv", curve_number=1)
        assert a != b


# ---------------------------------------------------------------------------
# Tests: session → hint list
# ---------------------------------------------------------------------------


class TestBuildHintListFromSession:

    def test_empty_session_returns_none(self):
        session_mock: dict[str, float | None] = {}
        result = build_hint_list_from_session(
            filename="a.csv", n_curves=2, session_store=session_mock
        )
        assert result is None, (
            "no hints entered → hint list should be None, not [None, None]"
        )

    def test_partial_session_returns_list_with_none_entries(self):
        """When only some curves have hints, return a list with None
        for the unset ones — the detector (M3) short-circuits on None
        entries per-curve.
        """
        k1 = session_key_for_curve("a.csv", curve_number=1)
        k2 = session_key_for_curve("a.csv", curve_number=2)
        session_mock: dict[str, float | None] = {k1: 25.0}  # only bake-1 hinted
        result = build_hint_list_from_session(
            filename="a.csv", n_curves=2, session_store=session_mock
        )
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == pytest.approx(25.0 * 60.0)  # minutes → seconds
        assert result[1] is None

    def test_full_session_returns_populated_list(self):
        k1 = session_key_for_curve("a.csv", curve_number=1)
        k2 = session_key_for_curve("a.csv", curve_number=2)
        session_mock: dict[str, float | None] = {k1: 25.0, k2: 30.0}
        result = build_hint_list_from_session(
            filename="a.csv", n_curves=2, session_store=session_mock
        )
        assert result == [25.0 * 60.0, 30.0 * 60.0]

    def test_hints_from_other_files_are_ignored(self):
        k_a = session_key_for_curve("a.csv", curve_number=1)
        k_b = session_key_for_curve("b.csv", curve_number=1)
        session_mock: dict[str, float | None] = {k_a: 25.0, k_b: 99.0}
        result_a = build_hint_list_from_session(
            filename="a.csv", n_curves=1, session_store=session_mock
        )
        result_b = build_hint_list_from_session(
            filename="b.csv", n_curves=1, session_store=session_mock
        )
        assert result_a == [25.0 * 60.0]
        assert result_b == [99.0 * 60.0]

    def test_zero_or_none_minutes_treated_as_no_hint(self):
        """``st.number_input`` with empty input returns None or 0.0
        depending on configuration — both must be treated as "no hint"."""
        k1 = session_key_for_curve("a.csv", curve_number=1)
        k2 = session_key_for_curve("a.csv", curve_number=2)
        session_mock: dict[str, float | None] = {k1: 0.0, k2: None}
        result = build_hint_list_from_session(
            filename="a.csv", n_curves=2, session_store=session_mock
        )
        assert result is None, (
            "all-empty session should collapse to overall None"
        )
