"""Bake-3 physical interpretation: verify it's a real bake (rising VCT)
and not just a hot oven dwell.
"""
import os, sys
REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import numpy as np
from src.data.column_helpers import resolve_core_temperature_series
from src.data.curve_boundary_detector import _resolve_max_sensor_series, _SENSOR_COLUMNS
from tests.fixtures.curve_boundary_cases import load_real_case


df = load_real_case("1000BA3C_1759")
vct = resolve_core_temperature_series(df).to_numpy(dtype=float)
ts = df["Timestamp"].to_numpy(dtype=float)
dt = float(np.median(np.diff(ts)))
print(f"Median sample period dt = {dt:.3f} s")

b3_start, b3_end = 5888, 6185
dur = (ts[b3_end] - ts[b3_start]) / 60.0
print(f"Bake 3: start={b3_start}, end={b3_end}, duration={dur:.2f} min")
print(f"Bake 3: VCT start={vct[b3_start]:.2f}, peak={max(vct[b3_start:b3_end+1]):.2f}, "
      f"end={vct[b3_end]:.2f}")
print(f"Bake 3: VCT rise={max(vct[b3_start:b3_end+1]) - vct[b3_start]:.2f} °C over {dur:.1f} min")

# Rise shape: how long from start to first hit 80°C (full-bake indicator)?
core_80 = None
for j in range(b3_start, b3_end + 1):
    if vct[j] >= 80.0:
        core_80 = j
        break
if core_80 is not None:
    print(f"Bake 3: first VCT>=80 at idx {core_80}, "
          f"{(ts[core_80] - ts[b3_start])/60:.2f} min after start")

# Compare to bakes 1 and 2
for name, s, e in [("Bake 1", 13, 293), ("Bake 2", 651, 944), ("Bake 3", 5888, 6185)]:
    peak = max(vct[s:e+1])
    rise = peak - vct[s]
    dur_min = (ts[e] - ts[s]) / 60.0
    # Time from start to VCT>=80
    t80 = None
    for j in range(s, e+1):
        if vct[j] >= 80.0:
            t80 = j; break
    t80_min = (ts[t80] - ts[s]) / 60.0 if t80 else None
    print(f"  {name}: start_vct={vct[s]:.2f}, peak={peak:.2f}, rise={rise:.2f} °C, "
          f"duration={dur_min:.2f} min, t_to_80={t80_min}")
