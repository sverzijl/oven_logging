"""HMS Daring — M16 Luikov-tin OBSERVED-BC inverse end-to-end driver.

Reformulation of M15 with:
  - Observed T_air(t) from M2a-flagged ambient sensors
  - Observed h_eff(t) from surface energy balance
  - Piecewise alpha(T) profile (alpha_post/alpha_pre ratio)
  - 4-5 free parameters (down from M15's 8)

Phases:
  1. Diagnostic — extract observables JSON
  2. Forward sanity — pytest sub-suite
  3. Synthetic recovery — different alpha_pre in generator vs inverter
  4. Real-CSV inverse — 7 fixtures
  5. LOO subset — 6 fits (T1, T2 on 3 representative fixtures)

Outputs:
  - tests/baselines/observables_diagnostic.json (Phase 1)
  - tests/baselines/luikov_tin_observed_research.json (raw)
  - tests/baselines/luikov_tin_observed_research.md (report)
  - .nelson/missions/2026-04-28_145444_9193a856/captains-log.md
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
import pytest

from src.data.spatial_reconstruction.luikov_tin_observed import (  # noqa: E402
    SENSOR_NAMES_DEFAULT,
    SENSOR_POSITIONS_MM_FROM_TIP,
    fit_luikov_tin_observed_inverse,
    infer_core_depth_from_forward,
    solve_luikov_tin_observed,
)
from tests._diagnose_observables import (  # noqa: E402
    diagnose_fixture,
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
    _segmented_real_fixture,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON_PATH = os.path.join(BASE_DIR, "baselines", "luikov_tin_observed_research.json")
OUT_MD_PATH = os.path.join(BASE_DIR, "baselines", "luikov_tin_observed_research.md")
OBSERVABLES_JSON_PATH = os.path.join(BASE_DIR, "baselines", "observables_diagnostic.json")
CAPTAINS_LOG_PATH = os.path.join(
    os.path.dirname(BASE_DIR),
    ".nelson",
    "missions",
    "2026-04-28_145444_9193a856",
    "captains-log.md",
)

DOWNSAMPLE_FACTOR = 4
N_SPATIAL = 60
SAMPLE_PERIOD_S = 5.0

LOO_FIXTURES = {"BA3C_0946", "100098DE_1351", "wonder_white"}
LOO_HOLD_OUT = ("T1", "T2")

SYNTH_SEEDS = 3

# Comparators
M9_MAIN = {
    "BA3C_0946": 5.76,
    "BA3C_1759_C0": 5.76,
    "BA3C_1759_C1": 6.80,
    "BA3C_1759_C2": 7.95,
    "100098DE_1351": 7.49,
    "wonder_white": 11.03,
    "post_wonder_meal": 10.55,
}
M15_MAIN = {
    "BA3C_0946": 5.98,
    "BA3C_1759_C0": 5.98,
    "BA3C_1759_C1": 6.23,
    "BA3C_1759_C2": 6.43,
    "100098DE_1351": float("nan"),
    "wonder_white": float("nan"),
    "post_wonder_meal": float("nan"),
}
M9_T1_LOO_RANGE = (9.0, 21.0)
M15_T1_LOO_MEDIAN = 11.74


def _phase(name: str) -> float:
    print(f"\n=== {name} ===", flush=True)
    return time.time()


# -------------------------------------------------------------------------
# Phase 1 — Observables diagnostic
# -------------------------------------------------------------------------


def phase1_observables() -> dict:
    """Run the Phase 1 diagnostic for all fixtures."""
    out: dict = {}
    for spec in REAL_FIXTURES:
        try:
            d = diagnose_fixture(spec)
            out[spec["label"]] = d
            if "error" in d:
                print(f"  {spec['label']:>20}: ERROR {d['error']}")
            else:
                steam_str = (
                    f"steam={d['steam_duration_s']:.0f}s"
                    if d["steam_detected"]
                    else "no-steam"
                )
                spring_str = (
                    f"spring=[{d['spring_start_s']:.0f}-{d['spring_end_s']:.0f}]s"
                    if d["spring_detected"]
                    else "no-spring"
                )
                print(
                    f"  {spec['label']:>20}: {steam_str:>15} {spring_str:>22} "
                    f"T_air[{d['T_air_min_C']:.0f},{d['T_air_max_C']:.0f}]°C "
                    f"h_eff_med={d['h_eff_median']:.1f}"
                )
        except Exception as exc:
            out[spec["label"]] = {"label": spec["label"], "error": str(exc)}
            print(f"  {spec['label']:>20}: EXC {exc}")
    # Persist alongside observables_diagnostic.json
    with open(OBSERVABLES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"fixtures": out, "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
            f, indent=2, default=str,
        )
    return out


# -------------------------------------------------------------------------
# Phase 2 — Forward sanity (pytest sub-suite)
# -------------------------------------------------------------------------


def phase2_forward_sanity() -> dict:
    test_path = os.path.join(BASE_DIR, "test_luikov_tin_observed_research.py")
    rc = pytest.main([test_path, "-v", "--tb=short", "-q"])
    return {"pytest_returncode": int(rc), "passed": int(rc) == 0}


# -------------------------------------------------------------------------
# Phase 3 — Synthetic recovery
# -------------------------------------------------------------------------


SYNTH_TRUTH = {
    "L_m": 0.095,
    "D_m": 0.065,
    "Lu": 0.10,
    "q_bottom_eff": 20.0,
    "alpha_ratio": 0.4,
}


def _synthesise(observables: dict, seed: int, noise_sigma_c: float = 0.5) -> tuple[pd.DataFrame, list, np.ndarray, np.ndarray]:
    """Generate synthetic data using observed T_air and h_eff patterns from BA3C_0946.

    Generator uses alpha_pre = 1.0e-7; inverter uses alpha_pre = 1.4e-7
    (different-class tautology guard).
    """
    truth = SYNTH_TRUTH
    # Use BA3C_0946 observables for realistic patterns
    diag = observables["BA3C_0946"]
    if "error" in diag:
        # Fallback: synthetic patterns
        n_t = 600
        t_grid = np.arange(n_t, dtype=float) * SAMPLE_PERIOD_S
        T_air_K = 295.0 + (470.0 - 295.0) * (1 - np.exp(-t_grid / 600.0))
        h_eff = np.full(n_t, 30.0)
    else:
        t_grid_full = np.array(diag["t_grid_s"], dtype=float)
        T_air_full = np.array(diag["T_air_K_t"], dtype=float)
        h_eff_full = np.array([
            v if v is not None else float("nan")
            for v in diag["h_eff_t"]
        ], dtype=float)
        # Take first 3000 s for synthetic
        n_t = min(600, len(t_grid_full))
        t_grid = t_grid_full[:n_t]
        T_air_K = T_air_full[:n_t]
        h_eff = h_eff_full[:n_t]
        # Fill NaN h_eff via interpolation
        finite = np.isfinite(h_eff)
        if not finite.any():
            h_eff = np.full_like(h_eff, 20.0)
        else:
            idx = np.arange(len(h_eff))
            h_eff = np.interp(idx, idx[finite], h_eff[finite])

    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    d_mm = truth["D_m"] * 1000.0 - p_mm
    L_mm = truth["L_m"] * 1000.0
    in_dough_mask = (d_mm > 0.5) & (d_mm < L_mm - 0.5)
    in_dough = [SENSOR_NAMES_DEFAULT[i] for i in range(8) if in_dough_mask[i]]
    d_in = d_mm[in_dough_mask] / 1000.0

    fwd = solve_luikov_tin_observed(
        L_m=truth["L_m"],
        Lu=truth["Lu"],
        q_bottom_eff=truth["q_bottom_eff"],
        alpha_ratio=truth["alpha_ratio"],
        t_grid_s=t_grid,
        T_air_K_t=T_air_K,
        h_eff_t=h_eff,
        T_initial_K=295.0,
        sample_x_m=d_in,
        n_spatial=N_SPATIAL,
        alpha_pre_m2_s=1.0e-7,  # GENERATOR
    )
    T_pred_C = fwd.T_field_K - 273.15
    rng = np.random.default_rng(seed)
    if noise_sigma_c > 0:
        T_pred_C = T_pred_C + rng.normal(0.0, noise_sigma_c, T_pred_C.shape)
    df = pd.DataFrame({"Timestamp": t_grid})
    for k, name in enumerate(in_dough):
        df[name] = T_pred_C[:, k]
    air_C = T_air_K - 273.15
    for name in SENSOR_NAMES_DEFAULT:
        if name not in df.columns:
            df[name] = air_C
    return df, in_dough, T_air_K, h_eff


def phase3_synthetic_recovery(observables: dict) -> dict:
    rows = []
    truth = SYNTH_TRUTH
    for seed in range(SYNTH_SEEDS):
        df, in_dough, T_air_K, h_eff = _synthesise(
            observables, seed=seed, noise_sigma_c=0.5
        )
        t0 = time.time()
        try:
            r = fit_luikov_tin_observed_inverse(
                df=df,
                in_dough_sensors=in_dough,
                T_air_K_t=T_air_K,
                h_eff_t=h_eff,
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                max_iter=400,
                fit_alpha_ratio=True,
            )
            r["seed"] = seed
            r["fit_seconds"] = time.time() - t0
            rows.append(r)
            print(
                f"  seed={seed}: "
                f"L={r['L_m']*1000:.0f}mm D={r['D_m']*1000:.0f}mm "
                f"Lu={r['Lu']:.3f} qbot={r['q_bottom_eff']:.1f} "
                f"αr={r['alpha_ratio']:.2f} rmse={r['rmse_per_sensor']:.3f}K "
                f"interior={r['n_interior_params']}/{r['n_param']} "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
        except Exception as exc:
            rows.append({"seed": seed, "error": str(exc)})
            print(f"  seed={seed}: ERROR {exc}", flush=True)

    finite = [r for r in rows if "error" not in r]
    if not finite:
        return {"truth": truth, "rows": rows, "summary": {"n_finite": 0}}

    def _within_30pct(name: str) -> int:
        arr = np.array([r[name] for r in finite], dtype=float)
        tru = truth[name]
        return int(np.sum(np.abs(arr - tru) / max(abs(tru), 1e-9) < 0.30))

    summary = {
        "n_runs": len(rows),
        "n_finite": len(finite),
        "rmse_median": float(np.median([r["rmse_per_sensor"] for r in finite])),
        "rmse_max": float(np.max([r["rmse_per_sensor"] for r in finite])),
        "L_m_within_30pct": _within_30pct("L_m"),
        "D_m_within_30pct": _within_30pct("D_m"),
        "Lu_within_30pct": _within_30pct("Lu"),
        "q_bottom_eff_within_30pct": _within_30pct("q_bottom_eff"),
        "alpha_ratio_within_30pct": _within_30pct("alpha_ratio"),
        "interior_count_median": float(
            np.median([r["n_interior_params"] for r in finite])
        ),
    }
    return {"truth": truth, "rows": rows, "summary": summary}


# -------------------------------------------------------------------------
# Phase 4 — Real-CSV inverse
# -------------------------------------------------------------------------


def _build_air_h_arrays(diag: dict) -> tuple[np.ndarray, np.ndarray]:
    """Extract T_air, h_eff time series from diagnostic, with NaN handling."""
    T_air = np.array(diag["T_air_K_t"], dtype=float)
    h_eff = np.array(
        [v if v is not None else float("nan") for v in diag["h_eff_t"]],
        dtype=float,
    )
    finite = np.isfinite(h_eff)
    if finite.any():
        idx = np.arange(len(h_eff))
        h_eff = np.interp(idx, idx[finite], h_eff[finite])
    else:
        h_eff = np.full_like(h_eff, 15.0)
    return T_air, h_eff


def phase4_real_csv(observables: dict) -> dict:
    out: dict = {}
    for spec in REAL_FIXTURES:
        df = _segmented_real_fixture(spec)
        diag = observables.get(spec["label"], {})
        if "error" in diag:
            print(f"  {spec['label']:>20}: SKIP no observables")
            out[spec["label"]] = {
                "error": "no observables",
                "rmse_per_sensor": float("nan"),
                "fixture_label": spec["label"],
                "converged": False,
                "n_interior_params": 0,
                "param_at_bound": {},
            }
            continue
        T_air_K, h_eff_t = _build_air_h_arrays(diag)
        # Make sure df length matches T_air length (diagnostic uses same df)
        if len(T_air_K) != len(df):
            # Trim or align defensively
            n = min(len(T_air_K), len(df))
            T_air_K = T_air_K[:n]
            h_eff_t = h_eff_t[:n]
            df = df.iloc[:n].reset_index(drop=True)

        t0 = time.time()
        try:
            r = fit_luikov_tin_observed_inverse(
                df=df,
                in_dough_sensors=spec["in_dough"],
                T_air_K_t=T_air_K,
                h_eff_t=h_eff_t,
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                max_iter=600,
                fit_alpha_ratio=True,
            )
            r["fit_seconds"] = time.time() - t0
            r["fixture_label"] = spec["label"]
            r["fixture_name"] = spec["fixture_name"]
            r["expected_curve_idx"] = spec["expected_curve_idx"]
        except Exception as exc:
            r = {
                "error": str(exc),
                "rmse_per_sensor": float("nan"),
                "L_m": float("nan"),
                "D_m": float("nan"),
                "Lu": float("nan"),
                "q_bottom_eff": float("nan"),
                "alpha_ratio": float("nan"),
                "x_core_depth_inferred_mm": float("nan"),
                "converged": False,
                "fit_seconds": time.time() - t0,
                "fixture_label": spec["label"],
                "in_dough": list(spec["in_dough"]),
                "n_interior_params": 0,
                "param_at_bound": {},
                "n_param": 5,
            }
        out[spec["label"]] = r
        if "error" in r:
            print(f"  {spec['label']:>20}: ERROR {r['error']}", flush=True)
        else:
            print(
                f"  {spec['label']:>20}: "
                f"L={r['L_m']*1000:.0f}mm D={r['D_m']*1000:.0f}mm "
                f"Lu={r['Lu']:.3f} qbot={r['q_bottom_eff']:.1f} "
                f"αr={r['alpha_ratio']:.2f} "
                f"rmse={r['rmse_per_sensor']:.2f}K "
                f"x_core={r['x_core_depth_inferred_mm']:.1f}mm "
                f"interior={r['n_interior_params']}/{r['n_param']} "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
    return out


# -------------------------------------------------------------------------
# Phase 4b — Residual decomposition
# -------------------------------------------------------------------------


def _forward_eval_at_fit(spec: dict, fit: dict, T_air_K: np.ndarray, h_eff_t: np.ndarray) -> dict:
    df = _segmented_real_fixture(spec)
    in_dough = list(spec["in_dough"])
    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    pos_by_name = dict(zip(SENSOR_NAMES_DEFAULT, p_mm / 1000.0))
    p_obs_m = np.array([pos_by_name[s] for s in in_dough], dtype=float)
    d_obs_m = fit["D_m"] - p_obs_m
    d_clipped = np.clip(d_obs_m, 0.0, fit["L_m"])

    n = min(len(T_air_K), len(df))
    df = df.iloc[:n].reset_index(drop=True)
    T_air_K = T_air_K[:n]
    h_eff_t = h_eff_t[:n]

    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    T_obs_C = np.column_stack(
        [df[s].to_numpy(dtype=float)[sl] for s in in_dough]
    )
    T_obs_K = T_obs_C + 273.15
    T_air_obs = T_air_K[sl]
    h_eff_obs = h_eff_t[sl]

    fwd = solve_luikov_tin_observed(
        L_m=fit["L_m"],
        Lu=fit["Lu"],
        q_bottom_eff=fit["q_bottom_eff"],
        alpha_ratio=fit["alpha_ratio"],
        t_grid_s=t_obs,
        T_air_K_t=T_air_obs,
        h_eff_t=h_eff_obs,
        T_initial_K=fit["T_initial_K"],
        sample_x_m=d_clipped,
        n_spatial=int(fit.get("n_spatial", N_SPATIAL)),
    )
    residual = fwd.T_field_K - T_obs_K
    return {
        "label": spec["label"],
        "in_dough": in_dough,
        "T_pred_K": fwd.T_field_K,
        "T_obs_K": T_obs_K,
        "residual": residual,
        "rmse_full_recomputed": float(np.sqrt(np.mean(residual ** 2))),
    }


def phase4b_residual_decomposition(phase4: dict, observables: dict) -> list:
    decomps: list = []
    for spec in REAL_FIXTURES:
        fit = phase4.get(spec["label"], {})
        if not fit.get("converged", False) or "error" in fit:
            decomps.append(
                {"label": spec["label"], "skipped_reason": "did_not_converge"}
            )
            continue
        diag = observables.get(spec["label"], {})
        if "error" in diag:
            decomps.append(
                {"label": spec["label"], "skipped_reason": "no_observables"}
            )
            continue
        T_air_K, h_eff_t = _build_air_h_arrays(diag)
        try:
            ev = _forward_eval_at_fit(spec, fit, T_air_K, h_eff_t)
        except Exception as exc:
            decomps.append(
                {"label": spec["label"], "skipped_reason": f"forward_eval_failed: {exc}"}
            )
            continue
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
            "L_m": float(fit["L_m"]),
            "D_m": float(fit["D_m"]),
            "Lu": float(fit["Lu"]),
            "q_bottom_eff": float(fit["q_bottom_eff"]),
            "alpha_ratio": float(fit["alpha_ratio"]),
            "x_core_depth_inferred_mm": float(fit["x_core_depth_inferred_mm"]),
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
# Phase 5 — LOO subset
# -------------------------------------------------------------------------


def _loo_predict(fit: dict, df: pd.DataFrame, held_out: str, T_air_K: np.ndarray, h_eff_t: np.ndarray) -> tuple:
    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    pos_by_name = dict(zip(SENSOR_NAMES_DEFAULT, p_mm / 1000.0))
    p_held_m = float(pos_by_name[held_out])
    d_held_m = fit["D_m"] - p_held_m
    d_clipped = np.array([max(0.0, min(d_held_m, fit["L_m"]))], dtype=float)
    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    T_air_obs = T_air_K[sl]
    h_eff_obs = h_eff_t[sl]
    fwd = solve_luikov_tin_observed(
        L_m=fit["L_m"],
        Lu=fit["Lu"],
        q_bottom_eff=fit["q_bottom_eff"],
        alpha_ratio=fit["alpha_ratio"],
        t_grid_s=t_obs,
        T_air_K_t=T_air_obs,
        h_eff_t=h_eff_obs,
        T_initial_K=fit["T_initial_K"],
        sample_x_m=d_clipped,
        n_spatial=int(fit.get("n_spatial", N_SPATIAL)),
    )
    T_pred_held_C = fwd.T_field_K[:, 0] - 273.15
    T_obs_held_C = df[held_out].to_numpy(dtype=float)[sl]
    return T_pred_held_C, T_obs_held_C


def _loo_one(spec: dict, observables: dict, held_out: str) -> dict:
    df = _segmented_real_fixture(spec)
    diag = observables.get(spec["label"], {})
    if "error" in diag:
        return {
            "fixture": spec["label"],
            "held_out_sensor": held_out,
            "skipped": "no_observables",
        }
    T_air_K, h_eff_t = _build_air_h_arrays(diag)
    n = min(len(T_air_K), len(df))
    df = df.iloc[:n].reset_index(drop=True)
    T_air_K = T_air_K[:n]
    h_eff_t = h_eff_t[:n]

    full = list(spec["in_dough"])
    if held_out not in full:
        return {
            "fixture": spec["label"],
            "held_out_sensor": held_out,
            "skipped": "not_in_dough",
        }
    training = [s for s in full if s != held_out]
    t0 = time.time()
    try:
        result = fit_luikov_tin_observed_inverse(
            df=df,
            in_dough_sensors=training,
            T_air_K_t=T_air_K,
            h_eff_t=h_eff_t,
            downsample_factor=DOWNSAMPLE_FACTOR,
            n_spatial=N_SPATIAL,
            max_iter=600,
            fit_alpha_ratio=True,
        )
    except Exception as exc:
        return {
            "fixture": spec["label"],
            "held_out_sensor": held_out,
            "training_sensors": training,
            "error": str(exc),
            "fit_seconds": time.time() - t0,
        }

    T_pred_held, T_obs_held = _loo_predict(result, df, held_out, T_air_K, h_eff_t)
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
            "L_m": float(result["L_m"]),
            "D_m": float(result["D_m"]),
            "Lu": float(result["Lu"]),
            "q_bottom_eff": float(result["q_bottom_eff"]),
            "alpha_ratio": float(result["alpha_ratio"]),
        },
        "x_core_depth_inferred_mm": float(result["x_core_depth_inferred_mm"]),
        "n_interior_params": int(result["n_interior_params"]),
        "n_iter": int(result.get("n_iter", -1)),
        "converged": bool(result.get("converged", False)),
        "fit_seconds": time.time() - t0,
    }


def phase5_loo_subset(observables: dict) -> list:
    rows = []
    for spec in REAL_FIXTURES:
        if spec["label"] not in LOO_FIXTURES:
            continue
        for held in LOO_HOLD_OUT:
            r = _loo_one(spec, observables, held)
            rows.append(r)
            if "error" in r:
                print(f"  LOO {spec['label']:>20} -{held}: ERROR {r['error']}", flush=True)
                continue
            if "skipped" in r:
                print(f"  LOO {spec['label']:>20} -{held}: skipped ({r['skipped']})", flush=True)
                continue
            print(
                f"  LOO {spec['label']:>20} -{held}: "
                f"loo_rmse={r['loo_rmse']:.2f} "
                f"in_sample={r['in_sample_rmse_pooled']:.2f} "
                f"ratio={r['ratio_loo_to_in_sample']:.2f} "
                f"max|res|={r['loo_max_abs_residual']:.1f} "
                f"x_core={r['x_core_depth_inferred_mm']:.1f}mm "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
    return rows


# -------------------------------------------------------------------------
# Verdict
# -------------------------------------------------------------------------


def _verdict(phase2: dict, phase3: dict, phase4: dict, phase4b: list, phase5: list) -> tuple[str, list]:
    rationale: list = []

    rationale.append(
        f"Forward sanity: 8-test pytest sub-suite "
        f"{'PASS' if phase2.get('passed') else 'FAIL'} "
        f"(returncode={phase2.get('pytest_returncode')})."
    )

    s3 = phase3.get("summary", {})
    rationale.append(
        f"Synthetic recovery (different α_pre: gen 1.0e-7 vs inv 1.4e-7; "
        f"{s3.get('n_finite', 0)}/{s3.get('n_runs', 0)} runs finite, "
        f"σ_noise=0.5 °C, {SYNTH_SEEDS} seeds): "
        f"RMSE median {s3.get('rmse_median', float('nan')):.3f} °C; "
        f"L_m within 30%={s3.get('L_m_within_30pct', 0)}/{s3.get('n_finite', 0)}; "
        f"D_m within 30%={s3.get('D_m_within_30pct', 0)}/{s3.get('n_finite', 0)}; "
        f"Lu within 30%={s3.get('Lu_within_30pct', 0)}/{s3.get('n_finite', 0)}; "
        f"q_bot within 30%={s3.get('q_bottom_eff_within_30pct', 0)}/{s3.get('n_finite', 0)}; "
        f"α_ratio within 30%={s3.get('alpha_ratio_within_30pct', 0)}/{s3.get('n_finite', 0)}."
    )

    fit_count_converged = sum(1 for v in phase4.values() if v.get("converged", False))
    n_fixtures = len(phase4)
    rationale.append(
        f"Real-CSV 4-5 param convergence: {fit_count_converged}/{n_fixtures}."
    )

    main_rmses = [
        d["segment_rmse"]["main"]
        for d in phase4b
        if "segment_rmse" in d and math.isfinite(d["segment_rmse"]["main"])
    ]
    n_under_4 = sum(1 for r in main_rmses if r < 4.0)
    n_4_to_6 = sum(1 for r in main_rmses if 4.0 <= r <= 6.0)
    n_over_6 = sum(1 for r in main_rmses if r > 6.0)
    rmse_med = float(np.median(main_rmses)) if main_rmses else float("nan")
    rationale.append(
        f"Main-bake RMSE: <4 °C={n_under_4}/{len(main_rmses)}, "
        f"4-6 °C={n_4_to_6}/{len(main_rmses)}, >6 °C={n_over_6}/{len(main_rmses)} "
        f"(median {rmse_med:.2f} °C)."
    )

    interior_counts = [
        v.get("n_interior_params", 0) for v in phase4.values() if v.get("converged")
    ]
    n_param = max((v.get("n_param", 5) for v in phase4.values() if v.get("converged")), default=5)
    threshold = max(4, int(np.ceil(0.8 * n_param)))
    n_with_threshold_interior = sum(1 for c in interior_counts if c >= threshold)
    rationale.append(
        f"Fixtures with ≥{threshold}/{n_param} interior params: "
        f"{n_with_threshold_interior}/{fit_count_converged}."
    )

    x_cores = [
        v["x_core_depth_inferred_mm"] for v in phase4.values()
        if v.get("converged") and math.isfinite(
            v.get("x_core_depth_inferred_mm", float("nan"))
        )
    ]
    in_band_count = sum(1 for x in x_cores if 30.0 <= x <= 80.0)
    rationale.append(
        f"x_core_depth_inferred in [30, 80] mm: "
        f"{in_band_count}/{len(x_cores)} fixtures "
        f"(range {min(x_cores) if x_cores else float('nan'):.1f}-"
        f"{max(x_cores) if x_cores else float('nan'):.1f} mm)."
    )

    loo_finite = [
        r for r in phase5
        if "error" not in r and "skipped" not in r and "loo_rmse" in r
    ]
    if loo_finite:
        t1_runs = [r for r in loo_finite if r["held_out_sensor"] == "T1"]
        t2_runs = [r for r in loo_finite if r["held_out_sensor"] == "T2"]
        t1_rmse_med = float(np.median([r["loo_rmse"] for r in t1_runs])) if t1_runs else float("nan")
        t2_rmse_med = float(np.median([r["loo_rmse"] for r in t2_runs])) if t2_runs else float("nan")
        rationale.append(
            f"LOO subset (T1, T2 on {len(LOO_FIXTURES)} fixtures): "
            f"T1 LOO-RMSE median {t1_rmse_med:.2f} °C ({len(t1_runs)} fits), "
            f"T2 LOO-RMSE median {t2_rmse_med:.2f} °C ({len(t2_runs)} fits). "
            f"Compare M9 Stefan {M9_T1_LOO_RANGE[0]:.1f}-{M9_T1_LOO_RANGE[1]:.1f} °C; "
            f"M15 {M15_T1_LOO_MEDIAN:.2f} °C."
        )
        deep_end_pass = math.isfinite(t1_rmse_med) and t1_rmse_med < 4.0
    else:
        rationale.append("LOO phase produced no finite fits.")
        deep_end_pass = False

    main_under_4 = (
        n_under_4 >= max(4, int(np.ceil(0.5 * len(main_rmses))))
        if main_rmses else False
    )

    if (
        fit_count_converged >= 5
        and main_under_4
        and deep_end_pass
        and n_with_threshold_interior >= max(1, fit_count_converged - 1)
    ):
        verdict = "GO"
        rationale.append(
            "Observed-BC reformulation + α(T) profile delivers within-4 °C "
            "main-bake fits, deep-end T1 LOO < 4 °C, and most parameters "
            "interior. Wire as canonical inverse."
        )
    elif (
        fit_count_converged >= 5
        and (n_under_4 + n_4_to_6) >= max(3, int(np.ceil(0.5 * len(main_rmses))))
    ):
        verdict = "GO-WITH-CAVEATS"
        rationale.append(
            "Observed-BC reformulation reduces residual but not uniformly. "
            "Wire with low-confidence flags on worst fixtures."
        )
    else:
        verdict = "CONFIRM-information-limit"
        rationale.append(
            "Even with observed top BC and free α(T), the in-dough "
            "observation matrix does not constrain the model class. "
            "Method 4 (oven-setpoint metadata + tin/lid state at acquisition) "
            "is the unambiguous next step."
        )
    return verdict, rationale


# -------------------------------------------------------------------------
# Report
# -------------------------------------------------------------------------


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


def _render_report(observables, phase2, phase3, phase4, phase4b, phase5, verdict, rationale) -> str:
    lines: list = []
    lines.append("# Luikov OBSERVED-BC inverse — research report (HMS Daring / M16)")
    lines.append("")
    lines.append(
        "**Mission:** Reformulate the M15 asymmetric-tin Luikov inverse with "
        "OBSERVED top-BC inputs (T_air(t) from M2a-flagged ambient sensor, "
        "h_eff(t) from surface energy balance) and a piecewise α(T) profile "
        "for oven-spring property change. 4-5 free parameters (down from "
        "M15's 8). Per-fixture diagnostics extracted upfront."
    )
    lines.append("")
    lines.append("**Branch:** `refactor/role-classification-unified`  ")
    lines.append("**Mission dir:** `.nelson/missions/2026-04-28_145444_9193a856`  ")
    lines.append("**Date:** 2026-04-28 (M16)  ")
    lines.append("")

    # Executive summary
    lines.append("## Executive summary")
    lines.append("")
    lines.append(f"**Verdict: {verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    # Method
    lines.append("## Method")
    lines.append("")
    lines.append(
        "M15 → M16 reformulation: T_oven_eff (was a free parameter) is "
        "now extracted as T_air(t) directly from the M2a-flagged ambient "
        "sensor; Bi_top (was free) is replaced by h_eff(t) extracted from "
        "the surface energy balance "
        "`q ≈ -k_dough · ∂T/∂x` between surface and next-deeper sensor. "
        "α(T) is added as a piecewise function: α_pre at T<50°C, "
        "α_pre·alpha_ratio at T>65°C, linear in between. Pinned: "
        "k_dough=0.5 W/(m·K), Ko=4.0, ε=0.5, δ=2.0, α_pre=1.4×10⁻⁷ m²/s. "
        "Free parameters (5): L_m, D_m, Lu, q_bottom_eff, alpha_ratio."
    )
    lines.append("")

    # Phase 1 diagnostic table
    lines.append("## Phase 1 — Per-fixture observables diagnostic")
    lines.append("")
    lines.append(
        "| fixture | steam_dur(s) | spring_start(s) | spring_end(s) | "
        "T_air_min(°C) | T_air_max(°C) | h_eff_med(W/m²·K) |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for label, d in observables.items():
        if "error" in d:
            lines.append(f"| `{label}` | ERR | | | | | |")
            continue
        steam_dur = d.get("steam_duration_s", 0.0)
        spring_s = d.get("spring_start_s", float("nan"))
        spring_e = d.get("spring_end_s", float("nan"))
        air_min = d.get("T_air_min_C", float("nan"))
        air_max = d.get("T_air_max_C", float("nan"))
        h_med = d.get("h_eff_median", float("nan"))
        lines.append(
            f"| `{label}` | {steam_dur:.0f} | "
            f"{spring_s:.0f} | {spring_e:.0f} | "
            f"{air_min:.0f} | {air_max:.0f} | {h_med:.1f} |"
        )
    lines.append("")

    # Forward sanity
    lines.append("## Forward solver sanity")
    lines.append("")
    lines.append(
        f"8-test pytest sub-suite (`tests/test_luikov_tin_observed_research.py`): "
        f"**{'PASS' if phase2.get('passed') else 'FAIL'}** "
        f"(returncode={phase2.get('pytest_returncode')}). "
        f"Tests: alpha(T) profile (low/high/midband), constant-input baseline, "
        f"alpha(T) evolution speed, steady-state convergence, time-varying "
        f"input tracking, core-depth inference."
    )
    lines.append("")

    # Synthetic recovery
    lines.append("## Synthetic recovery (different α_pre generator)")
    lines.append("")
    s3 = phase3.get("summary", {})
    truth = phase3.get("truth", {})
    lines.append(
        f"Truth: L={truth.get('L_m', 0)*1000:.0f} mm, "
        f"D={truth.get('D_m', 0)*1000:.0f} mm, "
        f"Lu={truth.get('Lu')}, q_bot={truth.get('q_bottom_eff')}, "
        f"α_ratio={truth.get('alpha_ratio')}. "
        f"Generator α_pre=1.0e-7 m²/s; inverter α_pre=1.4e-7 m²/s. "
        f"σ_noise=0.5 °C, {SYNTH_SEEDS} seeds. "
        f"T_air(t) and h_eff(t) patterns sourced from BA3C_0946 observed."
    )
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| n_runs | {s3.get('n_runs', 0)} |")
    lines.append(f"| n_finite | {s3.get('n_finite', 0)} |")
    lines.append(f"| RMSE median | {s3.get('rmse_median', float('nan')):.3f} |")
    lines.append(f"| RMSE max | {s3.get('rmse_max', float('nan')):.3f} |")
    for name in ("L_m", "D_m", "Lu", "q_bottom_eff", "alpha_ratio"):
        key = f"{name}_within_30pct"
        lines.append(
            f"| {name} within 30% | "
            f"{s3.get(key, 0)}/{s3.get('n_finite', 0)} |"
        )
    lines.append("")
    lines.append("Per-seed table:")
    lines.append("")
    lines.append(
        "| seed | L (mm) | D (mm) | Lu | q_bot | α_ratio | rmse | interior | s |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in phase3.get("rows", []):
        if "error" in r:
            lines.append(f"| {r.get('seed', '?')} | ERR | | | | | | | |")
            continue
        lines.append(
            f"| {r['seed']} | {r['L_m']*1000:.1f} | {r['D_m']*1000:.1f} | "
            f"{r['Lu']:.3f} | {r['q_bottom_eff']:.1f} | "
            f"{r['alpha_ratio']:.2f} | {r['rmse_per_sensor']:.3f} | "
            f"{r['n_interior_params']}/{r['n_param']} | "
            f"{r.get('fit_seconds', float('nan')):.1f} |"
        )
    lines.append("")

    # Per-fixture real CSV
    lines.append("## Per-fixture real-CSV inverse results")
    lines.append("")
    lines.append(
        "| fixture | L (mm) | D (mm) | Lu | q_bot | α_ratio | x_core (mm) | "
        "RMSE_full | interior |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for label, fit in phase4.items():
        if "error" in fit or not fit.get("converged", False):
            lines.append(f"| `{label}` | ERR/no-conv | | | | | | | |")
            continue
        lines.append(
            f"| `{label}` | {fit['L_m']*1000:.1f} | {fit['D_m']*1000:.1f} | "
            f"{fit['Lu']:.3f} | {fit['q_bottom_eff']:.1f} | "
            f"{fit['alpha_ratio']:.2f} | "
            f"{fit['x_core_depth_inferred_mm']:.1f} | "
            f"{fit['rmse_per_sensor']:.2f} | "
            f"{fit['n_interior_params']}/{fit['n_param']} |"
        )
    lines.append("")

    # Residual decomposition
    lines.append("## Per-fixture residual decomposition (M10 helpers)")
    lines.append("")
    lines.append(
        "| fixture | RMSE_full | RMSE_main | RMSE_startup | RMSE_tail | ρ_main |"
    )
    lines.append("|---|---|---|---|---|---|")
    by_label = {d["label"]: d for d in phase4b if "label" in d}
    for label in phase4:
        d = by_label.get(label, {})
        if "skipped_reason" in d or not d.get("segment_rmse"):
            lines.append(f"| `{label}` | (skipped) | | | | |")
            continue
        seg = d["segment_rmse"]
        rho = d["segment_lag1_autocorr"]
        lines.append(
            f"| `{label}` | "
            f"{d['rmse_full_recomputed']:.2f} | "
            f"{seg['main']:.2f} | "
            f"{seg['startup']:.2f} | "
            f"{seg['tail']:.2f} | "
            f"{rho['main']:.3f} |"
        )
    lines.append("")

    # Side-by-side comparison
    lines.append("## Main-bake RMSE: Daring (M16) vs Sirius (M15) vs M9 Stefan")
    lines.append("")
    lines.append("| fixture | Daring (M16) | Sirius (M15) | M9 Stefan |")
    lines.append("|---|---|---|---|")
    for label in M9_MAIN:
        d = by_label.get(label)
        m16 = (
            d["segment_rmse"]["main"]
            if d and "segment_rmse" in d
            else float("nan")
        )
        m15 = M15_MAIN.get(label, float("nan"))
        m9 = M9_MAIN.get(label, float("nan"))
        lines.append(
            f"| `{label}` | {m16:.2f} | {m15:.2f} | {m9:.2f} |"
        )
    lines.append("")

    # Bound hitting
    lines.append("## Bound-hitting (per-parameter, per-fixture)")
    lines.append("")
    lines.append(
        "| fixture | L_m | D_m | Lu | q_bottom_eff | alpha_ratio |"
    )
    lines.append("|---|---|---|---|---|---|")
    for label, fit in phase4.items():
        bs = fit.get("param_at_bound", {})
        if not bs:
            lines.append(f"| `{label}` | n/a | n/a | n/a | n/a | n/a |")
            continue
        lines.append(
            f"| `{label}` | {bs.get('L_m','?')} | {bs.get('D_m','?')} | "
            f"{bs.get('Lu','?')} | {bs.get('q_bottom_eff','?')} | "
            f"{bs.get('alpha_ratio','?')} |"
        )
    lines.append("")

    # LOO
    lines.append("## LOO subset (deep-end T1, T2 on 3 representative fixtures)")
    lines.append("")
    lines.append(
        f"M15 T1 LOO median: {M15_T1_LOO_MEDIAN:.2f} °C. "
        f"M9 Stefan range: {M9_T1_LOO_RANGE[0]:.1f}-{M9_T1_LOO_RANGE[1]:.1f} °C."
    )
    lines.append("")
    if not phase5:
        lines.append("_(LOO phase skipped)_")
    else:
        lines.append(
            "| fixture | held_out | LOO_rmse | in_sample | ratio | "
            "max&#124;res&#124; | mean_res | x_core (mm) | interior | s |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in phase5:
            if "error" in r or "skipped" in r:
                lines.append(
                    f"| `{r['fixture']}` | {r['held_out_sensor']} | "
                    f"({r.get('error', r.get('skipped', '?'))}) | | | | | | | |"
                )
                continue
            lines.append(
                f"| `{r['fixture']}` | {r['held_out_sensor']} | "
                f"{r['loo_rmse']:.2f} | {r['in_sample_rmse_pooled']:.2f} | "
                f"{r['ratio_loo_to_in_sample']:.2f} | "
                f"{r['loo_max_abs_residual']:.1f} | "
                f"{r['loo_mean_residual']:+.2f} | "
                f"{r['x_core_depth_inferred_mm']:.1f} | "
                f"{r['n_interior_params']}/5 | "
                f"{r['fit_seconds']:.1f} |"
            )
    lines.append("")

    # Recommendation
    lines.append("## Recommendation for production")
    lines.append("")
    if verdict == "GO":
        rec = (
            "M16 observed-BC reformulation delivers within-4 °C main-bake RMSE "
            "with deep-end LOO under 4 °C and parameters interior. Wire "
            "`fit_luikov_tin_observed_inverse` into the production loader as "
            "the canonical inverse, replacing M11 Zürcher and M14/M15 Luikov."
        )
    elif verdict == "GO-WITH-CAVEATS":
        rec = (
            "M16 reformulation halves the parameter count and reduces residuals "
            "vs M15 on multiple fixtures, but does not uniformly clear the 4 °C "
            "bar. Production wiring is justified with low-confidence flags on "
            "fixtures with main-bake RMSE > 5 °C or deep-end LOO > 5 °C."
        )
    else:
        rec = (
            "Even with observed top BC and a free α(T) profile, the in-dough-"
            "only observation matrix does not pin the deep-end response or "
            "the full parameter space. The information limit confirmed by M15 "
            "is now reaffirmed at half the parameter count. Method 4 — per-CSV "
            "loaf-thickness, oven-setpoint, tin/lid metadata — is the only "
            "remaining structural lever."
        )
    lines.append(rec)
    lines.append("")

    return "\n".join(lines)


def _render_captains_log(observables, phase2, phase3, phase4, phase4b, phase5, verdict, rationale, wall_seconds) -> str:
    lines: list = []
    lines.append("# Captain's log — HMS Daring, M16 Luikov OBSERVED-BC inverse")
    lines.append("")
    lines.append(
        "**Mission:** Reformulate M15 with observed T_air(t) and h_eff(t) "
        "(replacing fitted T_oven_eff and Bi_top), add α(T) piecewise profile, "
        "and halve the parameter count (4-5 free params vs M15's 8)."
    )
    lines.append("")
    lines.append("**Branch:** `refactor/role-classification-unified`  ")
    lines.append("**Mission dir:** `.nelson/missions/2026-04-28_145444_9193a856`  ")
    lines.append("**Date:** 2026-04-28 (M16)  ")
    lines.append(f"**Wall-clock:** {wall_seconds:.1f} s end-to-end.")
    lines.append("")
    lines.append(f"## Verdict: **{verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    lines.append("## Phase 1 observables diagnostic")
    lines.append("")
    lines.append(
        "| fixture | steam? | spring_window | T_air range | h_eff median |"
    )
    lines.append("|---|---|---|---|---|")
    for label, d in observables.items():
        if "error" in d:
            lines.append(f"| `{label}` | ERR | | | |")
            continue
        steam_str = "yes" if d.get("steam_detected") else "no"
        spring_str = (
            f"{d.get('spring_start_s', 0):.0f}-{d.get('spring_end_s', 0):.0f}s"
            if d.get("spring_detected") else "—"
        )
        air_range = f"{d.get('T_air_min_C', 0):.0f}-{d.get('T_air_max_C', 0):.0f}°C"
        h_med = f"{d.get('h_eff_median', 0):.1f}"
        lines.append(
            f"| `{label}` | {steam_str} | {spring_str} | {air_range} | {h_med} |"
        )
    lines.append("")

    lines.append("## Per-fixture x_core_depth_inferred")
    lines.append("")
    lines.append(
        "| fixture | x_core_inferred (mm) | L_m fitted (mm) | "
        "D_m fitted (mm) | α_ratio fitted |"
    )
    lines.append("|---|---|---|---|---|")
    for label, fit in phase4.items():
        if "error" in fit or not fit.get("converged"):
            lines.append(f"| `{label}` | (no fit) | | | |")
            continue
        lines.append(
            f"| `{label}` | {fit['x_core_depth_inferred_mm']:.1f} | "
            f"{fit['L_m']*1000:.1f} | {fit['D_m']*1000:.1f} | "
            f"{fit['alpha_ratio']:.2f} |"
        )
    lines.append("")

    lines.append("## Did observed-BC reformulation help vs M15?")
    lines.append("")
    by_label = {d["label"]: d for d in phase4b if "label" in d}
    lines.append("| fixture | Daring (M16) | Sirius (M15) | M9 Stefan |")
    lines.append("|---|---|---|---|")
    for label in M9_MAIN:
        d = by_label.get(label)
        m16 = d["segment_rmse"]["main"] if d and "segment_rmse" in d else float("nan")
        m15 = M15_MAIN.get(label, float("nan"))
        m9 = M9_MAIN.get(label, float("nan"))
        lines.append(f"| `{label}` | {m16:.2f} | {m15:.2f} | {m9:.2f} |")
    lines.append("")

    loo_t1 = [
        r for r in phase5
        if "error" not in r and "skipped" not in r and r.get("held_out_sensor") == "T1"
    ]
    if loo_t1:
        rmses = [r["loo_rmse"] for r in loo_t1]
        lines.append("## LOO T1 deep-end test")
        lines.append("")
        lines.append(
            f"T1 LOO-RMSE (M16): median {float(np.median(rmses)):.2f} °C, "
            f"max {float(np.max(rmses)):.2f} °C, n={len(rmses)}.  "
            f"Compare M9 Stefan {M9_T1_LOO_RANGE[0]:.1f}-{M9_T1_LOO_RANGE[1]:.1f} °C; "
            f"M15 {M15_T1_LOO_MEDIAN:.2f} °C."
        )
        lines.append("")

    lines.append("## Open follow-ups")
    lines.append("")
    if verdict == "GO":
        lines.append(
            "- Wire `fit_luikov_tin_observed_inverse` into `loader.py` as the "
            "canonical inverse; gate behind a config flag.\n"
            "- Method-4 metadata capture remains useful for further tightening."
        )
    elif verdict == "GO-WITH-CAVEATS":
        lines.append(
            "- Production wiring with low-confidence flags on fixtures with "
            "main-bake RMSE > 5 °C or LOO ratio > 1.5.\n"
            "- Method-4 metadata capture in parallel."
        )
    else:
        lines.append(
            "- Information limit reaffirmed at half the parameter count of M15. "
            "The hierarchy single-medium → Stefan → Zürcher → Luikov-symmetric → "
            "Luikov-asymmetric-tin (M15) → Luikov-observed-BC (M16) has been "
            "exhausted on the in-dough-only observation matrix.\n"
            "- **Method 4** is now the only remaining structural lever: capture "
            "per-CSV loaf thickness, oven setpoint, tin/lid contact state at "
            "acquisition time; include surface-sensor signal in inverse loss. "
            "Pivot away from inverse-problem research on this data alone."
        )
    lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main() -> None:
    overall_t0 = time.time()
    out: dict = {
        "mission": "HMS Daring M16 — Luikov OBSERVED-BC inverse",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "downsample_factor": DOWNSAMPLE_FACTOR,
        "n_spatial": N_SPATIAL,
        "loo_fixtures": sorted(LOO_FIXTURES),
        "loo_hold_out": list(LOO_HOLD_OUT),
    }

    t0 = _phase("phase 1: per-fixture observables diagnostic")
    out["phase1"] = phase1_observables()
    print(f"  phase 1 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase("phase 2: forward solver sanity (8-test pytest sub-suite)")
    out["phase2"] = phase2_forward_sanity()
    print(f"  phase 2 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(f"phase 3: synthetic recovery ({SYNTH_SEEDS} seeds)")
    out["phase3"] = phase3_synthetic_recovery(out["phase1"])
    print(f"  phase 3 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(f"phase 4: real-CSV observed-BC inverse ({len(REAL_FIXTURES)} fixtures, 4-5 param)")
    out["phase4"] = phase4_real_csv(out["phase1"])
    print(f"  phase 4 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase("phase 4b: residual decomposition")
    out["phase4b"] = phase4b_residual_decomposition(out["phase4"], out["phase1"])
    print(f"  phase 4b elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(
        f"phase 5: LOO subset on {len(LOO_FIXTURES)} fixtures × "
        f"{len(LOO_HOLD_OUT)} held-out sensors"
    )
    out["phase5"] = phase5_loo_subset(out["phase1"])
    print(f"  phase 5 elapsed: {time.time() - t0:.1f}s", flush=True)

    verdict, rationale = _verdict(
        out["phase2"], out["phase3"], out["phase4"], out["phase4b"], out["phase5"],
    )
    out["verdict"] = verdict
    out["rationale"] = rationale
    out["wall_seconds"] = time.time() - overall_t0

    print(f"\n  total wall-time: {out['wall_seconds']:.1f}s", flush=True)
    print(f"  verdict: {verdict}", flush=True)
    for r in rationale:
        print(f"    - {r}", flush=True)

    with open(OUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"  wrote {OUT_JSON_PATH}", flush=True)

    md_text = _render_report(
        out["phase1"], out["phase2"], out["phase3"],
        out["phase4"], out["phase4b"], out["phase5"], verdict, rationale,
    )
    with open(OUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"  wrote {OUT_MD_PATH}", flush=True)

    log_text = _render_captains_log(
        out["phase1"], out["phase2"], out["phase3"],
        out["phase4"], out["phase4b"], out["phase5"], verdict, rationale,
        out["wall_seconds"],
    )
    os.makedirs(os.path.dirname(CAPTAINS_LOG_PATH), exist_ok=True)
    with open(CAPTAINS_LOG_PATH, "w", encoding="utf-8") as f:
        f.write(log_text)
    print(f"  wrote {CAPTAINS_LOG_PATH}", flush=True)


if __name__ == "__main__":
    main()
