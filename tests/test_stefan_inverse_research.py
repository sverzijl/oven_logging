"""HMS Triumph — M9 1D Stefan-front inverse research tests.

Three test classes:

* :class:`TestForwardSolverSanity` — analytical Stefan-Neumann match +
  reduction-to-heat-eq when ρL_eff = 0.
* :class:`TestSyntheticRecovery` — single-seed end-to-end joint fit on a
  synthetic generated with a different ΔT_smear (the M7 lesson: don't
  self-grade an inverse-problem study).
* :class:`TestModuleAPI` — public-API smoke: dict shape, correlation matrix
  size, conversion of literature values into normalised units.

The full multi-fixture viability sweep lives in
``tests/_driver_stefan_inverse.py`` (~25-30 min wall-time). pytest
imports this file but does NOT block on the driver — the driver is run
manually and its outputs (.json + .md) are checked in.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.stefan_inverse import (  # noqa: E402
    ALPHA_CRUST_LIT_SI,
    ALPHA_DOUGH_LIT_SI,
    LOAF_THICKNESS_M,
    RHO_L_EFF_LIT_SI,
    T_FRONT_C,
    classical_stefan_neumann,
    fit_stefan_inverse_joint,
    fit_stefan_inverse_pinned,
    solve_stefan_forward,
)


SENSOR_NAMES = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")
SENSOR_POSITIONS = tuple(i / 7 for i in range(8))


# ---------------------------------------------------------------------------
# Class 1 — Forward solver sanity
# ---------------------------------------------------------------------------


class TestForwardSolverSanity:
    """Two analytical sanity checks. If these fail, the rest is moot."""

    def test_zero_latent_reduces_to_heat_equation(self):
        """rhoL_eff = 0 → Stefan forward solver matches a pure heat-eq erfc.

        Surface held at 200 °C, dough initially at 22 °C, semi-infinite
        (Neumann far enough away that diffusion length doesn't reach it).
        Standard `T(x, t) - T_init = (T_surf - T_init)·erfc((x_surf - x)/(2√(αt)))`.
        """
        from scipy.special import erfc

        T_init = 22.0
        T_surf = 200.0
        alpha = 1e-3
        t = np.linspace(0.0, 200.0, 50)
        surf = np.full_like(t, T_surf)
        sample_x = np.array([0.7, 0.85, 0.95])

        T_num = solve_stefan_forward(
            x_core=-1.0,
            x_surface=1.0,
            alpha_dough=alpha,
            alpha_crust=alpha,
            rhoL_eff=0.0,
            t_grid=t,
            T_surface_series=surf,
            T_initial=T_init,
            n_spatial=80,
            sample_x=sample_x,
            delta_T_smear=1.0,
        )
        T_ana = np.empty_like(T_num)
        for i, ti in enumerate(t):
            if ti <= 0:
                T_ana[i, :] = T_init
                continue
            arg = (1.0 - sample_x) / (2.0 * np.sqrt(alpha * ti))
            T_ana[i, :] = T_init + (T_surf - T_init) * erfc(arg)

        # Skip first 5 samples (stiff-clamp transient).
        diff = np.abs(T_num[5:, :] - T_ana[5:, :])
        assert diff.max() < 2.0, (
            f"zero-latent reduction max err {diff.max():.3f} °C exceeds 2 °C "
            f"(per-position max = {diff.max(axis=0)})"
        )

    def test_classical_stefan_neumann_match(self):
        """One-phase Stefan-Neumann: Ste = 2 (less latent-dominated → tighter).

        Bar of 3 °C; the residual gap is the unavoidable enthalpy-method
        smearing-window bias (well-known limitation; tightening dT does
        not remove it because rhoL_eff is conserved).
        """
        T_surf = 150.0
        T_init = T_FRONT_C  # one-phase: dough already at melting temp
        alpha = 1e-3
        Ste = 2.0
        rhoL = (T_surf - T_init) / Ste  # = 25 K

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
        diff = np.abs(T_num[20:, :] - T_ana[20:, :])
        assert diff.max() < 3.0, (
            f"Stefan-Neumann max err {diff.max():.3f} °C exceeds 3 °C "
            f"(per-position max = {diff.max(axis=0)})"
        )
        # Sanity: front position is monotonic and inside domain at t_end.
        assert s_ana[-1] < 1.0
        assert s_ana[0] >= 1.0 - 1e-6  # at t=0 front is at the surface


# ---------------------------------------------------------------------------
# Class 2 — Synthetic ground-truth recovery
# ---------------------------------------------------------------------------


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
) -> pd.DataFrame:
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
    return df


class TestSyntheticRecovery:
    """Single-seed gating test. Generator dT=0.3 vs inverter dT=1.0.

    The brief calls for 10-seed recovery in the driver. The pytest version
    runs ONE seed (~2 min) and asserts the joint fit lands close to truth.
    Token budget for the test file is more important here than coverage —
    the driver's 10 seeds will catch anything systematic.
    """

    @pytest.mark.slow
    def test_single_seed_recovery(self):
        df = _synthetic_real_bake(seed=0)
        r = fit_stefan_inverse_joint(
            df=df,
            in_dough_sensors=["T1", "T2", "T3", "T4", "T5"],
            x_surface_continuous=1.0,
            init={
                "x_core": -0.05,
                "alpha_dough": 1e-3,
                "alpha_crust": 1e-3,
                "rhoL_eff": 50.0,
            },
            downsample_factor=4,
            n_spatial=30,
            delta_T_smear=1.0,
            max_iter=400,
        )
        # The smearing-window mismatch (gen dT=0.3 vs inv dT=1.0) introduces
        # a few-cm bias on x_core. Bar at 0.10 — clean signal-recovery, not
        # the strict <0.02 a self-test would have.
        assert math.isfinite(r["x_core"])
        assert abs(r["x_core"] - (-0.10)) < 0.10, (
            f"x_core fit {r['x_core']:.4f} too far from true −0.10 "
            f"(bar 0.10)"
        )
        # RMSE bar: 3 °C — generous to cover noise + smearing mismatch.
        assert r["rmse_per_sensor"] < 3.0, (
            f"RMSE {r['rmse_per_sensor']:.3f} °C exceeds 3 °C bar"
        )
        # Joint fit should be well-conditioned on the synthetic.
        if math.isfinite(r["max_abs_off_diag_correlation"]):
            assert r["max_abs_off_diag_correlation"] < 0.95, (
                f"Joint fit too degenerate; max |ρ| = "
                f"{r['max_abs_off_diag_correlation']:.3f}"
            )


# ---------------------------------------------------------------------------
# Class 3 — Module API smoke
# ---------------------------------------------------------------------------


class TestModuleAPI:
    """Cheap shape/contract checks that don't run the full inverse fit."""

    def test_joint_result_shape(self):
        """Run a tiny 1-step fit (max_iter=1) and verify dict shape."""
        # Tiny synthetic so the fit returns immediately.
        T_init = 22.0
        t = np.arange(20, dtype=float) * 5.0
        surf = np.linspace(T_init, 100.0, 20)
        df = pd.DataFrame({"Timestamp": t})
        for s in SENSOR_NAMES:
            df[s] = surf  # placeholder; the inverter runs anyway
        r = fit_stefan_inverse_joint(
            df=df,
            in_dough_sensors=["T1", "T2"],
            x_surface_continuous=1.0,
            init={
                "x_core": -0.05,
                "alpha_dough": 1e-3,
                "alpha_crust": 1e-3,
                "rhoL_eff": 50.0,
            },
            downsample_factor=2,
            n_spatial=20,
            delta_T_smear=1.0,
            max_iter=2,  # exit immediately
        )
        for key in (
            "x_core",
            "alpha_dough",
            "alpha_crust",
            "rhoL_eff",
            "x_core_se",
            "alpha_dough_se",
            "alpha_crust_se",
            "rhoL_eff_se",
            "full_correlation_matrix",
            "max_abs_off_diag_correlation",
            "sse",
            "rmse_per_sensor",
            "n_obs",
            "converged",
            "n_iter",
            "T_initial",
            "x_surface_continuous",
            "extrapolated",
            "bc_source",
        ):
            assert key in r, f"missing key: {key}"
        # 4×4 correlation matrix.
        corr = r["full_correlation_matrix"]
        assert isinstance(corr, list) and len(corr) == 4
        for row in corr:
            assert len(row) == 4

    def test_pinned_result_shape(self):
        """Pinned variant returns the same dict shape, plus the pinned values."""
        T_init = 22.0
        t = np.arange(20, dtype=float) * 5.0
        surf = np.linspace(T_init, 100.0, 20)
        df = pd.DataFrame({"Timestamp": t})
        for s in SENSOR_NAMES:
            df[s] = surf
        r = fit_stefan_inverse_pinned(
            df=df,
            in_dough_sensors=["T1", "T2"],
            x_surface_continuous=1.0,
            downsample_factor=2,
            n_spatial=20,
            delta_T_smear=1.0,
            max_iter=2,
        )
        for key in (
            "x_core",
            "x_core_se",
            "alpha_dough_pinned",
            "alpha_crust_pinned",
            "rhoL_eff_pinned",
            "alpha_dough_lit_si",
            "alpha_crust_lit_si",
            "rhoL_eff_lit_si",
            "loaf_thickness_m",
            "rmse_per_sensor",
            "converged",
            "variant",
        ):
            assert key in r, f"missing key: {key}"
        # The literature-pinned values should match the module constants.
        assert r["alpha_dough_lit_si"] == pytest.approx(ALPHA_DOUGH_LIT_SI)
        assert r["alpha_crust_lit_si"] == pytest.approx(ALPHA_CRUST_LIT_SI)
        assert r["rhoL_eff_lit_si"] == pytest.approx(RHO_L_EFF_LIT_SI)
        assert r["loaf_thickness_m"] == pytest.approx(LOAF_THICKNESS_M)
        assert r["variant"] == "pinned"

    def test_stefan_neumann_lambda_is_positive_root(self):
        """λ should be in (0, 5) for reasonable Stefan numbers."""
        from src.data.spatial_reconstruction.stefan_inverse import (
            _stefan_neumann_lambda,
        )

        for Ste in (0.1, 0.5, 1.0, 2.0, 5.0):
            lam = _stefan_neumann_lambda(Ste)
            assert 0.0 < lam < 5.0
            # λ grows with Ste.
        lams = [_stefan_neumann_lambda(s) for s in (0.1, 0.5, 1.0, 2.0)]
        assert lams[0] < lams[1] < lams[2] < lams[3]
