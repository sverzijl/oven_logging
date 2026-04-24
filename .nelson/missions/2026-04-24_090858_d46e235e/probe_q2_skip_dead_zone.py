"""Q2 — Does `_skip_probe_pull_tail` over-skip on 1759? Is there a dead zone?

Probe the exact trajectory on 1759 between bakes 1 and 2, and between bakes 2 and 3:
  - Find where skip stops (index and VCT value).
  - Find where the detector's cold-start would fire next.
  - Compare — the "dead zone" is samples between skip-stop and start-detect.
"""
from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _REPO)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from config.constants import CURVE_DETECTION_CONFIG  # noqa: E402
from src.data.curve_boundary_detector import CurveBoundaryDetector  # noqa: E402
from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402
from tests.fixtures.curve_boundary_cases import load_real_case  # noqa: E402


df = load_real_case("1000BA3C_1759")
det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
pred_state = df["PredictionState"].to_numpy(copy=True)

print(f"Total rows: {len(df)}")
print(f"bake_active_c={det._bake_active_c}  room_temp_max={det._room_temp_max}  confirm_n={det._confirm_n}")

curves = det.extract_curves(df)
print("\n=== Detected curves ===")
for c in curves:
    print(f"  start={c['start_idx']} end={c['end_idx']} peak={c['max_temp']:.2f}")

# ---------- Between bake 1 and bake 2 ----------
print("\n=== Between bake 1 (cliff at 293) and bake 2 (start 775 annotated) ===")
cliff_end_1 = 293
search_from = cliff_end_1 + 1
# first skip past >room_temp_max
skip1 = det._skip_probe_pull_tail(temps, search_from)
print(f"skip_from={search_from}  skip_to={skip1}  VCT[{skip1}]={temps[skip1]:.2f}")
# Now a cold-start scan from skip1 onwards:
next_start = det._detect_start(temps, pred_state, skip1)
print(f"cold-start scan from {skip1} → start_idx={next_start}  VCT[{next_start}]={temps[next_start]:.2f}")
# Dead zone?
print(f"dead zone = {next_start - skip1} samples (skip_stop..start_detect)")

# Also trace: what's the first index where VCT drops below room_temp_max after 294?
first_below = None
for j in range(294, len(temps)):
    if temps[j] <= 35.0:
        first_below = j
        break
print(f"first VCT<=35 after idx 294: idx={first_below}  VCT={temps[first_below]:.2f}")
# show a few samples around the skip-stop region
print("\nSample trajectory around skip region:")
start_trace = max(skip1 - 4, 0)
for j in range(start_trace, min(skip1 + 5, len(temps))):
    mark = " <-- skip_to" if j == skip1 else ""
    print(f"  idx={j}  VCT={temps[j]:.2f}{mark}")

print("\nSample trajectory around bake-2 start (775 annotated):")
for j in range(770, 785):
    mark = ""
    if j == 775:
        mark = " <-- annotated start"
    if j == 766:
        mark += " <-- original admiral estimate"
    print(f"  idx={j}  VCT={temps[j]:.2f}{mark}")

# ---------- Between bake 2 and bake 3 ----------
print("\n=== Between bake 2 (cliff at 944) and bake 3 (detector says 6032, annotation says 6022) ===")
cliff_end_2 = 944
search_from2 = cliff_end_2 + 1
skip2 = det._skip_probe_pull_tail(temps, search_from2)
print(f"skip_from={search_from2}  skip_to={skip2}  VCT[{skip2}]={temps[skip2]:.2f}")
next_start2 = det._detect_start(temps, pred_state, skip2)
print(f"cold-start scan from {skip2} → start_idx={next_start2}  VCT[{next_start2}]={temps[next_start2]:.2f}")
print(f"dead zone = {next_start2 - skip2} samples")
# Show trajectory around 6020-6035
print("\nSample trajectory around bake-3 start (6022 annotated, 6032 detector):")
for j in range(6015, 6040):
    mark = ""
    if j == 6022:
        mark = " <-- annotated start"
    if j == 6032:
        mark += " <-- detector start"
    print(f"  idx={j}  VCT={temps[j]:.2f}{mark}")
