"""Bake-Out Analysis tab — extracted from app.py's original tab6 block."""
import streamlit as st

from config.constants import BAKEOUT_TARGETS
from src.visualization.plots import ThermalPlotter


def render():
    st.header("Bake-Out Analysis")

    product_type = st.session_state.get('product_type', 'white_pan')

    # Perform bake-out analysis
    bakeout = st.session_state.s_curve_analyzer.analyze_bake_out(product_type)

    # Bake-out visualization
    plotter = ThermalPlotter()
    fig_bakeout = plotter.plot_bakeout_analysis(bakeout, st.session_state.data)
    st.plotly_chart(fig_bakeout, use_container_width=True)

    # Bake-out recommendations
    if bakeout.recommendations:
        st.subheader("Bake-Out Recommendations")
        for rec in bakeout.recommendations:
            if "increase" in rec.lower():
                st.warning(f"⚠️ {rec}")
            elif "reduce" in rec.lower():
                st.warning(f"⚠️ {rec}")
            else:
                st.success(f"✅ {rec}")

    # Product-specific targets
    target_range = BAKEOUT_TARGETS[product_type]
    st.info(f"Target bake-out percentage for {product_type.replace('_', ' ').title()}: {target_range[0]}-{target_range[1]}%")
