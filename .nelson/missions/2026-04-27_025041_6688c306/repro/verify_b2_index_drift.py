"""
Flotilla sign-off: Verification 1 — B2 Index Drift (pre-flotilla vs post-flotilla)

Pre-flotilla scenario: simulate what old render() did with two separate calls
that could use different curve indices.

Post-flotilla scenario: call build_sensor_role_map(loader, explicit_index) directly
and show both indices return the correctly indexed result.
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# repro/ -> mission/ -> missions/ -> .nelson/ -> oven_logging/
REPO = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..', '..'))
sys.path.insert(0, REPO)
os.chdir(REPO)

from src.data.loader import ThermalProfileLoader
from src.ui.sensor_role_helpers import build_sensor_role_map, build_sensor_label_map

CSV = 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'

loader = ThermalProfileLoader()
loader.load_csv(CSV)

print(f"Loaded: {CSV}")
print(f"Curve count: {loader.get_curve_count()}")
print()

# Inject distinct per-curve assignments (same perturbation as M0)
loader.curve_sensor_assignments[0]["core"]    = "T3"
loader.curve_sensor_assignments[0]["surface"] = "T6"
loader.curve_sensor_assignments[1]["core"]    = "T1"
loader.curve_sensor_assignments[1]["surface"] = "T7"

print("=== INJECTED assignments ===")
print(f"  curve 0: core=T3, surface=T6")
print(f"  curve 1: core=T1, surface=T7")
print()

# -------------------------------------------------------------------
# PRE-FLOTILLA: simulate old render() with diverged calls
# line-19: get_sensor_assignments_with_overrides(1) — curve_index from session_state
# line-53: get_sensor_assignments_with_overrides()  — no arg, falls to loader.current_curve_index=0
# -------------------------------------------------------------------
loader.current_curve_index = 0

a19_pre = loader.get_sensor_assignments_with_overrides(1)   # line-19 sim
a53_pre = loader.get_sensor_assignments_with_overrides()    # line-53 sim (no arg)

print("=== PRE-FLOTILLA scenario (old dual-call with diverged indices) ===")
print(f"  line-19 surface (curve_index=1): {a19_pre.get('surface_sensor')}")
print(f"  line-53 surface (no arg → idx=0): {a53_pre.get('surface_sensor')}")
pre_diverged = a19_pre.get('surface_sensor') != a53_pre.get('surface_sensor')
print(f"  DIVERGED: {pre_diverged}")
if pre_diverged:
    print("  PRE-FLOTILLA VERDICT: BUG PRESENT — label (T7) contradicts plot roles (T6)")
else:
    print("  PRE-FLOTILLA VERDICT: No divergence (perturbation may be ineffective)")
print()

# -------------------------------------------------------------------
# POST-FLOTILLA: new render() hoists curve_index once, passes to BOTH helpers
# Simulate: curve_index = st.session_state.current_curve_index = 1 (user is on curve 1)
# build_sensor_label_map(loader, curve_index) — same index to both calls
# build_sensor_role_map(loader, curve_index)  — same index to both calls
# -------------------------------------------------------------------
curve_index = 1   # the hoisted value

labels_post = build_sensor_label_map(loader, curve_index)
roles_post  = build_sensor_role_map(loader, curve_index)

print("=== POST-FLOTILLA scenario (hoisted curve_index=1 passed to both helpers) ===")
print(f"  label map surface sensor T7: {labels_post.get('T7')}")
print(f"  role map T7: {roles_post.get('T7')}")
print(f"  role map T6: {roles_post.get('T6')}")
# For curve 1: T7=surface, T6=unknown (correct)
post_label_surface_correct = 'Surface' in labels_post.get('T7', '')
post_role_T7_surface = roles_post.get('T7') == 'surface'
post_role_T6_not_surface = roles_post.get('T6') != 'surface'
print(f"  T7 labelled as Surface: {post_label_surface_correct}")
print(f"  T7 role = surface: {post_role_T7_surface}")
print(f"  T6 role != surface: {post_role_T6_not_surface}")

# Also test curve_index=0 to confirm isolation
roles_curve0 = build_sensor_role_map(loader, 0)
print(f"  curve_index=0 → T6 role: {roles_curve0.get('T6')}  (should be surface)")
print(f"  curve_index=0 → T7 role: {roles_curve0.get('T7')}  (should NOT be surface)")

post_fixed = post_label_surface_correct and post_role_T7_surface and post_role_T6_not_surface
print()
if post_fixed:
    print("POST-FLOTILLA VERDICT: BUG FIXED — single hoisted curve_index, both helpers agree")
else:
    print("POST-FLOTILLA VERDICT: STILL BROKEN — verify helper implementation")

print()
print("=== SUMMARY ===")
print(f"  Pre-flotilla divergence (BUG present): {pre_diverged}")
print(f"  Post-flotilla fixed (no divergence):   {post_fixed}")
print(f"  Flip confirmed: {pre_diverged and post_fixed}")
