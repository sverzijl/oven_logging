"""Sensor-naming helpers shared across the Streamlit UI.

Pure functions that map a `ThermalProfileLoader`'s per-curve role assignments
onto display labels and default-selection lists. Extracted verbatim from the
monolithic `app.py`.
"""
import streamlit as st

from config.constants import SENSOR_NAMES


def get_dynamic_sensor_names(loader):
    """
    Generate sensor names based on actual sensor role assignments.

    Args:
        loader: ThermalProfileLoader instance

    Returns:
        dict: Mapping of sensor names to their actual roles
    """
    sensor_names = dict(SENSOR_NAMES)  # Start with default names

    if loader:
        assignments = loader.get_sensor_assignments()

        # If we have assignment info, update sensor names
        if 'core_info' in assignments:
            core_sensors = assignments['core_info'].get('all_sensors', {})
            for sensor, count in core_sensors.items():
                if sensor and sensor.startswith('T'):
                    sensor_names[sensor] = f"Core (Primary)" if sensor == assignments.get('core') else "Core"

        if 'surface_info' in assignments:
            surface_sensors = assignments['surface_info'].get('all_sensors', {})
            for sensor, count in surface_sensors.items():
                if sensor and sensor.startswith('T'):
                    sensor_names[sensor] = f"Surface (Primary)" if sensor == assignments.get('surface') else "Surface"

        if 'ambient_info' in assignments:
            ambient_sensors = assignments['ambient_info'].get('all_sensors', {})
            for sensor, count in ambient_sensors.items():
                if sensor and sensor.startswith('T'):
                    sensor_names[sensor] = f"Ambient (Primary)" if sensor == assignments.get('ambient') else "Ambient"

    return sensor_names


def get_default_sensors(loader):
    """
    Get default sensors to display based on actual assignments.

    Args:
        loader: ThermalProfileLoader instance

    Returns:
        list: List of sensor names to display by default
    """
    if not loader:
        return ['T1', 'T4', 'T6', 'T8']  # Fallback defaults

    defaults = []

    # Get current curve index from session state if available
    curve_index = st.session_state.get('current_curve_index', 0) if hasattr(st, 'session_state') else 0

    # Add core sensor
    core_sensor = loader.get_core_sensor(curve_index)
    if core_sensor:
        defaults.append(core_sensor)

    # Add surface sensor
    surface_sensor = loader.get_surface_sensor(curve_index)
    if surface_sensor and surface_sensor not in defaults:
        defaults.append(surface_sensor)

    # Add one or two internal sensors (not core) for showing spread
    internal_sensors = loader.get_internal_sensors(curve_index)
    for sensor in internal_sensors:
        if sensor != core_sensor and sensor not in defaults:
            defaults.append(sensor)
            if len(defaults) >= 3:  # Limit to show core + surface + 1 internal
                break

    # Add one ambient sensor if space
    if len(defaults) < 4:
        ambient_sensors = loader.get_ambient_sensors(curve_index)
        if ambient_sensors and ambient_sensors[0] not in defaults:
            defaults.append(ambient_sensors[0])

    # Ensure we have at least some sensors
    if not defaults:
        defaults = ['T1', 'T4', 'T7']

    return sorted(defaults, key=lambda x: int(x[1]))
