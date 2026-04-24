"""Synthetic: probe inserted warm (j=50 with drop 25->7), then warm up to a real bake."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import pandas as pd
from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector

detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)

# Case: probe is in air (25C), then abruptly dropped into dough (say, 7C cold
# storage); cliff at j=50 in the detector's view.  Then real bake rises to 95.
print("=== Case (a): warm probe insertion into cold dough at j=50 ===")
# 50 ambient samples at 25C
pre = [25.0] * 50
# Sudden drop to 7C (probe hit the cold dough)
# Instantaneous drop of 18C
drop_tail = [7.0, 8.0, 10.0, 13.0, 17.0]
# Rise to bake: 20 samples to 95
rise = list(np.linspace(17, 95, 40))
plateau = [95, 95, 95]
# Probe pull cliff
cliff_tail = [75, 55, 40, 32, 28, 25]
temps = np.array(pre + drop_tail + rise + plateau + cliff_tail, dtype=float)
n = len(temps)
ts = np.arange(n, dtype=float) * 5.0
df = pd.DataFrame({
    "Timestamp": ts,
    "VirtualCoreTemperature": temps,
    "PredictionState": ["Probe Not Inserted"]*3 + ["Cooking"]*(n-3),
})
curves = detector.extract_curves(df)
print(f"  n={n}")
print(f"  drop at j=49->50: {temps[49]:.2f} -> {temps[50]:.2f}")
print(f"  rise starts at j={len(pre)+len(drop_tail)}")
for c in curves:
    print(f"  start={c['start_idx']} end={c['end_idx']} max={c['max_temp']:.2f} trunc={c['truncated']}")

print("\n=== Case (b): double cliff - probe-pull at j=50 + real bake cliff at j=300 ===")
# Bake 1: 0..50 rises from 25 to 95, cliff at 50->51 (drop to 72)
rise1 = list(np.linspace(25, 95, 50))
cliff1_tail = [72, 55, 40, 35, 32, 30, 28, 27, 26, 25]
# Rest (pull out); 200 samples of ambient before reinsertion
pause = [25.0] * 50
# Bake 2: rises from 25 to 95, cliff at some later idx
rise2 = list(np.linspace(25, 95, 50))
cliff2_tail = [75, 60, 45, 35, 30, 26, 24]
temps = np.array(rise1 + cliff1_tail + pause + rise2 + cliff2_tail, dtype=float)
n = len(temps)
ts = np.arange(n, dtype=float) * 5.0
pred = ["Probe Not Inserted"]*3 + ["Cooking"]*(n-3)
df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": temps, "PredictionState": pred})
curves = detector.extract_curves(df)
print(f"  n={n}, cliff1 at j=49->50, cliff2 at j={50+len(cliff1_tail)+len(pause)+49}->{50+len(cliff1_tail)+len(pause)+50}")
for c in curves:
    print(f"  start={c['start_idx']} end={c['end_idx']} max={c['max_temp']:.2f} trunc={c['truncated']}")
