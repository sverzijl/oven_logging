"""Unit tests for the sigmoid refinement module.

Introduced by flotilla mission M2 HMS Resolution (branch
``refactor/expected-bake-time``).  Tests the pure 4-parameter logistic
fit and the two candidate-scoring helpers that M3 Agincourt (end) and
M4 Hood (start) will consume.

Red-cell empirical verification (project memory feedback
``feedback_redcell_empirical_verification``): at least one test must
run the code under noise perturbation at σ ∈ {0.15, 0.5, 1.0} °C —
``test_red_cell_t0_variance_low_at_sigma_015`` covers this.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.sigmoid_refinement import (
    LogisticFit,
    fit_logistic,
    score_end_candidate,
    score_start_candidate,
)

# Baseline config matching the M2 additions to CURVE_DETECTION_CONFIG.
# Tests use this dict rather than importing the real config so that
# thresholds can be tightened per-test without monkeypatching config.
_BASE_CONFIG = {
    "SIGMOID_FIT_MIN_R2": 0.85,
    "SIGMOID_FIT_MIN_SAMPLES": 30,
    "SIGMOID_FIT_COMPOSITE_WEIGHT_R2": 0.6,
    "SIGMOID_FIT_COMPOSITE_WEIGHT_PROXIMITY": 0.4,
    "EXPECTED_DURATION_TOLERANCE_FRAC": 0.15,
    "EXPECTED_DURATION_MIN_TOLERANCE_SECONDS": 60.0,
}


# ---------------------------------------------------------------------------
# Synthetic sigmoid builders
# ---------------------------------------------------------------------------

def _logistic_truth(t: np.ndarray, L: float, U: float, k: float, t0: float) -> np.ndarray:
    """Ground-truth 4-parameter logistic — test-side reference."""
    return L + (U - L) / (1.0 + np.exp(-k * (t - t0)))


def _sigmoid_bake(
    n_samples: int = 120,
    period_s: float = 5.0,
    L: float = 22.0,
    U: float = 97.0,
    k: float = 0.006,
    t0_s: float = 300.0,
    sigma: float = 0.0,
    seed: int | None = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (timestamps, temperatures) for a noisy S-curve bake.

    Default parameters approximate a 10-minute bake rising from 22 °C to
    ~97 °C with inflection at 5 min — representative of the real fixtures.
    """
    t = np.arange(n_samples, dtype=float) * period_s
    T_clean = _logistic_truth(t, L, U, k, t0_s)
    if sigma > 0:
        rng = np.random.default_rng(seed)
        T = T_clean + rng.normal(0.0, sigma, size=T_clean.shape)
    else:
        T = T_clean
    return t, T


# ---------------------------------------------------------------------------
# Tests: fit_logistic
# ---------------------------------------------------------------------------

class TestFitLogistic:
    """Core numerical primitive — 4-parameter logistic fit."""

    def test_clean_sigmoid_recovers_parameters_with_r2_above_0999(self):
        """At σ=0, fit must recover L, U, k, t0 and hit R² ≥ 0.999."""
        t, T = _sigmoid_bake(sigma=0.0)
        fit = fit_logistic(t, T)
        assert fit.converged, "clean sigmoid should converge"
        assert fit.r2 >= 0.999, f"clean sigmoid R²={fit.r2} below 0.999"
        assert abs(fit.L - 22.0) < 0.5
        assert abs(fit.U - 97.0) < 0.5
        assert abs(fit.t0 - 300.0) < 5.0  # within one sample period

    def test_noisy_sigmoid_sigma_015_converges(self):
        """At σ=0.15 °C (Combustion Inc. spec noise), fit converges and R² ≥ min_r2."""
        t, T = _sigmoid_bake(sigma=0.15, seed=7)
        fit = fit_logistic(t, T)
        assert fit.converged
        assert fit.r2 >= 0.85  # matches SIGMOID_FIT_MIN_R2

    def test_noisy_sigmoid_sigma_1_0_still_converges(self):
        """At σ=1.0 °C (stressful), fit still converges (R² may degrade)."""
        t, T = _sigmoid_bake(sigma=1.0, seed=13)
        fit = fit_logistic(t, T)
        assert fit.converged
        # No R² assertion — 1 °C noise on 75 °C swing may push r² below min_r2;
        # the *gating* is the caller's job (tested in TestScoreEndCandidate).

    def test_flat_data_returns_failed_fit(self):
        """Constant T — degenerate case, must not raise."""
        t = np.arange(60, dtype=float) * 5.0
        T = np.full(60, 25.0)
        fit = fit_logistic(t, T)
        assert not fit.converged
        assert fit.r2 == 0.0

    def test_short_array_returns_failed_fit(self):
        """Arrays shorter than 4 samples cannot be fit."""
        t = np.array([0.0, 5.0, 10.0])
        T = np.array([22.0, 50.0, 90.0])
        fit = fit_logistic(t, T)
        assert not fit.converged

    def test_mismatched_shapes_returns_failed_fit(self):
        """Defensive against caller error."""
        t = np.arange(50, dtype=float)
        T = np.arange(30, dtype=float)
        fit = fit_logistic(t, T)
        assert not fit.converged

    def test_red_cell_t0_variance_low_at_sigma_015(self):
        """RED-CELL PROBE (per project memory): t₀ recovery variance across seeds.

        Empirically verifies the fit is noise-stable at the manufacturer-
        spec σ=0.15 °C.  Across 20 seeds, the t₀ estimate must stay within
        one sample period of ground truth on average, with standard
        deviation ≤ 1 sample period.
        """
        period_s = 5.0
        t0_truth = 300.0
        estimates: list[float] = []
        for seed in range(20):
            t, T = _sigmoid_bake(sigma=0.15, seed=seed)
            fit = fit_logistic(t, T)
            assert fit.converged, f"seed={seed}: fit failed unexpectedly"
            estimates.append(fit.t0)
        arr = np.asarray(estimates)
        assert abs(float(np.mean(arr)) - t0_truth) <= period_s, (
            f"mean t0 estimate {np.mean(arr):.2f} drifted > {period_s}s from truth "
            f"{t0_truth} at σ=0.15"
        )
        assert float(np.std(arr)) <= period_s, (
            f"t0 estimate std {np.std(arr):.2f} exceeds one sample period "
            f"({period_s}s) at σ=0.15 — red-cell fragility threshold breached"
        )


# ---------------------------------------------------------------------------
# Tests: score_end_candidate
# ---------------------------------------------------------------------------

class TestScoreEndCandidate:
    """End-candidate scoring — composite of sigmoid R² + proximity to expected."""

    def test_candidate_at_expected_end_scores_high(self):
        """Clean sigmoid, candidate exactly at expected-duration end → high score."""
        t, T = _sigmoid_bake(n_samples=120, sigma=0.0)
        start_idx = 0
        candidate_idx = 119
        expected_duration_s = float(t[candidate_idx] - t[start_idx])
        score = score_end_candidate(T, t, start_idx, candidate_idx,
                                     expected_duration_s, _BASE_CONFIG)
        # w_r2*r2 + w_prox*prox_full = 0.6*~1 + 0.4*1 = ~1.0
        assert score >= 0.9, f"clean sigmoid at expected end scored {score}"

    def test_candidate_far_beyond_tolerance_band_has_zero_proximity(self):
        """Candidate 2× the expected duration → proximity component drops to 0."""
        t, T = _sigmoid_bake(n_samples=240, sigma=0.0)
        start_idx = 0
        candidate_idx = 200
        actual_duration = float(t[candidate_idx] - t[start_idx])
        # Expected duration is half of actual → actual is 100% over, far outside 15% tol
        expected_duration_s = actual_duration / 2.0
        score = score_end_candidate(T, t, start_idx, candidate_idx,
                                     expected_duration_s, _BASE_CONFIG)
        # Still gets the R² contribution on a clean sigmoid but no proximity
        # → bounded above by w_r2 = 0.6
        assert score <= 0.6 + 1e-6, (
            f"score {score} exceeds w_r2={_BASE_CONFIG['SIGMOID_FIT_COMPOSITE_WEIGHT_R2']}; "
            "proximity should be 0 outside the tolerance band"
        )

    def test_insufficient_samples_returns_zero_without_calling_curve_fit(
        self, monkeypatch
    ):
        """Window shorter than MIN_SAMPLES must short-circuit before curve_fit.

        Protects the hot path from paying solver cost on tiny windows.
        """
        import src.data.sigmoid_refinement as mod

        def _boom(*args, **kwargs):
            raise AssertionError(
                "curve_fit must NOT be called when window < SIGMOID_FIT_MIN_SAMPLES"
            )

        monkeypatch.setattr(mod, "curve_fit", _boom)

        t, T = _sigmoid_bake(n_samples=20, sigma=0.0)  # 20 < min 30
        score = score_end_candidate(T, t, 0, 19, 95.0, _BASE_CONFIG)
        assert score == 0.0

    def test_non_sigmoid_noise_scores_below_min_r2_component(self):
        """Noise-only data → fit.r2 < min_r2 → R² contribution 0; only proximity."""
        rng = np.random.default_rng(42)
        t = np.arange(60, dtype=float) * 5.0
        T = rng.normal(50.0, 0.5, size=60)  # flat noise, no curve
        expected_duration_s = float(t[-1] - t[0])
        score = score_end_candidate(T, t, 0, len(T) - 1, expected_duration_s, _BASE_CONFIG)
        # R² gate eliminates 0.6 contribution; proximity full → bounded by w_prox
        assert score <= _BASE_CONFIG["SIGMOID_FIT_COMPOSITE_WEIGHT_PROXIMITY"] + 1e-6

    def test_score_is_bounded_in_unit_interval(self):
        """Score must lie in [0, 1] for any reasonable input."""
        t, T = _sigmoid_bake(sigma=0.3, seed=99)
        for candidate_idx in (40, 80, 119):
            expected = float(t[candidate_idx] - t[0])
            for expected_mult in (0.5, 1.0, 1.2, 2.0):
                s = score_end_candidate(
                    T, t, 0, candidate_idx, expected * expected_mult, _BASE_CONFIG
                )
                assert 0.0 <= s <= 1.0, f"score {s} outside [0, 1]"

    def test_candidate_before_or_at_start_returns_zero(self):
        """Defensive: candidate_idx <= start_idx is ill-defined."""
        t, T = _sigmoid_bake(sigma=0.0)
        assert score_end_candidate(T, t, 10, 10, 300.0, _BASE_CONFIG) == 0.0
        assert score_end_candidate(T, t, 10, 5, 300.0, _BASE_CONFIG) == 0.0


# ---------------------------------------------------------------------------
# Tests: score_start_candidate
# ---------------------------------------------------------------------------

class TestScoreStartCandidate:
    """Start-candidate scoring — delegates to end-scoring with inferred window."""

    def test_proposed_start_at_true_start_scores_high(self):
        """Clean sigmoid, propose start=0 with correct expected duration."""
        t, T = _sigmoid_bake(n_samples=120, sigma=0.0)
        expected_duration_s = float(t[-1])
        score = score_start_candidate(T, t, 0, expected_duration_s, _BASE_CONFIG)
        assert score >= 0.9

    def test_negative_start_returns_zero(self):
        t, T = _sigmoid_bake(sigma=0.0)
        assert score_start_candidate(T, t, -1, 400.0, _BASE_CONFIG) == 0.0

    def test_start_beyond_array_returns_zero(self):
        t, T = _sigmoid_bake(n_samples=30, sigma=0.0)
        # Proposed start leaves no room for expected duration → 0
        score = score_start_candidate(T, t, 29, 600.0, _BASE_CONFIG)
        assert score == 0.0

    def test_start_in_middle_of_curve_scores_lower_than_start_at_zero(self):
        """Starting mid-rise truncates the sigmoid shape — fit quality drops."""
        t, T = _sigmoid_bake(n_samples=120, sigma=0.0)
        expected_duration_s = 300.0
        score_good = score_start_candidate(T, t, 0, expected_duration_s, _BASE_CONFIG)
        score_mid = score_start_candidate(T, t, 60, expected_duration_s, _BASE_CONFIG)
        assert score_good >= score_mid, (
            f"start-at-0 score {score_good} should not be less than "
            f"start-at-60 score {score_mid}"
        )


# ---------------------------------------------------------------------------
# Tests: LogisticFit dataclass
# ---------------------------------------------------------------------------

class TestLogisticFitDataclass:

    def test_failed_factory_returns_nan_params_and_converged_false(self):
        f = LogisticFit.failed()
        assert not f.converged
        assert math.isnan(f.L)
        assert math.isnan(f.U)
        assert math.isnan(f.k)
        assert math.isnan(f.t0)
        assert f.r2 == 0.0
        assert math.isinf(f.rmse)


# ---------------------------------------------------------------------------
# Tests: CURVE_DETECTION_CONFIG wiring
# ---------------------------------------------------------------------------


class TestConfigWiring:
    """Pins the 6 new config keys so they cannot be renamed without a test failure.

    M3 Agincourt and M4 Hood will read these from the production
    ``CURVE_DETECTION_CONFIG`` dict; a silent rename here would make
    the detector fall back to ``.get`` defaults which is a drift hazard.
    """

    def test_required_keys_present_in_curve_detection_config(self):
        from config.constants import CURVE_DETECTION_CONFIG

        required = [
            "EXPECTED_DURATION_TOLERANCE_FRAC",
            "EXPECTED_DURATION_MIN_TOLERANCE_SECONDS",
            "SIGMOID_FIT_MIN_R2",
            "SIGMOID_FIT_MIN_SAMPLES",
            "SIGMOID_FIT_COMPOSITE_WEIGHT_R2",
            "SIGMOID_FIT_COMPOSITE_WEIGHT_PROXIMITY",
        ]
        for key in required:
            assert key in CURVE_DETECTION_CONFIG, (
                f"CURVE_DETECTION_CONFIG missing required key '{key}'"
            )

    def test_composite_weights_sum_to_one(self):
        """Documented invariant — drift here distorts the score scale."""
        from config.constants import CURVE_DETECTION_CONFIG

        w_r2 = CURVE_DETECTION_CONFIG["SIGMOID_FIT_COMPOSITE_WEIGHT_R2"]
        w_prox = CURVE_DETECTION_CONFIG["SIGMOID_FIT_COMPOSITE_WEIGHT_PROXIMITY"]
        assert abs((w_r2 + w_prox) - 1.0) < 1e-9, (
            f"Composite weights must sum to 1.0, got {w_r2 + w_prox}"
        )

    def test_tolerance_frac_in_open_unit_interval(self):
        from config.constants import CURVE_DETECTION_CONFIG

        frac = CURVE_DETECTION_CONFIG["EXPECTED_DURATION_TOLERANCE_FRAC"]
        assert 0.0 < frac <= 1.0, f"tolerance_frac out of bounds: {frac}"

    def test_min_samples_is_positive_integer(self):
        from config.constants import CURVE_DETECTION_CONFIG

        n = CURVE_DETECTION_CONFIG["SIGMOID_FIT_MIN_SAMPLES"]
        assert isinstance(n, int) and n > 0
