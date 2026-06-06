"""Per-curve feature extraction + ProfileFit dataclass.

This module is the single source of truth for per-sensor feature vectors used
by the piecewise (and future Stefan) fits. Downstream scoring functions in
``classifier.py`` read from the dict produced by ``extract_features`` and
must never recompute per-sensor quantities themselves — that's the DRY
contract.

The features were chosen to make the four roles physically distinguishable:

- ``terminal_temp`` and ``max_temp`` — coarse role hint: ambient is high,
  dough is plateau-bounded near 100 °C.
- ``plateau_dwell_seconds_near_100c`` — latent-heat plateau is the strongest
  in-dough signature.
- ``time_fraction_below_100c`` — air-side sensors spend almost no time below
  100 °C; deep-dough sensors spend most of the curve below.
- ``rise_slope_30_to_80c_c_per_s`` — air sensors rise faster than dough.
- ``post_80c_variance`` — air sensors keep rising; dough flattens at 100°C.
- ``time_to_100c_seconds`` — dough may never reach 100 °C; air does fast.
- ``xcorr_lag_to_oven_proxy_seconds`` — air sensors are in phase with the
  oven proxy ``max(T1..T8)``; dough sensors lag behind it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Iterable, Union

import numpy as np
import pandas as pd

from config.constants import (  # noqa: E402
    SENSOR_LIST,
    ROLE_CLASSIFIER_CONFIG,
)


def _heat_up_score(features: dict, sensor_name: str, terminal_temp: float) -> float:
    """Heat-up-time score for one sensor — larger = slower-heating = more core-like.

    Single source of the ``time_to_60c → time_to_100c → -terminal_temp``
    fallback chain shared by the piecewise and Stefan fits (each previously
    inlined it twice). ``time_to_60c_seconds`` is preferred because it is
    well-defined for both lidded (no 100 °C crossing) and unlidded bakes;
    ``time_to_100c_seconds`` is the secondary; the NEGATIVE terminal
    temperature is the tertiary fallback so the coldest-terminal sensor still
    wins among sensors that never cross a heat-up threshold.
    """
    feats = features.get(sensor_name, {})
    t60 = feats.get("time_to_60c_seconds")
    if t60 is not None:
        return float(t60)
    t100 = feats.get("time_to_100c_seconds")
    if t100 is not None:
        return float(t100)
    return -float(terminal_temp)


# ---------------------------------------------------------------------------
# ProfileFit dataclass — emitted by the piecewise / Stefan fits.
# ---------------------------------------------------------------------------


class _FitQualityMapping:
    """Read-only, dict-compatible accessors for the typed fit-quality
    dataclasses (``piecewise.PiecewiseFitQuality`` / ``stefan.StefanFitQuality``).

    The classifier and comparison harness read fit-quality fields
    model-agnostically via ``.get(key, default)``. Providing that here lets a
    fit carry a typed, frozen dataclass while those legacy call sites keep
    working unchanged — a key absent from one model's dataclass returns the
    ``.get`` default, exactly as it did when ``fit_quality`` was a free-form
    dict (M28 M3 consolidation).
    """

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def __contains__(self, key):
        return hasattr(self, key)


@dataclass(frozen=True)
class ProfileFit:
    """Result of a per-curve spatial profile fit.

    Attributes
    ----------
    model:
        Identifier of the fit model — ``"piecewise"`` for M2a, ``"stefan"``
        for M2b.
    sensor_positions_normalised:
        8-tuple of normalised probe positions used during the fit.
    terminal_temps:
        Mapping ``sensor → terminal_T`` (the same vector ``fit_piecewise``
        operated on; preserved for downstream traceability).
    x_dough_air:
        Inferred dough/air interface, in the same normalised coordinates.
        ``None`` when no interface is present (full-immersion case). For
        through-loaf insertion this is a 2-tuple
        ``(x_left_interface, x_right_interface)``.
    x_core:
        Position of the coldest in-dough sensor; ``None`` when no dough
        region is identified.
    x_lid:
        Position where T plateau is below cavity proxy by at least
        ``LID_TEMP_BELOW_CAVITY_C``; ``None`` when no lid contact detected.
    fit_quality:
        Typed, frozen, dict-compatible diagnostic — a
        :class:`piecewise.PiecewiseFitQuality` or
        :class:`stefan.StefanFitQuality` (both subclass
        :class:`_FitQualityMapping`, so legacy ``.get(key, default)`` access
        still works). Defaults to an empty dict for fits built without one.
    """

    model: str
    sensor_positions_normalised: tuple
    terminal_temps: dict
    x_dough_air: Union[float, tuple, None]
    x_core: Optional[float]
    x_lid: Optional[float]
    fit_quality: Union[_FitQualityMapping, dict] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-sensor feature extraction
# ---------------------------------------------------------------------------


def compute_oven_proxy(
    df: pd.DataFrame, sensors: Iterable[str] = SENSOR_LIST
) -> pd.Series:
    """Return the time series of ``max(T_sensor for sensor in sensors)``.

    The hottest sensor at each timestep is the most reliable oven-cavity
    proxy — at any moment, whichever sensor is most exposed to free oven air
    samples the cavity temperature.
    """
    cols = [s for s in sensors if s in df.columns]
    if not cols:
        return pd.Series(dtype=float, index=df.index)
    return df[cols].max(axis=1)


def _safe_robust_mean(values: np.ndarray) -> float:
    if values.size == 0:
        return float("nan")
    # Trim to middle 90% via percentile clip — protects against probe-pull
    # spikes without losing all signal in tiny windows.
    if values.size >= 5:
        lo, hi = np.percentile(values, [5, 95])
        clipped = values[(values >= lo) & (values <= hi)]
        if clipped.size > 0:
            return float(np.mean(clipped))
    return float(np.mean(values))


def _longest_contiguous_run(mask: np.ndarray) -> int:
    """Length (in samples) of the longest contiguous True run in ``mask``."""
    if mask.size == 0:
        return 0
    longest = 0
    cur = 0
    for v in mask:
        if v:
            cur += 1
            if cur > longest:
                longest = cur
        else:
            cur = 0
    return longest


def _xcorr_lag_seconds(
    sensor: np.ndarray, proxy: np.ndarray, period_s: float, max_lag_samples: int = 40
) -> float:
    """Return the lag (in seconds) at which ``sensor`` cross-correlates max
    against the oven proxy. Positive lag → sensor trails proxy (dough-like).
    Zero lag → sensor is in phase with proxy (ambient-like).

    Cheap implementation: shift sensor 0..max_lag samples, compute correlation,
    pick the argmax.
    """
    n = len(sensor)
    if n < 5:
        return 0.0
    sensor = np.asarray(sensor, dtype=float)
    proxy = np.asarray(proxy, dtype=float)
    sensor = sensor - np.mean(sensor)
    proxy = proxy - np.mean(proxy)
    s_std = np.std(sensor)
    p_std = np.std(proxy)
    if s_std < 1e-9 or p_std < 1e-9:
        return 0.0

    max_lag = min(max_lag_samples, n - 2)
    best_lag = 0
    best_corr = -np.inf
    for lag in range(0, max_lag + 1):
        if lag == 0:
            s_seg = sensor
            p_seg = proxy
        else:
            s_seg = sensor[lag:]
            p_seg = proxy[:-lag]
        if len(s_seg) < 5:
            continue
        denom = (np.std(s_seg) * np.std(p_seg))
        if denom < 1e-9:
            continue
        corr = float(np.mean(s_seg * p_seg) / denom)
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    return float(best_lag) * period_s


def extract_features(
    df: pd.DataFrame,
    sample_period_ms: int = 5000,
    sensors: Iterable[str] = SENSOR_LIST,
) -> dict:
    """Build the per-sensor feature dict that drives the piecewise fit.

    Returns a dict ``{sensor: feature_vec}`` where ``feature_vec`` is a dict
    with the keys documented in the module docstring.
    """
    cfg = ROLE_CLASSIFIER_CONFIG
    period_s = sample_period_ms / 1000.0

    sensors_present = [s for s in sensors if s in df.columns]
    if not sensors_present:
        return {}

    n = len(df)
    if n == 0:
        return {s: _empty_feature_vec() for s in sensors_present}

    proxy = compute_oven_proxy(df, sensors_present).to_numpy(dtype=float)

    # "Terminal" window — robust per-sensor temperature representative of the
    # active bake. We anchor at the proxy peak: the centre of the window is
    # the index where the oven proxy reaches its max, and the window spans
    # ``TERMINAL_WINDOW_FRACTION`` of the total samples (centred on that idx,
    # clipped to the available range). This captures the steady-state plateau
    # for in-dough sensors and the peak terminal value for air-side sensors,
    # while ignoring post-bake cool-down samples that would otherwise pull
    # every sensor toward room temperature.
    terminal_frac = float(cfg["TERMINAL_WINDOW_FRACTION"])
    half_window = max(1, int(round(n * terminal_frac / 2)))
    if proxy.size > 0 and np.any(np.isfinite(proxy)):
        peak_idx = int(np.nanargmax(proxy))
    else:
        peak_idx = max(0, n - half_window)
    win_lo = max(0, peak_idx - half_window)
    win_hi = min(n, peak_idx + half_window + 1)

    plat_lo = float(cfg["PLATEAU_NEAR_100_LOWER_C"])
    plat_hi = float(cfg["PLATEAU_NEAR_100_UPPER_C"])
    plat_rate = float(cfg["PLATEAU_RATE_THRESHOLD_C_PER_S"])
    rise_lo = float(cfg["RISE_SLOPE_LOWER_C"])
    rise_hi = float(cfg["RISE_SLOPE_UPPER_C"])

    out: dict[str, dict] = {}
    for sensor in sensors_present:
        values = df[sensor].to_numpy(dtype=float)

        # Terminal robust mean — anchored at the proxy peak (see above).
        terminal_window = values[win_lo:win_hi]
        terminal_temp = _safe_robust_mean(terminal_window)

        max_temp = float(np.nanmax(values)) if values.size else float("nan")

        # Plateau-near-100°C dwell: contiguous run where T ∈ [lo, hi] AND
        # |dT/dt| < plat_rate.
        dT = np.gradient(values, period_s)
        plateau_mask = (
            (values >= plat_lo)
            & (values <= plat_hi)
            & (np.abs(dT) < plat_rate)
        )
        run_samples = _longest_contiguous_run(plateau_mask)
        plateau_dwell_s = float(run_samples) * period_s

        # Time fraction below 100 °C.
        below_mask = values < 100.0
        time_fraction_below_100c = float(below_mask.mean())

        # Rise slope in [rise_lo, rise_hi] band — linear regression on those
        # samples. If too few samples, returns None (handled downstream).
        in_band = (values >= rise_lo) & (values <= rise_hi)
        if in_band.sum() >= 3:
            xs = np.flatnonzero(in_band).astype(float) * period_s
            ys = values[in_band]
            try:
                slope = float(np.polyfit(xs, ys, 1)[0])
            except (np.linalg.LinAlgError, ValueError):
                slope = None
        else:
            slope = None

        # Variance above 80 °C — air sensors keep rising; dough flattens.
        above_80 = values[values > 80.0]
        post_80c_variance = float(np.var(above_80)) if above_80.size > 1 else 0.0

        # Time to first crossing of 100 °C.
        crossings = np.flatnonzero(values >= 100.0)
        if crossings.size > 0:
            time_to_100c = float(crossings[0]) * period_s
        else:
            time_to_100c = None

        # Time to first crossing of 60 °C — robust heat-up-speed feature
        # for lid bakes where no sensor reaches 100 °C. Air-side sensors
        # cross 60 °C far faster than deep-dough sensors.
        crossings_60 = np.flatnonzero(values >= 60.0)
        if crossings_60.size > 0:
            time_to_60c = float(crossings_60[0]) * period_s
        else:
            time_to_60c = None

        # Cross-correlation lag against the oven proxy.
        xcorr_lag_s = _xcorr_lag_seconds(values, proxy, period_s)

        out[sensor] = {
            "terminal_temp": terminal_temp,
            "max_temp": max_temp,
            "plateau_dwell_seconds_near_100c": plateau_dwell_s,
            "time_fraction_below_100c": time_fraction_below_100c,
            "rise_slope_30_to_80c_c_per_s": slope,
            "post_80c_variance": post_80c_variance,
            "time_to_100c_seconds": time_to_100c,
            "time_to_60c_seconds": time_to_60c,
            "xcorr_lag_to_oven_proxy_seconds": xcorr_lag_s,
        }

    return out


def interpolate_temperature_series_at(
    df: pd.DataFrame,
    positions: tuple,
    x_target: float,
    sensors: tuple = SENSOR_LIST,
) -> pd.Series:
    """Per-timestep linear spatial interpolation along the probe axis.

    For each timestep ``t``, treat ``(positions, [df[s][t] for s in sensors])``
    as samples of T(x) and linearly interpolate at ``x = x_target``. The
    result is a pd.Series aligned with ``df.index``.

    Behaviour at boundaries:
    * ``x_target <= positions[0]`` → returns ``df[sensors[0]].copy()``.
    * ``x_target >= positions[-1]`` → returns ``df[sensors[-1]].copy()``.
    * Otherwise the two adjacent sensors bracketing ``x_target`` are
      identified via ``np.searchsorted`` and the per-row blend
      ``(1 - frac) * df[s_lo] + frac * df[s_hi]`` is returned.

    Vectorised: the per-row blend is a single numpy linear combination of
    two columns — no per-row Python loop.
    """
    pos_arr = np.asarray(positions, dtype=float)
    n = len(pos_arr)
    sensors_t = tuple(sensors)
    if n == 0 or len(sensors_t) == 0:
        return pd.Series([], dtype=float, index=df.index)
    if len(sensors_t) < n:
        # Trim positions to the available sensor count (shouldn't happen for
        # the canonical 8-sensor probe, but degrade gracefully).
        pos_arr = pos_arr[: len(sensors_t)]
        n = len(sensors_t)

    if x_target <= pos_arr[0]:
        s0 = sensors_t[0]
        return df[s0].copy() if s0 in df.columns else pd.Series(
            np.zeros(len(df)), index=df.index, dtype=float
        )
    if x_target >= pos_arr[-1]:
        sN = sensors_t[n - 1]
        return df[sN].copy() if sN in df.columns else pd.Series(
            np.zeros(len(df)), index=df.index, dtype=float
        )

    upper_idx = int(np.searchsorted(pos_arr, x_target))
    if upper_idx <= 0:
        upper_idx = 1
    if upper_idx >= n:
        upper_idx = n - 1
    lower_idx = upper_idx - 1
    x_lo = float(pos_arr[lower_idx])
    x_hi = float(pos_arr[upper_idx])
    if x_hi == x_lo:
        # Degenerate (duplicate positions) — fall back to the lower sensor.
        s_lo = sensors_t[lower_idx]
        return df[s_lo].copy() if s_lo in df.columns else pd.Series(
            np.zeros(len(df)), index=df.index, dtype=float
        )
    frac = (x_target - x_lo) / (x_hi - x_lo)
    s_lo = sensors_t[lower_idx]
    s_hi = sensors_t[upper_idx]
    if s_lo not in df.columns or s_hi not in df.columns:
        # Missing sensor column — return whichever exists, else zeros.
        if s_lo in df.columns:
            return df[s_lo].copy()
        if s_hi in df.columns:
            return df[s_hi].copy()
        return pd.Series(np.zeros(len(df)), index=df.index, dtype=float)
    blended = (1.0 - frac) * df[s_lo] + frac * df[s_hi]
    blended.name = None
    return blended


def _empty_feature_vec() -> dict:
    return {
        "terminal_temp": float("nan"),
        "max_temp": float("nan"),
        "plateau_dwell_seconds_near_100c": 0.0,
        "time_fraction_below_100c": 0.0,
        "rise_slope_30_to_80c_c_per_s": None,
        "post_80c_variance": 0.0,
        "time_to_100c_seconds": None,
        "time_to_60c_seconds": None,
        "xcorr_lag_to_oven_proxy_seconds": 0.0,
    }
