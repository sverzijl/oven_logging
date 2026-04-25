"""Sigmoid-aware refinement helpers for curve-boundary detection.

Pure module (no pandas / streamlit / loader imports) so it can be unit
tested in isolation and consumed by the detector without coupling to
Streamlit session state or DataFrame layout.

Fitted model: ``T(t) = L + (U - L) / (1 + exp(-k * (t - t0)))``.

The module is **passive**.  It computes a score in ``[0, 1]`` that a
caller (M3 Agincourt, M4 Hood) uses to arbitrate among competing
end/start candidates — it never decides a candidate on its own.

Introduced by flotilla mission M2 HMS Resolution (branch
``refactor/expected-bake-time``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import curve_fit


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LogisticFit:
    """Result of a 4-parameter logistic fit.

    Attributes
    ----------
    L
        Lower asymptote (ambient / start temperature, °C).
    U
        Upper asymptote (peak / plateau temperature, °C).
    k
        Steepness parameter (1/s); positive for a rising sigmoid.
    t0
        Inflection time in the same units as the input ``t`` (typically
        seconds, relative to the window start).
    r2
        Coefficient of determination on the fit window.
    rmse
        Root-mean-squared error in °C.
    converged
        ``True`` iff ``scipy.optimize.curve_fit`` returned without
        raising.  When ``False`` the numerical fields are NaN / Inf and
        must not be used.
    """

    L: float
    U: float
    k: float
    t0: float
    r2: float
    rmse: float
    converged: bool

    @classmethod
    def failed(cls) -> "LogisticFit":
        """Sentinel for a non-converged fit."""
        return cls(
            L=math.nan,
            U=math.nan,
            k=math.nan,
            t0=math.nan,
            r2=0.0,
            rmse=math.inf,
            converged=False,
        )


# ---------------------------------------------------------------------------
# Core fit
# ---------------------------------------------------------------------------


def _logistic(
    t: np.ndarray, L: float, U: float, k: float, t0: float
) -> np.ndarray:
    z = -k * (t - t0)
    # Clamp the exponent to avoid overflow on pathological initial guesses.
    z = np.clip(z, -500.0, 500.0)
    return L + (U - L) / (1.0 + np.exp(z))


def fit_logistic(t: np.ndarray, T: np.ndarray) -> LogisticFit:
    """Fit ``T(t) = L + (U - L) / (1 + exp(-k * (t - t0)))``.

    Returns a :class:`LogisticFit`.  The fit is considered *converged*
    only when ``curve_fit`` returns without raising; callers must still
    check ``LogisticFit.r2`` against their quality gate.
    """
    t = np.asarray(t, dtype=float)
    T = np.asarray(T, dtype=float)
    if t.shape != T.shape or t.ndim != 1 or len(t) < 4:
        return LogisticFit.failed()

    L0 = float(np.min(T))
    U0 = float(np.max(T))
    if U0 - L0 < 1e-6:  # essentially flat data
        return LogisticFit.failed()

    # Midpoint-crossing heuristic for t0.
    mid = 0.5 * (L0 + U0)
    above = np.where(T >= mid)[0]
    t0_init = float(t[above[0]]) if above.size > 0 else float(t[len(t) // 2])
    span = float(t[-1] - t[0]) if len(t) > 1 else 1.0
    k0 = 4.0 / span if span > 0 else 1.0

    try:
        popt, _ = curve_fit(
            _logistic,
            t,
            T,
            p0=[L0, U0, k0, t0_init],
            maxfev=2000,
            bounds=(
                [L0 - 20.0, L0, 0.0, float(t[0]) - span],
                [U0, U0 + 20.0, 10.0, float(t[-1]) + span],
            ),
        )
    except (RuntimeError, ValueError):
        return LogisticFit.failed()

    L, U, k, t0 = (float(x) for x in popt)
    T_pred = _logistic(t, L, U, k, t0)
    ss_res = float(np.sum((T - T_pred) ** 2))
    ss_tot = float(np.sum((T - float(np.mean(T))) ** 2))
    r2 = 0.0 if ss_tot < 1e-12 else 1.0 - ss_res / ss_tot
    rmse = float(np.sqrt(ss_res / len(T)))
    return LogisticFit(L=L, U=U, k=k, t0=t0, r2=r2, rmse=rmse, converged=True)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _proximity_score(
    actual_duration_s: float, expected_duration_s: float, tolerance_frac: float
) -> float:
    """Linear falloff within the tolerance band; 0 outside.

    Returns 1.0 when actual == expected, 0.0 at the edge of the band,
    and 0.0 everywhere beyond.  The caller controls tolerance_frac
    (typically ``EXPECTED_DURATION_TOLERANCE_FRAC``).
    """
    if expected_duration_s <= 0.0 or tolerance_frac <= 0.0:
        return 0.0
    band = expected_duration_s * tolerance_frac
    deviation = abs(actual_duration_s - expected_duration_s)
    if deviation >= band:
        return 0.0
    return 1.0 - deviation / band


def score_end_candidate(
    temps: np.ndarray,
    timestamps: np.ndarray,
    start_idx: int,
    candidate_idx: int,
    expected_duration_s: float,
    config: dict[str, Any],
) -> float:
    """Score an end-candidate index in ``[0, 1]``.

    Combines sigmoid fit quality (R² gated at ``SIGMOID_FIT_MIN_R2``)
    with proximity to the expected duration.  Returns 0.0 on
    insufficient samples, flat data, or non-converged fit.

    Short-circuits *before* invoking ``curve_fit`` when the window is
    smaller than ``SIGMOID_FIT_MIN_SAMPLES`` so the hot path stays cheap.
    """
    if candidate_idx <= start_idx:
        return 0.0

    min_samples = int(config.get("SIGMOID_FIT_MIN_SAMPLES", 30))
    n = candidate_idx - start_idx + 1
    if n < min_samples:
        return 0.0

    temps_arr = np.asarray(temps, dtype=float)
    ts_arr = np.asarray(timestamps, dtype=float)
    if candidate_idx >= len(temps_arr) or candidate_idx >= len(ts_arr):
        return 0.0

    t_window = ts_arr[start_idx : candidate_idx + 1]
    T_window = temps_arr[start_idx : candidate_idx + 1]
    # Normalise time origin for numerical stability.
    t_window = t_window - t_window[0]

    fit = fit_logistic(t_window, T_window)

    min_r2 = float(config.get("SIGMOID_FIT_MIN_R2", 0.85))
    w_r2 = float(config.get("SIGMOID_FIT_COMPOSITE_WEIGHT_R2", 0.6))
    w_prox = float(config.get("SIGMOID_FIT_COMPOSITE_WEIGHT_PROXIMITY", 0.4))
    tol_frac = float(config.get("EXPECTED_DURATION_TOLERANCE_FRAC", 0.15))

    if fit.converged and fit.r2 >= min_r2:
        r2_component = max(0.0, min(1.0, fit.r2))
    else:
        r2_component = 0.0

    actual_duration = float(ts_arr[candidate_idx] - ts_arr[start_idx])
    prox_component = _proximity_score(
        actual_duration, expected_duration_s, tol_frac
    )

    score = w_r2 * r2_component + w_prox * prox_component
    # Clamp to [0, 1] against pathological weight configs.
    return max(0.0, min(1.0, score))


def score_start_candidate(
    temps: np.ndarray,
    timestamps: np.ndarray,
    proposed_start_idx: int,
    expected_duration_s: float,
    config: dict[str, Any],
) -> float:
    """Score a proposed start index in ``[0, 1]``.

    Infers a window end by advancing from ``proposed_start_idx`` until
    ``timestamps`` exceeds ``proposed_start_idx_time + expected_duration_s``,
    then delegates to :func:`score_end_candidate`.  This lets M4 Hood
    evaluate "if I moved the start to here, would the sigmoid fit over
    the expected-duration window?"
    """
    ts_arr = np.asarray(timestamps, dtype=float)
    n = len(ts_arr)
    if proposed_start_idx < 0 or proposed_start_idx >= n:
        return 0.0
    if expected_duration_s <= 0.0:
        return 0.0

    target_end_time = ts_arr[proposed_start_idx] + expected_duration_s
    candidate_idx = int(np.searchsorted(ts_arr, target_end_time))
    candidate_idx = min(candidate_idx, n - 1)
    if candidate_idx <= proposed_start_idx:
        return 0.0

    return score_end_candidate(
        temps,
        timestamps,
        proposed_start_idx,
        candidate_idx,
        expected_duration_s,
        config,
    )


__all__ = [
    "LogisticFit",
    "fit_logistic",
    "score_end_candidate",
    "score_start_candidate",
]
