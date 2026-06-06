"""Tests for the isothermal-tracking temporal wrapper (M24 HMS Foxhound).

The isothermal tracker differs from the per-snapshot classifier wrapper
(M23 HMS Drake): instead of re-running the snapshot classifier per stride
(which produces walking-core artefacts because the classifier was designed
for full-bake spatial profiles), it interpolates sensor temperatures at
each timestep to find where T(x) crosses target values (60, 80, 100, 110 C),
and traces those positions over time. The core/surface position is computed
ONCE from the full bake.

Test classes:

* ``TestIsothermalSynthetic`` — fast synthetic-DataFrame tests for the
  basic algorithm: stationary temperature profile -> stationary isotherm
  position; advancing front -> monotone-decreasing isotherm position.
* ``TestIsothermalBA3C0946`` — empirical tests on the canonical single-bake
  CSV. These run the real classifier and tracker so they are slower
  (~20-60 s total wall time when both are run).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.isothermal import (  # noqa: E402
    IsothermalAssignment,
    track_isothermal,
    _find_isotherm_position,
)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BA3C_0946_CSV = os.path.join(
    REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
)


# ---------------------------------------------------------------------------
# Synthetic DataFrame builder
# ---------------------------------------------------------------------------


def _make_static_profile_df(
    n_samples: int = 200,
    period_s: float = 5.0,
    temps: tuple = (40.0, 55.0, 70.0, 85.0, 100.0, 115.0, 130.0, 145.0),
) -> pd.DataFrame:
    """A bake where each sensor sits at a constant temperature for all time.

    Used to verify that isotherm position is constant when the spatial
    profile is stationary.
    """
    ts = np.arange(n_samples, dtype=float) * period_s
    cols = {"Timestamp": ts}
    for i, T in enumerate(temps, start=1):
        cols[f"T{i}"] = np.full(n_samples, T, dtype=float)
    return pd.DataFrame(cols)


def _make_advancing_front_df(
    n_samples: int = 360, period_s: float = 5.0
) -> pd.DataFrame:
    """A synthetic bake where temperature rises everywhere, with the surface
    end (high-x sensors) heating first; the 100 C isotherm starts near
    x=1 (surface) and advances inward toward x=0 (core) over time.
    """
    rng = np.random.default_rng(42)
    ts = np.arange(n_samples, dtype=float) * period_s

    def _profile(t_lag: float, t_final: float, plateau_T: float | None = None):
        x = (ts - t_lag) / 200.0
        rise = 22.0 + (t_final - 22.0) / (1.0 + np.exp(-x))
        if plateau_T is not None:
            rise = np.minimum(rise, plateau_T)
        return rise + rng.normal(0.0, 0.1, size=n_samples)

    df = pd.DataFrame({
        "Timestamp": ts,
        "T1": _profile(t_lag=900.0, t_final=98.0, plateau_T=99.0),
        "T2": _profile(t_lag=820.0, t_final=98.5, plateau_T=99.0),
        "T3": _profile(t_lag=740.0, t_final=99.0, plateau_T=99.0),
        "T4": _profile(t_lag=660.0, t_final=99.5, plateau_T=99.0),
        "T5": _profile(t_lag=500.0, t_final=140.0),
        "T6": _profile(t_lag=400.0, t_final=160.0),
        "T7": _profile(t_lag=300.0, t_final=175.0),
        "T8": _profile(t_lag=200.0, t_final=185.0),
    })
    return df


# ---------------------------------------------------------------------------
# Unit tests for _find_isotherm_position helper
# ---------------------------------------------------------------------------


class TestFindIsothermPositionUnit:

    def test_target_below_all_returns_nan(self):
        positions = np.array([0.0, 1 / 7, 2 / 7, 3 / 7, 4 / 7, 5 / 7, 6 / 7, 1.0])
        temps = np.array([30.0, 32.0, 35.0, 38.0, 42.0, 47.0, 53.0, 60.0])
        # 100 C is above max of 60 C (front not yet in dough)
        result = _find_isotherm_position(positions, temps, 100.0)
        assert np.isnan(result)

    def test_target_above_all_returns_nan(self):
        # fix/deep-review #4: re-derived from the corrected behaviour. The old
        # implementation snapped to 0.0 whenever min(temps) > target ("front
        # passed the probe tip"). That snap MIS-LOCATES the front on inverted /
        # non-monotonic profiles (Wonder full-crumb) — it reports a front at the
        # probe tip that is not actually sampled by any sensor. The corrected
        # rule scans every adjacent pair for a bracket and returns NaN when the
        # target is genuinely not bracketed by any pair (no sensor reports it),
        # rather than fabricating a position at x=0. Here every sensor is above
        # 100 C, so 100 C is not bracketed -> NaN.
        positions = np.array([0.0, 1 / 7, 2 / 7, 3 / 7, 4 / 7, 5 / 7, 6 / 7, 1.0])
        temps = np.array([105.0, 110.0, 115.0, 120.0, 125.0, 130.0, 140.0, 150.0])
        result = _find_isotherm_position(positions, temps, 100.0)
        assert np.isnan(result)

    def test_target_in_middle_linear_interp(self):
        positions = np.array([0.0, 1 / 7, 2 / 7, 3 / 7, 4 / 7, 5 / 7, 6 / 7, 1.0])
        # T8=150 (surface) ... T1=20 (core). Monotone decreasing toward core.
        # Walking from surface to core: T8=150, T7=130, T6=110, T5=90, T4=70 ...
        # 100 C lies between T5=90 (x=4/7) and T6=110 (x=5/7).
        temps = np.array([20.0, 35.0, 50.0, 70.0, 90.0, 110.0, 130.0, 150.0])
        result = _find_isotherm_position(positions, temps, 100.0)
        # Between T5 (x=4/7=0.5714) and T6 (x=5/7=0.7143)
        # Linear: from T6=110 toward T5=90, target=100 is halfway.
        # Position should be (5/7 + 4/7) / 2 = 4.5/7 = 0.6429
        expected = 4.5 / 7.0
        assert abs(result - expected) < 1e-6


# ---------------------------------------------------------------------------
# Synthetic tests
# ---------------------------------------------------------------------------


class TestStrideGridCoverage:
    """fix/deep-review #5 — the stride grid must cover the first and last
    samples of the bake (the old grid started at ``stride_seconds`` and stopped
    at ``bake_duration_s``, omitting the t=0 row and clipping the final row).
    """

    def test_grid_starts_at_zero(self):
        df = _make_static_profile_df(n_samples=240, period_s=5.0)
        result = track_isothermal(
            df,
            sample_period_ms=5000,
            isotherms_C=(100.0,),
            stride_seconds=30.0,
        )
        # The first stride centre must be t=0 (covering the opening row).
        assert result.t_grid_s.size > 0
        assert result.t_grid_s[0] == 0.0

    def test_grid_covers_final_row(self):
        # bake_duration_s = (240-1)*5 = 1195 s. With stride 30 the OLD grid
        # ran 30..1190 (np.arange stops before 1195+eps at 1200), so the final
        # row at 1195 was uncovered. The fix must include a stride at/after the
        # last sample time.
        n = 240
        period_s = 5.0
        df = _make_static_profile_df(n_samples=n, period_s=period_s)
        result = track_isothermal(
            df,
            sample_period_ms=5000,
            isotherms_C=(100.0,),
            stride_seconds=30.0,
        )
        bake_duration_s = (n - 1) * period_s
        # The last stride centre must reach the final sample time (within one
        # stride of the end is not enough — it must cover the last row).
        assert result.t_grid_s[-1] >= bake_duration_s - 1e-6


class TestIsothermalSynthetic:

    def test_static_profile_returns_constant_position(self):
        """Sensors at fixed temperatures monotone in x; target temperature
        in middle; isotherm position should be the same at every timestep.
        """
        # T1=40, T2=55, T3=70, T4=85, T5=100, T6=115, T7=130, T8=145.
        # Target 100 C lies exactly at T5 (x = 4/7 ~ 0.5714).
        df = _make_static_profile_df(n_samples=240, period_s=5.0)
        result = track_isothermal(
            df,
            sample_period_ms=5000,
            isotherms_C=(70.0, 100.0, 130.0),
            stride_seconds=30.0,
            smoothing_window_seconds=120.0,
            smoothing_polyorder=2,
        )
        assert isinstance(result, IsothermalAssignment)
        n_grid = result.t_grid_s.size
        assert n_grid > 0

        # Each isotherm position should be a (near-)constant array.
        for T_target, expected_x in [
            (70.0, 2 / 7),
            (100.0, 4 / 7),
            (130.0, 6 / 7),
        ]:
            arr = result.isotherm_positions_raw[T_target]
            assert arr.size == n_grid
            finite = arr[np.isfinite(arr)]
            assert finite.size >= 5, (
                f"Static profile did not yield finite isotherm "
                f"positions for T={T_target}"
            )
            # All should be exactly the expected x (synthetic, no noise).
            assert np.allclose(finite, expected_x, atol=1e-6), (
                f"Static profile T={T_target}: got {finite[:3]}, "
                f"expected {expected_x}"
            )

    def test_advancing_front_decreases_position(self):
        """Synthetic bake: front advances from x=1 to x=0 over time.
        100 C isotherm position should monotone-decrease from late-bake
        start to end (compare first-quartile mean vs last-quartile mean).
        """
        df = _make_advancing_front_df(n_samples=360, period_s=5.0)
        result = track_isothermal(
            df,
            sample_period_ms=5000,
            isotherms_C=(60.0, 80.0, 100.0, 110.0),
            stride_seconds=30.0,
            smoothing_window_seconds=120.0,
            smoothing_polyorder=2,
        )
        front_100 = result.isotherm_positions[100.0]
        valid_mask = np.isfinite(front_100)
        if valid_mask.sum() < 5:
            pytest.skip("not enough 100 C front samples in synthetic")
        valid = front_100[valid_mask]
        # First quartile mean vs last quartile mean — must show inward drift.
        n = valid.size
        q1 = float(np.mean(valid[: max(1, n // 4)]))
        q4 = float(np.mean(valid[-max(1, n // 4):]))
        assert q4 < q1, (
            f"Advancing front did NOT trend inward: "
            f"q1={q1:.3f} q4={q4:.3f}"
        )


# ---------------------------------------------------------------------------
# BA3C_0946 empirical tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ba3c_0946_isothermal():
    """Run track_isothermal on BA3C_0946 once per module."""
    pytest.importorskip("scipy")
    if not os.path.exists(_BA3C_0946_CSV):
        pytest.skip(f"fixture missing: {_BA3C_0946_CSV}")
    from src.data.loader import ThermalProfileLoader

    loader = ThermalProfileLoader()
    loader.load_csv(file_path=_BA3C_0946_CSV)
    assert loader.all_curves, "BA3C_0946 must yield at least one curve"
    df_curve = loader.all_curves[0]["data"]
    sample_period_ms = int(loader.metadata.get("sample_period_ms", 5000))

    result = track_isothermal(
        df_curve,
        sample_period_ms=sample_period_ms,
        isotherms_C=(60.0, 80.0, 100.0, 110.0),
        stride_seconds=30.0,
        smoothing_window_seconds=120.0,
        smoothing_polyorder=2,
    )
    return result, df_curve, sample_period_ms


class TestIsothermalBA3C0946:

    def test_real_csv_smoke(self, ba3c_0946_isothermal):
        """Loading BA3C_0946 and running track_isothermal returns a
        well-formed IsothermalAssignment.
        """
        result, df, _ = ba3c_0946_isothermal
        assert isinstance(result, IsothermalAssignment)
        assert result.t_grid_s.size >= 5
        assert result.isotherm_temps_C == (60.0, 80.0, 100.0, 110.0)
        # Positions dict has every requested isotherm.
        for T in result.isotherm_temps_C:
            assert T in result.isotherm_positions
            assert T in result.isotherm_positions_raw
            assert result.isotherm_positions[T].size == result.t_grid_s.size
        # Fixed core/surface are scalar floats.
        assert isinstance(result.fixed_core_x, float)
        assert isinstance(result.fixed_surface_x, float)
        assert 0.0 <= result.fixed_core_x <= 1.0
        # T_at_fixed_core must be finite for late-bake (last-half) strides.
        assert result.T_at_fixed_core_t.size == result.t_grid_s.size
        late_T_core = result.T_at_fixed_core_t[result.t_grid_s.size // 2:]
        late_finite = np.isfinite(late_T_core)
        assert late_finite.mean() > 0.9

    def test_isotherm_ordering(self, ba3c_0946_isothermal):
        """During the active baking phase, isotherm ordering should hold:
        x_110C >= x_100C >= x_80C >= x_60C  (110 C nearest surface, 60 C
        deepest into the dough).

        fix/deep-review #4: scan the WHOLE bake for strides where all four
        isotherms are simultaneously finite, rather than the last quarter. The
        corrected front detector no longer snaps under-target fronts to x=0.0,
        so by the late bake the 60/80 C fronts have correctly advanced PAST the
        probe tip (NaN), and the four-way coexistence window is the mid-bake
        active phase (BA3C strides ~6-33), not the tail.
        """
        result, _, _ = ba3c_0946_isothermal
        x60 = result.isotherm_positions[60.0]
        x80 = result.isotherm_positions[80.0]
        x100 = result.isotherm_positions[100.0]
        x110 = result.isotherm_positions[110.0]
        # Find strides where ALL FOUR are finite simultaneously.
        all_finite = (
            np.isfinite(x60) & np.isfinite(x80)
            & np.isfinite(x100) & np.isfinite(x110)
        )
        assert all_finite.sum() >= 10, (
            "expected a substantial mid-bake window where all four isotherms "
            f"coexist; got {int(all_finite.sum())} strides"
        )
        # For each such stride, x110 >= x100 >= x80 >= x60 must hold.
        # Allow a small tolerance for numerical equality at the probe tip.
        tol = 1e-6
        for k in np.flatnonzero(all_finite):
            assert x110[k] >= x100[k] - tol, (
                f"Stride {k}: x110={x110[k]:.4f} < x100={x100[k]:.4f}"
            )
            assert x100[k] >= x80[k] - tol, (
                f"Stride {k}: x100={x100[k]:.4f} < x80={x80[k]:.4f}"
            )
            assert x80[k] >= x60[k] - tol, (
                f"Stride {k}: x80={x80[k]:.4f} < x60={x60[k]:.4f}"
            )

    def test_100C_front_monotone_inward(self, ba3c_0946_isothermal):
        """Once x_100C is non-NaN, it should monotone-decrease overall
        (advance inward toward T1 = lower x). Allow small backsteps
        from noise; check overall trend (first-half vs second-half mean).
        """
        result, _, _ = ba3c_0946_isothermal
        front = result.isotherm_positions[100.0]
        valid_mask = np.isfinite(front)
        if valid_mask.sum() < 5:
            pytest.skip("not enough 100 C front samples in BA3C_0946")
        valid_front = front[valid_mask]
        n = valid_front.size
        # Compare first-fifth-mean vs last-fifth-mean.
        head = float(np.mean(valid_front[: max(1, n // 5)]))
        tail = float(np.mean(valid_front[-max(1, n // 5):]))
        assert tail <= head + 0.05, (
            f"100 C front did NOT trend inward in BA3C_0946: "
            f"head={head:.3f} tail={tail:.3f}"
        )

    def test_fixed_core_does_not_walk(self, ba3c_0946_isothermal):
        """Core position is computed ONCE from the full bake. It is
        a single scalar — there is no time-varying core array to walk.
        """
        result, _, _ = ba3c_0946_isothermal
        # Hard contract: fixed_core_x is a Python float, not an array.
        assert isinstance(result.fixed_core_x, float)
        assert isinstance(result.fixed_surface_x, float)
        # Core should be at low-x end (T1 side) for BA3C_0946 (which is a
        # canonical single-side insertion bake).
        assert result.fixed_core_x < result.fixed_surface_x, (
            f"core_x={result.fixed_core_x} should be < "
            f"surface_x={result.fixed_surface_x}"
        )
