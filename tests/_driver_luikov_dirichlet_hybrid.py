"""HMS Endeavour — M17 Luikov-Dirichlet hybrid driver (end-to-end).

Combines M9's Dirichlet top BC (anchored to M2a-detected surface
temperature) with M15/M16's moisture/asymmetric-tin/α(T) physics. 5 free
parameters total: L, D, Lu, q_bottom_eff, alpha_ratio.

Phases:
  1. Forward sanity (5-test pytest sub-suite)
  2. Synthetic recovery (different α_pre in generator vs inverter)
  3. Real-CSV inverse (7 fixtures)
  3b. Residual decomposition (M10 helpers)
  4. LOO subset (T1, T2 on 3 representative fixtures)

Outputs:
  - tests/baselines/luikov_dirichlet_hybrid_research.json
  - tests/baselines/luikov_dirichlet_hybrid_research.md
  - .nelson/missions/2026-04-28_223435_3acb09f9/captains-log.md
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
import pytest

from src.data.spatial_reconstruction.classifier import classify  # noqa: E402
from src.data.spatial_reconstruction.geometry import lookup_geometry  # noqa: E402
from src.data.spatial_reconstruction.luikov_dirichlet_hybrid import (  # noqa: E402
    PROBE_T_SPAN_M,
    SENSOR_NAMES_DEFAULT,
    SENSOR_POSITIONS_MM_FROM_TIP,
    fit_luikov_dirichlet_hybrid_inverse,
    infer_core_depth_from_forward,
    solve_luikov_dirichlet_hybrid_forward,
)
from src.data.spatial_reconstruction.profile import (  # noqa: E402
    interpolate_temperature_series_at,
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
OUT_JSON_PATH = os.path.join(
    BASE_DIR, "baselines", "luikov_dirichlet_hybrid_research.json"
)
OUT_MD_PATH = os.path.join(
    BASE_DIR, "baselines", "luikov_dirichlet_hybrid_research.md"
)
CAPTAINS_LOG_PATH = os.path.join(
    os.path.dirname(BASE_DIR),
    ".nelson",
    "missions",
    "2026-04-28_223435_3acb09f9",
    "captains-log.md",
)

DOWNSAMPLE_FACTOR = 4
N_SPATIAL = 40
SAMPLE_PERIOD_S = 5.0

LOO_FIXTURES = {"BA3C_0946", "100098DE_1351", "wonder_white"}
LOO_HOLD_OUT = ("T1", "T2")

SYNTH_SEEDS = 5

# Comparators (per briefing).
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
M16_MAIN: dict[str, float] = {}  # populated from M16 baseline JSON if present

M9_T1_LOO_RANGE = (9.0, 21.0)
M15_T1_LOO_MEDIAN = 11.74


def _phase(name: str) -> float:
    print(f"\n=== {name} ===", flush=True)
    return time.time()


def _classifier_x_surface(spec: dict) -> float:
    """M2a continuous interface position normalised to probe span."""
    df = _segmented_real_fixture(spec)
    geom = lookup_geometry(probe_sn=None, probe_model=None)
    a = classify(df, sample_period_ms=5000, probe_geometry=geom)
    if a.surface_assignment is None:
        return float(spec["x_surface"])
    return float(a.surface_assignment.position_normalised)


def _surface_K_series(df: pd.DataFrame, x_surface_norm: float) -> np.ndarray:
    """Build the per-timestep observed surface T(t) (Kelvin) at the M2a
    interface position via M6's spatial interpolation across all sensors.

    Probe normalised positions are i/7 for i in 0..7 (T1 at tip → 0, T8
    → 1), matching ``geometry.py``.
    """
    positions = tuple(i / 7.0 for i in range(8))
    surface_C = interpolate_temperature_series_at(
        df,
        positions=positions,
        x_target=float(x_surface_norm),
        sensors=SENSOR_NAMES_DEFAULT,
    ).to_numpy(dtype=float)
    return surface_C + 273.15


# -------------------------------------------------------------------------
# Phase 1 — Forward sanity (pytest sub-suite)
# -------------------------------------------------------------------------


def phase1_forward_sanity() -> dict:
    test_path = os.path.join(BASE_DIR, "test_luikov_dirichlet_hybrid_research.py")
    rc = pytest.main([test_path, "-v", "--tb=short", "-q"])
    return {"pytest_returncode": int(rc), "passed": int(rc) == 0}


# -------------------------------------------------------------------------
# Phase 2 — Synthetic recovery
# -------------------------------------------------------------------------


SYNTH_TRUTH = {
    "L_m": 0.095,
    "D_m": 0.065,
    "Lu": 0.10,
    "q_bottom_eff": 20.0,
    "alpha_ratio": 0.4,
}


def _synth_one(seed: int, noise_sigma_c: float) -> dict:
    truth = SYNTH_TRUTH
    n_t = 400
    t_grid = np.arange(n_t, dtype=float) * SAMPLE_PERIOD_S
    # Realistic surface profile rising from ~22 → ~107 °C over 1500 s
    T_surface_K = 295.0 + (380.0 - 295.0) * (1.0 - np.exp(-t_grid / 600.0))

    # Sensors that are below the M2a interface AND below the L bound.
    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    d_mm = truth["D_m"] * 1000.0 - p_mm
    L_mm = truth["L_m"] * 1000.0
    # x_surface in loaf frame:
    x_surf_norm = 0.65  # mid-probe surface for synthetic
    x_surf_loaf_mm = truth["D_m"] * 1000.0 - x_surf_norm * 95.0
    in_dough_mask = (d_mm > x_surf_loaf_mm + 0.5) & (d_mm < L_mm - 0.5)
    in_dough = [SENSOR_NAMES_DEFAULT[i] for i in range(8) if in_dough_mask[i]]
    if len(in_dough) < 3:
        # Fallback — pick the deepest few sensors regardless of x_surf.
        in_dough = ["T1", "T2", "T3"]
    d_in_m = (truth["D_m"] - p_mm[in_dough_mask] / 1000.0)

    fwd = solve_luikov_dirichlet_hybrid_forward(
        L_m=truth["L_m"],
        D_m=truth["D_m"],
        Lu=truth["Lu"],
        q_bottom_eff=truth["q_bottom_eff"],
        alpha_ratio=truth["alpha_ratio"],
        t_grid_s=t_grid,
        T_surface_K_t=T_surface_K,
        x_surface_continuous_normalised=x_surf_norm,
        T_initial_K=295.0,
        sample_x_m=d_in_m,
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
    # Build all 8 sensor columns: surface sensor synthesised from T_surface_K,
    # missing sensors use surface temperature (won't enter fit).
    surf_C = T_surface_K - 273.15
    for name in SENSOR_NAMES_DEFAULT:
        if name not in df.columns:
            df[name] = surf_C
    # Write the spatially-interpolated surface column as well.
    return {
        "df": df,
        "in_dough": in_dough,
        "x_surface_norm": x_surf_norm,
        "T_surface_K": T_surface_K,
    }


def phase2_synthetic_recovery() -> dict:
    truth = SYNTH_TRUTH
    rows: list = []
    for seed in range(SYNTH_SEEDS):
        synth = _synth_one(seed, noise_sigma_c=0.5)
        t0 = time.time()
        try:
            r = fit_luikov_dirichlet_hybrid_inverse(
                df=synth["df"],
                in_dough_sensors=synth["in_dough"],
                T_surface_K_t=synth["T_surface_K"],
                x_surface_continuous_normalised=synth["x_surface_norm"],
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                max_iter=400,
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
# Phase 3 — Real-CSV inverse
# -------------------------------------------------------------------------


def phase3_real_csv() -> dict:
    out: dict = {}
    for spec in REAL_FIXTURES:
        df = _segmented_real_fixture(spec)
        x_surf_norm = _classifier_x_surface(spec)
        T_surface_K = _surface_K_series(df, x_surf_norm)

        t0 = time.time()
        try:
            r = fit_luikov_dirichlet_hybrid_inverse(
                df=df,
                in_dough_sensors=spec["in_dough"],
                T_surface_K_t=T_surface_K,
                x_surface_continuous_normalised=x_surf_norm,
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                max_iter=600,
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
                "x_surface_continuous_normalised": float(x_surf_norm),
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
                f"x_surf={x_surf_norm:.3f} "
                f"interior={r['n_interior_params']}/{r['n_param']} "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
    return out


# -------------------------------------------------------------------------
# Phase 3b — Residual decomposition
# -------------------------------------------------------------------------


def _forward_eval_at_fit(spec: dict, fit: dict) -> dict:
    df = _segmented_real_fixture(spec)
    x_surf_norm = float(fit["x_surface_continuous_normalised"])
    T_surface_K = _surface_K_series(df, x_surf_norm)

    in_dough = list(spec["in_dough"])
    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    pos_by_name = dict(zip(SENSOR_NAMES_DEFAULT, p_mm / 1000.0))
    p_obs_m = np.array([pos_by_name[s] for s in in_dough], dtype=float)
    d_obs_m = fit["D_m"] - p_obs_m
    x_surf_loaf = max(0.0, fit["D_m"] - x_surf_norm * PROBE_T_SPAN_M)
    d_clipped = np.clip(d_obs_m, x_surf_loaf, fit["L_m"])

    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    T_obs_C = np.column_stack(
        [df[s].to_numpy(dtype=float)[sl] for s in in_dough]
    )
    T_obs_K = T_obs_C + 273.15
    T_surf_obs = T_surface_K[sl]

    fwd = solve_luikov_dirichlet_hybrid_forward(
        L_m=fit["L_m"],
        D_m=fit["D_m"],
        Lu=fit["Lu"],
        q_bottom_eff=fit["q_bottom_eff"],
        alpha_ratio=fit["alpha_ratio"],
        t_grid_s=t_obs,
        T_surface_K_t=T_surf_obs,
        x_surface_continuous_normalised=x_surf_norm,
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


def phase3b_residual_decomposition(phase3: dict) -> list:
    decomps: list = []
    for spec in REAL_FIXTURES:
        fit = phase3.get(spec["label"], {})
        if not fit.get("converged", False) or "error" in fit:
            decomps.append(
                {"label": spec["label"], "skipped_reason": "did_not_converge"}
            )
            continue
        try:
            ev = _forward_eval_at_fit(spec, fit)
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
# Phase 4 — LOO subset
# -------------------------------------------------------------------------


def _loo_predict(fit: dict, df: pd.DataFrame, held_out: str, T_surface_K: np.ndarray, x_surf_norm: float) -> tuple:
    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    pos_by_name = dict(zip(SENSOR_NAMES_DEFAULT, p_mm / 1000.0))
    p_held_m = float(pos_by_name[held_out])
    d_held_m = fit["D_m"] - p_held_m
    x_surf_loaf = max(0.0, fit["D_m"] - x_surf_norm * PROBE_T_SPAN_M)
    d_clipped = np.array([max(x_surf_loaf, min(d_held_m, fit["L_m"]))], dtype=float)
    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    T_surf_obs = T_surface_K[sl]
    fwd = solve_luikov_dirichlet_hybrid_forward(
        L_m=fit["L_m"],
        D_m=fit["D_m"],
        Lu=fit["Lu"],
        q_bottom_eff=fit["q_bottom_eff"],
        alpha_ratio=fit["alpha_ratio"],
        t_grid_s=t_obs,
        T_surface_K_t=T_surf_obs,
        x_surface_continuous_normalised=x_surf_norm,
        T_initial_K=fit["T_initial_K"],
        sample_x_m=d_clipped,
        n_spatial=int(fit.get("n_spatial", N_SPATIAL)),
    )
    T_pred_held_C = fwd.T_field_K[:, 0] - 273.15
    T_obs_held_C = df[held_out].to_numpy(dtype=float)[sl]
    return T_pred_held_C, T_obs_held_C


def _loo_one(spec: dict, held_out: str) -> dict:
    df = _segmented_real_fixture(spec)
    x_surf_norm = _classifier_x_surface(spec)
    T_surface_K = _surface_K_series(df, x_surf_norm)
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
        result = fit_luikov_dirichlet_hybrid_inverse(
            df=df,
            in_dough_sensors=training,
            T_surface_K_t=T_surface_K,
            x_surface_continuous_normalised=x_surf_norm,
            downsample_factor=DOWNSAMPLE_FACTOR,
            n_spatial=N_SPATIAL,
            max_iter=600,
        )
    except Exception as exc:
        return {
            "fixture": spec["label"],
            "held_out_sensor": held_out,
            "training_sensors": training,
            "error": str(exc),
            "fit_seconds": time.time() - t0,
        }

    T_pred_held, T_obs_held = _loo_predict(result, df, held_out, T_surface_K, x_surf_norm)
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


def phase4_loo_subset() -> list:
    rows = []
    for spec in REAL_FIXTURES:
        if spec["label"] not in LOO_FIXTURES:
            continue
        for held in LOO_HOLD_OUT:
            r = _loo_one(spec, held)
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
# M16 baseline pull
# -------------------------------------------------------------------------


def _load_m16_main() -> dict:
    """Pull M16 main-bake RMSEs from prior baseline JSON if available."""
    p = os.path.join(BASE_DIR, "baselines", "luikov_tin_observed_research.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
        out: dict = {}
        for d in obj.get("phase4b", []):
            if "label" in d and "segment_rmse" in d:
                out[d["label"]] = float(d["segment_rmse"]["main"])
        return out
    except Exception:
        return {}


# -------------------------------------------------------------------------
# Verdict
# -------------------------------------------------------------------------


def _verdict(phase1: dict, phase2: dict, phase3: dict, phase3b: list, phase4: list) -> tuple[str, list]:
    rationale: list = []
    rationale.append(
        f"Forward sanity: 5-test pytest sub-suite "
        f"{'PASS' if phase1.get('passed') else 'FAIL'} "
        f"(returncode={phase1.get('pytest_returncode')})."
    )

    s2 = phase2.get("summary", {})
    rationale.append(
        f"Synthetic recovery (different α_pre: gen 1.0e-7 vs inv 1.4e-7; "
        f"{s2.get('n_finite', 0)}/{s2.get('n_runs', 0)} runs finite, "
        f"σ_noise=0.5 °C, {SYNTH_SEEDS} seeds): "
        f"RMSE median {s2.get('rmse_median', float('nan')):.3f} K; "
        f"L_m within 30%={s2.get('L_m_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"D_m within 30%={s2.get('D_m_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"Lu within 30%={s2.get('Lu_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"q_bot within 30%={s2.get('q_bottom_eff_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"α_ratio within 30%={s2.get('alpha_ratio_within_30pct', 0)}/{s2.get('n_finite', 0)}."
    )

    fit_count_converged = sum(1 for v in phase3.values() if v.get("converged", False))
    n_fixtures = len(phase3)
    rationale.append(
        f"Real-CSV 5-param convergence: {fit_count_converged}/{n_fixtures}."
    )

    main_rmses = [
        d["segment_rmse"]["main"]
        for d in phase3b
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
        v.get("n_interior_params", 0) for v in phase3.values() if v.get("converged")
    ]
    n_param_max = 5
    threshold = 3
    n_with_threshold_interior = sum(1 for c in interior_counts if c >= threshold)
    rationale.append(
        f"Fixtures with ≥{threshold}/{n_param_max} interior params: "
        f"{n_with_threshold_interior}/{fit_count_converged}."
    )

    x_cores = [
        v["x_core_depth_inferred_mm"] for v in phase3.values()
        if v.get("converged") and math.isfinite(
            v.get("x_core_depth_inferred_mm", float("nan"))
        )
    ]
    if x_cores:
        in_band_count = sum(1 for x in x_cores if 30.0 <= x <= 80.0)
        rationale.append(
            f"x_core_depth_inferred in [30, 80] mm: "
            f"{in_band_count}/{len(x_cores)} fixtures "
            f"(range {min(x_cores):.1f}-{max(x_cores):.1f} mm)."
        )
    else:
        rationale.append("No converged x_core_depth values.")

    loo_finite = [
        r for r in phase4
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
            "Surface-Dirichlet hybrid (M9 BC + M15/M16 physics) breaks the "
            "M9 5-11 °C floor; main-bake RMSE < 4 °C, T1 LOO < 4 °C, "
            "≥3/5 params interior. Wire as canonical inverse."
        )
    elif (
        fit_count_converged >= 5
        and (n_under_4 + n_4_to_6) >= max(3, int(np.ceil(0.5 * len(main_rmses))))
    ):
        verdict = "GO-WITH-CAVEATS"
        rationale.append(
            "Hybrid reduces residuals but does not uniformly clear 4 °C bar. "
            "Wire with low-confidence flags on worst fixtures."
        )
    else:
        verdict = "CONFIRM-information-limit"
        rationale.append(
            "Surface-Dirichlet was the right top BC choice — the physics "
            "additions (moisture, asymmetric tin, α(T)) do not break the "
            "M9 floor. The 5-11 °C residual is the structural information "
            "limit on the in-dough-only observation matrix. Method 4 "
            "(per-CSV oven-setpoint + tin/lid metadata) is the only "
            "remaining structural lever."
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


def _render_report(phase1, phase2, phase3, phase3b, phase4, verdict, rationale, m16_main) -> str:
    lines: list = []
    lines.append("# Luikov-Dirichlet HYBRID inverse — research report (HMS Endeavour / M17)")
    lines.append("")
    lines.append(
        "**Mission:** Combine M9's surface-Dirichlet top BC (anchored to "
        "the M2a-detected per-timestep spatially-interpolated surface "
        "temperature) with M15/M16's moisture/asymmetric-tin/α(T) physics. "
        "Single-hypothesis test of whether the M9 5-11 °C floor was "
        "BC-limited or physics-limited."
    )
    lines.append("")
    lines.append("**Branch:** `refactor/role-classification-unified`  ")
    lines.append("**Mission dir:** `.nelson/missions/2026-04-28_223435_3acb09f9`  ")
    lines.append("**Date:** 2026-04-28 (M17)  ")
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
        "Lineage: M9 Stefan (Dirichlet top, no moisture) → M15 Luikov-tin "
        "(asymmetric-tin Robin BCs, fitted T_oven_eff and Bi_top) → M16 "
        "(observed-Robin top BC via T_air(t), h_eff(t)) → **M17 Hybrid** "
        "(Dirichlet top BC anchored to spatially-interpolated surface, "
        "M16 bottom BC and α(T)). The Dirichlet form replaces the Robin "
        "top, which M16 found added more freedom than the in-dough data "
        "could constrain. The 5 free parameters are L, D, Lu, "
        "q_bottom_eff, alpha_ratio."
    )
    lines.append("")
    lines.append("**Top BC**:")
    lines.append("")
    lines.append("```")
    lines.append("T(x_surface_in_loaf, t) = T_observed(t)")
    lines.append("x_surface_in_loaf = D - x_surface_continuous_normalised * 0.095 m")
    lines.append("T_observed(t) = interpolate_temperature_series_at(M2a x_surface)")
    lines.append("```")
    lines.append("")

    # Forward sanity
    lines.append("## Forward solver sanity")
    lines.append("")
    lines.append(
        f"5-test pytest sub-suite (`tests/test_luikov_dirichlet_hybrid_research.py`): "
        f"**{'PASS' if phase1.get('passed') else 'FAIL'}** "
        f"(returncode={phase1.get('pytest_returncode')}). Tests: Dirichlet "
        f"surface anchoring, constant-surface steady-state, α(T) transition, "
        f"bottom BC heat flux response, core-depth inference."
    )
    lines.append("")

    # Synthetic recovery
    lines.append("## Synthetic recovery (different α_pre generator vs inverter)")
    lines.append("")
    s2 = phase2.get("summary", {})
    truth = phase2.get("truth", {})
    lines.append(
        f"Truth: L={truth.get('L_m', 0)*1000:.0f} mm, "
        f"D={truth.get('D_m', 0)*1000:.0f} mm, "
        f"Lu={truth.get('Lu')}, q_bot={truth.get('q_bottom_eff')}, "
        f"α_ratio={truth.get('alpha_ratio')}. "
        f"Generator α_pre=1.0e-7 m²/s; inverter α_pre=1.4e-7 m²/s. "
        f"σ_noise=0.5 °C, {SYNTH_SEEDS} seeds. "
        f"Surface profile: 295 K → 380 K (1 - exp(-t/600))."
    )
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| n_runs | {s2.get('n_runs', 0)} |")
    lines.append(f"| n_finite | {s2.get('n_finite', 0)} |")
    lines.append(f"| RMSE median | {s2.get('rmse_median', float('nan')):.3f} |")
    lines.append(f"| RMSE max | {s2.get('rmse_max', float('nan')):.3f} |")
    for name in ("L_m", "D_m", "Lu", "q_bottom_eff", "alpha_ratio"):
        key = f"{name}_within_30pct"
        lines.append(
            f"| {name} within 30% | "
            f"{s2.get(key, 0)}/{s2.get('n_finite', 0)} |"
        )
    lines.append("")
    lines.append("Per-seed table:")
    lines.append("")
    lines.append(
        "| seed | L (mm) | D (mm) | Lu | q_bot | α_ratio | rmse | interior | s |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in phase2.get("rows", []):
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
        "| fixture | L (mm) | D (mm) | Lu | q_bot | α_ratio | x_surf_loaf (mm) | "
        "x_core (mm) | RMSE_full | interior |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for label, fit in phase3.items():
        if "error" in fit or not fit.get("converged", False):
            lines.append(f"| `{label}` | ERR/no-conv | | | | | | | | |")
            continue
        lines.append(
            f"| `{label}` | {fit['L_m']*1000:.1f} | {fit['D_m']*1000:.1f} | "
            f"{fit['Lu']:.3f} | {fit['q_bottom_eff']:.1f} | "
            f"{fit['alpha_ratio']:.2f} | "
            f"{fit.get('x_surface_in_loaf_mm', float('nan')):.1f} | "
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
    by_label = {d["label"]: d for d in phase3b if "label" in d}
    for label in phase3:
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

    # Side-by-side comparison: M9 vs M15 vs M16 vs M17
    lines.append("## Main-bake RMSE: M9 Stefan vs M15 Luikov-tin vs M16 observed-BC vs M17 hybrid")
    lines.append("")
    lines.append("| fixture | M17 hybrid | M16 obs-BC | M15 Luikov-tin | M9 Stefan |")
    lines.append("|---|---|---|---|---|")
    for label in M9_MAIN:
        d = by_label.get(label)
        m17 = (
            d["segment_rmse"]["main"]
            if d and "segment_rmse" in d
            else float("nan")
        )
        m16 = m16_main.get(label, float("nan"))
        m15 = M15_MAIN.get(label, float("nan"))
        m9 = M9_MAIN.get(label, float("nan"))
        lines.append(
            f"| `{label}` | {m17:.2f} | {m16:.2f} | {m15:.2f} | {m9:.2f} |"
        )
    lines.append("")

    # Bound hitting
    lines.append("## Bound-hitting (per-parameter, per-fixture)")
    lines.append("")
    lines.append(
        "| fixture | L_m | D_m | Lu | q_bottom_eff | alpha_ratio |"
    )
    lines.append("|---|---|---|---|---|---|")
    for label, fit in phase3.items():
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

    # Correlation summary
    lines.append("## 5×5 correlation matrix max|off-diag| per fixture")
    lines.append("")
    lines.append("| fixture | max&#124;ρ_off&#124; |")
    lines.append("|---|---|")
    for label, fit in phase3.items():
        v = fit.get("max_abs_off_diag_correlation", float("nan"))
        try:
            vv = float(v)
        except Exception:
            vv = float("nan")
        if math.isfinite(vv):
            lines.append(f"| `{label}` | {vv:.3f} |")
        else:
            lines.append(f"| `{label}` | n/a |")
    lines.append("")

    # LOO
    lines.append("## LOO subset (deep-end T1, T2 on 3 representative fixtures)")
    lines.append("")
    lines.append(
        f"M9 Stefan T1 LOO range: {M9_T1_LOO_RANGE[0]:.1f}-{M9_T1_LOO_RANGE[1]:.1f} °C. "
        f"M15 T1 LOO median: {M15_T1_LOO_MEDIAN:.2f} °C."
    )
    lines.append("")
    if not phase4:
        lines.append("_(LOO phase skipped)_")
    else:
        lines.append(
            "| fixture | held_out | LOO_rmse | in_sample | ratio | "
            "max&#124;res&#124; | mean_res | x_core (mm) | interior | s |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for r in phase4:
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
            "M17 hybrid breaks the M9 floor: Dirichlet top + α(T) + tin "
            "bottom delivers within-4 °C main-bake RMSE with deep-end T1 "
            "LOO under 4 °C and ≥3/5 parameters interior. Wire "
            "`fit_luikov_dirichlet_hybrid_inverse` into the production "
            "loader as the canonical inverse, replacing M11 Zürcher and "
            "M14/M15 Luikov."
        )
    elif verdict == "GO-WITH-CAVEATS":
        rec = (
            "Hybrid improves on M9/M15/M16 on multiple fixtures but does "
            "not uniformly clear the 4 °C bar. Production wiring is "
            "justified with low-confidence flags on fixtures with "
            "main-bake RMSE > 5 °C or deep-end LOO > 5 °C."
        )
    else:
        rec = (
            "The surface-Dirichlet BC was the right top BC choice. The "
            "M15/M16 physics additions (moisture, asymmetric-tin, α(T)) "
            "do not break the M9 5-11 °C information limit. The "
            "hierarchy single-medium → Stefan → Zürcher → Luikov "
            "(symmetric → asymmetric-tin → observed-Robin → "
            "surface-Dirichlet hybrid) has been exhausted on the "
            "in-dough-only observation matrix. **Method 4 is final**: "
            "capture per-CSV loaf thickness, oven setpoint, tin/lid "
            "contact at acquisition, and include surface-sensor signal "
            "in the inverse loss."
        )
    lines.append(rec)
    lines.append("")

    return "\n".join(lines)


def _render_captains_log(phase1, phase2, phase3, phase3b, phase4, verdict, rationale, wall_seconds, m16_main) -> str:
    lines: list = []
    lines.append("# Captain's log — HMS Endeavour, M17 Luikov-Dirichlet hybrid inverse")
    lines.append("")
    lines.append(
        "**Mission:** Single-hypothesis test of the surface-Dirichlet top "
        "BC (anchored to M2a-detected spatially-interpolated surface "
        "temperature) combined with M15/M16's moisture, asymmetric-tin "
        "and α(T) physics. 5 free parameters total: L, D, Lu, "
        "q_bottom_eff, alpha_ratio."
    )
    lines.append("")
    lines.append("**Branch:** `refactor/role-classification-unified`  ")
    lines.append("**Mission dir:** `.nelson/missions/2026-04-28_223435_3acb09f9`  ")
    lines.append("**Date:** 2026-04-28 (M17)  ")
    lines.append(f"**Wall-clock:** {wall_seconds:.1f} s end-to-end.")
    lines.append("")
    lines.append(f"## Verdict: **{verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    lines.append("## Per-fixture x_core_depth_inferred")
    lines.append("")
    lines.append(
        "| fixture | x_core_inferred (mm) | L_m fitted (mm) | "
        "D_m fitted (mm) | α_ratio fitted | x_surface_in_loaf (mm) |"
    )
    lines.append("|---|---|---|---|---|---|")
    for label, fit in phase3.items():
        if "error" in fit or not fit.get("converged"):
            lines.append(f"| `{label}` | (no fit) | | | | |")
            continue
        lines.append(
            f"| `{label}` | {fit['x_core_depth_inferred_mm']:.1f} | "
            f"{fit['L_m']*1000:.1f} | {fit['D_m']*1000:.1f} | "
            f"{fit['alpha_ratio']:.2f} | "
            f"{fit.get('x_surface_in_loaf_mm', float('nan')):.1f} |"
        )
    lines.append("")

    lines.append("## Did surface-Dirichlet hybrid break the M9 floor?")
    lines.append("")
    by_label = {d["label"]: d for d in phase3b if "label" in d}
    lines.append("| fixture | M17 hybrid | M16 obs-BC | M15 Luikov-tin | M9 Stefan |")
    lines.append("|---|---|---|---|---|")
    for label in M9_MAIN:
        d = by_label.get(label)
        m17 = d["segment_rmse"]["main"] if d and "segment_rmse" in d else float("nan")
        m16 = m16_main.get(label, float("nan"))
        m15 = M15_MAIN.get(label, float("nan"))
        m9 = M9_MAIN.get(label, float("nan"))
        lines.append(f"| `{label}` | {m17:.2f} | {m16:.2f} | {m15:.2f} | {m9:.2f} |")
    lines.append("")

    loo_t1 = [
        r for r in phase4
        if "error" not in r and "skipped" not in r and r.get("held_out_sensor") == "T1"
    ]
    if loo_t1:
        rmses = [r["loo_rmse"] for r in loo_t1]
        lines.append("## LOO T1 deep-end test")
        lines.append("")
        lines.append(
            f"T1 LOO-RMSE (M17): median {float(np.median(rmses)):.2f} °C, "
            f"max {float(np.max(rmses)):.2f} °C, n={len(rmses)}.  "
            f"Compare M9 Stefan {M9_T1_LOO_RANGE[0]:.1f}-{M9_T1_LOO_RANGE[1]:.1f} °C; "
            f"M15 {M15_T1_LOO_MEDIAN:.2f} °C."
        )
        lines.append("")

    lines.append("## Open follow-ups")
    lines.append("")
    if verdict == "GO":
        lines.append(
            "- Wire `fit_luikov_dirichlet_hybrid_inverse` into `loader.py` "
            "as the canonical inverse; gate behind a config flag.\n"
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
            "- Information limit confirmed. The surface-Dirichlet BC was "
            "correct; missing physics layers don't break the floor. Method "
            "4 (per-CSV oven setpoint + tin/lid metadata + surface-sensor "
            "signal in the inverse loss) is the final remaining structural "
            "lever. Pivot away from inverse-problem research on this data "
            "alone."
        )
    lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main() -> None:
    overall_t0 = time.time()
    out: dict = {
        "mission": "HMS Endeavour M17 — Luikov-Dirichlet hybrid inverse",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "downsample_factor": DOWNSAMPLE_FACTOR,
        "n_spatial": N_SPATIAL,
        "loo_fixtures": sorted(LOO_FIXTURES),
        "loo_hold_out": list(LOO_HOLD_OUT),
    }

    t0 = _phase("phase 1: forward solver sanity (5-test pytest sub-suite)")
    out["phase1"] = phase1_forward_sanity()
    print(f"  phase 1 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(f"phase 2: synthetic recovery ({SYNTH_SEEDS} seeds)")
    out["phase2"] = phase2_synthetic_recovery()
    print(f"  phase 2 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(f"phase 3: real-CSV hybrid inverse ({len(REAL_FIXTURES)} fixtures, 5 param)")
    out["phase3"] = phase3_real_csv()
    print(f"  phase 3 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase("phase 3b: residual decomposition")
    out["phase3b"] = phase3b_residual_decomposition(out["phase3"])
    print(f"  phase 3b elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(
        f"phase 4: LOO subset on {len(LOO_FIXTURES)} fixtures × "
        f"{len(LOO_HOLD_OUT)} held-out sensors"
    )
    out["phase4"] = phase4_loo_subset()
    print(f"  phase 4 elapsed: {time.time() - t0:.1f}s", flush=True)

    m16_main = _load_m16_main()

    verdict, rationale = _verdict(
        out["phase1"], out["phase2"], out["phase3"], out["phase3b"], out["phase4"],
    )
    out["verdict"] = verdict
    out["rationale"] = rationale
    out["m16_main_pulled"] = m16_main
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
        out["phase3b"], out["phase4"], verdict, rationale, m16_main,
    )
    with open(OUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"  wrote {OUT_MD_PATH}", flush=True)

    log_text = _render_captains_log(
        out["phase1"], out["phase2"], out["phase3"],
        out["phase3b"], out["phase4"], verdict, rationale,
        out["wall_seconds"], m16_main,
    )
    os.makedirs(os.path.dirname(CAPTAINS_LOG_PATH), exist_ok=True)
    with open(CAPTAINS_LOG_PATH, "w", encoding="utf-8") as f:
        f.write(log_text)
    print(f"  wrote {CAPTAINS_LOG_PATH}", flush=True)


if __name__ == "__main__":
    main()
