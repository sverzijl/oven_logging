"""Q introspection probe — for every CASE, report:
 - post-peak single-sample cliff location + magnitude
 - cliff candidate fires? end_idx? truncated?
 - pre-cliff plateau duration (s) using 2 °C tolerance
"""
from __future__ import annotations

import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from src.data.loader import ThermalProfileLoader  # noqa: E402
from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402
from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402


def find_first_cliff(temps: np.ndarray, start: int, thresh_c: float = 15.0) -> int | None:
    for j in range(start, len(temps) - 1):
        if float(temps[j]) - float(temps[j + 1]) >= thresh_c:
            return j
    return None


def pre_cliff_plateau_seconds(temps: np.ndarray, ts: np.ndarray, j: int, tol: float = 2.0) -> float:
    """Count consecutive samples ending at j within tol of running peak-so-far; express in seconds."""
    if j <= 0:
        return 0.0
    peak_so_far = float(np.max(temps[: j + 1]))
    run = 0
    for k in range(j, -1, -1):
        if peak_so_far - float(temps[k]) <= tol:
            run += 1
        else:
            break
    if run < 2:
        return 0.0
    return float(ts[j] - ts[j - run + 1])


def run_case(case):
    df = case["df"]
    if case.get("raises") is not None:
        return {"name": case["name"], "skipped": "raises"}
    try:
        temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    except Exception as e:
        return {"name": case["name"], "error": str(e)}
    ts = df["Timestamp"].to_numpy(dtype=float)
    peak_idx = int(np.argmax(temps))

    # Run detector
    loader = ThermalProfileLoader()
    loader.metadata = {}
    loader.data = df
    curves = loader._extract_all_baking_curves(df.copy())

    first_cliff = find_first_cliff(temps, peak_idx)
    plateau_s = pre_cliff_plateau_seconds(temps, ts, first_cliff) if first_cliff is not None else None

    return {
        "name": case["name"],
        "source": case["source"],
        "n_samples": len(df),
        "peak_idx": peak_idx,
        "peak_temp": round(float(temps[peak_idx]), 2),
        "first_post_peak_cliff_idx": first_cliff,
        "pre_cliff_plateau_s": round(plateau_s, 1) if plateau_s is not None else None,
        "n_curves_detected": len(curves),
        "curve0_end_idx": curves[0]["end_idx"] if curves else None,
        "curve0_truncated": curves[0]["truncated"] if curves else None,
        "expected_ends": case["expected_ends"],
    }


if __name__ == "__main__":
    rows = []
    for case in CASES:
        rows.append(run_case(case))
    fmt = "{:<50} {:<9} {:>6} {:>6} {:>7} {:>12} {:>6} {:>6} {:<6} {:<20}"
    print(fmt.format("name", "source", "nsmp", "peak", "Tpeak", "cliff_idx", "platS", "nc", "trunc", "end_idx (exp)"))
    for r in rows:
        if "error" in r or "skipped" in r:
            print(f"{r['name']:<50} {r.get('error') or r.get('skipped')}")
            continue
        exp = r["expected_ends"]
        print(fmt.format(
            r["name"][:50], r["source"], r["n_samples"], r["peak_idx"],
            r["peak_temp"],
            str(r["first_post_peak_cliff_idx"]),
            str(r["pre_cliff_plateau_s"]),
            r["n_curves_detected"],
            str(r["curve0_truncated"]),
            f"{r['curve0_end_idx']} ({exp})",
        ))
