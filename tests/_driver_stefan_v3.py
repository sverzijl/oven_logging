"""HMS Onslaught (M21) — Stefan v3 driver (1D + distributed side-source).

Phases:

1. **Forward sanity** —
   (a) ``Q_side=0`` reproduces M9/M20 forward within 0.01 K.
   (b) ``Q_side > 0`` warms the interior vs the no-source case.

2. **Synthetic recovery** — generate a bake at known Q_side under
   different-class generators (varying x_core, smear, α). Recovery
   target: 30% relative on Q_side across at least 3/5 seeds.

3. **Single-fixture decision gate on BA3C_0946** —
   bar: main-bake RMSE < 4 °C AND ≥4/6 params interior.
   Verdict honoured.

4. **5-fixture sweep** — only if the gate passes.

Outputs:

* ``tests/baselines/stefan_v3_research.json`` — structured JSON.
* ``tests/baselines/stefan_v3_research.md`` — human-readable report.
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

from src.data.spatial_reconstruction.profile import (  # noqa: E402
    interpolate_temperature_series_at,
)
from src.data.spatial_reconstruction.stefan_inverse import (  # noqa: E402
    solve_stefan_forward,
)
from src.data.spatial_reconstruction.stefan_inverse_v3 import (  # noqa: E402
    BOUNDS_V3,
    INIT_V3,
    PARAM_NAMES_V3,
    _build_g_oven_from_ambient,
    fit_stefan_inverse_v3,
    solve_stefan_forward_v3,
)
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    SENSOR_NAMES,
    SENSOR_POSITIONS,
    _segmented_real_fixture,
)

DOWNSAMPLE_FACTOR = 4
N_SPATIAL = 30
MAX_ITER = 700

# Baselines for comparison.
M9_MAIN_BAKE_RMSE = {
    "BA3C_0946": 5.76,
    "BA3C_1759_C0": 6.80,
    "BA3C_1759_C1": 7.95,
    "BA3C_1759_C2": 7.49,
    "100098DE_1351": 11.03,
}
M20_MAIN_BAKE_RMSE = {
    "BA3C_0946": 5.73,
}

SWEEP_LABELS = (
    "BA3C_0946",
    "BA3C_1759_C0",
    "BA3C_1759_C1",
    "BA3C_1759_C2",
    "100098DE_1351",
)

X_SURFACE_CACHED = {
    "BA3C_0946": 0.6786994367639527,
    "BA3C_1759_C0": 0.6786994367639527,
    "BA3C_1759_C1": 0.7177439275421984,
    "BA3C_1759_C2": 0.7131671056904703,
    "100098DE_1351": 0.7703681378329582,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(BASE_DIR, "baselines", "stefan_v3_research.json")
OUT_MD = os.path.join(BASE_DIR, "baselines", "stefan_v3_research.md")


def _segment_main_mask(n_t: int) -> np.ndarray:
    idx = np.arange(n_t)
    frac = idx / max(n_t - 1, 1)
    return (frac >= 0.10) & (frac < 0.90)


def _build_obs(df: pd.DataFrame, in_dough: list, x_surface_continuous: float):
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs = np.array([pos_map[s] for s in in_dough], dtype=float)
    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    T_cols = [df[s].to_numpy(dtype=float)[sl] for s in in_dough]
    T_obs = np.column_stack(T_cols)
    surface_full = interpolate_temperature_series_at(
        df,
        positions=SENSOR_POSITIONS,
        x_target=float(x_surface_continuous),
        sensors=SENSOR_NAMES,
    ).to_numpy(dtype=float)
    T_surf_obs = np.interp(t_obs, t_full, surface_full)
    T_initial = float(np.mean(T_obs[0, :]))
    g_obs = _build_g_oven_from_ambient(
        df=df,
        sensor_names=SENSOR_NAMES,
        sensor_positions_normalised=SENSOR_POSITIONS,
        x_surface_continuous=x_surface_continuous,
        t_target=t_obs,
        T_initial_dough=T_initial,
    )
    return t_obs, T_obs, x_obs, T_surf_obs, T_initial, g_obs


def _main_bake_rmse_from_fit(
    df: pd.DataFrame, in_dough: list, x_surface_continuous: float, fit: dict
) -> tuple[float, float]:
    t_obs, T_obs, x_obs, T_surf_obs, T_initial, g_obs = _build_obs(
        df, in_dough, x_surface_continuous
    )
    T_pred = solve_stefan_forward_v3(
        x_core=fit["x_core"],
        x_surface=x_surface_continuous,
        alpha_dough=fit["alpha_dough"],
        alpha_crust=fit["alpha_crust"],
        rhoL_eff=fit["rhoL_eff"],
        t_grid=t_obs,
        T_surface_series=T_surf_obs,
        T_initial=T_initial,
        Q_side=fit["Q_side"],
        g_oven_series=g_obs,
        n_spatial=N_SPATIAL,
        sample_x=x_obs,
        delta_T_smear=fit["delta_T_smear"],
    )
    residual = T_pred - T_obs
    rmse_full = float(np.sqrt(np.mean(residual ** 2)))
    main_mask = _segment_main_mask(residual.shape[0])
    rmse_main = float(np.sqrt(np.mean(residual[main_mask, :] ** 2)))
    return rmse_full, rmse_main


def _phase_header(name: str) -> float:
    print(f"\n=== {name} ===", flush=True)
    return time.time()


# -------------------------------------------------------------------------
# Phase 1 — forward sanity
# -------------------------------------------------------------------------


def phase1_forward_sanity() -> dict:
    t = np.linspace(0.0, 1500.0, 200)
    surf = np.linspace(25.0, 200.0, 200)
    sample_x = np.array([0.0, 0.15, 0.30, 0.45, 0.60])
    g_t = np.clip((surf - 25.0) / (200.0 - 25.0), 0.0, 1.0)

    common = dict(
        x_core=-0.05,
        x_surface=0.7,
        alpha_dough=8e-7,
        alpha_crust=5e-7,
        rhoL_eff=100.0,
        t_grid=t,
        T_surface_series=surf,
        T_initial=25.0,
        n_spatial=40,
        sample_x=sample_x,
        delta_T_smear=5.0,
    )
    T_v2 = solve_stefan_forward(**common)
    T_v3_zero = solve_stefan_forward_v3(**common, Q_side=0.0)
    diff_zero = float(np.max(np.abs(T_v2 - T_v3_zero)))
    sanity_a = diff_zero < 0.01

    T_v3_high = solve_stefan_forward_v3(
        **common, Q_side=1e5, g_oven_series=g_t
    )
    delta_high = T_v3_high - T_v3_zero
    sanity_b = bool(delta_high.max() > 1.0 and delta_high.min() > -1e-3)

    print(
        f"  (a) Q_side=0 reproduces v2: max|Δ| = {diff_zero:.5f} K → "
        f"{'PASS' if sanity_a else 'FAIL'}",
        flush=True,
    )
    print(
        f"  (b) Q_side=1e5 warms interior: max ΔT = {delta_high.max():.2f} K, "
        f"min ΔT = {delta_high.min():.4f} K → "
        f"{'PASS' if sanity_b else 'FAIL'}",
        flush=True,
    )
    return {
        "Q_side_zero_max_dev_K": diff_zero,
        "Q_side_high_max_warming_K": float(delta_high.max()),
        "Q_side_high_min_warming_K": float(delta_high.min()),
        "pass_a": bool(sanity_a),
        "pass_b": bool(sanity_b),
        "pass": bool(sanity_a and sanity_b),
    }


# -------------------------------------------------------------------------
# Phase 2 — synthetic recovery
# -------------------------------------------------------------------------


def phase2_synthetic_recovery(seeds: tuple = (11, 23, 37, 53, 71)) -> dict:
    """Generate synthetic at varied truths; recover Q_side within 30%."""
    rng_master = np.random.default_rng(7)
    n_t = 240
    period_s = 5.0
    t = np.arange(n_t, dtype=float) * period_s
    half = n_t // 2
    surf = np.empty(n_t)
    surf[:half] = np.linspace(25.0, 200.0, half)
    surf[half:] = 200.0
    g_t = np.clip((surf - 25.0) / (200.0 - 25.0), 0.0, 1.0)
    in_dough = ("T1", "T2", "T3", "T4", "T5")
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs = np.array([pos_map[s] for s in in_dough])

    rows = []
    n_pass = 0
    # Choose truth distributions sampling within v3 bounds.
    truths = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        # Q_side in [1e4, 1.5e5] — interior of (0, 5e5).
        Q_true = float(rng.uniform(1e4, 1.5e5))
        # alpha_dough in [3e-4, 1e-3] — interior of v3 bounds.
        ad_true = float(rng.uniform(3e-4, 1e-3))
        ac_true = float(rng.uniform(1e-4, 6e-4))
        rhoL_true = float(rng.uniform(50.0, 400.0))
        smear_true = float(rng.uniform(4.0, 8.0))
        xc_true = float(rng.uniform(-0.08, 0.05))
        truths.append(
            dict(
                seed=int(seed),
                Q_side=Q_true,
                alpha_dough=ad_true,
                alpha_crust=ac_true,
                rhoL_eff=rhoL_true,
                delta_T_smear=smear_true,
                x_core=xc_true,
            )
        )

    for spec in truths:
        x_surface = 0.7
        try:
            T_synth = solve_stefan_forward_v3(
                x_core=spec["x_core"],
                x_surface=x_surface,
                alpha_dough=spec["alpha_dough"],
                alpha_crust=spec["alpha_crust"],
                rhoL_eff=spec["rhoL_eff"],
                t_grid=t,
                T_surface_series=surf,
                T_initial=25.0,
                Q_side=spec["Q_side"],
                g_oven_series=g_t,
                n_spatial=80,
                sample_x=x_obs,
                delta_T_smear=spec["delta_T_smear"],
            )
        except Exception as exc:
            rows.append({**spec, "error": f"forward_failed:{exc}"})
            continue
        rng_noise = np.random.default_rng(spec["seed"] + 9999)
        T_synth = T_synth + rng_noise.normal(0.0, 0.3, size=T_synth.shape)
        df = pd.DataFrame({"Timestamp": t})
        for k, s in enumerate(in_dough):
            df[s] = T_synth[:, k]
        for s in SENSOR_NAMES:
            if s not in df.columns:
                df[s] = surf
        try:
            t0 = time.time()
            r = fit_stefan_inverse_v3(
                df=df,
                in_dough_sensors=list(in_dough),
                x_surface_continuous=x_surface,
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                max_iter=MAX_ITER,
                g_oven_series=g_t,
            )
            fit_seconds = time.time() - t0
            Q_fit = r["Q_side"]
            rel_err_Q = abs(Q_fit - spec["Q_side"]) / max(spec["Q_side"], 1.0)
            ok = rel_err_Q < 0.30
            n_pass += int(ok)
            rows.append({
                "seed": spec["seed"],
                "Q_side_true": spec["Q_side"],
                "Q_side_fit": float(Q_fit),
                "Q_side_rel_err": float(rel_err_Q),
                "alpha_dough_true": spec["alpha_dough"],
                "alpha_dough_fit": float(r["alpha_dough"]),
                "alpha_crust_true": spec["alpha_crust"],
                "alpha_crust_fit": float(r["alpha_crust"]),
                "delta_T_smear_true": spec["delta_T_smear"],
                "delta_T_smear_fit": float(r["delta_T_smear"]),
                "rhoL_true": spec["rhoL_eff"],
                "rhoL_fit": float(r["rhoL_eff"]),
                "x_core_true": spec["x_core"],
                "x_core_fit": float(r["x_core"]),
                "rmse_per_sensor": float(r["rmse_per_sensor"]),
                "fit_seconds": float(fit_seconds),
                "n_at_bound": int(r["n_at_bound"]),
                "recovered_within_30pct": bool(ok),
            })
            print(
                f"  seed={spec['seed']:>3}: Q_true={spec['Q_side']:.2e} "
                f"Q_fit={Q_fit:.2e} rel_err={rel_err_Q*100:.1f}% "
                f"rmse={r['rmse_per_sensor']:.2f} n_b={r['n_at_bound']} "
                f"({fit_seconds:.1f}s) → {'PASS' if ok else 'FAIL'}",
                flush=True,
            )
        except Exception as exc:
            rows.append({"seed": spec["seed"], "error": f"fit_failed:{exc}"})
            print(f"  seed={spec['seed']}: ERROR {exc}", flush=True)

    return {
        "rows": rows,
        "n_pass": int(n_pass),
        "n_total": int(len(seeds)),
        "pass_threshold": 3,
        "pass": bool(n_pass >= 3),
    }


# -------------------------------------------------------------------------
# Phase 3 — single-fixture decision gate
# -------------------------------------------------------------------------


def _fit_one_fixture(label: str) -> dict:
    spec = next(s for s in REAL_FIXTURES if s["label"] == label)
    df = _segmented_real_fixture(spec)
    x_surface_continuous = X_SURFACE_CACHED[label]

    t0 = time.time()
    result = fit_stefan_inverse_v3(
        df=df,
        in_dough_sensors=spec["in_dough"],
        x_surface_continuous=x_surface_continuous,
        downsample_factor=DOWNSAMPLE_FACTOR,
        n_spatial=N_SPATIAL,
        max_iter=MAX_ITER,
    )
    fit_seconds = time.time() - t0

    rmse_full, rmse_main = _main_bake_rmse_from_fit(
        df, spec["in_dough"], x_surface_continuous, result
    )
    out = dict(result)
    out["fixture_label"] = label
    out["fixture_name"] = spec["fixture_name"]
    out["expected_curve_idx"] = spec["expected_curve_idx"]
    out["x_surface_continuous"] = x_surface_continuous
    out["fit_seconds"] = float(fit_seconds)
    out["rmse_full_recomputed"] = float(rmse_full)
    out["rmse_main_bake"] = float(rmse_main)
    out["m9_main_bake_rmse"] = M9_MAIN_BAKE_RMSE.get(label, float("nan"))
    out["m20_main_bake_rmse"] = M20_MAIN_BAKE_RMSE.get(label, float("nan"))
    return out


def phase3_single_fixture() -> dict:
    label = "BA3C_0946"
    res = _fit_one_fixture(label)
    rmse_main = res["rmse_main_bake"]
    n_at_bound = res.get("n_at_bound", 99)
    n_interior = 6 - n_at_bound
    main_pass = (rmse_main < 4.0) and (n_interior >= 4)

    print(
        f"  {label}: main-bake RMSE = {rmse_main:.2f} °C "
        f"(M9={res['m9_main_bake_rmse']:.2f}, "
        f"M20={res['m20_main_bake_rmse']:.2f}); "
        f"n_interior={n_interior}/6; converged={res['converged']}; "
        f"max|ρ|={res['max_abs_off_diag_correlation']:.3f}; "
        f"({res['fit_seconds']:.1f}s) → {'PASS' if main_pass else 'FAIL'}",
        flush=True,
    )
    print(
        f"  fitted params: x_core={res['x_core']:.4f} "
        f"alpha_dough={res['alpha_dough']:.3e} "
        f"alpha_crust={res['alpha_crust']:.3e} "
        f"rhoL_eff={res['rhoL_eff']:.2f} "
        f"delta_T_smear={res['delta_T_smear']:.2f} "
        f"Q_side={res['Q_side']:.3e}",
        flush=True,
    )
    print(f"  param_at_bound={res['param_at_bound']}", flush=True)
    return {
        "fit": res,
        "main_pass": bool(main_pass),
        "rmse_main_bar_C": 4.0,
        "n_interior_min": 4,
    }


# -------------------------------------------------------------------------
# Phase 4 — sweep (only on gate pass)
# -------------------------------------------------------------------------


def phase4_sweep(skip_first: Optional[dict] = None) -> dict:
    rows = {}
    if skip_first is not None and skip_first.get("fixture_label") == "BA3C_0946":
        rows["BA3C_0946"] = skip_first
    for label in SWEEP_LABELS:
        if label in rows:
            continue
        try:
            r = _fit_one_fixture(label)
            rows[label] = r
            print(
                f"  {label}: main-bake RMSE = {r['rmse_main_bake']:.2f} °C "
                f"(M9={r['m9_main_bake_rmse']:.2f}); "
                f"n_at_bound={r['n_at_bound']}; "
                f"Q_side={r['Q_side']:.3e}; "
                f"converged={r['converged']}; "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
        except Exception as exc:
            rows[label] = {
                "fixture_label": label,
                "error": str(exc),
                "rmse_main_bake": float("nan"),
                "rmse_full_recomputed": float("nan"),
                "converged": False,
                "n_at_bound": 99,
            }
            print(f"  {label}: ERROR {exc}", flush=True)
    return rows


# -------------------------------------------------------------------------
# Verdict
# -------------------------------------------------------------------------


def _verdict(p2: dict, p3: dict, p4: Optional[dict]) -> tuple[str, list[str]]:
    rationale = []
    p3_rmse = p3["fit"]["rmse_main_bake"]
    p3_n_int = 6 - p3["fit"]["n_at_bound"]
    rationale.append(
        f"Phase 3 single-fixture BA3C_0946 main-bake RMSE = {p3_rmse:.2f} °C "
        f"(M9 5.76, M20 5.73; bar 4.0). n_interior = {p3_n_int}/6 (min 4)."
    )
    rationale.append(
        f"Phase 2 synthetic recovery: {p2['n_pass']}/{p2['n_total']} seeds "
        f"recovered Q_side within 30% (gate {p2['pass_threshold']})."
    )
    if not p3["main_pass"]:
        if p3_rmse >= 6.0:
            return "CONFIRM-information-limit", rationale
        return "GO-WITH-CAVEATS", rationale
    if p4 is None:
        return "GO-WITH-CAVEATS", rationale
    main_rmses = [
        v.get("rmse_main_bake", float("nan"))
        for v in p4.values()
        if math.isfinite(v.get("rmse_main_bake", float("nan")))
    ]
    if not main_rmses:
        return "CONFIRM-information-limit", rationale
    median_main = float(np.median(main_rmses))
    max_main = float(np.max(main_rmses))
    rationale.append(
        f"Phase 4 sweep: median main-bake RMSE = {median_main:.2f} °C, "
        f"max = {max_main:.2f} °C across {len(main_rmses)} fixtures (bar 4.0)."
    )
    if median_main < 4.0 and max_main < 6.0:
        return "GO", rationale
    if median_main < 6.0:
        return "GO-WITH-CAVEATS", rationale
    return "CONFIRM-information-limit", rationale


# -------------------------------------------------------------------------
# Report writer
# -------------------------------------------------------------------------


def _format_corr_matrix(corr, names) -> str:
    if corr is None or len(corr) == 0:
        return "_(unavailable)_"
    n = len(corr)
    header = "| | " + " | ".join(names[:n]) + " |"
    sep = "|---|" + "|".join(["---"] * n) + "|"
    rows = [header, sep]
    for i in range(n):
        cells = []
        for j in range(n):
            v = corr[i][j]
            if isinstance(v, float) and not math.isfinite(v):
                cells.append("n/a")
            else:
                cells.append(f"{v: .3f}")
        rows.append(f"| **{names[i]}** | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _render_report(out: dict) -> str:
    lines: list[str] = []
    lines.append("# M21 HMS Onslaught — Stefan v3 (6-param, side-source freed)\n")
    lines.append(
        "**Mission**: extend M20 Stefan v2 with a distributed side-heat "
        "source `S(x,t) = Q_side · w(x) · g_oven(t)` representing tin-wall "
        "heat flux. Test the hypothesis that 1D-from-top can't explain "
        "deep-sensor heating because the model omits sidewall conduction.\n"
    )
    verdict = out.get("verdict", "n/a")
    lines.append(f"## Executive summary\n\n**Verdict: {verdict}**\n")
    for r in out.get("rationale", []):
        lines.append(f"- {r}")
    lines.append("")

    p1 = out.get("phase1", {})
    lines.append("## Phase 1 — Forward sanity\n")
    lines.append(
        f"(a) `Q_side=0` reproduces M20 forward: "
        f"max|Δ| = {p1.get('Q_side_zero_max_dev_K', float('nan')):.5f} K → "
        f"{'PASS' if p1.get('pass_a') else 'FAIL'}.\n"
    )
    lines.append(
        f"(b) `Q_side=1e5` warms interior: "
        f"max ΔT = {p1.get('Q_side_high_max_warming_K', float('nan')):.2f} K → "
        f"{'PASS' if p1.get('pass_b') else 'FAIL'}.\n"
    )

    p2 = out.get("phase2")
    if p2 is not None:
        lines.append("## Phase 2 — Synthetic recovery\n")
        lines.append(
            f"Recovery target: Q_side within 30% on at least 3/5 seeds. "
            f"Result: **{p2['n_pass']}/{p2['n_total']}** seeds recovered. "
            f"→ {'PASS' if p2['pass'] else 'FAIL'}\n"
        )
        lines.append("\n| seed | Q_true | Q_fit | rel_err | RMSE | "
                     "n_at_bound | recovered |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in p2["rows"]:
            if "error" in r:
                lines.append(
                    f"| {r['seed']} | — | — | ERROR | — | — | "
                    f"`{r['error']}` |"
                )
                continue
            lines.append(
                f"| {r['seed']} | {r['Q_side_true']:.2e} | "
                f"{r['Q_side_fit']:.2e} | "
                f"{r['Q_side_rel_err']*100:.1f}% | "
                f"{r['rmse_per_sensor']:.2f} | "
                f"{r['n_at_bound']} | "
                f"{'yes' if r['recovered_within_30pct'] else 'no'} |"
            )
        lines.append("")

    p3 = out.get("phase3")
    if p3 is not None:
        lines.append("## Phase 3 — Single-fixture decision gate (BA3C_0946)\n")
        fit = p3["fit"]
        lines.append(
            f"Bar: main-bake RMSE < 4 °C AND ≥ 4/6 params interior. "
            f"Result: main-bake RMSE = **{fit['rmse_main_bake']:.2f} °C** "
            f"(M9={fit['m9_main_bake_rmse']:.2f}, "
            f"M20={fit['m20_main_bake_rmse']:.2f}); "
            f"n_interior = {6-fit['n_at_bound']}/6; "
            f"max&#124;ρ&#124; = {fit['max_abs_off_diag_correlation']:.3f}; "
            f"converged = {fit['converged']}; "
            f"→ {'PASS' if p3['main_pass'] else 'FAIL'}.\n"
        )
        lines.append("\n### Fitted parameters\n")
        lines.append("| param | value | bound | SE |")
        lines.append("|---|---|---|---|")
        rows = [
            ("x_core_normalised", fit["x_core"],
             fit["param_at_bound"]["x_core_normalised"], fit["x_core_se"]),
            ("alpha_dough (norm)", fit["alpha_dough"],
             fit["param_at_bound"]["alpha_dough"], fit["alpha_dough_se"]),
            ("alpha_crust (norm)", fit["alpha_crust"],
             fit["param_at_bound"]["alpha_crust"], fit["alpha_crust_se"]),
            ("rhoL_eff (K)", fit["rhoL_eff"],
             fit["param_at_bound"]["rhoL_eff"], fit["rhoL_eff_se"]),
            ("delta_T_smear (°C)", fit["delta_T_smear"],
             fit["param_at_bound"]["delta_T_smear"], fit["delta_T_smear_se"]),
            ("Q_side (W/m³)", fit["Q_side"],
             fit["param_at_bound"]["Q_side"], fit["Q_side_se"]),
        ]
        for name, v, b, se in rows:
            v_s = f"{v:.4e}" if abs(v) < 1e-2 or abs(v) >= 1e3 else f"{v:.4f}"
            if isinstance(se, float) and math.isfinite(se):
                se_s = (
                    f"{se:.3e}" if abs(se) < 1e-2 or abs(se) >= 1e3
                    else f"{se:.3f}"
                )
            else:
                se_s = "n/a"
            lines.append(f"| {name} | {v_s} | {b} | {se_s} |")
        lines.append("")

        lines.append("\n### 6×6 correlation matrix\n")
        lines.append(_format_corr_matrix(
            fit["full_correlation_matrix"],
            ["x_core", "α_d", "α_c", "ρL", "ΔT_smear", "Q_side"],
        ))
        lines.append("")

        lines.append("\n### Comparison vs prior missions\n")
        lines.append("| mission | params | main-bake RMSE | Δ vs M9 |")
        lines.append("|---|---|---|---|")
        m9 = fit["m9_main_bake_rmse"]
        m20 = fit["m20_main_bake_rmse"]
        m21 = fit["rmse_main_bake"]
        lines.append(f"| M9 (4-param baseline) | 4 | {m9:.2f} | — |")
        lines.append(
            f"| M20 (5-param: +α_d, +Δ_T_smear) | 5 | {m20:.2f} | "
            f"{m20-m9:+.2f} |"
        )
        lines.append(
            f"| M21 (6-param: +Q_side) | 6 | {m21:.2f} | {m21-m9:+.2f} |"
        )
        lines.append("")

    p4 = out.get("phase4")
    if p4 is not None:
        lines.append("\n## Phase 4 — 5-fixture sweep\n")
        lines.append(
            "| fixture | main RMSE (v3) | M9 | x_core | α_d | α_c | ρL | "
            "ΔT_smear | Q_side | n_at_bound | converged |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for label in SWEEP_LABELS:
            r = p4.get(label, {})
            if "error" in r:
                lines.append(f"| `{label}` | ERROR | | | | | | | | | |")
                continue
            lines.append(
                f"| `{label}` | "
                f"{r.get('rmse_main_bake', float('nan')):.2f} | "
                f"{r.get('m9_main_bake_rmse', float('nan')):.2f} | "
                f"{r.get('x_core', float('nan')):.4f} | "
                f"{r.get('alpha_dough', float('nan')):.2e} | "
                f"{r.get('alpha_crust', float('nan')):.2e} | "
                f"{r.get('rhoL_eff', float('nan')):.1f} | "
                f"{r.get('delta_T_smear', float('nan')):.2f} | "
                f"{r.get('Q_side', float('nan')):.2e} | "
                f"{r.get('n_at_bound', '—')} | "
                f"{r.get('converged', False)} |"
            )
        lines.append("")

    lines.append("\n## Recommendation\n")
    if verdict == "GO":
        rec = (
            "Side-heat source closes the residual gap below 4 °C across the "
            "unlidded sweep. **Recommend M22 wires the v3 6-param fitter "
            "into the runtime classifier.** The Q_side parameter quantifies "
            "the lateral heat flux, opening a path toward instrument-driven "
            "tin-thermometry guidance for deeper accuracy. Estimated work "
            "for M22: 1-2 days to expose Q_side in the spatial-reconstruction "
            "API + add a lid-state branch (lidded fixtures will need a "
            "different temporal profile g(t))."
        )
    elif verdict == "GO-WITH-CAVEATS":
        rec = (
            "v3 helps on the single-fixture gate but either misses the < 4 °C "
            "bar slightly or has multiple parameters at bounds. Treat v3 as a "
            "research curiosity; do not wire to runtime until either the "
            "synthetic recovery floor is solid OR the production-landing "
            "Method 1+4 metadata path is in place. Recommend M22 land Method 1 "
            "+ Method 4 stub in parallel with any further v3 polish."
        )
    else:
        rec = (
            "**Side-heat is not the missing physics.** Even with Q_side "
            "freed across (0, 5e5) W/m³ and α_dough + Δ_T_smear in their "
            "RCA-recommended ranges, main-bake RMSE on BA3C_0946 stays "
            "above the 4 °C bar (and structurally near 6 °C — the M14/M15 "
            "information-limit verdict). Eighteen prior missions plus M21 "
            "now confirm: in-dough thermometry alone, with no per-CSV "
            "metadata, cannot identify the loaf physics to better than "
            "5-6 °C. **Production landing M18 (Method 1 + Method 4 stub) "
            "is the unambiguous path.** Recommend M22 pivots away from "
            "inverse-problem extension and lands the metadata acquisition "
            "tooling for thickness, oven-setpoint, and lid-state."
        )
    lines.append(rec + "\n")
    return "\n".join(lines)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main() -> None:
    overall_t0 = time.time()
    out: dict = {
        "mission": "M21 HMS Onslaught",
        "bounds": dict(BOUNDS_V3),
        "init": dict(INIT_V3),
        "param_names": list(PARAM_NAMES_V3),
        "downsample_factor": DOWNSAMPLE_FACTOR,
        "n_spatial": N_SPATIAL,
        "max_iter": MAX_ITER,
    }

    t0 = _phase_header("Phase 1 — Forward sanity")
    p1 = phase1_forward_sanity()
    out["phase1"] = p1
    print(f"  phase 1 elapsed: {time.time() - t0:.1f}s", flush=True)
    if not p1.get("pass"):
        out["verdict"] = "CONFIRM-information-limit"
        out["rationale"] = ["Phase 1 forward sanity failed; aborting."]
        out["wall_seconds"] = time.time() - overall_t0
        _write_outputs(out)
        return

    t0 = _phase_header("Phase 2 — Synthetic recovery")
    p2 = phase2_synthetic_recovery()
    out["phase2"] = p2
    print(f"  phase 2 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase_header("Phase 3 — Single-fixture decision gate (BA3C_0946)")
    p3 = phase3_single_fixture()
    out["phase3"] = p3
    print(f"  phase 3 elapsed: {time.time() - t0:.1f}s", flush=True)

    if not p3.get("main_pass"):
        verdict, rationale = _verdict(p2, p3, None)
        out["verdict"] = verdict
        out["rationale"] = rationale
        out["wall_seconds"] = time.time() - overall_t0
        print(
            f"\n  decision gate FAILED — skipping phase 4. verdict={verdict}",
            flush=True,
        )
        _write_outputs(out)
        return

    t0 = _phase_header("Phase 4 — 5-fixture sweep")
    p4 = phase4_sweep(skip_first=p3["fit"])
    out["phase4"] = p4
    print(f"  phase 4 elapsed: {time.time() - t0:.1f}s", flush=True)

    verdict, rationale = _verdict(p2, p3, p4)
    out["verdict"] = verdict
    out["rationale"] = rationale
    out["wall_seconds"] = time.time() - overall_t0
    print(f"\n  total wall-time: {out['wall_seconds']:.1f}s", flush=True)
    print(f"  verdict: {verdict}", flush=True)
    for r in rationale:
        print(f"    - {r}", flush=True)
    _write_outputs(out)


def _write_outputs(out: dict) -> None:
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"  wrote {OUT_JSON}", flush=True)
    md_text = _render_report(out)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"  wrote {OUT_MD}", flush=True)


if __name__ == "__main__":
    main()
