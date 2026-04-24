"""Trace the outer loop on 1759 to verify which method fires for bakes 2 and 3."""
import os, sys
REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import numpy as np
import pandas as pd
from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import (
    CurveBoundaryDetector, _resolve_max_sensor_series, _SENSOR_COLUMNS,
)
from src.data.column_helpers import resolve_core_temperature_series
from tests.fixtures.curve_boundary_cases import load_real_case


df = load_real_case("1000BA3C_1759")
core = resolve_core_temperature_series(df).to_numpy(dtype=float)
max_sensor = _resolve_max_sensor_series(df, core)
ts = df["Timestamp"].to_numpy(dtype=float)

det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
pred_state = df["PredictionState"].to_numpy()

# Simulate the outer loop's _detect_start starting from various search_from values
def first_pred_trans(pred_state, search_from, n):
    for j in range(search_from, n - 1):
        if pred_state[j] == 'Probe Not Inserted' and pred_state[j + 1] != 'Probe Not Inserted':
            return j + 1
    return None

room = float(CURVE_DETECTION_CONFIG["ROOM_TEMP_MAX"])
confirm_n = int(CURVE_DETECTION_CONFIG["CONFIRMATION_WINDOW_SAMPLES"])
bake_active = 40.0
n = len(core)

print("=== 1759 outer-loop trace ===")
print(f"confirm_n={confirm_n}  room_temp_max={room}  bake_active={bake_active}")
print(f"n={n}")

# After bake 1 ends at 293, cliff_fired=True so _skip_probe_pull_tail runs.
# Simulate it.
search_from = 294  # end_idx + 1 = 293 + 1
print(f"\n--- After bake 1 (end_idx=293) ---")
print(f"search_from = 294")
j = search_from
# Fast-forward through samples where max > room_temp_max
advance1_start = j
while j < n and float(max_sensor[j]) > room:
    j += 1
print(f"fast-forward through max_sensor > {room}: ended at j={j} "
      f"(max_sensor[j]={max_sensor[j] if j < n else 'EOF'})")
# Then confirm sub-room run
confirmed = 0
while j < n and confirmed < confirm_n:
    if float(max_sensor[j]) <= room:
        confirmed += 1; j += 1
    else:
        confirmed = 0; j += 1
print(f"post-confirm search_from = {j} "
      f"(max_sensor[j-1]={max_sensor[j-1]}, core[j-1]={core[j-1]})")

skip_out_1 = j

# Now what does _detect_start return from here?
# Method 1: PredictionState transition after skip_out_1? Should be None because there's no 'Probe Not Inserted'
# after the first one.
m1 = first_pred_trans(pred_state, skip_out_1, n)
print(f"\n_detect_start from {skip_out_1}:")
print(f"  method 1 (PredictionState): {m1}")
# Method 2a: only fires at search_from==0, irrelevant here
# Method 2b: first max_sensor >= 40 with confirmation
def method_2b(start):
    for j in range(start, n):
        if max_sensor[j] < bake_active:
            continue
        look = min(confirm_n - 1, n - 1 - j)
        ok = all(max_sensor[j + k] >= bake_active for k in range(1, look + 1))
        if ok:
            return j
    return None
m2b = method_2b(skip_out_1)
print(f"  method 2b (max_sensor>=40, confirm): {m2b}")
print(f"  -> actual detector start for bake 2: 651")

# After bake 2 ends at 944 (cliff), skip_probe_pull_tail again
search_from = 945
print(f"\n--- After bake 2 (end_idx=944) ---")
print(f"search_from = 945")
j = search_from
while j < n and float(max_sensor[j]) > room:
    j += 1
print(f"fast-forward through max_sensor > {room}: ended at j={j}")
confirmed = 0
while j < n and confirmed < confirm_n:
    if float(max_sensor[j]) <= room:
        confirmed += 1; j += 1
    else:
        confirmed = 0; j += 1
print(f"post-confirm search_from = {j} (max_sensor[j-1]={max_sensor[j-1]})")
skip_out_2 = j
m1 = first_pred_trans(pred_state, skip_out_2, n)
m2b = method_2b(skip_out_2)
print(f"  method 1 (PredictionState): {m1}")
print(f"  method 2b (max_sensor): {m2b}")
print(f"  -> actual detector start for bake 3: 5888")

# Also verify bake 2 start via method 2b from skip_out_1
# Does max_sensor cross 40 before 651 between 294 and 651 inadvertently?
print(f"\nMax_sensor samples between 294 and 651 where max_sensor >= 40:")
hits = [(i, float(max_sensor[i])) for i in range(294, 652) if max_sensor[i] >= 40]
print(f"  count={len(hits)}, first={hits[0] if hits else None}")

# Verify bake 3 region 945..5888 — is there any false candidate?
print(f"\nMax_sensor between 945 and 5887 where max_sensor >= 40:")
hits2 = [(i, float(max_sensor[i])) for i in range(945, 5888) if max_sensor[i] >= 40]
print(f"  count={len(hits2)}")
if hits2:
    print(f"  first 5: {hits2[:5]}")
    print(f"  last 5:  {hits2[-5:]}")
    # Among those, any runs of length >= confirm_n?
    runs = []
    i = 0
    while i < len(hits2):
        # runs of consecutive indices
        j0 = i
        while j0 + 1 < len(hits2) and hits2[j0+1][0] == hits2[j0][0] + 1:
            j0 += 1
        runs.append((hits2[i][0], hits2[j0][0], j0 - i + 1))
        i = j0 + 1
    print(f"  runs of consecutive >=40 between 945 and 5887:")
    for r in runs[:10]:
        print(f"    start={r[0]} end={r[1]} length={r[2]}")
    if len(runs) > 10:
        print(f"    ... {len(runs) - 10} more runs")

# Verify gap between bake 2 and bake 3: how low does max_sensor get?
print(f"\nMax_sensor quiescent period (idx 950..5880): min={min(max_sensor[950:5880]):.2f}, "
      f"max={max(max_sensor[950:5880]):.2f}, mean={np.mean(max_sensor[950:5880]):.2f}")
