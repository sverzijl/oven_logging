"""Detailed look at 100098DE post-cliff tail: trace skip and confirm no re-fire.
"""
import os, sys
REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import numpy as np
from src.data.curve_boundary_detector import _resolve_max_sensor_series, _SENSOR_COLUMNS
from src.data.column_helpers import resolve_core_temperature_series
from tests.fixtures.curve_boundary_cases import load_real_case

df = load_real_case("100098DE_1351")
core = resolve_core_temperature_series(df).to_numpy(dtype=float)
max_sensor = _resolve_max_sensor_series(df, core)

# Curve ends at 306; simulate _skip_probe_pull_tail from search_from=307
search_from = 307
n = len(core)
room = 35.0
confirm_n = 3

print(f"Starting skip from {search_from}, n={n}")
j = search_from
adv1 = 0
while j < n and float(max_sensor[j]) > room:
    j += 1
    adv1 += 1
print(f"after fast-forward through >{room}: j={j}, advanced {adv1} samples")

confirmed = 0
while j < n and confirmed < confirm_n:
    if float(max_sensor[j]) <= room:
        confirmed += 1; j += 1
    else:
        confirmed = 0; j += 1
print(f"after confirm: j={j}, max_sensor[j-1]={max_sensor[j-1]:.2f}")

skip_out = j
# From skip_out, does method 2b fire anywhere?
def method_2b(start):
    for k in range(start, n):
        if max_sensor[k] < 40:
            continue
        look = min(confirm_n - 1, n - 1 - k)
        ok = all(max_sensor[k + m] >= 40 for m in range(1, look + 1))
        if ok:
            return k
    return None

m2b = method_2b(skip_out)
print(f"method 2b from {skip_out}: {m2b}")
if m2b is not None:
    print(f"  max_sensor[{m2b}..{m2b+5}]: {[float(max_sensor[m2b+i]) for i in range(min(6, n-m2b))]}")
    # Check whether this candidate survives curve-end detection
else:
    print(f"  no further curve start found - good")

# Also inspect max_sensor trajectory over post-cliff region
print(f"\nmax_sensor samples 307..360 (post-cliff cascade):")
for i in range(307, min(361, n), 3):
    print(f"  idx={i}: max={max_sensor[i]:.2f} core={core[i]:.2f}")
