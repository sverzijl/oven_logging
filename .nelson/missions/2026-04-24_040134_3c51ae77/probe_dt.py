"""Probe the sample periods and compute pre-cliff plateau durations with correct dt."""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402
from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402


for case in CASES:
    if case.get("raises") is not None:
        continue
    df = case["df"]
    ts = df["Timestamp"].to_numpy(dtype=float)
    if len(ts) < 2:
        continue
    dts = np.diff(ts)
    median_dt = float(np.median(dts))
    mean_dt = float(np.mean(dts))
    min_dt = float(dts.min())
    max_dt = float(dts.max())
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    peak = int(np.argmax(temps))
    peak_temp = float(temps[peak])
    # find first cliff (≥15 deg drop single-sample) after peak
    cliff = None
    for j in range(peak, len(temps) - 1):
        if float(temps[j]) - float(temps[j + 1]) >= 15.0:
            cliff = j
            break
    plateau_s = 0.0
    if cliff is not None:
        peak_so_far = float(np.max(temps[: cliff + 1]))
        run = 0
        for k in range(cliff, -1, -1):
            if peak_so_far - float(temps[k]) <= 2.0:
                run += 1
            else:
                break
        if run >= 2:
            plateau_s = float(ts[cliff] - ts[cliff - run + 1])
    print(f"{case['name']:<45} dt_med={median_dt:6.2f} dt_mean={mean_dt:6.2f} min/max=[{min_dt:5.1f},{max_dt:6.1f}] cliff={cliff} plat={plateau_s:6.1f}s")
