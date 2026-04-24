"""Noise perturbation battery on the PWM lidded case: does the cliff still fire?"""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from config import constants  # noqa: E402
from src.data.curve_boundary_detector import CurveBoundaryDetector  # noqa: E402
from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402


def main():
    cfg = dict(constants.CURVE_DETECTION_CONFIG)
    df0 = next(c for c in CASES if c["name"] == "post_wonder_meal_lidded")["df"]
    target = 344
    for sigma in (0.1, 0.3, 0.5, 1.0, 2.0):
        hits = 0
        total = 60
        ends = []
        for seed in range(total):
            rng = np.random.default_rng(seed)
            d = df0.copy()
            noise = rng.normal(0.0, sigma, len(d))
            if "CoreTemperature" in d.columns:
                d["CoreTemperature"] = d["CoreTemperature"].to_numpy(dtype=float) + noise
            if "VirtualCoreTemperature" in d.columns:
                d["VirtualCoreTemperature"] = d["VirtualCoreTemperature"].to_numpy(dtype=float) + noise
            det = CurveBoundaryDetector(cfg)
            curves = det.extract_curves(d)
            if not curves:
                continue
            end = curves[0]["end_idx"]
            ends.append(end)
            if abs(end - target) <= 5:
                hits += 1
        print(f"PWM σ={sigma}: {hits}/{total} within ±5 of 344.  ends range [{min(ends) if ends else '-'}, {max(ends) if ends else '-'}]")


if __name__ == "__main__":
    main()
