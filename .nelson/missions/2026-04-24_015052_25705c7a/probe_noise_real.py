"""Probe: noise-injection false-positive rate on the 3 real unlidded CSVs.

Inject gaussian noise σ=1.0 °C on each sensor column, 100 seeds per CSV. Count
how many seeds flip `cool_contamination_detected` from the baseline False → True.

If any CSV exceeds a 5% flip rate, that's a REVISE-worthy finding: Vanguard's
any-sensor-per-sample semantics have lowered the false-positive floor on clean
real cooldowns.

BA3C_1759 is the most important guardrail: its slow, clean cooldown is the
reference case for "don't trigger contamination".
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _REPO_ROOT)

from src.data.thermodynamic_sensor_classifier import (  # noqa: E402
    identify_core_sensor_combined_rank,
)


def load_curve_for_csv(csv_path: str) -> pd.DataFrame:
    """Mirror tests/fixtures/curve_boundary_cases.load_real_case — read raw CSV,
    drop Unnamed cols and NaN VirtualCoreTemperature rows.
    """
    df = pd.read_csv(csv_path, skiprows=10)
    unnamed = [c for c in df.columns if c.startswith("Unnamed:")]
    if unnamed:
        df = df.drop(columns=unnamed)
    if "VirtualCoreTemperature" in df.columns and "CoreTemperature" not in df.columns:
        df["CoreTemperature"] = df["VirtualCoreTemperature"]
    df = df.dropna(subset=["VirtualCoreTemperature"]).reset_index(drop=True)
    return df


def baseline_contamination(df: pd.DataFrame, sensor_cols: list[str]) -> dict:
    winner, diag = identify_core_sensor_combined_rank(df, sensor_cols)
    return {
        "winner": winner,
        "cool_contamination_detected": diag.get("cool_contamination_detected"),
        "cool_available": diag.get("cool_available"),
    }


def perturb_and_check(
    df: pd.DataFrame,
    sensor_cols: list[str],
    sigma: float,
    n_seeds: int,
) -> dict:
    rng_master = np.random.default_rng(12345)
    flips_true = 0
    flips_winner = 0
    base = baseline_contamination(df, sensor_cols)
    baseline_winner = base["winner"]
    baseline_contam = base["cool_contamination_detected"]
    for seed in range(n_seeds):
        rng = np.random.default_rng(int(rng_master.integers(0, 2**31 - 1)))
        noisy = df.copy()
        for s in sensor_cols:
            if s in noisy.columns:
                noisy[s] = noisy[s] + rng.normal(0.0, sigma, size=len(noisy))
        winner, diag = identify_core_sensor_combined_rank(noisy, sensor_cols)
        contam = diag.get("cool_contamination_detected")
        if bool(contam) and not bool(baseline_contam):
            flips_true += 1
        if winner != baseline_winner:
            flips_winner += 1
    return {
        "baseline": base,
        "n_seeds": n_seeds,
        "sigma": sigma,
        "flips_contam_False_to_True": flips_true,
        "flips_winner": flips_winner,
    }


def main():
    csvs = {
        "100098DE_1351": os.path.join(_REPO_ROOT, "ProbeData_100098DE_2025-05-30 13_51_07.csv"),
        "BA3C_0946": os.path.join(_REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"),
        "BA3C_1759": os.path.join(_REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"),
    }
    sensor_cols = [f"T{i}" for i in range(1, 9)]
    sigma = 1.0
    n_seeds = 100
    results = {}
    for name, path in csvs.items():
        if not os.path.exists(path):
            print(f"MISSING: {path}")
            continue
        df = load_curve_for_csv(path)
        result = perturb_and_check(df, sensor_cols, sigma, n_seeds)
        results[name] = result
        print(f"=== {name} ===")
        print(f"  baseline winner={result['baseline']['winner']}, "
              f"contam={result['baseline']['cool_contamination_detected']}, "
              f"cool_available={result['baseline']['cool_available']}")
        print(f"  σ={sigma}, seeds={n_seeds}")
        print(f"  contam False→True flips: {result['flips_contam_False_to_True']}/{n_seeds}")
        print(f"  winner flips: {result['flips_winner']}/{n_seeds}")
    print()
    print("SUMMARY TABLE (contam False→True rate per CSV at σ=1.0, 100 seeds):")
    for name, r in results.items():
        rate = r["flips_contam_False_to_True"] / r["n_seeds"] * 100.0
        print(f"  {name:20s} {r['flips_contam_False_to_True']:3d}/{r['n_seeds']}  ({rate:.1f}%)")


if __name__ == "__main__":
    main()
