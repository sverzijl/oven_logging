"""S-Curve Analysis tab — extracted from app.py's original tab2 block."""
import pandas as pd
import streamlit as st

from src.ui.core_confidence_banner import core_confidence_banner_text
from src.visualization.plots import ThermalPlotter
from tabs._shared import get_s_curve_report


def render():
    st.header("S-Curve Analysis")

    # Core-confidence banner — shared predicate with the Temperature Profile
    # and Spatial Evolution tabs (M29). The S-curve is read off the core
    # trace, so a low-confidence core is worth flagging here too.
    _loader = st.session_state.loader
    _conf, _reason = _loader.get_core_confidence(st.session_state.current_curve_index)
    _level, _msg = core_confidence_banner_text(_conf, _reason)
    if _level == "warning":
        st.warning(_msg)
    elif _level == "caption":
        st.caption(_msg)

    # Product-aware (#8) S-curve report, deduped per selection (#20).
    s_curve_report = get_s_curve_report()
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
    st.plotly_chart(fig_s_curve, width="stretch")

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
    st.dataframe(pd.DataFrame(zone_data), width="stretch")

    # Overall score
    score = s_curve_report['overall_score']
    st.metric("S-Curve Quality Score", f"{score:.1f}/100")
