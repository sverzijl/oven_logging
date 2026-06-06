"""Zone Analysis tab — extracted from app.py's original tab3 block."""
import streamlit as st

from src.visualization.plots import ThermalPlotter
from src.visualization.zone_cards import create_zone_summary_dashboard
from tabs._shared import get_zone_analyzer


def render():
    st.header("Temperature Zone Analysis")

    # Zone analysis — deduped per (file, curve) so Recommendations doesn't
    # rebuild the same ZoneAnalyzer on the same rerun (#20).
    zone_analyzer = get_zone_analyzer()
    zone_analysis = st.session_state.analyzer.analyze_temperature_zones()

    # Create beautiful zone dashboard
    create_zone_summary_dashboard(zone_analysis)

    # Zone duration chart
    plotter = ThermalPlotter()
    st.markdown("### Zone Duration Timeline")
    fig_zones = plotter.plot_zone_duration_chart(zone_analysis)
    st.plotly_chart(fig_zones, width="stretch")

    # Zone transitions
    st.markdown("### Zone Transitions")
    transitions = zone_analyzer.calculate_zone_transitions()

    if not transitions.empty:
        # Add explanation for transitions
        with st.expander("ℹ️ Understanding Zone Transitions", expanded=False):
            st.markdown("""
            Zone transitions show how quickly the product moves between critical temperature ranges:

            • **Duration**: Time spent transitioning between zones
            • **Rate**: How fast temperature changes (°C/min)
            • **Type**: Whether measuring core (internal) or surface temperature

            Smooth, controlled transitions generally produce better quality.
            """)

        # Display transitions with better formatting
        for _, trans in transitions.iterrows():
            temp_type_icon = "🎯" if trans['temperature_type'] == 'core' else "🌡️"
            rate_color = "#52c41a" if 0.5 <= trans['rate_c_per_min'] <= 2.0 else "#faad14"

            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"{temp_type_icon} **{trans['from_zone']} → {trans['to_zone']}**")
            with col2:
                st.markdown(f"Duration: {trans['duration_minutes']:.1f} min")
            with col3:
                st.markdown(f"<span style='color: {rate_color}'>Rate: {trans['rate_c_per_min']:.1f}°C/min</span>", unsafe_allow_html=True)
    else:
        st.info("No zone transitions detected - this may indicate rapid heating or missing temperature zones.")
