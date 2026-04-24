"""Probe: run combined-rank classifier on every fixture case and report
winner + cool_contamination_detected + cool_available.

Any unexpected `cool_contamination_detected=True` on a case that should be
clean-unlidded is a red flag.
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _REPO_ROOT)

from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402
from src.data.thermodynamic_sensor_classifier import (  # noqa: E402
    identify_core_sensor_combined_rank,
)


def run():
    sensor_cols = [f"T{i}" for i in range(1, 9)]
    print(f"{'case':40s}  {'winner':6s}  {'expected':8s}  {'contam':6s}  {'cool_av':7s}  {'match':5s}")
    print("-" * 90)
    for case in CASES:
        name = case["name"]
        df = case.get("df")
        if df is None or len(df) == 0:
            print(f"{name:40s}  (no df)")
            continue
        # Only run on cases with T1..T8 present; otherwise skip
        have_all = all(s in df.columns for s in sensor_cols)
        if not have_all:
            # Try whatever sensor cols are there
            avail = [s for s in sensor_cols if s in df.columns]
            if len(avail) < 2:
                print(f"{name:40s}  (no T-cols)")
                continue
            cols = avail
        else:
            cols = sensor_cols
        try:
            winner, diag = identify_core_sensor_combined_rank(df, cols)
        except Exception as e:
            print(f"{name:40s}  ERROR: {type(e).__name__}: {e}")
            continue
        expected = case.get("expected_core_sensor", "-")
        contam = diag.get("cool_contamination_detected")
        cool_av = diag.get("cool_available")
        match = "YES" if winner == expected else ("-" if expected == "-" else "NO")
        print(f"{name:40s}  {str(winner):6s}  {str(expected):8s}  {str(contam):6s}  {str(cool_av):7s}  {match:5s}")


if __name__ == "__main__":
    run()
