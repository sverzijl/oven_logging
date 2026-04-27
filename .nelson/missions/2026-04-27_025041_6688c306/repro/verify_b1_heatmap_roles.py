"""
Flotilla sign-off: Verification 2 — B1 Heatmap role-blindness (pre-flotilla vs post-flotilla)

Pre-flotilla: call plot_temperature_gradient_heatmap(data) with no roles arg.
             y-axis should show hardcoded SENSOR_NAMES regardless of any assignment.

Post-flotilla: call plot_temperature_gradient_heatmap(data, sensor_roles={...}).
              y-axis should show role-annotated labels for assigned sensors.
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..', '..'))
sys.path.insert(0, REPO)
os.chdir(REPO)

import numpy as np
import pandas as pd
from src.visualization.plots import ThermalPlotter
from config.constants import SENSOR_NAMES

n = 50
data = pd.DataFrame({
    'TimeMinutes': np.linspace(0, 30, n),
    'T1': 85 + np.linspace(0, 10, n),   # will be 'core'
    'T2': 82 + np.linspace(0, 10, n),   # will be 'surface'
    'T3': 80 + np.linspace(0, 8, n),
    'T4': 78 + np.linspace(0, 7, n),
    'T5': 100 + np.linspace(0, 50, n),
    'T6': 110 + np.linspace(0, 60, n),
    'T7': 150 + np.linspace(0, 20, n),  # will be 'ambient'
    'T8': 200 + np.linspace(0, 30, n),
})

plotter = ThermalPlotter()

# -------------------------------------------------------------------
# PRE-FLOTILLA: no sensor_roles arg
# Expected: all labels are firmware-default SENSOR_NAMES, no role suffix
# -------------------------------------------------------------------
fig_pre = plotter.plot_temperature_gradient_heatmap(data)
y_pre = list(fig_pre.data[0].y)

print("=== PRE-FLOTILLA: no sensor_roles arg ===")
print(f"  y-axis labels: {y_pre}")
# Pre-flotilla expected: ['Core 1', 'Core 2', 'Core 3', 'Core 4', 'Middle 1', 'Middle 2', 'Near Surface', 'Surface']
# None should contain '(Surface)' or '(Ambient)' etc.
pre_has_role_suffix = any('(' in label for label in y_pre)
print(f"  Any role suffix in labels: {pre_has_role_suffix}")
# This is the bug: T2 is override-surface but label says 'Core 2', T7 is ambient but label says 'Near Surface'
pre_T2_label = y_pre[1]  # index 1 = T2
pre_T7_label = y_pre[6]  # index 6 = T7
print(f"  T2 label (expect 'Core 2', not 'Core 2 (Surface)'): {pre_T2_label}")
print(f"  T7 label (expect 'Near Surface', not 'Near Surface (Ambient)'): {pre_T7_label}")
print()

# -------------------------------------------------------------------
# POST-FLOTILLA: pass sensor_roles={T2: surface, T7: ambient}
# Expected: T2 label includes '(Surface)', T7 includes '(Ambient)', others unchanged
# -------------------------------------------------------------------
sensor_roles = {'T2': 'surface', 'T7': 'ambient'}
fig_post = plotter.plot_temperature_gradient_heatmap(data, sensor_roles=sensor_roles)
y_post = list(fig_post.data[0].y)

print("=== POST-FLOTILLA: sensor_roles={'T2': 'surface', 'T7': 'ambient'} ===")
print(f"  y-axis labels: {y_post}")
post_T2_label = y_post[1]  # T2
post_T7_label = y_post[6]  # T7
post_T8_label = y_post[7]  # T8 — no role, should be firmware default

print(f"  T2 label: {post_T2_label}")
print(f"  T7 label: {post_T7_label}")
print(f"  T8 label (no role override, expect firmware default): {post_T8_label}")

post_T2_has_surface = '(Surface)' in post_T2_label
post_T7_has_ambient = '(Ambient)' in post_T7_label
post_T8_default = '(' not in post_T8_label

print()
print(f"  T2 includes '(Surface)': {post_T2_has_surface}")
print(f"  T7 includes '(Ambient)': {post_T7_has_ambient}")
print(f"  T8 uses firmware default (no suffix): {post_T8_default}")

post_fixed = post_T2_has_surface and post_T7_has_ambient and post_T8_default

print()
print("=== SUMMARY ===")
print(f"  Pre-flotilla role-blind (BUG present): {not pre_has_role_suffix}")
print(f"  Post-flotilla role-aware (BUG fixed):  {post_fixed}")
print(f"  Flip confirmed: {(not pre_has_role_suffix) and post_fixed}")
