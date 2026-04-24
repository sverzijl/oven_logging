"""Investigate the exact pre-cliff 'plateau' samples on PWM (and synthetic cliff)."""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402
from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402


for name in ("post_wonder_meal_lidded", "cliff_probe_pull_with_monotonic_cooldown",
             "real_1000BA3C_1759", "real_1000BA3C_0946"):
    df = next(c for c in CASES if c["name"] == name)["df"]
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    ts = df["Timestamp"].to_numpy(dtype=float)
    peak_idx = int(np.argmax(temps))
    peak_temp = float(temps[peak_idx])
    # Cliff location
    cliff = None
    for j in range(peak_idx, len(temps) - 1):
        if float(temps[j]) - float(temps[j + 1]) >= 15.0:
            cliff = j
            break
    if cliff is None:
        continue
    peak_so_far = float(np.max(temps[: cliff + 1]))
    run = 0
    for k in range(cliff, -1, -1):
        if peak_so_far - float(temps[k]) <= 2.0:
            run += 1
        else:
            break
    span_s = float(ts[cliff] - ts[cliff - run + 1]) if run >= 2 else 0.0
    print(f"\n=== {name}: peak={peak_idx} cliff={cliff} plateau_run={run} span_s={span_s:.1f} ===")
    j0 = max(0, cliff - run - 3)
    j1 = min(len(temps), cliff + 5)
    for k in range(j0, j1):
        marker = "P" if k == peak_idx else (" " if peak_so_far - temps[k] <= 2.0 else ".")
        marker2 = "CLIFF" if k == cliff else ""
        print(f"  idx={k:5} ts={ts[k]:8.1f} T={temps[k]:7.3f} delta_peak={peak_so_far - temps[k]:5.2f}  {marker} {marker2}")
