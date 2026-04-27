"""
Claim (a) Empirical verification: Index drift between line-19 and line-53
of tabs/temperature_profile.py.

Loads ProbeData_1000BA3C_2025-05-30 17_59_37.csv (3 curves).
Forces divergence: loader.current_curve_index = 0, but line-19 passes
curve_index=1 explicitly and line-53 passes no arg (falls back to
loader.current_curve_index=0).
"""
import sys
import os

REPO = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'oven_logging')
# Actually from this script's location, repo is 5 levels up from mission/repro
# Let's do it cleanly:
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# mission dir = SCRIPT_DIR/..
# .nelson dir = SCRIPT_DIR/../..
# oven_logging = SCRIPT_DIR/../../..
REPO = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
sys.path.insert(0, REPO)
os.chdir(REPO)

from src.data.loader import ThermalProfileLoader

CSV = 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'

loader = ThermalProfileLoader()
loader.load_csv(CSV)

print(f"Loaded: {CSV}")
print(f"Curve count: {loader.get_curve_count()}")
print(f"loader.current_curve_index after load_csv: {loader.current_curve_index}")
print()

# --- Simulate line-19: explicit curve_index=1 ---
assignments_line19 = loader.get_sensor_assignments_with_overrides(1)

print("=== Line-19 simulation: get_sensor_assignments_with_overrides(1) ===")
print(f"  core_sensor:      {assignments_line19.get('core_sensor')}")
print(f"  surface_sensor:   {assignments_line19.get('surface_sensor')}")
print(f"  internal_sensors: {assignments_line19.get('internal_sensors')}")
print(f"  ambient_sensors:  {assignments_line19.get('ambient_sensors')}")
print()

# Force divergence: set loader.current_curve_index = 0
loader.current_curve_index = 0

# --- Simulate line-53: no arg (falls back to self.current_curve_index) ---
assignments_line53 = loader.get_sensor_assignments_with_overrides()

print("=== Line-53 simulation: get_sensor_assignments_with_overrides() [no arg, current=0] ===")
print(f"  core_sensor:      {assignments_line53.get('core_sensor')}")
print(f"  surface_sensor:   {assignments_line53.get('surface_sensor')}")
print(f"  internal_sensors: {assignments_line53.get('internal_sensors')}")
print(f"  ambient_sensors:  {assignments_line53.get('ambient_sensors')}")
print()

# Check divergence
keys = ['core_sensor', 'surface_sensor', 'internal_sensors', 'ambient_sensors']
diverged = any(assignments_line19.get(k) != assignments_line53.get(k) for k in keys)

if diverged:
    print("VERDICT: PASS — role assignments DIFFER between line-19 and line-53 calls.")
    print("         End-user sees labels and plot from DIFFERENT curve indices.")
    for k in keys:
        v19 = assignments_line19.get(k)
        v53 = assignments_line53.get(k)
        marker = "  <<< DIFFERS" if v19 != v53 else ""
        print(f"  {k}: line19={v19}  vs  line53={v53}{marker}")
else:
    print("VERDICT: FAIL — assignments are identical despite index divergence.")
    print("         Bug surface is theoretical, not actual for this CSV/curve pair.")

# Also show ALL three curves' assignments side by side
print()
print("=== All curve assignments for reference ===")
for i in range(loader.get_curve_count()):
    a = loader.get_sensor_assignments_with_overrides(i)
    print(f"  curve_index={i}: core={a.get('core_sensor')}, surface={a.get('surface_sensor')}, "
          f"internal={a.get('internal_sensors')}, ambient={a.get('ambient_sensors')}")
