"""Tests that the sidebar product selector drives the analysis (#8).

Wave A gave ``SCurveAnalyzer.generate_optimization_report`` /
``diagnose_quality_issues`` / ``analyze_bake_out`` an optional
``product_type`` argument. The selected product (in
``st.session_state.product_type``) must actually be threaded into those
calls from the S-Curve, Recommendations and Bake-Out tabs — otherwise the
selector is cosmetic.

We patch ``st.session_state`` and the heavy plotting/UI calls, then capture
the ``product_type`` that each tab passes to the analyzer.
"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import MagicMock, patch

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

SELECTED_PRODUCT = "sourdough"


def _session_state(s_curve_analyzer, analyzer=None):
    ss = MagicMock()
    ss.product_type = SELECTED_PRODUCT
    ss.s_curve_analyzer = s_curve_analyzer
    ss.analyzer = analyzer or MagicMock()
    ss.loader = MagicMock()
    ss.loader.get_core_confidence.return_value = (None, None)
    ss.loader.get_internal_sensors.return_value = []
    ss.current_curve_index = 0
    ss.data = pd.DataFrame({"TimeMinutes": [0.0, 1.0, 2.0]})
    ss.metadata = {"sample_period_s": 1.0}
    ss.get.side_effect = lambda key, default=None: {
        "product_type": SELECTED_PRODUCT,
        "show_zones": True,
    }.get(key, default)
    return ss


def _fake_report():
    return {
        "landmarks": {},
        "zone_analysis": {},
        "quality_issues": [],
        "recommendations": [],
        "overall_score": 80.0,
        "summary": "ok",
    }


class TestSCurveTabThreadsProduct:
    def test_generate_optimization_report_gets_product(self):
        import streamlit as st
        import tabs.s_curve_analysis as mod

        analyzer = MagicMock()
        analyzer.generate_optimization_report.return_value = _fake_report()
        ss = _session_state(analyzer)

        from src.ui.core_confidence_banner import core_confidence_banner_text  # noqa: F401

        with patch.object(st, "session_state", ss), \
                patch.object(st, "header"), patch.object(st, "subheader"), \
                patch.object(st, "warning"), patch.object(st, "caption"), \
                patch.object(st, "markdown"), patch.object(st, "metric"), \
                patch.object(st, "plotly_chart"), patch.object(st, "dataframe"), \
                patch.object(st, "columns", return_value=[MagicMock(), MagicMock(), MagicMock()]), \
                patch("tabs.s_curve_analysis.ThermalPlotter"):
            mod.render()

        analyzer.generate_optimization_report.assert_called_once()
        _, kwargs = analyzer.generate_optimization_report.call_args
        passed = kwargs.get("product_type")
        if passed is None and analyzer.generate_optimization_report.call_args.args:
            passed = analyzer.generate_optimization_report.call_args.args[0]
        assert passed == SELECTED_PRODUCT, (
            f"S-Curve tab must pass product_type={SELECTED_PRODUCT!r}, got {passed!r}"
        )


class TestRecommendationsTabThreadsProduct:
    def test_generate_optimization_report_gets_product(self):
        import streamlit as st
        import tabs.recommendations as mod

        analyzer = MagicMock()
        analyzer.generate_optimization_report.return_value = _fake_report()
        ss = _session_state(analyzer)
        ss.analyzer.identify_process_events.return_value = {}

        with patch.object(st, "session_state", ss), \
                patch.object(st, "header"), patch.object(st, "subheader"), \
                patch.object(st, "warning"), patch.object(st, "info"), \
                patch.object(st, "success"), patch.object(st, "error"), \
                patch.object(st, "markdown"), patch.object(st, "divider"), \
                patch.object(st, "table"), patch.object(st, "plotly_chart"), \
                patch.object(st, "columns", return_value=[MagicMock(), MagicMock(), MagicMock()]), \
                patch("tabs.recommendations.ThermalPlotter"), \
                patch("tabs.recommendations.get_zone_analyzer") as GZA:
            # The report flows through tabs._shared.get_s_curve_report, which
            # calls the analyzer with the selected product_type.
            GZA.return_value.recommend_zone_optimizations.return_value = []
            mod.render()

        analyzer.generate_optimization_report.assert_called_once()
        call = analyzer.generate_optimization_report.call_args
        passed = call.kwargs.get("product_type")
        if passed is None and call.args:
            passed = call.args[0]
        assert passed == SELECTED_PRODUCT, (
            f"Recommendations tab must pass product_type={SELECTED_PRODUCT!r}, got {passed!r}"
        )


class TestBakeoutTabThreadsProduct:
    def test_analyze_bake_out_gets_product(self):
        import streamlit as st
        import tabs.bakeout_analysis as mod

        analyzer = MagicMock()
        bakeout = MagicMock()
        bakeout.recommendations = []
        analyzer.analyze_bake_out.return_value = bakeout
        ss = _session_state(analyzer)

        with patch.object(st, "session_state", ss), \
                patch.object(st, "header"), patch.object(st, "subheader"), \
                patch.object(st, "warning"), patch.object(st, "info"), \
                patch.object(st, "success"), patch.object(st, "plotly_chart"), \
                patch("tabs.bakeout_analysis.ThermalPlotter"):
            mod.render()

        analyzer.analyze_bake_out.assert_called_once()
        call = analyzer.analyze_bake_out.call_args
        passed = call.kwargs.get("product_type")
        if passed is None and call.args:
            passed = call.args[0]
        assert passed == SELECTED_PRODUCT, (
            f"Bake-Out tab must pass product_type={SELECTED_PRODUCT!r}, got {passed!r}"
        )
