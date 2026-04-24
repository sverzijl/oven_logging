"""Q2 — Correctness of peak_idx+1 scan start.

Test whether the scan start shift from `peak_idx` to `peak_idx+1` can cause
false negatives (missing genuine cliffs):

(a) Short-log case where peak_idx IS the final pre-cliff sample — does the
    grace-window fallback pick it up?  Simulate by running through the full
    detector and confirming truncated flag.
(b) Pathological synthetic: peak at j=10, cliff at j=10->11 (no intermediate).
(c) Very short bake that peaks and immediately gets probe-pulled.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import pandas as pd
from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector

def make_df(temps, dt=5.0):
    n = len(temps)
    ts = np.arange(n, dtype=float) * dt
    return pd.DataFrame({
        "Timestamp": ts,
        "VirtualCoreTemperature": temps,
        "PredictionState": ["Probe Not Inserted"]*3 + ["Cooking"]*(n-3),
    })

detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)

# Case A: peak is at j=peak_idx, cliff at peak_idx -> peak_idx+1, followed by
# monotonic decline to short tail.  Does detector find end?
# Build: 10 pre-heat rising to 95, cliff to 30, 6 more sub-ambient samples.
# Short tail forces fallback to trigger.
print("=== Case A: peak-then-cliff, short tail ===")
rise = list(np.linspace(25, 95, 20))
cliff_tail = [80, 65, 55, 45, 38, 32]  # starts at 80 (below peak) post-cliff
temps = np.array(rise + cliff_tail, dtype=float)
df = make_df(temps)
curves = detector.extract_curves(df)
print(f"  n={len(temps)}, peak expected at idx=19 (95C)")
print(f"  curves found: {len(curves)}")
if curves:
    c = curves[0]
    print(f"  end_idx={c['end_idx']}, truncated={c['truncated']}, max_temp={c['max_temp']:.2f}")
    # Expected: grace fallback catches j=19 (peak) since peak+1 scan skips it
    # but the top-level loop after main scan fails will re-run with peak_idx.
print()

# Case B: normal cliff: long bake, peak well before cliff, cliff picked up by main loop
print("=== Case B: normal bake, cliff long after peak ===")
rise = list(np.linspace(25, 95, 30))
plateau = [95 + 0.1*i for i in range(20)]  # mild rise to 96.9
cliff_tail = [75, 55, 45, 35, 28, 25]
temps = np.array(rise + plateau + cliff_tail, dtype=float)
df = make_df(temps)
curves = detector.extract_curves(df)
if curves:
    c = curves[0]
    print(f"  peak_expected~idx=49, actual_end={c['end_idx']}, truncated={c['truncated']}")
print()

# Case C: double cliff — probe pull at j=50, reinsert, real cliff at j=100
print("=== Case C: double cliff (synthetic 2-bake-1-curve) ===")
rise1 = list(np.linspace(25, 90, 20))
cliff1_tail = [70, 55, 45, 40, 38, 36, 35, 34, 33, 32]
# Reheat after probe reinsertion
rise2 = list(np.linspace(35, 96, 20))
cliff2_tail = [76, 60, 48, 38, 30, 25, 22]
temps = np.array(rise1 + cliff1_tail + rise2 + cliff2_tail, dtype=float)
df = make_df(temps)
curves = detector.extract_curves(df)
print(f"  cliff1 at j=19->20, cliff2 at j=49->50")
print(f"  n={len(temps)}, curves found: {len(curves)}")
for i, c in enumerate(curves):
    print(f"  curve{i}: end_idx={c['end_idx']}, max_temp={c['max_temp']:.2f}, truncated={c['truncated']}")
print()

# Case D: does peak_idx+1 scan miss a LEGITIMATE cliff at the running peak?
# Short bake that peaks EXACTLY one sample before probe-pull.  Without the
# grace fallback this would be a silent miss.
print("=== Case D: very short bake, cliff immediately after peak, log ends shortly ===")
rise = list(np.linspace(25, 85, 10))
peak = [90]  # single-sample peak
cliff_tail = [70, 55, 45, 38, 35, 32]
temps = np.array(rise + peak + cliff_tail, dtype=float)
df = make_df(temps)
curves = detector.extract_curves(df)
print(f"  peak at idx=10 (single sample, 90C), cliff at j=10->11")
for i, c in enumerate(curves):
    print(f"  end_idx={c['end_idx']}, truncated={c['truncated']}, max_temp={c['max_temp']:.2f}")
print()

# Case E: BA3C_0946 analogue — does peak+1 scan catch the cliff here?
print("=== Case E: load BA3C_0946 raw, run detector ===")
CSV = Path(__file__).resolve().parents[3] / "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
df = pd.read_csv(str(CSV), skiprows=10)
curves = detector.extract_curves(df)
for i, c in enumerate(curves):
    print(f"  curve{i}: start={c['start_idx']}, end={c['end_idx']}, max_temp={c['max_temp']:.2f}, truncated={c['truncated']}")
