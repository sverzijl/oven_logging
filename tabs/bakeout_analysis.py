"""Bake-Out Analysis tab — extracted from app.py's original tab6 block."""
import streamlit as st

from config.constants import BAKEOUT_TARGETS
from src.visualization.plots import ThermalPlotter

# Substrings that mark an *actionable* (warning) bake-out recommendation.
# WAVE-A FOLLOW-UP b: the analyzer emits a plain List[str] with no severity
# field, and Wave A's reworded #25 line is a directional minutes correction
# ("more min ... needed" / "fewer min ... needed") that matches neither
# "increase" nor "reduce". Broaden the match so directional corrections, dryness
# and excess-moisture flags all render as warnings; "optimal"/"maintain" stay
# success. Display-only.
_WARNING_MARKERS = (
    "increase",
    "reduce",
    "more min",
    "fewer min",
    "less min",
    "too dry",
    "excess moisture",
    "extend bake",
    "check oven",
)


def bakeout_rec_style(rec: str) -> str:
    """Return ``"warning"`` for an actionable recommendation, else ``"success"``.

    Robust to the directional #25 wording that the old "increase"/"reduce"-only
    match missed.
    """
    low = rec.lower()
    if any(marker in low for marker in _WARNING_MARKERS):
        return "warning"
    return "success"


def render():
    st.header("Bake-Out Analysis")

    product_type = st.session_state.get('product_type', 'white_pan')

    # Perform bake-out analysis
    bakeout = st.session_state.s_curve_analyzer.analyze_bake_out(product_type)

    # Bake-out visualization
    plotter = ThermalPlotter()
    fig_bakeout = plotter.plot_bakeout_analysis(bakeout, st.session_state.data)
    st.plotly_chart(fig_bakeout, width="stretch")

    # Bake-out recommendations
    if bakeout.recommendations:
        st.subheader("Bake-Out Recommendations")
        for rec in bakeout.recommendations:
            if bakeout_rec_style(rec) == "warning":
                st.warning(f"⚠️ {rec}")
            else:
                st.success(f"✅ {rec}")

    # Product-specific targets
    target_range = BAKEOUT_TARGETS[product_type]
    st.info(f"Target bake-out percentage for {product_type.replace('_', ' ').title()}: {target_range[0]}-{target_range[1]}%")
