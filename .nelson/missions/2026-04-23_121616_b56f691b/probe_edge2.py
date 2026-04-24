"""Follow-up edge probes: confirm plateau behaviour on 1.9 and 10.1 rise60s thresholds."""
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


def get_candidate(df, peak_idx):
    """Get what plateau candidate returns independently."""
    det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
    from src.data.column_helpers import resolve_core_temperature_series
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    ts = df["Timestamp"].to_numpy(dtype=float)
    return det._candidate_core_peak_plateau(temps, ts, peak_idx, peak_idx + det._post_peak_grace)


# Build the 1.9 rise case properly — plateau onset EXPECTED to be rejected by guard
period = 5.0
slow_rise = np.linspace(40.0, 96.1, 500)  # 500 samples
fast_end = np.linspace(96.1, 98.0, 12)    # rise60s ~= 1.9
plateau = np.full(60, 98.0)                # stay at 98 for 300s
decline = np.linspace(98.0, 40.0, 100)
post = np.full(50, 22.0)
vct = np.concatenate([slow_rise, fast_end, plateau, decline, post])
ts = np.arange(len(vct), dtype=float) * period
df_19 = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
peak_idx = int(np.argmax(vct))
rise60 = vct[peak_idx] - vct[peak_idx - 12]
print(f"1.9 case: peak_idx={peak_idx}, rise60s={rise60:.3f}")
cand = get_candidate(df_19, peak_idx)
print(f"  plateau candidate returns: {cand} (None = guard rejected, as expected)")
curves = _run(df_19)
print(f"  detector end_idx={curves[0]['end_idx']}, truncated={curves[0].get('truncated')}")

# 10.1 case
slow_rise = np.linspace(40.0, 87.9, 400)
fast_end = np.linspace(87.9, 98.0, 12)
plateau_full = np.full(60, 98.0)
decline = np.linspace(98.0, 40.0, 100)
post = np.full(50, 22.0)
vct = np.concatenate([slow_rise, fast_end, plateau_full, decline, post])
ts = np.arange(len(vct), dtype=float) * period
df_101 = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
peak_idx = int(np.argmax(vct))
rise60 = vct[peak_idx] - vct[peak_idx - 12]
print(f"\n10.1 case: peak_idx={peak_idx}, rise60s={rise60:.3f}")
cand = get_candidate(df_101, peak_idx)
print(f"  plateau candidate returns: {cand} (None = guard rejected, as expected)")
curves = _run(df_101)
print(f"  detector end_idx={curves[0]['end_idx']}, truncated={curves[0].get('truncated')}")

# Now the CRITICAL case: slow-rise unlidded with 20s pause and rise60s in guard window
# Investigate WHY plateau didn't fire when it should have been eligible
rise = np.linspace(22.0, 95.0, 150)
pause = np.full(4, 95.0)
sharp_fall = np.linspace(95.0, 22.0, 40)
post = np.full(30, 22.0)
vct = np.concatenate([rise, pause, sharp_fall, post])
ts = np.arange(len(vct), dtype=float) * 5.0
df_s = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
peak_idx = int(np.argmax(vct))
rise60 = vct[peak_idx] - vct[peak_idx - 12]
print(f"\nSlow-rise-unlidded 20s pause: peak_idx={peak_idx}, rise60s={rise60:.3f}")
cand = get_candidate(df_s, peak_idx)
print(f"  plateau candidate returns: {cand}")
# WHY? The plateau candidate requires 4 samples (20s) of rate < 0.01 C/s. At peak the rate over 30s window...
# window_n = 30/5 = 6 samples. rate over 6-sample window at peak: need to check.
# Pause is only 4 samples at peak (idx 150..153); by idx 154 temp is already falling fast.
# At idx 150 (start of pause): rate over window of 6 = (95 - vct[144])/30s.
#   vct[144] = 22 + (95-22)*144/149 = ~92.57; rate = (95-92.57)/30 = 0.081 °C/s (ABOVE 0.01 threshold)
# So window rate stays > 0.01 at the pause onset. Plateau can't fire yet.
# By idx 151 (still in pause): window covers idx 145..151. vct[145]=~93.06, still rising. rate=0.065.
# By idx 152: covers 146..152. vct[146]=~93.56, still rising. rate=0.048.
# By idx 153 (last pause sample): covers 147..153. vct[147]=~94.05. rate=0.032.
# By idx 154 (first fall sample): temp=93.175. rate=(93.175-94.55)/30=-0.046. Rate too high (abs).
# So the 30s rate window NEVER stays under 0.01 for 4 consecutive samples on this curve.
# That's why plateau didn't fire. The 30s window is a SECOND defense.
print(f"  Analysis: The 30s rate window means rate-of-rise BEFORE peak still shows >0.01 C/s")
print(f"  The plateau guard has 2 layers: (a) rise60s in 2-10, (b) rate over 30s window <0.01")
print(f"  Both must hold for 4 consecutive samples (20s).")
print(f"  On slow-rise unlidded with 20s pause, (b) doesn't hold through the short pause.")

# But what if the pause is longer? 60s pause on a slow-rising unlidded bake?
rise = np.linspace(22.0, 95.0, 150)
pause = np.full(12, 95.0)   # 60s pause — 2x confirm_n and includes full 30s window
sharp_fall = np.linspace(95.0, 22.0, 40)
post = np.full(30, 22.0)
vct = np.concatenate([rise, pause, sharp_fall, post])
ts = np.arange(len(vct), dtype=float) * 5.0
df_60 = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
peak_idx = int(np.argmax(vct))
rise60 = vct[peak_idx] - vct[peak_idx - 12]
print(f"\nSlow-rise-unlidded 60s pause: peak_idx={peak_idx}, rise60s={rise60:.3f}")
cand = get_candidate(df_60, peak_idx)
print(f"  plateau candidate returns: {cand}")
curves = _run(df_60)
print(f"  detector end_idx={curves[0]['end_idx']}")
print(f"  If end ~idx 150: plateau FIRED spuriously on unlidded with a 60s pause.")
