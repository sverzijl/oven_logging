"""Perturbation battery:

1. Noise σ=0.1 °C on 1759 — does 3-curve structure hold?
2. Synthetic: two-cliff curve with second cliff inside post-skip window.
"""
from __future__ import annotations

import copy
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


det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)

# ---------- Noise test on 1759 ----------
print("=== Noise σ=0.1 °C on 1759 — 30 trials ===")
df_orig = load_real_case("1000BA3C_1759")
base = resolve_core_temperature_series(df_orig).to_numpy(dtype=float)
ts = df_orig["Timestamp"].to_numpy(dtype=float)
pred_state = df_orig["PredictionState"].to_numpy(copy=True)

rng = np.random.default_rng(20260424)
n_three = 0
n_other = 0
other_counts = []
for trial in range(30):
    noise = rng.normal(0.0, 0.1, size=len(base))
    df_n = df_orig.copy()
    df_n["VirtualCoreTemperature"] = base + noise
    df_n["CoreTemperature"] = df_n["VirtualCoreTemperature"]
    got = det.extract_curves(df_n)
    if len(got) == 3:
        n_three += 1
    else:
        n_other += 1
        other_counts.append(len(got))
print(f"  3-curve trials: {n_three}/30")
print(f"  non-3-curve trials: {n_other}/30, counts={other_counts}")

# Higher noise stress
for sigma in (0.05, 0.15, 0.3):
    n_three = 0
    wrong_counts = []
    for trial in range(30):
        noise = rng.normal(0.0, sigma, size=len(base))
        df_n = df_orig.copy()
        df_n["VirtualCoreTemperature"] = base + noise
        df_n["CoreTemperature"] = df_n["VirtualCoreTemperature"]
        got = det.extract_curves(df_n)
        if len(got) == 3:
            n_three += 1
        else:
            wrong_counts.append(len(got))
    print(f"  σ={sigma}: 3-curve {n_three}/30, other={wrong_counts}")

# ---------- Synthetic: curve with TWO cliffs (simulate probe pulled partway, reinserted, pulled again) ----------
print("\n=== Synthetic: curve with TWO cliffs ===")
# Construct: pre_ambient + rise + plateau_a + CLIFF1 + cold + rise2 + plateau_b + CLIFF2 + post_ambient
period = 5.0
n_pre = 10
ambient = 22.0
peak = 95.0

# bake 1
rise1 = np.linspace(ambient, peak, 40)
plat1 = np.full(10, peak)
# cliff1 drop from 95 to ~25 in one sample, then monotonic
cliff1 = np.array([25.0, 24.0, 23.5, 23.0, 22.8, 22.5, 22.3])
# cold interlude
cold = np.full(30, ambient)
# bake 2
rise2 = np.linspace(ambient, peak, 40)
plat2 = np.full(10, peak)
# cliff2
cliff2 = np.array([25.0, 24.0, 23.5, 23.0, 22.8, 22.5, 22.3])
post = np.full(10, ambient)

vct = np.concatenate([
    np.full(n_pre, ambient), rise1, plat1, cliff1, cold, rise2, plat2, cliff2, post,
])
n = len(vct)
ts2 = np.arange(n, dtype=float) * period
df2 = pd.DataFrame({"Timestamp": ts2, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
got = det.extract_curves(df2)
print(f"  expected: 2 curves")
print(f"  got: {len(got)} curves")
for c in got:
    print(f"    start={c['start_idx']} end={c['end_idx']} peak={c['max_temp']:.2f}")

# ---------- Check: cliff inside the skip window on a merged scenario ----------
# If a cliff fires BEFORE cooldown completes and a re-insertion happens inside
# the skip window, would skip eat the second curve's start?
print("\n=== Synthetic: cliff immediately followed by reinsertion (skip vs new-start race) ===")
# bake1 (short cold tail), then rise straight into bake 2 while still warm-ish
rise1 = np.linspace(ambient, peak, 40)
plat1 = np.full(10, peak)
cliff1 = np.array([25.0, 24.0, 23.5, 23.0, 22.8, 22.5, 22.3, 22.0])  # short cooldown
# immediately re-insert and re-heat (no long quiescent period)
rise_fast = np.linspace(22.0, peak, 30)
plat2 = np.full(10, peak)
decay = np.linspace(peak, ambient, 40)
vct = np.concatenate([
    np.full(n_pre, ambient), rise1, plat1, cliff1, rise_fast, plat2, decay,
])
n = len(vct)
ts3 = np.arange(n, dtype=float) * period
df3 = pd.DataFrame({"Timestamp": ts3, "VirtualCoreTemperature": vct, "CoreTemperature": vct})
got = det.extract_curves(df3)
print(f"  expected: 2 curves (cliff ends #1, immediate re-rise starts #2)")
print(f"  got: {len(got)} curves")
for c in got:
    print(f"    start={c['start_idx']} end={c['end_idx']} peak={c['max_temp']:.2f}")
