"""Temperature Profile tab — refactored to use canonical sensor role helpers."""
import streamlit as st

from src.ui.core_confidence_banner import core_confidence_banner_text
from src.ui.sensor_role_helpers import build_sensor_label_map, build_sensor_role_map
from src.visualization.plots import ThermalPlotter
from sensor_naming import get_default_sensors
from config.constants import SENSOR_LIST


def render():
    st.header("Temperature Profile Analysis")

    curve_index = st.session_state.current_curve_index
    loader = st.session_state.loader

    # Core-confidence banner — shared predicate with the Spatial Evolution
    # and S-Curve tabs (M29). Warns when the core position was extrapolated
    # past the probe tip and invites bake-metadata entry.
    _conf, _reason = loader.get_core_confidence(curve_index)
    _level, _msg = core_confidence_banner_text(_conf, _reason)
    if _level == "warning":
        st.warning(_msg)
    elif _level == "caption":
        st.caption(_msg)

    # SINGLE fetch — closes B2 and S6.
    sensor_labels = build_sensor_label_map(loader, curve_index)
    sensor_roles = build_sensor_role_map(loader, curve_index)

    # Display options
    col1, col2 = st.columns([1, 3])
    with col1:
        show_all_sensors = st.checkbox(
            "Show all sensors",
            value=False,
            key=f"temp_profile_show_all_{curve_index}",
        )

    if not show_all_sensors:
        with col2:
            default_sensors = get_default_sensors(loader)
            selected_sensors = st.multiselect(
                "Select sensors to display on graph",
                options=list(SENSOR_LIST),
                default=default_sensors,
                format_func=lambda x: sensor_labels.get(x, x),
                key=f"temp_profile_sensor_select_{curve_index}",
            )
    else:
        selected_sensors = None

    plotter = ThermalPlotter()
    fig_temp = plotter.plot_temperature_profile(
        st.session_state.data,
        show_zones=st.session_state.get('show_zones', True),
        sensors=selected_sensors,
        sensor_roles=sensor_roles,
    )
    st.plotly_chart(fig_temp, width="stretch")

    st.subheader("Temperature Distribution Heatmap")
    fig_heatmap = plotter.plot_temperature_gradient_heatmap(
        st.session_state.data,
        sensor_roles=sensor_roles,
    )
    st.plotly_chart(fig_heatmap, width="stretch")
