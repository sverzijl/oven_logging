"""Sweep sigma in [0.05, 0.15, 0.3, 0.5, 1.0] on 5 real CSVs.

Check whether noise causes curve-count inflation vs baseline.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
import pandas as pd
from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector
from src.data.column_helpers import resolve_core_temperature_series
from tests.fixtures.curve_boundary_cases import CASES

detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)

TARGETS = [
    "real_100098DE_1351",
    "real_1000BA3C_0946",
    "real_1000BA3C_1759",
    "post_wonder_meal_lidded",
    "wonder_white_10k_lidded",
]

SIGMAS = [0.05, 0.15, 0.3, 0.5, 1.0]
N_TRIALS = 30

print(f"{'case':<30} {'sigma':>6} {'split_rate':>10} {'end_drift_max':>14}")
for case in CASES:
    if case["name"] not in TARGETS:
        continue
    df = case["df"].copy()
    base = detector.extract_curves(df)
    base_ends = [c["end_idx"] for c in base]
    base_nc = len(base)
    col = "VirtualCoreTemperature" if "VirtualCoreTemperature" in df.columns else "CoreTemperature"
    orig = resolve_core_temperature_series(df).to_numpy(dtype=float).copy()

    for sigma in SIGMAS:
        rng = np.random.default_rng(2026)
        splits = 0
        max_drift = 0
        for t in range(N_TRIALS):
            noisy = orig + rng.normal(0, sigma, size=orig.shape)
            df[col] = noisy
            try:
                curves = detector.extract_curves(df)
            except Exception:
                continue
            if len(curves) != base_nc:
                splits += 1
                continue
            for i, c in enumerate(curves):
                d = abs(c["end_idx"] - base_ends[i])
                if d > max_drift:
                    max_drift = d
        print(f"{case['name']:<30} {sigma:>6.2f} {splits}/{N_TRIALS:<6} {max_drift:>14}")
