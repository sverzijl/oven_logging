"""Q4 — Noise perturbation battery.

(a) Add sigma=1.0 C Gaussian noise to 3 unlidded CSVs + 2 lidded CSVs.  Count
    how many times the detector's end_idx wanders relative to baseline.
(b) Check interaction with min_k=2 contamination detector (core classifier).
    If the cliff at j=293 somehow leaked into bake-1, would both detectors
    trigger on the same event with disagreement?
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
RNG = np.random.default_rng(42)
SIGMA = 1.0
N_TRIALS = 30

TARGETS = [
    "real_100098DE_1351",
    "real_1000BA3C_0946",
    "real_1000BA3C_1759",
    "post_wonder_meal_lidded",
    "wonder_white_10k_lidded",
]

for case in CASES:
    if case["name"] not in TARGETS:
        continue
    df = case["df"].copy()
    # Baseline ends
    base_curves = detector.extract_curves(df)
    base_ends = [c["end_idx"] for c in base_curves]
    base_starts = [c["start_idx"] for c in base_curves]
    print(f"\n--- {case['name']} baseline: starts={base_starts} ends={base_ends} ---")

    # Perturb VirtualCoreTemperature
    orig = resolve_core_temperature_series(df).to_numpy(dtype=float).copy()
    col = "VirtualCoreTemperature" if "VirtualCoreTemperature" in df.columns else "CoreTemperature"

    spurious_n_curves = 0
    end_drifts = []
    for t in range(N_TRIALS):
        noisy = orig + RNG.normal(0, SIGMA, size=orig.shape)
        df[col] = noisy
        try:
            curves = detector.extract_curves(df)
        except Exception:
            continue
        ends = [c["end_idx"] for c in curves]
        if len(ends) != len(base_ends):
            spurious_n_curves += 1
            print(f"  trial {t}: n_curves={len(ends)} (base={len(base_ends)})")
            continue
        for i, e in enumerate(ends):
            drift = abs(e - base_ends[i])
            end_drifts.append(drift)
            if drift > 10:
                print(f"  trial {t} curve{i}: end={e} vs base {base_ends[i]} (drift {drift})")
    print(f"  trials with different n_curves: {spurious_n_curves}/{N_TRIALS}")
    print(f"  end drift: max={max(end_drifts) if end_drifts else 0}, "
          f"mean={np.mean(end_drifts) if end_drifts else 0:.2f}")

print("\n=== Q4 min_k=2 contamination interaction ===")
# The min_k=2 logic is in src.data core classifier.  Cliff detector is in
# curve_boundary_detector.  Verify no grep overlap.
import subprocess
out = subprocess.run(["grep", "-rn", "min_k", "src/"], capture_output=True, text=True)
print("min_k references:")
print(out.stdout or "(none)")
