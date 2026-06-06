"""Tests for the per-tab error boundary in app.py (#18).

A failing tab must not blank the whole app with a raw traceback. The tab
render loop wraps each ``render_fn()`` in a try/except that shows an
``st.error`` and (only behind a debug flag) ``st.exception``. One tab's
failure must not stop the other tabs from rendering.

The error-boundary logic lives in a small pure helper
``app.render_tab_safely`` so it is unit-testable without spinning up the
whole Streamlit app; an AppTest scenario then proves the integration:
a tab whose render raises shows an st.error and the AppTest has no
top-level exception.
"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app  # noqa: E402


class TestRenderTabSafelyHelper:
    """Unit tests for the pure error-boundary helper."""

    def test_successful_render_calls_render_fn(self):
        import streamlit as st

        called = {"n": 0}

        def _ok():
            called["n"] += 1

        with patch.object(st, "error") as mock_error, \
                patch.object(st, "exception") as mock_exc:
            app.render_tab_safely(_ok)

        assert called["n"] == 1
        mock_error.assert_not_called()
        mock_exc.assert_not_called()

    def test_failing_render_shows_error_not_raise(self):
        import streamlit as st

        def _boom():
            raise RuntimeError("kaboom")

        ss = MagicMock()
        ss.get.side_effect = lambda key, default=None: default  # debug off
        with patch.object(st, "session_state", ss), \
                patch.object(st, "error") as mock_error, \
                patch.object(st, "exception") as mock_exc:
            # Must NOT raise — the boundary swallows it.
            app.render_tab_safely(_boom)

        assert mock_error.called, "a failing tab must surface an st.error"
        # Debug flag off -> no raw exception/traceback shown.
        mock_exc.assert_not_called()

    def test_failing_render_shows_exception_when_debug(self):
        import streamlit as st

        def _boom():
            raise ValueError("detail")

        ss = MagicMock()
        ss.get.side_effect = lambda key, default=None: (
            True if key == "debug" else default
        )
        with patch.object(st, "session_state", ss), \
                patch.object(st, "error") as mock_error, \
                patch.object(st, "exception") as mock_exc:
            app.render_tab_safely(_boom)

        assert mock_error.called
        assert mock_exc.called, "debug flag on -> st.exception should show"

    def test_one_failure_does_not_block_other_tabs(self):
        import streamlit as st

        order = []

        def _boom():
            order.append("boom-start")
            raise RuntimeError("nope")

        def _ok():
            order.append("ok")

        ss = MagicMock()
        ss.get.side_effect = lambda key, default=None: default
        with patch.object(st, "session_state", ss), \
                patch.object(st, "error"), \
                patch.object(st, "exception"):
            for fn in (_boom, _ok):
                app.render_tab_safely(fn)

        assert "ok" in order, "second tab must render after first one failed"


class TestErrorBoundaryAppTest:
    """Integration: a tab that raises shows st.error, no top-level exception."""

    def test_failing_tab_shows_error_no_top_level_exception(self):
        try:
            from streamlit.testing.v1 import AppTest
        except ImportError:
            pytest.skip("streamlit.testing not available")

        script = """
import streamlit as st
import sys
sys.path.insert(0, r"{root}")
import app

def good():
    st.write("good tab")

def bad():
    raise RuntimeError("intentional tab failure")

for fn in (bad, good):
    app.render_tab_safely(fn)
""".format(root=PROJECT_ROOT)

        at = AppTest.from_string(script, default_timeout=30)
        at.run()

        assert not at.exception, (
            f"error boundary must absorb the failure; got {at.exception}"
        )
        assert len(at.error) >= 1, "a failing tab must surface an st.error"
        # The healthy tab still rendered.
        markdowns = " ".join(str(m.value) for m in at.markdown)
        assert "good tab" in markdowns, "healthy tab must still render"
