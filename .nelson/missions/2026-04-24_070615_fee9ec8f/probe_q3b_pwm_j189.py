"""Why does post_wonder_meal_lidded end at 344 and not at the cliff at j=189?"""
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

for case in CASES:
    if case["name"] == "post_wonder_meal_lidded":
        df = case["df"]
        temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
        ts = df["Timestamp"].to_numpy(dtype=float)
        print(f"n={len(df)}")
        print(f"\n--- Around j=185..210 (first 'cliff' at 189) ---")
        for j in range(185, 210):
            print(f"  j={j} t={ts[j]:.1f} core={temps[j]:.2f}")
        # Find running peak up through j=200
        pk_idx = int(np.argmax(temps[:200]))
        print(f"\nrunning peak up to j=200: idx={pk_idx} val={temps[pk_idx]:.2f}")
        # What is the running peak AT j=189?
        pk_at_189 = int(np.argmax(temps[:190]))
        print(f"running peak up to j=189: idx={pk_at_189} val={temps[pk_at_189]:.2f}")
        # Scan scan_from peak+1
        print(f"\ncliff scan from {pk_at_189+1}: {CurveBoundaryDetector(CURVE_DETECTION_CONFIG)._candidate_probe_pull_cliff(temps, ts, pk_at_189+1)}")
        # Full curve extract
        detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
        curves = detector.extract_curves(df)
        print(f"\nextract_curves:")
        for c in curves:
            print(f"  start={c['start_idx']}, end={c['end_idx']}, max={c['max_temp']:.2f}, trunc={c['truncated']}")
        break
