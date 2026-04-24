"""Inspect the quiescent region between bakes 2 and 3 in 1759 to see if any
sustained hot run exists that could trigger method 2b spuriously from some
intermediate search_from.
"""
import os, sys
REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import numpy as np
import pandas as pd
from src.data.curve_boundary_detector import _resolve_max_sensor_series, _SENSOR_COLUMNS
from src.data.column_helpers import resolve_core_temperature_series
from tests.fixtures.curve_boundary_cases import load_real_case


df = load_real_case("1000BA3C_1759")
core = resolve_core_temperature_series(df).to_numpy(dtype=float)
max_sensor = _resolve_max_sensor_series(df, core)

# Find where max_sensor > 40 in range 950..5880
hits = [(i, float(max_sensor[i])) for i in range(950, 5880) if max_sensor[i] > 40]
print(f"Samples 950..5879 where max_sensor > 40: count={len(hits)}")
for h in hits[:30]:
    print(f"  idx={h[0]} max={h[1]:.2f}")

# What's the absolute peak in this range and its index?
region = max_sensor[950:5880]
peak = np.argmax(region) + 950
print(f"\nPeak in 950..5879: idx={peak}, max_sensor={max_sensor[peak]:.2f}")
# What sensors contribute?
if all(c in df.columns for c in _SENSOR_COLUMNS):
    print(f"  T1..T8 at idx {peak}:")
    for s in _SENSOR_COLUMNS:
        print(f"    {s}: {df[s].iloc[peak]:.2f}")

# Verify: is this within the bake-2 cliff cooldown skip region (<=1001)?
print(f"\nSkip ended at 1001. idx {peak} within skip region (<=1001)? {peak <= 1001}")
