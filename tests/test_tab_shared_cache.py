"""Tests for the per-(file, curve) analyzer/report dedup helper (#20).

The ZoneAnalyzer was built twice (zone_analysis + recommendations) and the
S-curve optimization report was computed twice (s_curve_analysis +
recommendations) on every rerun. ``tabs._shared`` builds each ONCE and caches
it in ``st.session_state`` keyed by ``(current_file, current_curve_index,
product_type)``, rebuilding only when the key changes.

@st.cache_data is fragile here because the loader / DataFrame arguments are not
hashable, so we dedup via session_state instead (see #20 in the prompt).
"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import MagicMock, patch

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from tabs import _shared  # noqa: E402


class _DictState(dict):
    """A session_state stand-in supporting both attribute and item access
    plus .get(), like st.session_state."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def _base_state(s_curve_analyzer=None):
    ss = _DictState()
    ss["current_file"] = "f.csv"
    ss["current_curve_index"] = 0
    ss["product_type"] = "white_pan"
    ss["data"] = pd.DataFrame({"TimeMinutes": [0.0, 1.0]})
    ss["metadata"] = {"sample_period_s": 1.0}
    ss["loader"] = MagicMock()
    ss["s_curve_analyzer"] = s_curve_analyzer or MagicMock()
    return ss


class TestSCurveReportCache:
    def test_report_built_once_then_reused(self):
        import streamlit as st

        analyzer = MagicMock()
        analyzer.generate_optimization_report.return_value = {"summary": "x"}
        ss = _base_state(analyzer)

        with patch.object(st, "session_state", ss):
            r1 = _shared.get_s_curve_report()
            r2 = _shared.get_s_curve_report()

        assert r1 is r2
        analyzer.generate_optimization_report.assert_called_once()
        _, kwargs = analyzer.generate_optimization_report.call_args
        assert kwargs.get("product_type") == "white_pan"

    def test_report_rebuilt_when_curve_changes(self):
        import streamlit as st

        analyzer = MagicMock()
        analyzer.generate_optimization_report.side_effect = [
            {"summary": "a"},
            {"summary": "b"},
        ]
        ss = _base_state(analyzer)

        with patch.object(st, "session_state", ss):
            _shared.get_s_curve_report()
            ss["current_curve_index"] = 1  # switch curve
            _shared.get_s_curve_report()

        assert analyzer.generate_optimization_report.call_count == 2

    def test_report_rebuilt_when_product_changes(self):
        import streamlit as st

        analyzer = MagicMock()
        analyzer.generate_optimization_report.side_effect = [
            {"summary": "a"},
            {"summary": "b"},
        ]
        ss = _base_state(analyzer)

        with patch.object(st, "session_state", ss):
            _shared.get_s_curve_report()
            ss["product_type"] = "sourdough"
            _shared.get_s_curve_report()

        assert analyzer.generate_optimization_report.call_count == 2


class TestZoneAnalyzerCache:
    def test_zone_analyzer_built_once_then_reused(self):
        import streamlit as st

        ss = _base_state()
        with patch.object(st, "session_state", ss), \
                patch("tabs._shared.ZoneAnalyzer") as ZA:
            ZA.return_value = MagicMock()
            z1 = _shared.get_zone_analyzer()
            z2 = _shared.get_zone_analyzer()

        assert z1 is z2
        ZA.assert_called_once()

    def test_zone_analyzer_rebuilt_when_curve_changes(self):
        import streamlit as st

        ss = _base_state()
        with patch.object(st, "session_state", ss), \
                patch("tabs._shared.ZoneAnalyzer") as ZA:
            ZA.side_effect = [MagicMock(), MagicMock()]
            _shared.get_zone_analyzer()
            ss["current_curve_index"] = 2
            _shared.get_zone_analyzer()

        assert ZA.call_count == 2
