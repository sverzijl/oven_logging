"""After single-curve CSVs (100098DE, BA3C_0946) hit their cliff, verify that
the outer loop does NOT find a spurious second curve via method 2b.
"""
import os, sys
REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector, _resolve_max_sensor_series
from src.data.column_helpers import resolve_core_temperature_series
from tests.fixtures.curve_boundary_cases import load_real_case, load_wonder_white, load_post_wonder_meal

det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)

for name, df in [
    ("100098DE_1351", load_real_case("100098DE_1351")),
    ("BA3C_0946", load_real_case("1000BA3C_0946")),
    ("wonder_white", load_wonder_white()),
    ("post_wonder_meal", load_post_wonder_meal()),
]:
    curves = det.extract_curves(df)
    print(f"{name}: n_curves={len(curves)}")
    for i, c in enumerate(curves):
        print(f"  curve {i+1}: start={c['start_idx']}, end={c['end_idx']}, "
              f"truncated={c['truncated']}, duration_min={c['duration']:.2f}")
    core = resolve_core_temperature_series(df).to_numpy(dtype=float)
    max_sensor = _resolve_max_sensor_series(df, core)
    n = len(core)
    # For a single-curve CSV, look at the post-curve tail
    if len(curves) == 1:
        c = curves[0]
        post = c["end_idx"] + 1
        print(f"  post-curve samples: {n - post} (from idx {post} to {n-1})")
        if post < n:
            # How many samples have max_sensor >= 40 in the tail?
            hot = sum(1 for j in range(post, n) if max_sensor[j] >= 40)
            print(f"    samples with max_sensor >= 40 in tail: {hot}")
