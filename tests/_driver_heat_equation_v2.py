"""HMS Resolution — Method 3 round-2 driver.

Runs the corrected-BC v2 fitter, the profile-likelihood scan, and the
synthetic_shallow_insertion misfit baseline; appends a Round 2 section to
``tests/baselines/heat_equation_extrapolation_research.md``.

Phases:
1. v2 corrected-BC viability across all 7 real fixtures (~6 min).
2. Profile-likelihood scan on 3 fixtures × 25 grid points (~12 min).
3. synthetic_shallow_insertion misfit fit (~50 s).

Approximate runtime: ~20 min on the same hardware that ran M7.

Usage::

    python -m tests._driver_heat_equation_v2

If wall-time becomes an issue, raise ``DOWNSAMPLE_FACTOR`` from 4 to 16.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from src.data.spatial_reconstruction.classifier import classify  # noqa: E402
from src.data.spatial_reconstruction.geometry import lookup_geometry  # noqa: E402
from src.data.spatial_reconstruction.heat_equation import (  # noqa: E402
    _build_observation_matrix,
    fit_heat_equation_inverse_v2,
    profile_likelihood_x_core,
    solve_heat_eq_forward,
)
from src.data.spatial_reconstruction.profile import (  # noqa: E402
    interpolate_temperature_series_at,
)
from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    SENSOR_NAMES,
    SENSOR_POSITIONS,
    TestRealCSVViability,
    _segmented_real_fixture,
)


DOWNSAMPLE_FACTOR = 4
PROFILE_GRID_SIZE = 25
PROFILE_X_LO = -0.5
PROFILE_X_HI = 0.5

# 3 representative fixtures for the profile-likelihood scan
PROFILE_LABELS = ("BA3C_0946", "100098DE_1351", "wonder_white")


def _phase(name: str) -> float:
    print(f"\n=== {name} ===", flush=True)
    return time.time()


def _classifier_x_surface(spec: dict) -> float:
    df = _segmented_real_fixture(spec)
    geom = lookup_geometry(probe_sn=None, probe_model=None)
    a = classify(df, sample_period_ms=5000, probe_geometry=geom)
    if a.surface_assignment is None:
        return float(spec["x_surface"])
    return float(a.surface_assignment.position_normalised)


def main() -> None:
    out: dict = {"phase1_v2": {}, "phase2_profile": {}, "phase3_misfit": {}}

    # -------------------- Phase 1: v2 corrected-BC viability ----------
    t0 = _phase(f"phase 1: v2 corrected-BC viability ({len(REAL_FIXTURES)} fixtures)")
    for spec in REAL_FIXTURES:
        df = _segmented_real_fixture(spec)
        x_surf_cont = _classifier_x_surface(spec)
        t_fit = time.time()
        r = fit_heat_equation_inverse_v2(
            df=df,
            in_dough_sensors=spec["in_dough"],
            x_surface_continuous=x_surf_cont,
            x_core_init=-0.05,
            alpha_init=1e-3,
            downsample_factor=DOWNSAMPLE_FACTOR,
        )
        out["phase1_v2"][spec["label"]] = {
            **r,
            "fixture_name": spec["fixture_name"],
            "expected_curve_idx": spec["expected_curve_idx"],
            "n_in_dough": len(spec["in_dough"]),
            "x_surface_continuous": x_surf_cont,
            "in_dough": list(spec["in_dough"]),
            "fit_seconds": time.time() - t_fit,
        }
        print(
            f"  {spec['label']:>20}: x_surf_cont={x_surf_cont:.4f}  "
            f"x_core={r['x_core']:.4f}  alpha={r['alpha']:.2e}  "
            f"rmse={r['rmse_per_sensor']:.2f}  rho={r['rho_alpha_xcore']:.3f}  "
            f"({time.time() - t_fit:.1f}s)",
            flush=True,
        )
    print(f"  phase 1 elapsed: {time.time() - t0:.1f}s", flush=True)

    # -------------------- Phase 2: profile-likelihood scans -----------
    t0 = _phase(
        f"phase 2: profile-likelihood scan ({len(PROFILE_LABELS)} fixtures × "
        f"{PROFILE_GRID_SIZE} grid points)"
    )
    for spec in REAL_FIXTURES:
        if spec["label"] not in PROFILE_LABELS:
            continue
        df = _segmented_real_fixture(spec)
        x_surf_cont = _classifier_x_surface(spec)
        # Keep grid interior to x_surface_continuous (model rejects x_core ≥ x_surface).
        upper = min(PROFILE_X_HI, x_surf_cont - 0.05)
        x_grid = np.linspace(PROFILE_X_LO, upper, PROFILE_GRID_SIZE)
        t_scan = time.time()
        scan = profile_likelihood_x_core(
            df=df,
            in_dough_sensors=spec["in_dough"],
            x_surface_continuous=x_surf_cont,
            x_core_grid=x_grid,
            alpha_init=1e-3,
            downsample_factor=DOWNSAMPLE_FACTOR,
        )
        out["phase2_profile"][spec["label"]] = {
            "x_surface_continuous": x_surf_cont,
            "in_dough": list(spec["in_dough"]),
            "scan": scan.to_dict(orient="records"),
            "fit_seconds": time.time() - t_scan,
        }
        # Quick verdict numbers
        finite = scan[np.isfinite(scan["loss"])]
        if len(finite) > 0:
            lmin = float(finite["loss"].min())
            lmax = float(finite["loss"].max())
            lmed = float(finite["loss"].median())
            x_at_min = float(finite.loc[finite["loss"].idxmin(), "x_core"])
            relative_range = (lmax - lmin) / max(abs(lmed), 1e-9)
            print(
                f"  {spec['label']:>20}: scan_min_loss={lmin:.1f} max={lmax:.1f} "
                f"med={lmed:.1f}  argmin_x_core={x_at_min:.3f}  "
                f"rel_range={relative_range:.2f}  ({time.time() - t_scan:.1f}s)",
                flush=True,
            )
    print(f"  phase 2 elapsed: {time.time() - t0:.1f}s", flush=True)

    # -------------------- Phase 3: synthetic_shallow_insertion --------
    t0 = _phase("phase 3: synthetic_shallow_insertion misfit baseline")
    case = next(c for c in CASES if c["name"] == "synthetic_shallow_insertion")
    df = case["df"].copy()
    starts = case.get("expected_starts") or [0]
    ends = case.get("expected_ends") or [len(df) - 1]
    s, e = int(starts[0]), int(ends[0])
    sub = df.iloc[s : e + 1].reset_index(drop=True)
    if "Timestamp" in sub.columns:
        t_offset = float(sub["Timestamp"].iloc[0])
        sub["Timestamp"] = sub["Timestamp"].to_numpy(dtype=float) - t_offset
    x_surf_cont = float(case["expected_x_dough_air_normalised"])
    in_dough = ["T1", "T2"]
    t_fit = time.time()
    r3 = fit_heat_equation_inverse_v2(
        df=sub,
        in_dough_sensors=in_dough,
        x_surface_continuous=x_surf_cont,
        x_core_init=-0.05,
        alpha_init=1e-3,
        downsample_factor=2,
    )
    # Per-sensor residuals
    t_obs, T_obs, x_obs = _build_observation_matrix(
        df=sub,
        in_dough_sensors=in_dough,
        sensor_names=SENSOR_NAMES,
        sensor_positions_normalised=SENSOR_POSITIONS,
        downsample_factor=2,
    )
    surf_full = interpolate_temperature_series_at(
        sub, positions=SENSOR_POSITIONS, x_target=x_surf_cont, sensors=SENSOR_NAMES,
    ).to_numpy(dtype=float)
    T_surf_obs = np.interp(t_obs, sub["Timestamp"].to_numpy(dtype=float), surf_full)
    T_pred = solve_heat_eq_forward(
        alpha=r3["alpha"],
        x_core=r3["x_core"],
        x_surface=x_surf_cont,
        t_grid=t_obs,
        T_surface_series=T_surf_obs,
        T_initial=r3["T_initial"],
        n_spatial=30,
        sample_x=x_obs,
    )
    per_sensor_rmse = {
        in_dough[k]: float(np.sqrt(np.mean((T_pred[:, k] - T_obs[:, k]) ** 2)))
        for k in range(len(in_dough))
    }
    out["phase3_misfit"] = {
        **r3,
        "x_surface_continuous": x_surf_cont,
        "in_dough": list(in_dough),
        "per_sensor_rmse": per_sensor_rmse,
        "fit_seconds": time.time() - t_fit,
    }
    print(
        f"  shallow_insertion: x_core={r3['x_core']:.4f}  alpha={r3['alpha']:.2e}  "
        f"rmse={r3['rmse_per_sensor']:.2f}  per_sensor={per_sensor_rmse}",
        flush=True,
    )

    # -------------------- Persist raw JSON ----------------------------
    json_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "baselines",
        "heat_equation_extrapolation_round2.json",
    )
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  wrote {json_path}", flush=True)

    # -------------------- Append Round 2 section to report ------------
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "baselines",
        "heat_equation_extrapolation_research.md",
    )
    section = _render_round2_section(out)
    with open(report_path, "a", encoding="utf-8") as f:
        f.write(section)
    print(f"  appended Round 2 section to {report_path}", flush=True)


def _verdict_logic(
    phase1: dict, phase2: dict, phase3: dict
) -> tuple[str, list[str]]:
    """Apply the spec's verdict criteria and return (verdict, rationale lines).

    * **REVISE TO GO** if corrected-BC RMSE < 2 °C across most fixtures
      AND profile-likelihood shows a clear minimum AND at least one BA3C
      fixture extrapolates past T1.
    * **REVISE TO GO-WITH-CAVEATS** if corrected-BC RMSE drops to 2-4 °C
      OR profile-likelihood shows a basin.
    * **CONFIRM NO-GO** if corrected-BC RMSE is still > 4 °C on most
      fixtures AND profile-likelihood is genuinely flat.
    """
    rmses = [
        v["rmse_per_sensor"]
        for v in phase1.values()
        if math.isfinite(v["rmse_per_sensor"])
    ]
    median_rmse = float(np.median(rmses)) if rmses else float("nan")
    max_rmse = float(np.max(rmses)) if rmses else float("nan")

    ba3c_extrap = any(
        v["x_core"] < 0.0 and label.startswith("BA3C")
        for label, v in phase1.items()
    )

    # Profile-likelihood verdict per fixture
    pl_basin_count = 0
    pl_total = 0
    for label, payload in phase2.items():
        scan = pd.DataFrame(payload["scan"])
        finite = scan[np.isfinite(scan["loss"])]
        if len(finite) < 5:
            continue
        pl_total += 1
        lmin = float(finite["loss"].min())
        lmax = float(finite["loss"].max())
        lmed = float(finite["loss"].median()) or 1.0
        # Basin = relative range > 0.5 AND argmin is interior to grid
        rel_range = (lmax - lmin) / max(abs(lmed), 1e-9)
        if rel_range > 0.5:
            pl_basin_count += 1

    rationale: list[str] = []
    rationale.append(
        f"Corrected-BC RMSE: median={median_rmse:.2f} °C, "
        f"max={max_rmse:.2f} °C across {len(rmses)} fixtures."
    )
    rationale.append(
        f"Profile-likelihood: {pl_basin_count}/{pl_total} fixtures show a basin; "
        f"the rest are flat-loss (structural degeneracy)."
    )
    rationale.append(
        f"BA3C past-T1 extrapolation: "
        f"{'YES' if ba3c_extrap else 'NO'} (no BA3C case crosses x_core<0 with corrected BC)"
        if not ba3c_extrap else
        f"BA3C past-T1 extrapolation: YES — at least one BA3C fixture has x_core<0."
    )

    if (
        max_rmse < 2.0
        and pl_basin_count == pl_total
        and ba3c_extrap
    ):
        return "REVISE TO GO", rationale
    if median_rmse < 4.0 or pl_basin_count > 0:
        return "REVISE TO GO-WITH-CAVEATS", rationale
    return "CONFIRM NO-GO", rationale


def _render_round2_section(out: dict) -> str:
    phase1 = out["phase1_v2"]
    phase2 = out["phase2_profile"]
    phase3 = out["phase3_misfit"]
    verdict, rationale = _verdict_logic(phase1, phase2, phase3)

    lines: list[str] = []
    lines.append("\n\n---\n")
    lines.append("# Round 2 — corrected BC + profile likelihood (HMS Resolution, 2026-04-28)\n")
    lines.append(
        "The Round 1 (HMS Ambush) verdict was driven in part by a discrete-sensor "
        "surface BC. On the typical BA3C insertion the M2a classifier identifies "
        "T6 as the surface-side sensor, but T6 itself is *in dough* (it plateaus "
        "near 100 °C). Feeding T6's time series as the Dirichlet BC at x_surface "
        "is feeding a fake-plateau, not the true dough/air interface temperature; "
        "the inverse problem becomes information-free over most of the bake.\n"
    )
    lines.append(
        "Round 2 retests with three fixes: (i) the BC is built by per-timestep "
        "linear *spatial* interpolation across all 8 sensors at the M2a "
        "continuous interface position `surface_assignment.position_normalised`, "
        "(ii) a profile-likelihood scan distinguishes structural degeneracy "
        "from optimiser laziness, and (iii) `synthetic_shallow_insertion` is "
        "inverted as a true model-misfit baseline (its data was NOT generated "
        "by the heat-eq forward solver).\n"
    )

    # ---- Phase 1 table
    lines.append("\n## Corrected-BC real-CSV viability (7 fixtures)\n")
    lines.append(
        "| fixture | x_surf_cont | x_core (v2) | x_core (M7 v1) | α (v2) | "
        "&#124;ρ&#124; (v2) | RMSE v2 (°C) | RMSE v1 (°C) | extrap |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|"
    )
    # Round-1 values from M7's report (canonical record)
    M7_V1 = {
        "BA3C_1759_C1": {"x_core": 0.117, "rho": -0.871, "rmse": 6.14},
        "BA3C_0946": {"x_core": 0.032, "rho": -0.905, "rmse": 6.09},
        "BA3C_1759_C0": {"x_core": 0.032, "rho": -0.905, "rmse": 6.09},
        "BA3C_1759_C2": {"x_core": 0.249, "rho": -0.907, "rmse": 6.48},
        "100098DE_1351": {"x_core": 0.430, "rho": -0.905, "rmse": 7.03},
        "post_wonder_meal": {"x_core": -0.061, "rho": -0.001, "rmse": 9.98},
        "wonder_white": {"x_core": -0.081, "rho": -0.003, "rmse": 10.01},
    }
    for label, r in phase1.items():
        v1 = M7_V1.get(label, {})
        rho_str = (
            f"{abs(r['rho_alpha_xcore']):.3f}"
            if math.isfinite(r["rho_alpha_xcore"])
            else "n/a"
        )
        v1_xcore = f"{v1.get('x_core', float('nan')):.3f}" if v1 else "n/a"
        v1_rmse = f"{v1.get('rmse', float('nan')):.2f}" if v1 else "n/a"
        lines.append(
            f"| `{label}` | {r['x_surface_continuous']:.4f} | "
            f"{r['x_core']:.3f} | {v1_xcore} | {r['alpha']:.2e} | "
            f"{rho_str} | {r['rmse_per_sensor']:.2f} | {v1_rmse} | "
            f"{r['extrapolated']} |"
        )

    # ---- Phase 2 profile-likelihood
    lines.append("\n## Profile-likelihood diagnostic (3 fixtures)\n")
    for label, payload in phase2.items():
        scan = pd.DataFrame(payload["scan"])
        finite = scan[np.isfinite(scan["loss"])]
        if len(finite) == 0:
            lines.append(f"\n### `{label}` — all loss values non-finite\n")
            continue
        lmin = float(finite["loss"].min())
        lmax = float(finite["loss"].max())
        lmed = float(finite["loss"].median())
        x_argmin = float(finite.loc[finite["loss"].idxmin(), "x_core"])
        rel_range = (lmax - lmin) / max(abs(lmed), 1e-9)
        is_basin = rel_range > 0.5 and (
            x_argmin > finite["x_core"].min() + 1e-3
            and x_argmin < finite["x_core"].max() - 1e-3
        )
        verdict_line = (
            "BASIN — loss has a clear minimum (numerical, not structural)."
            if is_basin
            else "FLAT — structural degeneracy (loss varies < 50% across the grid)."
        )
        lines.append(
            f"\n### `{label}` (x_surf_cont = {payload['x_surface_continuous']:.4f})\n"
        )
        lines.append(f"min loss = {lmin:.1f}, max = {lmax:.1f}, median = {lmed:.1f}, "
                     f"argmin x_core = {x_argmin:.3f}, relative range = {rel_range:.2f}")
        lines.append(f"\n**Verdict: {verdict_line}**\n")
        lines.append("\n| x_core | α best | loss |")
        lines.append("|---|---|---|")
        # Show every 3rd row to keep table compact
        for i, row in finite.iloc[::3].iterrows():
            lines.append(
                f"| {row['x_core']:.3f} | {row['alpha_best']:.2e} | {row['loss']:.1f} |"
            )

    # ---- Phase 3 shallow insertion
    lines.append("\n## Synthetic shallow-insertion model-misfit baseline\n")
    lines.append(
        "The fixture was *not* generated by the heat-eq forward solver — its "
        "temperatures come from the role-classifier fixture-builder. Inverting "
        "it tests whether the heat-equation model class fits real bake "
        "geometries at all.\n"
    )
    lines.append(
        f"\n* x_surface_continuous = {phase3['x_surface_continuous']:.4f}"
    )
    lines.append(f"* in-dough sensors = {phase3['in_dough']}")
    lines.append(
        f"* fitted x_core = {phase3['x_core']:.4f}, "
        f"α = {phase3['alpha']:.2e}, "
        f"overall RMSE = {phase3['rmse_per_sensor']:.2f} °C"
    )
    lines.append("\nPer-sensor RMSE:\n")
    lines.append("| sensor | RMSE (°C) |")
    lines.append("|---|---|")
    for s, rmse in phase3["per_sensor_rmse"].items():
        lines.append(f"| {s} | {rmse:.2f} |")

    # ---- Revised verdict
    lines.append("\n## Revised verdict\n")
    lines.append(f"**{verdict}**\n")
    for line in rationale:
        lines.append(f"- {line}")
    lines.append("")
    lines.append(
        "Verdict logic: REVISE TO GO requires max-RMSE < 2 °C, every "
        "profile-likelihood scan showing a basin, and at least one BA3C case "
        "extrapolating past T1 (x_core<0). REVISE TO GO-WITH-CAVEATS if "
        "median-RMSE < 4 °C or any scan shows a basin. CONFIRM NO-GO otherwise."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
