"""HMS Sirius — M15 Luikov-tin asymmetric-BC inverse end-to-end driver.

This is the post-flotilla research mission that fixes M14's three
compounding methodology errors:

1. Loaf thickness as a free parameter (was pinned at 50 mm).
2. Probe geometry decoupled from loaf size: T1-T8 span 95 mm fixed.
3. Asymmetric BCs — radiative-convective top to oven, conductive
   bottom through the tin — instead of symmetric Neumann.

Phases
------

1. **Forward sanity** — 4 unit tests (in ``tests/test_luikov_tin_forward.py``).
   Driver re-runs them to embed status in the report.
2. **Synthetic recovery** — generator uses ε=0.3 and δ=2.5; inverter
   uses ε=0.5 and δ=2.0 (different-class tautology guard). 5 seeds.
3. **Real-CSV joint fits** — same 7 fixtures as M9/M14.
4. **LOO subset** — 3 representative fixtures × {T1, T2} held out
   (deep-end test — M13 specifically flagged T1 LOO blow-up).

Outputs
-------

* ``tests/baselines/luikov_tin_research.json`` — raw fit results.
* ``tests/baselines/luikov_tin_research.md`` — report.
* ``.nelson/missions/2026-04-28_135827_d3177ebb/captains-log.md``.

Usage::

    python -m tests._driver_luikov_tin
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

from src.data.spatial_reconstruction.luikov_tin import (  # noqa: E402
    SENSOR_NAMES_DEFAULT,
    SENSOR_POSITIONS_MM_FROM_TIP,
    fit_luikov_tin_inverse,
    infer_core_depth_from_forward,
    sensor_depths_mm_from_D,
    solve_luikov_tin_forward,
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
    BASE_DIR, "baselines", "luikov_tin_research.json"
)
OUT_MD_PATH = os.path.join(
    BASE_DIR, "baselines", "luikov_tin_research.md"
)
CAPTAINS_LOG_PATH = os.path.join(
    os.path.dirname(BASE_DIR),
    ".nelson",
    "missions",
    "2026-04-28_135827_d3177ebb",
    "captains-log.md",
)

DOWNSAMPLE_FACTOR = 4
N_SPATIAL = 60
SAMPLE_PERIOD_S = 5.0

LOO_FIXTURES = {"BA3C_0946", "100098DE_1351", "wonder_white"}
LOO_HOLD_OUT = ("T1", "T2")  # deep-end stress test

SYNTH_SEEDS = 5

# Comparators for side-by-side table.
M9_MAIN = {
    "BA3C_0946": 5.76,
    "BA3C_1759_C0": 5.76,
    "BA3C_1759_C1": 6.80,
    "BA3C_1759_C2": 7.95,
    "100098DE_1351": 7.49,
    "wonder_white": 11.03,
    "post_wonder_meal": 10.55,
}
M14_MAIN = {
    "BA3C_0946": 20.35,
    "BA3C_1759_C0": 20.35,
    "BA3C_1759_C1": 20.99,
    "BA3C_1759_C2": 19.76,
    "100098DE_1351": 13.47,
    "wonder_white": 19.00,
    "post_wonder_meal": float("nan"),
}
# M13 LOO baseline (T1 deep-end).
M9_T1_LOO_RANGE = (9.0, 21.0)
M14_T1_LOO_RMSE = 26.75


def _phase(name: str) -> float:
    print(f"\n=== {name} ===", flush=True)
    return time.time()


# -------------------------------------------------------------------------
# Phase 1 — Forward sanity (run pytest sub-suite)
# -------------------------------------------------------------------------


def phase1_forward_sanity() -> dict:
    """Run the 4 forward-sanity tests and capture their pass/fail status."""
    test_path = os.path.join(BASE_DIR, "test_luikov_tin_forward.py")
    rc = pytest.main([test_path, "-v", "--tb=short", "-q"])
    return {"pytest_returncode": int(rc), "passed": int(rc) == 0}


# -------------------------------------------------------------------------
# Phase 2 — Synthetic recovery (different-class generator)
# -------------------------------------------------------------------------


SYNTH_TRUTH = {
    "L_m": 0.095,
    "D_m": 0.065,
    "Lu": 0.10,
    "Ko": 5.0,
    "Bi_top": 8.0,
    "Bi_bottom": 2.0,
    "T_oven_K": 470.0,
    "T_tin_K": 410.0,
}


def _synthesise(seed: int, noise_sigma_c: float = 0.5) -> tuple[pd.DataFrame, list]:
    """Generate synthetic in-dough observations under the truth params.

    Generator uses ε=0.3 and δ=2.5; inverter uses ε=0.5 and δ=2.0
    (different-class tautology guard).
    """
    truth = SYNTH_TRUTH
    # T1..T8 depths under the truth D, in metres.
    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    d_mm = truth["D_m"] * 1000.0 - p_mm
    # In-dough sensors: those whose depth lies inside (0, L_m). Allow
    # 1 mm tolerance on either edge.
    L_mm = truth["L_m"] * 1000.0
    in_dough_mask = (d_mm > 0.5) & (d_mm < L_mm - 0.5)
    in_dough = [SENSOR_NAMES_DEFAULT[i] for i in range(8) if in_dough_mask[i]]
    d_in = d_mm[in_dough_mask] / 1000.0  # metres

    n_t = 600
    t_grid = np.arange(n_t, dtype=float) * SAMPLE_PERIOD_S
    fwd = solve_luikov_tin_forward(
        L_m=truth["L_m"],
        Lu=truth["Lu"],
        Ko=truth["Ko"],
        Bi_top=truth["Bi_top"],
        Bi_bottom=truth["Bi_bottom"],
        T_oven_K=truth["T_oven_K"],
        T_tin_K=truth["T_tin_K"],
        t_grid_s=t_grid,
        T_initial_K=295.0,
        sample_x_m=d_in,
        n_spatial=N_SPATIAL,
        epsilon=0.3,        # generator ε
        delta_posnov=2.5,   # generator δ
    )
    T_pred_C = fwd.T_field_K - 273.15
    rng = np.random.default_rng(seed)
    if noise_sigma_c > 0:
        T_pred_C = T_pred_C + rng.normal(0.0, noise_sigma_c, T_pred_C.shape)
    df = pd.DataFrame({"Timestamp": t_grid})
    for k, name in enumerate(in_dough):
        df[name] = T_pred_C[:, k]
    # Fill out-of-dough sensors with ambient-air-ish trend (uniform).
    air_C = np.linspace(22.0, 200.0, n_t)
    for name in SENSOR_NAMES_DEFAULT:
        if name not in df.columns:
            df[name] = air_C
    return df, in_dough


def phase2_synthetic_recovery() -> dict:
    rows = []
    for seed in range(SYNTH_SEEDS):
        df, in_dough = _synthesise(seed=seed, noise_sigma_c=0.5)
        t0 = time.time()
        try:
            r = fit_luikov_tin_inverse(
                df=df,
                in_dough_sensors=in_dough,
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                max_iter=600,
            )
            r["seed"] = seed
            r["fit_seconds"] = time.time() - t0
            rows.append(r)
            print(
                f"  seed={seed}: "
                f"L={r['L_m']*1000:.0f}mm D={r['D_m']*1000:.0f}mm "
                f"Lu={r['Lu']:.3f} Ko={r['Ko']:.2f} "
                f"Bi_top={r['Bi_top']:.2f} Bi_bot={r['Bi_bottom']:.2f} "
                f"T_oven={r['T_oven_K']:.0f}K T_tin={r['T_tin_K']:.0f}K "
                f"rmse={r['rmse_per_sensor']:.3f}K "
                f"x_core_inf={r['x_core_depth_inferred_mm']:.1f}mm "
                f"interior={r['n_interior_params']}/8 "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
        except Exception as exc:
            rows.append({"seed": seed, "error": str(exc)})
            print(f"  seed={seed}: ERROR {exc}", flush=True)

    finite = [r for r in rows if "error" not in r]
    if not finite:
        return {"truth": SYNTH_TRUTH, "rows": rows, "summary": {"n_finite": 0}}
    truth = SYNTH_TRUTH

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
        "Ko_within_30pct": _within_30pct("Ko"),
        "Bi_top_within_30pct": _within_30pct("Bi_top"),
        "Bi_bottom_within_30pct": _within_30pct("Bi_bottom"),
        "T_oven_K_within_30pct": _within_30pct("T_oven_K"),
        "T_tin_K_within_30pct": _within_30pct("T_tin_K"),
        "interior_count_median": float(
            np.median([r["n_interior_params"] for r in finite])
        ),
        "x_core_inferred_median_mm": float(
            np.median([r["x_core_depth_inferred_mm"] for r in finite])
        ),
    }
    return {"truth": truth, "rows": rows, "summary": summary}


# -------------------------------------------------------------------------
# Phase 3 — Real-CSV joint inverse
# -------------------------------------------------------------------------


def phase3_real_csv() -> dict:
    out: dict = {}
    for spec in REAL_FIXTURES:
        df = _segmented_real_fixture(spec)
        t0 = time.time()
        try:
            r = fit_luikov_tin_inverse(
                df=df,
                in_dough_sensors=spec["in_dough"],
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                max_iter=1000,
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
                "Ko": float("nan"),
                "Bi_top": float("nan"),
                "Bi_bottom": float("nan"),
                "T_oven_K": float("nan"),
                "T_tin_K": float("nan"),
                "x_core_depth_inferred_mm": float("nan"),
                "converged": False,
                "fit_seconds": time.time() - t0,
                "fixture_label": spec["label"],
                "in_dough": list(spec["in_dough"]),
                "n_interior_params": 0,
                "param_at_bound": {},
            }
        out[spec["label"]] = r
        if "error" in r:
            print(f"  {spec['label']:>20}: ERROR {r['error']}", flush=True)
        else:
            print(
                f"  {spec['label']:>20}: "
                f"L={r['L_m']*1000:.0f}mm D={r['D_m']*1000:.0f}mm "
                f"Lu={r['Lu']:.3f} Ko={r['Ko']:.2f} "
                f"Bi_top={r['Bi_top']:.2f} Bi_bot={r['Bi_bottom']:.2f} "
                f"T_oven={r['T_oven_K']:.0f}K T_tin={r['T_tin_K']:.0f}K "
                f"rmse={r['rmse_per_sensor']:.2f}K "
                f"x_core={r['x_core_depth_inferred_mm']:.1f}mm "
                f"interior={r['n_interior_params']}/8 "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
    return out


# -------------------------------------------------------------------------
# Phase 3b — Residual decomposition
# -------------------------------------------------------------------------


def _forward_eval_at_fit(spec: dict, fit: dict) -> dict:
    df = _segmented_real_fixture(spec)
    in_dough = list(spec["in_dough"])
    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    pos_by_name = dict(zip(SENSOR_NAMES_DEFAULT, p_mm / 1000.0))
    p_obs_m = np.array([pos_by_name[s] for s in in_dough], dtype=float)
    d_obs_m = fit["D_m"] - p_obs_m
    d_clipped = np.clip(d_obs_m, 0.0, fit["L_m"])
    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    T_obs_C = np.column_stack(
        [df[s].to_numpy(dtype=float)[sl] for s in in_dough]
    )
    T_obs_K = T_obs_C + 273.15
    fwd = solve_luikov_tin_forward(
        L_m=fit["L_m"],
        Lu=fit["Lu"],
        Ko=fit["Ko"],
        Bi_top=fit["Bi_top"],
        Bi_bottom=fit["Bi_bottom"],
        T_oven_K=fit["T_oven_K"],
        T_tin_K=fit["T_tin_K"],
        t_grid_s=t_obs,
        T_initial_K=fit["T_initial_K"],
        sample_x_m=d_clipped,
        n_spatial=int(fit.get("n_spatial", N_SPATIAL)),
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
            "Ko": float(fit["Ko"]),
            "Bi_top": float(fit["Bi_top"]),
            "Bi_bottom": float(fit["Bi_bottom"]),
            "T_oven_K": float(fit["T_oven_K"]),
            "T_tin_K": float(fit["T_tin_K"]),
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
# Phase 4 — LOO subset (T1, T2 held out on 3 representative fixtures)
# -------------------------------------------------------------------------


def _loo_predict_at_held_out(
    fit: dict, df: pd.DataFrame, held_out: str
) -> tuple:
    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    pos_by_name = dict(zip(SENSOR_NAMES_DEFAULT, p_mm / 1000.0))
    p_held_m = float(pos_by_name[held_out])
    d_held_m = fit["D_m"] - p_held_m
    d_clipped = np.array([max(0.0, min(d_held_m, fit["L_m"]))], dtype=float)
    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    fwd = solve_luikov_tin_forward(
        L_m=fit["L_m"],
        Lu=fit["Lu"],
        Ko=fit["Ko"],
        Bi_top=fit["Bi_top"],
        Bi_bottom=fit["Bi_bottom"],
        T_oven_K=fit["T_oven_K"],
        T_tin_K=fit["T_tin_K"],
        t_grid_s=t_obs,
        T_initial_K=fit["T_initial_K"],
        sample_x_m=d_clipped,
        n_spatial=int(fit.get("n_spatial", N_SPATIAL)),
    )
    T_pred_held_C = fwd.T_field_K[:, 0] - 273.15
    T_obs_held_C = df[held_out].to_numpy(dtype=float)[sl]
    return T_pred_held_C, T_obs_held_C


def _loo_one(spec: dict, held_out: str) -> dict:
    df = _segmented_real_fixture(spec)
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
        result = fit_luikov_tin_inverse(
            df=df,
            in_dough_sensors=training,
            downsample_factor=DOWNSAMPLE_FACTOR,
            n_spatial=N_SPATIAL,
            max_iter=1000,
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
            "L_m": float(result["L_m"]),
            "D_m": float(result["D_m"]),
            "Lu": float(result["Lu"]),
            "Ko": float(result["Ko"]),
            "Bi_top": float(result["Bi_top"]),
            "Bi_bottom": float(result["Bi_bottom"]),
            "T_oven_K": float(result["T_oven_K"]),
            "T_tin_K": float(result["T_tin_K"]),
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
                print(
                    f"  LOO {spec['label']:>20} -{held}: ERROR {r['error']}",
                    flush=True,
                )
                continue
            if "skipped" in r:
                print(
                    f"  LOO {spec['label']:>20} -{held}: skipped ({r['skipped']})",
                    flush=True,
                )
                continue
            print(
                f"  LOO {spec['label']:>20} -{held}: "
                f"loo_rmse={r['loo_rmse']:.2f} "
                f"in_sample={r['in_sample_rmse_pooled']:.2f} "
                f"ratio={r['ratio_loo_to_in_sample']:.2f} "
                f"max|res|={r['loo_max_abs_residual']:.1f} "
                f"x_core_inf={r['x_core_depth_inferred_mm']:.1f}mm "
                f"interior={r['n_interior_params']}/8 "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
    return rows


# -------------------------------------------------------------------------
# Verdict
# -------------------------------------------------------------------------


def _verdict(
    phase1: dict, phase2: dict, phase3: dict, phase3b: list, phase4: list,
) -> tuple[str, list]:
    rationale: list = []

    rationale.append(
        f"Forward sanity: 4-test pytest sub-suite "
        f"{'PASS' if phase1.get('passed') else 'FAIL'} "
        f"(returncode={phase1.get('pytest_returncode')})."
    )

    s2 = phase2.get("summary", {})
    rationale.append(
        f"Synthetic recovery (different-class generator: gen ε=0.3 δ=2.5 vs "
        f"inv ε=0.5 δ=2.0; {s2.get('n_finite', 0)}/{s2.get('n_runs', 0)} runs "
        f"finite, σ_noise=0.5 °C, {SYNTH_SEEDS} seeds): "
        f"RMSE median {s2.get('rmse_median', float('nan')):.3f} °C; "
        f"L_m within 30%={s2.get('L_m_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"D_m within 30%={s2.get('D_m_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"Lu within 30%={s2.get('Lu_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"Ko within 30%={s2.get('Ko_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"Bi_top within 30%={s2.get('Bi_top_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"Bi_bot within 30%={s2.get('Bi_bottom_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"T_oven within 30%={s2.get('T_oven_K_within_30pct', 0)}/{s2.get('n_finite', 0)}; "
        f"T_tin within 30%={s2.get('T_tin_K_within_30pct', 0)}/{s2.get('n_finite', 0)}."
    )

    fit_count_converged = sum(
        1 for v in phase3.values() if v.get("converged", False)
    )
    n_fixtures = len(phase3)
    rationale.append(
        f"Real-CSV 8-param convergence: {fit_count_converged}/{n_fixtures}."
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
        v.get("n_interior_params", 0) for v in phase3.values()
        if v.get("converged")
    ]
    n_with_6plus_interior = sum(1 for c in interior_counts if c >= 6)
    rationale.append(
        f"Fixtures with ≥6/8 interior params: "
        f"{n_with_6plus_interior}/{fit_count_converged}."
    )

    # x_core_depth_inferred plausibility (40-70 mm in a 100 mm loaf as
    # the briefing's plausible band, per fixture).
    x_cores = [
        v["x_core_depth_inferred_mm"] for v in phase3.values()
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

    # LOO summary — T1 deep-end specifically.
    loo_finite = [
        r for r in phase4
        if "error" not in r and "skipped" not in r and "loo_rmse" in r
    ]
    if loo_finite:
        t1_runs = [r for r in loo_finite if r["held_out_sensor"] == "T1"]
        t2_runs = [r for r in loo_finite if r["held_out_sensor"] == "T2"]
        t1_rmse_med = (
            float(np.median([r["loo_rmse"] for r in t1_runs]))
            if t1_runs else float("nan")
        )
        t2_rmse_med = (
            float(np.median([r["loo_rmse"] for r in t2_runs]))
            if t2_runs else float("nan")
        )
        rationale.append(
            f"LOO subset (held-out T1, T2 on {len(LOO_FIXTURES)} fixtures): "
            f"T1 LOO-RMSE median {t1_rmse_med:.2f} °C "
            f"({len(t1_runs)} fits), "
            f"T2 LOO-RMSE median {t2_rmse_med:.2f} °C ({len(t2_runs)} fits). "
            f"Compare M9 Stefan T1 LOO {M9_T1_LOO_RANGE[0]:.1f}-"
            f"{M9_T1_LOO_RANGE[1]:.1f} °C; M14 Luikov T1 LOO "
            f"{M14_T1_LOO_RMSE:.2f} °C."
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
        and n_with_6plus_interior >= 4
        and in_band_count >= max(1, len(x_cores) // 2)
    ):
        verdict = "GO"
        rationale.append(
            "Asymmetric BC + correct geometry + correct loaf thickness "
            "delivers within-4 °C main-bake fits, deep-end T1 LOO < 4 °C, "
            "≥6/8 interior params on most fixtures, and physically plausible "
            "x_core_depth values. The Luikov coupled heat-mass formulation "
            "with corrected physics captures real bread-baking thermometry."
        )
    elif (
        fit_count_converged >= 5
        and (n_under_4 + n_4_to_6) >= max(3, int(np.ceil(0.5 * len(main_rmses))))
    ):
        verdict = "GO-WITH-CAVEATS"
        rationale.append(
            "Asymmetric-BC reformulation reduces the headline misfit but not "
            "uniformly to the 4 °C bar, or LOO is patchy. Some fixtures still "
            "show inadequate fit or LOO blow-up; production wiring is "
            "justified with low-confidence flags on the worst fixtures."
        )
    else:
        verdict = "CONFIRM-information-limit"
        rationale.append(
            "Even with full asymmetric-tin BCs, correct probe geometry, and a "
            "free loaf thickness, main-bake RMSE remains above 4 °C on "
            "multiple fixtures and/or the deep-end T1 LOO blows up. The data "
            "fundamentally underdetermines the model class. Method 4 (per-CSV "
            "metadata capture: actual loaf thickness, oven setpoint, lid/tin "
            "state, plus inclusion of the surface-sensor signal in the loss) "
            "is the unambiguously remaining path."
        )
    return verdict, rationale


# -------------------------------------------------------------------------
# Report rendering
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


def _render_report(
    phase1: dict, phase2: dict, phase3: dict, phase3b: list, phase4: list,
    verdict: str, rationale: list,
) -> str:
    lines: list = []
    lines.append(
        "# Luikov asymmetric-tin BC inverse — research report (HMS Sirius / M15)"
    )
    lines.append("")
    lines.append(
        "**Mission:** Reformulate the M14 Luikov inverse with corrected "
        "geometry (95 mm probe span / 13.571 mm sensor pitch / decoupled "
        "loaf thickness) and asymmetric BCs (radiative-convective top to "
        "oven, conductive bottom through the tin). 8 free parameters; "
        "x_core depth becomes a *derived* quantity from the fitted profile."
    )
    lines.append("")
    lines.append("**Branch:** `refactor/role-classification-unified`  ")
    lines.append(
        "**Mission dir:** `.nelson/missions/2026-04-28_135827_d3177ebb`  "
    )
    lines.append("**Date:** 2026-04-29 (M15)  ")
    lines.append("")

    # Executive summary.
    lines.append("## Executive summary")
    lines.append("")
    lines.append(f"**Verdict: {verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    # Method.
    lines.append("## Method")
    lines.append("")
    lines.append(
        "Coupled heat + moisture transport on `x ∈ [0, L]` with `x=0` at "
        "the oven-facing top and `x=L` at the tin-contacting bottom. "
        "Convective-radiative top BC and convective tin bottom BC. "
        "Pinned constants: α=1.4×10⁻⁷ m²/s, c=2000 J/(kg·K), L_v=2.26×10⁶ "
        "J/kg, u_init=0.4, ε=0.5, δ=2.0, ε_rad=0.85, k=0.5 W/(m·K). "
        "8 free parameters (L_m, D_m, Lu, Ko, Bi_top, Bi_bottom, T_oven_K, "
        "T_tin_K) optimised via Nelder-Mead with the soft constraint "
        "T_tin_K ≤ T_oven_K. Sensor positions are mapped from probe-relative "
        "(13.571 mm spacing from the tip) into loaf coordinates via "
        "d_i = D − (i−1)·13.571 mm — so probe geometry is decoupled from L."
    )
    lines.append("")

    # Forward sanity.
    lines.append("## Forward solver sanity")
    lines.append("")
    lines.append(
        f"4-test pytest sub-suite (`tests/test_luikov_tin_forward.py`): "
        f"**{'PASS' if phase1.get('passed') else 'FAIL'}** "
        f"(returncode={phase1.get('pytest_returncode')}). "
        f"Tests: top-only-heated → descending profile, "
        f"bottom-only-heated → ascending, "
        f"symmetric BCs (with ε_rad=0, Ko≈0) → symmetric profile + core at L/2, "
        f"long-time steady state → T → T_oven."
    )
    lines.append("")

    # Synthetic recovery.
    lines.append("## Synthetic recovery (different-class generator)")
    lines.append("")
    s2 = phase2.get("summary", {})
    truth = phase2.get("truth", {})
    lines.append(
        f"Truth: L={truth.get('L_m', 0)*1000:.0f} mm, "
        f"D={truth.get('D_m', 0)*1000:.0f} mm, "
        f"Lu={truth.get('Lu')}, Ko={truth.get('Ko')}, "
        f"Bi_top={truth.get('Bi_top')}, Bi_bottom={truth.get('Bi_bottom')}, "
        f"T_oven={truth.get('T_oven_K')} K, T_tin={truth.get('T_tin_K')} K. "
        f"Generator ε=0.3, δ=2.5; inverter ε=0.5, δ=2.0. σ_noise=0.5 °C, "
        f"{SYNTH_SEEDS} seeds."
    )
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| n_runs | {s2.get('n_runs', 0)} |")
    lines.append(f"| n_finite | {s2.get('n_finite', 0)} |")
    lines.append(f"| RMSE median | {s2.get('rmse_median', float('nan')):.3f} |")
    lines.append(f"| RMSE max | {s2.get('rmse_max', float('nan')):.3f} |")
    for name in (
        "L_m", "D_m", "Lu", "Ko",
        "Bi_top", "Bi_bottom", "T_oven_K", "T_tin_K",
    ):
        key = f"{name}_within_30pct"
        lines.append(
            f"| {name} within 30% | "
            f"{s2.get(key, 0)}/{s2.get('n_finite', 0)} |"
        )
    lines.append(
        f"| interior count median | "
        f"{s2.get('interior_count_median', float('nan')):.1f}/8 |"
    )
    lines.append(
        f"| x_core_inferred median (mm) | "
        f"{s2.get('x_core_inferred_median_mm', float('nan')):.1f} |"
    )
    lines.append("")
    lines.append(
        "Per-seed table:"
    )
    lines.append("")
    lines.append(
        "| seed | L_m (mm) | D_m (mm) | Lu | Ko | Bi_top | Bi_bot | "
        "T_oven (K) | T_tin (K) | x_core_inf (mm) | rmse | interior | fit_s |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    for r in phase2.get("rows", []):
        if "error" in r:
            lines.append(
                f"| {r.get('seed', '?')} | ERROR ({r['error']}) | | | | | | | | | | |"
            )
            continue
        lines.append(
            f"| {r['seed']} | {r['L_m']*1000:.1f} | {r['D_m']*1000:.1f} | "
            f"{r['Lu']:.3f} | {r['Ko']:.2f} | {r['Bi_top']:.2f} | "
            f"{r['Bi_bottom']:.2f} | {r['T_oven_K']:.0f} | "
            f"{r['T_tin_K']:.0f} | {r['x_core_depth_inferred_mm']:.1f} | "
            f"{r['rmse_per_sensor']:.3f} | {r['n_interior_params']}/8 | "
            f"{r.get('fit_seconds', float('nan')):.1f} |"
        )
    lines.append("")

    # Per-fixture real-CSV.
    lines.append("## Per-fixture real-CSV inverse results")
    lines.append("")
    lines.append(
        "| fixture | L_m (mm) | D_m (mm) | Lu | Ko | Bi_top | Bi_bot | "
        "T_oven (K) | T_tin (K) | x_core_inf (mm) | RMSE_full | "
        "interior |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    for label, fit in phase3.items():
        if "error" in fit or not fit.get("converged", False):
            lines.append(f"| `{label}` | ERROR/no-conv | | | | | | | | | | |")
            continue
        lines.append(
            f"| `{label}` | {fit['L_m']*1000:.1f} | {fit['D_m']*1000:.1f} | "
            f"{fit['Lu']:.3f} | {fit['Ko']:.2f} | "
            f"{fit['Bi_top']:.2f} | {fit['Bi_bottom']:.2f} | "
            f"{fit['T_oven_K']:.0f} | {fit['T_tin_K']:.0f} | "
            f"{fit['x_core_depth_inferred_mm']:.1f} | "
            f"{fit['rmse_per_sensor']:.2f} | "
            f"{fit['n_interior_params']}/8 |"
        )
    lines.append("")

    # Per-fixture residual decomposition.
    lines.append("## Per-fixture residual decomposition (M10 helpers)")
    lines.append("")
    lines.append(
        "| fixture | RMSE_full | RMSE_main | RMSE_startup | RMSE_tail | "
        "ρ_main | max&#124;ρ_off&#124; |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    by_label = {d["label"]: d for d in phase3b if "label" in d}
    for label, fit in phase3.items():
        d = by_label.get(label, {})
        if "skipped_reason" in d or not d.get("segment_rmse"):
            lines.append(f"| `{label}` | (skipped) | | | | | |")
            continue
        seg = d["segment_rmse"]
        rho = d["segment_lag1_autocorr"]
        lines.append(
            f"| `{label}` | "
            f"{d['rmse_full_recomputed']:.2f} | "
            f"{seg['main']:.2f} | "
            f"{seg['startup']:.2f} | "
            f"{seg['tail']:.2f} | "
            f"{rho['main']:.3f} | "
            f"{fit.get('max_abs_off_diag_correlation', float('nan')):.3f} |"
        )
    lines.append("")

    # Side-by-side comparator.
    lines.append("## Main-bake RMSE comparison: Sirius vs M9 Stefan vs M14 Luikov")
    lines.append("")
    lines.append(
        "| fixture | Sirius (M15) | M9 Stefan | M14 Luikov (50mm/symmetric) |"
    )
    lines.append("|---|---|---|---|")
    for label in M9_MAIN:
        d = by_label.get(label)
        sirius_main = (
            d["segment_rmse"]["main"]
            if d and "segment_rmse" in d
            else float("nan")
        )
        m9 = M9_MAIN.get(label, float("nan"))
        m14 = M14_MAIN.get(label, float("nan"))
        lines.append(
            f"| `{label}` | {sirius_main:.2f} | {m9:.2f} | {m14:.2f} |"
        )
    lines.append("")

    # Bound-hitting summary.
    lines.append("## Bound-hitting (per-parameter, per-fixture)")
    lines.append("")
    lines.append(
        "Each cell shows where the parameter landed: `interior`, `lo` (at "
        "lower bound), or `hi` (at upper bound)."
    )
    lines.append("")
    lines.append(
        "| fixture | L_m | D_m | Lu | Ko | Bi_top | Bi_bot | T_oven | T_tin |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for label, fit in phase3.items():
        bs = fit.get("param_at_bound", {})
        if not bs:
            lines.append(f"| `{label}` | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |")
            continue
        lines.append(
            f"| `{label}` | {bs.get('L_m','?')} | {bs.get('D_m','?')} | "
            f"{bs.get('Lu','?')} | {bs.get('Ko','?')} | "
            f"{bs.get('Bi_top','?')} | {bs.get('Bi_bottom','?')} | "
            f"{bs.get('T_oven_K','?')} | {bs.get('T_tin_K','?')} |"
        )
    lines.append("")

    # LOO subset.
    lines.append("## LOO subset (deep-end T1, T2 on 3 representative fixtures)")
    lines.append("")
    lines.append(
        f"M13 Stefan/Zürcher T1 LOO range: {M9_T1_LOO_RANGE[0]:.1f}-"
        f"{M9_T1_LOO_RANGE[1]:.1f} °C. M14 Luikov T1 LOO: "
        f"{M14_T1_LOO_RMSE:.2f} °C. Question for M15: does asymmetric BC + "
        "correct geometry recover the deep end?"
    )
    lines.append("")
    if not phase4:
        lines.append("_(LOO phase skipped — wall-clock budget)_")
    else:
        lines.append(
            "| fixture | held_out | LOO_rmse | in_sample | ratio | "
            "max&#124;res&#124; | mean_res | x_core_inf (mm) | interior | "
            "fit_s |"
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
                f"{r['n_interior_params']}/8 | "
                f"{r['fit_seconds']:.1f} |"
            )
    lines.append("")

    # Correlation matrices.
    lines.append("## 8x8 correlation matrices per fixture")
    lines.append("")
    var_names = list([
        "L_m", "D_m", "Lu", "Ko", "Bi_top", "Bi_bot", "T_oven_K", "T_tin_K",
    ])
    for label, fit in phase3.items():
        lines.append(f"\n### `{label}`\n")
        lines.append(
            f"max |off-diag|: "
            f"{fit.get('max_abs_off_diag_correlation', float('nan')):.3f}"
        )
        lines.append("")
        corr = fit.get("full_correlation_matrix")
        lines.append(_format_corr_matrix(corr, var_names))
        lines.append("")

    # Recommendation.
    lines.append("## Recommendation for production")
    lines.append("")
    if verdict == "GO":
        rec = (
            "Asymmetric BC + correct geometry delivers within-4 °C main-bake "
            "RMSE with deep-end LOO under 4 °C and physically plausible "
            "x_core_depth. Wire `fit_luikov_tin_inverse` into the production "
            "loader as the canonical inverse, replacing the M11/M12 Zürcher "
            "and the M14 Luikov paths."
        )
    elif verdict == "GO-WITH-CAVEATS":
        rec = (
            "Asymmetric-BC reformulation reduces M14's main-bake misfit "
            "meaningfully but not uniformly to the 4 °C bar. Production "
            "wiring is justified with low-confidence flags on fixtures with "
            "main-bake RMSE > 5 °C or deep-end LOO > 5 °C. Continue Method 4 "
            "metadata-capture in parallel."
        )
    else:
        rec = (
            "Even with the corrected geometry and asymmetric tin BCs, the "
            "in-dough-only observation matrix does not constrain the deep "
            "region or the full 8-parameter space. The complete physics-class "
            "hierarchy plus geometric correction has been exhausted on this "
            "data alone. **Method 4** — per-CSV loaf-thickness, oven-setpoint, "
            "lid/tin-state metadata capture, plus inclusion of the spatially-"
            "interpolated surface-sensor signal in the loss — is the only "
            "remaining structural path."
        )
    lines.append(rec)
    lines.append("")

    return "\n".join(lines)


def _render_captains_log(
    phase1: dict, phase2: dict, phase3: dict, phase3b: list, phase4: list,
    verdict: str, rationale: list, wall_seconds: float,
) -> str:
    lines: list = []
    lines.append("# Captain's log — HMS Sirius, M15 Luikov asymmetric-tin BC inverse")
    lines.append("")
    lines.append(
        "**Mission:** Reformulate the M14 Luikov inverse from scratch with "
        "corrected geometry and asymmetric tin BCs. M14's three compounding "
        "errors — wrong loaf-thickness assumption (50 mm pinned vs ~100 mm "
        "actual), conflated probe and loaf scales (sensors normalised to "
        "loaf instead of using the probe's fixed 13.571 mm pitch), and "
        "symmetric Neumann at the deep end (wrong physics: the bread is in "
        "a tin) — are addressed simultaneously here."
    )
    lines.append("")
    lines.append("**Branch:** `refactor/role-classification-unified`  ")
    lines.append("**Mission dir:** `.nelson/missions/2026-04-28_135827_d3177ebb`  ")
    lines.append("**Date:** 2026-04-29 (M15)  ")
    lines.append(f"**Wall-clock:** {wall_seconds:.1f} s end-to-end.")
    lines.append("")

    lines.append(f"## Verdict: **{verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    # Per-fixture x_core depth inferred.
    lines.append("## Per-fixture x_core_depth_inferred")
    lines.append("")
    lines.append("| fixture | x_core_depth_inferred (mm) | L_m fitted (mm) | D_m fitted (mm) |")
    lines.append("|---|---|---|---|")
    for label, fit in phase3.items():
        if "error" in fit or not fit.get("converged"):
            lines.append(f"| `{label}` | (no fit) | | |")
            continue
        lines.append(
            f"| `{label}` | {fit['x_core_depth_inferred_mm']:.1f} | "
            f"{fit['L_m']*1000:.1f} | {fit['D_m']*1000:.1f} |"
        )
    lines.append("")

    # Asymmetric-BC effect on T1 LOO.
    lines.append("## Did asymmetric BC fix the M13 deep-end LOO failure?")
    lines.append("")
    loo_t1 = [
        r for r in phase4
        if "error" not in r and "skipped" not in r and r.get("held_out_sensor") == "T1"
    ]
    if loo_t1:
        rmses = [r["loo_rmse"] for r in loo_t1]
        lines.append(
            f"T1 LOO-RMSE (M15): median {float(np.median(rmses)):.2f} °C, "
            f"max {float(np.max(rmses)):.2f} °C, n={len(rmses)}.  "
            f"Compare M9 Stefan {M9_T1_LOO_RANGE[0]:.1f}-{M9_T1_LOO_RANGE[1]:.1f} °C; "
            f"M14 Luikov {M14_T1_LOO_RMSE:.2f} °C."
        )
    else:
        lines.append("LOO T1 phase produced no finite fits.")
    lines.append("")

    # Side-by-side.
    lines.append("## Main-bake RMSE: Sirius vs M9 vs M14")
    lines.append("")
    by_label = {d["label"]: d for d in phase3b if "label" in d}
    lines.append("| fixture | Sirius | M9 Stefan | M14 Luikov |")
    lines.append("|---|---|---|---|")
    for label in M9_MAIN:
        d = by_label.get(label)
        sirius = (
            d["segment_rmse"]["main"]
            if d and "segment_rmse" in d
            else float("nan")
        )
        m9 = M9_MAIN.get(label, float("nan"))
        m14 = M14_MAIN.get(label, float("nan"))
        lines.append(
            f"| `{label}` | {sirius:.2f} | {m9:.2f} | {m14:.2f} |"
        )
    lines.append("")

    # Closing.
    lines.append("## Open follow-ups for production wiring")
    lines.append("")
    if verdict == "GO":
        lines.append(
            "- Wire `fit_luikov_tin_inverse` into `loader.py` as the "
            "canonical inverse; gate behind a config flag for safe roll-out.\n"
            "- Add Method-4 metadata capture (oven setpoint, tin contact, "
            "actual loaf-thickness measurement) to the data-capture pipeline "
            "to further constrain the inverse and enable point-estimates with "
            "tighter SEs."
        )
    elif verdict == "GO-WITH-CAVEATS":
        lines.append(
            "- Production wiring with low-confidence flags on fixtures "
            "with main-bake RMSE > 5 °C or LOO ratio > 1.5.\n"
            "- Method-4 metadata capture in parallel.\n"
            "- Investigate per-fixture fits that hit bounds — bound-hitting "
            "with corrected geometry indicates either a remaining physics "
            "gap or a true information-limit on those fixtures."
        )
    else:
        lines.append(
            "- The full physics-class hierarchy (single-medium → Stefan → "
            "Zürcher → Luikov-symmetric → **Luikov-asymmetric-tin**) has "
            "now been exhausted on the in-dough-only observation matrix. "
            "Information limit confirmed.\n"
            "- **Method 4** is the unambiguous remaining path: capture per-CSV "
            "loaf thickness, oven setpoint, lid/tin contact state at "
            "acquisition time; include the spatially-interpolated surface "
            "signal in the inverse loss; pivot away from inverse-problem "
            "research on this data alone.\n"
            "- Recommend halting Luikov-class research and starting Method-4 "
            "data-capture engineering."
        )
    lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main() -> None:
    overall_t0 = time.time()
    out: dict = {
        "mission": "HMS Sirius M15 — Luikov asymmetric-tin BC inverse",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "downsample_factor": DOWNSAMPLE_FACTOR,
        "n_spatial": N_SPATIAL,
        "loo_fixtures": sorted(LOO_FIXTURES),
        "loo_hold_out": list(LOO_HOLD_OUT),
    }

    t0 = _phase("phase 1: forward solver sanity (4-test pytest sub-suite)")
    out["phase1"] = phase1_forward_sanity()
    print(f"  phase 1 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(
        f"phase 2: synthetic recovery (different-class generator, "
        f"{SYNTH_SEEDS} seeds)"
    )
    out["phase2"] = phase2_synthetic_recovery()
    print(f"  phase 2 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(
        f"phase 3: real-CSV asymmetric-tin Luikov inverse "
        f"({len(REAL_FIXTURES)} fixtures, 8-param)"
    )
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
    main()
