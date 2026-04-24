"""Compare old core-based skip vs new max-sensor-based skip for 100098DE.
Establish whether max-sensor change is strictly stronger defense."""
import os, sys
REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import numpy as np
from src.data.curve_boundary_detector import _resolve_max_sensor_series
from src.data.column_helpers import resolve_core_temperature_series
from tests.fixtures.curve_boundary_cases import load_real_case, load_wonder_white, load_post_wonder_meal

def simulate_skip(series, search_from, room_temp_max=35.0, confirm_n=3):
    n = len(series)
    j = search_from
    while j < n and float(series[j]) > room_temp_max:
        j += 1
    confirmed = 0
    while j < n and confirmed < confirm_n:
        if float(series[j]) <= room_temp_max:
            confirmed += 1; j += 1
        else:
            confirmed = 0; j += 1
    return j

def method_2b_on(series, start, n, threshold=40.0, confirm_n=3):
    for k in range(start, n):
        if series[k] < threshold:
            continue
        look = min(confirm_n - 1, n - 1 - k)
        ok = all(series[k + m] >= threshold for m in range(1, look + 1))
        if ok:
            return k
    return None

for name, df, end in [
    ("100098DE", load_real_case("100098DE_1351"), 306),
    ("BA3C_0946", load_real_case("1000BA3C_0946"), 293),
    ("BA3C_1759_bake1", load_real_case("1000BA3C_1759"), 293),
    ("BA3C_1759_bake2", load_real_case("1000BA3C_1759"), 944),
    ("WW", load_wonder_white(), 338),
    ("PWM", load_post_wonder_meal(), 344),
]:
    core = resolve_core_temperature_series(df).to_numpy(dtype=float)
    max_sensor = _resolve_max_sensor_series(df, core)
    n = len(core)
    old = simulate_skip(core, end + 1)
    new = simulate_skip(max_sensor, end + 1)
    # Now check method 2b after each — on max_sensor (current detector method 2b scans max_sensor)
    m2b_after_old = method_2b_on(max_sensor, old, n)
    m2b_after_new = method_2b_on(max_sensor, new, n)
    print(f"{name}: end={end}, old core-skip->{old}, new max-skip->{new}, "
          f"m2b_after_old={m2b_after_old}, m2b_after_new={m2b_after_new}")
