"""Battery check #2: for each LIDDED case (where cliff CAN fire), verify whether
the aggregator picks cliff or plateau — and confirm they don't conflict.

For wonder white and lidded_bake_plateau_classic, the plateau should win.
For PWM and synthetic cliff, the cliff should win.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from config import constants  # noqa: E402
from src.data.curve_boundary_detector import CurveBoundaryDetector  # noqa: E402
from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402
from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402


def candidate_dump(det: CurveBoundaryDetector, df):
    """Call each candidate on the raw (whole-log) arrays."""
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    ts = df["Timestamp"].to_numpy(dtype=float)
    peak_idx = int(np.argmax(temps))
    peak_temp = float(temps[peak_idx])
    first_scan = peak_idx + det._post_peak_grace
    cool_window = det._long_cool_window_samples(ts)

    cands = {}
    cands["drop_rate"] = det._candidate_drop_rate(temps, ts, first_scan)
    cands["cool"] = det._candidate_cool_to_ambient(temps, first_scan, cool_window)
    cands["roomplateau"] = det._candidate_room_temp_plateau(temps, first_scan, cool_window)
    cands["dip_rerise"] = det._candidate_dip_with_rerise(temps, peak_idx, peak_temp)
    cands["corepeak"] = det._candidate_core_peak_plateau(temps, ts, peak_idx, first_scan)
    cands["cliff"] = det._candidate_probe_pull_cliff(temps, ts, peak_idx)
    return peak_idx, cands


def main():
    cfg = dict(constants.CURVE_DETECTION_CONFIG)
    det = CurveBoundaryDetector(cfg)
    for name in ["post_wonder_meal_lidded", "cliff_probe_pull_with_monotonic_cooldown",
                 "wonder_white_10k_lidded", "lidded_bake_plateau_classic",
                 "lidded_bake_plateau_truncated",
                 "real_100098DE_1351", "real_1000BA3C_0946", "real_1000BA3C_1759",
                 "noise_spike_midbake", "two_bakes_no_cool", "midbake_start"]:
        try:
            df = next(c for c in CASES if c["name"] == name)["df"]
            peak, cands = candidate_dump(det, df)
            cands_sorted = sorted(((k, v) for k, v in cands.items() if v is not None),
                                  key=lambda kv: kv[1])
            winner = cands_sorted[0] if cands_sorted else ("NONE", None)
            print(f"{name:<45} peak={peak:5}  winner={winner[0]:<12}@{winner[1]}   all={cands}")
        except Exception as e:
            print(f"{name} ERROR: {e}")


if __name__ == "__main__":
    main()
