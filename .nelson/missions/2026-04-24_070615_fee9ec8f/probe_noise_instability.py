"""Investigate noise-induced curve-count changes on BA3C_1759 and 1351."""
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
RNG = np.random.default_rng(42)

# First: BA3C_1759 under noise.  With noise the running peak's *location* can
# move around; does the first-cliff at j=293 ever fire?
for case in CASES:
    if case["name"] == "real_1000BA3C_1759":
        df = case["df"].copy()
        orig = resolve_core_temperature_series(df).to_numpy(dtype=float).copy()
        col = "VirtualCoreTemperature"
        print(f"BA3C_1759 baseline:")
        base = detector.extract_curves(df)
        for c in base:
            print(f"  start={c['start_idx']} end={c['end_idx']} max={c['max_temp']:.2f}")
        print(f"\n--- 3 noise trials with detail ---")
        for t in range(3):
            noisy = orig + RNG.normal(0, 1.0, size=orig.shape)
            df[col] = noisy
            curves = detector.extract_curves(df)
            print(f"trial {t}: n_curves={len(curves)}")
            for c in curves:
                print(f"  start={c['start_idx']} end={c['end_idx']} max={c['max_temp']:.2f} trunc={c['truncated']}")

    if case["name"] == "real_100098DE_1351":
        df = case["df"].copy()
        orig = resolve_core_temperature_series(df).to_numpy(dtype=float).copy()
        col = "VirtualCoreTemperature"
        print(f"\n\n1351 baseline:")
        base = detector.extract_curves(df)
        for c in base:
            print(f"  start={c['start_idx']} end={c['end_idx']} max={c['max_temp']:.2f}")
        print(f"\n--- 5 noise trials with detail ---")
        for t in range(5):
            noisy = orig + RNG.normal(0, 1.0, size=orig.shape)
            df[col] = noisy
            curves = detector.extract_curves(df)
            print(f"trial {t}: n_curves={len(curves)}")
            for c in curves:
                print(f"  start={c['start_idx']} end={c['end_idx']} max={c['max_temp']:.2f} trunc={c['truncated']}")

        # Where does max drift come from?
        # Print raw around 1351's cliff at idx 306 to understand
        temps = resolve_core_temperature_series(case["df"]).to_numpy(dtype=float)
        print(f"\n1351 cliff raw: j=305 {temps[305]:.2f}, j=306 {temps[306]:.2f}, j=307 {temps[307]:.2f}")
        print(f"n={len(df)}, running peak at end: {temps.max():.2f} at idx {int(temps.argmax())}")
