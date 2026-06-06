"""Recommendations tab — extracted from app.py's original tab7 block.

The S-curve report and ZoneAnalyzer are sourced from ``tabs._shared`` so they
are built ONCE per (file, curve, product) selection rather than re-derived here
after the S-Curve and Zone Analysis tabs already built them on the same rerun
(#20). ``st.tabs`` renders every tab body eagerly, so without this dedup the
report/ZoneAnalyzer were computed two-or-more times per rerun.
"""
import pandas as pd
import streamlit as st

from src.visualization.plots import ThermalPlotter
from tabs._shared import get_s_curve_report, get_zone_analyzer


def render():
    st.header("Process Optimization Recommendations")

    # Product-aware (#8) report + ZoneAnalyzer, deduped per selection (#20).
    s_curve_report = get_s_curve_report()
    zone_analyzer = get_zone_analyzer()

    # Get S-curve diagnostics
    s_curve_issues = s_curve_report['quality_issues']
    s_curve_recommendations = s_curve_report['recommendations']

    # Quality diagnostics visualization
    plotter = ThermalPlotter()
    fig_diagnostics = plotter.plot_quality_diagnostics(s_curve_issues, s_curve_report['overall_score'])
    st.plotly_chart(fig_diagnostics, width="stretch")

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
