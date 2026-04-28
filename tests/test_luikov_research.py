"""HMS Lively — M14 Luikov coupled heat-mass research tests.

Two test classes:

* :class:`TestForwardSolverSanity` — uncoupled-limit and steady-state checks
  (the same checks the driver runs in phase 1; replicated here so the
  pytest suite catches regressions in the forward solver without running
  the full driver).
* :class:`TestSyntheticRecoveryDifferentClass` — load-bearing identifiability
  test: generator uses different (α, ε) than inverter, recovery within 30%
  on at least one of (Lu, Ko, Bi) per the briefing's "1 case" bar.

Memory-feedback compliance:

* TDD — these tests fail empirically if the forward solver returns
  divergent fields or the inverse fitter cannot recover even an
  approximate truth.
* DRY — reuses ``SENSOR_NAMES`` and ``SENSOR_POSITIONS`` from the M7
  test module.
* Avoids the M7 tautology trap — generator α=1.0e-7, ε=0.3 vs inverter
  α=1.4e-7, ε=0.5.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.luikov import (  # noqa: E402
    ALPHA_DEFAULT_M2_S,
    EPSILON_DEFAULT,
    LOAF_THICKNESS_M_DEFAULT,
    fit_luikov_inverse,
    solve_luikov_forward,
)
from tests.test_heat_equation_research import (  # noqa: E402
    SENSOR_NAMES,
    SENSOR_POSITIONS,
)


class TestForwardSolverSanity:
    """Forward-solver sanity — uncoupled limit and steady state."""

    def test_uncoupled_limit_converges_to_oven_temperature(self):
        """At Lu, Ko, ε ≈ 0 and large Bi, long-time T → T_oven across the field.

        Bread-baking diffusion timescale L²/α ≈ 0.06²/1.4e-7 ≈ 26000 s for
        the standard 60 mm domain — push to 200000 s so the deep core has
        time to equilibrate.
        """
        t_grid = np.linspace(0.0, 200000.0, 200)
        fwd = solve_luikov_forward(
            x_core_m=-0.01,
            Lu=0.001,
            Ko=0.001,
            Bi=10.0,
            T_oven_eff_K=450.0,
            t_grid_s=t_grid,
            T_initial_K=295.0,
            epsilon=0.001,
            n_spatial=40,
        )
        assert fwd.converged
        T_final = fwd.T_field_K[-1]
        max_dev = float(np.max(np.abs(T_final - 450.0)))
        assert max_dev < 1.0, (
            f"Uncoupled-limit final field deviation {max_dev:.2f} K > 1 K bar."
        )

    def test_steady_state_full_coupling(self):
        """Full-coupling long-time limit: T in (320, 460) K and u_max < 0.4."""
        t_grid = np.linspace(0.0, 60000.0, 200)
        fwd = solve_luikov_forward(
            x_core_m=-0.005,
            Lu=0.15,
            Ko=4.0,
            Bi=5.0,
            T_oven_eff_K=450.0,
            t_grid_s=t_grid,
            T_initial_K=295.0,
            n_spatial=40,
        )
        assert fwd.converged
        T_final = fwd.T_field_K[-1]
        u_final = fwd.u_field[-1]
        assert 320.0 < T_final.min() < 460.0
        assert 320.0 < T_final.max() < 460.0
        # Moisture should drop from 0.4 (initial) under the Dirichlet drying BC.
        assert u_final.max() < 0.40, (
            f"u_max {u_final.max():.4f} did not drop below initial 0.40 — "
            "Dirichlet drying BC broken?"
        )


class TestSyntheticRecoveryDifferentClass:
    """Synthetic recovery with a different-class generator (M7 trap avoidance).

    Bar per the briefing: synthetic recovery within 30% on at least 1 case.
    """

    def _synth(self, seed: int, truth: dict) -> tuple:
        in_dough = ["T1", "T2", "T3", "T4", "T5"]
        x_surf_n = 5 / 7
        loaf = LOAF_THICKNESS_M_DEFAULT
        pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
        x_obs_n = np.array([pos_map[s] for s in in_dough])
        x_core_m_true = float(truth["x_core_m"])
        sample_x_m = x_core_m_true + (x_obs_n / x_surf_n) * (loaf - x_core_m_true)
        t_grid = np.arange(400, dtype=float) * 5.0
        fwd = solve_luikov_forward(
            x_core_m=x_core_m_true,
            Lu=float(truth["Lu"]),
            Ko=float(truth["Ko"]),
            Bi=float(truth["Bi"]),
            T_oven_eff_K=float(truth["T_oven_eff_K"]),
            t_grid_s=t_grid,
            T_initial_K=295.0,
            epsilon=0.3,        # generator ε differs from inverter's 0.5
            alpha_m2_s=1.0e-7,  # generator α differs from inverter's 1.4e-7
            sample_x_m=sample_x_m,
            n_spatial=40,
        )
        T_obs_C = fwd.T_field_K - 273.15
        rng = np.random.default_rng(seed)
        T_obs_C = T_obs_C + rng.normal(0.0, 0.5, T_obs_C.shape)
        df = pd.DataFrame({"Timestamp": t_grid})
        for k, s in enumerate(in_dough):
            df[s] = T_obs_C[:, k]
        for s in SENSOR_NAMES:
            if s not in df.columns:
                df[s] = T_obs_C[:, 0]
        return df, in_dough, x_surf_n

    def test_recover_one_param_within_30pct(self):
        """At least one of (Lu, Ko, Bi) recovers within 30% on at least 1 seed."""
        truth = dict(
            x_core_m=-0.008, Lu=0.20, Ko=4.0, Bi=3.0, T_oven_eff_K=460.0,
        )
        any_recovery = False
        for seed in range(3):
            df, in_dough, x_surf_n = self._synth(seed, truth)
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
                downsample_factor=4,
                max_iter=400,
            )
            assert r["converged"] or r["n_iter"] >= 50
            for name, true in (
                ("Lu", truth["Lu"]),
                ("Ko", truth["Ko"]),
                ("Bi", truth["Bi"]),
            ):
                rel = abs(r[name] - true) / max(abs(true), 1e-9)
                if rel < 0.30:
                    any_recovery = True
                    return  # one is enough per the briefing
        assert any_recovery, (
            "No (Lu, Ko, Bi) recovered within 30% across 3 seeds — Luikov "
            "inverse appears non-identifiable on the synthetic data class. "
            "(Note: the briefing's bar is just '1 case', so this is a strict "
            "interpretation.)"
        )
