"""Temperature Profile tab — extracted verbatim from app.py's original tab1 block."""
import streamlit as st

from src.visualization.plots import ThermalPlotter
from sensor_naming import get_default_sensors


def render():
    st.header("Temperature Profile Analysis")

    # Display options for this tab
    col1, col2 = st.columns([1, 3])
    with col1:
        show_all_sensors = st.checkbox("Show all sensors", value=False, key=f"temp_profile_show_all_{st.session_state.current_curve_index}")

    if not show_all_sensors:
        with col2:
            # Get sensor role assignments for labeling
            assignments = st.session_state.loader.get_sensor_assignments_with_overrides(st.session_state.current_curve_index)

            # Create labels showing sensor roles
            sensor_labels = {}
            core_sensor = assignments.get('core_sensor')
            surface_sensor = assignments.get('surface_sensor')
            internal_sensors = assignments.get('internal_sensors', [])
            ambient_sensors = assignments.get('ambient_sensors', [])

            for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']:
                if sensor == core_sensor:
                    sensor_labels[sensor] = f"{sensor} (Core)"
                elif sensor == surface_sensor:
                    sensor_labels[sensor] = f"{sensor} (Surface)"
                elif sensor in internal_sensors:
                    sensor_labels[sensor] = f"{sensor} (Internal)"
                elif sensor in ambient_sensors:
                    sensor_labels[sensor] = f"{sensor} (Ambient)"
                else:
                    sensor_labels[sensor] = sensor

            default_sensors = get_default_sensors(st.session_state.loader)
            selected_sensors = st.multiselect(
                "Select sensors to display on graph",
                options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
                default=default_sensors,
                format_func=lambda x: sensor_labels.get(x, x),
                key=f"temp_profile_sensor_select_{st.session_state.current_curve_index}"
            )
    else:
        selected_sensors = None

    # Build sensor roles dictionary for visualization
    sensor_roles = {}
    assignments = st.session_state.loader.get_sensor_assignments_with_overrides()
    core_sensor = assignments.get('core_sensor')
    surface_sensor = assignments.get('surface_sensor')
    internal_sensors = assignments.get('internal_sensors', [])
    ambient_sensors = assignments.get('ambient_sensors', [])

    for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']:
        if sensor == core_sensor:
            sensor_roles[sensor] = 'core'
        elif sensor == surface_sensor:
            sensor_roles[sensor] = 'surface'
        elif sensor in internal_sensors:
            sensor_roles[sensor] = 'internal'
        elif sensor in ambient_sensors:
            sensor_roles[sensor] = 'ambient'

    # Create main temperature plot
    plotter = ThermalPlotter()
    fig_temp = plotter.plot_temperature_profile(
        st.session_state.data,
        show_zones=st.session_state.get('show_zones', True),
        sensors=selected_sensors,
        sensor_roles=sensor_roles
    )
    st.plotly_chart(fig_temp, use_container_width=True)

    # Temperature gradient heatmap
    st.subheader("Temperature Distribution Heatmap")
    fig_heatmap = plotter.plot_temperature_gradient_heatmap(st.session_state.data)
    st.plotly_chart(fig_heatmap, use_container_width=True)
