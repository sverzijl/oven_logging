"""Curve Comparison tab — extracted from app.py's original tab8 block.

Rendered only when `len(st.session_state.all_curves) > 1`; the dispatcher in
app.py gates inclusion.
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analysis.curve_comparison import (
    CurveComparison,
    transform_sensor_assignments_to_roles,
)
from src.analysis.s_curve_analysis import SCurveAnalyzer
from src.visualization.plots import ThermalPlotter


def render():
    st.header("Curve Comparison")

    show_zones = st.session_state.get('show_zones', True)
    plotter = ThermalPlotter()

    # Allow selection of curves to compare
    st.subheader("Select curves to compare")

    # Group curves by file for better organization
    files_dict = {}
    for i, curve in enumerate(st.session_state.all_curves):
        filename = curve['filename']
        if filename not in files_dict:
            files_dict[filename] = []
        files_dict[filename].append((i, curve))

    # Create checkboxes grouped by file
    curve_checkboxes = {}
    for filename, curves in files_dict.items():
        st.markdown(f"**{filename}**")
        for global_idx, curve_info in curves:
            curve_data = curve_info['curve_data']
            file_curve_idx = curve_info['file_curve_index']

            # Create label
            if len(curves) > 1:
                label = f"Curve {file_curve_idx+1} ({curve_data['duration']:.1f} min, Max {curve_data['max_temp']:.0f}°C)"
            else:
                label = f"{curve_data['duration']:.1f} min, Max {curve_data['max_temp']:.0f}°C"

            checked = st.checkbox(
                label,
                value=global_idx == st.session_state.global_curve_index,
                key=f"curve_check_{global_idx}"
            )
            curve_checkboxes[global_idx] = checked
        st.write("")  # Add space between files

    # Get selected curves
    selected_curves = [idx for idx, checked in curve_checkboxes.items() if checked]

    if len(selected_curves) < 2:
        st.info("📊 Please select at least 2 curves to compare")
        return

    # Prepare curves for comparison
    curves_for_comparison = []
    for idx in selected_curves:
        curve_info = st.session_state.all_curves[idx]

        # Get sensor roles for this curve
        sensor_roles = {}
        if 'loader' in curve_info:
            # Temporarily set to this curve to get sensor roles
            original_idx = curve_info['loader'].current_curve_index
            curve_info['loader'].set_current_curve(curve_info['file_curve_index'])
            sensor_assignments = curve_info['loader'].get_sensor_assignments()
            sensor_roles = transform_sensor_assignments_to_roles(sensor_assignments)
            curve_info['loader'].set_current_curve(original_idx)

        curves_for_comparison.append({
            'curve_data': {'data': curve_info['curve_data']['data']},
            'sensor_roles': sensor_roles,
            'metadata': curve_info.get('metadata', {}),
            'filename': curve_info['filename'],
            'file_curve_index': curve_info['file_curve_index']
        })

    # Create comparison object
    comparison = CurveComparison(curves_for_comparison)

    # Create tabs for different comparison views
    comp_tab1, comp_tab2, comp_tab3, comp_tab4, comp_tab5 = st.tabs([
        "Temperature Profiles", "Zone Analysis", "S-Curve Analysis",
        "Heating Rates", "Quality Metrics"
    ])

    # Temperature Profile Comparison
    with comp_tab1:
        st.subheader("Role-Based Temperature Comparison")

        # Get role-based data
        role_data = comparison.get_role_based_data()

        # For internal sensors, we need to get the properly filtered list from each curve
        # This ensures we only show sensors that are actually inside the loaf
        internal_data_filtered = []
        for idx in selected_curves:
            curve_info = st.session_state.all_curves[idx]
            curve_data = curve_info['curve_data']['data']
            curve_loader = curve_info['loader']

            # Get filtered internal sensors using the same logic as S-curve analysis
            internal_sensors = curve_loader.get_internal_sensors(
                curve_info['file_curve_index'],
                curve_data
            )

            if internal_sensors:
                # Extract temperature data for these sensors
                internal_temps = []
                for sensor in internal_sensors:
                    if sensor in curve_data.columns:
                        internal_temps.append(curve_data[sensor].values)

                if internal_temps:
                    # Get curve name from existing role_data
                    curve_name = None
                    curve_short_name = None
                    for existing_data in role_data.get('internal', []):
                        # Match by time array length (simple but effective)
                        if len(existing_data['time']) == len(curve_data['TimeMinutes']):
                            curve_name = existing_data['curve_name']
                            curve_short_name = existing_data['curve_short_name']
                            break

                    if curve_name:
                        internal_data_filtered.append({
                            'time': curve_data['TimeMinutes'].values,
                            'temperature': np.array(internal_temps).T,  # Time x Sensors
                            'curve_name': curve_name,
                            'curve_short_name': curve_short_name,
                            'sensors': internal_sensors
                        })

        # Replace the internal data with filtered version
        role_data['internal'] = internal_data_filtered

        # Create columns for different roles
        col1, col2 = st.columns(2)

        with col1:
            # Core temperature comparison
            st.markdown("### Core Temperature")
            fig_core = plotter.plot_role_based_comparison(role_data, 'core', show_zones)
            st.plotly_chart(fig_core, use_container_width=True)

            # Ambient temperature comparison
            st.markdown("### Ambient Temperature")
            fig_ambient = plotter.plot_role_based_comparison(role_data, 'ambient', False)
            st.plotly_chart(fig_ambient, use_container_width=True)

        with col2:
            # Surface temperature comparison
            st.markdown("### Surface Temperature")
            fig_surface = plotter.plot_role_based_comparison(role_data, 'surface', show_zones)
            st.plotly_chart(fig_surface, use_container_width=True)

            # Internal temperature comparison
            st.markdown("### Internal Temperature Range")
            fig_internal = plotter.plot_role_based_comparison(role_data, 'internal', False)
            st.plotly_chart(fig_internal, use_container_width=True)

    # Zone Analysis Comparison
    with comp_tab2:
        st.subheader("Temperature Zone Duration Comparison")

        # Get zone comparison data
        zone_comparison = comparison.compare_zone_durations()

        # Display zone comparison chart
        fig_zones = plotter.plot_zone_duration_comparison(zone_comparison)
        st.plotly_chart(fig_zones, use_container_width=True)

        # Display zone comparison table
        st.markdown("### Zone Duration Details")
        st.dataframe(zone_comparison, use_container_width=True)

    # S-Curve Analysis Comparison
    with comp_tab3:
        st.subheader("S-Curve Comparison with Landmarks")

        # Prepare S-curve data
        s_curve_data = []
        landmark_comparison = comparison.compare_s_curve_landmarks()

        for idx in selected_curves:
            curve_info = st.session_state.all_curves[idx]
            curve_data = curve_info['curve_data']['data']

            # Get landmarks for this curve
            s_curve_analyzer = SCurveAnalyzer(curve_data, curve_info.get('metadata', {}))
            landmarks = s_curve_analyzer.identify_landmarks()

            # Get internal sensors for this curve
            # Note: We need to get the curve-specific sensor assignments
            curve_loader = curve_info['loader']
            internal_sensors = curve_loader.get_internal_sensors(
                curve_info['file_curve_index'],
                curve_data
            )

            # Create descriptive name
            if len(st.session_state.files[curve_info['filename']]['curves']) > 1:
                curve_name = f"{curve_info['filename']} - Curve {curve_info['file_curve_index']+1}"
            else:
                curve_name = curve_info['filename']

            s_curve_data.append({
                'data': curve_data,
                'landmarks': landmarks,
                'name': curve_name,
                'internal_sensors': internal_sensors
            })

        # Plot S-curve comparison
        fig_s_curve = plotter.plot_s_curve_comparison(s_curve_data)
        st.plotly_chart(fig_s_curve, use_container_width=True)

        # Display landmark comparison table
        st.markdown("### Landmark Comparison")
        st.dataframe(landmark_comparison, use_container_width=True)

    # Heating Rate Comparison
    with comp_tab4:
        st.subheader("Heating Rate Analysis")

        # Get heating rate data
        heating_data = comparison.get_heating_rate_comparison()

        # Plot heating rate comparison
        fig_heating = plotter.plot_heating_rate_comparison(heating_data)
        st.plotly_chart(fig_heating, use_container_width=True)

        # Display consistency scores
        if heating_data['consistency_scores']:
            st.markdown("### Heating Consistency Scores")
            consistency_df = pd.DataFrame(heating_data['consistency_scores'])

            # Create metric columns
            cols = st.columns(len(consistency_df))
            for idx, (col, row) in enumerate(zip(cols, consistency_df.itertuples())):
                with col:
                    st.metric(
                        label=row.curve_name,
                        value=f"{row.score:.1f}%",
                        delta=None
                    )

    # Quality Metrics Comparison
    with comp_tab5:
        st.subheader("Quality Metrics Comparison")

        # Get quality metrics
        quality_metrics = comparison.compare_quality_metrics()

        # Display metrics table
        st.dataframe(quality_metrics, use_container_width=True)

        # Create visual metrics dashboard
        st.markdown("### Quality Score Overview")

        # Extract quality scores for visualization
        quality_scores = []
        for _, row in quality_metrics.iterrows():
            try:
                score = float(row['Quality Score'])
                quality_scores.append({
                    'Curve': row['Curve'],
                    'Score': score
                })
            except:
                pass

        if quality_scores:
            # Create bar chart of quality scores
            scores_df = pd.DataFrame(quality_scores)
            fig_quality = go.Figure(data=[
                go.Bar(
                    x=scores_df['Curve'],
                    y=scores_df['Score'],
                    marker_color=['green' if s >= 80 else 'orange' if s >= 60 else 'red'
                                for s in scores_df['Score']],
                    text=[f"{s:.1f}" for s in scores_df['Score']],
                    textposition='auto'
                )
            ])

            fig_quality.update_layout(
                title="Quality Score Comparison",
                xaxis_title="Curve",
                yaxis_title="Quality Score",
                yaxis=dict(range=[0, 100]),
                showlegend=False
            )

            st.plotly_chart(fig_quality, use_container_width=True)
