"""Isothermal-position tracker over time (M24 HMS Foxhound).

Different from per-snapshot classifier-driver in ``temporal.py``: at each
timestep, interpolate the sensor temperatures spatially to find where T
crosses target values (60, 80, 100, 110 C). These are physically meaningful
'fronts' that advance through the dough during baking.

Key contract: the core/surface positions are computed ONCE from the full
bake (using ``classify``) and reported as scalars — the probe doesn't move,
so the geometric core position should NOT be time-varying. The "walking
core" artefact in M23 was the snapshot classifier being run on incomplete
mid-bake data; the role-assignment heuristics misbehave because they were
designed for full-bake spatial profiles.

The isotherms (60, 80, 100, 110 C) DO move over time — they are the
advancing temperature fronts. These are what the user actually wants to
see on a "moisture front" diagram: 100 C is the Stefan front
(latent-heat boiling boundary), 60 C is the yeast-kill front, 80 C is
roughly the starch-gelatinisation onset, and 110 C is the crust-formation
zone.

The full bake is also processed via :func:`classify` for fixed core/surface
positions — so this module is DRY with respect to the per-snapshot logic
already shipped in M2a.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from config.constants import SENSOR_LIST  # noqa: E402

from .classifier import classify, SpatialAssignment
from .geometry import lookup_geometry
from .profile import interpolate_temperature_series_at


DEFAULT_ISOTHERMS_C = (60.0, 80.0, 100.0, 110.0)

# Epsilon for the "<= fixed_surface_x" in-bounds test (fix/deep-review #2b).
_SURFACE_EPS = 1e-6


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IsothermalAssignment:
    """Time-evolving isotherm positions plus fixed core/surface positions.

    Attributes
    ----------
    t_grid_s:
        Stride centre times in seconds; length ``N_t``.
    isotherm_temps_C:
        Tuple of target temperatures used (e.g. ``(60.0, 80.0, 100.0, 110.0)``).
    isotherm_positions:
        ``{T_target: smoothed_x_array}``; each array has length ``N_t`` and
        contains NaN where the isotherm is not yet (or no longer) defined.
    isotherm_positions_raw:
        Same shape as ``isotherm_positions`` but pre-smoothing.
    fixed_core_x:
        Single normalised core position from the full-bake :func:`classify`
        result. Does NOT vary with time — the probe doesn't move.
    fixed_surface_x:
        Single normalised surface position from the full-bake classify
        result. NaN if the classifier could not determine a surface.
    T_at_fixed_core_t:
        Temperature at the fixed core position over time (per-stride
        spatial interpolation across the eight sensors).
    T_at_fixed_surface_t:
        Temperature at the fixed surface position over time.
    classification:
        The full-bake :class:`SpatialAssignment` (kept for diagnostics).
    """

    t_grid_s: np.ndarray
    isotherm_temps_C: tuple
    isotherm_positions: dict
    isotherm_positions_raw: dict
    fixed_core_x: float
    fixed_surface_x: float
    T_at_fixed_core_t: np.ndarray
    T_at_fixed_surface_t: np.ndarray
    classification: SpatialAssignment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_isotherm_crossings(
    sensor_positions_norm: np.ndarray,
    sensor_temps_C: np.ndarray,
    target_T_C: float,
) -> list[float]:
    """Return ALL x-positions where the spatial T(x) profile crosses
    ``target_T_C``, sorted ascending by x.

    Bracket-scan (the same pattern ``piecewise._crossing_position`` and
    ``stefan._find_100c_crossings`` use): order the sensors by position, then
    scan EVERY adjacent pair for a bracket ``min(t0,t1) <= target <= max(t0,t1)``
    and linearly interpolate the crossing position within that pair. A
    non-monotonic / U-shaped profile (Wonder full-crumb) yields multiple
    crossings; the caller decides which to report.

    NaN sensor temperatures are dropped before the scan (defensive).
    Returns an empty list when no pair brackets the target.
    """
    pos = np.asarray(sensor_positions_norm, dtype=float)
    T = np.asarray(sensor_temps_C, dtype=float)
    if pos.size != T.size or pos.size == 0:
        return []
    finite_mask = np.isfinite(T)
    if finite_mask.sum() < 2:
        return []
    pos = pos[finite_mask]
    T = T[finite_mask]

    sorted_idx = np.argsort(pos)
    positions = pos[sorted_idx]
    temps = T[sorted_idx]

    crossings: list[float] = []
    for i in range(len(temps) - 1):
        t0 = float(temps[i])
        t1 = float(temps[i + 1])
        lo_T = min(t0, t1)
        hi_T = max(t0, t1)
        if lo_T <= target_T_C <= hi_T:
            x0 = float(positions[i])
            x1 = float(positions[i + 1])
            denom = t1 - t0
            if denom == 0.0:
                # Flat bracket sitting exactly on the target — the crossing
                # spans [x0, x1]; report the surface-side (higher-x) end.
                x_cross = max(x0, x1)
            else:
                frac = (target_T_C - t0) / denom
                frac = float(np.clip(frac, 0.0, 1.0))
                x_cross = x0 + frac * (x1 - x0)
            crossings.append(x_cross)
    crossings.sort()
    return crossings


def _find_isotherm_position(
    sensor_positions_norm: np.ndarray,
    sensor_temps_C: np.ndarray,
    target_T_C: float,
    max_x: float | None = None,
    prefer_near: float | None = None,
) -> float:
    """Find x where the spatial T(x) profile crosses ``target_T_C``.

    fix/deep-review #4 / #16 / #2b. Wraps :func:`_find_isotherm_crossings` and
    selects ONE crossing under two well-defined constraints:

    * ``prefer_near`` (fix/deep-review #2b constraint (b)) — when supplied,
      return the crossing NEAREST this hint (the previous stride's reported
      position for this isotherm) to enforce front CONTINUITY across strides and
      eliminate the discontinuous teleport (probe-tip limb -> grazing surface
      sensor the instant it reaches the target).
    * ``max_x`` (fix/deep-review #2b constraint (a)) — used only to SEED the
      first finite stride (``prefer_near is None``): among the crossings, prefer
      the surface-most one that is still ``<= max_x`` (the inferred surface).
      The moisture/Stefan front advances inward from the surface, so the
      surface-side in-bounds crossing is the physically relevant seed. If NO
      crossing is in-bounds (e.g. a genuine crust front sitting just outside the
      dough/air interface, as on BA3C's 100 C front), fall back to the
      surface-most crossing rather than dropping the front — clamping the seed
      below a genuine crust front would amputate it.

    With neither hint set, behaviour is the legacy "surface-most crossing"; with
    no bracket at all, returns NaN (never snaps to 0.0).
    """
    crossings = _find_isotherm_crossings(
        sensor_positions_norm, sensor_temps_C, target_T_C
    )
    if not crossings:
        return float("nan")
    # Constraint (b): front continuity — pick the crossing nearest the hint.
    # Continuity, not clamping, is what prevents the teleport on a non-monotone
    # profile, so it takes precedence once a front has been seeded.
    if prefer_near is not None and np.isfinite(prefer_near):
        return float(min(crossings, key=lambda x: abs(x - prefer_near)))
    # Seed (constraint (a)): prefer the surface-most in-bounds crossing.
    if max_x is not None and np.isfinite(max_x):
        in_bounds = [x for x in crossings if x <= max_x + _SURFACE_EPS]
        if in_bounds:
            return float(in_bounds[-1])
        # No in-bounds crossing — genuine crust front; keep the surface-most.
    return float(crossings[-1])


def _smooth_savgol_contiguous(
    raw: np.ndarray,
    window_samples: int,
    polyorder: int,
) -> np.ndarray:
    """Apply Savitzky-Golay smoothing per contiguous finite run.

    NaN entries pass through unchanged. Each contiguous finite run of
    length >= ``polyorder + 2`` is smoothed independently; shorter runs
    are returned verbatim. Window is forced odd and clipped to run length.
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
            run_end = i
            run_len = run_end - run_start
            if run_len >= polyorder + 2:
                w = min(window_samples, run_len)
                if w % 2 == 0:
                    w -= 1
                if w >= polyorder + 2:
                    out[run_start:run_end] = savgol_filter(
                        raw[run_start:run_end],
                        window_length=w,
                        polyorder=polyorder,
                    )
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def track_isothermal(
    df: pd.DataFrame,
    sample_period_ms: int = 5000,
    sensors: tuple = tuple(SENSOR_LIST),
    sensor_positions_normalised: tuple = tuple(i / 7 for i in range(8)),
    isotherms_C: tuple = DEFAULT_ISOTHERMS_C,
    stride_seconds: float = 30.0,
    smoothing_window_seconds: float = 120.0,
    smoothing_polyorder: int = 2,
    probe_geometry: Optional[dict] = None,
    model: str = "piecewise",
) -> IsothermalAssignment:
    """Track per-temperature isothermal positions over time.

    Algorithm
    ---------
    1. Run :func:`classify` on the FULL bake to obtain the (fixed)
       core_x and surface_x.
    2. Build a stride grid from t=0 to t=bake_end every ``stride_seconds``.
    3. For each stride centre, look up the corresponding df row.
    4. For each target T in ``isotherms_C``, call
       :func:`_find_isotherm_position` to locate the spatial cross.
    5. Apply Savitzky-Golay smoothing per isotherm, on contiguous finite runs.
    6. Compute T_at_fixed_core_t and T_at_fixed_surface_t by spatial
       interpolation of the eight sensors at the fixed positions.
    7. Return an :class:`IsothermalAssignment`.

    Parameters
    ----------
    df:
        Per-curve DataFrame with the canonical T1..T8 sensor columns.
    sample_period_ms:
        Sample period in milliseconds (default 5000, matches Combustion
        firmware).
    sensors:
        Sensor column names; default ``("T1", ..., "T8")``.
    sensor_positions_normalised:
        Normalised positions of each sensor; default uniform [0, 1/7, ..., 1].
    isotherms_C:
        Target isotherm temperatures (C); default ``(60, 80, 100, 110)``.
    stride_seconds:
        Spacing of the stride grid (seconds). Default 30 s.
    smoothing_window_seconds:
        Savitzky-Golay window width (seconds). Default 120 s.
    smoothing_polyorder:
        SavGol polynomial order. Default 2.
    probe_geometry:
        Optional probe geometry override; if provided, overrides
        ``sensor_positions_normalised``.
    model:
        Either ``"piecewise"`` (default) or ``"stefan"`` — passed through
        to :func:`classify`.

    Returns
    -------
    IsothermalAssignment
    """
    period_s = sample_period_ms / 1000.0
    n_rows = len(df)

    if probe_geometry is not None:
        sensor_positions_normalised = tuple(
            probe_geometry["sensor_positions_normalised"]
        )

    # ------------------------------------------------------------------
    # 1) Full-bake classify — gives us fixed core and surface positions.
    # ------------------------------------------------------------------
    if probe_geometry is None:
        probe_geometry_for_classify = lookup_geometry()
    else:
        probe_geometry_for_classify = probe_geometry

    if n_rows == 0:
        # Defensive: empty bake.
        empty = np.array([], dtype=float)
        empty_iso = {T: empty.copy() for T in isotherms_C}
        # Build a degenerate classification so callers can still access the
        # dataclass fields, but bail out on positions.
        return IsothermalAssignment(
            t_grid_s=empty,
            isotherm_temps_C=tuple(isotherms_C),
            isotherm_positions=empty_iso,
            isotherm_positions_raw={T: empty.copy() for T in isotherms_C},
            fixed_core_x=float("nan"),
            fixed_surface_x=float("nan"),
            T_at_fixed_core_t=empty,
            T_at_fixed_surface_t=empty,
            classification=None,  # type: ignore[arg-type]
        )

    classification = classify(
        df,
        sample_period_ms=sample_period_ms,
        probe_geometry=probe_geometry_for_classify,
        model=model,
    )

    # Clamp to the probe domain [0, 1]: the classifier's parabolic vertex
    # may extrapolate past the probe tip when the relaxed-clamp surface
    # places the geometric core outside the probe (low_extrapolated label).
    # For isothermal tracking we need a usable position to interpolate
    # temperature at; clamp to the probe-tip x=0. The original confidence
    # label survives in ``classification.core_assignment.confidence``.
    if classification.core_assignment is not None:
        raw_core_x = float(classification.core_assignment.position_normalised)
        fixed_core_x = float(np.clip(raw_core_x, 0.0, 1.0))
    else:
        fixed_core_x = float("nan")
    if classification.surface_assignment is not None:
        raw_surf_x = float(classification.surface_assignment.position_normalised)
        fixed_surface_x = float(np.clip(raw_surf_x, 0.0, 1.0))
    else:
        # Full-immersion bake — fall back to the highest-x sensor as the
        # nominal "surface end" of the probe (so the diagnostic plot has a
        # reference line). Mark via NaN if user prefers; we use the
        # high-x end of the probe as a sensible default.
        fixed_surface_x = float(max(sensor_positions_normalised))

    # ------------------------------------------------------------------
    # 2) Stride grid.
    # ------------------------------------------------------------------
    bake_duration_s = (n_rows - 1) * period_s
    if bake_duration_s < stride_seconds:
        empty = np.array([], dtype=float)
        empty_iso = {T: empty.copy() for T in isotherms_C}
        return IsothermalAssignment(
            t_grid_s=empty,
            isotherm_temps_C=tuple(isotherms_C),
            isotherm_positions=empty_iso,
            isotherm_positions_raw={T: empty.copy() for T in isotherms_C},
            fixed_core_x=fixed_core_x,
            fixed_surface_x=fixed_surface_x,
            T_at_fixed_core_t=empty,
            T_at_fixed_surface_t=empty,
            classification=classification,
        )
    # fix/deep-review #5: start the grid at t=0 so the opening row is covered,
    # and extend the upper bound by one stride past bake_duration_s so the
    # FINAL sample is always covered (np.arange's half-open stop otherwise drops
    # the last row when bake_duration_s is not an exact multiple of the stride).
    t_grid = np.arange(0.0, bake_duration_s + stride_seconds, stride_seconds)
    # Clamp the final centre to the last sample time so we never index past the
    # bake (the per-stride loop rounds t/period to a row index and clips, but
    # keeping t_grid within the bake keeps the reported times honest).
    if t_grid.size > 0 and t_grid[-1] > bake_duration_s:
        t_grid[-1] = bake_duration_s

    # ------------------------------------------------------------------
    # 3-4) Per-stride isotherm positions.
    # ------------------------------------------------------------------
    pos_arr = np.asarray(sensor_positions_normalised, dtype=float)
    isotherm_raw: dict = {T: np.full(t_grid.size, np.nan, dtype=float) for T in isotherms_C}

    # Pre-fetch sensor columns as numpy for speed.
    sensor_cols_present = [s for s in sensors if s in df.columns]
    if len(sensor_cols_present) < 2:
        empty = np.array([], dtype=float)
        empty_iso = {T: empty.copy() for T in isotherms_C}
        return IsothermalAssignment(
            t_grid_s=t_grid,
            isotherm_temps_C=tuple(isotherms_C),
            isotherm_positions=empty_iso,
            isotherm_positions_raw={T: empty.copy() for T in isotherms_C},
            fixed_core_x=fixed_core_x,
            fixed_surface_x=fixed_surface_x,
            T_at_fixed_core_t=empty,
            T_at_fixed_surface_t=empty,
            classification=classification,
        )
    # Trim positions to whichever sensors are present (defensive).
    sensor_to_pos_idx = {s: i for i, s in enumerate(sensors)}
    used_pos = np.array(
        [pos_arr[sensor_to_pos_idx[s]] for s in sensor_cols_present],
        dtype=float,
    )
    sensor_matrix = df[sensor_cols_present].to_numpy(dtype=float)  # (n_rows, n_sensors)

    # fix/deep-review #2b: enforce (a) no front beyond the inferred surface and
    # (b) front continuity across strides. ``max_x`` clamps to fixed_surface_x;
    # ``prev_pos`` seeds per-isotherm continuity. The FIRST finite stride for an
    # isotherm has no previous position, so it picks the surface-most in-bounds
    # crossing (prefer_near=None); every later finite stride picks the crossing
    # nearest the previous reported position, killing the teleport from the hot
    # probe-tip limb to a grazing surface sensor.
    max_x = float(fixed_surface_x) if np.isfinite(fixed_surface_x) else None
    prev_pos: dict = {T: None for T in isotherms_C}
    for k, t_c in enumerate(t_grid):
        row_idx = int(round(float(t_c) / period_s))
        row_idx = max(0, min(n_rows - 1, row_idx))
        temps_now = sensor_matrix[row_idx, :]
        for T_target in isotherms_C:
            x = _find_isotherm_position(
                used_pos,
                temps_now,
                float(T_target),
                max_x=max_x,
                prefer_near=prev_pos[T_target],
            )
            isotherm_raw[T_target][k] = x
            if np.isfinite(x):
                prev_pos[T_target] = x

    # ------------------------------------------------------------------
    # 5) Per-isotherm Savitzky-Golay smoothing.
    # ------------------------------------------------------------------
    window_samples = max(3, int(round(smoothing_window_seconds / stride_seconds)))
    if window_samples % 2 == 0:
        window_samples += 1
    isotherm_smoothed: dict = {}
    for T_target in isotherms_C:
        smoothed = _smooth_savgol_contiguous(
            isotherm_raw[T_target], window_samples, smoothing_polyorder
        )
        # Clamp smoothed positions to the probe domain [0, 1] — SavGol
        # polynomial fits can overshoot past the boundaries when the raw
        # signal saturates at the probe tip (e.g. 60 C front sitting at
        # x=0 while 80 C is still declining produces edge ringing).
        with np.errstate(invalid="ignore"):
            smoothed = np.where(
                np.isfinite(smoothed),
                np.clip(smoothed, 0.0, 1.0),
                smoothed,
            )
        isotherm_smoothed[T_target] = smoothed

    # ------------------------------------------------------------------
    # 6) T at fixed core/surface — per-stride spatial interpolation.
    # ------------------------------------------------------------------
    # Use the existing helper which already handles the boundary cases.
    if np.isfinite(fixed_core_x):
        T_core_series = interpolate_temperature_series_at(
            df,
            tuple(sensor_positions_normalised),
            float(fixed_core_x),
            sensors=tuple(sensors),
        )
        T_core_arr = T_core_series.to_numpy(dtype=float)
    else:
        T_core_arr = np.full(n_rows, np.nan, dtype=float)
    if np.isfinite(fixed_surface_x):
        T_surf_series = interpolate_temperature_series_at(
            df,
            tuple(sensor_positions_normalised),
            float(fixed_surface_x),
            sensors=tuple(sensors),
        )
        T_surf_arr = T_surf_series.to_numpy(dtype=float)
    else:
        T_surf_arr = np.full(n_rows, np.nan, dtype=float)

    # Sample at stride row indices.
    T_at_fixed_core_t = np.full(t_grid.size, np.nan, dtype=float)
    T_at_fixed_surface_t = np.full(t_grid.size, np.nan, dtype=float)
    for k, t_c in enumerate(t_grid):
        row_idx = int(round(float(t_c) / period_s))
        row_idx = max(0, min(n_rows - 1, row_idx))
        T_at_fixed_core_t[k] = T_core_arr[row_idx]
        T_at_fixed_surface_t[k] = T_surf_arr[row_idx]

    # ------------------------------------------------------------------
    # 7) Pack the assignment.
    # ------------------------------------------------------------------
    return IsothermalAssignment(
        t_grid_s=t_grid,
        isotherm_temps_C=tuple(isotherms_C),
        isotherm_positions=isotherm_smoothed,
        isotherm_positions_raw=isotherm_raw,
        fixed_core_x=fixed_core_x,
        fixed_surface_x=fixed_surface_x,
        T_at_fixed_core_t=T_at_fixed_core_t,
        T_at_fixed_surface_t=T_at_fixed_surface_t,
        classification=classification,
    )
