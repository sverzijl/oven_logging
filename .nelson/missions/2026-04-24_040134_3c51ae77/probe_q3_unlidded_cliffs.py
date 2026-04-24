"""Q3: Do the unlidded CSVs contain post-peak cliff-style drops that could be
probe pulls?  Does the current ground-truth annotation treat them as part of
the curve (cool-to-ambient) or truncate them?

For each unlidded CSV, display the peak, the first ≥10 °C single-sample drop
post-peak, and the temperatures either side of the annotated expected_end.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402
from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402


for name in ("real_100098DE_1351", "real_1000BA3C_0946", "real_1000BA3C_1759"):
    df = next(c for c in CASES if c["name"] == name)["df"]
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    ts = df["Timestamp"].to_numpy(dtype=float)
    peak = int(np.argmax(temps))
    peak_temp = float(temps[peak])
    # Look at all ≥10 °C single-sample drops post-peak
    drops = []
    for j in range(peak, len(temps) - 1):
        d = float(temps[j]) - float(temps[j + 1])
        if d >= 10.0:
            drops.append((j, d, float(temps[j]), float(temps[j + 1])))

    exp = next(c for c in CASES if c["name"] == name)["expected_ends"]
    print(f"\n=== {name} peak={peak} Tpeak={peak_temp:.2f} expected_ends={exp} ===")
    print("  ≥10 °C single-sample post-peak drops:")
    for j, d, before, after in drops:
        # Is this followed by monotonic cooling for 5 samples?
        mono = True
        for k in range(1, 6):
            if j + k + 1 >= len(temps): break
            if temps[j + k + 1] > temps[j + k]:
                mono = False
                break
        print(f"    idx={j} ts={ts[j]:.0f}  {before:.2f} → {after:.2f}  drop={d:.2f} °C  mono5={mono}")

    # Post-probe-pull behavior, if any: what happens 30 samples after annotated end?
    last_exp = exp[-1]
    if last_exp + 30 < len(temps):
        print(f"  around expected_end={last_exp}: T[last_exp-3..last_exp+30] =")
        for k in range(max(0, last_exp - 3), min(len(temps), last_exp + 31), 3):
            print(f"    idx={k} ts={ts[k]:.0f} T={temps[k]:.2f}")
