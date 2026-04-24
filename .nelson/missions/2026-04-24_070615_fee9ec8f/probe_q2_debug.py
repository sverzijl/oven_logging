"""Diagnose Case A behavior."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import pandas as pd
from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector

dt = 5.0
rise = list(np.linspace(25, 95, 20))
cliff_tail = [80, 65, 55, 45, 38, 32]
temps = np.array(rise + cliff_tail, dtype=float)
print(f"temps[:5]={temps[:5]}")
print(f"temps[18:22]={temps[18:22]}")  # peak at 19 = 95
print(f"temps[19:26]={temps[19:26]}")
print(f"argmax={int(np.argmax(temps))} = {temps.argmax()}")

n = len(temps)
ts = np.arange(n, dtype=float) * dt
df = pd.DataFrame({
    "Timestamp": ts,
    "VirtualCoreTemperature": temps,
    "PredictionState": ["Probe Not Inserted"]*3 + ["Cooking"]*(n-3),
})
detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
curves = detector.extract_curves(df)
print(f"\nn={n}")
print(f"curves found: {len(curves)}")
for c in curves:
    print(f"  start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']}, trunc={c['truncated']}")

# Now inspect _detect_curve_end directly
end_idx, peak_idx, truncated, plateau_fired = detector._detect_curve_end(
    temps, ts, 0, cooking_continuous=False
)
print(f"\n_detect_curve_end: end={end_idx}, peak={peak_idx}, trunc={truncated}, plat={plateau_fired}")

# Manually try cliff candidate
cliff = detector._candidate_probe_pull_cliff(temps, ts, 0)
print(f"\ncliff candidate from idx=0: {cliff}")
cliff2 = detector._candidate_probe_pull_cliff(temps, ts, 19)
print(f"cliff candidate from peak_idx=19: {cliff2}")
cliff3 = detector._candidate_probe_pull_cliff(temps, ts, 20)
print(f"cliff candidate from peak_idx+1=20: {cliff3}")
