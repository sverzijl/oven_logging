"""Noise perturbation of 1759: add gaussian noise to T1..T8 and verify the
detector still produces 3 curves with starts within tolerance.
"""
import os, sys
REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import numpy as np
import pandas as pd
from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector, _SENSOR_COLUMNS
from tests.fixtures.curve_boundary_cases import load_real_case


def run_perturbations(sigma, trials=30, seed0=1000):
    df0 = load_real_case("1000BA3C_1759")
    det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)

    n_wrong = 0
    starts = []
    ends = []
    n_curves_list = []
    for t in range(trials):
        rng = np.random.default_rng(seed0 + t)
        df = df0.copy()
        for s in _SENSOR_COLUMNS:
            df[s] = df[s].to_numpy(dtype=float) + rng.normal(0.0, sigma, len(df))
        # Also add noise to the VCT/CoreTemperature so core-based branches see same noise
        if "VirtualCoreTemperature" in df.columns:
            df["VirtualCoreTemperature"] = df["VirtualCoreTemperature"].to_numpy(dtype=float) + rng.normal(0.0, sigma, len(df))
        if "CoreTemperature" in df.columns:
            df["CoreTemperature"] = df["CoreTemperature"].to_numpy(dtype=float) + rng.normal(0.0, sigma, len(df))

        curves = det.extract_curves(df)
        n = len(curves)
        n_curves_list.append(n)
        if n != 3:
            n_wrong += 1
        else:
            starts.append([c["start_idx"] for c in curves])
            ends.append([c["end_idx"] for c in curves])

    starts = np.array(starts) if starts else np.empty((0, 3), dtype=int)
    ends = np.array(ends) if ends else np.empty((0, 3), dtype=int)
    print(f"\n--- σ = {sigma} °C, trials={trials} ---")
    print(f"  n_wrong (curve count != 3): {n_wrong}/{trials}")
    if len(starts):
        for i in range(starts.shape[1]):
            print(f"  curve {i+1} starts: mean={starts[:,i].mean():.2f} std={starts[:,i].std():.2f} "
                  f"min={starts[:,i].min()} max={starts[:,i].max()}")
        for i in range(ends.shape[1]):
            print(f"  curve {i+1} ends:   mean={ends[:,i].mean():.2f} std={ends[:,i].std():.2f} "
                  f"min={ends[:,i].min()} max={ends[:,i].max()}")
    print(f"  curve-count distribution: {dict((c, n_curves_list.count(c)) for c in set(n_curves_list))}")

for sigma in [0.15, 0.5, 1.0]:
    run_perturbations(sigma, trials=30)
