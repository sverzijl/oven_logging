"""HMS Resolute (M20) — Stefan v2 driver.

Phases:

1. **Forward sanity** — call ``solve_stefan_forward`` at the v2 default
   smear (5 °C); verify the output shape, finite values, and a smoother
   100 °C plateau than at smear=1.

2. **Single-fixture validation on BA3C_0946** — early-exit decision gate.
   Bar: main-bake RMSE < 4 °C AND ≤ 2 of the 5 params at bounds.

3. **Full sweep** (only if phase 2 passes) — 5 unlidded fixtures.

4. **LOO subset** (only if phase 3 passes) — BA3C_0946 holding out T1
   then T2; compare against M9 LOO baseline (T1=9.45, T2=7.40).

Outputs:

* ``tests/baselines/stefan_v2_research.json`` — full structured JSON.
* ``tests/baselines/stefan_v2_research.md`` — human-readable report.
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
from src.data.spatial_reconstruction.stefan_inverse_v2 import (  # noqa: E402
    BOUNDS_V2,
    INIT_V2,
    fit_stefan_inverse_v2,
)
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    SENSOR_NAMES,
    SENSOR_POSITIONS,
    _segmented_real_fixture,
)


DOWNSAMPLE_FACTOR = 4
N_SPATIAL = 30
MAX_ITER = 600

# M9 baseline numbers we compare against.
M9_MAIN_BAKE_RMSE = {
    "BA3C_0946": 5.76,
    "BA3C_1759_C0": 6.80,
    "BA3C_1759_C1": 7.95,
    "BA3C_1759_C2": 7.49,
    "100098DE_1351": 11.03,
}

# M9 LOO baseline on BA3C_0946 (from
# tests/baselines/loo_cross_validation.json, stefan_rows section).
M9_LOO_BA3C_0946 = {
    "T1": 9.45,
    "T2": 7.40,
}

# These five fixtures are the unlidded set per the M20 spec.
SWEEP_LABELS = ("BA3C_0946", "BA3C_1759_C0", "BA3C_1759_C1", "BA3C_1759_C2", "100098DE_1351")

# Pre-cached x_surface_continuous values (taken from M9 baseline JSON so
# the v2 fit is apples-to-apples vs M9 — same surface BC interpolation).
X_SURFACE_CACHED = {
    "BA3C_0946": 0.6786994367639527,
    "BA3C_1759_C0": 0.6786994367639527,
    "BA3C_1759_C1": 0.7177439275421984,
    "BA3C_1759_C2": 0.7131671056904703,
    "100098DE_1351": 0.7703681378329582,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(BASE_DIR, "baselines", "stefan_v2_research.json")
OUT_MD = os.path.join(BASE_DIR, "baselines", "stefan_v2_research.md")


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _segment_main_mask(n_t: int) -> np.ndarray:
    """Match the M10 main-bake window: indices in [0.10, 0.90) of the bake."""
    idx = np.arange(n_t)
    frac = idx / max(n_t - 1, 1)
    return (frac >= 0.10) & (frac < 0.90)


def _build_obs(df: pd.DataFrame, in_dough: list, x_surface_continuous: float):
    """Return (t_obs, T_obs, x_obs, T_surf_obs, T_initial) at downsample 4."""
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
    return t_obs, T_obs, x_obs, T_surf_obs, T_initial


def _main_bake_rmse_from_fit(
    df: pd.DataFrame, in_dough: list, x_surface_continuous: float, fit: dict
) -> tuple[float, float]:
    """Re-run the forward at the fitted params; return (rmse_full, rmse_main)."""
    t_obs, T_obs, x_obs, T_surf_obs, T_initial = _build_obs(
        df, in_dough, x_surface_continuous
    )
    T_pred = solve_stefan_forward(
        x_core=fit["x_core"],
        x_surface=x_surface_continuous,
        alpha_dough=fit["alpha_dough"],
        alpha_crust=fit["alpha_crust"],
        rhoL_eff=fit["rhoL_eff"],
        t_grid=t_obs,
        T_surface_series=T_surf_obs,
        T_initial=T_initial,
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
    """Verify ``solve_stefan_forward`` at smear=5 produces sensible output."""
    t = np.linspace(0.0, 1500.0, 200)
    surf = np.linspace(25.0, 200.0, 200)
    sample_x = np.array([0.0, 0.2, 0.4, 0.6])

    T1 = solve_stefan_forward(
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
        delta_T_smear=1.0,
    )
    T5 = solve_stefan_forward(
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
    finite_1 = bool(np.all(np.isfinite(T1)))
    finite_5 = bool(np.all(np.isfinite(T5)))
    # Final core temp should sit in [T_init, T_surface] for both.
    core1_final = float(T1[-1, 0])
    core5_final = float(T5[-1, 0])
    sanity_ok = (
        finite_1
        and finite_5
        and 24.0 <= core1_final <= 200.0
        and 24.0 <= core5_final <= 200.0
    )
    print(
        f"  forward smear=1 final core T={core1_final:.1f} °C; "
        f"smear=5 final core T={core5_final:.1f} °C; "
        f"finite_1={finite_1} finite_5={finite_5} → {'PASS' if sanity_ok else 'FAIL'}",
        flush=True,
    )
    return {
        "smear_1_final_core_T": core1_final,
        "smear_5_final_core_T": core5_final,
        "smear_1_finite": finite_1,
        "smear_5_finite": finite_5,
        "pass": bool(sanity_ok),
    }


# -------------------------------------------------------------------------
# Phase 2 — single-fixture validation on BA3C_0946
# -------------------------------------------------------------------------


def _fit_one_fixture(label: str) -> dict:
    """Run the v2 fitter on a single fixture and return the result + main-bake RMSE."""
    spec = next(s for s in REAL_FIXTURES if s["label"] == label)
    df = _segmented_real_fixture(spec)
    x_surface_continuous = X_SURFACE_CACHED[label]

    t0 = time.time()
    result = fit_stefan_inverse_v2(
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
    return out


def phase2_single_fixture() -> dict:
    """Validate on BA3C_0946. Decision gate enforced by ``main_pass`` flag."""
    label = "BA3C_0946"
    res = _fit_one_fixture(label)

    rmse_main = res["rmse_main_bake"]
    n_at_bound = res.get("n_at_bound", 0)
    main_pass = (rmse_main < 4.0) and (n_at_bound <= 2)

    print(
        f"  {label}: main-bake RMSE = {rmse_main:.2f} °C "
        f"(M9={res['m9_main_bake_rmse']:.2f}); "
        f"n_at_bound={n_at_bound}; converged={res['converged']}; "
        f"max|ρ|={res['max_abs_off_diag_correlation']:.3f}; "
        f"({res['fit_seconds']:.1f}s) → {'PASS' if main_pass else 'FAIL'}",
        flush=True,
    )
    print(
        f"  fitted params: x_core={res['x_core']:.4f} "
        f"alpha_dough={res['alpha_dough']:.3e} "
        f"alpha_crust={res['alpha_crust']:.3e} "
        f"rhoL_eff={res['rhoL_eff']:.2f} "
        f"delta_T_smear={res['delta_T_smear']:.2f}",
        flush=True,
    )
    print(f"  param_at_bound={res['param_at_bound']}", flush=True)
    return {
        "fit": res,
        "main_pass": bool(main_pass),
        "rmse_main_bar_C": 4.0,
        "n_at_bound_max_allowed": 2,
    }


# -------------------------------------------------------------------------
# Phase 3 — full sweep
# -------------------------------------------------------------------------


def phase3_sweep(skip_first: Optional[dict] = None) -> dict:
    """Fit each unlidded fixture in :data:`SWEEP_LABELS`. Reuse phase-2 result."""
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
# Phase 4 — LOO subset on BA3C_0946 (T1, T2 held out)
# -------------------------------------------------------------------------


def phase4_loo() -> dict:
    """Hold out T1 and T2 separately on BA3C_0946; compare main-bake RMSE.

    For each held-out sensor, refit on the remaining 4 in-dough sensors,
    then evaluate the held-out sensor's full-bake LOO RMSE.
    """
    label = "BA3C_0946"
    spec = next(s for s in REAL_FIXTURES if s["label"] == label)
    df = _segmented_real_fixture(spec)
    x_surface_continuous = X_SURFACE_CACHED[label]
    full_in_dough = list(spec["in_dough"])
    out = {"fixture": label}
    for held_out in ("T1", "T2"):
        train = [s for s in full_in_dough if s != held_out]
        t0 = time.time()
        try:
            r = fit_stefan_inverse_v2(
                df=df,
                in_dough_sensors=train,
                x_surface_continuous=x_surface_continuous,
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                max_iter=MAX_ITER,
            )
            fit_seconds = time.time() - t0
            # Now evaluate the held-out sensor.
            t_obs, _, _, T_surf_obs, T_initial = _build_obs(
                df, full_in_dough, x_surface_continuous
            )
            pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
            x_held = np.array([pos_map[held_out]])
            T_held_obs = df[held_out].to_numpy(dtype=float)
            t_full = df["Timestamp"].to_numpy(dtype=float)
            sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
            T_held_obs_ds = T_held_obs[sl]

            T_pred_held = solve_stefan_forward(
                x_core=r["x_core"],
                x_surface=x_surface_continuous,
                alpha_dough=r["alpha_dough"],
                alpha_crust=r["alpha_crust"],
                rhoL_eff=r["rhoL_eff"],
                t_grid=t_obs,
                T_surface_series=T_surf_obs,
                T_initial=T_initial,
                n_spatial=N_SPATIAL,
                sample_x=x_held,
                delta_T_smear=r["delta_T_smear"],
            )[:, 0]
            residual = T_pred_held - T_held_obs_ds
            loo_rmse = float(np.sqrt(np.mean(residual ** 2)))
            m9 = M9_LOO_BA3C_0946.get(held_out, float("nan"))
            rel_drop = (
                (m9 - loo_rmse) / m9 * 100.0
                if math.isfinite(m9) and m9 > 0
                else float("nan")
            )
            print(
                f"  LOO {held_out}: v2 LOO-RMSE = {loo_rmse:.2f} °C "
                f"(M9 = {m9:.2f}); rel drop = {rel_drop:+.1f}% "
                f"({fit_seconds:.1f}s)",
                flush=True,
            )
            out[held_out] = {
                "training_sensors": train,
                "held_out": held_out,
                "loo_rmse": loo_rmse,
                "m9_loo_rmse": m9,
                "rel_drop_pct": rel_drop,
                "fitted_params": {
                    "x_core": r["x_core"],
                    "alpha_dough": r["alpha_dough"],
                    "alpha_crust": r["alpha_crust"],
                    "rhoL_eff": r["rhoL_eff"],
                    "delta_T_smear": r["delta_T_smear"],
                },
                "param_at_bound": r["param_at_bound"],
                "n_at_bound": r["n_at_bound"],
                "converged": r["converged"],
                "n_iter": r["n_iter"],
                "fit_seconds": fit_seconds,
                "in_sample_rmse_per_sensor": r["rmse_per_sensor"],
            }
        except Exception as exc:
            out[held_out] = {
                "training_sensors": train,
                "held_out": held_out,
                "error": str(exc),
                "loo_rmse": float("nan"),
            }
            print(f"  LOO {held_out}: ERROR {exc}", flush=True)
    # Best drop across the two LOO conditions.
    drops = []
    for k in ("T1", "T2"):
        v = out.get(k, {})
        rd = v.get("rel_drop_pct")
        if isinstance(rd, float) and math.isfinite(rd):
            drops.append(rd)
    out["best_rel_drop_pct"] = max(drops) if drops else float("nan")
    return out


# -------------------------------------------------------------------------
# Verdict
# -------------------------------------------------------------------------


def _verdict(phase2: dict, phase3: Optional[dict], phase4: Optional[dict]) -> tuple[str, list[str]]:
    rationale = []
    p2_rmse = phase2["fit"]["rmse_main_bake"]
    rationale.append(
        f"Phase 2 single-fixture BA3C_0946 main-bake RMSE = {p2_rmse:.2f} °C "
        f"(M9 baseline {M9_MAIN_BAKE_RMSE['BA3C_0946']:.2f}; bar 4.0)."
    )
    n_b = phase2["fit"]["n_at_bound"]
    rationale.append(
        f"Phase 2 n_at_bound = {n_b} of 5 (max allowed 2)."
    )
    if not phase2.get("main_pass"):
        if p2_rmse >= 6.0:
            return "CONFIRM", rationale
        return "GO-WITH-CAVEATS", rationale
    if phase3 is None:
        return "GO-WITH-CAVEATS", rationale
    main_rmses = [
        v.get("rmse_main_bake", float("nan"))
        for v in phase3.values()
        if math.isfinite(v.get("rmse_main_bake", float("nan")))
    ]
    if not main_rmses:
        return "CONFIRM", rationale
    median_main = float(np.median(main_rmses))
    max_main = float(np.max(main_rmses))
    rationale.append(
        f"Phase 3 sweep: median main-bake RMSE = {median_main:.2f} °C, "
        f"max = {max_main:.2f} °C across {len(main_rmses)} fixtures (bar 4.0)."
    )
    if phase4 is not None:
        best_drop = phase4.get("best_rel_drop_pct", float("nan"))
        rationale.append(
            f"Phase 4 LOO: best held-out RMSE drop vs M9 = "
            f"{best_drop:+.1f}% (target ≥ 30%)."
        )
        loo_ok = (
            isinstance(best_drop, float) and math.isfinite(best_drop) and best_drop >= 30.0
        )
    else:
        loo_ok = False
    if median_main < 4.0 and max_main < 6.0 and loo_ok:
        return "GO", rationale
    if median_main < 6.0:
        return "GO-WITH-CAVEATS", rationale
    return "CONFIRM", rationale


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
    lines.append("# M20 HMS Resolute — Stefan v2 (5-param, α + smear free)\n")
    lines.append(
        "**Mission**: take M9 Stefan exactly as-is, free α_dough in (5e-7, 1e-5) m²/s "
        "and Δ_T_smear in (3, 10) °C. Single-fixture validation on BA3C_0946 first. "
        "Acceptance: main-bake RMSE < 4 °C with parameters interior.\n"
    )
    verdict = out.get("verdict", "n/a")
    lines.append(f"## Executive summary\n\n**Verdict: {verdict}**\n")
    for r in out.get("rationale", []):
        lines.append(f"- {r}")
    lines.append("")

    # Phase 1
    p1 = out["phase1"]
    lines.append("## Phase 1 — Forward sanity\n")
    lines.append(
        f"smear=1 final core T = {p1['smear_1_final_core_T']:.2f} °C "
        f"(finite={p1['smear_1_finite']}); "
        f"smear=5 final core T = {p1['smear_5_final_core_T']:.2f} °C "
        f"(finite={p1['smear_5_finite']}); "
        f"→ {'PASS' if p1['pass'] else 'FAIL'}.\n"
    )

    # Phase 2
    lines.append("## Phase 2 — Single-fixture BA3C_0946 (decision gate)\n")
    p2 = out["phase2"]
    fit = p2["fit"]
    lines.append(
        f"Bar: main-bake RMSE < 4 °C AND ≤ 2 of 5 params at bounds. "
        f"Result: main-bake RMSE = **{fit['rmse_main_bake']:.2f} °C** "
        f"(M9 baseline {fit['m9_main_bake_rmse']:.2f}); "
        f"n_at_bound = {fit['n_at_bound']} of 5; "
        f"max&#124;ρ&#124; = {fit['max_abs_off_diag_correlation']:.3f}; "
        f"converged = {fit['converged']}; "
        f"→ {'PASS' if p2['main_pass'] else 'FAIL'}.\n"
    )
    lines.append("\n### Fitted parameters\n")
    lines.append("| param | value | bound | SE |")
    lines.append("|---|---|---|---|")
    rows = [
        ("x_core_normalised", fit["x_core"], fit["param_at_bound"]["x_core_normalised"], fit["x_core_se"]),
        ("alpha_dough (m²/s_norm)", fit["alpha_dough"], fit["param_at_bound"]["alpha_dough"], fit["alpha_dough_se"]),
        ("alpha_crust (m²/s_norm)", fit["alpha_crust"], fit["param_at_bound"]["alpha_crust"], fit["alpha_crust_se"]),
        ("rhoL_eff (K)", fit["rhoL_eff"], fit["param_at_bound"]["rhoL_eff"], fit["rhoL_eff_se"]),
        ("delta_T_smear (°C)", fit["delta_T_smear"], fit["param_at_bound"]["delta_T_smear"], fit["delta_T_smear_se"]),
    ]
    for name, v, b, se in rows:
        if isinstance(v, float):
            v_s = f"{v:.4e}" if abs(v) < 1e-2 or abs(v) >= 1e3 else f"{v:.4f}"
        else:
            v_s = str(v)
        if isinstance(se, float) and math.isfinite(se):
            se_s = f"{se:.3e}" if abs(se) < 1e-2 or abs(se) >= 1e3 else f"{se:.3f}"
        else:
            se_s = "n/a"
        lines.append(f"| {name} | {v_s} | {b} | {se_s} |")
    lines.append("")

    lines.append("\n### 5×5 correlation matrix\n")
    lines.append(_format_corr_matrix(
        fit["full_correlation_matrix"],
        ["x_core", "α_d", "α_c", "ρL", "ΔT_smear"],
    ))
    lines.append("")

    # Phase 3
    if "phase3" in out and out["phase3"] is not None:
        lines.append("\n## Phase 3 — 5-fixture sweep\n")
        lines.append(
            "| fixture | main-bake RMSE (v2) | main-bake RMSE (M9) | "
            "x_core | α_d | α_c | ρL | Δ_T_smear | n_at_bound | max&#124;ρ&#124; | "
            "converged |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|---|---|---|"
        )
        for label in SWEEP_LABELS:
            r = out["phase3"].get(label, {})
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
                f"{r.get('n_at_bound', '—')} | "
                f"{r.get('max_abs_off_diag_correlation', float('nan')):.3f} | "
                f"{r.get('converged', False)} |"
            )
        lines.append("")

    # Phase 4 LOO
    if "phase4" in out and out["phase4"] is not None:
        lines.append("\n## Phase 4 — LOO subset on BA3C_0946\n")
        lines.append("| held out | v2 LOO RMSE | M9 LOO RMSE | rel drop |")
        lines.append("|---|---|---|---|")
        for held in ("T1", "T2"):
            v = out["phase4"].get(held, {})
            if "error" in v:
                lines.append(f"| {held} | ERROR | {M9_LOO_BA3C_0946.get(held, float('nan')):.2f} | — |")
                continue
            lines.append(
                f"| {held} | {v.get('loo_rmse', float('nan')):.2f} | "
                f"{v.get('m9_loo_rmse', float('nan')):.2f} | "
                f"{v.get('rel_drop_pct', float('nan')):+.1f}% |"
            )
        lines.append("")

    # Verdict footer
    lines.append("\n## Recommendation\n")
    if verdict == "GO":
        rec = (
            "Main-bake RMSE consistently below 4 °C across the unlidded sweep, "
            "with at least one LOO held-out RMSE dropping ≥ 30% vs M9. "
            "**Recommend M21 wires the 5-param Stefan v2 inverse into the "
            "runtime classifier**, replacing the M9 4-param fitter. The smear "
            "and freed α_dough together close the depth-dependent residual "
            "signature M10 flagged on BA3C_0946."
        )
    elif verdict == "GO-WITH-CAVEATS":
        rec = (
            "Stefan v2 improves on M9 — main-bake RMSE drops below 6 °C — but "
            "either the < 4 °C bar is missed on some fixtures, or LOO drop is "
            "below the 30% target, or parameters are at bounds on multiple "
            "fixtures. Recommend treating Stefan v2 as a *research-only* "
            "improvement; do not wire to runtime until a fixture-stratified "
            "follow-up identifies which fixtures need a model-class change "
            "(lid pathology, geometry mismatch). M21 should pursue Method 4 "
            "(loaf-thickness metadata) in parallel."
        )
    else:
        rec = (
            "Even with α_dough and Δ_T_smear freed across RCA-recommended "
            "bounds, main-bake RMSE remains above 6 °C. The structural "
            "information limit verdict from M14/M15 survives a properly-"
            "formulated test: in-dough thermometry alone cannot identify "
            "the loaf physics. **Method 4 (per-CSV loaf-thickness, oven-"
            "setpoint, lid-state metadata) is the only remaining path.** "
            "M21 should pivot away from inverse-problem extension and "
            "toward Method 4 acquisition tooling."
        )
    lines.append(rec + "\n")
    return "\n".join(lines)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main() -> None:
    overall_t0 = time.time()
    out: dict = {
        "mission": "M20 HMS Resolute",
        "bounds": dict(BOUNDS_V2),
        "init": dict(INIT_V2),
        "downsample_factor": DOWNSAMPLE_FACTOR,
        "n_spatial": N_SPATIAL,
        "max_iter": MAX_ITER,
    }

    # Phase 1
    t0 = _phase_header("Phase 1 — Forward sanity")
    p1 = phase1_forward_sanity()
    out["phase1"] = p1
    print(f"  phase 1 elapsed: {time.time() - t0:.1f}s", flush=True)
    if not p1.get("pass"):
        out["verdict"] = "CONFIRM"
        out["rationale"] = ["Phase 1 forward sanity failed; aborting."]
        out["wall_seconds"] = time.time() - overall_t0
        _write_outputs(out)
        return

    # Phase 2
    t0 = _phase_header("Phase 2 — Single-fixture validation (BA3C_0946)")
    p2 = phase2_single_fixture()
    out["phase2"] = p2
    print(f"  phase 2 elapsed: {time.time() - t0:.1f}s", flush=True)

    if not p2.get("main_pass"):
        verdict, rationale = _verdict(p2, None, None)
        out["verdict"] = verdict
        out["rationale"] = rationale
        out["wall_seconds"] = time.time() - overall_t0
        print(
            f"\n  decision gate FAILED — skipping phases 3 and 4. "
            f"verdict={verdict}",
            flush=True,
        )
        _write_outputs(out)
        return

    # Phase 3
    t0 = _phase_header("Phase 3 — 5-fixture sweep")
    p3 = phase3_sweep(skip_first=p2["fit"])
    out["phase3"] = p3
    print(f"  phase 3 elapsed: {time.time() - t0:.1f}s", flush=True)

    # Phase 4
    t0 = _phase_header("Phase 4 — LOO subset on BA3C_0946 (T1, T2)")
    p4 = phase4_loo()
    out["phase4"] = p4
    print(f"  phase 4 elapsed: {time.time() - t0:.1f}s", flush=True)

    # Verdict
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
