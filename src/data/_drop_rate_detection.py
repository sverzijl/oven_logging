"""Shared drop-rate detection primitives.

Both the curve boundary detector and the core-sensor classifier need to find
the first index at which a drop rate sustains above a threshold — the
unmistakable signature of an operator pulling the probe out of the loaf.

Two flavours of the primitive live here:

- ``find_confirmed_drop_start`` — single-series scan (one temperature signal).
  Used by ``curve_boundary_detector._candidate_drop_rate`` where the exit
  signal comes from the resolved core temperature alone.

- ``find_confirmed_multi_sensor_drop`` — multi-series scan where the
  confirmation requires at least ``min_k_sensors`` sensors (default 2)
  exceeding the rate threshold on the SAME sample, for ``confirm_n``
  consecutive samples. Physics: a real probe pull extracts the whole probe
  at once so ≥2 sensors drop simultaneously; single-sensor noise spikes are
  uncorrelated. Tightened from any-sensor (min_k=1) to min_k=2 per
  Audacious red-cell verdict (mission 2026-04-24_015052_25705c7a) which
  measured 13%→4% false-positive rate on BA3C_1759 at σ=1.0 °C noise.
  See CORE_DETECTION_CONFIG["PROBE_REMOVAL_MIN_SIMULTANEOUS_SENSORS"] for
  the tuning rationale.
  Used by ``thermodynamic_sensor_classifier._detect_probe_removal_in_cool_window``.

Keeping both helpers here keeps the rate-computation semantics in one place
(DRY; see memory/feedback_tdd_dry.md — mission 2026-04-24_015052_25705c7a).
"""

from __future__ import annotations

import numpy as np


def _rate_at(
    temps: np.ndarray, timestamps: np.ndarray, idx: int
) -> float | None:
    """Drop rate in °C/s at ``idx`` — ``(temps[idx-1]-temps[idx]) / dt``.

    Returns ``None`` when the rate is undefined (at idx=0 or dt<=0).
    """
    if idx == 0:
        return None
    dt = timestamps[idx] - timestamps[idx - 1]
    if dt <= 0:
        return None
    return (temps[idx - 1] - temps[idx]) / dt


def find_confirmed_drop_start(
    temps: np.ndarray,
    timestamps: np.ndarray,
    first_scan: int,
    rate_c_s: float,
    confirm_n: int,
) -> int | None:
    """Return the first index ``j`` in ``[first_scan, len(temps))`` such that
    every sample in ``[j, j + confirm_n)`` shows a drop-rate (°C/s) strictly
    exceeding ``rate_c_s`` on a single series ``temps``.
    """
    n = len(temps)

    for j in range(first_scan, n):
        if j == 0:
            continue
        window_ok = True
        for k in range(confirm_n):
            idx = j + k
            if idx >= n:
                window_ok = False
                break
            rate = _rate_at(temps, timestamps, idx)
            if rate is None or rate < rate_c_s:
                window_ok = False
                break
        if window_ok:
            return j
    return None


def find_confirmed_multi_sensor_drop(
    sensor_temps: dict[str, np.ndarray],
    timestamps: np.ndarray,
    first_scan: int,
    rate_c_s: float,
    confirm_n: int,
    min_k_sensors: int = 2,
) -> int | None:
    """Return the first index ``j`` in ``[first_scan, len(timestamps))`` such that
    every sample in ``[j, j + confirm_n)`` has AT LEAST ``min_k_sensors``
    sensors whose drop rate (°C/s) at or exceeds ``rate_c_s`` on the SAME sample.

    ``min_k_sensors=2`` (default) matches the physics of a whole-probe pull:
    the operator extracts the entire probe at once so multiple sensors exit the
    loaf simultaneously. A single-sensor spike on any given sample is
    characteristic of noise rather than probe extraction.

    Tightened from any-sensor (min_k=1) to min_k=2 per Audacious red-cell
    verdict (mission 2026-04-24_015052_25705c7a): BA3C_1759 false-positive rate
    at σ=1.0 °C noise dropped from 13% (min_k=1) to 4% (min_k=2) while the
    PWM true positive was retained. See CORE_DETECTION_CONFIG[
    "PROBE_REMOVAL_MIN_SIMULTANEOUS_SENSORS"] for the config entry.

    Note on staggered pulls: min_k=2 still fires on PWM (T1 at idx 345, T5/T6
    at idx 346 — both samples have ≥2 sensors above threshold). The staggered-
    sensor timing is within a single confirm_n=2 window, not spread across many
    independent samples, so this requirement does not under-trigger on real data.
    """
    n = len(timestamps)

    if not sensor_temps:
        return None

    def count_sensor_drops(idx: int) -> int:
        count = 0
        for temps in sensor_temps.values():
            if idx >= len(temps):
                continue
            rate = _rate_at(temps, timestamps, idx)
            if rate is not None and rate >= rate_c_s:
                count += 1
        return count

    for j in range(first_scan, n):
        if j == 0:
            continue
        window_ok = True
        for k in range(confirm_n):
            idx = j + k
            if idx >= n or count_sensor_drops(idx) < min_k_sensors:
                window_ok = False
                break
        if window_ok:
            return j
    return None
