"""Introspection across all fixtures — n_curves + starts + ends + truncated."""
from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _REPO)

from config.constants import CURVE_DETECTION_CONFIG  # noqa: E402
from src.data.curve_boundary_detector import CurveBoundaryDetector  # noqa: E402
from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402


det = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
print(f"{'name':<40} {'n':<3} {'starts':<30} {'ends':<30} {'trunc':<6}")
print("-" * 120)
for c in CASES:
    name = c["name"]
    df = c["df"]
    exp_starts = c.get("expected_starts", [])
    exp_ends = c.get("expected_ends", [])
    exp_n = c.get("expected_n_curves", 0)
    raises = c.get("raises")
    if raises is not None:
        print(f"{name:<40} (raises {raises.__name__})")
        continue
    try:
        got = det.extract_curves(df)
    except Exception as e:
        print(f"{name:<40} EXC: {e}")
        continue
    starts = [g["start_idx"] for g in got]
    ends = [g["end_idx"] for g in got]
    truncs = [g["truncated"] for g in got]
    match = "OK" if (starts == exp_starts and ends == exp_ends and len(got) == exp_n) else "MISS"
    tol = c.get("tolerance")
    if match == "MISS" and tol is not None and len(got) == exp_n:
        # re-evaluate with tolerance
        s_ok = all(abs(a - b) <= tol for a, b in zip(starts, exp_starts))
        e_ok = all(abs(a - b) <= tol for a, b in zip(ends, exp_ends))
        if s_ok and e_ok:
            match = f"OK(tol={tol})"
    print(
        f"{name:<40} {len(got):<3} {str(starts):<30} {str(ends):<30} {str(truncs):<10} "
        f"exp_starts={exp_starts} exp_ends={exp_ends}  {match}"
    )
