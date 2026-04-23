"""Recommendations tab — extracted from app.py's original tab7 block.

Recomputes `s_curve_report` and the `ZoneAnalyzer` locally because the
original code reused locals from tabs 2 and 3 — which tab-isolated modules
cannot rely on.
"""
import pandas as pd
import streamlit as st

from src.analysis.zone_analysis import ZoneAnalyzer
from src.visualization.plots import ThermalPlotter


def render():
    st.header("Process Optimization Recommendations")

    s_curve_report = st.session_state.s_curve_analyzer.generate_optimization_report()
    zone_analyzer = ZoneAnalyzer(
        st.session_state.data,
        st.session_state.metadata['sample_period_s'],
        st.session_state.loader
    )

    # Get S-curve diagnostics
    s_curve_issues = s_curve_report['quality_issues']
    s_curve_recommendations = s_curve_report['recommendations']

    # Quality diagnostics visualization
    plotter = ThermalPlotter()
    fig_diagnostics = plotter.plot_quality_diagnostics(s_curve_issues, s_curve_report['overall_score'])
    st.plotly_chart(fig_diagnostics, use_container_width=True)

    # S-curve based recommendations
    if s_curve_recommendations:
        st.subheader("🎯 S-Curve Optimization Recommendations")
        for rec in s_curve_recommendations:
            if rec['priority'] == 'High':
                st.error(f"""
                **High Priority**: {rec['action']}

                Expected Result: {rec['expected_result']}
                """)
            else:
                st.warning(f"""
                **{rec['priority']} Priority**: {rec['action']}

                Expected Result: {rec['expected_result']}
                """)

    # Zone-based recommendations
    st.subheader("🌡️ Zone-Based Recommendations")
    recommendations = zone_analyzer.recommend_zone_optimizations()

    if recommendations:
        # Group by priority
        high_priority = [r for r in recommendations if r['priority'] == 'High']
        medium_priority = [r for r in recommendations if r['priority'] == 'Medium']
        low_priority = [r for r in recommendations if r['priority'] == 'Low']

        if high_priority:
            st.markdown("### 🔴 High Priority")
            for rec in high_priority:
                st.warning(f"""
                **{rec['zone']}**: {rec['issue']}

                💡 **Recommendation**: {rec['recommendation']}
                """)

        if medium_priority:
            st.markdown("### 🟡 Medium Priority")
            for rec in medium_priority:
                st.info(f"""
                **{rec['zone']}**: {rec['issue']}

                💡 **Recommendation**: {rec['recommendation']}
                """)

        if low_priority:
            st.markdown("### 🟢 Low Priority")
            for rec in low_priority:
                st.success(f"""
                **{rec['zone']}**: {rec['issue']}

                💡 **Recommendation**: {rec['recommendation']}
                """)
    else:
        st.success("✅ No zone-based issues found.")

    # Display summary
    st.divider()
    st.markdown(f"### 📋 Analysis Summary")
    st.markdown(s_curve_report['summary'])

    # Process events
    st.subheader("Key Process Events")
    events = st.session_state.analyzer.identify_process_events()

    event_data = []
    for event_name, event_info in events.items():
        if isinstance(event_info, dict) and 'time_minutes' in event_info:
            event_data.append({
                'Event': event_name.replace('_', ' ').title(),
                'Time (min)': f"{event_info['time_minutes']:.1f}",
                'Temperature (°C)': f"{event_info.get('temperature', 'N/A'):.1f}" if event_info.get('temperature') else 'N/A',
                'Details': f"Rate: {event_info.get('rate', 0):.2f}°C/s" if 'rate' in event_info else ''
            })

    if event_data:
        st.table(pd.DataFrame(event_data))
