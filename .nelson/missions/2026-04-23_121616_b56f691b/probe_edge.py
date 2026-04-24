"""Edge case probes: focus on perturbations near the rise-magnitude threshold and flaky pre-peak."""
import os
import sys
import numpy as np
import pandas as pd

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _REPO)

from src.data.loader import ThermalProfileLoader
from src.data.curve_boundary_detector import CurveBoundaryDetector
from config.constants import CURVE_DETECTION_CONFIG
from tests.fixtures.curve_boundary_cases import CASES


def _run(df):
    loader = ThermalProfileLoader()
    loader.metadata = {}
    loader.data = df
    return loader._extract_all_baking_curves(df.copy())


print("=" * 80)
print("EDGE 1: Rise-magnitude boundary - what about 1.9 C? 10.1 C?")
print("=" * 80)
# Build a lidded bake where rise60s is exactly 1.9 (just below) or 10.1 (just above)
period = 5.0
# Target rise60s = 1.9. peak=98. T(peak - 60s) should be 96.1.
# Build: slow ramp to 96.1 over (say 500s), then rise to 98 in 60s, then plateau
# Slow enough that we pass >40 for duration. Simpler: start at 40, ramp slowly, hit 96.1, then rise to 98 in 60s.
slow_rise = np.linspace(40.0, 96.1, 500)  # 500 samples at 5s = 2500s
fast_end = np.linspace(96.1, 98.0, 12)    # 12 samples = 60s
plateau = np.full(60, 98.0)                # stay at 98 for 300s
decline = np.linspace(98.0, 40.0, 100)
post = np.full(50, 22.0)
vct = np.concatenate([slow_rise, fast_end, plateau, decline, post])
ts = np.arange(len(vct), dtype=float) * period
df_19 = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
# Expected: rise60s ~1.9 → guard should REJECT plateau, falls through to cool_to_ambient
curves = _run(df_19)
print(f"  rise60s~1.9 case: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']:.1f}, truncated={c.get('truncated')}")
print(f"  Peak at {500+12-1}=511, plateau onset 511, decline starts 572.")

# Now try rise60s = 10.1 (just above upper)
# T(peak-60s) should be 87.9. Ramp from ambient to 87.9 over longer time, then 87.9→98 in 60s
slow_rise = np.linspace(40.0, 87.9, 400)
fast_end = np.linspace(87.9, 98.0, 12)    # rise60s ~= 10.1
plateau = np.full(60, 98.0)
decline = np.linspace(98.0, 40.0, 100)
post = np.full(50, 22.0)
vct = np.concatenate([slow_rise, fast_end, plateau, decline, post])
ts = np.arange(len(vct), dtype=float) * period
df_101 = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
curves = _run(df_101)
print(f"  rise60s~10.1 case: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']:.1f}, truncated={c.get('truncated')}")
print(f"  Peak at 411. If plateau fires near 411, the 10-C ceiling is too lenient.")

print()
print("=" * 80)
print("EDGE 2: Unlidded bake with brief 20s pause at peak (does it fire spuriously?)")
print("=" * 80)
# Classic unlidded bake but with exactly 20s pause at peak before sharp decline
period = 5.0
rise = np.linspace(22.0, 95.0, 60)   # 60 samples = 300s (typical bake rise)
pause = np.full(4, 95.0)             # 4 samples = 20s (exactly plateau_confirm_s)
sharp_fall = np.linspace(95.0, 22.0, 40)
post = np.full(30, 22.0)
vct = np.concatenate([rise, pause, sharp_fall, post])
ts = np.arange(len(vct), dtype=float) * period
df_p = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
# Rise60s: peak is at idx 59+3=62 (last 95 before fall). 60s = 12 samples earlier → idx 50.
# temp[50] should be around (95-22)*50/59 + 22 = 83.8. rise60s = 11.2. Should REJECT guard.
curves = _run(df_p)
print(f"  20s pause unlidded: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']:.1f}, truncated={c.get('truncated')}")

# What about a slower-rising unlidded? Some loaves might rise more slowly
rise = np.linspace(22.0, 95.0, 150)  # slower rise: 750s
pause = np.full(4, 95.0)
sharp_fall = np.linspace(95.0, 22.0, 40)
post = np.full(30, 22.0)
vct = np.concatenate([rise, pause, sharp_fall, post])
ts = np.arange(len(vct), dtype=float) * period
df_ps = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
# Rise60s: peak at idx 152. 12 samples earlier = idx 140. temp[140] = rise[140] = 22 + (95-22)*140/149 = ~91.
# rise60s = 95 - 91 = ~4. THIS IS IN THE 2-10 WINDOW!
curves = _run(df_ps)
print(f"  slow-rise unlidded with 20s pause: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']:.1f}, truncated={c.get('truncated')}")
print(f"  DANGER: if end<=160 (plateau onset), plateau fires spuriously on slow-rising unlidded bake.")

print()
print("=" * 80)
print("EDGE 3: Compute rise60s and peak idx for the slow-rise unlidded case")
print("=" * 80)
rise = np.linspace(22.0, 95.0, 150)
pause = np.full(4, 95.0)
sharp_fall = np.linspace(95.0, 22.0, 40)
post = np.full(30, 22.0)
vct = np.concatenate([rise, pause, sharp_fall, post])
peak_idx = int(np.argmax(vct))
rise60 = vct[peak_idx] - vct[peak_idx - 12]
print(f"  peak_idx={peak_idx}, peak_temp={vct[peak_idx]:.2f}, rise60s={rise60:.3f}")

# Scan: bracket rise duration where rise60s transitions OUT of the 2-10 window
for n_rise_samples in [60, 80, 100, 120, 140, 160, 180, 200, 300]:
    r = np.linspace(22.0, 95.0, n_rise_samples)
    pk = n_rise_samples - 1
    if pk >= 12:
        rise60 = r[pk] - r[pk - 12]
        print(f"  n_rise={n_rise_samples} ({n_rise_samples*5}s total): rise60s={rise60:.2f}, guard_passes={2.0 <= rise60 <= 10.0}")

print()
print("=" * 80)
print("EDGE 4: what about a 30s pause instead of 20s? Real unlidded may not pause even 20s.")
print("=" * 80)
# Same slow rise but 30s pause (6 samples at 5s)
rise = np.linspace(22.0, 95.0, 150)
pause30 = np.full(6, 95.0)
sharp_fall = np.linspace(95.0, 22.0, 40)
post = np.full(30, 22.0)
vct = np.concatenate([rise, pause30, sharp_fall, post])
ts = np.arange(len(vct), dtype=float) * 5.0
df_30 = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
curves = _run(df_30)
print(f"  slow-rise + 30s pause unlidded: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']:.1f}, truncated={c.get('truncated')}")
print(f"  Peak ~idx 152. If end ~152-155 → plateau fires on unlidded-slow bake. That's a false positive.")

print()
print("=" * 80)
print("EDGE 5: Verify _skip_plateau_tail doesn't eat a second genuine bake")
print("=" * 80)
# Multi-curve: first is lidded (ends at plateau, then tail cools slowly over many samples),
# immediately after cooling below 40, a new bake starts very fast.
period = 5.0
rise1 = np.linspace(22.0, 98.0, 100)
plateau1 = np.full(30, 98.0)           # ends idx 129
gentle1 = np.linspace(98.0, 40.0, 50)  # cooling ends idx 179
# The _skip_plateau_tail will advance until temp<40 for confirm_n (3) samples
subbk = np.linspace(40.0, 35.0, 3)     # idx 180..182 get below 40
# Second bake: immediate rise
rise2 = np.linspace(35.0, 95.0, 80)    # 183..262
fall2 = np.linspace(95.0, 22.0, 40)
post = np.full(30, 22.0)
vct = np.concatenate([rise1, plateau1, gentle1, subbk, rise2, fall2, post])
ts = np.arange(len(vct), dtype=float) * period
df_s = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
curves = _run(df_s)
print(f"  lidded + immediate 2nd bake: n_curves={len(curves)}")
for c in curves:
    print(f"    start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']:.1f}")
print(f"  Expected: 2 curves; bake1 at ~100, bake2 starts ~183.")
