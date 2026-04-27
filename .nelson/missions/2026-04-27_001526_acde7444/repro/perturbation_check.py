"""
Verification 3: Perturbation re-run.

Loads ProbeData_1000BA3C_2025-05-30 17_59_37.csv (3 curves).
Injects distinct per-curve surface assignments and verifies:
 (a) build_sensor_role_map(loader, 0) and build_sensor_role_map(loader, 1) differ as expected
 (b) build_sensor_role_map(loader) with loader.current_curve_index=0 equals
     build_sensor_role_map(loader, curve_index=0)
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
sys.path.insert(0, REPO)
os.chdir(REPO)

from src.data.loader import ThermalProfileLoader
from src.ui.sensor_role_helpers import build_sensor_role_map

CSV = 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'

loader = ThermalProfileLoader()
loader.load_csv(CSV)
n_curves = loader.get_curve_count()
print(f"Loaded: {CSV}")
print(f"Curve count: {n_curves}")
assert n_curves >= 2, f"Expected >= 2 curves, got {n_curves}"

# Inject distinct per-curve surface overrides
loader.set_sensor_override(0, 'surface', 'T6')
loader.set_sensor_override(1, 'surface', 'T7')

# --- (a) Per-curve distinction ---
result_0 = build_sensor_role_map(loader, curve_index=0)
result_1 = build_sensor_role_map(loader, curve_index=1)

print(f"\nbuild_sensor_role_map(loader, curve_index=0):")
print(f"  {result_0}")
print(f"\nbuild_sensor_role_map(loader, curve_index=1):")
print(f"  {result_1}")

assert result_0.get('T6') == 'surface', f"FAIL: curve 0 T6 expected 'surface', got {result_0.get('T6')!r}"
assert result_1.get('T7') == 'surface', f"FAIL: curve 1 T7 expected 'surface', got {result_1.get('T7')!r}"
assert result_0.get('T7') != 'surface', f"FAIL: curve 0 T7 should NOT be surface (got {result_0.get('T7')!r})"
assert result_1.get('T6') != 'surface', f"FAIL: curve 1 T6 should NOT be surface (got {result_1.get('T6')!r})"

print("\n(a) PASS — curve 0 shows T6='surface', curve 1 shows T7='surface'; they differ as expected.")

# --- (b) Default-index-from-loader-state ---
loader.current_curve_index = 0
result_default = build_sensor_role_map(loader)           # no curve_index arg
result_explicit = build_sensor_role_map(loader, curve_index=0)

print(f"\nbuild_sensor_role_map(loader)  [current_curve_index=0]:")
print(f"  {result_default}")
print(f"\nbuild_sensor_role_map(loader, curve_index=0):")
print(f"  {result_explicit}")

assert result_default == result_explicit, (
    f"FAIL: default call differs from explicit(0):\n  default={result_default}\n  explicit={result_explicit}"
)
print("\n(b) PASS — default-index call matches explicit(0).")

# Cleanup
loader.clear_sensor_overrides(0)
loader.clear_sensor_overrides(1)

print("\n=== PERTURBATION CHECK: ALL ASSERTIONS PASSED ===")
