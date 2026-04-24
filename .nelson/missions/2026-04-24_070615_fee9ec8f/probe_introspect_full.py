"""Independent introspection across all 18 fixture cases.

Verify Dragon's claimed matrix:
- real_100098DE_1351: 306, not truncated
- real_1000BA3C_0946: 293, not truncated
- real_1000BA3C_1759 [curve 0]: 944
- real_1000BA3C_1759 [curve 1]: 6185
- post_wonder_meal_lidded: 344
- wonder_white_10k_lidded: 338
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from config.constants import CURVE_DETECTION_CONFIG
from src.data.curve_boundary_detector import CurveBoundaryDetector
from tests.fixtures.curve_boundary_cases import CASES

detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)

print(f"{'case':<42} {'n':>6} {'exp_starts':<18} {'exp_ends':<18} {'act_starts':<18} {'act_ends':<18} {'trunc':<10} {'max_t':<8}")
print("-" * 150)
fails = []
for case in CASES:
    name = case["name"]
    df = case.get("df")
    if df is None:
        print(f"{name:<42} <no df>")
        continue
    exp_starts = case.get("expected_starts", [])
    exp_ends = case.get("expected_ends", [])
    tol = case.get("tolerance", 5)
    try:
        curves = detector.extract_curves(df)
    except Exception as e:
        print(f"{name:<42} EXCEPTION: {e}")
        continue
    act_starts = [c["start_idx"] for c in curves]
    act_ends = [c["end_idx"] for c in curves]
    act_trunc = [c["truncated"] for c in curves]
    act_max = [round(c["max_temp"], 2) for c in curves]
    print(
        f"{name:<42} {len(df):>6} "
        f"{str(exp_starts):<18} {str(exp_ends):<18} "
        f"{str(act_starts):<18} {str(act_ends):<18} "
        f"{str(act_trunc):<10} {str(act_max):<8}"
    )
    # Check within tolerance
    if len(act_ends) != len(exp_ends):
        fails.append(f"{name}: n_curves {len(act_ends)} != expected {len(exp_ends)}")
    for i in range(min(len(act_ends), len(exp_ends))):
        if abs(act_ends[i] - exp_ends[i]) > tol:
            fails.append(f"{name}[{i}]: end {act_ends[i]} vs expected {exp_ends[i]} (tol {tol})")

print()
print(f"Failures: {len(fails)}")
for f in fails:
    print(f"  {f}")
