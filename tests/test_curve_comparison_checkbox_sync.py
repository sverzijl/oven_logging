"""Tests for curve-comparison checkbox re-sync after a sidebar curve switch (#37).

The per-curve checkboxes used to set ``value=global_idx == global_curve_index``.
Streamlit only honours ``value=`` on the FIRST instantiation of a keyed widget;
after that the widget state in ``st.session_state[key]`` wins. So once the user
touched (or first rendered) the checkboxes, switching the active curve in the
sidebar no longer moved the checked box — the comparison stayed pinned to the
old curve.

The fix drives the checkboxes from ``st.session_state`` directly: when the
detected active curve index changes, the checkbox keys are (re)written BEFORE
the widgets instantiate, and the widgets no longer pass ``value=``. The
decision is a pure helper ``sync_curve_checkbox_state`` so it is unit-testable.
"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import patch

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import inspect  # noqa: E402

import tabs.curve_comparison as cc  # noqa: E402


class _DictState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class TestSyncCurveCheckboxState:
    def _keys(self, n):
        return [f"curve_check_{i}" for i in range(n)]

    def test_first_render_selects_active_curve_only(self):
        import streamlit as st

        ss = _DictState()
        keys = self._keys(3)
        with patch.object(st, "session_state", ss):
            cc.sync_curve_checkbox_state(
                global_indices=[0, 1, 2], keys=keys, active_index=1
            )
        assert ss["curve_check_0"] is False
        assert ss["curve_check_1"] is True
        assert ss["curve_check_2"] is False
        assert ss["_curve_check_synced_active"] == 1

    def test_switch_active_curve_moves_the_check(self):
        import streamlit as st

        ss = _DictState()
        keys = self._keys(3)
        with patch.object(st, "session_state", ss):
            cc.sync_curve_checkbox_state(
                global_indices=[0, 1, 2], keys=keys, active_index=0
            )
            # User then toggles a couple boxes manually...
            ss["curve_check_2"] = True
            # ...then switches the active curve in the sidebar to index 2.
            cc.sync_curve_checkbox_state(
                global_indices=[0, 1, 2], keys=keys, active_index=2
            )
        assert ss["curve_check_0"] is False
        assert ss["curve_check_2"] is True, (
            "#37: switching the active curve must re-check the new active box"
        )
        assert ss["_curve_check_synced_active"] == 2

    def test_no_resync_when_active_unchanged(self):
        """Manual toggles persist across reruns when the active curve is the
        same (so the user can build an arbitrary comparison selection)."""
        import streamlit as st

        ss = _DictState()
        keys = self._keys(3)
        with patch.object(st, "session_state", ss):
            cc.sync_curve_checkbox_state(
                global_indices=[0, 1, 2], keys=keys, active_index=0
            )
            ss["curve_check_1"] = True  # user adds curve 1 to the comparison
            # Rerun with the SAME active index — must NOT clobber the manual add.
            cc.sync_curve_checkbox_state(
                global_indices=[0, 1, 2], keys=keys, active_index=0
            )
        assert ss["curve_check_1"] is True, (
            "manual selection must survive reruns with unchanged active curve"
        )

    def test_render_does_not_pass_value_to_checkbox(self):
        """Structural guard: the checkbox must read state, not re-seed value=
        (which Streamlit ignores after first render)."""
        src = inspect.getsource(cc.render)
        # The per-curve loop's st.checkbox must not pass value=.
        assert "value=global_idx" not in src, (
            "#37: checkbox must be driven from session_state, not value="
        )
