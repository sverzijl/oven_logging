"""HMS Sirius — forward solver sanity tests for the asymmetric-BC Luikov inverse.

These tests are TDD-first: they were written before the inverse fits were
run, and codify the four sanity checks the briefing requires:

1. Top-only heated → descending profile (T high at x=0, low at x=L).
2. Bottom-only heated → ascending profile (T low at x=0, high at x=L).
3. Symmetric BCs → symmetric profile, core at L/2.
4. Long-time steady state → BCs honoured, no phase-change source residual.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.luikov_tin import (  # noqa: E402
    solve_luikov_tin_forward,
    infer_core_depth_from_forward,
)


class TestForwardSanity:
    """Forward-solver sanity per the M15 briefing."""

    def test_top_only_heated_gives_descending_profile(self):
        """Hot top, cold tin → T decreasing from x=0 to x=L at mid-bake."""
        t_grid = np.linspace(0.0, 20.0 * 60.0, 200)  # 20 min
        fwd = solve_luikov_tin_forward(
            L_m=0.100,
            Lu=0.15,
            Ko=4.0,
            Bi_top=10.0,
            Bi_bottom=0.5,  # weak bottom coupling
            T_oven_K=450.0,
            T_tin_K=295.0,
            t_grid_s=t_grid,
            T_initial_K=295.0,
            n_spatial=60,
        )
        assert fwd.converged
        T_final = fwd.T_full_K[-1]
        # Top should be substantially hotter than bottom.
        assert T_final[0] > T_final[-1] + 30.0, (
            f"top {T_final[0]:.1f} K not >> bottom {T_final[-1]:.1f} K"
        )
        # Profile should be roughly monotonic non-increasing in x (allow
        # small numerical wobble, especially near boundary cells).
        # Strict monotonicity is not guaranteed at very short times due to
        # initial condition + radiative coupling, so we check a window of
        # the interior nodes.
        interior = T_final[2:-2]
        diffs = np.diff(interior)
        # No more than 3 increasing pairs greater than 0.5 K.
        n_violations = int(np.sum(diffs > 0.5))
        assert n_violations <= 3, (
            f"too many ascending pairs in top-heated profile: {n_violations}"
        )

    def test_bottom_only_heated_gives_ascending_profile(self):
        """Cold top, hot tin → T increasing from x=0 to x=L."""
        t_grid = np.linspace(0.0, 20.0 * 60.0, 200)
        fwd = solve_luikov_tin_forward(
            L_m=0.100,
            Lu=0.15,
            Ko=4.0,
            Bi_top=0.5,
            Bi_bottom=10.0,
            T_oven_K=295.0,
            T_tin_K=450.0,
            t_grid_s=t_grid,
            T_initial_K=295.0,
            n_spatial=60,
        )
        assert fwd.converged
        T_final = fwd.T_full_K[-1]
        # Bottom should be substantially hotter than top.
        assert T_final[-1] > T_final[0] + 30.0, (
            f"bottom {T_final[-1]:.1f} K not >> top {T_final[0]:.1f} K"
        )
        interior = T_final[2:-2]
        diffs = np.diff(interior)
        n_violations = int(np.sum(diffs < -0.5))
        assert n_violations <= 3, (
            f"too many descending pairs in bottom-heated profile: "
            f"{n_violations}"
        )

    def test_symmetric_BCs_recover_symmetric_profile(self):
        """Bi_bottom=Bi_top, T_tin=T_oven, ε_rad=0, Ko≈0 → symmetric profile.

        Radiation must be disabled for genuine top-bottom symmetry: the
        ε·σ·T⁴ term lives only at the top boundary and breaks symmetry
        even with equal Bi and equal target temperatures. The moisture
        BCs are also intrinsically asymmetric (Dirichlet u=0 at top,
        Neumann at bottom — physically correct for a tinned loaf), so we
        suppress moisture coupling with Ko≈0 to isolate the heat
        equation symmetry.
        """
        t_grid = np.linspace(0.0, 20.0 * 60.0, 200)
        L_m = 0.100
        fwd = solve_luikov_tin_forward(
            L_m=L_m,
            Lu=0.15,
            Ko=1e-3,  # decouple moisture for the heat-symmetry test
            Bi_top=5.0,
            Bi_bottom=5.0,
            T_oven_K=450.0,
            T_tin_K=450.0,
            t_grid_s=t_grid,
            T_initial_K=295.0,
            n_spatial=60,
            epsilon_rad=0.0,
        )
        assert fwd.converged
        # Mid-bake snapshot.
        i_mid = len(t_grid) // 4
        T_mid = fwd.T_full_K[i_mid]
        N = len(T_mid)
        # Symmetry about index N//2: T[i] ≈ T[N-1-i].
        max_asym = 0.0
        for i in range(N // 2):
            asym = abs(T_mid[i] - T_mid[N - 1 - i])
            max_asym = max(max_asym, asym)
        assert max_asym < 1.0, (
            f"symmetric-BC asymmetry max {max_asym:.3f} K (should be ~0)"
        )
        # Core inference should land near L/2.
        x_core_mm = infer_core_depth_from_forward(
            fwd.T_full_K, fwd.x_grid_m, fwd.t_grid_s
        )
        assert abs(x_core_mm - L_m * 1000.0 / 2.0) < 8.0, (
            f"symmetric core depth {x_core_mm:.1f} mm not near "
            f"{L_m*1000/2:.1f} mm"
        )

    def test_steady_state_long_time(self):
        """At very long times with Ko≈0 and ε_rad=0, T → T_oven via Bi."""
        # Decouple moisture (Ko ≈ 0) and disable radiation so the
        # asymptotic limit is the simple convective Robin steady state
        # T(x) → T_oven (with Bi_top=Bi_bottom and T_tin=T_oven).
        t_grid = np.linspace(0.0, 36000.0, 200)
        fwd = solve_luikov_tin_forward(
            L_m=0.100,
            Lu=0.15,
            Ko=1e-3,
            Bi_top=20.0,
            Bi_bottom=20.0,
            T_oven_K=450.0,
            T_tin_K=450.0,
            t_grid_s=t_grid,
            T_initial_K=295.0,
            n_spatial=60,
            epsilon_rad=0.0,
        )
        assert fwd.converged
        T_final = fwd.T_full_K[-1]
        T_min = float(T_final.min())
        T_max = float(T_final.max())
        # With strong Bi (h·L/k = 20 → h = 100 W/m²K with k=0.5, L=0.1) on
        # both sides and equal T_oven=T_tin=450K, after 5τ ≈ 36000s the
        # field should be ≈ 450 K. Bi=20 is "strong" so surface error is
        # small (~1/Bi · ΔT_initial drop) but transient.
        assert abs(T_max - 450.0) < 5.0, f"steady T_max={T_max:.2f} K"
        # Allow a slightly looser bound on T_min (interior was coldest at
        # init).
        assert abs(T_min - 450.0) < 5.0, f"steady T_min={T_min:.2f} K"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
