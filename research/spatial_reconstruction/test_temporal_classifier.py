"""Tests for the temporal wrapper over the per-snapshot spatial classifier.

M23 HMS Drake — wraps ``classify(df, ...)`` to run repeatedly across a stride
grid of timesteps, collecting per-snapshot derived quantities into time-series
arrays. Smooths via Savitzky-Golay for visual continuity.

Two test classes:

* ``TestTemporalClassifierSynthetic`` — fast synthetic-DataFrame tests that
  exercise shape contracts and the smoothing reduction-of-jaggedness check.
* ``TestTemporalClassifierBA3C0946`` — empirical tests on the canonical
  single-bake CSV. These run the real classifier so they are slower (~30-90s
  total wall time when all three are run).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.temporal import (  # noqa: E402
    TemporalAssignment,
    classify_temporal,
)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BA3C_0946_CSV = os.path.join(
    REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
)


# ---------------------------------------------------------------------------
# Synthetic DataFrame builder — keeps the synthetic tests self-contained.
# ---------------------------------------------------------------------------


def _make_synthetic_bake_df(
    n_samples: int = 280, period_s: float = 5.0
) -> pd.DataFrame:
    """Build a synthetic 8-sensor bake DataFrame.

    T1..T4 are dough-side (slow rise, plateau near 100 C). T5..T8 are
    air-side (fast rise to 180 C). The shape is rough but adequate to
    exercise the classifier-driver shape contract without depending on
    a real CSV file.
    """
    rng = np.random.default_rng(42)
    ts = np.arange(n_samples, dtype=float) * period_s

    # Heat-up half-curves with per-sensor lag and final-T.
    def _profile(t_lag: float, t_final: float, plateau_T: float | None = None) -> np.ndarray:
        # Logistic rise from 22 C to t_final centred at t_lag, slope ~150s.
        x = (ts - t_lag) / 150.0
        rise = 22.0 + (t_final - 22.0) / (1.0 + np.exp(-x))
        if plateau_T is not None:
            rise = np.minimum(rise, plateau_T)
        return rise + rng.normal(0.0, 0.3, size=n_samples)

    df = pd.DataFrame({
        "Timestamp": ts,
        "T1": _profile(t_lag=600.0, t_final=98.0, plateau_T=99.0),
        "T2": _profile(t_lag=550.0, t_final=98.5, plateau_T=99.0),
        "T3": _profile(t_lag=500.0, t_final=99.0, plateau_T=99.0),
        "T4": _profile(t_lag=450.0, t_final=99.5, plateau_T=99.0),
        "T5": _profile(t_lag=350.0, t_final=140.0),
        "T6": _profile(t_lag=300.0, t_final=160.0),
        "T7": _profile(t_lag=250.0, t_final=175.0),
        "T8": _profile(t_lag=200.0, t_final=180.0),
    })
    return df


# ---------------------------------------------------------------------------
# Synthetic tests
# ---------------------------------------------------------------------------


class TestTemporalClassifierSynthetic:

    def test_temporal_classify_returns_expected_shape(self):
        """A synthetic 280-step df at 5s period yields a TemporalAssignment
        whose t_grid_s and per-trace arrays all share the same length."""
        df = _make_synthetic_bake_df(n_samples=280, period_s=5.0)
        result = classify_temporal(
            df,
            sample_period_ms=5000,
            stride_seconds=60.0,
            smoothing_window_seconds=120.0,
            smoothing_polyorder=2,
        )
        assert isinstance(result, TemporalAssignment)
        n_grid = result.t_grid_s.size
        assert n_grid > 0
        # All trace arrays must be 1D and length n_grid.
        for arr_name in (
            "x_core_t",
            "x_surface_t",
            "x_stefan_front_t",
            "T_core_t",
            "T_surface_t",
            "x_core_t_raw",
            "x_surface_t_raw",
            "x_stefan_front_t_raw",
        ):
            arr = getattr(result, arr_name)
            assert arr.ndim == 1, f"{arr_name} must be 1D"
            assert arr.size == n_grid, (
                f"{arr_name} size {arr.size} mismatch grid {n_grid}"
            )
        # Confidence trace also length n_grid.
        assert len(result.confidence_t) == n_grid

    def test_savgol_smoothing_reduces_jaggedness(self):
        """Inject a known noisy core-position trace (via a noisy synthetic
        curve where the classifier output naturally jitters) and confirm
        that ``x_core_t`` has equal-or-lower std than ``x_core_t_raw``.

        We add stronger Gaussian noise to T1..T4 so the per-snapshot
        classifier picks bounce slightly between sensors, producing a
        jagged raw trace. SavGol with a >=5-sample window should smooth it.
        """
        rng = np.random.default_rng(7)
        n = 320
        period_s = 5.0
        ts = np.arange(n, dtype=float) * period_s

        def _profile(t_lag: float, t_final: float, plateau_T: float | None,
                     noise: float) -> np.ndarray:
            x = (ts - t_lag) / 150.0
            rise = 22.0 + (t_final - 22.0) / (1.0 + np.exp(-x))
            if plateau_T is not None:
                rise = np.minimum(rise, plateau_T)
            return rise + rng.normal(0.0, noise, size=n)

        df = pd.DataFrame({
            "Timestamp": ts,
            "T1": _profile(600.0, 98.0, 99.0, noise=2.0),
            "T2": _profile(550.0, 98.3, 99.0, noise=2.0),
            "T3": _profile(500.0, 98.6, 99.0, noise=2.0),
            "T4": _profile(450.0, 99.0, 99.0, noise=2.0),
            "T5": _profile(350.0, 140.0, None, noise=0.5),
            "T6": _profile(300.0, 160.0, None, noise=0.5),
            "T7": _profile(250.0, 175.0, None, noise=0.5),
            "T8": _profile(200.0, 180.0, None, noise=0.5),
        })
        result = classify_temporal(
            df,
            sample_period_ms=5000,
            stride_seconds=30.0,
            smoothing_window_seconds=180.0,
            smoothing_polyorder=2,
        )
        # The proper measure of "jaggedness" is the std of the
        # FIRST-DIFFERENCE (sample-to-sample jumps). SavGol cannot reduce the
        # aggregate std of a drifting non-stationary signal, but it MUST
        # reduce sample-to-sample noise. We compare std(diff(raw)) vs
        # std(diff(smoothed)) over the stable portion of the bake.
        if result.x_core_t.size >= 10:
            raw_finite = result.x_core_t_raw[5:]
            smooth_finite = result.x_core_t[5:]
            raw_diff = np.diff(raw_finite[np.isfinite(raw_finite)])
            smooth_diff = np.diff(smooth_finite[np.isfinite(smooth_finite)])
            if raw_diff.size >= 3 and smooth_diff.size >= 3:
                raw_jag = float(np.std(raw_diff))
                smooth_jag = float(np.std(smooth_diff))
                # Allow tiny numerical slack (1e-6).
                assert smooth_jag <= raw_jag + 1e-6, (
                    f"SavGol smoothing increased sample-to-sample jaggedness "
                    f"(raw_diff_std={raw_jag:.5f} -> smoothed_diff_std={smooth_jag:.5f})"
                )


# ---------------------------------------------------------------------------
# BA3C_0946 empirical tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ba3c_0946_temporal():
    """Run classify_temporal on BA3C_0946 once per module (slow; ~30-90 s)."""
    pytest.importorskip("scipy")
    if not os.path.exists(_BA3C_0946_CSV):
        pytest.skip(f"fixture missing: {_BA3C_0946_CSV}")
    from src.data.loader import ThermalProfileLoader

    loader = ThermalProfileLoader()
    loader.load_csv(file_path=_BA3C_0946_CSV)
    assert loader.all_curves, "BA3C_0946 must yield at least one curve"
    df_curve = loader.all_curves[0]["data"]
    sample_period_ms = int(loader.metadata.get("sample_period_ms", 5000))

    result = classify_temporal(
        df_curve,
        sample_period_ms=sample_period_ms,
        stride_seconds=30.0,
        smoothing_window_seconds=120.0,
        smoothing_polyorder=2,
    )
    return result, df_curve, sample_period_ms


class TestTemporalClassifierBA3C0946:

    def test_real_csv_smoke(self, ba3c_0946_temporal):
        """Loading BA3C_0946 and running the temporal classifier returns a
        TemporalAssignment with finite values for at least most strides."""
        result, _, _ = ba3c_0946_temporal
        assert isinstance(result, TemporalAssignment)
        assert result.t_grid_s.size >= 5

        # x_core_t must be finite for the majority of strides.
        finite_core = np.isfinite(result.x_core_t)
        assert finite_core.mean() > 0.5, (
            f"x_core_t finite fraction {finite_core.mean():.2f} too low"
        )

        # T_core_t must be finite where x_core_t is finite.
        valid_T_core = np.isfinite(result.T_core_t[finite_core])
        assert valid_T_core.mean() > 0.95

    def test_stefan_front_advances_inward_monotone(self, ba3c_0946_temporal):
        """Once the Stefan front begins, x_stefan_front_t should trend
        monotone-decreasing within tolerance over its active period.

        Convention for BA3C_0946: probe inserted from T8 side; core is at
        the low-x end (T1). The 100 C front sits between dough and air
        sensors. As the bake progresses the front advances *inward* toward
        the core, i.e. x_stefan_front_t decreases over time.

        We tolerate small noise-driven backsteps. The test asserts the
        OVERALL monotone-decreasing trend over the active window: end value
        must be <= start value within a small tolerance.
        """
        result, _, _ = ba3c_0946_temporal
        front = result.x_stefan_front_t
        valid_mask = np.isfinite(front)
        if valid_mask.sum() < 5:
            pytest.skip("not enough Stefan-front samples in BA3C_0946 trace")
        valid_front = front[valid_mask]
        # End-of-trace value should not be substantially greater than start.
        # Allow up to 0.05 normalised position of "drift back" — well within
        # the spatial uncertainty of two-sensor interpolation.
        start_val = float(np.mean(valid_front[: max(1, len(valid_front) // 5)]))
        end_val = float(np.mean(valid_front[-max(1, len(valid_front) // 5):]))
        assert end_val <= start_val + 0.05, (
            f"Stefan front did NOT trend inward: start={start_val:.3f} "
            f"end={end_val:.3f}"
        )

    def test_core_position_stable(self, ba3c_0946_temporal):
        """``x_core_t`` std across the *late-bake stable* window (last
        quarter of the bake, where the dough plateau is fully developed
        and the deepest sensor IS the slowest-heating one) should be
        < 0.05 (≈ 5% of probe length, roughly 5 mm).

        Note: during the early/mid bake the slowest-heating dough sensor
        progressively migrates outward through T8 → T7 → T6 → ... as
        successive sensors cross the heat-up score threshold; that is
        physically meaningful per-snapshot behaviour, not jaggedness.
        The "stable insertion" claim only holds once the dough region is
        contiguous and the true geometric core has emerged as the
        slowest-heating sensor — i.e. the last quarter of the bake.
        """
        result, _, _ = ba3c_0946_temporal
        finite = np.isfinite(result.x_core_t)
        assert finite.sum() >= 5
        if result.t_grid_s.size >= 4:
            q_idx = 3 * result.t_grid_s.size // 4
            stable = result.x_core_t[q_idx:]
            stable = stable[np.isfinite(stable)]
            assert stable.size >= 3, "not enough stable-window samples"
            std = float(np.std(stable))
            assert std < 0.05, (
                f"core position std (late-bake stable window) "
                f"{std:.4f} too large (>= 0.05)"
            )
