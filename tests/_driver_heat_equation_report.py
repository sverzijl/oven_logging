"""One-shot driver that runs the synthetic + real-CSV harness and writes
the markdown report. Standalone (no pytest required); used to refresh the
empirical baseline at::

    tests/baselines/heat_equation_extrapolation_research.md

Usage::

    python -m tests._driver_heat_equation_report

Approximate runtime: ~10-15 minutes (100-seed synthetic recovery is the
dominant cost; the real-CSV pass is ~9 minutes).
"""

from __future__ import annotations

import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from src.data.spatial_reconstruction.heat_equation import (  # noqa: E402
    fit_heat_equation_inverse,
    solve_heat_eq_forward,
)
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    ROBUSTNESS_FIXTURES,
    TestRealCSVViability,
    TestRobustnessUnderNoise,
    _parabolic_extrap_x_core,
    _segmented_real_fixture,
    _surface_series_from_df,
    _synthetic_dough_observations,
    _hessian_ci_includes,
    write_report,
)
from tests.test_role_classifier_perturbation import _perturb_df  # noqa: E402


def _phase(name: str):
    print(f"\n=== {name} ===", flush=True)
    return time.time()


def main() -> None:
    # 1. Synthetic recovery (100 seeds at sigma=0.5).
    t = _phase("synthetic recovery (100 seeds, sigma=0.5)")
    x_core_true = -0.15
    alpha_true = 1.5e-3
    n_seeds = 100
    sigma = 0.5
    x_fits, x_covered = [], 0
    for seed in range(n_seeds):
        df, surf = _synthetic_dough_observations(
            alpha_true=alpha_true,
            x_core_true=x_core_true,
            in_dough_sensors=("T1", "T2", "T3", "T4"),
            noise_sigma_c=sigma,
            seed=seed,
        )
        r = fit_heat_equation_inverse(
            df=df,
            in_dough_sensors=["T1", "T2", "T3", "T4"],
            x_surface=1.0,
            T_surface_series=surf,
            x_core_init=-0.05,
            alpha_init=1e-3,
            downsample_factor=4,
        )
        if r["converged"]:
            x_fits.append(r["x_core"])
            if _hessian_ci_includes(r["x_core"], r["x_core_se"], x_core_true):
                x_covered += 1
        if (seed + 1) % 10 == 0:
            print(f"  seed {seed + 1}/{n_seeds}", flush=True)
    spread = float(np.std(x_fits))
    bias = float(np.mean(x_fits) - x_core_true)
    TestRealCSVViability._SYNTHETIC_RECOVERY = {
        "n_seeds": n_seeds,
        "sigma_c": sigma,
        "x_core_true": x_core_true,
        "alpha_true": alpha_true,
        "n_converged": len(x_fits),
        "n_covered": x_covered,
        "coverage_rate": x_covered / max(n_seeds, 1),
        "spread": spread,
        "bias": bias,
    }
    print(
        f"  bias={bias:.5f} spread={spread:.5f} covered={x_covered}/{n_seeds} "
        f"({time.time() - t:.1f}s)"
    )

    # 2. Real-CSV viability — all 7 fixtures.
    t = _phase("real-CSV viability (7 fixtures)")
    for spec in REAL_FIXTURES:
        df = _segmented_real_fixture(spec)
        surf = _surface_series_from_df(df, spec["surface"])
        r = fit_heat_equation_inverse(
            df=df,
            in_dough_sensors=spec["in_dough"],
            x_surface=spec["x_surface"],
            T_surface_series=surf,
            x_core_init=-0.05,
            alpha_init=1e-3,
            downsample_factor=4,
        )
        TestRealCSVViability._RESULTS[spec["label"]] = {
            **r,
            "fixture_name": spec["fixture_name"],
            "expected_curve_idx": spec["expected_curve_idx"],
            "n_in_dough": len(spec["in_dough"]),
            "x_surface": spec["x_surface"],
        }
        print(
            f"  {spec['label']}: x_core={r['x_core']:.4f} "
            f"alpha={r['alpha']:.2e} rmse={r['rmse_per_sensor']:.2f}"
            f" rho={r['rho_alpha_xcore']:.3f}",
            flush=True,
        )

    # 3. Noise robustness on the 3 BA3C-flavoured fixtures × 4 sigmas × 30 seeds.
    t = _phase("noise robustness (3 fixtures × 4 sigmas × 30 seeds)")
    for spec in ROBUSTNESS_FIXTURES:
        base_df = _segmented_real_fixture(spec)
        for sigma_c in [0.0, 0.5, 1.0, 2.0]:
            heat_xs, parab_xs = [], []
            for seed in range(TestRobustnessUnderNoise.SEEDS_PER_CONDITION):
                rng = np.random.default_rng(7000 + 31 * seed + int(round(sigma_c * 10)))
                if sigma_c > 0:
                    df_b = _perturb_df(base_df, sigma_c, rng)
                else:
                    df_b = base_df
                surf = _surface_series_from_df(df_b, spec["surface"])
                try:
                    r = fit_heat_equation_inverse(
                        df=df_b,
                        in_dough_sensors=spec["in_dough"],
                        x_surface=spec["x_surface"],
                        T_surface_series=surf,
                        x_core_init=-0.05,
                        alpha_init=1e-3,
                        downsample_factor=4,
                    )
                    if r["converged"]:
                        heat_xs.append(r["x_core"])
                except Exception:
                    pass
                try:
                    p = _parabolic_extrap_x_core(df_b, spec["in_dough"])
                    if p is not None and math.isfinite(p):
                        parab_xs.append(p)
                except Exception:
                    pass
            TestRobustnessUnderNoise._RESULTS[(spec["label"], sigma_c)] = {
                "heat_eq_n": len(heat_xs),
                "heat_eq_mean": float(np.mean(heat_xs)) if heat_xs else None,
                "heat_eq_std": float(np.std(heat_xs)) if heat_xs else None,
                "parab_n": len(parab_xs),
                "parab_mean": float(np.mean(parab_xs)) if parab_xs else None,
                "parab_std": float(np.std(parab_xs)) if parab_xs else None,
            }
            print(
                f"  {spec['label']} sigma={sigma_c}: "
                f"heat n={len(heat_xs)} mean={np.mean(heat_xs) if heat_xs else float('nan'):.4f} "
                f"std={np.std(heat_xs) if heat_xs else float('nan'):.4f} | "
                f"parab n={len(parab_xs)} mean={np.mean(parab_xs) if parab_xs else float('nan'):.4f} "
                f"std={np.std(parab_xs) if parab_xs else float('nan'):.4f}",
                flush=True,
            )

    # 4. Write the report.
    t = _phase("write report")
    path = write_report()
    print(f"  wrote {path} ({time.time() - t:.1f}s)")

    # 5. Dump the raw numbers as JSON next to the report for downstream
    # consumers (captain's log).
    raw = {
        "synthetic_recovery": TestRealCSVViability._SYNTHETIC_RECOVERY,
        "real_csv": {
            k: {kk: vv for kk, vv in v.items() if kk != "T_initial"}
            for k, v in TestRealCSVViability._RESULTS.items()
        },
        "noise_robustness": {
            f"{k[0]}__{k[1]}": v for k, v in TestRobustnessUnderNoise._RESULTS.items()
        },
    }
    json_path = os.path.join(
        os.path.dirname(path), "heat_equation_extrapolation_raw.json"
    )
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, default=str)
    print(f"  wrote {json_path}")


if __name__ == "__main__":
    main()
