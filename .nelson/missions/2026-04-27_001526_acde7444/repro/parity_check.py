"""
Verification 2: Helper-vs-inline parity check.

Loads a real CSV, computes build_sensor_role_map() AND the inline loop
from temperature_profile.py:52-67, asserts they match for all assigned sensors.
Also checks build_sensor_label_map() against the Pattern A inline loop.
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
sys.path.insert(0, REPO)
os.chdir(REPO)

from src.data.loader import ThermalProfileLoader
from src.ui.sensor_role_helpers import build_sensor_role_map, build_sensor_label_map

SINGLE_CURVE_CSV = 'ProbeData_1000F3C1_2025-05-23 09_11_59.csv'
MULTI_CURVE_CSV = 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'

SENSOR_KEYS = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']


def inline_role_loop_pattern_b(assignments: dict) -> dict:
    """Exact replica of tabs/temperature_profile.py:52-67 (Pattern B — no 'unknown')."""
    sensor_roles = {}
    core_sensor = assignments.get('core_sensor')
    surface_sensor = assignments.get('surface_sensor')
    internal_sensors = assignments.get('internal_sensors', [])
    ambient_sensors = assignments.get('ambient_sensors', [])

    for sensor in SENSOR_KEYS:
        if sensor == core_sensor:
            sensor_roles[sensor] = 'core'
        elif sensor == surface_sensor:
            sensor_roles[sensor] = 'surface'
        elif sensor in internal_sensors:
            sensor_roles[sensor] = 'internal'
        elif sensor in ambient_sensors:
            sensor_roles[sensor] = 'ambient'
        # Note: template does NOT set 'unknown'; helper DOES. This is a known intentional divergence.
    return sensor_roles


def inline_label_loop_pattern_a(assignments: dict) -> dict:
    """Exact replica of tabs/temperature_profile.py:22-38 (Pattern A)."""
    sensor_labels = {}
    core_sensor = assignments.get('core_sensor')
    surface_sensor = assignments.get('surface_sensor')
    internal_sensors = assignments.get('internal_sensors', [])
    ambient_sensors = assignments.get('ambient_sensors', [])

    for sensor in SENSOR_KEYS:
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
    return sensor_labels


def check_parity(csv_path, label):
    loader = ThermalProfileLoader()
    loader.load_csv(csv_path)
    curve_idx = loader.current_curve_index

    assignments = loader.get_sensor_assignments_with_overrides(curve_idx)
    print(f"\n=== {label} (curve_idx={curve_idx}) ===")
    print(f"  Assignments: core={assignments.get('core_sensor')}, "
          f"surface={assignments.get('surface_sensor')}, "
          f"internal={assignments.get('internal_sensors')}, "
          f"ambient={assignments.get('ambient_sensors')}")

    # Pattern B (role map) parity
    helper_role = build_sensor_role_map(loader, curve_idx)
    inline_role = inline_role_loop_pattern_b(assignments)

    role_divergence = []
    for sensor in SENSOR_KEYS:
        if sensor in inline_role:
            if helper_role.get(sensor) != inline_role[sensor]:
                role_divergence.append(
                    f"  DIVERGE: {sensor}: helper={helper_role.get(sensor)!r} vs inline={inline_role[sensor]!r}"
                )
        else:
            # inline didn't assign it; helper should say 'unknown'
            if helper_role.get(sensor) != 'unknown':
                role_divergence.append(
                    f"  DIVERGE: {sensor}: helper={helper_role.get(sensor)!r} vs inline=<not set> (expected 'unknown')"
                )

    if role_divergence:
        print("  Pattern B PARITY: FAIL")
        for d in role_divergence:
            print(d)
    else:
        print("  Pattern B PARITY: OK — all assigned sensors match; unassigned are 'unknown' in helper")
        print(f"  helper_role = {helper_role}")

    # Pattern A (label map) parity
    helper_label = build_sensor_label_map(loader, curve_idx)
    inline_label = inline_label_loop_pattern_a(assignments)

    if helper_label == inline_label:
        print("  Pattern A PARITY: OK — label maps are byte-identical")
    else:
        print("  Pattern A PARITY: FAIL")
        for sensor in SENSOR_KEYS:
            if helper_label.get(sensor) != inline_label.get(sensor):
                print(f"  DIVERGE: {sensor}: helper={helper_label.get(sensor)!r} vs inline={inline_label.get(sensor)!r}")

    return len(role_divergence) == 0 and (helper_label == inline_label)


all_ok = True
all_ok &= check_parity(SINGLE_CURVE_CSV, "Single-curve CSV (F3C1)")

loader_multi = ThermalProfileLoader()
loader_multi.load_csv(MULTI_CURVE_CSV)
for i in range(loader_multi.get_curve_count()):
    loader_multi.current_curve_index = i
    assignments = loader_multi.get_sensor_assignments_with_overrides(i)
    print(f"\n=== Multi-curve CSV (BA3C) curve {i} ===")
    print(f"  Assignments: core={assignments.get('core_sensor')}, "
          f"surface={assignments.get('surface_sensor')}, "
          f"internal={assignments.get('internal_sensors')}, "
          f"ambient={assignments.get('ambient_sensors')}")
    helper_role = build_sensor_role_map(loader_multi, i)
    inline_role = inline_role_loop_pattern_b(assignments)
    role_divergence = []
    for sensor in SENSOR_KEYS:
        if sensor in inline_role:
            if helper_role.get(sensor) != inline_role[sensor]:
                role_divergence.append(f"  DIVERGE: {sensor}: helper={helper_role.get(sensor)!r} vs inline={inline_role[sensor]!r}")
        else:
            if helper_role.get(sensor) != 'unknown':
                role_divergence.append(f"  DIVERGE: {sensor}: helper={helper_role.get(sensor)!r} vs inline=<not set>")
    if role_divergence:
        print("  Pattern B PARITY: FAIL"); [print(d) for d in role_divergence]; all_ok = False
    else:
        print(f"  Pattern B PARITY: OK | helper_role = {helper_role}")

    helper_label = build_sensor_label_map(loader_multi, i)
    inline_label = inline_label_loop_pattern_a(assignments)
    if helper_label == inline_label:
        print("  Pattern A PARITY: OK")
    else:
        print("  Pattern A PARITY: FAIL"); all_ok = False
        for sensor in SENSOR_KEYS:
            if helper_label.get(sensor) != inline_label.get(sensor):
                print(f"  DIVERGE: {sensor}: helper={helper_label.get(sensor)!r} vs inline={inline_label.get(sensor)!r}")

print(f"\n=== OVERALL PARITY RESULT: {'PASS' if all_ok else 'FAIL'} ===")
