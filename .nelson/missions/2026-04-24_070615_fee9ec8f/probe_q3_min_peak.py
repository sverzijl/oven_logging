"""Q3 — Is MIN_PEAK_TEMP=80C a defensible universal threshold for cliffs?

Investigate:
(a) Lowest post-peak temperature in any fixture (min of temps[j] where j is on
    the cool-down tail after peak, pre-cliff — to see if 80C filter would reject
    any real cliff).
(b) Suppose a legitimate bake peaks at exactly 80C (MIN_PEAK_TEMP boundary).
    Does the cliff detector still fire?
(c) Cold-finished product synthetic: bake peaks at 78C.  Does cliff fire?
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import pandas as pd
from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector
from tests.fixtures.curve_boundary_cases import CASES

detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)

print("=== (a) For each real-CSV fixture, find the cliff sample temp ===")
# A cliff fires at sample j if temps[j] >= MIN_PEAK_TEMP and temps[j+1] is
# 15 C below temps[j].  Scan for the last pre-cliff temp in each fixture.
from src.data.column_helpers import resolve_core_temperature_series

for case in CASES:
    if case.get("source") != "real":
        continue
    df = case["df"]
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    # Find all cliff candidates (single-sample drops >= 15C)
    for j in range(len(temps) - 1):
        drop = temps[j] - temps[j+1]
        if drop >= 15.0:
            print(f"  {case['name']:<30} j={j} temps[j]={temps[j]:.2f} drop={drop:.2f}")

print("\n=== (b) Synthetic: peak at exactly 80C, then 15C cliff ===")
# 20 pre-rise, plateau at 80, then cliff 80->65
rise = list(np.linspace(25, 80, 30))
plateau = [80] * 30  # 150s plateau to satisfy duration
cliff_tail = [60, 48, 40, 34, 30, 27, 25]
temps = np.array(rise + plateau + cliff_tail, dtype=float)
n = len(temps)
ts = np.arange(n, dtype=float) * 5.0
df = pd.DataFrame({
    "Timestamp": ts,
    "VirtualCoreTemperature": temps,
    "PredictionState": ["Probe Not Inserted"]*3 + ["Cooking"]*(n-3),
})
curves = detector.extract_curves(df)
print(f"  n={n}, peak at idx=59 (80C), cliff at j=59->60")
for c in curves:
    print(f"    end={c['end_idx']}, max={c['max_temp']:.2f}, trunc={c['truncated']}")

print("\n=== (c) Cold-finished: peak at 78C (below MIN_PEAK_TEMP) ===")
rise = list(np.linspace(25, 78, 30))
plateau = [78] * 30
cliff_tail = [58, 44, 35, 30, 27, 25, 24]
temps = np.array(rise + plateau + cliff_tail, dtype=float)
n = len(temps)
ts = np.arange(n, dtype=float) * 5.0
df = pd.DataFrame({
    "Timestamp": ts,
    "VirtualCoreTemperature": temps,
    "PredictionState": ["Probe Not Inserted"]*3 + ["Cooking"]*(n-3),
})
curves = detector.extract_curves(df)
print(f"  n={n}, peak at ~idx=59 (78C)")
print(f"  curves: {len(curves)}")
for c in curves:
    print(f"    end={c['end_idx']}, max={c['max_temp']:.2f}, trunc={c['truncated']}")

print("\n=== (d) Dragon's 'cascade' concern: cliff candidate called from below-80 sample ===")
# After the first cliff fires at 96.75 -> 76.70, does the cliff scan
# incorrectly register a SECOND cliff at the tail?
temps = np.array([96.75, 76.70, 60.70, 52.00, 47.55, 44.00, 41.15, 39.45, 37.60, 36.45,
                  35.20, 33.65, 32.35, 31.25, 30.40, 29.55, 28.60, 27.90, 27.15, 26.50], dtype=float)
ts = np.arange(len(temps), dtype=float) * 5.0
cliff = detector._candidate_probe_pull_cliff(temps, ts, 0)
print(f"  Direct cliff scan from idx=0 on BA3C-like tail: {cliff}")
# Now with min_peak_temp filter — the 96.75 sample qualifies
cliff = detector._candidate_probe_pull_cliff(temps, ts, 1)
print(f"  Direct cliff scan from idx=1 (skip peak): {cliff}")
# At idx=1, temps[1]=76.70 which is BELOW 80, so cascade blocked.
