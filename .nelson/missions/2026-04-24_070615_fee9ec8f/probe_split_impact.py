"""What does the split actually produce on BA3C_1759 at sigma=0.05?"""
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

for case in CASES:
    if case["name"] == "real_1000BA3C_1759":
        df = case["df"].copy()
        orig = resolve_core_temperature_series(df).to_numpy(dtype=float).copy()
        col = "VirtualCoreTemperature"
        rng = np.random.default_rng(2026)
        # Find a split seed
        for trial in range(30):
            noisy = orig + rng.normal(0, 0.05, size=orig.shape)
            df[col] = noisy
            curves = detector.extract_curves(df)
            if len(curves) != 2:
                print(f"Trial {trial} at sigma=0.05: n_curves={len(curves)}")
                for c in curves:
                    print(f"  start={c['start_idx']} end={c['end_idx']} max={c['max_temp']:.2f} trunc={c['truncated']}")
                break
        # Reset and try sigma=0.15
        rng = np.random.default_rng(2026)
        print("\nsigma=0.15:")
        for trial in range(30):
            noisy = orig + rng.normal(0, 0.15, size=orig.shape)
            df[col] = noisy
            curves = detector.extract_curves(df)
            if len(curves) != 2:
                print(f"Trial {trial}: n_curves={len(curves)}")
                for c in curves:
                    print(f"  start={c['start_idx']} end={c['end_idx']} max={c['max_temp']:.2f} trunc={c['truncated']}")
                break
