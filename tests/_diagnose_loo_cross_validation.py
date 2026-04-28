"""HMS Hermione - M13 leave-one-sensor-out cross-validation diagnostic.

The M7-M12 missions reported main-bake RMSE in the 6-22 deg C band against
the 8 sensors used to fit the model. Because RMSE is computed against the
same data the optimiser saw, that number is an *in-sample* fit measure, not
a validation. The "model misfit" might simply be sensor-side noise +
calibration drift + response-time lag that the model has no representation
of, NOT genuine missing physics.

This driver runs two phases:

1. **Sensor calibration floor** (Phase 1) - extract T1..T8 readings before
   the bake starts (PredictionState='Probe Not Inserted' or first samples
   of the segmented fixture) and report the room-temperature spread per
   fixture.

2. **Leave-one-sensor-out** (Phase 2) - for each fixture x model
   (M9 Stefan, M12 Zurcher 5-param), drop one in-dough sensor from the
   training set, refit, and predict the held-out sensor's temperature
   trajectory. Report LOO-RMSE per sensor, in-sample RMSE per training
   sensor, ratio LOO/in-sample.

Outputs:

* ``tests/baselines/loo_cross_validation.json`` - raw per-fit data.
* Round 2 sections appended to
  ``tests/baselines/stefan_inverse_research.md`` and
  ``tests/baselines/zurcher_two_state_research.md``.
* ``.nelson/missions/2026-04-28_083939_1b437582/captains-log.md``.

Usage::

    python -m tests._diagnose_loo_cross_validation
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
    fit_stefan_inverse_joint,
    solve_stefan_forward,
)
from src.data.spatial_reconstruction.zurcher import (  # noqa: E402
    LOAF_THICKNESS_M_DEFAULT,
    T_C_K,
    fit_zurcher_inverse_v2,
    solve_zurcher_forward,
)
from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    SENSOR_NAMES,
    SENSOR_POSITIONS,
    _segmented_real_fixture,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
M9_JSON_PATH = os.path.join(BASE_DIR, "baselines", "stefan_inverse_research.json")
M12_JSON_PATH = os.path.join(
    BASE_DIR, "baselines", "zurcher_two_state_research_v2.json"
)
OUT_JSON_PATH = os.path.join(BASE_DIR, "baselines", "loo_cross_validation.json")
STEFAN_MD_PATH = os.path.join(BASE_DIR, "baselines", "stefan_inverse_research.md")
ZURCHER_MD_PATH = os.path.join(BASE_DIR, "baselines", "zurcher_two_state_research.md")
CAPTAINS_LOG_PATH = os.path.join(
    os.path.dirname(BASE_DIR),
    ".nelson",
    "missions",
    "2026-04-28_083939_1b437582",
    "captains-log.md",
)

DOWNSAMPLE_FACTOR = 4
N_SPATIAL = 30
DELTA_T_SMEAR = 1.0
SAMPLE_PERIOD_S = 5.0

# Stefan LOO uses the 3 representative fixtures fallback per the briefing
# (full Stefan sweep would be 35-105 minutes; 3 fixtures is enough to test
# the verdict robustly across unlidded vs lidded).
STEFAN_LOO_FIXTURES = {"BA3C_0946", "100098DE_1351", "wonder_white"}


def _phase(name: str) -> float:
    print(f"\n=== {name} ===", flush=True)
    return time.time()


# -------------------------------------------------------------------------
# Phase 1 - sensor calibration floor at t=0
# -------------------------------------------------------------------------


def _raw_case_df_for_fixture(spec: dict) -> pd.DataFrame:
    """Return the raw (un-segmented) DataFrame for a fixture.

    Used to extract pre-bake samples (PredictionState='Probe Not Inserted')
    rather than the post-segmentation fixture which already starts after
    probe insertion.
    """
    case = next(c for c in CASES if c["name"] == spec["fixture_name"])
    return case["df"].copy()


def _pre_bake_room_temp_samples(spec: dict, n_min: int = 5) -> dict:
    """Return per-sensor room-temp readings before probe insertion.

    Strategy:
    1. Pull the raw case DataFrame.
    2. If ``PredictionState`` is present and there are samples flagged as
       ``'Probe Not Inserted'`` BEFORE the curve start, use those; the
       last ``n_min`` of them.
    3. Otherwise fall back to the first ``n_min`` samples of the segmented
       fixture (the first samples after the curve-boundary detector
       declared the bake started; sensors should still be near room
       temperature for the first few seconds).
    """
    raw = _raw_case_df_for_fixture(spec)
    case = next(c for c in CASES if c["name"] == spec["fixture_name"])
    starts = case.get("expected_starts") or [0]
    idx = spec["expected_curve_idx"]
    curve_start = int(starts[idx])

    source = "fallback_first_5_segmented"
    samples = None
    if "PredictionState" in raw.columns and curve_start > 0:
        pre_mask = raw.index < curve_start
        ps = raw.loc[pre_mask, "PredictionState"].astype(str)
        room_mask = (ps == "Probe Not Inserted")
        if room_mask.any():
            # Use the LAST n_min samples before insertion - these are at
            # equilibrium room temperature (sensors equilibrated with the
            # ambient lab, NOT recently picked up from the box).
            room_idx = pre_mask & raw["PredictionState"].astype(str).eq("Probe Not Inserted")
            sub = raw.loc[room_idx]
            if len(sub) >= n_min:
                samples = sub.tail(n_min)
                source = f"last_{n_min}_pre_insertion"
            elif len(sub) >= 1:
                samples = sub
                source = f"all_{len(sub)}_pre_insertion"

    if samples is None:
        # Fallback: first n_min samples of the segmented fixture.
        seg = _segmented_real_fixture(spec)
        samples = seg.head(n_min)
        source = f"first_{n_min}_segmented"

    sensor_means = {}
    for s in SENSOR_NAMES:
        if s in samples.columns:
            sensor_means[s] = float(samples[s].astype(float).mean())
        else:
            sensor_means[s] = float("nan")

    finite_vals = np.array(
        [v for v in sensor_means.values() if math.isfinite(v)],
        dtype=float,
    )
    if len(finite_vals) == 0:
        return {
            "label": spec["label"],
            "source": source,
            "n_samples_used": int(len(samples)),
            "sensor_means": sensor_means,
            "mean_C": float("nan"),
            "stddev_C": float("nan"),
            "range_C": float("nan"),
            "per_sensor_offset_C": {s: float("nan") for s in SENSOR_NAMES},
        }

    grand_mean = float(finite_vals.mean())
    stddev = float(finite_vals.std(ddof=1)) if len(finite_vals) > 1 else 0.0
    rng = float(finite_vals.max() - finite_vals.min())
    offsets = {
        s: (sensor_means[s] - grand_mean) if math.isfinite(sensor_means[s]) else float("nan")
        for s in SENSOR_NAMES
    }
    return {
        "label": spec["label"],
        "source": source,
        "n_samples_used": int(len(samples)),
        "sensor_means": sensor_means,
        "mean_C": grand_mean,
        "stddev_C": stddev,
        "range_C": rng,
        "per_sensor_offset_C": offsets,
    }


def phase1_sensor_calibration_floor() -> list[dict]:
    rows = []
    for spec in REAL_FIXTURES:
        out = _pre_bake_room_temp_samples(spec)
        rows.append(out)
        print(
            f"  {spec['label']:>20}: source={out['source']:>26} "
            f"n={out['n_samples_used']} "
            f"mean={out['mean_C']:.2f} sigma={out['stddev_C']:.3f} "
            f"range={out['range_C']:.2f} degC",
            flush=True,
        )
    return rows


# -------------------------------------------------------------------------
# Phase 2 - LOO cross-validation
# -------------------------------------------------------------------------


def _stefan_predict_at_held_out(
    fit: dict,
    df: pd.DataFrame,
    held_out_sensor: str,
    x_surface_continuous: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run forward Stefan solve at fit params; sample at held_out_sensor.

    Returns (t_obs, T_pred_at_held_out_C, T_obs_at_held_out_C).
    """
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_held = np.array([pos_map[held_out_sensor]], dtype=float)

    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    surface_full = interpolate_temperature_series_at(
        df,
        positions=SENSOR_POSITIONS,
        x_target=float(x_surface_continuous),
        sensors=SENSOR_NAMES,
    ).to_numpy(dtype=float)
    T_surf_obs = np.interp(t_obs, t_full, surface_full)

    T_pred = solve_stefan_forward(
        x_core=float(fit["x_core"]),
        x_surface=float(x_surface_continuous),
        alpha_dough=float(fit["alpha_dough"]),
        alpha_crust=float(fit["alpha_crust"]),
        rhoL_eff=float(fit["rhoL_eff"]),
        t_grid=t_obs,
        T_surface_series=T_surf_obs,
        T_initial=float(fit["T_initial"]),
        n_spatial=N_SPATIAL,
        sample_x=x_held,
        delta_T_smear=DELTA_T_SMEAR,
    )
    T_pred_held = T_pred[:, 0]
    T_obs_held_full = df[held_out_sensor].to_numpy(dtype=float)
    T_obs_held = T_obs_held_full[sl]
    return t_obs, T_pred_held, T_obs_held


def _zurcher_predict_at_held_out(
    fit: dict,
    df: pd.DataFrame,
    held_out_sensor: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run forward Zurcher v2 solve at fit params; sample at held_out_sensor."""
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_held_n = float(pos_map[held_out_sensor])

    loaf = float(fit["loaf_thickness_m"])
    x_surf_n = float(fit["x_surface_normalised"])
    x_core_m = float(fit["x_core_m"])
    # Map the held-out sensor's normalised position to metres-from-centre,
    # using the same convention as the inverter's _build_observation_matrix:
    #   sample_x_m = x_core_m + (x_n / x_surf_n) * (loaf - x_core_m)
    sample_x_m = np.array(
        [x_core_m + (x_held_n / x_surf_n) * (loaf - x_core_m)], dtype=float
    )

    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]

    physical_constants = {
        "k": float(fit["k"]),
        "c": float(fit["c"]),
    }
    fwd = solve_zurcher_forward(
        x_core_m=x_core_m,
        j_0=float(fit["j_0"]),
        T_oven_eff_K=float(fit["T_oven_eff_K"]),
        t_grid_s=t_obs,
        T_initial_K=float(fit["T_initial_K"]),
        T_in_initial_K=float(fit["T_initial_K"]),
        T_out_initial_K=T_C_K,
        loaf_thickness_m=loaf,
        dx_m=float(fit["dx_m"]),
        sample_x_m=sample_x_m,
        physical_constants=physical_constants,
    )
    T_pred_held_C = fwd.T_predicted_K[:, 0] - 273.15
    T_obs_held_C = df[held_out_sensor].to_numpy(dtype=float)[sl]
    return t_obs, T_pred_held_C, T_obs_held_C


def _per_sensor_rmse_residual(residual: np.ndarray, sensors: list) -> dict:
    out = {}
    for j, s in enumerate(sensors):
        out[s] = float(np.sqrt(np.mean(residual[:, j] ** 2)))
    return out


def _stefan_in_sample_rmse(fit: dict, df: pd.DataFrame, training: list) -> dict:
    """Recompute the Stefan in-sample RMSE on the training sensors at the
    cached / refit parameters. Returns dict with 'pooled' and 'per_sensor'.
    """
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs = np.array([pos_map[s] for s in training], dtype=float)
    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    T_obs = np.column_stack([df[s].to_numpy(dtype=float)[sl] for s in training])
    surface_full = interpolate_temperature_series_at(
        df,
        positions=SENSOR_POSITIONS,
        x_target=float(fit["x_surface_continuous"]),
        sensors=SENSOR_NAMES,
    ).to_numpy(dtype=float)
    T_surf_obs = np.interp(t_obs, t_full, surface_full)
    T_pred = solve_stefan_forward(
        x_core=float(fit["x_core"]),
        x_surface=float(fit["x_surface_continuous"]),
        alpha_dough=float(fit["alpha_dough"]),
        alpha_crust=float(fit["alpha_crust"]),
        rhoL_eff=float(fit["rhoL_eff"]),
        t_grid=t_obs,
        T_surface_series=T_surf_obs,
        T_initial=float(fit["T_initial"]),
        n_spatial=N_SPATIAL,
        sample_x=x_obs,
        delta_T_smear=DELTA_T_SMEAR,
    )
    residual = T_pred - T_obs
    return {
        "pooled": float(np.sqrt(np.mean(residual ** 2))),
        "per_sensor": _per_sensor_rmse_residual(residual, training),
    }


def _zurcher_in_sample_rmse(fit: dict, df: pd.DataFrame, training: list) -> dict:
    """Recompute Zurcher v2 in-sample RMSE on training sensors."""
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs_n = np.array([pos_map[s] for s in training], dtype=float)
    loaf = float(fit["loaf_thickness_m"])
    x_surf_n = float(fit["x_surface_normalised"])
    x_core_m = float(fit["x_core_m"])
    sample_x_m = x_core_m + (x_obs_n / x_surf_n) * (loaf - x_core_m)

    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), DOWNSAMPLE_FACTOR)
    t_obs = t_full[sl]
    T_obs_C = np.column_stack(
        [df[s].to_numpy(dtype=float)[sl] for s in training]
    )

    physical_constants = {
        "k": float(fit["k"]),
        "c": float(fit["c"]),
    }
    fwd = solve_zurcher_forward(
        x_core_m=x_core_m,
        j_0=float(fit["j_0"]),
        T_oven_eff_K=float(fit["T_oven_eff_K"]),
        t_grid_s=t_obs,
        T_initial_K=float(fit["T_initial_K"]),
        T_in_initial_K=float(fit["T_initial_K"]),
        T_out_initial_K=T_C_K,
        loaf_thickness_m=loaf,
        dx_m=float(fit["dx_m"]),
        sample_x_m=sample_x_m,
        physical_constants=physical_constants,
    )
    T_pred_C = fwd.T_predicted_K - 273.15
    residual = T_pred_C - T_obs_C
    return {
        "pooled": float(np.sqrt(np.mean(residual ** 2))),
        "per_sensor": _per_sensor_rmse_residual(residual, training),
    }


def _loo_one_stefan(spec: dict, held_out: str) -> dict:
    df = _segmented_real_fixture(spec)
    full_in_dough = list(spec["in_dough"])
    if held_out not in full_in_dough:
        return {"skipped": "not_in_dough"}
    training = [s for s in full_in_dough if s != held_out]
    x_surface_continuous = float(spec["x_surface"])
    t0 = time.time()
    try:
        result = fit_stefan_inverse_joint(
            df=df,
            in_dough_sensors=training,
            x_surface_continuous=x_surface_continuous,
            init={
                "x_core": -0.05,
                "alpha_dough": 1e-3,
                "alpha_crust": 1e-3,
                "rhoL_eff": 50.0,
            },
            downsample_factor=DOWNSAMPLE_FACTOR,
            n_spatial=N_SPATIAL,
            delta_T_smear=DELTA_T_SMEAR,
            max_iter=400,
        )
    except Exception as exc:
        return {
            "fixture": spec["label"],
            "model": "stefan",
            "held_out_sensor": held_out,
            "training_sensors": training,
            "error": str(exc),
            "fit_seconds": time.time() - t0,
        }
    # Predict at held-out sensor
    fit_for_predict = dict(result)
    fit_for_predict["x_surface_continuous"] = x_surface_continuous
    _, T_pred_held, T_obs_held = _stefan_predict_at_held_out(
        fit_for_predict, df, held_out, x_surface_continuous
    )
    loo_residual = T_pred_held - T_obs_held
    loo_rmse = float(np.sqrt(np.mean(loo_residual ** 2)))
    in_sample = _stefan_in_sample_rmse(fit_for_predict, df, training)
    return {
        "fixture": spec["label"],
        "model": "stefan",
        "held_out_sensor": held_out,
        "training_sensors": training,
        "loo_rmse": loo_rmse,
        "loo_max_abs_residual": float(np.max(np.abs(loo_residual))),
        "loo_mean_residual": float(np.mean(loo_residual)),
        "in_sample_rmse_pooled": in_sample["pooled"],
        "in_sample_rmse_per_sensor": in_sample["per_sensor"],
        "ratio_loo_to_in_sample": (
            loo_rmse / in_sample["pooled"] if in_sample["pooled"] > 0 else float("inf")
        ),
        "fitted_params": {
            "x_core": float(result["x_core"]),
            "alpha_dough": float(result["alpha_dough"]),
            "alpha_crust": float(result["alpha_crust"]),
            "rhoL_eff": float(result["rhoL_eff"]),
        },
        "n_iter": int(result.get("n_iter", -1)),
        "converged": bool(result.get("converged", False)),
        "fit_seconds": time.time() - t0,
    }


def _loo_one_zurcher(spec: dict, held_out: str) -> dict:
    df = _segmented_real_fixture(spec)
    full_in_dough = list(spec["in_dough"])
    if held_out not in full_in_dough:
        return {"skipped": "not_in_dough"}
    training = [s for s in full_in_dough if s != held_out]
    t0 = time.time()
    try:
        result = fit_zurcher_inverse_v2(
            df=df,
            in_dough_sensors=training,
            x_surface_normalised=float(spec["x_surface"]),
            free_constants=["k", "c"],
            init={
                "x_core_m": -0.005,
                "j_0": 0.05,
                "T_oven_eff_K": 450.0,
                "k": 0.35,
                "c": 2200.0,
            },
            downsample_factor=DOWNSAMPLE_FACTOR,
            loaf_thickness_m=LOAF_THICKNESS_M_DEFAULT,
            max_iter=2000,
        )
    except Exception as exc:
        return {
            "fixture": spec["label"],
            "model": "zurcher",
            "held_out_sensor": held_out,
            "training_sensors": training,
            "error": str(exc),
            "fit_seconds": time.time() - t0,
        }
    _, T_pred_held, T_obs_held = _zurcher_predict_at_held_out(
        result, df, held_out
    )
    loo_residual = T_pred_held - T_obs_held
    loo_rmse = float(np.sqrt(np.mean(loo_residual ** 2)))
    in_sample = _zurcher_in_sample_rmse(result, df, training)
    return {
        "fixture": spec["label"],
        "model": "zurcher",
        "held_out_sensor": held_out,
        "training_sensors": training,
        "loo_rmse": loo_rmse,
        "loo_max_abs_residual": float(np.max(np.abs(loo_residual))),
        "loo_mean_residual": float(np.mean(loo_residual)),
        "in_sample_rmse_pooled": in_sample["pooled"],
        "in_sample_rmse_per_sensor": in_sample["per_sensor"],
        "ratio_loo_to_in_sample": (
            loo_rmse / in_sample["pooled"] if in_sample["pooled"] > 0 else float("inf")
        ),
        "fitted_params": {
            "x_core_m": float(result["x_core_m"]),
            "j_0": float(result["j_0"]),
            "T_oven_eff_K": float(result["T_oven_eff_K"]),
            "k": float(result["k"]),
            "c": float(result["c"]),
        },
        "n_iter": int(result.get("n_iter", -1)),
        "converged": bool(result.get("converged", False)),
        "fit_seconds": time.time() - t0,
    }


def phase2_loo_zurcher() -> list[dict]:
    """Full sweep across all 7 fixtures for Zurcher v2 (faster model)."""
    rows = []
    for spec in REAL_FIXTURES:
        for held_out in spec["in_dough"]:
            r = _loo_one_zurcher(spec, held_out)
            rows.append(r)
            if "error" in r:
                print(
                    f"  zurcher {spec['label']:>20} -{held_out}: ERROR {r['error']}",
                    flush=True,
                )
                continue
            print(
                f"  zurcher {spec['label']:>20} -{held_out}: "
                f"LOO_rmse={r['loo_rmse']:.2f} in_sample={r['in_sample_rmse_pooled']:.2f} "
                f"ratio={r['ratio_loo_to_in_sample']:.2f} "
                f"max|res|={r['loo_max_abs_residual']:.1f} "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
    return rows


def phase2_loo_stefan() -> list[dict]:
    """Cheap fallback: 3 representative fixtures for Stefan (slow model)."""
    rows = []
    for spec in REAL_FIXTURES:
        if spec["label"] not in STEFAN_LOO_FIXTURES:
            continue
        for held_out in spec["in_dough"]:
            r = _loo_one_stefan(spec, held_out)
            rows.append(r)
            if "error" in r:
                print(
                    f"  stefan {spec['label']:>20} -{held_out}: ERROR {r['error']}",
                    flush=True,
                )
                continue
            print(
                f"  stefan {spec['label']:>20} -{held_out}: "
                f"LOO_rmse={r['loo_rmse']:.2f} in_sample={r['in_sample_rmse_pooled']:.2f} "
                f"ratio={r['ratio_loo_to_in_sample']:.2f} "
                f"max|res|={r['loo_max_abs_residual']:.1f} "
                f"({r['fit_seconds']:.1f}s)",
                flush=True,
            )
    return rows


# -------------------------------------------------------------------------
# Aggregation + verdict
# -------------------------------------------------------------------------


def _aggregate(rows: list, model: str) -> dict:
    """Return per-fixture median LOO RMSE and overall summary."""
    finite = [r for r in rows if "error" not in r and "loo_rmse" in r]
    by_fixture: dict = {}
    for r in finite:
        by_fixture.setdefault(r["fixture"], []).append(r)
    per_fixture_summary = {}
    for label, frs in by_fixture.items():
        loo_arr = np.array([fr["loo_rmse"] for fr in frs], dtype=float)
        in_sample_arr = np.array(
            [fr["in_sample_rmse_pooled"] for fr in frs], dtype=float
        )
        ratio_arr = np.array([fr["ratio_loo_to_in_sample"] for fr in frs], dtype=float)
        per_fixture_summary[label] = {
            "n_loo": int(len(frs)),
            "loo_rmse_median": float(np.median(loo_arr)),
            "loo_rmse_max": float(np.max(loo_arr)),
            "loo_rmse_min": float(np.min(loo_arr)),
            "in_sample_rmse_median": float(np.median(in_sample_arr)),
            "ratio_median": float(np.median(ratio_arr)),
            "ratio_max": float(np.max(ratio_arr)),
        }
    if finite:
        all_loo = np.array([r["loo_rmse"] for r in finite])
        all_ratio = np.array([r["ratio_loo_to_in_sample"] for r in finite])
        all_in_sample = np.array([r["in_sample_rmse_pooled"] for r in finite])
        overall = {
            "model": model,
            "n_fits": len(finite),
            "n_errors": sum(1 for r in rows if "error" in r),
            "loo_rmse_median": float(np.median(all_loo)),
            "loo_rmse_max": float(np.max(all_loo)),
            "loo_rmse_min": float(np.min(all_loo)),
            "ratio_median": float(np.median(all_ratio)),
            "ratio_max": float(np.max(all_ratio)),
            "in_sample_median": float(np.median(all_in_sample)),
            "n_loo_under_2": int(np.sum(all_loo < 2.0)),
            "n_loo_under_4": int(np.sum(all_loo < 4.0)),
            "n_loo_over_4": int(np.sum(all_loo > 4.0)),
        }
    else:
        overall = {"model": model, "n_fits": 0, "all_failed": True}
    return {"per_fixture": per_fixture_summary, "overall": overall}


def _verdict_from_aggregates(
    stefan_agg: dict, zurcher_agg: dict, floor_rows: list
) -> tuple[str, list]:
    rationale: list = []
    floor_ranges = [
        r["range_C"]
        for r in floor_rows
        if math.isfinite(r.get("range_C", float("nan")))
    ]
    floor_stds = [
        r["stddev_C"]
        for r in floor_rows
        if math.isfinite(r.get("stddev_C", float("nan")))
    ]
    if floor_ranges:
        rationale.append(
            f"Sensor calibration floor (T1-T8 spread at room temp, "
            f"{len(floor_ranges)} fixtures): median range "
            f"{float(np.median(floor_ranges)):.2f} degC, max range "
            f"{float(np.max(floor_ranges)):.2f} degC, median sigma "
            f"{float(np.median(floor_stds)):.3f} degC."
        )

    z_overall = zurcher_agg.get("overall", {})
    if z_overall.get("n_fits", 0) > 0:
        rationale.append(
            f"Zurcher 5-param LOO ({z_overall['n_fits']} fits): "
            f"LOO-RMSE median {z_overall['loo_rmse_median']:.2f} degC, "
            f"max {z_overall['loo_rmse_max']:.2f} degC; ratio LOO/in-sample "
            f"median {z_overall['ratio_median']:.2f}, max "
            f"{z_overall['ratio_max']:.2f}; "
            f"{z_overall['n_loo_under_2']}/{z_overall['n_fits']} held-out "
            f"sensors below 2 degC, {z_overall['n_loo_under_4']} below 4 degC, "
            f"{z_overall['n_loo_over_4']} above 4 degC."
        )

    s_overall = stefan_agg.get("overall", {})
    if s_overall.get("n_fits", 0) > 0:
        rationale.append(
            f"Stefan LOO ({s_overall['n_fits']} fits, 3 representative "
            f"fixtures): LOO-RMSE median {s_overall['loo_rmse_median']:.2f} "
            f"degC, max {s_overall['loo_rmse_max']:.2f} degC; ratio LOO/in-sample "
            f"median {s_overall['ratio_median']:.2f}, max "
            f"{s_overall['ratio_max']:.2f}; "
            f"{s_overall['n_loo_under_2']}/{s_overall['n_fits']} held-out "
            f"sensors below 2 degC, {s_overall['n_loo_under_4']} below 4 degC."
        )

    # Verdict logic per the briefing.
    # Use Zurcher's full sweep as the primary signal (more fits, all
    # fixtures); Stefan's 3-fixture sweep is corroborative.
    z_loo_med = z_overall.get("loo_rmse_median", float("inf"))
    z_ratio_med = z_overall.get("ratio_median", float("inf"))
    s_loo_med = s_overall.get("loo_rmse_median", float("inf"))
    s_ratio_med = s_overall.get("ratio_median", float("inf"))

    # REVISE TO GO: most LOO < 2 degC AND ratio close to 1.
    if (
        z_loo_med < 2.0
        and z_ratio_med < 2.0
        and (s_loo_med == float("inf") or s_loo_med < 2.0)
    ):
        verdict = "REVISE TO GO"
        rationale.append(
            "LOO-RMSE on most held-out sensors is below 2 degC and the "
            "LOO/in-sample ratio is close to 1. The model is not "
            "overfitting; the in-sample RMSE represented sensor noise + "
            "irreducible misfit, not missing physics. M7-M12 verdicts "
            "overstated the model misfit."
        )
    elif (
        z_loo_med < 4.0
        and z_ratio_med < 2.5
        and (s_loo_med == float("inf") or s_loo_med < 4.0)
    ):
        verdict = "GO-WITH-CAVEATS"
        rationale.append(
            "LOO-RMSE 2-4 degC; some fixtures show held-out predictions "
            "noticeably worse than in-sample. The models capture most "
            "of the spatial profile but not all. Per-product calibration "
            "with low-confidence flags on outlier fixtures is justified."
        )
    elif z_loo_med > 4.0 or z_ratio_med > 2.0 or s_ratio_med > 2.0:
        verdict = "CONFIRM-information-limit"
        rationale.append(
            "LOO-RMSE on held-out sensors exceeds 4 degC and/or the "
            "LOO/in-sample ratio exceeds 2x. The models genuinely fail to "
            "capture the spatial profile - a sensor whose data the optimiser "
            "didn't see is mispredicted. In-sample RMSE of 6-22 degC was "
            "genuine model misfit, not sensor-side noise. M7-M12 verdicts "
            "stand."
        )
    else:
        verdict = "GO-WITH-CAVEATS"
        rationale.append(
            "Mixed signal - LOO sits between the GO and "
            "CONFIRM-information-limit thresholds. Recommend per-fixture "
            "low-confidence flags."
        )
    return verdict, rationale


# -------------------------------------------------------------------------
# Markdown rendering
# -------------------------------------------------------------------------


def _format_floor_table(floor_rows: list) -> str:
    lines = []
    lines.append(
        "| fixture | source | n | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | "
        "mean | sigma | range |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    for r in floor_rows:
        sm = r["sensor_means"]
        cells = []
        for s in SENSOR_NAMES:
            v = sm.get(s, float("nan"))
            cells.append(f"{v:.2f}" if math.isfinite(v) else "n/a")
        mean_s = f"{r['mean_C']:.2f}" if math.isfinite(r["mean_C"]) else "n/a"
        std_s = f"{r['stddev_C']:.3f}" if math.isfinite(r["stddev_C"]) else "n/a"
        rng_s = f"{r['range_C']:.2f}" if math.isfinite(r["range_C"]) else "n/a"
        lines.append(
            f"| `{r['label']}` | {r['source']} | {r['n_samples_used']} | "
            + " | ".join(cells)
            + f" | {mean_s} | {std_s} | {rng_s} |"
        )
    return "\n".join(lines)


def _format_loo_table(rows: list, model: str) -> str:
    """Wide table: per-fixture per-sensor LOO RMSE."""
    finite = [r for r in rows if "error" not in r and "loo_rmse" in r]
    if not finite:
        return "_(no successful fits)_"
    lines = []
    lines.append(
        "| fixture | held_out | LOO_rmse | in_sample | ratio | "
        "max&#124;res&#124; | mean_res | converged |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in finite:
        lines.append(
            f"| `{r['fixture']}` | {r['held_out_sensor']} | "
            f"{r['loo_rmse']:.2f} | {r['in_sample_rmse_pooled']:.2f} | "
            f"{r['ratio_loo_to_in_sample']:.2f} | "
            f"{r['loo_max_abs_residual']:.1f} | "
            f"{r['loo_mean_residual']:+.2f} | "
            f"{r['converged']} |"
        )
    return "\n".join(lines)


def _format_aggregate_table(agg: dict) -> str:
    pf = agg["per_fixture"]
    if not pf:
        return "_(no successful fits)_"
    lines = []
    lines.append(
        "| fixture | n_loo | LOO_rmse_median | LOO_rmse_max | "
        "in_sample_median | ratio_median | ratio_max |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for label, s in pf.items():
        lines.append(
            f"| `{label}` | {s['n_loo']} | "
            f"{s['loo_rmse_median']:.2f} | {s['loo_rmse_max']:.2f} | "
            f"{s['in_sample_rmse_median']:.2f} | "
            f"{s['ratio_median']:.2f} | {s['ratio_max']:.2f} |"
        )
    return "\n".join(lines)


def _render_round_section(
    floor_rows: list,
    rows: list,
    agg: dict,
    model_label: str,
    verdict: str,
    rationale: list,
) -> str:
    """Render the Round 2 section appended to a baseline report."""
    lines: list = []
    lines.append("")
    lines.append(
        f"## Round 2 - leave-one-sensor-out cross-validation "
        f"(HMS Hermione, 2026-04-28)"
    )
    lines.append("")
    lines.append(
        "**Methodological context.** Rounds 1 of M7-M12 reported "
        "main-bake RMSE in the 6-22 degC band, but those numbers were "
        "computed on the same in-dough sensors the optimiser saw - an "
        "in-sample fit measure, not a validation. The headline RMSE may "
        "have been inflated by sensor-side noise, calibration drift, and "
        "response-time lag that the model has no representation of, "
        "rather than genuine missing physics. M13's Hermione mission "
        "pulls those threads apart by (a) measuring the sensor calibration "
        "floor at room temperature (the irreducible noise budget) and "
        "(b) running leave-one-sensor-out cross-validation: refit the "
        "model on N-1 in-dough sensors and predict the held-out sensor's "
        "trajectory. If LOO-RMSE on the held-out sensor matches in-sample "
        "RMSE, the model genuinely fits the spatial profile and the "
        "headline RMSE was sensor-side. If LOO-RMSE blows up, the model "
        "is overfitting / failing on data it didn't see, and the misfit "
        "is genuine."
    )
    lines.append("")

    # Floor.
    lines.append("### Sensor calibration floor at room temperature")
    lines.append("")
    lines.append(
        "Per fixture, the last n_samples before probe insertion (when "
        "PredictionState='Probe Not Inserted' is available pre-curve) or "
        "the first n_samples of the segmented fixture (fallback). Sensors "
        "should all read room temperature; spread is the sensor-to-sensor "
        "calibration floor."
    )
    lines.append("")
    lines.append(_format_floor_table(floor_rows))
    lines.append("")

    finite_ranges = [
        r["range_C"]
        for r in floor_rows
        if math.isfinite(r.get("range_C", float("nan")))
    ]
    finite_stds = [
        r["stddev_C"]
        for r in floor_rows
        if math.isfinite(r.get("stddev_C", float("nan")))
    ]
    if finite_ranges:
        lines.append(
            f"**Floor summary**: median range "
            f"{float(np.median(finite_ranges)):.2f} degC, max range "
            f"{float(np.max(finite_ranges)):.2f} degC, median sigma "
            f"{float(np.median(finite_stds)):.3f} degC across "
            f"{len(finite_ranges)} fixtures."
        )
    lines.append("")

    # Per-fit LOO.
    lines.append(f"### Per-fit LOO-RMSE ({model_label})")
    lines.append("")
    lines.append(_format_loo_table(rows, model_label))
    lines.append("")

    # Per-fixture aggregate.
    lines.append("### Per-fixture aggregate")
    lines.append("")
    lines.append(_format_aggregate_table(agg))
    lines.append("")

    # Overall.
    overall = agg.get("overall", {})
    if overall.get("n_fits", 0) > 0:
        lines.append(
            f"**Overall ({model_label}, {overall['n_fits']} fits)**: "
            f"LOO-RMSE median **{overall['loo_rmse_median']:.2f} degC** "
            f"(max {overall['loo_rmse_max']:.2f}), ratio LOO/in-sample "
            f"median **{overall['ratio_median']:.2f}** (max "
            f"{overall['ratio_max']:.2f}); "
            f"{overall['n_loo_under_2']}/{overall['n_fits']} below 2 degC, "
            f"{overall['n_loo_under_4']} below 4 degC, "
            f"{overall['n_loo_over_4']} above 4 degC."
        )
    lines.append("")

    # Verdict.
    lines.append("### Revised verdict")
    lines.append("")
    lines.append(f"**{verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    return "\n".join(lines)


def _append_round_section(md_path: str, section: str) -> None:
    with open(md_path, "r", encoding="utf-8") as f:
        existing = f.read()
    marker = "## Round 2 - leave-one-sensor-out cross-validation"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + "\n"
    new_md = existing.rstrip() + "\n" + section.lstrip("\n")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(new_md)


# -------------------------------------------------------------------------
# Captain's log
# -------------------------------------------------------------------------


def _render_captains_log(
    floor_rows: list,
    stefan_rows: list, stefan_agg: dict,
    zurcher_rows: list, zurcher_agg: dict,
    verdict: str, rationale: list,
    wall_seconds: float,
) -> str:
    lines: list = []
    lines.append(
        "# Captain's log - HMS Hermione, M13 leave-one-sensor-out "
        "cross-validation"
    )
    lines.append("")
    lines.append(
        "**Mission**: Run leave-one-sensor-out cross-validation on the "
        "M9 Stefan and M12 Zurcher 5-param fits, plus measure the sensor "
        "calibration floor at t=0. Determine empirically whether the "
        "M7-M12 main-bake RMSE 6-22 degC was missing physics or sensor "
        "noise + calibration drift + response-time lag."
    )
    lines.append("")
    lines.append(
        "**Branch**: `refactor/role-classification-unified`  \n"
        "**Mission dir**: `.nelson/missions/2026-04-28_083939_1b437582`  \n"
        "**Date**: 2026-04-28  \n"
        f"**Wall-clock**: {wall_seconds:.1f} s end-to-end."
    )
    lines.append("")

    # Floor.
    lines.append("## Sensor calibration floor")
    lines.append("")
    finite_ranges = [
        r["range_C"]
        for r in floor_rows
        if math.isfinite(r.get("range_C", float("nan")))
    ]
    finite_stds = [
        r["stddev_C"]
        for r in floor_rows
        if math.isfinite(r.get("stddev_C", float("nan")))
    ]
    if finite_ranges:
        lines.append(
            f"Across {len(finite_ranges)} fixtures, T1-T8 readings at "
            f"room temperature (pre-bake or first samples of segmented "
            f"fixture) span a median range of "
            f"{float(np.median(finite_ranges)):.2f} degC (max "
            f"{float(np.max(finite_ranges)):.2f} degC), with median "
            f"per-fixture sigma {float(np.median(finite_stds)):.3f} degC. "
            f"This is the sensor-to-sensor calibration floor: any model "
            f"RMSE smaller than this is unphysical."
        )
    else:
        lines.append("No finite floor measurements obtained.")
    lines.append("")
    lines.append(_format_floor_table(floor_rows))
    lines.append("")

    # LOO summaries.
    lines.append("## Zurcher 5-param LOO (full sweep)")
    lines.append("")
    z_overall = zurcher_agg.get("overall", {})
    if z_overall.get("n_fits", 0) > 0:
        lines.append(
            f"{z_overall['n_fits']} LOO fits across all 7 fixtures. "
            f"Median LOO-RMSE **{z_overall['loo_rmse_median']:.2f} degC** "
            f"(max {z_overall['loo_rmse_max']:.2f}). Ratio LOO/in-sample "
            f"median **{z_overall['ratio_median']:.2f}**, max "
            f"{z_overall['ratio_max']:.2f}. "
            f"{z_overall['n_loo_under_2']} held-out sensors below 2 degC, "
            f"{z_overall['n_loo_under_4']} below 4 degC, "
            f"{z_overall['n_loo_over_4']} above 4 degC."
        )
    lines.append("")
    lines.append(_format_aggregate_table(zurcher_agg))
    lines.append("")

    lines.append("## Stefan LOO (3 representative fixtures)")
    lines.append("")
    s_overall = stefan_agg.get("overall", {})
    if s_overall.get("n_fits", 0) > 0:
        lines.append(
            f"{s_overall['n_fits']} LOO fits on "
            + ", ".join(sorted(STEFAN_LOO_FIXTURES))
            + f". Median LOO-RMSE **{s_overall['loo_rmse_median']:.2f} degC** "
            f"(max {s_overall['loo_rmse_max']:.2f}). Ratio LOO/in-sample "
            f"median **{s_overall['ratio_median']:.2f}**, max "
            f"{s_overall['ratio_max']:.2f}. "
            f"{s_overall['n_loo_under_2']} held-out sensors below 2 degC, "
            f"{s_overall['n_loo_under_4']} below 4 degC."
        )
    lines.append("")
    lines.append(_format_aggregate_table(stefan_agg))
    lines.append("")

    # Verdict.
    lines.append("## Verdict and rationale")
    lines.append("")
    lines.append(f"**{verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    # Production wiring recommendation.
    lines.append("## Production wiring recommendation")
    lines.append("")
    if verdict == "REVISE TO GO":
        rec = (
            "The previous M7-M12 verdicts overstated the model misfit. "
            "On held-out sensors, both Stefan and Zurcher predict within "
            "the sensor calibration floor. The headline 6-22 degC RMSE "
            "was driven by sensor-side noise / calibration drift / "
            "response-time lag, not missing physics. **Wire either "
            "`fit_stefan_inverse_joint` or `fit_zurcher_inverse_v2(free_constants="
            "['k','c'])` into production**, with a confidence flag derived "
            "from per-fixture LOO-RMSE quantiles."
        )
    elif verdict == "GO-WITH-CAVEATS":
        rec = (
            "LOO sits between the GO and CONFIRM thresholds. The models "
            "capture most of the spatial profile but produce noticeably "
            "worse predictions on some held-out sensors than on the "
            "training set, suggesting partial overfitting. **Production "
            "wiring is justified with per-fixture low-confidence flags** "
            "wherever LOO/in-sample ratio exceeds 1.5x or LOO-RMSE "
            "exceeds 4 degC. Continue the Method 4 metadata-capture "
            "track in parallel."
        )
    else:
        rec = (
            "LOO-RMSE on held-out sensors confirms the in-sample RMSE "
            "was genuine model misfit. Either the physics class is "
            "wrong (2D conduction, moisture migration, convective "
            "coupling) or the parametrisation is genuinely "
            "non-identifiable from in-dough-only thermometry. "
            "**Pivot to Method 4** (per-CSV loaf-thickness, "
            "oven-setpoint, and lid-state metadata capture). The "
            "inverse-problem track on the present observation matrix "
            "is closed."
        )
    lines.append(rec)
    lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main() -> None:
    overall_t0 = time.time()
    out: dict = {
        "mission": "HMS Hermione M13 - LOO cross-validation",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "downsample_factor": DOWNSAMPLE_FACTOR,
        "n_spatial": N_SPATIAL,
        "delta_T_smear": DELTA_T_SMEAR,
        "stefan_fixtures_used": sorted(STEFAN_LOO_FIXTURES),
    }

    t0 = _phase("phase 1: sensor calibration floor at room temperature")
    floor_rows = phase1_sensor_calibration_floor()
    out["floor"] = floor_rows
    print(f"  phase 1 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(
        f"phase 2a: Zurcher 5-param LOO sweep "
        f"(all 7 fixtures, ~7x5={sum(len(s['in_dough']) for s in REAL_FIXTURES)} fits)"
    )
    zurcher_rows = phase2_loo_zurcher()
    zurcher_agg = _aggregate(zurcher_rows, "zurcher")
    out["zurcher_rows"] = zurcher_rows
    out["zurcher_aggregate"] = zurcher_agg
    print(f"  phase 2a elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(
        f"phase 2b: Stefan LOO sweep "
        f"(3 representative fixtures, ~15 fits)"
    )
    stefan_rows = phase2_loo_stefan()
    stefan_agg = _aggregate(stefan_rows, "stefan")
    out["stefan_rows"] = stefan_rows
    out["stefan_aggregate"] = stefan_agg
    print(f"  phase 2b elapsed: {time.time() - t0:.1f}s", flush=True)

    verdict, rationale = _verdict_from_aggregates(
        stefan_agg, zurcher_agg, floor_rows
    )
    out["verdict"] = verdict
    out["rationale"] = rationale
    out["wall_seconds"] = time.time() - overall_t0

    print(f"\n  verdict: {verdict}", flush=True)
    for r in rationale:
        print(f"    - {r}", flush=True)
    print(f"  total wall-time: {out['wall_seconds']:.1f}s", flush=True)

    # Dump JSON.
    with open(OUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"  wrote {OUT_JSON_PATH}", flush=True)

    # Append Round 2 sections.
    stefan_section = _render_round_section(
        floor_rows, stefan_rows, stefan_agg, "M9 Stefan", verdict, rationale
    )
    _append_round_section(STEFAN_MD_PATH, stefan_section)
    print(f"  appended Round 2 section to {STEFAN_MD_PATH}", flush=True)

    zurcher_section = _render_round_section(
        floor_rows, zurcher_rows, zurcher_agg,
        "M12 Zurcher 5-param", verdict, rationale,
    )
    _append_round_section(ZURCHER_MD_PATH, zurcher_section)
    print(f"  appended Round 2 section to {ZURCHER_MD_PATH}", flush=True)

    # Captain's log.
    log_text = _render_captains_log(
        floor_rows, stefan_rows, stefan_agg,
        zurcher_rows, zurcher_agg,
        verdict, rationale, out["wall_seconds"],
    )
    os.makedirs(os.path.dirname(CAPTAINS_LOG_PATH), exist_ok=True)
    with open(CAPTAINS_LOG_PATH, "w", encoding="utf-8") as f:
        f.write(log_text)
    print(f"  wrote {CAPTAINS_LOG_PATH}", flush=True)


if __name__ == "__main__":
    main()
