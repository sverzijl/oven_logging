"""HMS Ambush — Method 3 (1D heat-equation inverse) research tests.

Four test classes:

* :class:`TestForwardSolverSanity` — steady state + step-response match.
* :class:`TestInverseGroundTruthRecovery` — synthetic recovery; the
  load-bearing test that decides whether Method 3 is viable.
* :class:`TestRealCSVViability` — runs the inverter on each real CSV the
  user wants to extrapolate past the probe tip on. NOT a hard pass/fail —
  records evidence into a class-level dict that the report regenerator
  reads.
* :class:`TestRobustnessUnderNoise` — per-fixture per-σ x_core spread,
  comparing heat-eq vs parabolic extrapolation.

Memory-feedback compliance:

* TDD — sanity tests run first and would fail if the forward solver were
  broken (steady-state and step-response analytical comparisons).
* DRY — the noise injection helper is wrapped from
  ``test_role_classifier_perturbation._perturb_df`` — we don't reimplement
  it here.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Any, Optional

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.heat_equation import (  # noqa: E402
    fit_heat_equation_inverse,
    solve_heat_eq_forward,
)
from tests.fixtures.curve_boundary_cases import CASES, load_real_case  # noqa: E402
from tests.test_role_classifier_perturbation import _perturb_df  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


SENSOR_NAMES = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")
SENSOR_POSITIONS = tuple(i / 7 for i in range(8))


def _synthetic_dough_observations(
    alpha_true: float,
    x_core_true: float,
    x_surface: float = 1.0,
    T_initial: float = 22.0,
    T_surface_final: float = 230.0,
    n_t: int = 200,
    period_s: float = 5.0,
    in_dough_sensors: tuple = ("T1", "T2", "T3", "T4"),
    noise_sigma_c: float = 0.0,
    seed: int = 0,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Generate synthetic in-dough observations for a known (α, x_core).

    The surface ramps linearly from ``T_initial`` to ``T_surface_final`` over
    the first half of the run, then plateaus. Returns ``(df, T_surface_series)``
    where ``df`` carries 8 sensor columns (in-dough sensors hold the
    forward-solve solution; the rest are filled with ambient air to be
    realistic but unused by the inverter).
    """
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs = np.array([pos_map[s] for s in in_dough_sensors], dtype=float)
    t_grid = np.arange(n_t, dtype=float) * period_s
    half = n_t // 2
    surf = np.empty(n_t, dtype=float)
    surf[:half] = np.linspace(T_initial, T_surface_final, half)
    surf[half:] = T_surface_final
    T_pred = solve_heat_eq_forward(
        alpha=alpha_true,
        x_core=x_core_true,
        x_surface=x_surface,
        t_grid=t_grid,
        T_surface_series=surf,
        T_initial=T_initial,
        n_spatial=40,
        sample_x=x_obs,
    )
    rng = np.random.default_rng(seed)
    if noise_sigma_c > 0:
        T_pred = T_pred + rng.normal(0.0, noise_sigma_c, size=T_pred.shape)
    df = pd.DataFrame({"Timestamp": t_grid})
    # Fill the in-dough sensors with the forward-solve output.
    for k, s in enumerate(in_dough_sensors):
        df[s] = T_pred[:, k]
    # Fill the rest with synthetic air (unused by the inverter but realistic).
    for s in SENSOR_NAMES:
        if s not in df.columns:
            df[s] = surf  # surface-side filler
    df["SurfaceTemperature"] = surf
    return df, surf


def _hessian_ci_includes(x_hat: float, x_se: float, x_true: float, z: float = 1.96) -> bool:
    if not (math.isfinite(x_hat) and math.isfinite(x_se) and x_se > 0):
        return False
    return abs(x_hat - x_true) <= z * x_se


# ---------------------------------------------------------------------------
# Class 1 — Forward solver sanity
# ---------------------------------------------------------------------------


class TestForwardSolverSanity:
    """Two analytical sanity checks — if these fail, the rest is moot."""

    def test_steady_state_uniform_initial(self):
        """If T_surface(t) = T0 constant and T_initial = T0, T(x, t) = T0."""
        T0 = 80.0
        t_grid = np.linspace(0.0, 1000.0, 50)
        surf = np.full_like(t_grid, T0)
        T = solve_heat_eq_forward(
            alpha=1e-3,
            x_core=-0.1,
            x_surface=1.0,
            t_grid=t_grid,
            T_surface_series=surf,
            T_initial=T0,
            n_spatial=30,
        )
        # Should equal T0 at every (t, x). Allow 1e-3 °C numerical slack.
        assert np.max(np.abs(T - T0)) < 1e-3

    def test_step_response_matches_analytical(self):
        """Step input on surface, semi-infinite-slab analytical solution.

        For a deep domain whose Neumann boundary the diffusion front
        hasn't yet reached, a step from T_init to T_surf at t=0
        propagates as

            T(x, t) - T_init = (T_surf - T_init) · erfc((x_surface - x) / (2 √(α t)))

        Pick α = 1e-3 and a 200 s window: diffusion length
        ℓ = 2√(αt) ≈ 0.9 — well shy of the 2.0-unit domain depth, so the
        Neumann reflection at x_core hasn't disturbed the analytical regime.
        Sample at near-surface positions where erfc has appreciable signal
        and compare at intermediate-to-long times once the stiff Dirichlet
        clamp has equilibrated.
        """
        T_init = 22.0
        T_surf = 200.0
        alpha = 1e-3
        x_core = -1.0  # deep enough that ℓ < domain depth at t_max
        x_surface = 1.0
        t_grid = np.linspace(0.0, 200.0, 50)
        surf = np.full_like(t_grid, T_surf)
        # Sample a few near-surface positions where the analytical formula
        # has appreciable signal.
        sample_x = np.array([0.7, 0.85, 0.95])
        T_num = solve_heat_eq_forward(
            alpha=alpha,
            x_core=x_core,
            x_surface=x_surface,
            t_grid=t_grid,
            T_surface_series=surf,
            T_initial=T_init,
            n_spatial=80,
            sample_x=sample_x,
        )
        # Analytical erfc solution.
        from scipy.special import erfc

        T_ana = np.empty_like(T_num)
        for i, t in enumerate(t_grid):
            if t <= 0:
                T_ana[i, :] = T_init
                continue
            arg = (x_surface - sample_x) / (2.0 * np.sqrt(alpha * t))
            T_ana[i, :] = T_init + (T_surf - T_init) * erfc(arg)
        # Compare at intermediate-to-long times only (samples 10-49). The
        # earliest few samples carry the Dirichlet stiff-clamp transient.
        diff = np.abs(T_num[10:, :] - T_ana[10:, :])
        # 2 °C bar — generous enough to absorb the stiff-clamp boundary
        # layer effect at x=0.95 (very close to the Dirichlet boundary
        # where the discretisation is least accurate); the deeper sample
        # positions match much tighter.
        assert np.max(diff) < 2.0, (
            f"step-response error {np.max(diff):.3f} °C exceeds 2 °C bar; "
            f"per-position max errs = {np.max(diff, axis=0)}"
        )


# ---------------------------------------------------------------------------
# Class 2 — Inverse ground-truth recovery
# ---------------------------------------------------------------------------


class TestInverseGroundTruthRecovery:
    """The load-bearing test for Method 3 viability.

    If we can't recover a known x_core in noiseless synthetic data, the
    method has no chance on real CSVs.
    """

    def test_recovers_known_x_core_no_noise(self):
        x_core_true = -0.15
        alpha_true = 1.5e-3
        df, surf = _synthetic_dough_observations(
            alpha_true=alpha_true,
            x_core_true=x_core_true,
            in_dough_sensors=("T1", "T2", "T3", "T4"),
            noise_sigma_c=0.0,
            seed=1,
        )
        result = fit_heat_equation_inverse(
            df=df,
            in_dough_sensors=["T1", "T2", "T3", "T4"],
            x_surface=1.0,
            T_surface_series=surf,
            x_core_init=-0.05,
            alpha_init=1e-3,
            downsample_factor=4,
        )
        assert result["converged"], f"optimiser did not converge: {result}"
        assert abs(result["x_core"] - x_core_true) < 0.02, (
            f"x_core_fit = {result['x_core']:.4f}; expected ≈ {x_core_true}"
        )
        # Alpha sanity: within 50% of truth (the alpha-x_core landscape is
        # mildly degenerate so we don't ask for tighter).
        assert abs(result["alpha"] - alpha_true) / alpha_true < 0.5, (
            f"alpha_fit = {result['alpha']:.2e}; expected ≈ {alpha_true:.2e}"
        )

    def test_recovers_known_x_core_with_noise_p95_coverage(self):
        """100 seeds at σ=0.5 °C noise.

        Bars:
        * coverage ≥ 90 / 100 (at most 10 misses for a 95% interval — looser
          than nominal 95% to allow Hessian-approximation slack).
        * spread σ(x_core_fit) < 0.05.
        """
        x_core_true = -0.15
        alpha_true = 1.5e-3
        n_seeds = 100
        sigma = 0.5
        x_fits: list[float] = []
        x_covered = 0
        for seed in range(n_seeds):
            df, surf = _synthetic_dough_observations(
                alpha_true=alpha_true,
                x_core_true=x_core_true,
                in_dough_sensors=("T1", "T2", "T3", "T4"),
                noise_sigma_c=sigma,
                seed=seed,
            )
            r = fit_heat_equation_inverse(
                df=df,
                in_dough_sensors=["T1", "T2", "T3", "T4"],
                x_surface=1.0,
                T_surface_series=surf,
                x_core_init=-0.05,
                alpha_init=1e-3,
                downsample_factor=4,
            )
            if r["converged"]:
                x_fits.append(r["x_core"])
                if _hessian_ci_includes(r["x_core"], r["x_core_se"], x_core_true):
                    x_covered += 1

        spread = float(np.std(x_fits)) if x_fits else float("nan")
        # Stash for the report regenerator.
        TestRealCSVViability._SYNTHETIC_RECOVERY = {
            "n_seeds": n_seeds,
            "sigma_c": sigma,
            "x_core_true": x_core_true,
            "alpha_true": alpha_true,
            "n_converged": len(x_fits),
            "n_covered": x_covered,
            "coverage_rate": x_covered / max(n_seeds, 1),
            "spread": spread,
            "bias": float(np.mean(x_fits) - x_core_true) if x_fits else float("nan"),
        }
        assert x_covered >= 90, (
            f"Hessian 95% CI covered {x_covered}/{n_seeds}; bar is 90/100."
        )
        assert spread < 0.05, (
            f"x_core spread {spread:.4f} ≥ 0.05; bar is 0.05."
        )


# ---------------------------------------------------------------------------
# Class 3 — Real-CSV viability (records evidence; tolerant)
# ---------------------------------------------------------------------------


# (fixture name in CASES, in-dough sensors, surface sensor, optional
# (start, end) within the loaded df). The in-dough/surface picks come from
# the M2a classifier's expected_* annotations.
REAL_FIXTURES: list[dict] = [
    {
        "label": "BA3C_0946",
        "fixture_name": "real_1000BA3C_0946",
        "in_dough": ["T1", "T2", "T3", "T4", "T5"],
        "surface": "T6",
        "x_surface": 5 / 7,
        "expected_curve_idx": 0,
    },
    {
        "label": "BA3C_1759_C0",
        "fixture_name": "real_1000BA3C_1759",
        "in_dough": ["T1", "T2", "T3", "T4", "T5"],
        "surface": "T6",
        "x_surface": 5 / 7,
        "expected_curve_idx": 0,
    },
    {
        "label": "BA3C_1759_C1",
        "fixture_name": "real_1000BA3C_1759",
        "in_dough": ["T1", "T2", "T3", "T4", "T5"],
        "surface": "T6",
        "x_surface": 5 / 7,
        "expected_curve_idx": 1,
    },
    {
        "label": "BA3C_1759_C2",
        "fixture_name": "real_1000BA3C_1759",
        "in_dough": ["T1", "T2", "T3", "T4", "T5"],
        "surface": "T6",
        "x_surface": 5 / 7,
        "expected_curve_idx": 2,
    },
    {
        "label": "100098DE_1351",
        "fixture_name": "real_100098DE_1351",
        "in_dough": ["T1", "T2", "T3", "T4"],
        "surface": "T7",
        "x_surface": 6 / 7,
        "expected_curve_idx": 0,
    },
    {
        "label": "wonder_white",
        "fixture_name": "wonder_white_10k_lidded",
        "in_dough": ["T1", "T2", "T3", "T4", "T5", "T6"],
        "surface": "T7",
        "x_surface": 6 / 7,
        "expected_curve_idx": 0,
    },
    {
        "label": "post_wonder_meal",
        "fixture_name": "post_wonder_meal_lidded",
        "in_dough": ["T1", "T2", "T3", "T4", "T5"],
        "surface": "T7",
        "x_surface": 6 / 7,
        "expected_curve_idx": 0,
    },
]


def _segmented_real_fixture(spec: dict) -> pd.DataFrame:
    case = next(c for c in CASES if c["name"] == spec["fixture_name"])
    df = case["df"].copy()
    starts = case.get("expected_starts") or [0]
    ends = case.get("expected_ends") or [len(df) - 1]
    idx = spec["expected_curve_idx"]
    s = int(starts[idx])
    e = int(ends[idx])
    sub = df.iloc[s : e + 1].reset_index(drop=True)
    # Reset Timestamp to start at zero so the inverter sees a clean t=0.
    if "Timestamp" in sub.columns:
        t0 = float(sub["Timestamp"].iloc[0])
        sub["Timestamp"] = sub["Timestamp"].to_numpy(dtype=float) - t0
    return sub


def _surface_series_from_df(df: pd.DataFrame, surface_sensor: str) -> np.ndarray:
    if surface_sensor in df.columns:
        return df[surface_sensor].to_numpy(dtype=float)
    if "SurfaceTemperature" in df.columns:
        return df["SurfaceTemperature"].to_numpy(dtype=float)
    raise KeyError(f"No surface column for {surface_sensor}")


class TestRealCSVViability:
    """Run the inversion on each real CSV. Records evidence."""

    _RESULTS: dict[str, dict] = {}
    _SYNTHETIC_RECOVERY: dict = {}

    @pytest.mark.parametrize(
        "spec",
        REAL_FIXTURES,
        ids=lambda s: s["label"],
    )
    def test_inversion_runs_on_real_csv(self, spec):
        df = _segmented_real_fixture(spec)
        surf = _surface_series_from_df(df, spec["surface"])
        result = fit_heat_equation_inverse(
            df=df,
            in_dough_sensors=spec["in_dough"],
            x_surface=spec["x_surface"],
            T_surface_series=surf,
            x_core_init=-0.05,
            alpha_init=1e-3,
            downsample_factor=4,
        )
        # Record evidence — do not gatekeep; the report decides go/no-go.
        TestRealCSVViability._RESULTS[spec["label"]] = {
            **result,
            "fixture_name": spec["fixture_name"],
            "expected_curve_idx": spec["expected_curve_idx"],
            "n_in_dough": len(spec["in_dough"]),
            "x_surface": spec["x_surface"],
        }
        # Hard contract: the optimiser must run to completion. Whether
        # x_core landed in a sensible place is a report-level question.
        assert result["converged"] or result["n_iter"] >= 50, (
            f"{spec['label']}: optimiser failed to make progress"
            f" (iter={result['n_iter']})"
        )


# ---------------------------------------------------------------------------
# Class 4 — Robustness under noise
# ---------------------------------------------------------------------------


def _parabolic_extrap_x_core(
    df: pd.DataFrame, in_dough: list[str], sensor_positions: tuple = SENSOR_POSITIONS
) -> Optional[float]:
    """Cheap parabolic-vertex stand-in for the legacy method.

    Fit a parabola to ``(x_i, time_to_60c_i)`` across the in-dough sensors
    and return the vertex. Falls back to the slowest-heating-sensor's
    position when fewer than 3 sensors are eligible.
    """
    pos_map = dict(zip(SENSOR_NAMES, sensor_positions))
    times = []
    xs = []
    for s in in_dough:
        if s not in df.columns:
            continue
        T = df[s].to_numpy(dtype=float)
        idx_above = np.argmax(T >= 60.0)
        if T[idx_above] < 60.0:
            t60 = df["Timestamp"].iloc[-1]
        else:
            t60 = df["Timestamp"].iloc[idx_above]
        times.append(float(t60))
        xs.append(pos_map[s])
    if len(xs) < 3:
        return float(xs[int(np.argmax(times))]) if xs else None
    xs_a = np.array(xs)
    ts_a = np.array(times)
    coeffs = np.polyfit(xs_a, ts_a, 2)
    a, b, _ = coeffs
    if abs(a) < 1e-12:
        return float(xs[int(np.argmax(times))])
    return float(-b / (2.0 * a))


# Keep robustness tight — three fixtures × three sigmas × 30 seeds is a
# reasonable budget. We pick the BA3C cases the user motivated.
ROBUSTNESS_FIXTURES = [
    f for f in REAL_FIXTURES if f["label"] in {"BA3C_0946", "BA3C_1759_C0", "100098DE_1351"}
]


class TestRobustnessUnderNoise:
    """Per-fixture per-σ x_core spread, heat-eq vs parabolic-extrap."""

    _RESULTS: dict[tuple, dict] = {}
    SEEDS_PER_CONDITION = 30

    @pytest.mark.parametrize("sigma_c", [0.0, 0.5, 1.0, 2.0])
    @pytest.mark.parametrize(
        "spec",
        ROBUSTNESS_FIXTURES,
        ids=lambda s: s["label"],
    )
    def test_x_core_spread_under_noise(self, spec, sigma_c):
        base_df = _segmented_real_fixture(spec)
        heat_xs: list[float] = []
        parab_xs: list[float] = []
        for seed in range(self.SEEDS_PER_CONDITION):
            rng = np.random.default_rng(7000 + 31 * seed + int(round(sigma_c * 10)))
            if sigma_c > 0:
                df_b = _perturb_df(base_df, sigma_c, rng)
            else:
                df_b = base_df
            surf = _surface_series_from_df(df_b, spec["surface"])
            try:
                r = fit_heat_equation_inverse(
                    df=df_b,
                    in_dough_sensors=spec["in_dough"],
                    x_surface=spec["x_surface"],
                    T_surface_series=surf,
                    x_core_init=-0.05,
                    alpha_init=1e-3,
                    downsample_factor=4,
                )
                if r["converged"]:
                    heat_xs.append(r["x_core"])
            except Exception:
                pass
            try:
                p = _parabolic_extrap_x_core(df_b, spec["in_dough"])
                if p is not None and math.isfinite(p):
                    parab_xs.append(p)
            except Exception:
                pass
        TestRobustnessUnderNoise._RESULTS[(spec["label"], sigma_c)] = {
            "heat_eq_n": len(heat_xs),
            "heat_eq_mean": float(np.mean(heat_xs)) if heat_xs else None,
            "heat_eq_std": float(np.std(heat_xs)) if heat_xs else None,
            "parab_n": len(parab_xs),
            "parab_mean": float(np.mean(parab_xs)) if parab_xs else None,
            "parab_std": float(np.std(parab_xs)) if parab_xs else None,
        }
        # Soft contract: at least half the seeds must converge (we want a
        # spread number to report, not an empty list).
        assert len(heat_xs) >= self.SEEDS_PER_CONDITION // 2, (
            f"{spec['label']} σ={sigma_c}: only "
            f"{len(heat_xs)}/{self.SEEDS_PER_CONDITION} heat-eq fits converged"
        )


# ---------------------------------------------------------------------------
# Report regenerator (invoked manually via -k regenerate_report)
# ---------------------------------------------------------------------------


def _regenerate_report() -> str:
    """Render the markdown report from the class-level result dicts.

    Invoke via::

        pytest tests/test_heat_equation_research.py -v
        python -m tests.test_heat_equation_research

    Returns the report as a string.
    """
    syn = TestRealCSVViability._SYNTHETIC_RECOVERY
    real = TestRealCSVViability._RESULTS
    rob = TestRobustnessUnderNoise._RESULTS

    lines: list[str] = []
    lines.append("# Method 3 — Heat-Equation Extrapolation Research")
    lines.append("")
    lines.append("HMS Ambush research mission. Empirically tests whether the")
    lines.append("1D heat-equation inverse problem can recover the loaf core")
    lines.append("position past the deepest probe sensor on the existing real")
    lines.append("CSVs. Research-only — no production wiring.")
    lines.append("")

    # --- Executive summary
    lines.append("## Executive summary")
    lines.append("")
    if syn:
        lines.append(
            f"Synthetic ground-truth recovery at σ=0.5 °C: bias = "
            f"{syn['bias']:.4f}, spread σ(x_core) = {syn['spread']:.4f}, "
            f"95% Hessian-CI coverage = {syn['n_covered']}/{syn['n_seeds']}."
        )
    else:
        lines.append("Synthetic recovery: NOT RUN.")
    if real:
        rmses = [r["rmse_per_sensor"] for r in real.values() if math.isfinite(r["rmse_per_sensor"])]
        rhos = [r["rho_alpha_xcore"] for r in real.values() if math.isfinite(r["rho_alpha_xcore"])]
        if rmses:
            lines.append(
                f"Real-CSV residual RMSE: median = {np.median(rmses):.2f} °C; "
                f"max = {np.max(rmses):.2f} °C across {len(rmses)} fixtures."
            )
        if rhos:
            lines.append(
                f"Real-CSV |rho_alpha_xcore|: median = {np.median(np.abs(rhos)):.3f}; "
                f"max = {np.max(np.abs(rhos)):.3f}."
            )
    lines.append("")

    # --- Method
    lines.append("## Method")
    lines.append("")
    lines.append(
        "Forward solver: method-of-lines on a uniform spatial grid of 30 "
        "points. Spatial second derivative via central differences; Neumann "
        "BC at x_core via the symmetric ghost-cell trick "
        "(T_xx[0] ≈ 2(T[1] - T[0]) / dx²); Dirichlet BC at x_surface enforced "
        "by a stiff clamp `(T_surf(t) - T[N-1]) / τ` with `τ = 0.05 dx²/α`. "
        "Time integration: `scipy.integrate.solve_ivp` with method LSODA, "
        "rtol=1e-5, atol=1e-6."
    )
    lines.append("")
    lines.append(
        "Inverse fit: Nelder-Mead minimisation of SSE in (log α, x_core) "
        "space (log keeps α positive without a constraint). xatol=1e-3, "
        "fatol=1e-2, adaptive=True. Confidence intervals derived from a "
        "5-point central-difference Hessian: Cov ≈ 2σ²·H⁻¹ where σ² = "
        "SSE/n_obs, then delta-method conversion of var(log α) to var(α)."
    )
    lines.append("")
    lines.append(
        "Observation grid: every 4th time-sample (downsample_factor=4) "
        "across the in-dough sensors only. The surface time-series is "
        "interpolated to the same grid and used as the Dirichlet boundary."
    )
    lines.append("")

    # --- Synthetic recovery
    lines.append("## Synthetic ground-truth recovery")
    lines.append("")
    if syn:
        lines.append(
            f"100 seeds, σ=0.5 °C, x_core_true = {syn['x_core_true']}, "
            f"α_true = {syn['alpha_true']:.2e}."
        )
        lines.append("")
        lines.append("| metric | value |")
        lines.append("|---|---|")
        lines.append(f"| seeds converged | {syn['n_converged']}/{syn['n_seeds']} |")
        lines.append(f"| bias (mean(x_core_fit) − x_core_true) | {syn['bias']:.5f} |")
        lines.append(f"| spread σ(x_core_fit) | {syn['spread']:.5f} |")
        lines.append(f"| Hessian 95% CI coverage | {syn['n_covered']}/{syn['n_seeds']} |")
    lines.append("")

    # --- Real-CSV table
    lines.append("## Real-CSV inferred x_core")
    lines.append("")
    lines.append(
        "| fixture | x_core_fit | 95% CI | α (1/s) | ρ(α, x_core) | RMSE (°C) | extrapolated |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for label, r in real.items():
        ci_lo = r["x_core"] - 1.96 * r["x_core_se"] if math.isfinite(r["x_core_se"]) else float("nan")
        ci_hi = r["x_core"] + 1.96 * r["x_core_se"] if math.isfinite(r["x_core_se"]) else float("nan")
        ci_str = (
            f"[{ci_lo:.3f}, {ci_hi:.3f}]"
            if math.isfinite(ci_lo)
            else "n/a"
        )
        rho_str = f"{r['rho_alpha_xcore']:.3f}" if math.isfinite(r["rho_alpha_xcore"]) else "n/a"
        lines.append(
            f"| {label} | {r['x_core']:.4f} | {ci_str} | {r['alpha']:.2e} | "
            f"{rho_str} | {r['rmse_per_sensor']:.2f} | {r['extrapolated']} |"
        )
    lines.append("")

    # --- Noise robustness
    lines.append("## Noise robustness (heat-eq vs parabolic extrapolation)")
    lines.append("")
    lines.append("| fixture | σ (°C) | heat-eq mean ± std | parabolic mean ± std |")
    lines.append("|---|---|---|---|")
    fixture_labels = sorted({k[0] for k in rob.keys()})
    for fl in fixture_labels:
        for sigma in [0.0, 0.5, 1.0, 2.0]:
            key = (fl, sigma)
            if key not in rob:
                continue
            r = rob[key]
            heat_str = (
                f"{r['heat_eq_mean']:.4f} ± {r['heat_eq_std']:.4f}"
                if r["heat_eq_mean"] is not None
                else "n/a"
            )
            parab_str = (
                f"{r['parab_mean']:.4f} ± {r['parab_std']:.4f}"
                if r["parab_mean"] is not None
                else "n/a"
            )
            lines.append(f"| {fl} | {sigma} | {heat_str} | {parab_str} |")
    lines.append("")

    # --- Recommendation
    lines.append("## Recommendation")
    lines.append("")
    # Decide GO / GO-WITH-CAVEATS / NO-GO based on the empirical data.
    verdict = "NO-GO"
    rationale: list[str] = []
    rmses = [r["rmse_per_sensor"] for r in real.values() if math.isfinite(r["rmse_per_sensor"])]
    rhos = [abs(r["rho_alpha_xcore"]) for r in real.values() if math.isfinite(r["rho_alpha_xcore"])]
    if syn and real:
        synth_ok = (
            syn["n_covered"] >= 90
            and abs(syn["bias"]) < 0.02
            and syn["spread"] < 0.05
        )
        rmse_ok = bool(rmses) and max(rmses) < 2.0
        rho_ok = bool(rhos) and max(rhos) < 0.8
        if synth_ok and rmse_ok and rho_ok:
            verdict = "GO"
            rationale.append("synthetic recovery passes; real RMSE < 2 °C; |rho| < 0.8.")
        elif synth_ok and (rmse_ok or rho_ok):
            verdict = "GO-WITH-CAVEATS"
            if not rmse_ok:
                rationale.append("real-CSV residual RMSE exceeds 2 °C on some fixtures.")
            if not rho_ok:
                rationale.append("alpha-x_core correlation exceeds 0.8 — partially degenerate.")
        else:
            verdict = "NO-GO"
            if not synth_ok:
                rationale.append("synthetic ground-truth recovery does not meet bars.")
            if rhos and max(rhos) > 0.95:
                rationale.append(
                    "alpha-x_core correlation > 0.95 on real data — inverse problem is degenerate."
                )
    lines.append(f"**Verdict: {verdict}**")
    if rationale:
        lines.append("")
        for r in rationale:
            lines.append(f"- {r}")
    lines.append("")
    lines.append(
        "Conditions for production wiring (per mission spec): real-CSV "
        "residual RMSE < 2 °C across all fixtures *and* α-x_core correlation "
        "|rho| < 0.8 on every fixture. The inverse problem must not be too "
        "degenerate."
    )
    lines.append("")

    return "\n".join(lines)


def write_report(path: Optional[str] = None) -> str:
    """Run all four classes manually and write the report markdown file.

    Used by the report regenerator (not pytest itself). Run via::

        python -c "from tests.test_heat_equation_research import write_report; write_report()"
    """
    if path is None:
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "baselines",
            "heat_equation_extrapolation_research.md",
        )
    body = _regenerate_report()
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path
