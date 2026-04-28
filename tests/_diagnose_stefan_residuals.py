"""HMS Diamond — M10 residual decomposition for the M9 Stefan inverse fits.

Loads the cached M9 fitted parameters from
``tests/baselines/stefan_inverse_research.json``, runs the forward solver
once per fixture at those parameters, and decomposes the residual matrix
``R[t, s] = T_pred[t, s] - T_obs[t, s]`` along four axes:

1. **Per-time-segment RMSE** — startup (0-10%), main (10-90%), tail (90-100%).
2. **Per-sensor RMSE** — full bake, one column per in-dough sensor.
3. **Trim-mean RMSE** — pooled RMSE after dropping the worst-RMSE sensor.
4. **Residual structure** — lag-1 auto-correlation (mean across sensors)
   and segment-mean residual (signed bias).

No new physics — reuses the M9 forward solver and fixture loaders.

Usage::

    python -m tests._diagnose_stefan_residuals
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
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    SENSOR_NAMES,
    SENSOR_POSITIONS,
    _segmented_real_fixture,
)


DOWNSAMPLE_FACTOR = 4  # match M9
N_SPATIAL = 30  # match M9
DELTA_T_SMEAR = 1.0  # match M9

# Round-1 (M9) JSON path — read-only.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
M9_JSON_PATH = os.path.join(BASE_DIR, "baselines", "stefan_inverse_research.json")
OUT_JSON_PATH = os.path.join(
    BASE_DIR, "baselines", "stefan_inverse_residual_decomposition.json"
)
OUT_MD_PATH = os.path.join(BASE_DIR, "baselines", "stefan_inverse_research.md")


# -------------------------------------------------------------------------
# Forward eval at M9 fitted params
# -------------------------------------------------------------------------


def _build_obs_and_surface(
    df: pd.DataFrame,
    in_dough_sensors: list,
    x_surface_continuous: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Replicate the observation matrix + interpolated surface BC the M9
    inverse fitter constructed, so the forward eval at the cached params
    matches the inverse problem byte-for-byte.

    Returns
    -------
    (t_obs, T_obs, x_obs, T_surf_obs)
        ``T_obs`` shape (n_t, n_sensors); ``T_surf_obs`` shape (n_t,).
    """
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs = np.array([pos_map[s] for s in in_dough_sensors], dtype=float)
    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), int(DOWNSAMPLE_FACTOR))
    t_obs = t_full[sl]
    T_cols = [df[s].to_numpy(dtype=float)[sl] for s in in_dough_sensors]
    T_obs = np.column_stack(T_cols)
    surface_full = interpolate_temperature_series_at(
        df,
        positions=SENSOR_POSITIONS,
        x_target=float(x_surface_continuous),
        sensors=SENSOR_NAMES,
    ).to_numpy(dtype=float)
    T_surf_obs = np.interp(t_obs, t_full, surface_full)
    return t_obs, T_obs, x_obs, T_surf_obs


def _forward_eval(spec: dict, m9_fit: dict) -> dict:
    """Run the Stefan forward solve at the M9-cached params; return
    ``T_pred``, ``T_obs``, ``residual``, ``t_obs`` and metadata.
    """
    df = _segmented_real_fixture(spec)
    x_surface_continuous = float(m9_fit["x_surface_continuous"])
    in_dough = list(m9_fit["in_dough"])
    t_obs, T_obs, x_obs, T_surf_obs = _build_obs_and_surface(
        df, in_dough, x_surface_continuous
    )
    T_initial = float(m9_fit["T_initial"])

    t0 = time.time()
    T_pred = solve_stefan_forward(
        x_core=float(m9_fit["x_core"]),
        x_surface=x_surface_continuous,
        alpha_dough=float(m9_fit["alpha_dough"]),
        alpha_crust=float(m9_fit["alpha_crust"]),
        rhoL_eff=float(m9_fit["rhoL_eff"]),
        t_grid=t_obs,
        T_surface_series=T_surf_obs,
        T_initial=T_initial,
        n_spatial=N_SPATIAL,
        sample_x=x_obs,
        delta_T_smear=DELTA_T_SMEAR,
    )
    elapsed = time.time() - t0
    residual = T_pred - T_obs  # shape (n_t, n_sensors)
    return {
        "label": spec["label"],
        "in_dough": in_dough,
        "t_obs": t_obs,
        "T_obs": T_obs,
        "T_pred": T_pred,
        "residual": residual,
        "x_surface_continuous": x_surface_continuous,
        "T_initial": T_initial,
        "x_core": float(m9_fit["x_core"]),
        "rmse_full_recomputed": float(np.sqrt(np.mean(residual ** 2))),
        "rmse_full_m9_reported": float(m9_fit["rmse_per_sensor"]),
        "forward_seconds": elapsed,
    }


# -------------------------------------------------------------------------
# Decomposition axes
# -------------------------------------------------------------------------


def _segment_slices(n_t: int) -> dict:
    """Return three boolean masks for startup / main / tail (10/80/10 split)."""
    idx = np.arange(n_t)
    frac = idx / max(n_t - 1, 1)
    return {
        "startup": frac < 0.10,
        "main": (frac >= 0.10) & (frac < 0.90),
        "tail": frac >= 0.90,
    }


def _segment_rmse(residual: np.ndarray, masks: dict) -> dict:
    """Pooled RMSE per segment — over (timesteps in segment × all sensors)."""
    out = {}
    for name, mask in masks.items():
        if not mask.any():
            out[name] = float("nan")
            continue
        sub = residual[mask, :]
        out[name] = float(np.sqrt(np.mean(sub ** 2)))
    out["full"] = float(np.sqrt(np.mean(residual ** 2)))
    return out


def _segment_mean_residual(residual: np.ndarray, masks: dict) -> dict:
    """Signed mean residual per segment — non-zero indicates systematic bias."""
    out = {}
    for name, mask in masks.items():
        if not mask.any():
            out[name] = float("nan")
            continue
        out[name] = float(np.mean(residual[mask, :]))
    out["full"] = float(np.mean(residual))
    return out


def _per_sensor_rmse(residual: np.ndarray, sensors: list) -> dict:
    """RMSE per sensor over its full time series."""
    out = {}
    for j, s in enumerate(sensors):
        out[s] = float(np.sqrt(np.mean(residual[:, j] ** 2)))
    return out


def _trim_mean_rmse(residual: np.ndarray, sensors: list) -> dict:
    """Drop the worst-RMSE sensor and recompute the pooled RMSE."""
    per_sensor = _per_sensor_rmse(residual, sensors)
    worst = max(per_sensor, key=per_sensor.get)
    keep = [j for j, s in enumerate(sensors) if s != worst]
    trimmed = residual[:, keep]
    return {
        "worst_sensor": worst,
        "worst_sensor_rmse": per_sensor[worst],
        "trim_rmse": float(np.sqrt(np.mean(trimmed ** 2))),
        "full_rmse": float(np.sqrt(np.mean(residual ** 2))),
    }


def _lag1_autocorr_per_sensor(x: np.ndarray) -> float:
    """Pearson lag-1 auto-correlation of a 1-D residual series.

    Implemented directly (not scipy) to avoid adding a dependency. Returns
    NaN if the series has zero variance or fewer than 3 samples.
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    if n < 3:
        return float("nan")
    a = x[:-1]
    b = x[1:]
    a_c = a - a.mean()
    b_c = b - b.mean()
    denom = math.sqrt(float(np.sum(a_c * a_c)) * float(np.sum(b_c * b_c)))
    if denom <= 0:
        return float("nan")
    return float(np.sum(a_c * b_c) / denom)


def _lag1_autocorr_segment(residual: np.ndarray, mask: np.ndarray) -> float:
    """Mean lag-1 auto-correlation across sensors within a segment."""
    if mask.sum() < 3:
        return float("nan")
    sub = residual[mask, :]
    rho_per_sensor = [_lag1_autocorr_per_sensor(sub[:, j]) for j in range(sub.shape[1])]
    finite = [r for r in rho_per_sensor if math.isfinite(r)]
    if not finite:
        return float("nan")
    return float(np.mean(finite))


def _decompose_one(eval_out: dict) -> dict:
    """Run all four decomposition axes for a single fixture."""
    residual = eval_out["residual"]
    sensors = eval_out["in_dough"]
    n_t = residual.shape[0]
    masks = _segment_slices(n_t)

    seg_rmse = _segment_rmse(residual, masks)
    seg_mean = _segment_mean_residual(residual, masks)
    per_sensor = _per_sensor_rmse(residual, sensors)
    trim = _trim_mean_rmse(residual, sensors)

    # Lag-1 auto-corr per segment — main is the headline; report all three.
    seg_rho = {
        name: _lag1_autocorr_segment(residual, masks[name])
        for name in ("startup", "main", "tail")
    }

    return {
        "label": eval_out["label"],
        "in_dough": sensors,
        "n_t": int(n_t),
        "n_sensors": int(residual.shape[1]),
        "rmse_full_recomputed": eval_out["rmse_full_recomputed"],
        "rmse_full_m9_reported": eval_out["rmse_full_m9_reported"],
        "x_core": eval_out["x_core"],
        "x_surface_continuous": eval_out["x_surface_continuous"],
        "T_initial": eval_out["T_initial"],
        "segment_rmse": seg_rmse,
        "segment_mean_residual": seg_mean,
        "segment_lag1_autocorr": seg_rho,
        "per_sensor_rmse": per_sensor,
        "trim_mean": trim,
        "forward_seconds": eval_out["forward_seconds"],
    }


# -------------------------------------------------------------------------
# Verdict logic
# -------------------------------------------------------------------------


def _verdict(decomps: list) -> tuple[str, list]:
    """Apply the M10 verdict rules.

    GO if main-bake RMSE < 3 °C across most fixtures AND main-bake lag-1
    auto-corr < 0.3.
    GO-WITH-CAVEATS if main-bake RMSE 3-6 °C OR lag-1 auto-corr 0.3-0.6.
    NO-GO if main-bake RMSE > 6 °C OR lag-1 auto-corr > 0.6.
    """
    main_rmses = [d["segment_rmse"]["main"] for d in decomps]
    main_rhos = [d["segment_lag1_autocorr"]["main"] for d in decomps]
    main_rmses_finite = [r for r in main_rmses if math.isfinite(r)]
    main_rhos_finite = [r for r in main_rhos if math.isfinite(r)]

    n = len(decomps)
    n_under_3 = sum(1 for r in main_rmses_finite if r < 3.0)
    n_3_to_6 = sum(1 for r in main_rmses_finite if 3.0 <= r <= 6.0)
    n_over_6 = sum(1 for r in main_rmses_finite if r > 6.0)
    rho_med = float(np.median(main_rhos_finite)) if main_rhos_finite else float("nan")
    rho_max = float(np.max(np.abs(main_rhos_finite))) if main_rhos_finite else float("nan")

    rationale = [
        f"Main-bake RMSE distribution: <3 °C={n_under_3}/{n}, "
        f"3-6 °C={n_3_to_6}/{n}, >6 °C={n_over_6}/{n} "
        f"(median={float(np.median(main_rmses_finite)):.2f} °C).",
        f"Main-bake lag-1 auto-corr: median={rho_med:.3f}, max|ρ|={rho_max:.3f}.",
    ]

    # GO: main-bake RMSE < 3 across "most" (≥4/7), AND lag-1 |ρ| max < 0.3.
    if n_under_3 >= max(4, int(np.ceil(0.5 * n))) and rho_max < 0.3:
        rationale.append(
            "Most fixtures have main-bake RMSE < 3 °C and weak residual "
            "auto-correlation (< 0.3) — Stefan is sufficient; the "
            "headline M9 RMSE was inflated by accounting (startup IC, "
            "tail probe-pull, sensor calibration)."
        )
        return "REVISE TO GO", rationale

    # GO-WITH-CAVEATS: most main-bake RMSE in (3, 6] OR lag-1 |ρ| in [0.3, 0.6).
    if (
        n_over_6 == 0
        and (n_3_to_6 + n_under_3) == n
        and rho_max < 0.6
    ):
        rationale.append(
            "Main-bake RMSE 3-6 °C across most fixtures or auto-corr "
            "0.3-0.6 — Stefan captures the bulk of the dynamics but a "
            "residual physics layer (e.g. moisture migration, 2D "
            "conduction) is missing."
        )
        return "REVISE TO GO-WITH-CAVEATS", rationale

    # CONFIRM NO-GO: ≥1 fixture above 6 °C OR auto-corr > 0.6.
    rationale.append(
        "Main-bake RMSE remains > 6 °C on multiple fixtures and/or "
        "residuals show strong temporal structure (|ρ| > 0.6) — Stefan "
        "does not fit main-bake dynamics; the headline M9 RMSE was a "
        "genuine model-misfit signal, not an accounting artefact."
    )
    return "CONFIRM NO-GO", rationale


# -------------------------------------------------------------------------
# Markdown rendering
# -------------------------------------------------------------------------


def _format_per_sensor_row(per_sensor: dict, all_sensors: list) -> str:
    cells = []
    for s in all_sensors:
        if s in per_sensor:
            cells.append(f"{per_sensor[s]:.2f}")
        else:
            cells.append("—")
    return " | ".join(cells)


def _render_round2(decomps: list, verdict: str, rationale: list) -> str:
    """Render the Round 2 markdown section to append to the M9 report."""
    all_sensors = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
    # Restrict to sensors actually used across any fixture for tightness.
    used = sorted({s for d in decomps for s in d["in_dough"]})

    lines: list = []
    lines.append("")
    lines.append("## Round 2 — residual decomposition (HMS Diamond, 2026-04-28)")
    lines.append("")
    lines.append(
        "The M9 driver verdict was NO-GO based on real-CSV RMSE 6-10 °C "
        "matching M7's heat-equation baseline. The admiral suspected the "
        "RMSE might be inflated by startup transient, probe-pull tail, and "
        "per-sensor calibration bias rather than genuine model misfit. This "
        "decomposition tests that hypothesis empirically by re-evaluating "
        "the M9-fitted forward solver once per fixture and slicing the "
        "residual matrix by time segment, by sensor, and by autocorrelation "
        "structure. No new physics — same Stefan forward solver, same M9 "
        "fitted parameters."
    )
    lines.append("")

    # Axis 1 — per-time-segment RMSE.
    lines.append("### Per-time-segment RMSE")
    lines.append("")
    lines.append(
        "| fixture | startup (0-10%) | main (10-90%) | tail (90-100%) | full |"
    )
    lines.append("|---|---|---|---|---|")
    for d in decomps:
        seg = d["segment_rmse"]
        lines.append(
            f"| `{d['label']}` | {seg['startup']:.2f} | {seg['main']:.2f} "
            f"| {seg['tail']:.2f} | {seg['full']:.2f} |"
        )
    lines.append("")

    # Axis 2 — per-sensor RMSE + Axis 3 trim-mean.
    lines.append("### Per-sensor RMSE")
    lines.append("")
    header = "| fixture | " + " | ".join(used) + " | worst | trim-mean (drop worst) | full |"
    sep = "|---|" + "---|" * (len(used) + 3)
    lines.append(header)
    lines.append(sep)
    for d in decomps:
        per = d["per_sensor_rmse"]
        cells = []
        for s in used:
            cells.append(f"{per[s]:.2f}" if s in per else "—")
        trim = d["trim_mean"]
        cells.append(f"{trim['worst_sensor']} ({trim['worst_sensor_rmse']:.2f})")
        cells.append(f"{trim['trim_rmse']:.2f}")
        cells.append(f"{trim['full_rmse']:.2f}")
        lines.append("| `" + d["label"] + "` | " + " | ".join(cells) + " |")
    lines.append("")

    # Axis 4 — residual structure (lag-1 autocorr, segment mean).
    lines.append("### Residual structure (lag-1 autocorr, signed mean)")
    lines.append("")
    lines.append(
        "| fixture | segment | lag-1 ρ (mean over sensors) | mean residual (°C) |"
    )
    lines.append("|---|---|---|---|")
    for d in decomps:
        for seg in ("startup", "main", "tail"):
            rho = d["segment_lag1_autocorr"][seg]
            mu = d["segment_mean_residual"][seg]
            rho_s = f"{rho:.3f}" if math.isfinite(rho) else "n/a"
            mu_s = f"{mu:+.2f}" if math.isfinite(mu) else "n/a"
            lines.append(f"| `{d['label']}` | {seg} | {rho_s} | {mu_s} |")
    lines.append("")

    # Verdict
    lines.append("### Revised verdict")
    lines.append("")
    lines.append(f"**{verdict}**")
    lines.append("")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    return "\n".join(lines)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main() -> None:
    overall_t0 = time.time()
    print(f"Loading M9 cached fits from {M9_JSON_PATH}", flush=True)
    with open(M9_JSON_PATH, "r", encoding="utf-8") as f:
        m9 = json.load(f)
    joint_fits = m9["phase3"]["joint"]

    # Sanity check coverage.
    expected = {spec["label"] for spec in REAL_FIXTURES}
    cached = set(joint_fits)
    missing = expected - cached
    if missing:
        raise RuntimeError(f"Missing M9 cached fits for: {missing}")

    decomps: list = []
    for spec in REAL_FIXTURES:
        label = spec["label"]
        m9_fit = joint_fits[label]
        print(f"  forward-eval {label} ...", flush=True)
        eval_out = _forward_eval(spec, m9_fit)
        d = _decompose_one(eval_out)
        decomps.append(d)
        seg = d["segment_rmse"]
        print(
            f"    n_t={d['n_t']} n_sensors={d['n_sensors']} "
            f"rmse_recomp={d['rmse_full_recomputed']:.2f} "
            f"(M9 reported {d['rmse_full_m9_reported']:.2f}) "
            f"| startup={seg['startup']:.2f} main={seg['main']:.2f} "
            f"tail={seg['tail']:.2f} | trim={d['trim_mean']['trim_rmse']:.2f} "
            f"| ρ_main={d['segment_lag1_autocorr']['main']:.3f} "
            f"({d['forward_seconds']:.1f}s)",
            flush=True,
        )

    verdict, rationale = _verdict(decomps)
    print(f"\n  verdict: {verdict}", flush=True)
    for r in rationale:
        print(f"    - {r}", flush=True)

    # Dump JSON.
    out_obj = {
        "mission": "HMS Diamond M10 — Stefan residual decomposition",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "downsample_factor": DOWNSAMPLE_FACTOR,
        "n_spatial": N_SPATIAL,
        "delta_T_smear": DELTA_T_SMEAR,
        "fixtures": decomps,
        "verdict": verdict,
        "rationale": rationale,
        "wall_seconds": time.time() - overall_t0,
    }
    with open(OUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, indent=2, default=str)
    print(f"  wrote {OUT_JSON_PATH}", flush=True)

    # Append Round 2 section to the existing report.
    md_section = _render_round2(decomps, verdict, rationale)
    with open(OUT_MD_PATH, "r", encoding="utf-8") as f:
        existing = f.read()
    # Idempotent append — strip any prior Round-2 section before appending.
    marker = "## Round 2 — residual decomposition"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + "\n"
    new_md = existing.rstrip() + "\n" + md_section.lstrip("\n")
    with open(OUT_MD_PATH, "w", encoding="utf-8") as f:
        f.write(new_md)
    print(f"  appended Round 2 section to {OUT_MD_PATH}", flush=True)

    print(f"\n  total wall-time: {time.time() - overall_t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
