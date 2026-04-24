"""Q3: If we relaxed the pre-peak-plateau guard, what would the cliff fire on?

For each real CSV, run the cliff candidate WITHOUT the plateau guard and see
where it fires.
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


def main():
    # Temporarily monkey-patch the cliff candidate to ignore the plateau guard.
    original = CurveBoundaryDetector._candidate_probe_pull_cliff

    def no_plateau_cliff(self, temps, timestamps, first_scan):
        n = len(temps)
        confirm_n = self._cliff_confirm_n
        if n < 2:
            return None
        for j in range(first_scan, n - confirm_n - 1):
            drop = float(temps[j]) - float(temps[j + 1])
            if drop < self._instant_drop_c:
                continue
            monotonic = True
            for k in range(1, confirm_n + 1):
                if float(temps[j + k + 1]) > float(temps[j + k]):
                    monotonic = False
                    break
            if not monotonic:
                continue
            return j
        return None

    CurveBoundaryDetector._candidate_probe_pull_cliff = no_plateau_cliff

    try:
        cfg = dict(constants.CURVE_DETECTION_CONFIG)
        for name in ["real_100098DE_1351", "real_1000BA3C_0946", "real_1000BA3C_1759"]:
            df = next(c for c in CASES if c["name"] == name)["df"]
            det = CurveBoundaryDetector(cfg)
            curves = det.extract_curves(df)
            exp = next(c for c in CASES if c["name"] == name)["expected_ends"]
            print(f"{name:<40} n_curves={len(curves)} end_idx={[c['end_idx'] for c in curves]}  (expected {exp})")
    finally:
        CurveBoundaryDetector._candidate_probe_pull_cliff = original


if __name__ == "__main__":
    main()
