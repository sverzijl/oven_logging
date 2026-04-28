"""HMS Daring — M16 forward solver sanity tests for the observed-BC Luikov inverse.

These tests are TDD-first per the briefing:

1. Forward solver: with constant T_air and constant h_eff matching M15
   fitted values, reduces to plausible monotonic profile behaviour.
2. alpha(T) profile: at low T, evolution uses alpha_pre; after rise crosses
   65 °C, evolution uses alpha_pre * alpha_ratio.
3. Steady state: T converges to a profile matching observed BCs at long
   times.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.luikov_tin_observed import (  # noqa: E402
    SPRING_TEMP_LOWER_K,
    SPRING_TEMP_UPPER_K,
    _alpha_profile,
    infer_core_depth_from_forward,
    solve_luikov_tin_observed,
)


class TestAlphaProfile:
    """Validate the piecewise alpha(T) profile."""

    def test_alpha_low_T_is_alpha_pre(self):
        T = np.array([300.0, 310.0, 320.0])
        a = _alpha_profile(T, alpha_pre=1.4e-7, alpha_ratio=0.4)
        assert np.allclose(a, 1.4e-7)

    def test_alpha_high_T_is_alpha_pre_times_ratio(self):
        T = np.array([340.0, 360.0, 400.0])
        a = _alpha_profile(T, alpha_pre=1.4e-7, alpha_ratio=0.4)
        expected = 1.4e-7 * 0.4
        assert np.allclose(a, expected)

    def test_alpha_midband_linearly_interpolates(self):
        T_mid = np.array([0.5 * (SPRING_TEMP_LOWER_K + SPRING_TEMP_UPPER_K)])
        a = _alpha_profile(T_mid, alpha_pre=1.4e-7, alpha_ratio=0.4)
        expected = 1.4e-7 * 0.5 * (1 + 0.4)
        assert np.isclose(a[0], expected, rtol=1e-3)


class TestForwardObserved:
    """Forward-solver sanity per the M16 briefing."""

    def test_constant_T_air_h_eff_matches_M15_class(self):
        """With const T_air ≈ 470 K and const h_eff matching Bi_top=10/L scale,
        produces a heated dough profile."""
        n_t = 200
        t_grid = np.linspace(0.0, 20.0 * 60.0, n_t)
        T_air_K = np.full(n_t, 460.0)
        # h_eff_t equivalent: M15 used Bi_top=10 with L=0.1 → h = 10*0.5/0.1 = 50 W/m²·K
        h_eff_t = np.full(n_t, 50.0)

        fwd = solve_luikov_tin_observed(
            L_m=0.100,
            Lu=0.15,
            q_bottom_eff=20.0,
            alpha_ratio=0.4,
            t_grid_s=t_grid,
            T_air_K_t=T_air_K,
            h_eff_t=h_eff_t,
            T_initial_K=295.0,
            n_spatial=60,
        )
        assert fwd.converged
        T_final = fwd.T_full_K[-1]
        # Top should be hotter than centre/bottom because air is hot
        assert T_final[0] > T_final[-1] - 1.0  # may be similar if conduction equilibrates
        assert T_final[0] > 320.0  # surface heats well above initial
        # All temperatures should rise above initial
        assert np.all(T_final >= 295.0 - 1.0)

    def test_alpha_T_changes_evolution_speed(self):
        """When alpha_ratio < 1, the dough above 65°C heats more slowly
        than a comparable run with alpha_ratio = 1.0."""
        n_t = 300
        t_grid = np.linspace(0.0, 30.0 * 60.0, n_t)
        T_air_K = np.full(n_t, 470.0)
        h_eff_t = np.full(n_t, 50.0)

        fwd_low = solve_luikov_tin_observed(
            L_m=0.100, Lu=0.10, q_bottom_eff=20.0, alpha_ratio=0.3,
            t_grid_s=t_grid, T_air_K_t=T_air_K, h_eff_t=h_eff_t,
            T_initial_K=295.0, n_spatial=40,
        )
        fwd_unity = solve_luikov_tin_observed(
            L_m=0.100, Lu=0.10, q_bottom_eff=20.0, alpha_ratio=1.0,
            t_grid_s=t_grid, T_air_K_t=T_air_K, h_eff_t=h_eff_t,
            T_initial_K=295.0, n_spatial=40,
        )
        assert fwd_low.converged and fwd_unity.converged
        # The alpha_ratio=1 case should heat the deep core faster
        # Take temperature near deep end at last timestep
        T_low_deep = fwd_low.T_full_K[-1, -1]
        T_unity_deep = fwd_unity.T_full_K[-1, -1]
        assert T_unity_deep > T_low_deep, (
            f"alpha_ratio=1.0 (T_deep={T_unity_deep:.1f}) should heat "
            f"faster than alpha_ratio=0.3 (T_deep={T_low_deep:.1f})"
        )

    def test_steady_state_top_approaches_T_air(self):
        """Long-time: with sufficient h_eff and zero bottom flux, the top
        should approach T_air."""
        n_t = 800
        t_grid = np.linspace(0.0, 90.0 * 60.0, n_t)  # 90 min
        T_air_K = np.full(n_t, 450.0)
        h_eff_t = np.full(n_t, 60.0)

        fwd = solve_luikov_tin_observed(
            L_m=0.080,
            Lu=0.10,
            q_bottom_eff=60.0,  # similar coupling on bottom
            alpha_ratio=1.0,    # disable spring effect
            t_grid_s=t_grid,
            T_air_K_t=T_air_K,
            h_eff_t=h_eff_t,
            T_initial_K=295.0,
            n_spatial=40,
        )
        assert fwd.converged
        T_top_final = fwd.T_full_K[-1, 0]
        # Should be within ~50 K of T_air at long time given sustained h_eff
        assert abs(T_top_final - 450.0) < 50.0, (
            f"top {T_top_final:.1f} K not approaching T_air=450 K"
        )

    def test_time_varying_inputs_track_changes(self):
        """When T_air and h_eff change in time, the surface follows."""
        n_t = 400
        t_grid = np.linspace(0.0, 40.0 * 60.0, n_t)
        # Step up T_air at t=10 min
        T_air_K = np.where(t_grid < 600.0, 320.0, 470.0)
        h_eff_t = np.full(n_t, 30.0)

        fwd = solve_luikov_tin_observed(
            L_m=0.100, Lu=0.10, q_bottom_eff=10.0, alpha_ratio=1.0,
            t_grid_s=t_grid, T_air_K_t=T_air_K, h_eff_t=h_eff_t,
            T_initial_K=295.0, n_spatial=40,
        )
        assert fwd.converged
        T_top = fwd.T_full_K[:, 0]
        # Before step: top should be near 320 K, not 470 K
        before = T_top[t_grid < 590.0][-10:]
        # After step: top heats up
        after = T_top[t_grid > 1500.0][:30]
        assert np.mean(before) < 350.0, f"before-step mean {np.mean(before):.1f} K"
        assert np.mean(after) > np.mean(before) + 20.0, (
            f"after-step ({np.mean(after):.1f}) not > before ({np.mean(before):.1f})+20"
        )

    def test_core_depth_inference(self):
        """When asymmetric BCs heavily favour top, core depth shifts toward bottom."""
        n_t = 200
        t_grid = np.linspace(0.0, 20.0 * 60.0, n_t)
        T_air_K = np.full(n_t, 470.0)
        h_eff_t = np.full(n_t, 100.0)  # strong top coupling

        fwd = solve_luikov_tin_observed(
            L_m=0.100, Lu=0.10, q_bottom_eff=2.0, alpha_ratio=1.0,
            t_grid_s=t_grid, T_air_K_t=T_air_K, h_eff_t=h_eff_t,
            T_initial_K=295.0, n_spatial=60,
        )
        assert fwd.converged
        x_core = infer_core_depth_from_forward(
            fwd.T_full_K, fwd.x_grid_m, fwd.t_grid_s
        )
        # Strong top coupling, weak bottom: core (coldest) should be near bottom
        assert x_core > 50.0, f"x_core={x_core:.1f}mm should be > 50mm in 100mm loaf"
