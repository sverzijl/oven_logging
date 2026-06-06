"""
Thermal Profile Analyzer for Bread Baking Optimization
A Streamlit application for analyzing temperature profiles in manufacturing environments.
"""
import streamlit as st

import sidebar
from session_state import initialize_session_state
from tabs import (
    bakeout_analysis,
    boundary_review,
    curve_comparison,
    heating_analysis,
    quality_metrics,
    recommendations,
    s_curve_analysis,
    spatial_evolution,
    temperature_profile,
    zone_analysis,
)

# Page configuration
st.set_page_config(
    page_title="Thermal Profile Analyzer",
    page_icon="🍞",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

initialize_session_state()

# Title and description
st.title("🍞 Thermal Profile Analyzer")
st.markdown("### Optimize bread baking processes through advanced thermal analysis")

sidebar.render()

# Tab dispatch — single parameterised builder collapsing the old 7-/8-tab
# duplication at app.py:573-592. Curve-comparison is appended conditionally.
TAB_SPECS = [
    ("🔬 Curve Boundaries", boundary_review.render),
    ("📈 Temperature Profile", temperature_profile.render),
    ("🌡️ Spatial Evolution", spatial_evolution.render),
    ("📉 S-Curve Analysis", s_curve_analysis.render),
    ("🎯 Zone Analysis", zone_analysis.render),
    ("📊 Quality Metrics", quality_metrics.render),
    ("🔥 Heating Analysis", heating_analysis.render),
    ("💧 Bake-Out Analysis", bakeout_analysis.render),
    ("💡 Recommendations", recommendations.render),
]

# Main content area
if st.session_state.data is None:
    # Welcome screen
    st.info("👆 Please upload one or more thermal profile CSV files to begin analysis")

    with st.expander("📖 How to use this application"):
        st.markdown("""
        1. **Upload Data**: Use the sidebar to upload one or more CSV files from Combustion Inc. temperature probes
        2. **Analyze**: The application will automatically detect and analyze all baking curves in each file
        3. **Compare**: When multiple curves are available (from one or multiple files), use the comparison tab
        4. **Explore**: Navigate through different tabs to view various analyses
        5. **Optimize**: Review recommendations for process improvements

        **Key Features:**
        - Multi-file support for comparing different baking sessions
        - Automatic detection of multiple curves within each file
        - Real-time temperature profile visualization
        - S-Curve analysis with landmark identification
        - Bake-out percentage calculation and optimization
        - Critical zone analysis (yeast kill, starch gelatinization, etc.)
        - Quality metrics and uniformity analysis
        - Process optimization recommendations
        - Product-specific quality diagnostics
        """)
else:
    tab_specs = list(TAB_SPECS)
    if len(st.session_state.all_curves) > 1:
        tab_specs.append(("🔄 Curve Comparison", curve_comparison.render))

    labels = [label for label, _ in tab_specs]
    tab_objects = st.tabs(labels)
    for (_, render_fn), tab_obj in zip(tab_specs, tab_objects):
        with tab_obj:
            render_fn()

# Footer
st.divider()
st.markdown("""
<div style="text-align: center; color: #666;">
    Thermal Profile Analyzer v1.0 | Optimize your baking process with data-driven insights
</div>
""", unsafe_allow_html=True)
