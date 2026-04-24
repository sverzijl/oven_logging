"""Q1 noise battery: add σ=1.0 °C per-sample gaussian to the core column and
check for spurious cliff firing on the 3 unlidded CSVs.

Also sweep σ over {0.3, 1.0, 2.0} and count "cliff FIRED spuriously" events
(end_idx < expected_end − 10).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from config import constants  # noqa: E402
from src.data.curve_boundary_detector import CurveBoundaryDetector  # noqa: E402
from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402
from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402


def run_once(df: pd.DataFrame):
    cfg = dict(constants.CURVE_DETECTION_CONFIG)
    det = CurveBoundaryDetector(cfg)
    return det.extract_curves(df)


def perturb(df: pd.DataFrame, sigma: float, rng: np.random.Generator) -> pd.DataFrame:
    d = df.copy()
    noise = rng.normal(0.0, sigma, len(d))
    if "CoreTemperature" in d.columns:
        d["CoreTemperature"] = d["CoreTemperature"].to_numpy(dtype=float) + noise
    if "VirtualCoreTemperature" in d.columns:
        d["VirtualCoreTemperature"] = d["VirtualCoreTemperature"].to_numpy(dtype=float) + noise
    return d


def main():
    unlidded = {
        "real_100098DE_1351": 329,
        "real_1000BA3C_0946": 299,
        "real_1000BA3C_1759_bake1": 955,  # multi-curve, bake 1
    }
    for sigma in (0.3, 1.0, 2.0):
        print(f"\n=== σ={sigma} °C noise, 60 seeds ===")
        for name, exp_end in unlidded.items():
            case_name = "real_1000BA3C_1759" if name.endswith("_bake1") else name
            df = next(c for c in CASES if c["name"] == case_name)["df"]
            spur = 0
            runs = 60
            end_values = []
            for seed in range(runs):
                rng = np.random.default_rng(seed)
                pert = perturb(df, sigma, rng)
                curves = run_once(pert)
                if not curves:
                    spur += 0
                    continue
                c0 = curves[0]
                end_values.append(c0["end_idx"])
                # cliff fires spuriously if the curve ends < expected_end - 15 samples
                if c0["end_idx"] < exp_end - 15:
                    spur += 1
            if end_values:
                min_end = min(end_values)
                max_end = max(end_values)
                print(f"  {name:<40} spur={spur}/{runs}  end∈[{min_end},{max_end}]  (exp ~{exp_end})")
            else:
                print(f"  {name:<40} NO CURVES detected in all runs")


if __name__ == "__main__":
    main()
