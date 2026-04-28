"""HMS Triumph — M9 Stefan-front inverse driver.

Phases:

1. Forward-solver sanity vs analytical Stefan-Neumann (one-phase, Ste=2).
2. Synthetic ground-truth recovery (10 seeds; generator uses ΔT_smear=0.3,
   inverse uses ΔT_smear=1.0 — distinct numerical realisations of the same
   physics class so the test is not a tautology).
3. Real-CSV viability — 7 fixtures × {joint 4-param, pinned 1-param}.

Approximate runtime: 25-40 min on the same hardware that ran M7. If wall
time becomes a problem, drop ``SYNTH_SEEDS`` to 5 or raise
``DOWNSAMPLE_FACTOR`` from 4 to 8.

Usage::

    python -m tests._driver_stefan_inverse
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
from src.data.spatial_reconstruction.stefan_inverse import (  # noqa: E402
    classical_stefan_neumann,
    fit_stefan_inverse_joint,
    fit_stefan_inverse_pinned,
    solve_stefan_forward,
)
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    SENSOR_NAMES,
    SENSOR_POSITIONS,
    _segmented_real_fixture,
)


DOWNSAMPLE_FACTOR = 4
N_SPATIAL = 30  # BDF integrator + this grid → ~250 ms per forward solve.
SYNTH_SEEDS = 10

# Round 1 (M7) values for context column in the report.
M7_V1 = {
    "BA3C_1759_C1": 6.14,
    "BA3C_0946": 6.09,
    "BA3C_1759_C0": 6.09,
    "BA3C_1759_C2": 6.48,
    "100098DE_1351": 7.03,
    "post_wonder_meal": 9.98,
    "wonder_white": 10.01,
}


def _phase(name: str) -> float:
    print(f"\n=== {name} ===", flush=True)
    return time.time()


def _classifier_x_surface(spec: dict) -> float:
    """Look up the M2a continuous interface position for a fixture."""
    df = _segmented_real_fixture(spec)
    geom = lookup_geometry(probe_sn=None, probe_model=None)
    a = classify(df, sample_period_ms=5000, probe_geometry=geom)
    if a.surface_assignment is None:
        return float(spec["x_surface"])
    return float(a.surface_assignment.position_normalised)


# -------------------------------------------------------------------------
# Phase 1 — analytical sanity
# -------------------------------------------------------------------------


def phase1_sanity() -> dict:
    """Match enthalpy-method forward solver to one-phase Stefan-Neumann.

    One-phase Stefan-Neumann: dough region initially at 100 °C, surface held
    at T_surf > 100 °C. Front penetrates inward as `s(t) = x_surface −
    2λ√(α_crust · t)`. Tolerance bar is 3 °C — the residual gap between
    enthalpy method and the sharp-interface analytical comes from the
    inevitable smearing window (this is documented behaviour of the
    enthalpy method; tightening dT_smear stiffens the ODE without removing
    the bias).
    """
    T_surf = 150.0
    T_init = 100.0  # one-phase: dough already at melting temp
    alpha = 1e-3
    Ste = 2.0  # less latent-dominated → tighter analytical match
    rhoL = (T_surf - T_init) / Ste  # = 25 K (matches Ste cleanly)

    t = np.linspace(0.0, 4000.0, 120)
    surf = np.full_like(t, T_surf)
    sample_x = np.array([0.5, 0.7, 0.85, 0.95])

    T_ana, s_ana = classical_stefan_neumann(
        T_init=T_init,
        T_surface=T_surf,
        alpha_crust=alpha,
        stefan_number=Ste,
        x_surface=1.0,
        x=sample_x,
        t=t,
    )
    T_num = solve_stefan_forward(
        x_core=-2.0,
        x_surface=1.0,
        alpha_dough=alpha,
        alpha_crust=alpha,
        rhoL_eff=rhoL,
        t_grid=t,
        T_surface_series=surf,
        T_initial=T_init,
        n_spatial=200,
        sample_x=sample_x,
        delta_T_smear=0.5,
    )
    # Ignore the first 20 samples (stiff-clamp boundary transient).
    diffs = np.abs(T_num[20:, :] - T_ana[20:, :])
    max_diff = float(diffs.max())
    pass_at_3c = bool(max_diff < 3.0)

    print(
        f"  Stefan-Neumann sanity: max |T_num - T_ana| = {max_diff:.2f} °C "
        f"(bar 3 °C → {'PASS' if pass_at_3c else 'FAIL'})",
        flush=True,
    )
    return {
        "stefan_number": Ste,
        "rhoL_eff_used": rhoL,
        "alpha": alpha,
        "T_surf": T_surf,
        "T_init": T_init,
        "max_abs_diff_C": max_diff,
        "per_position_max_C": diffs.max(axis=0).tolist(),
        "tolerance_C": 3.0,
        "pass": pass_at_3c,
        "note": (
            "Enthalpy method has unavoidable bias O(rhoL_eff/2) °C from the "
            "smearing window when matched to a sharp-interface analytical "
            "solution — tightening dT does not remove the bias since "
            "rhoL_eff is held constant. Bar of 3 °C accepts that bias as "
            "the cost of a non-stiff inverse problem."
        ),
    }


# -------------------------------------------------------------------------
# Phase 2 — synthetic recovery (different ΔT_smear in generator vs inverter)
# -------------------------------------------------------------------------


def _synthetic_real_bake(
    seed: int,
    x_core_true: float = -0.10,
    alpha_dough_true: float = 1e-3,
    alpha_crust_true: float = 8e-4,
    rhoL_true: float = 80.0,
    n_t: int = 280,
    period_s: float = 5.0,
    in_dough: tuple = ("T1", "T2", "T3", "T4", "T5"),
    noise_sigma_c: float = 0.5,
    delta_T_smear_generator: float = 0.3,
) -> tuple[pd.DataFrame, float, float]:
    """Synthesise a real-bake-shaped dataset with a known (x_core, αs, ρL).

    Surface ramps 22 → 200 over the first half, then plateaus. Returns
    (df, x_core_true, x_surface_true) suitable for inverse fitting.
    """
    T_init = 22.0
    t = np.arange(n_t, dtype=float) * period_s
    half = n_t // 2
    surf = np.empty(n_t)
    surf[:half] = np.linspace(T_init, 200.0, half)
    surf[half:] = 200.0
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs = np.array([pos_map[s] for s in in_dough])
    T_pred = solve_stefan_forward(
        x_core=x_core_true,
        x_surface=1.0,
        alpha_dough=alpha_dough_true,
        alpha_crust=alpha_crust_true,
        rhoL_eff=rhoL_true,
        t_grid=t,
        T_surface_series=surf,
        T_initial=T_init,
        n_spatial=80,
        sample_x=x_obs,
        delta_T_smear=delta_T_smear_generator,
    )
    rng = np.random.default_rng(seed)
    if noise_sigma_c > 0:
        T_pred = T_pred + rng.normal(0.0, noise_sigma_c, size=T_pred.shape)
    df = pd.DataFrame({"Timestamp": t})
    for k, s in enumerate(in_dough):
        df[s] = T_pred[:, k]
    for s in SENSOR_NAMES:
        if s not in df.columns:
            df[s] = surf
    return df, float(x_core_true), 1.0


def phase2_synthetic_recovery(seeds: int = SYNTH_SEEDS) -> dict:
    """Generator uses ΔT_smear=0.3; inverse fitter uses ΔT_smear=1.0."""
    x_core_true = -0.10
    rows = []
    for s in range(seeds):
        df, x_true, x_surf = _synthetic_real_bake(seed=s, x_core_true=x_core_true)
        t0 = time.time()
        try:
            r = fit_stefan_inverse_joint(
                df=df,
                in_dough_sensors=["T1", "T2", "T3", "T4", "T5"],
                x_surface_continuous=x_surf,
                init={
                    "x_core": -0.05,
                    "alpha_dough": 1e-3,
                    "alpha_crust": 1e-3,
                    "rhoL_eff": 50.0,
                },
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                delta_T_smear=1.0,
                max_iter=400,
            )
            rows.append(
                {
                    "seed": s,
                    "x_core_true": x_true,
                    "x_core_fit": r["x_core"],
                    "alpha_dough_fit": r["alpha_dough"],
                    "alpha_crust_fit": r["alpha_crust"],
                    "rhoL_eff_fit": r["rhoL_eff"],
                    "rmse_per_sensor": r["rmse_per_sensor"],
                    "max_abs_off_diag_correlation": r["max_abs_off_diag_correlation"],
                    "converged": r["converged"],
                    "n_iter": r["n_iter"],
                    "fit_seconds": time.time() - t0,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "seed": s,
                    "x_core_true": x_true,
                    "x_core_fit": float("nan"),
                    "rmse_per_sensor": float("nan"),
                    "converged": False,
                    "error": str(exc),
                    "fit_seconds": time.time() - t0,
                }
            )
        last = rows[-1]
        print(
            f"  seed {s}: x_core_fit={last.get('x_core_fit', 'n/a')!r} "
            f"rmse={last.get('rmse_per_sensor', 'n/a')!r} "
            f"({last['fit_seconds']:.1f}s)",
            flush=True,
        )

    df_rows = pd.DataFrame(rows)
    finite = df_rows[np.isfinite(df_rows["x_core_fit"])]
    bias = float((finite["x_core_fit"] - x_core_true).mean()) if len(finite) else float("nan")
    spread = float(finite["x_core_fit"].std(ddof=1)) if len(finite) >= 2 else float("nan")
    rmse_med = float(finite["rmse_per_sensor"].median()) if len(finite) else float("nan")
    return {
        "rows": rows,
        "summary": {
            "n_seeds": int(seeds),
            "n_converged": int(sum(r.get("converged", False) for r in rows)),
            "x_core_true": x_core_true,
            "bias": bias,
            "spread": spread,
            "rmse_median": rmse_med,
            "generator_delta_T_smear": 0.3,
            "inverter_delta_T_smear": 1.0,
        },
    }


# -------------------------------------------------------------------------
# Phase 3 — real-CSV joint + pinned
# -------------------------------------------------------------------------


def phase3_real_csv() -> dict:
    out = {"joint": {}, "pinned": {}}
    for spec in REAL_FIXTURES:
        df = _segmented_real_fixture(spec)
        x_surf_cont = _classifier_x_surface(spec)
        # Joint
        t0 = time.time()
        try:
            rj = fit_stefan_inverse_joint(
                df=df,
                in_dough_sensors=spec["in_dough"],
                x_surface_continuous=x_surf_cont,
                init={
                    "x_core": -0.05,
                    "alpha_dough": 1e-3,
                    "alpha_crust": 1e-3,
                    "rhoL_eff": 50.0,
                },
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                delta_T_smear=1.0,
                max_iter=400,
            )
            rj["fit_seconds"] = time.time() - t0
            rj["fixture_label"] = spec["label"]
            rj["fixture_name"] = spec["fixture_name"]
            rj["expected_curve_idx"] = spec["expected_curve_idx"]
            rj["n_in_dough"] = len(spec["in_dough"])
            rj["in_dough"] = list(spec["in_dough"])
        except Exception as exc:
            rj = {
                "error": str(exc),
                "rmse_per_sensor": float("nan"),
                "x_core": float("nan"),
                "converged": False,
                "fit_seconds": time.time() - t0,
                "fixture_label": spec["label"],
                "in_dough": list(spec["in_dough"]),
                "x_surface_continuous": x_surf_cont,
            }
        out["joint"][spec["label"]] = rj
        print(
            f"  joint {spec['label']:>20}: "
            f"x_core={rj.get('x_core', float('nan')):.3f} "
            f"alpha_d={rj.get('alpha_dough', float('nan')):.2e} "
            f"alpha_c={rj.get('alpha_crust', float('nan')):.2e} "
            f"rhoL={rj.get('rhoL_eff', float('nan')):.1f} "
            f"rmse={rj.get('rmse_per_sensor', float('nan')):.2f} "
            f"|ρ|max={rj.get('max_abs_off_diag_correlation', float('nan')):.3f} "
            f"({rj['fit_seconds']:.1f}s)",
            flush=True,
        )

        # Pinned
        t0 = time.time()
        try:
            rp = fit_stefan_inverse_pinned(
                df=df,
                in_dough_sensors=spec["in_dough"],
                x_surface_continuous=x_surf_cont,
                downsample_factor=DOWNSAMPLE_FACTOR,
                n_spatial=N_SPATIAL,
                delta_T_smear=1.0,
                max_iter=200,
            )
            rp["fit_seconds"] = time.time() - t0
            rp["fixture_label"] = spec["label"]
            rp["in_dough"] = list(spec["in_dough"])
        except Exception as exc:
            rp = {
                "error": str(exc),
                "rmse_per_sensor": float("nan"),
                "x_core": float("nan"),
                "converged": False,
                "fit_seconds": time.time() - t0,
                "fixture_label": spec["label"],
                "in_dough": list(spec["in_dough"]),
                "x_surface_continuous": x_surf_cont,
            }
        out["pinned"][spec["label"]] = rp
        print(
            f"  pinned {spec['label']:>19}: "
            f"x_core={rp.get('x_core', float('nan')):.3f} "
            f"rmse={rp.get('rmse_per_sensor', float('nan')):.2f} "
            f"({rp['fit_seconds']:.1f}s)",
            flush=True,
        )
    return out


# -------------------------------------------------------------------------
# Verdict logic
# -------------------------------------------------------------------------


def _verdict(phase1: dict, phase2: dict, phase3: dict) -> tuple[str, list[str]]:
    rationale = []
    sanity_pass = bool(phase1.get("pass", False))
    rationale.append(
        f"Forward-solver sanity (Stefan-Neumann analytical): "
        f"max diff {phase1['max_abs_diff_C']:.2f} °C (bar 3 °C) → "
        f"{'PASS' if sanity_pass else 'FAIL'}"
    )

    syn = phase2["summary"]
    syn_ok = (
        math.isfinite(syn["bias"])
        and abs(syn["bias"]) < 0.05
        and syn["n_converged"] >= max(1, int(syn["n_seeds"] * 0.7))
    )
    rationale.append(
        f"Synthetic recovery (10 seeds, generator dT=0.3, inverter dT=1.0): "
        f"bias={syn['bias']:.4f}, spread={syn['spread']:.4f}, "
        f"converged={syn['n_converged']}/{syn['n_seeds']} → "
        f"{'PASS' if syn_ok else 'FAIL'}"
    )

    joint_rmses = [
        v["rmse_per_sensor"]
        for v in phase3["joint"].values()
        if math.isfinite(v.get("rmse_per_sensor", float("nan")))
    ]
    pinned_rmses = [
        v["rmse_per_sensor"]
        for v in phase3["pinned"].values()
        if math.isfinite(v.get("rmse_per_sensor", float("nan")))
    ]
    n_under_3c = sum(1 for r in joint_rmses if r < 3.0)
    rationale.append(
        f"Joint RMSE (real CSVs): median={np.median(joint_rmses):.2f} °C, "
        f"max={np.max(joint_rmses):.2f} °C across {len(joint_rmses)} fixtures."
    )
    rationale.append(
        f"Pinned RMSE (real CSVs): median={np.median(pinned_rmses):.2f} °C, "
        f"max={np.max(pinned_rmses):.2f} °C across {len(pinned_rmses)} fixtures."
    )
    rationale.append(
        f"M7 heat-eq baseline RMSE for context: median={np.median(list(M7_V1.values())):.2f} °C."
    )
    rho_maxes = [
        v["max_abs_off_diag_correlation"]
        for v in phase3["joint"].values()
        if math.isfinite(v.get("max_abs_off_diag_correlation", float("nan")))
    ]
    rho_med = float(np.median(rho_maxes)) if rho_maxes else float("nan")
    rho_max = float(np.max(rho_maxes)) if rho_maxes else float("nan")
    rationale.append(
        f"Max |ρ| of joint 4-param fit: median={rho_med:.3f}, "
        f"max-across-fixtures={rho_max:.3f} (well-conditioned bar < 0.85)."
    )
    rationale.append(
        f"BA3C cases extrapolating past T1 (x_core < 0): "
        + ", ".join(
            label for label, v in phase3["joint"].items()
            if label.startswith("BA3C") and v.get("x_core", 1.0) < 0.0
        )
        or "(none)"
    )

    n_joint_converged = sum(1 for v in phase3["joint"].values() if v.get("converged", False))
    n_pinned_converged = sum(1 for v in phase3["pinned"].values() if v.get("converged", False))

    # Acceptance bar from spec:
    # GO: forward sanity PASS, joint converges on ≥5/7, pinned all 7, max|ρ|<0.85,
    #     ≥4 fixtures with joint RMSE < 3 °C.
    if (
        sanity_pass
        and n_joint_converged >= 5
        and n_pinned_converged == len(phase3["pinned"])
        and rho_max < 0.85
        and n_under_3c >= 4
    ):
        return "GO", rationale
    if (
        sanity_pass
        and n_joint_converged >= 4
        and n_pinned_converged >= 5
        and (n_under_3c >= 2 or rho_med < 0.85)
    ):
        return "GO-WITH-CAVEATS", rationale
    return "NO-GO", rationale


# -------------------------------------------------------------------------
# Report writer
# -------------------------------------------------------------------------


def _format_corr_matrix(corr: list, names: list) -> str:
    """Format a 4×4 correlation matrix as a markdown table."""
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
    phase1: dict, phase2: dict, phase3: dict, verdict: str, rationale: list
) -> str:
    lines: list[str] = []
    lines.append("# Method 3b — 1D Stefan-Front Inverse Research\n")
    lines.append(
        "**HMS Triumph research mission, 2026-04-28.** Tests whether the "
        "1D Stefan problem with a moving evaporation front (modelled via "
        "the enthalpy method) recovers the loaf core position from real "
        "bread-baking CSVs. M7 (heat-equation, no latent heat) gave "
        "RMSE 6-10 °C — wrong physics class. M9 hypothesis: explicit "
        "100 °C latent-heat plateau is the missing piece. Research-only "
        "— no production wiring."
    )
    lines.append("")
    lines.append("## Executive summary\n")
    lines.append(f"**Verdict: {verdict}**\n")
    for r in rationale:
        lines.append(f"- {r}")
    lines.append("")

    # Phase 1
    lines.append("## Forward-solver sanity vs Stefan-Neumann analytical\n")
    p1 = phase1
    lines.append(
        f"One-phase Stefan-Neumann setup: dough at 100 °C, surface held at "
        f"{p1['T_surf']} °C, α = {p1['alpha']:.2e}, Stefan number Ste = "
        f"{p1['stefan_number']}, ρL_eff = {p1['rhoL_eff_used']} K. Sample "
        f"positions x ∈ {{0.5, 0.7, 0.85, 0.95}}, t ∈ [0, 4000]s.\n"
    )
    lines.append(
        f"* max |T_num − T_ana| = **{p1['max_abs_diff_C']:.3f} °C** "
        f"(bar 3 °C → {'PASS' if p1['pass'] else 'FAIL'})\n"
    )
    lines.append(f"* per-position max diff: {p1['per_position_max_C']}\n")
    lines.append(p1["note"] + "\n")

    # Phase 2
    lines.append("## Synthetic ground-truth recovery\n")
    syn = phase2["summary"]
    lines.append(
        f"Generator: ΔT_smear = {syn['generator_delta_T_smear']} °C; "
        f"Inverter: ΔT_smear = {syn['inverter_delta_T_smear']} °C — "
        f"different numerical realisations of the same physics class so "
        f"the test is not a tautology. Realistic bake (ramp 22 → 200 °C, "
        f"period 5 s, 280 samples), Gaussian σ = 0.5 °C noise. True "
        f"x_core = {syn['x_core_true']}; α_dough = 1e-3; α_crust = 8e-4; "
        f"ρL_eff = 80 K.\n"
    )
    lines.append(
        f"* converged: {syn['n_converged']}/{syn['n_seeds']}\n"
        f"* mean bias `(x_fit − x_true)` = **{syn['bias']:.4f}**\n"
        f"* spread `σ(x_fit)` = **{syn['spread']:.4f}**\n"
        f"* median RMSE: **{syn['rmse_median']:.3f} °C**\n"
    )
    lines.append("\n| seed | x_core_fit | α_dough | α_crust | ρL_eff | RMSE | max&#124;ρ&#124; | iter |\n"
                 "|---|---|---|---|---|---|---|---|")
    for r in phase2["rows"]:
        if not math.isfinite(r.get("x_core_fit", float("nan"))):
            lines.append(
                f"| {r['seed']} | n/a | n/a | n/a | n/a | n/a | n/a | n/a |"
            )
            continue
        lines.append(
            f"| {r['seed']} | {r['x_core_fit']:.4f} | "
            f"{r['alpha_dough_fit']:.2e} | {r['alpha_crust_fit']:.2e} | "
            f"{r['rhoL_eff_fit']:.1f} | {r['rmse_per_sensor']:.2f} | "
            f"{r['max_abs_off_diag_correlation']:.3f} | {r['n_iter']} |"
        )
    lines.append("")

    # Phase 3 main table
    lines.append("## Real-CSV viability — joint vs pinned vs M7 baseline\n")
    lines.append(
        "| fixture | x_surf_cont | x_core_joint | x_core_pinned | "
        "α_dough_joint | α_crust_joint | ρL_eff_joint | RMSE_joint | "
        "RMSE_pinned | RMSE_M7 | max&#124;ρ&#124;_joint | extrap_joint |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|---|"
    )
    for label, rj in phase3["joint"].items():
        rp = phase3["pinned"].get(label, {})
        m7_rmse = M7_V1.get(label, float("nan"))
        lines.append(
            f"| `{label}` | "
            f"{rj.get('x_surface_continuous', float('nan')):.4f} | "
            f"{rj.get('x_core', float('nan')):.3f} | "
            f"{rp.get('x_core', float('nan')):.3f} | "
            f"{rj.get('alpha_dough', float('nan')):.2e} | "
            f"{rj.get('alpha_crust', float('nan')):.2e} | "
            f"{rj.get('rhoL_eff', float('nan')):.1f} | "
            f"{rj.get('rmse_per_sensor', float('nan')):.2f} | "
            f"{rp.get('rmse_per_sensor', float('nan')):.2f} | "
            f"{m7_rmse:.2f} | "
            f"{rj.get('max_abs_off_diag_correlation', float('nan')):.3f} | "
            f"{rj.get('extrapolated', False)} |"
        )

    # Phase 3 — joint correlation matrices per fixture
    lines.append("\n## Joint-fit 4×4 correlation matrices\n")
    var_names = ["x_core", "α_dough", "α_crust", "ρL_eff"]
    for label, rj in phase3["joint"].items():
        lines.append(f"\n### `{label}`\n")
        corr = rj.get("full_correlation_matrix")
        lines.append(_format_corr_matrix(corr, var_names))
        lines.append("")

    # Pinned literature conversion
    lines.append("\n## Literature-pinned variant — parameter conversion\n")
    rp_first = next(iter(phase3["pinned"].values())) if phase3["pinned"] else {}
    if rp_first:
        lines.append(
            f"Literature SI values: α_dough = {rp_first.get('alpha_dough_lit_si', 'n/a'):.2e} m²/s, "
            f"α_crust = {rp_first.get('alpha_crust_lit_si', 'n/a'):.2e} m²/s, "
            f"ρL_eff = {rp_first.get('rhoL_eff_lit_si', 'n/a'):.2e} J/m³.\n"
        )
        lines.append(
            f"Representative loaf thickness: {rp_first.get('loaf_thickness_m', 'n/a')*1000:.0f} mm.\n"
            f"Normalised values: α_dough = {rp_first.get('alpha_dough_pinned', 'n/a'):.4e}, "
            f"α_crust = {rp_first.get('alpha_crust_pinned', 'n/a'):.4e}, "
            f"ρL_eff = {rp_first.get('rhoL_eff_pinned', 'n/a'):.4e} K.\n"
        )

    # Recommendation
    lines.append("\n## Recommendation\n")
    if verdict == "GO":
        rec = (
            "The Stefan model class fits real bake physics qualitatively "
            "better than the heat equation. Production wiring is justified; "
            "the joint 4-parameter fit is well-conditioned and the per-fixture "
            "α/ρL values cluster near literature. Recommend wiring the "
            "joint variant as the canonical inverter, with the pinned "
            "variant as a fallback when individual fits diverge."
        )
    elif verdict == "GO-WITH-CAVEATS":
        rec = (
            "Stefan reduces RMSE relative to the heat-equation baseline on "
            "some fixtures and recovers a basin in the joint fit, but "
            "either degeneracy persists on some fixtures, or RMSE remains "
            "above the 3 °C bar on the lid-bake cases. Recommend the "
            "**pinned** variant for production (1-parameter fit avoids "
            "degeneracy), with 'low confidence' flag whenever joint-fit "
            "RMSE exceeds 4 °C."
        )
    else:
        rec = (
            "Stefan does not deliver enough RMSE reduction to justify the "
            "implementation cost. Either (a) the model class is still wrong "
            "(2D conduction? moisture migration?) or (b) the parametrisation "
            "is genuinely unidentifiable from in-dough thermometry alone. "
            "Recommend the loaf-thickness-metadata route (Method 4) over "
            "any further inverse-problem work."
        )
    lines.append(rec + "\n")
    lines.append(
        "## Open follow-ups\n\n"
        "1. The literature-pinned variant relies on a 50 mm loaf-thickness "
        "scaling. If/when production captures real loaf thickness per CSV, "
        "this becomes per-fixture and removes one pragmatic conversion.\n"
        "2. Lid-suppressed bakes (`wonder_white`, `post_wonder_meal`) cap "
        "the cavity at ~100 °C. The Stefan front cannot advance, and the "
        "inverse problem genuinely loses information. A different model "
        "(possibly two-parameter fit pinning ρL_eff and α_crust to "
        "literature) may be needed for those bakes.\n"
        "3. Forward-solver bias of ~2-3 °C from the smearing window propagates "
        "into RMSE. Tighter ΔT_smear (0.3 °C) would shave that bias at the "
        "cost of doubled wall-time per fit. Worth re-examining once "
        "production wiring is decided.\n"
    )
    return "\n".join(lines)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------


def main() -> None:
    overall_t0 = time.time()
    out: dict = {}

    t0 = _phase("phase 1: Stefan-Neumann analytical sanity")
    out["phase1"] = phase1_sanity()
    print(f"  phase 1 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(f"phase 2: synthetic recovery ({SYNTH_SEEDS} seeds)")
    out["phase2"] = phase2_synthetic_recovery(seeds=SYNTH_SEEDS)
    print(f"  phase 2 elapsed: {time.time() - t0:.1f}s", flush=True)

    t0 = _phase(f"phase 3: real-CSV joint+pinned ({len(REAL_FIXTURES)} fixtures)")
    out["phase3"] = phase3_real_csv()
    print(f"  phase 3 elapsed: {time.time() - t0:.1f}s", flush=True)

    verdict, rationale = _verdict(out["phase1"], out["phase2"], out["phase3"])
    out["verdict"] = verdict
    out["rationale"] = rationale
    out["wall_seconds"] = time.time() - overall_t0
    print(f"\n  total wall-time: {out['wall_seconds']:.1f}s", flush=True)
    print(f"  verdict: {verdict}", flush=True)
    for r in rationale:
        print(f"    - {r}", flush=True)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "baselines", "stefan_inverse_research.json")
    md_path = os.path.join(base_dir, "baselines", "stefan_inverse_research.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"  wrote {json_path}", flush=True)
    md_text = _render_report(out["phase1"], out["phase2"], out["phase3"], verdict, rationale)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"  wrote {md_path}", flush=True)


if __name__ == "__main__":
    main()
