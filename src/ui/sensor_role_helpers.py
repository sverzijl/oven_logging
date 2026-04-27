"""Pure helpers for building per-sensor role and label maps.

Bridge between ThermalProfileLoader.get_sensor_assignments_with_overrides()
and tab-side role-aware UI rendering. No Streamlit dependency.
"""
from typing import Optional
from config.constants import SENSOR_LIST


def build_sensor_role_map(loader, curve_index: Optional[int] = None) -> dict:
    """Returns {'T1': 'core'|'surface'|'internal'|'ambient'|'unknown', ...} for every sensor in SENSOR_LIST.

    Respects loader.get_sensor_assignments_with_overrides(curve_index) — physics corrections AND manual overrides apply.
    Role-priority order matches tabs/temperature_profile.py:52-67: core, surface, internal, ambient, unknown.
    """
    assignments = loader.get_sensor_assignments_with_overrides(curve_index)
    core_sensor = assignments.get('core_sensor')
    surface_sensor = assignments.get('surface_sensor')
    internal_sensors = assignments.get('internal_sensors', [])
    ambient_sensors = assignments.get('ambient_sensors', [])

    role_map = {}
    for sensor in SENSOR_LIST:
        if sensor == core_sensor:
            role_map[sensor] = 'core'
        elif sensor == surface_sensor:
            role_map[sensor] = 'surface'
        elif sensor in internal_sensors:
            role_map[sensor] = 'internal'
        elif sensor in ambient_sensors:
            role_map[sensor] = 'ambient'
        else:
            role_map[sensor] = 'unknown'
    return role_map


def build_sensor_label_map(loader, curve_index: Optional[int] = None, *, role_format: str = "({role})") -> dict:
    """Returns {'T1': 'T1 (Core)', ...} for multiselect format_func / display.

    Sensors with role 'unknown' map to plain 'T1' (no suffix).
    role_format is a format string with one named placeholder {role}; the role token is
    capitalised before substitution (matches Pattern A's "(Core)" style).
    Respects loader overrides identically to build_sensor_role_map.
    """
    role_map = build_sensor_role_map(loader, curve_index)
    label_map = {}
    for sensor, role in role_map.items():
        if role == 'unknown':
            label_map[sensor] = sensor
        else:
            label_map[sensor] = f"{sensor} {role_format.format(role=role.capitalize())}"
    return label_map
