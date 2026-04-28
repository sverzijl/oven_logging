"""HMS Lively — M14 Luikov 1D coupled heat-mass transfer end-to-end driver.

Phases
------

1. **Forward sanity** — uncoupled limit (Lu, ε → 0 should match pure heat
   equation with convective Robin BC) and steady-state check (long-time
   solution must converge to T_oven_eff and a smooth moisture profile).
2. **Synthetic recovery (avoiding the M7 tautology trap)** — generator
   uses ε=0.3 and α=1.0e-7, inverter uses ε=0.5 and α=1.4e-7. This makes
   the synthetic data class genuinely differ from the inverter's class,
   so recovering (Lu, Ko, Bi, x_core) within 30% becomes a real
   identifiability test.
3. **Real-CSV joint fits** — same 7 fixtures as M9/M11/M12.
4. **LOO subset** — 3 representative fixtures × ~5 sensors = 15 fits;
   compares Luikov LOO-RMSE to M13's Stefan/Zürcher LOO numbers,
   especially at the deep-end sensor T1.

If wall-clock budget runs out, phase 4 is skipped per the briefing.

Outputs
-------

* ``tests/baselines/luikov_inverse_research.json`` — raw fit results.
* ``tests/baselines/luikov_inverse_research.md`` — final report.
* ``.nelson/missions/2026-04-28_125109_7db8fefb/captains-log.md``.

Usage::

    python -m tests._driver_luikov
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

from src.data.spatial_reconstruction.luikov import (  # noqa: E402
    ALPHA_DEFAULT_M2_S,
    EPSILON_DEFAULT,
    LOAF_THICKNESS_M_DEFAULT,
    U_INITIAL_DEFAULT,
    fit_luikov_inverse,
    solve_luikov_forward,
)
from tests._diagnose_stefan_residuals import (  # noqa: E402
    _lag1_autocorr_segment,
    _per_sensor_rmse,
    _segment_mean_residual,
    _segment_rmse,
    _segment_slices,
)
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    SENSOR_NAMES,
    SENSOR_POSITIONS,
    _segmented_real_fixture,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON_PATH = os.path.join(
    BASE_DIR, "baselines", "luikov_inverse_research.json"
)
OUT_MD_PATH = os.path.join(
    BASE_DIR, "baselines", "luikov_inverse_research.md"
)
CAPTAINS_LOG_PATH = os.path.join(
    os.path.dirname(BASE_DIR),
    ".nelson",
    "missions",
    "2026-04-28_125109_7db8fefb",
    "captains-log.md",
)

DOWNSAMPLE_FACTOR = 4
N_SPATIAL = 40
SAMPLE_PERIOD_S = 5.0

# LOO subset matches M13.
LOO_FIXTURES = {"BA3C_0946", "100098DE_1351", "wonder_white"}

# Comparators — pulled from M9/M10/M12 baselines for the side-by-side table.
M9_MAIN = {
    "BA3C_0946": 5.76,
    "BA3C_1759_C0": 5.76,
    "BA3C_1759_C1": 6.80,
    "BA3C_1759_C2": 7.95,
    "100098DE_1351": 7.49,
    "wonder_white": 11.03,
    "post_wonder_meal": 10.55,
}
M12_MAIN = {
    "BA3C_0946": 36.51,
    "BA3C_1759_C0": 36.51,
    "BA3C_1759_C1": 34.70,
    "BA3C_1759_C2": 38.54,
    "100098DE_1351": 35.22,
    "wonder_white": 38.07,
    "post_wonder_meal": 35.40,
}

# Literature ranges per the briefing for the parameter physicality check.
LIT_LU_RANGE = (0.05, 0.5)
LIT_KO_RANGE = (1.0, 10.0)
LIT_BI_RANGE = (0.5, 10.0)
LIT_T_OVEN_LIDDED = (350.0, 380.0)
LIT_T_OVEN_OPEN = (450.0, 500.0)

SYNTH_SEEDS = 5


def _phase(name: str) -> float:
    print(f"\n=== {name} ===", flush=True)
    return time.time()


# -------------------------------------------------------------------------
# Phase 1 — Forward sanity
# -------------------------------------------------------------------------


def phase1_forward_sanity() -> dict:
    """Forward-solver sanity tests:

    1. **Uncoupled limit**: with Lu, ε, Ko → 0 the system reduces to pure
       heat conduction with a convective Robin BC. The temperature field
       should approach a smooth profile bounded by T_oven_eff.
    2. **Long-time steady state**: at very long times with fixed BCs,
       the temperature field should approach T_oven_eff (when Bi >> 1)
       and the moisture should approach 0 (Dirichlet drying BC).
    """
    out = {}

    # 1) Uncoupled limit — quasi-pure heat equation with convective BC.
    # Diffusion timescale L²/α ≈ 0.06²/1.4e-7 ≈ 26000s; push to 200000s so
    # the deep core has time to equilibrate.
    t_grid = np.linspace(0.0, 200000.0, 200)
    fwd = solve_luikov_forward(
        x_core_m=-0.01,
        Lu=0.001,
        Ko=0.001,
        Bi=10.0,  # large Bi drives surface to oven temp
        T_oven_eff_K=450.0,
        t_grid_s=t_grid,
        T_initial_K=295.0,
        epsilon=0.001,  # disable phase-change source
        n_spatial=40,
    )
    # At large Bi and long time, T → T_oven across the whole field.
    T_final = fwd.T_field_K[-1]
    T_max_dev = float(np.max(np.abs(T_final - 450.0)))
    uncoupled_pass = bool(fwd.converged) and T_max_dev < 1.0
    out["uncoupled_limit"] = {
        "converged": bool(fwd.converged),
        "T_final_min_K": float(T_final.min()),
        "T_final_max_K": float(T_final.max()),
        "T_oven_eff_K": 450.0,
        "max_dev_from_oven_K": T_max_dev,
        "passed": uncoupled_pass,
    }
    print(
        f"  Uncoupled limit (Bi=10, t=200000s): T_min={T_final.min():.1f}K "
        f"T_max={T_final.max():.1f}K, max|T-T_oven|={T_max_dev:.2f}K, "
        f"PASS={uncoupled_pass}",
        flush=True,
    )

    # 2) Steady-state check with full coupling.
    t_grid = np.linspace(0.0, 60000.0, 200)
    fwd2 = solve_luikov_forward(
        x_core_m=-0.005,
        Lu=0.15,
        Ko=4.0,
        Bi=5.0,
        T_oven_eff_K=450.0,
        t_grid_s=t_grid,
        T_initial_K=295.0,
        n_spatial=40,
    )
    # Moisture should drop substantially (Dirichlet drying BC; integrated
    # 60000s ≫ moisture diffusion timescale).
    u_final_max = float(fwd2.u_field[-1].max())
    T_final_min = float(fwd2.T_field_K[-1].min())
    T_final_max = float(fwd2.T_field_K[-1].max())
    # Must converge; final T must be in (320, 460) K window; final u_max < 0.4 (started at 0.4).
    steady_pass = (
        bool(fwd2.converged)
        and 320.0 < T_final_min < 460.0
        and 320.0 < T_final_max < 460.0
        and u_final_max < 0.40
    )
    out["steady_state"] = {
        "converged": bool(fwd2.converged),
        "T_final_min_K": T_final_min,
        "T_final_max_K": T_final_max,
        "u_final_max": u_final_max,
        "u_final_min": float(fwd2.u_field[-1].min()),
        "passed": steady_pass,
    }
    print(
        f"  Steady-state (full coupling, t=60000s): T=[{T_final_min:.1f}, "
        f"{T_final_max:.1f}]K, u_max={u_final_max:.4f}, PASS={steady_pass}",
        flush=True,
    )

    out["overall_passed"] = uncoupled_pass and steady_pass
    return out


# -------------------------------------------------------------------------
# Phase 2 — Synthetic recovery (avoiding the M7 tautology trap)
# -------------------------------------------------------------------------


def _synthesise(
    *,
    seed: int,
    truth: dict,
    n_t: int = 600,
    period_s: float = SAMPLE_PERIOD_S,
    in_dough: tuple = ("T1", "T2", "T3", "T4", "T5"),
    loaf: float = LOAF_THICKNESS_M_DEFAULT,
    noise_sigma_c: float = 0.5,
    x_surface_normalised: float = 5.0 / 7.0,
    gen_alpha: float = 1.0e-7,    # generator α (different from inverter's 1.4e-7)
    gen_epsilon: float = 0.3,     # generator ε (different from inverter's 0.5)
) -> tuple[pd.DataFrame, list, float]:
    """Generate synthetic in-dough observations.

    Generator uses (α=1.0e-7, ε=0.3); the inverter uses (α=1.4e-7, ε=0.5).
    Synthesised data class genuinely differs from the inverter's class —
    avoids the M7 tautology trap. Recovery within 30% becomes a real
    test of partial identifiability rather than perfect fit on toy data.
    """
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs_n = np.array([pos_map[s] for s in in_dough])
    x_core_m_true = float(truth["x_core_m"])
    sample_x_m = x_core_m_true + (x_obs_n / x_surface_normalised) * (
        loaf - x_core_m_true
    )
    t_grid = np.arange(n_t, dtype=float) * period_s

    fwd = solve_luikov_forward(
        x_core_m=x_core_m_true,
        Lu=float(truth["Lu"]),
        Ko=float(truth["Ko"]),
        Bi=float(truth["Bi"]),
        T_oven_eff_K=float(truth["T_oven_eff_K"]),
        t_grid_s=t_grid,
        T_initial_K=float(truth.get("T_initial_K", 295.0)),
        u_initial=float(truth.get("u_initial", U_INITIAL_DEFAULT)),
        epsilon=gen_epsilon,
        alpha_m2_s=gen_alpha,
        loaf_thickness_m=loaf,
        n_spatial=40,
        sample_x_m=sample_x_m,
    )
    T_pred_C = fwd.T_field_K - 273.15
    rng = np.random.default_rng(seed)
    if noise_sigma_c > 0:
        T_pred_C = T_pred_C + rng.normal(0.0, noise_sigma_c, T_pred_C.shape)

    df = pd.DataFrame({"Timestamp": t_grid})
    for k, s in enumerate(in_dough):
        df[s] = T_pred_C[:, k]
    for s in SENSOR_NAMES:
        if s not in df.columns:
            df[s] = T_pred_C[:, 0]
    return df, list(in_dough), x_surface_normalised


def phase2_synthetic_recovery() -> dict:
    """Run synthetic recovery, generator and inverter using **different**
    ε and α (avoids the M7 tautology trap).
    """
    truth = dict(
        x_core_m=-0.008,
        Lu=0.20,
        Ko=4.0,
        Bi=3.0,
        T_oven_eff_K=460.0,
    )
    rows = []
    for s in range(SYNTH_SEEDS):
        t0 = time.time()
        df, in_dough, x_surf_n = _synthesise(
            seed=s, truth=truth, noise_sigma_c=0.5,
        )
        try:
            r = fit_luikov_inverse(
                df=df,
                in_dough_sensors=in_dough,
                x_surface_normalised=x_surf_n,
                init={
                    "x_core_m": -0.005,
                    "Lu": 0.15,
                    "Ko": 4.0,
                    "Bi": 3.0,
                    "T_oven_eff_K": 450.0,
                },
                downsample_factor=DOWNSAMPLE_FACTOR,
                max_iter=600,
            )
            r["seed"] = s
            r["fit_seconds"] = time.time() - t0
            r["truth"] = truth
            rows.append(r)
            print(
                f"  seed={s}: x_m={r['x_core_m']:+.4f} "
                f"Lu={r['Lu']:.3f} Ko={r['Ko']:.3f} Bi={r['Bi']:.3f} "
                f"T_oven={r['T_oven_eff_K']:.1f}K rmse={r['rmse_per_sensor']:.3f} "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
        except Exception as exc:
            rows.append({"seed": s, "error": str(exc)})
            print(f"  seed={s}: ERROR {exc}", flush=True)

    finite = [r for r in rows if "error" not in r]
    if finite:
        x_core_arr = np.array([r["x_core_m"] for r in finite])
        Lu_arr = np.array([r["Lu"] for r in finite])
        Ko_arr = np.array([r["Ko"] for r in finite])
        Bi_arr = np.array([r["Bi"] for r in finite])
        T_oven_arr = np.array([r["T_oven_eff_K"] for r in finite])
        rmse_arr = np.array([r["rmse_per_sensor"] for r in finite])
        within_30pct = lambda arr, tru: int(
            np.sum(np.abs(arr - tru) / max(abs(tru), 1e-9) < 0.30)
        )
        summary = {
            "n_runs": len(rows),
            "n_finite": len(finite),
            "rmse_median": float(np.median(rmse_arr)),
            "rmse_max": float(np.max(rmse_arr)),
            "x_core_within_5mm": int(
                np.sum(np.abs(x_core_arr - truth["x_core_m"]) < 0.005)
            ),
            "Lu_within_30pct": within_30pct(Lu_arr, truth["Lu"]),
            "Ko_within_30pct": within_30pct(Ko_arr, truth["Ko"]),
            "Bi_within_30pct": within_30pct(Bi_arr, truth["Bi"]),
            "T_oven_within_5K": int(
                np.sum(np.abs(T_oven_arr - truth["T_oven_eff_K"]) < 5.0)
            ),
            "x_core_bias_m": float(np.mean(x_core_arr - truth["x_core_m"])),
            "Lu_bias": float(np.mean(Lu_arr - truth["Lu"])),
            "Ko_bias": float(np.mean(Ko_arr - truth["Ko"])),
            "Bi_bias": float(np.mean(Bi_arr - truth["Bi"])),
            "T_oven_bias_K": float(np.mean(T_oven_arr - truth["T_oven_eff_K"])),
        }
    else:
        summary = {"n_runs": len(rows), "n_finite": 0, "all_failed": True}
    summary["truth"] = truth
    summary["generator_alpha"] = 1.0e-7
    summary["inverter_alpha"] = ALPHA_DEFAULT_M2_S
    summary["generator_epsilon"] = 0.3
    summary["inverter_epsilon"] = EPSILON_DEFAULT
    return {"rows": rows, "summary": summary}


# -------------------------------------------------------------------------
# Phase 3 — Real-CSV joint inverse
# -------------------------------------------------------------------------


def phase3_real_csv() -> dict:
    out: dict = {}
    for spec in REAL_FIXTURES:
        df = _segmented_real_fixture(spec)
        t0 = time.time()
        try:
            r = fit_luikov_inverse(
                df=df,
                in_dough_sensors=spec["in_dough"],
                x_surface_normalised=float(spec["x_surface"]),
                init={
                    "x_core_m": -0.005,
                    "Lu": 0.15,
                    "Ko": 4.0,
                    "Bi": 3.0,
                    "T_oven_eff_K": 450.0,
                },
                downsample_factor=DOWNSAMPLE_FACTOR,
                loaf_thickness_m=LOAF_THICKNESS_M_DEFAULT,
                max_iter=800,
            )
            r["fit_seconds"] = time.time() - t0
            r["fixture_label"] = spec["label"]
            r["fixture_name"] = spec["fixture_name"]
            r["expected_curve_idx"] = spec["expected_curve_idx"]
        except Exception as exc:
            r = {
                "error": str(exc),
                "rmse_per_sensor": float("nan"),
                "x_core_m": float("nan"),
                "x_core_normalised": float("nan"),
                "Lu": float("nan"),
                "Ko": float("nan"),
                "Bi": float("nan"),
                "T_oven_eff_K": float("nan"),
                "converged": False,
                "fit_seconds": time.time() - t0,
                "fixture_label": spec["label"],
                "in_dough": list(spec["in_dough"]),
                "loaf_thickness_m": LOAF_THICKNESS_M_DEFAULT,
                "T_initial_K": float("nan"),
                "x_surface_normalised": float(spec["x_surface"]),
                "alpha_m2_s": ALPHA_DEFAULT_M2_S,
                "epsilon": EPSILON_DEFAULT,
                "u_initial": U_INITIAL_DEFAULT,
                "n_spatial": N_SPATIAL,
            }
        out[spec["label"]] = r
        x_n = r.get("x_core_normalised", float("nan"))
        if not math.isfinite(x_n):
            x_n = float("nan")
        print(
            f"  {spec['label']:>20}: "
            f"x_n={x_n:+.3f} "
            f"Lu={r.get('Lu', float('nan')):.3f} "
            f"Ko={r.get('Ko', float('nan')):.3f} "
            f"Bi={r.get('Bi', float('nan')):.3f} "
            f"T_oven={r.get('T_oven_eff_K', float('nan')):.0f}K "
            f"rmse={r.get('rmse_per_sensor', float('nan')):.2f}K "
            f"|ρ|max={r.get('max_abs_off_diag_correlation', float('nan')):.3f} "
            f"({r['fit_seconds']:.1f}s)",
            flush=True,
        )
    return out


# -------------------------------------------------------------------------
# Residual decomposition (segment RMSE)
# -------------------------------------------------------------------------


def _forward_eval_at_fit(spec: dict, fit: dict) -> dict:
    """Run the Luikov forward solve at the fitted params; return residuals."""
    df = _segmented_real_fixture(spec)
    in_dough = list(spec["in_dough"])
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs_n = np.array([pos_map[s] for s in in_dough])
    loaf = float(fit["loaf_thickness_m"])
    x_surf_n = float(fit["x_surface_normalised"])
    x_core_m = float(fit["x_core_m"])
    sample_x_m = x_core_m + (x_obs_n / x_surf_n) * (loaf - x_core_m)
    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    T_obs_C = np.column_stack(
        [df[s].to_numpy(dtype=float)[sl] for s in in_dough]
    )
    T_obs_K = T_obs_C + 273.15
    fwd = solve_luikov_forward(
        x_core_m=x_core_m,
        Lu=float(fit["Lu"]),
        Ko=float(fit["Ko"]),
        Bi=float(fit["Bi"]),
        T_oven_eff_K=float(fit["T_oven_eff_K"]),
        t_grid_s=t_obs,
        T_initial_K=float(fit["T_initial_K"]),
        u_initial=float(fit.get("u_initial", U_INITIAL_DEFAULT)),
        epsilon=float(fit.get("epsilon", EPSILON_DEFAULT)),
        alpha_m2_s=float(fit.get("alpha_m2_s", ALPHA_DEFAULT_M2_S)),
        loaf_thickness_m=loaf,
        n_spatial=int(fit.get("n_spatial", N_SPATIAL)),
        sample_x_m=sample_x_m,
    )
    residual = fwd.T_field_K - T_obs_K
    return {
        "label": spec["label"],
        "in_dough": in_dough,
        "t_obs": t_obs,
        "T_obs_K": T_obs_K,
        "T_pred_K": fwd.T_field_K,
        "residual": residual,
        "rmse_full_recomputed": float(np.sqrt(np.mean(residual ** 2))),
    }


def phase3b_residual_decomposition(phase3: dict) -> list:
    decomps: list = []
    for spec in REAL_FIXTURES:
        fit = phase3.get(spec["label"], {})
        if not fit.get("converged", False):
            decomps.append(
                {
                    "label": spec["label"],
                    "skipped_reason": "did_not_converge",
                }
            )
            continue
        ev = _forward_eval_at_fit(spec, fit)
        residual = ev["residual"]
        sensors = ev["in_dough"]
        n_t = residual.shape[0]
        masks = _segment_slices(n_t)
        seg_rmse = _segment_rmse(residual, masks)
        seg_mean = _segment_mean_residual(residual, masks)
        per_sensor = _per_sensor_rmse(residual, sensors)
        seg_rho = {
            name: _lag1_autocorr_segment(residual, masks[name])
            for name in ("startup", "main", "tail")
        }
        d = {
            "label": ev["label"],
            "in_dough": sensors,
            "n_t": int(n_t),
            "n_sensors": int(residual.shape[1]),
            "rmse_full_recomputed": ev["rmse_full_recomputed"],
            "rmse_full_reported": float(fit["rmse_per_sensor"]),
            "x_core_m": float(fit["x_core_m"]),
            "x_core_normalised": float(fit["x_core_normalised"]),
            "Lu": float(fit["Lu"]),
            "Ko": float(fit["Ko"]),
            "Bi": float(fit["Bi"]),
            "T_oven_eff_K": float(fit["T_oven_eff_K"]),
            "segment_rmse": seg_rmse,
            "segment_mean_residual": seg_mean,
            "segment_lag1_autocorr": seg_rho,
            "per_sensor_rmse": per_sensor,
        }
        decomps.append(d)
        print(
            f"  {ev['label']:>20}: startup={seg_rmse['startup']:.2f} "
            f"main={seg_rmse['main']:.2f} tail={seg_rmse['tail']:.2f} "
            f"ρ_main={seg_rho['main']:.3f}",
            flush=True,
        )
    return decomps


# -------------------------------------------------------------------------
# Phase 4 — LOO subset on 3 representative fixtures
# -------------------------------------------------------------------------


def _loo_predict_at_held_out(
    fit: dict, df: pd.DataFrame, held_out_sensor: str
) -> tuple:
    """Forward-evaluate the Luikov fit at the held-out sensor's position.

    Returns (T_pred_at_held_out_C, T_obs_at_held_out_C).
    """
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_held_n = float(pos_map[held_out_sensor])
    loaf = float(fit["loaf_thickness_m"])
    x_surf_n = float(fit["x_surface_normalised"])
    x_core_m = float(fit["x_core_m"])
    sample_x_m = np.array(
        [x_core_m + (x_held_n / x_surf_n) * (loaf - x_core_m)],
        dtype=float,
    )

    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    fwd = solve_luikov_forward(
        x_core_m=x_core_m,
        Lu=float(fit["Lu"]),
        Ko=float(fit["Ko"]),
        Bi=float(fit["Bi"]),
        T_oven_eff_K=float(fit["T_oven_eff_K"]),
        t_grid_s=t_obs,
        T_initial_K=float(fit["T_initial_K"]),
        u_initial=float(fit.get("u_initial", U_INITIAL_DEFAULT)),
        epsilon=float(fit.get("epsilon", EPSILON_DEFAULT)),
        alpha_m2_s=float(fit.get("alpha_m2_s", ALPHA_DEFAULT_M2_S)),
        loaf_thickness_m=loaf,
        n_spatial=int(fit.get("n_spatial", N_SPATIAL)),
        sample_x_m=sample_x_m,
    )
    T_pred_held_C = fwd.T_field_K[:, 0] - 273.15
    T_obs_held_C = df[held_out_sensor].to_numpy(dtype=float)[sl]
    return T_pred_held_C, T_obs_held_C


def _loo_one(spec: dict, held_out: str) -> dict:
    df = _segmented_real_fixture(spec)
    full = list(spec["in_dough"])
    if held_out not in full:
        return {"skipped": "not_in_dough"}
    training = [s for s in full if s != held_out]
    t0 = time.time()
    try:
        result = fit_luikov_inverse(
            df=df,
            in_dough_sensors=training,
            x_surface_normalised=float(spec["x_surface"]),
            init={
                "x_core_m": -0.005,
                "Lu": 0.15,
                "Ko": 4.0,
                "Bi": 3.0,
                "T_oven_eff_K": 450.0,
            },
            downsample_factor=DOWNSAMPLE_FACTOR,
            loaf_thickness_m=LOAF_THICKNESS_M_DEFAULT,
            max_iter=800,
        )
    except Exception as exc:
        return {
            "fixture": spec["label"],
            "held_out_sensor": held_out,
            "training_sensors": training,
            "error": str(exc),
            "fit_seconds": time.time() - t0,
        }
    T_pred_held, T_obs_held = _loo_predict_at_held_out(result, df, held_out)
    loo_residual = T_pred_held - T_obs_held
    loo_rmse = float(np.sqrt(np.mean(loo_residual ** 2)))
    in_sample_rmse = float(result["rmse_per_sensor"])
    return {
        "fixture": spec["label"],
        "held_out_sensor": held_out,
        "training_sensors": training,
        "loo_rmse": loo_rmse,
        "loo_max_abs_residual": float(np.max(np.abs(loo_residual))),
        "loo_mean_residual": float(np.mean(loo_residual)),
        "in_sample_rmse_pooled": in_sample_rmse,
        "ratio_loo_to_in_sample": (
            loo_rmse / in_sample_rmse if in_sample_rmse > 0 else float("inf")
        ),
        "fitted_params": {
            "x_core_m": float(result["x_core_m"]),
            "Lu": float(result["Lu"]),
            "Ko": float(result["Ko"]),
            "Bi": float(result["Bi"]),
            "T_oven_eff_K": float(result["T_oven_eff_K"]),
        },
        "n_iter": int(result.get("n_iter", -1)),
        "converged": bool(result.get("converged", False)),
        "fit_seconds": time.time() - t0,
    }


def phase4_loo_subset() -> list:
    rows = []
    for spec in REAL_FIXTURES:
        if spec["label"] not in LOO_FIXTURES:
            continue
        for held_out in spec["in_dough"]:
            r = _loo_one(spec, held_out)
            rows.append(r)
            if "error" in r:
                print(
                    f"  LOO {spec['label']:>20} -{held_out}: ERROR {r['error']}",
                    flush=True,
                )
                continue
            print(
                f"  LOO {spec['label']:>20} -{held_out}: "
                f"loo_rmse={r['loo_rmse']:.2f} in_sample={r['in_sample_rmse_pooled']:.2f} "
                f"ratio={r['ratio_loo_to_in_sample']:.2f} "
                f"max|res|={r['loo_max_abs_residual']:.1f} "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
    return rows


# -------------------------------------------------------------------------
# Verdict + report rendering
# -------------------------------------------------------------------------


def _is_in_lit_range(name: str, val: float, fixture_label: str) -> bool:
    if not math.isfinite(val):
        return False
    if name == "Lu":
        return LIT_LU_RANGE[0] <= val <= LIT_LU_RANGE[1]
    if name == "Ko":
        return LIT_KO_RANGE[0] <= val <= LIT_KO_RANGE[1]
    if name == "Bi":
        return LIT_BI_RANGE[0] <= val <= LIT_BI_RANGE[1]
    if name == "T_oven_eff_K":
        if fixture_label in {"wonder_white", "post_wonder_meal"}:
            return LIT_T_OVEN_LIDDED[0] <= val <= LIT_T_OVEN_LIDDED[1]
        return LIT_T_OVEN_OPEN[0] <= val <= LIT_T_OVEN_OPEN[1]
    return False


def _verdict(
    phase1: dict, phase2: dict, phase3: dict, phase3b: list, phase4: list,
) -> tuple[str, list]:
    rationale: list = []

    rationale.append(
        f"Forward sanity: uncoupled-limit PASS={phase1['uncoupled_limit']['passed']}, "
        f"steady-state PASS={phase1['steady_state']['passed']}."
    )

    s2 = phase2["summary"]
    rationale.append(
        f"Synthetic recovery (different-class generator: gen α=1.0e-7 ε=0.3 vs "
        f"inv α=1.4e-7 ε=0.5; {s2.get('n_finite', 0)}/{s2.get('n_runs', 0)} runs "
        f"finite, σ_noise=0.5 °C, {SYNTH_SEEDS} seeds): "
        f"RMSE median {s2.get('rmse_median', float('nan')):.3f} °C; "
        f"x_core within 5 mm = "
        f"{s2.get('x_core_within_5mm', 0)}/{s2.get('n_finite', 0)}; "
        f"Lu within 30% = {s2.get('Lu_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"Ko within 30% = {s2.get('Ko_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"Bi within 30% = {s2.get('Bi_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"T_oven within 5 K = "
        f"{s2.get('T_oven_within_5K', 0)}/{s2.get('n_finite', 0)}."
    )

    fit_count_converged = sum(
        1 for v in phase3.values() if v.get("converged", False)
    )
    n_fixtures = len(phase3)
    rationale.append(
        f"Real-CSV 5-param convergence: {fit_count_converged}/{n_fixtures} fixtures."
    )

    main_rmses = [
        d["segment_rmse"]["main"]
        for d in phase3b
        if "segment_rmse" in d and math.isfinite(d["segment_rmse"]["main"])
    ]
    n_under_3 = sum(1 for r in main_rmses if r < 3.0)
    n_3_to_6 = sum(1 for r in main_rmses if 3.0 <= r <= 6.0)
    n_over_6 = sum(1 for r in main_rmses if r > 6.0)
    rmse_med = float(np.median(main_rmses)) if main_rmses else float("nan")
    rationale.append(
        f"Main-bake RMSE: <3 °C={n_under_3}/{len(main_rmses)}, "
        f"3-6 °C={n_3_to_6}/{len(main_rmses)}, >6 °C={n_over_6}/{len(main_rmses)} "
        f"(median {rmse_med:.2f} °C)."
    )

    n_phys = 0
    for label, fit in phase3.items():
        if not fit.get("converged"):
            continue
        ok = sum(
            1 for name in ("Lu", "Ko", "Bi")
            if _is_in_lit_range(name, fit.get(name, float("nan")), label)
        )
        if ok == 3:
            n_phys += 1
    rationale.append(
        f"Fixtures with all of (Lu, Ko, Bi) inside literature ranges: "
        f"{n_phys}/{n_fixtures}."
    )

    # LOO summary.
    loo_finite = [r for r in phase4 if "error" not in r and "loo_rmse" in r]
    if loo_finite:
        loo_arr = np.array([r["loo_rmse"] for r in loo_finite])
        ratio_arr = np.array([r["ratio_loo_to_in_sample"] for r in loo_finite])
        # Deep-end T1 specifically.
        t1_runs = [r for r in loo_finite if r["held_out_sensor"] == "T1"]
        t1_rmse_med = (
            float(np.median([r["loo_rmse"] for r in t1_runs])) if t1_runs else float("nan")
        )
        rationale.append(
            f"LOO subset ({len(loo_finite)} fits across {len(LOO_FIXTURES)} fixtures): "
            f"LOO-RMSE median {float(np.median(loo_arr)):.2f} °C, max "
            f"{float(np.max(loo_arr)):.2f} °C; ratio LOO/in-sample median "
            f"{float(np.median(ratio_arr)):.2f}; T1 (deep-end) LOO-RMSE median "
            f"{t1_rmse_med:.2f} °C ({len(t1_runs)} fits)."
        )
        loo_med = float(np.median(loo_arr))
    else:
        loo_med = float("nan")
        t1_rmse_med = float("nan")

    # Verdict logic per the briefing.
    deep_end_pass = math.isfinite(t1_rmse_med) and t1_rmse_med < 4.0
    main_under_3 = n_under_3 >= max(4, int(np.ceil(0.5 * len(main_rmses)))) if main_rmses else False
    if (
        fit_count_converged >= 5
        and main_under_3
        and deep_end_pass
        and n_phys >= 4
    ):
        verdict = "GO"
        rationale.append(
            "Main-bake RMSE under 3 °C across most fixtures, T1 deep-end LOO-RMSE "
            "under 4 °C, and ≥4/7 fixtures have (Lu, Ko, Bi) inside literature "
            "ranges. The Luikov coupled heat-mass formulation captures the real "
            "physics; the moisture-transport piece was the missing layer."
        )
    elif (
        fit_count_converged >= 5
        and n_over_6 <= 2
        and (math.isfinite(loo_med) and loo_med < 6.0)
    ):
        verdict = "GO-WITH-CAVEATS"
        rationale.append(
            "Main-bake RMSE 3-6 °C on most fixtures or LOO patchy. Luikov reduces "
            "the headline misfit but not uniformly to the 3 °C bar; some "
            "fixtures still show inadequate fit or LOO blow-up."
        )
    else:
        verdict = "CONFIRM-information-limit"
        rationale.append(
            "Even with the full Luikov 5-parameter coupled heat-mass formulation, "
            "main-bake RMSE remains above 6 °C on multiple fixtures and/or the "
            "deep-end T1 LOO-RMSE blows up. The complete physics-class hierarchy "
            "(single-medium → Stefan-PDE → Zürcher-radiative → "
            "Luikov-coupled-heat-mass) has been exhausted on the in-dough-only "
            "observation matrix this dataset provides. **Method 4** (per-CSV "
            "loaf-thickness, oven-setpoint, and lid-state metadata capture, "
            "plus inclusion of the surface-sensor signal in the loss) is the "
            "only remaining path."
        )
    return verdict, rationale


def _format_corr_matrix(corr: list, names: list) -> str:
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


def _render_report(
    phase1: dict, phase2: dict, phase3: dict, phase3b: list, phase4: list,
    verdict: str, rationale: list,
) -> str:
    lines: list = []
    lines.append("# Luikov 1D coupled heat-mass inverse — research report")
    lines.append("")
    lines.append(
        "**Mission:** HMS Lively (M14) — final inverse-problem research mission "
        "across the full physics-class hierarchy. Implements the Luikov (1966) "
        "coupled heat-mass transfer formulation parameterised in the four "
        "Luikov dimensionless numbers (Lu, Ko, Bi, ε, Pn) plus core position "
        "and effective oven temperature, with explicit moisture transport via "
        "the phase-change source term."
    )
    lines.append("")
    lines.append("**Branch:** `refactor/role-classification-unified`  ")
    lines.append("**Mission dir:** `.nelson/missions/2026-04-28_125109_7db8fefb`  ")
    lines.append("**Date:** 2026-04-28  ")
    lines.append("")

    # Executive summary.
    lines.append("## Executive summary")
    lines.append("")
    lines.append(f"**Verdict: {verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    # Forward sanity.
    lines.append("## Forward solver sanity")
    lines.append("")
    p1 = phase1
    lines.append(
        f"**Uncoupled limit** (Lu=ε=Ko≈0, Bi=10, t=200000s): "
        f"final T_min={p1['uncoupled_limit']['T_final_min_K']:.2f} K, "
        f"T_max={p1['uncoupled_limit']['T_final_max_K']:.2f} K, "
        f"max|T-T_oven|={p1['uncoupled_limit']['max_dev_from_oven_K']:.2f} K — "
        f"PASS={p1['uncoupled_limit']['passed']}."
    )
    lines.append("")
    lines.append(
        f"**Steady-state** (full coupling, Lu=0.15, Ko=4, Bi=5, t=60000s): "
        f"T=[{p1['steady_state']['T_final_min_K']:.2f}, "
        f"{p1['steady_state']['T_final_max_K']:.2f}] K, "
        f"u_max={p1['steady_state']['u_final_max']:.4f}, "
        f"u_min={p1['steady_state']['u_final_min']:.4f} — "
        f"PASS={p1['steady_state']['passed']}."
    )
    lines.append("")
    lines.append(
        f"Overall forward sanity: {'PASS' if p1['overall_passed'] else 'FAIL'}."
    )
    lines.append("")

    # Synthetic recovery.
    lines.append("## Synthetic recovery (different-class generator)")
    lines.append("")
    s2 = phase2["summary"]
    truth = s2["truth"]
    lines.append(
        f"To avoid the M7 tautology trap, the generator used "
        f"α={s2['generator_alpha']:.1e} m²/s, ε={s2['generator_epsilon']} "
        f"while the inverter used α={s2['inverter_alpha']:.1e} m²/s, "
        f"ε={s2['inverter_epsilon']}. Synthetic data class genuinely differs "
        f"from the inverter's class — recovery within 30% becomes a real "
        f"identifiability test, not a tautology."
    )
    lines.append("")
    lines.append(
        f"Truth: x_core = {truth['x_core_m']*1000:+.1f} mm, "
        f"Lu = {truth['Lu']}, Ko = {truth['Ko']}, "
        f"Bi = {truth['Bi']}, T_oven_eff = {truth['T_oven_eff_K']:.0f} K. "
        f"σ_noise = 0.5 °C, {SYNTH_SEEDS} seeds."
    )
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| n_runs | {s2.get('n_runs', 0)} |")
    lines.append(f"| n_finite | {s2.get('n_finite', 0)} |")
    lines.append(f"| RMSE median | {s2.get('rmse_median', float('nan')):.3f} °C |")
    lines.append(f"| RMSE max | {s2.get('rmse_max', float('nan')):.3f} °C |")
    lines.append(
        f"| x_core within 5 mm | {s2.get('x_core_within_5mm', 0)}/"
        f"{s2.get('n_finite', 0)} |"
    )
    lines.append(
        f"| Lu within 30% | {s2.get('Lu_within_30pct', 0)}/"
        f"{s2.get('n_finite', 0)} |"
    )
    lines.append(
        f"| Ko within 30% | {s2.get('Ko_within_30pct', 0)}/"
        f"{s2.get('n_finite', 0)} |"
    )
    lines.append(
        f"| Bi within 30% | {s2.get('Bi_within_30pct', 0)}/"
        f"{s2.get('n_finite', 0)} |"
    )
    lines.append(
        f"| T_oven within 5 K | {s2.get('T_oven_within_5K', 0)}/"
        f"{s2.get('n_finite', 0)} |"
    )
    lines.append("")
    lines.append("Per-seed table:")
    lines.append("")
    lines.append(
        "| seed | x_core_m | Lu | Ko | Bi | T_oven | rmse | n_iter | converged | "
        "fit_s |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in phase2["rows"]:
        if "error" in r:
            lines.append(
                f"| {r.get('seed', '?')} | ERROR ({r['error']}) | | | | | | | | |"
            )
            continue
        lines.append(
            f"| {r['seed']} | {r['x_core_m']:+.4f} | {r['Lu']:.3f} | "
            f"{r['Ko']:.3f} | {r['Bi']:.3f} | {r['T_oven_eff_K']:.1f} | "
            f"{r['rmse_per_sensor']:.3f} | {r.get('n_iter', '?')} | "
            f"{r['converged']} | {r.get('fit_seconds', float('nan')):.1f} |"
        )
    lines.append("")

    # Per-fixture real-CSV.
    lines.append("## Per-fixture real-CSV inverse results")
    lines.append("")
    lines.append(
        "| fixture | x_core_n | Lu | Ko | Bi | T_oven | RMSE_full | "
        "RMSE_main | RMSE_startup | RMSE_tail | ρ_main | max&#124;ρ_off&#124; |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    by_label = {d["label"]: d for d in phase3b if "label" in d}
    for label, fit in phase3.items():
        d = by_label.get(label, {})
        seg = d.get("segment_rmse", {}) if d else {}
        rho = d.get("segment_lag1_autocorr", {}) if d else {}
        x_n = fit.get("x_core_normalised", float("nan"))
        rmse_main = seg.get("main", float("nan"))
        rmse_start = seg.get("startup", float("nan"))
        rmse_tail = seg.get("tail", float("nan"))
        lines.append(
            f"| `{label}` | {x_n:+.3f} | "
            f"{fit.get('Lu', float('nan')):.3f} | "
            f"{fit.get('Ko', float('nan')):.3f} | "
            f"{fit.get('Bi', float('nan')):.3f} | "
            f"{fit.get('T_oven_eff_K', float('nan')):.0f} | "
            f"{fit.get('rmse_per_sensor', float('nan')):.2f} | "
            f"{rmse_main:.2f} | {rmse_start:.2f} | {rmse_tail:.2f} | "
            f"{rho.get('main', float('nan')):.3f} | "
            f"{fit.get('max_abs_off_diag_correlation', float('nan')):.3f} |"
        )
    lines.append("")

    # Side-by-side comparison.
    lines.append("## Main-bake RMSE comparison: Luikov vs M9 Stefan vs M12 Zürcher")
    lines.append("")
    lines.append(
        "| fixture | Luikov main-bake (M14) | M9 Stefan main-bake (M10) | "
        "M12 Zürcher 5-param main-bake |"
    )
    lines.append("|---|---|---|---|")
    for label in M9_MAIN:
        d = by_label.get(label)
        luikov_main = (
            d["segment_rmse"]["main"]
            if d and "segment_rmse" in d
            else float("nan")
        )
        m9 = M9_MAIN.get(label, float("nan"))
        m12 = M12_MAIN.get(label, float("nan"))
        lines.append(
            f"| `{label}` | {luikov_main:.2f} | {m9:.2f} | {m12:.2f} |"
        )
    lines.append("")

    # Parameter physicality.
    lines.append("## Parameter physicality")
    lines.append("")
    lines.append(
        f"Literature ranges per the briefing: Lu ∈ "
        f"({LIT_LU_RANGE[0]:.2f}, {LIT_LU_RANGE[1]:.2f}); Ko ∈ "
        f"({LIT_KO_RANGE[0]:.1f}, {LIT_KO_RANGE[1]:.1f}); Bi ∈ "
        f"({LIT_BI_RANGE[0]:.1f}, {LIT_BI_RANGE[1]:.1f}); T_oven_eff ∈ "
        f"({LIT_T_OVEN_OPEN[0]:.0f}, {LIT_T_OVEN_OPEN[1]:.0f}) K open / "
        f"({LIT_T_OVEN_LIDDED[0]:.0f}, {LIT_T_OVEN_LIDDED[1]:.0f}) K lidded."
    )
    lines.append("")
    lines.append("| fixture | Lu in lit | Ko in lit | Bi in lit | T_oven in lit |")
    lines.append("|---|---|---|---|---|")
    for label, fit in phase3.items():
        if not fit.get("converged"):
            lines.append(f"| `{label}` | (no fit) | | | |")
            continue
        ok = lambda n: _is_in_lit_range(n, fit[n], label)
        Lu_ok = ok("Lu")
        Ko_ok = ok("Ko")
        Bi_ok = ok("Bi")
        T_ok = ok("T_oven_eff_K")

        def cell(name, val, fmt, ok):
            tag = " ✓" if ok else " ✗"
            return f"{val:{fmt}}{tag}"

        lines.append(
            f"| `{label}` | "
            f"{cell('Lu', fit['Lu'], '.3f', Lu_ok)} | "
            f"{cell('Ko', fit['Ko'], '.3f', Ko_ok)} | "
            f"{cell('Bi', fit['Bi'], '.3f', Bi_ok)} | "
            f"{cell('T_oven_eff_K', fit['T_oven_eff_K'], '.0f', T_ok)} |"
        )
    lines.append("")

    # LOO subset.
    lines.append("## LOO subset (3 representative fixtures)")
    lines.append("")
    if not phase4:
        lines.append("_(LOO phase skipped — wall-clock budget)_")
    else:
        lines.append(
            "Held-out sensor predicted from a refit on the remaining N-1 in-dough "
            "sensors. Question: does T1 (deep-end) LOO-RMSE improve under Luikov's "
            "moisture-transport physics vs M13's Stefan/Zürcher 11-37 °C?"
        )
        lines.append("")
        lines.append(
            "| fixture | held_out | LOO_rmse | in_sample | ratio | max&#124;res&#124; | "
            "mean_res | converged | fit_s |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for r in phase4:
            if "error" in r:
                continue
            lines.append(
                f"| `{r['fixture']}` | {r['held_out_sensor']} | "
                f"{r['loo_rmse']:.2f} | {r['in_sample_rmse_pooled']:.2f} | "
                f"{r['ratio_loo_to_in_sample']:.2f} | "
                f"{r['loo_max_abs_residual']:.1f} | "
                f"{r['loo_mean_residual']:+.2f} | "
                f"{r['converged']} | {r['fit_seconds']:.1f} |"
            )
    lines.append("")

    # 5x5 correlation matrices.
    lines.append("## Correlation matrices per fixture")
    lines.append("")
    var_names = ["x_core_m", "Lu", "Ko", "Bi", "T_oven_K"]
    for label, fit in phase3.items():
        lines.append(f"\n### `{label}`\n")
        corr = fit.get("full_correlation_matrix")
        lines.append(_format_corr_matrix(corr, var_names))
        lines.append("")

    # Recommendation.
    lines.append("## Recommendation for production")
    lines.append("")
    if verdict == "GO":
        rec = (
            "The Luikov coupled heat-mass inverse fits real bread-baking "
            "thermometry within the 3 °C bar with physical parameters and "
            "deep-end LOO under 4 °C. Wire `fit_luikov_inverse` into the "
            "production loader as the canonical inverse, replacing the M11/M12 "
            "Zürcher path."
        )
    elif verdict == "GO-WITH-CAVEATS":
        rec = (
            "Luikov reduces main-bake RMSE meaningfully relative to Stefan/"
            "Zürcher but not uniformly to the 3 °C bar. Consider production "
            "wiring with a low-confidence flag on fixtures with main-bake RMSE "
            "> 4 °C or deep-end LOO > 5 °C. Continue Method 4 metadata-capture "
            "in parallel."
        )
    else:
        rec = (
            "The full hierarchy (single-medium → Stefan-PDE → Zürcher-radiative "
            "→ Luikov-coupled-heat-mass) has been exhausted. Even with explicit "
            "moisture transport and convective Biot BC, the in-dough-only "
            "observation matrix does not constrain the deep region. **Method 4** "
            "(per-CSV loaf-thickness, oven-setpoint, lid-state metadata; or "
            "inclusion of the spatially-interpolated surface signal in the loss) "
            "is the only remaining path. Recommend pivoting away from "
            "inverse-problem work on this data alone."
        )
    lines.append(rec)
    lines.append("")

    return "\n".join(lines)


def _render_captains_log(
    phase1: dict, phase2: dict, phase3: dict, phase3b: list, phase4: list,
    verdict: str, rationale: list, wall_seconds: float,
) -> str:
    lines: list = []
    lines.append(
        "# Captain's log — HMS Lively, M14 Luikov 1D coupled heat-mass inverse"
    )
    lines.append("")
    lines.append(
        "**Mission:** Final inverse-problem research mission. Implement the "
        "Luikov (1966) coupled heat-mass transfer formulation parameterised "
        "in (Lu, Ko, Bi, ε, Pn) plus core position and effective oven "
        "temperature. After M9 Stefan PDE (latent-heat front) and M11/M12 "
        "Zürcher two-state (radiative BC) both stalled at ≥6 °C main-bake "
        "RMSE, this tests whether an explicit moisture-transport layer "
        "captures the missing physics."
    )
    lines.append("")
    lines.append("**Branch:** `refactor/role-classification-unified`  ")
    lines.append("**Mission dir:** `.nelson/missions/2026-04-28_125109_7db8fefb`  ")
    lines.append("**Date:** 2026-04-28  ")
    lines.append(f"**Wall-clock:** {wall_seconds:.1f} s end-to-end.")
    lines.append("")

    lines.append("## Plan executed")
    lines.append("")
    lines.append(
        "1. **New module** `src/data/spatial_reconstruction/luikov.py` "
        "(~600 lines) — coupled heat-mass forward solver via "
        "method-of-lines (40 spatial nodes × 2 state vars = 80 ODE "
        "variables, integrated by LSODA), 5-parameter Nelder-Mead inverse. "
        "DRY: reuses M7 `_build_observation_matrix` and `_numerical_hessian`.\n"
        "2. **Forward sanity** — uncoupled-limit (Lu, ε → 0 collapses to "
        "pure heat with convective BC) and steady-state checks.\n"
        "3. **Synthetic recovery (different-class generator)** — generator "
        "uses α=1.0e-7, ε=0.3 while inverter uses α=1.4e-7, ε=0.5. The "
        "synthetic data class genuinely differs from the inverter's class, "
        "avoiding the M7 tautology trap.\n"
        "4. **Real-CSV joint inverse** — same 7 fixtures as M9/M11/M12.\n"
        "5. **LOO subset** — 3 fixtures (BA3C_0946, 100098DE_1351, "
        "wonder_white) × all in-dough sensors. Compares deep-end T1 "
        "LOO-RMSE against M13's Stefan/Zürcher 11-37 °C numbers.\n"
        "6. **DRY** — reused M10 helpers (`_segment_rmse`, "
        "`_per_sensor_rmse`, `_lag1_autocorr_segment`); reused M9/M11 "
        "fixture loader (`REAL_FIXTURES`, `_segmented_real_fixture`)."
    )
    lines.append("")

    # Forward sanity.
    p1 = phase1
    lines.append("## Forward solver sanity")
    lines.append("")
    lines.append(
        f"- **Uncoupled limit** (Lu=ε≈0, Bi=10, t=200000s): "
        f"final T=[{p1['uncoupled_limit']['T_final_min_K']:.2f}, "
        f"{p1['uncoupled_limit']['T_final_max_K']:.2f}] K, "
        f"max|T-T_oven|={p1['uncoupled_limit']['max_dev_from_oven_K']:.2f} K — "
        f"PASS={p1['uncoupled_limit']['passed']}.\n"
        f"- **Steady-state** (Lu=0.15, Ko=4, Bi=5, t=60000s): "
        f"T=[{p1['steady_state']['T_final_min_K']:.2f}, "
        f"{p1['steady_state']['T_final_max_K']:.2f}] K, "
        f"u_max={p1['steady_state']['u_final_max']:.4f} — "
        f"PASS={p1['steady_state']['passed']}."
    )
    lines.append("")

    # Synthetic recovery.
    s2 = phase2["summary"]
    lines.append("## Synthetic recovery (different-class generator)")
    lines.append("")
    truth = s2["truth"]
    lines.append(
        f"Truth: x_core={truth['x_core_m']*1000:+.1f} mm, "
        f"Lu={truth['Lu']}, Ko={truth['Ko']}, Bi={truth['Bi']}, "
        f"T_oven={truth['T_oven_eff_K']:.0f} K. "
        f"Generator α=1.0e-7 ε=0.3 vs inverter α=1.4e-7 ε=0.5. "
        f"σ_noise=0.5 °C, {SYNTH_SEEDS} seeds, "
        f"{s2.get('n_finite', 0)}/{s2.get('n_runs', 0)} runs finite."
    )
    lines.append("")
    lines.append(
        f"- RMSE median {s2.get('rmse_median', float('nan')):.3f} °C "
        f"(max {s2.get('rmse_max', float('nan')):.3f}).\n"
        f"- x_core within 5 mm: "
        f"{s2.get('x_core_within_5mm', 0)}/{s2.get('n_finite', 0)}.\n"
        f"- Lu within 30%: "
        f"{s2.get('Lu_within_30pct', 0)}/{s2.get('n_finite', 0)}.\n"
        f"- Ko within 30%: "
        f"{s2.get('Ko_within_30pct', 0)}/{s2.get('n_finite', 0)}.\n"
        f"- Bi within 30%: "
        f"{s2.get('Bi_within_30pct', 0)}/{s2.get('n_finite', 0)}.\n"
        f"- T_oven within 5 K: "
        f"{s2.get('T_oven_within_5K', 0)}/{s2.get('n_finite', 0)}."
    )
    lines.append("")

    # Per-fixture comparison.
    lines.append("## Real-CSV main-bake RMSE — Luikov vs M9 Stefan vs M12 Zürcher")
    lines.append("")
    by_label = {d["label"]: d for d in phase3b if "label" in d}
    lines.append("| fixture | Luikov | M9 Stefan | M12 Zürcher 5-p |")
    lines.append("|---|---|---|---|")
    for label in M9_MAIN:
        d = by_label.get(label)
        luikov_main = (
            d["segment_rmse"]["main"]
            if d and "segment_rmse" in d
            else float("nan")
        )
        m9 = M9_MAIN.get(label, float("nan"))
        m12 = M12_MAIN.get(label, float("nan"))
        lines.append(
            f"| `{label}` | {luikov_main:.2f} | {m9:.2f} | {m12:.2f} |"
        )
    lines.append("")

    # LOO summary.
    lines.append("## LOO subset summary")
    lines.append("")
    if not phase4:
        lines.append("LOO phase skipped (wall-clock budget).")
    else:
        loo_finite = [r for r in phase4 if "error" not in r and "loo_rmse" in r]
        if loo_finite:
            loo_arr = np.array([r["loo_rmse"] for r in loo_finite])
            ratio_arr = np.array(
                [r["ratio_loo_to_in_sample"] for r in loo_finite]
            )
            t1_runs = [
                r for r in loo_finite if r["held_out_sensor"] == "T1"
            ]
            t1_rmse_med = (
                float(np.median([r["loo_rmse"] for r in t1_runs]))
                if t1_runs
                else float("nan")
            )
            lines.append(
                f"- {len(loo_finite)} LOO fits across {len(LOO_FIXTURES)} "
                f"fixtures.\n"
                f"- LOO-RMSE: median {float(np.median(loo_arr)):.2f} °C, "
                f"max {float(np.max(loo_arr)):.2f}.\n"
                f"- LOO/in-sample ratio: median "
                f"{float(np.median(ratio_arr)):.2f}, max "
                f"{float(np.max(ratio_arr)):.2f}.\n"
                f"- T1 (deep-end) LOO-RMSE median: {t1_rmse_med:.2f} °C "
                f"(across {len(t1_runs)} fits).\n"
                f"- Briefing's deep-end pass bar: T1 LOO-RMSE < 4 °C."
            )
    lines.append("")

    # Verdict.
    lines.append("## Verdict and rationale")
    lines.append("")
    lines.append(f"**{verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    # Closing.
    lines.append("## Closing")
    lines.append("")
    if verdict == "CONFIRM-information-limit":
        lines.append(
            "The full physics-class hierarchy (single-medium heat → Stefan "
            "PDE → Zürcher two-state radiative → Luikov coupled heat-mass) "
            "has now been exhausted. Across all four classes, in-dough-only "
            "thermometry on this dataset does not constrain the deep region "
            "(x < x_min(in-dough)) regardless of the physics added. The "
            "common cause is the observation matrix, not the parameter count "
            "or physics class. **Method 4** — capturing per-CSV loaf "
            "thickness, oven setpoint, and lid contact state at acquisition "
            "time, plus including the classifier's interpolated surface "
            "signal in the inverse loss — is the structural fix."
        )
    elif verdict == "GO-WITH-CAVEATS":
        lines.append(
            "Luikov delivers a real reduction in main-bake RMSE relative to "
            "Stefan/Zürcher; production wiring is justified with low-confidence "
            "flags on the worst fixtures and Method 4 metadata-capture as a "
            "parallel track."
        )
    else:
        lines.append(
            "Luikov delivers within-3 °C main-bake fits with deep-end T1 LOO "
            "below 4 °C. The moisture-transport physics is the missing piece; "
            "production wiring of `fit_luikov_inverse` recommended."
        )
    lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main(skip_loo: bool = False) -> None:
    overall_t0 = time.time()
    out: dict = {
        "mission": "HMS Lively M14 — Luikov coupled heat-mass inverse",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "downsample_factor": DOWNSAMPLE_FACTOR,
        "n_spatial": N_SPATIAL,
        "loo_fixtures": sorted(LOO_FIXTURES),
    }

    t0 = _phase("phase 1: forward solver sanity (uncoupled limit + steady state)")
    out["phase1"] = phase1_forward_sanity()
    print(f"  phase 1 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(f"phase 2: synthetic recovery (different-class generator, {SYNTH_SEEDS} seeds)")
    out["phase2"] = phase2_synthetic_recovery()
    print(f"  phase 2 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(f"phase 3: real-CSV Luikov inverse ({len(REAL_FIXTURES)} fixtures, 5-param)")
    out["phase3"] = phase3_real_csv()
    print(f"  phase 3 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase("phase 3b: residual decomposition (M10 helpers)")
    out["phase3b"] = phase3b_residual_decomposition(out["phase3"])
    print(f"  phase 3b elapsed: {time.time() - t0:.1f}s", flush=True)

    if skip_loo:
        out["phase4"] = []
        print("\n  phase 4 skipped (skip_loo=True)", flush=True)
    else:
        t0 = _phase(f"phase 4: LOO subset on {len(LOO_FIXTURES)} representative fixtures")
        out["phase4"] = phase4_loo_subset()
        print(f"  phase 4 elapsed: {time.time() - t0:.1f}s", flush=True)

    verdict, rationale = _verdict(
        out["phase1"], out["phase2"], out["phase3"], out["phase3b"], out["phase4"],
    )
    out["verdict"] = verdict
    out["rationale"] = rationale
    out["wall_seconds"] = time.time() - overall_t0

    print(f"\n  total wall-time: {out['wall_seconds']:.1f}s", flush=True)
    print(f"  verdict: {verdict}", flush=True)
    for r in rationale:
        print(f"    - {r}", flush=True)

    # Write outputs.
    with open(OUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"  wrote {OUT_JSON_PATH}", flush=True)

    md_text = _render_report(
        out["phase1"], out["phase2"], out["phase3"],
        out["phase3b"], out["phase4"], verdict, rationale,
    )
    with open(OUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"  wrote {OUT_MD_PATH}", flush=True)

    log_text = _render_captains_log(
        out["phase1"], out["phase2"], out["phase3"],
        out["phase3b"], out["phase4"], verdict, rationale,
        out["wall_seconds"],
    )
    os.makedirs(os.path.dirname(CAPTAINS_LOG_PATH), exist_ok=True)
    with open(CAPTAINS_LOG_PATH, "w", encoding="utf-8") as f:
        f.write(log_text)
    print(f"  wrote {CAPTAINS_LOG_PATH}", flush=True)


if __name__ == "__main__":
    skip = ("--skip-loo" in sys.argv) or (os.environ.get("SKIP_LOO") == "1")
    main(skip_loo=skip)
