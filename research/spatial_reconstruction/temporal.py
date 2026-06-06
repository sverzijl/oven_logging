"""Temporal wrapper over the per-snapshot spatial classifier (M23 HMS Drake).

Runs the existing :func:`classify` function repeatedly across a stride grid of
timesteps, collecting per-snapshot derived quantities (core position, surface
position, 100 C "Stefan-front" position, interpolated temperatures at those
positions, per-snapshot confidence) into time-series arrays. Applies a
Savitzky-Golay smoother to the resulting traces for visual continuity.

The piecewise / Stefan ``ProfileFit`` exposes the 100 C dough/air interface
under the field ``x_dough_air``. In the canonical single-interface case it is
a float; in the through-loaf case it is a 2-tuple ``(x_left, x_right)``; and
in pre-front / fully-immersed snapshots it is ``None``. We surface this field
under the public name ``x_stefan_front`` because the 100 C latent-heat front
IS the Stefan front in the dough/air thermodynamics — they are two names for
the same physical quantity. For through-loaf, we report the right-side
interface (matches the classifier's ``surface_assignment`` convention).

Windowing strategy: the classifier consumes ALL rows up to the stride centre
time (causal, all-history). The classifier internally computes terminal-window
features anchored at the proxy peak, so feeding it more data at later times
strengthens the fit rather than confusing it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .classifier import classify, SpatialAssignment


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemporalAssignment:
    """Time-evolving derived quantities from per-snapshot classification.

    All trace arrays share the same length as ``t_grid_s``. NaN entries
    indicate the per-snapshot classifier could not infer that quantity at
    that stride (e.g. Stefan front before any sensor crosses 100 C).
    """

    t_grid_s: np.ndarray              # stride centre times in seconds
    x_core_t: np.ndarray              # smoothed normalised core position
    x_surface_t: np.ndarray           # smoothed dough/air surface position
    x_stefan_front_t: np.ndarray      # smoothed 100 C front position (NaN when undefined)
    T_core_t: np.ndarray              # core T (interpolated at x_core)
    T_surface_t: np.ndarray           # surface T (interpolated at x_surface)
    confidence_t: list                # per-snapshot confidence: 'high'|'medium'|'low'

    # Raw (un-smoothed) versions for diagnostics
    x_core_t_raw: np.ndarray
    x_surface_t_raw: np.ndarray
    x_stefan_front_t_raw: np.ndarray


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_stefan_front(assignment: SpatialAssignment) -> float:
    """Return the (right-side, when ambiguous) 100 C dough/air front position.

    NaN when the snapshot has no inferred front (full-immersion / pre-100 C).
    """
    fit = assignment.profile_fit
    x = fit.x_dough_air
    if x is None:
        return float("nan")
    if isinstance(x, tuple):
        # Through-loaf — return the right-side (high-x) interface, matching
        # ``classifier.surface_assignment``'s convention.
        return float(x[1])
    return float(x)


def _smooth_savgol(
    raw: np.ndarray,
    window_samples: int,
    polyorder: int,
) -> np.ndarray:
    """Apply Savitzky-Golay smoothing to a 1D trace, NaN-aware.

    NaN entries in the input pass through unchanged. The filter is applied to
    each contiguous finite run of length >= ``polyorder + 2``; shorter runs
    are returned verbatim. The window length is forced odd and clipped to the
    longest finite run.

    Falls back to ``raw`` when scipy is not installed (defensive — the project
    requires scipy elsewhere but unit tests should not fail with ImportError
    in degraded environments).
    """
    if raw.size < 5:
        return raw.copy()

    try:
        from scipy.signal import savgol_filter
    except ImportError:
        return raw.copy()

    out = raw.copy()
    finite_mask = np.isfinite(raw)
    if finite_mask.sum() < polyorder + 2:
        return out

    # Apply per contiguous run.
    in_run = False
    run_start = 0
    n = raw.size
    for i in range(n + 1):
        is_finite = i < n and finite_mask[i]
        if is_finite and not in_run:
            in_run = True
            run_start = i
        elif (not is_finite) and in_run:
            in_run = False
            run_end = i  # exclusive
            run_len = run_end - run_start
            if run_len >= polyorder + 2:
                w = min(window_samples, run_len)
                if w % 2 == 0:
                    w -= 1
                if w >= polyorder + 2:
                    out[run_start:run_end] = savgol_filter(
                        raw[run_start:run_end], window_length=w, polyorder=polyorder
                    )
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def classify_temporal(
    df: pd.DataFrame,
    sample_period_ms: int = 5000,
    probe_geometry: Optional[dict] = None,
    model: str = "piecewise",
    stride_seconds: float = 30.0,
    smoothing_window_seconds: float = 120.0,
    smoothing_polyorder: int = 2,
    min_samples_to_classify: int = 30,
) -> TemporalAssignment:
    """Run the classifier across the bake; smooth the resulting traces.

    Parameters
    ----------
    df:
        Per-curve DataFrame with the canonical T1..T8 sensor columns.
    sample_period_ms:
        Sample period in milliseconds (defaults to 5000, matching Combustion
        firmware).
    probe_geometry:
        Optional probe geometry override; ``None`` uses the default 8-sensor
        uniform geometry.
    model:
        Either ``"piecewise"`` (default) or ``"stefan"``. Passed through to
        :func:`classify`.
    stride_seconds:
        Spacing of the stride grid (in seconds). Default 30 s.
    smoothing_window_seconds:
        Savitzky-Golay window width (in seconds). Forced to the nearest odd
        sample count and clipped to the trace length.
    smoothing_polyorder:
        SavGol polynomial order. Default 2.
    min_samples_to_classify:
        Skip strides whose causal sub-DataFrame has fewer than this many rows
        (the bake hasn't started yet — classifier has no signal).

    Returns
    -------
    TemporalAssignment
        Dataclass with ``t_grid_s``, smoothed and raw position traces,
        interpolated core/surface temperature traces, and per-stride
        confidence labels.
    """
    period_s = sample_period_ms / 1000.0
    n_rows = len(df)
    if n_rows == 0:
        empty = np.array([], dtype=float)
        return TemporalAssignment(
            t_grid_s=empty,
            x_core_t=empty,
            x_surface_t=empty,
            x_stefan_front_t=empty,
            T_core_t=empty,
            T_surface_t=empty,
            confidence_t=[],
            x_core_t_raw=empty,
            x_surface_t_raw=empty,
            x_stefan_front_t_raw=empty,
        )

    # Bake duration in seconds (sample-count * period; we don't trust the
    # Timestamp column to be monotonic across all CSVs).
    bake_duration_s = (n_rows - 1) * period_s

    # Stride grid — start from the first stride that satisfies the minimum-
    # samples condition (so we don't waste classifier calls on near-empty df).
    first_stride_s = max(stride_seconds, min_samples_to_classify * period_s)
    if bake_duration_s < first_stride_s:
        # Whole bake is shorter than the warm-up window — return empty traces.
        empty = np.array([], dtype=float)
        return TemporalAssignment(
            t_grid_s=empty,
            x_core_t=empty,
            x_surface_t=empty,
            x_stefan_front_t=empty,
            T_core_t=empty,
            T_surface_t=empty,
            confidence_t=[],
            x_core_t_raw=empty,
            x_surface_t_raw=empty,
            x_stefan_front_t_raw=empty,
        )

    t_grid = np.arange(first_stride_s, bake_duration_s + 1e-9, stride_seconds)

    # Per-snapshot collection.
    x_core_raw = np.full(t_grid.size, np.nan, dtype=float)
    x_surface_raw = np.full(t_grid.size, np.nan, dtype=float)
    x_stefan_raw = np.full(t_grid.size, np.nan, dtype=float)
    T_core = np.full(t_grid.size, np.nan, dtype=float)
    T_surface = np.full(t_grid.size, np.nan, dtype=float)
    confidence: list = []

    for k, t_c in enumerate(t_grid):
        # Causal window: rows [0, end_idx] with end_idx = floor(t_c / period_s)
        end_idx = int(np.floor(float(t_c) / period_s)) + 1
        end_idx = max(0, min(n_rows, end_idx))
        df_window = df.iloc[:end_idx]
        if len(df_window) < min_samples_to_classify:
            confidence.append("low")
            continue
        try:
            assignment: SpatialAssignment = classify(
                df_window,
                sample_period_ms=sample_period_ms,
                probe_geometry=probe_geometry,
                model=model,
            )
        except Exception:
            confidence.append("low")
            continue

        # Core position + interpolated terminal temperature at that position.
        if assignment.core_assignment is not None:
            x_core_raw[k] = float(assignment.core_assignment.position_normalised)
            ts_core = assignment.core_assignment.temperature_series
            if isinstance(ts_core, pd.Series) and ts_core.size > 0:
                # Use the latest available value (the "now" temperature at the
                # inferred core position — what the user wants to see on the
                # time-series plot).
                last = ts_core.iloc[-1]
                T_core[k] = float(last) if pd.notna(last) else float("nan")
            confidence.append(assignment.core_assignment.confidence)
        else:
            confidence.append("low")

        # Surface position + temperature at that position.
        if assignment.surface_assignment is not None:
            x_surface_raw[k] = float(assignment.surface_assignment.position_normalised)
            ts_surf = assignment.surface_assignment.temperature_series
            if isinstance(ts_surf, pd.Series) and ts_surf.size > 0:
                last = ts_surf.iloc[-1]
                T_surface[k] = float(last) if pd.notna(last) else float("nan")

        # Stefan front from the underlying ProfileFit.
        x_stefan_raw[k] = _extract_stefan_front(assignment)

    # Length-confidence sanity — confidence list may have been shorter than
    # t_grid if early loops continued before append; pad to t_grid length.
    while len(confidence) < t_grid.size:
        confidence.append("low")

    # ------------------------------------------------------------------
    # Savitzky-Golay smoothing.
    # ------------------------------------------------------------------
    window_samples = max(3, int(round(smoothing_window_seconds / stride_seconds)))
    if window_samples % 2 == 0:
        window_samples += 1

    x_core_smooth = _smooth_savgol(x_core_raw, window_samples, smoothing_polyorder)
    x_surface_smooth = _smooth_savgol(x_surface_raw, window_samples, smoothing_polyorder)
    x_stefan_smooth = _smooth_savgol(x_stefan_raw, window_samples, smoothing_polyorder)

    return TemporalAssignment(
        t_grid_s=t_grid,
        x_core_t=x_core_smooth,
        x_surface_t=x_surface_smooth,
        x_stefan_front_t=x_stefan_smooth,
        T_core_t=T_core,
        T_surface_t=T_surface,
        confidence_t=confidence,
        x_core_t_raw=x_core_raw,
        x_surface_t_raw=x_surface_raw,
        x_stefan_front_t_raw=x_stefan_raw,
    )
