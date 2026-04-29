"""HMS Endeavour — M17 forward solver sanity for Luikov-Dirichlet hybrid.

Forward sanity per the briefing:

1. ``test_dirichlet_anchors_surface_temperature``
2. ``test_constant_surface_steady_state``
3. ``test_alpha_T_transition``
4. ``test_bottom_BC_heat_flux``
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.luikov_dirichlet_hybrid import (  # noqa: E402
    SPRING_TEMP_LOWER_K,
    SPRING_TEMP_UPPER_K,
    _alpha_profile,
    infer_core_depth_from_forward,
    solve_luikov_dirichlet_hybrid_forward,
)


class TestForwardSanity:
    def test_dirichlet_anchors_surface_temperature(self):
        """Constant T_surface = 350 K should be reflected at the surface
        node throughout the run (stiff Dirichlet clamp)."""
        n_t = 200
        t_grid = np.linspace(0.0, 30.0 * 60.0, n_t)
        T_surface_K = np.full(n_t, 350.0)

        fwd = solve_luikov_dirichlet_hybrid_forward(
            L_m=0.100,
            D_m=0.080,
            Lu=0.10,
            q_bottom_eff=0.0,
            alpha_ratio=1.0,
            t_grid_s=t_grid,
            T_surface_K_t=T_surface_K,
            x_surface_continuous_normalised=0.5,  # surface mid-probe
            T_initial_K=295.0,
            n_spatial=40,
        )
        assert fwd.converged, "Forward did not converge"
        # Surface (top of dough domain, index 0) should be ~ T_surface.
        T_top = fwd.T_full_K[:, 0]
        # After a brief transient the clamp should hold.
        late = T_top[20:]
        max_dev = float(np.max(np.abs(late - 350.0)))
        assert max_dev < 1.0, (
            f"Top temperature deviated by {max_dev:.2f} K from imposed 350 K"
        )

    def test_constant_surface_steady_state(self):
        """Constant Dirichlet surface + zero bottom flux → uniform T at
        long times (everything equilibrates to the surface).

        Use elevated α_pre (1e-5 m²/s) so the diffusion timescale fits in
        a tractable test run; this exercises the same numerics as the
        physical α=1.4e-7 case but converges faster.
        """
        n_t = 600
        t_grid = np.linspace(0.0, 6.0 * 3600.0, n_t)
        T_surface_K = np.full(n_t, 380.0)

        fwd = solve_luikov_dirichlet_hybrid_forward(
            L_m=0.080,
            D_m=0.070,
            Lu=0.10,
            q_bottom_eff=0.0,         # insulated bottom
            alpha_ratio=1.0,          # disable spring nonlinearity
            t_grid_s=t_grid,
            T_surface_K_t=T_surface_K,
            x_surface_continuous_normalised=0.7,
            T_initial_K=295.0,
            n_spatial=30,
            alpha_pre_m2_s=1.0e-5,    # accelerate diffusion for the test
            epsilon=0.0,              # disable phase-change coupling
        )
        assert fwd.converged
        T_final = fwd.T_full_K[-1]
        # All cells should be close to 380 K once α-driven diffusion has
        # equilibrated the insulated rod.
        max_dev = float(np.max(np.abs(T_final - 380.0)))
        assert max_dev < 5.0, (
            f"Steady-state max deviation from 380 K: {max_dev:.2f}; "
            f"T_final={T_final}"
        )

    def test_alpha_T_transition(self):
        """α(T) profile changes the effective diffusivity around the
        spring window."""
        # Direct check on the helper (cheap and decisive).
        T_low = np.array([300.0, 320.0])
        T_mid = np.array([0.5 * (SPRING_TEMP_LOWER_K + SPRING_TEMP_UPPER_K)])
        T_high = np.array([350.0, 400.0])
        a_low = _alpha_profile(T_low, 1.4e-7, 0.4)
        a_mid = _alpha_profile(T_mid, 1.4e-7, 0.4)
        a_high = _alpha_profile(T_high, 1.4e-7, 0.4)
        assert np.allclose(a_low, 1.4e-7)
        assert np.allclose(a_high, 1.4e-7 * 0.4)
        assert np.isclose(a_mid[0], 1.4e-7 * 0.5 * (1.0 + 0.4), rtol=1e-3)

        # Indirect check: a profile with α_ratio=1 heats the deep core
        # faster than α_ratio=0.3 (since α drops while crossing 50→65 °C).
        n_t = 400
        t_grid = np.linspace(0.0, 60.0 * 60.0, n_t)
        # Surface ramp from 295 → 400 K
        T_surface_K = 295.0 + (400.0 - 295.0) * (1.0 - np.exp(-t_grid / 600.0))

        fwd_low = solve_luikov_dirichlet_hybrid_forward(
            L_m=0.100, D_m=0.080, Lu=0.10, q_bottom_eff=0.0,
            alpha_ratio=0.3,
            t_grid_s=t_grid, T_surface_K_t=T_surface_K,
            x_surface_continuous_normalised=0.7,
            T_initial_K=295.0, n_spatial=40,
        )
        fwd_unity = solve_luikov_dirichlet_hybrid_forward(
            L_m=0.100, D_m=0.080, Lu=0.10, q_bottom_eff=0.0,
            alpha_ratio=1.0,
            t_grid_s=t_grid, T_surface_K_t=T_surface_K,
            x_surface_continuous_normalised=0.7,
            T_initial_K=295.0, n_spatial=40,
        )
        assert fwd_low.converged and fwd_unity.converged
        # Take temperature at the deep end at ~half time.
        i_mid = n_t // 2
        T_low_deep = fwd_low.T_full_K[i_mid, -1]
        T_unity_deep = fwd_unity.T_full_K[i_mid, -1]
        assert T_unity_deep > T_low_deep, (
            f"α=1 deep T={T_unity_deep:.1f} K should exceed α=0.3 deep "
            f"T={T_low_deep:.1f} K"
        )

    def test_bottom_BC_heat_flux(self):
        """``q_bottom_eff`` controls bottom-node energy exchange with the
        tin: high q_bot pulls T(L) toward T_initial; low q_bot lets the
        bottom warm by conduction from the Dirichlet-anchored hot top.

        Use elevated α_pre so the test resolves the BC effect inside a
        tractable runtime.
        """
        n_t = 400
        t_grid = np.linspace(0.0, 4.0 * 3600.0, n_t)
        T_surface_K = np.full(n_t, 380.0)

        common = dict(
            L_m=0.080, D_m=0.070, Lu=0.10,
            alpha_ratio=1.0,
            t_grid_s=t_grid, T_surface_K_t=T_surface_K,
            x_surface_continuous_normalised=0.7,
            T_initial_K=295.0, n_spatial=30,
            alpha_pre_m2_s=1.0e-5,
            epsilon=0.0,
        )

        fwd_zero = solve_luikov_dirichlet_hybrid_forward(
            q_bottom_eff=0.0, **common,
        )
        fwd_high = solve_luikov_dirichlet_hybrid_forward(
            q_bottom_eff=200.0, **common,
        )
        assert fwd_zero.converged and fwd_high.converged
        T_bot_zero = fwd_zero.T_full_K[-1, -1]
        T_bot_high = fwd_high.T_full_K[-1, -1]
        # High q_bot pulls bottom toward T_initial (295 K) → cooler bottom
        # than the insulated case (which equilibrates to 380 K).
        assert T_bot_high < T_bot_zero - 10.0, (
            f"High q_bot bottom T={T_bot_high:.1f} K should be at least "
            f"10 K below zero-q_bot bottom T={T_bot_zero:.1f} K"
        )
        assert T_bot_zero > 350.0, (
            f"Zero-q_bot bottom should heat to near 380; got {T_bot_zero:.1f} K"
        )


class TestCoreDepthInference:
    def test_core_at_bottom_for_strong_top_drive(self):
        """When the top is held hot and the bottom is mildly coupled,
        the slowest-rising point lies near the bottom."""
        n_t = 200
        t_grid = np.linspace(0.0, 20.0 * 60.0, n_t)
        T_surface_K = np.full(n_t, 470.0)

        fwd = solve_luikov_dirichlet_hybrid_forward(
            L_m=0.100, D_m=0.080, Lu=0.10, q_bottom_eff=2.0,
            alpha_ratio=1.0,
            t_grid_s=t_grid, T_surface_K_t=T_surface_K,
            x_surface_continuous_normalised=0.7,
            T_initial_K=295.0, n_spatial=60,
        )
        assert fwd.converged
        x_core_mm = infer_core_depth_from_forward(
            fwd.T_full_K, fwd.x_grid_m, fwd.t_grid_s
        )
        # Surface in loaf frame: 0.080 - 0.7*0.095 = 0.0135 m → x in [13.5,
        # 100] mm. With strong top drive and weak bottom coupling, the
        # coldest spot at mid-bake should be near the bottom (x ≈ L).
        assert x_core_mm > 60.0, (
            f"x_core={x_core_mm:.1f} mm should be > 60 mm for top-driven case"
        )
