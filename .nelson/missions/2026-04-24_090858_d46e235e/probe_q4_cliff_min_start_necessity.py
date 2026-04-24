"""Q4 — Is CLIFF_MIN_START_TEMP_C=80 still necessary after peak_idx+1 removal?

Test:
  1. Artificially set CLIFF_MIN_START_TEMP_C=0 (disable the guard).
  2. Run detector over all real CSVs + synthetics.
  3. Check whether any case's curves shift — i.e., does the cliff spuriously
     fire during post-cliff cooldown cascade where VCT has already dropped?

Also probe the cliff firing pattern on 1759 at idx 294 onwards — the cooldown
cascade from 74 → 22 has multiple sharp drops that might look cliff-like.
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
from tests.fixtures.curve_boundary_cases import (  # noqa: E402
    load_real_case,
    load_wonder_white,
    load_post_wonder_meal,
    CASES,
)


fixtures = [
    ("real_100098DE_1351", load_real_case("100098DE_1351")),
    ("real_1000BA3C_0946", load_real_case("1000BA3C_0946")),
    ("real_1000BA3C_1759", load_real_case("1000BA3C_1759")),
    ("post_wonder_meal_lidded", load_post_wonder_meal()),
    ("wonder_white_10k_lidded", load_wonder_white()),
]

cfg_on = copy.deepcopy(CURVE_DETECTION_CONFIG)
cfg_off = copy.deepcopy(CURVE_DETECTION_CONFIG)
cfg_off["CLIFF_MIN_START_TEMP_C"] = 0.0  # disable the guard

print("Comparing detector output with CLIFF_MIN_START_TEMP_C=80 vs CLIFF_MIN_START_TEMP_C=0\n")
for name, df in fixtures:
    d_on = CurveBoundaryDetector(cfg_on)
    d_off = CurveBoundaryDetector(cfg_off)
    c_on = d_on.extract_curves(df)
    c_off = d_off.extract_curves(df)
    on_summary = [(c["start_idx"], c["end_idx"]) for c in c_on]
    off_summary = [(c["start_idx"], c["end_idx"]) for c in c_off]
    diff_mark = "  (DIFFERS)" if on_summary != off_summary else ""
    print(f"{name}{diff_mark}")
    print(f"  guard=ON  (80 °C): {on_summary}")
    print(f"  guard=OFF (0  °C): {off_summary}")

# Now probe 1759's post-cliff cascade at idx 293 onwards — any spurious cliff fires?
print("\n\n=== Cascade after bake-1 cliff (1759 idx 293+) ===")
df1759 = load_real_case("1000BA3C_1759")
t = resolve_core_temperature_series(df1759).to_numpy(dtype=float)
for j in range(290, 315):
    print(f"  idx={j}  VCT={t[j]:.2f}  drop={t[j]-t[j+1] if j+1 < len(t) else float('nan'):.2f}")

# Probe scanning cliff candidate from idx 294 with guard OFF
from src.data.curve_boundary_detector import CurveBoundaryDetector as D  # noqa: E402
det_off = D(cfg_off)
ts = df1759["Timestamp"].to_numpy(dtype=float)
j_off = det_off._candidate_probe_pull_cliff(t[:400], ts[:400], 294)
print(f"\nCliff candidate (guard=OFF) scanning from 294 (within first cascade): returns {j_off}")
det_on = D(cfg_on)
j_on = det_on._candidate_probe_pull_cliff(t[:400], ts[:400], 294)
print(f"Cliff candidate (guard=ON 80 °C) scanning from 294: returns {j_on}")
