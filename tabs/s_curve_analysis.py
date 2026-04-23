"""S-Curve Analysis tab — extracted from app.py's original tab2 block."""
import pandas as pd
import streamlit as st

from src.visualization.plots import ThermalPlotter


def render():
    st.header("S-Curve Analysis")

    # Calculate S-curve analysis
    s_curve_report = st.session_state.s_curve_analyzer.generate_optimization_report()
    landmarks = s_curve_report['landmarks']
    zones = s_curve_report['zone_analysis']

    # Get internal sensors for temperature spread visualization
    internal_sensors = st.session_state.loader.get_internal_sensors(
        st.session_state.current_curve_index,
        st.session_state.data
    )

    # Plot S-curve
    plotter = ThermalPlotter()
    fig_s_curve = plotter.plot_s_curve(
        st.session_state.data,
        landmarks,
        zones,
        show_targets=True,
        internal_sensors=internal_sensors
    )
    st.plotly_chart(fig_s_curve, use_container_width=True)

    # Landmark summary
    st.subheader("S-Curve Landmarks")

    landmark_cols = st.columns(3)
    for i, (name, landmark) in enumerate(landmarks.items()):
        col = landmark_cols[i % 3]
        with col:
            status_emoji = "✅" if landmark.is_within_target else "⚠️"
            st.markdown(f"""
            <div class="metric-card">
                <h4>{status_emoji} {landmark.name}</h4>
                <p><b>Temperature:</b> {landmark.temperature}°C</p>
                <p><b>Time:</b> {landmark.time_minutes:.1f} min ({landmark.time_percentage:.1f}%)</p>
                <p><b>Target:</b> {landmark.target_percentage_range[0]}-{landmark.target_percentage_range[1]}%</p>
            </div>
            """, unsafe_allow_html=True)

    # Zone summary
    st.subheader("S-Curve Zones")
    zone_data = []
    for zone_name, zone_info in zones.items():
        zone_data.append({
            'Zone': zone_name.replace('_', ' ').title(),
            'Duration (min)': f"{zone_info['duration_minutes']:.1f}",
            'Percentage': f"{zone_info['percentage_of_bake']:.1f}%",
            'Max Temp': f"{zone_info.get('max_temp_reached', 0):.1f}°C"
        })
    st.dataframe(pd.DataFrame(zone_data), use_container_width=True)

    # Overall score
    score = s_curve_report['overall_score']
    st.metric("S-Curve Quality Score", f"{score:.1f}/100")
