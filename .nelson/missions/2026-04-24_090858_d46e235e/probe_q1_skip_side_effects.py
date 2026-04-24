"""Q1 — Does `_skip_probe_pull_tail` fire spuriously on single-curve CSVs?

For each of 100098DE, BA3C_0946, PWM, wonder-white:
  - Run the detector.
  - Capture whether cliff fired, the value of `search_from` after skip,
    and whether any spurious second curve is produced.
  - Check whether the post-skip `search_from` sits in a region where
    `_detect_start` could fire spuriously (i.e., sustained VCT >= bake_active_c).
"""
from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _REPO)

import pandas as pd  # noqa: E402

from config.constants import CURVE_DETECTION_CONFIG  # noqa: E402
from src.data.curve_boundary_detector import CurveBoundaryDetector  # noqa: E402
from tests.fixtures.curve_boundary_cases import (  # noqa: E402
    load_real_case,
    load_wonder_white,
    load_post_wonder_meal,
)


def run(name: str, df: pd.DataFrame) -> None:
    det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
    curves = det.extract_curves(df)
    print(f"\n=== {name} ({len(df)} rows) ===")
    print(f"  n_curves = {len(curves)}")
    for c in curves:
        print(
            f"    start={c['start_idx']} end={c['end_idx']} "
            f"peak={c['max_temp']:.2f} truncated={c['truncated']}"
        )


for nm, key in [
    ("real_100098DE_1351", "100098DE_1351"),
    ("real_1000BA3C_0946", "1000BA3C_0946"),
]:
    run(nm, load_real_case(key))
run("post_wonder_meal_lidded", load_post_wonder_meal())
run("wonder_white_10k_lidded", load_wonder_white())

# Additional check — manually verify _skip_probe_pull_tail's effect on each cliff CSV.
# We want to see: after skip, does the remaining tail EVER cross bake_active_c again?
import numpy as np  # noqa: E402
from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402


def probe_skip(name: str, df: pd.DataFrame) -> None:
    det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    curves = det.extract_curves(df)
    if not curves:
        print(f"[{name}] no curves")
        return
    last = curves[-1]
    end_idx = last["end_idx"]
    # simulate skip from end_idx+1
    skipped = det._skip_probe_pull_tail(temps, end_idx + 1)
    tail = temps[skipped:]
    max_tail = float(np.max(tail)) if len(tail) else float("nan")
    # count consecutive samples >= 40 in tail
    crosses = np.sum(tail >= 40.0)
    print(
        f"[{name}] end={end_idx}  skip_from={end_idx+1}  skip_to={skipped}  "
        f"tail_len={len(tail)}  max_tail_temp={max_tail:.2f}  "
        f"tail_samples_gte40={crosses}"
    )


print("\n=== skip_probe_pull_tail behavior on each CSV's last-curve tail ===")
probe_skip("100098DE_1351", load_real_case("100098DE_1351"))
probe_skip("1000BA3C_0946", load_real_case("1000BA3C_0946"))
probe_skip("post_wonder_meal_lidded", load_post_wonder_meal())
probe_skip("wonder_white_10k_lidded", load_wonder_white())
