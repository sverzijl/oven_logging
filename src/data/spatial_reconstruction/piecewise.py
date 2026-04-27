"""Piecewise three-region spatial fit (M2a HMS Indefatigable).

Given a per-sensor terminal-temperature vector ``(x_i, T_i)`` the piecewise
model identifies:

1. **Dough region** — sensors with terminal T in or below the latent-heat
   plateau band (≤ ~100 °C with bounded variance).
2. **Air region** — sensors near the cavity proxy terminal value
   (``OVEN_PROXY_TOLERANCE_C`` of the max).
3. **Lid region (optional)** — sensors plateauing 20–60 °C below the cavity
   proxy.

The dough/air interface is the position with the largest spatial gradient
∂T/∂x along the probe. Through-loaf insertions produce two interfaces (one
near each end with dough in the middle) and the model returns a tuple
``(x_left_interface, x_right_interface)``.

x_core is the position of the coldest dough-side sensor.
"""

from __future__ import annotations

import numpy as np

from config.constants import ROLE_CLASSIFIER_CONFIG  # noqa: E402

from .profile import ProfileFit


def _parabolic_vertex(
    x_arr: np.ndarray, y_arr: np.ndarray, anchor_idx: int
) -> float:
    """3-point parabolic vertex interpolation around ``anchor_idx``.

    Fit a parabola through ``(x_arr[anchor_idx-1..anchor_idx+1],
    y_arr[same])`` and return the x-coordinate of its vertex (max OR min,
    whichever the parabola yields for the anchored extremum).

    Limitations (intentional, documented):
    * Boundary anchors (``anchor_idx == 0`` or ``anchor_idx == len-1``) cannot
      form a 3-point bracket — return ``x_arr[anchor_idx]`` verbatim.
    * Collinear samples (denominator < 1e-12) → degenerate parabola → return
      ``x_arr[anchor_idx]`` verbatim.
    * Offset is clamped to ``[-1, +1]`` (in units of half-step) so badly
      conditioned parabolas cannot extrapolate past the immediate neighbours.
    """
    n = len(x_arr)
    if anchor_idx <= 0 or anchor_idx >= n - 1:
        return float(x_arr[anchor_idx])
    x0, x1, x2 = float(x_arr[anchor_idx - 1]), float(x_arr[anchor_idx]), float(x_arr[anchor_idx + 1])
    y0, y1, y2 = float(y_arr[anchor_idx - 1]), float(y_arr[anchor_idx]), float(y_arr[anchor_idx + 1])
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1e-12:
        return float(x1)
    offset = 0.5 * (y0 - y2) / denom
    if offset > 1.0:
        offset = 1.0
    elif offset < -1.0:
        offset = -1.0
    dx = (x2 - x0) / 2.0
    return float(x1 + offset * dx)


def _crossing_position(
    positions: np.ndarray, temps: np.ndarray, target_temp: float
) -> float | None:
    """Linear interpolation along the spatial axis: return the first ``x``
    where the piecewise-linear T(x) profile crosses ``target_temp`` (going
    upward, low-T to high-T). Returns ``None`` when no crossing exists.

    Walks adjacent (positions, temps) pairs in index order. A bracket exists
    when ``temps[i] <= target_temp <= temps[i+1]`` (strict bound on either
    side) AND the bracket is non-flat (``temps[i] != temps[i+1]``).
    """
    n = len(temps)
    for i in range(n - 1):
        t0 = float(temps[i])
        t1 = float(temps[i + 1])
        if t0 == t1:
            continue
        if t0 <= target_temp <= t1:
            frac = (target_temp - t0) / (t1 - t0)
            return float(positions[i] + frac * (positions[i + 1] - positions[i]))
    return None


def _detect_through_loaf(temps: np.ndarray, jump_min: float) -> bool:
    """Return True if temps shows the symmetric U-shape of through-loaf
    insertion: high-low-high (both ends in air, middle in dough).

    Heuristic: both endpoints exceed the minimum interior temperature by at
    least ``jump_min`` °C. We additionally require the global minimum to be
    in the interior (not at an endpoint).
    """
    if temps.size < 5:
        return False
    interior_min = float(np.min(temps[1:-1]))
    interior_min_idx = int(np.argmin(temps[1:-1])) + 1
    left = float(temps[0])
    right = float(temps[-1])
    # Both endpoints higher than interior min by ≥ jump_min, and the global
    # min is strictly interior.
    if interior_min_idx in (0, len(temps) - 1):
        return False
    return (left - interior_min) >= jump_min and (right - interior_min) >= jump_min


def _interface_position(
    positions: np.ndarray,
    temps: np.ndarray,
    side: str = "single",
    jump_min: float = 15.0,
    plateau_hi: float = 105.0,
) -> float | None:
    """Return the normalised position of the dough/air interface.

    Algorithm:
    1. Mark each sensor as "in dough" (T ≤ plateau_hi) or "in air" (T > plateau_hi).
    2. The interface is the boundary between adjacent dough/air sensors.
    3. Tie-breaking: when multiple boundaries exist, prefer the one with the
       largest temperature jump.
    4. Fallback: if no plateau→air boundary exists (e.g. all sensors above
       plateau or all below), use the largest adjacent jump that exceeds
       ``jump_min``. Returns ``None`` when no jump qualifies.

    ``side`` constrains the scan to a half-probe relative to the interior min.
    """
    n = len(temps)
    if n < 2:
        return None

    if side == "single":
        lo, hi = 0, n - 1
    else:
        interior_argmin = int(np.argmin(temps[1:-1])) + 1 if n > 2 else int(np.argmin(temps))
        if side == "left":
            lo, hi = 0, interior_argmin
        elif side == "right":
            lo, hi = interior_argmin, n - 1
        else:
            return None

    # Collect plateau→air boundaries.
    boundary_candidates: list[tuple[int, float]] = []  # (idx, jump_magnitude)
    for i in range(lo, hi):
        T_lo = float(temps[i])
        T_hi = float(temps[i + 1])
        T_min, T_max = min(T_lo, T_hi), max(T_lo, T_hi)
        if T_min <= plateau_hi and T_max > plateau_hi:
            boundary_candidates.append((i, abs(T_hi - T_lo)))

    if boundary_candidates:
        # Prefer the boundary with the largest temperature jump; for through-
        # loaf "left" scan we additionally prefer the leftmost boundary so
        # the dough region is contiguous around the interior min.
        if side == "left":
            boundary_candidates.sort(key=lambda t: (t[0], -t[1]))
        elif side == "right":
            boundary_candidates.sort(key=lambda t: (-t[0], -t[1]))
        else:
            boundary_candidates.sort(key=lambda t: (-t[1],))
        best_idx = boundary_candidates[0][0]
        # Linear interpolation: the dough/air interface is the continuous
        # position where the spatial T(x) profile crosses ``plateau_hi``.
        T_lo = float(temps[best_idx])
        T_hi = float(temps[best_idx + 1])
        if T_hi != T_lo:
            frac = (plateau_hi - T_lo) / (T_hi - T_lo)
            # Clamp to [0, 1] to keep the crossing within the bracket.
            if frac < 0.0:
                frac = 0.0
            elif frac > 1.0:
                frac = 1.0
            return float(positions[best_idx] + frac * (positions[best_idx + 1] - positions[best_idx]))
        return float((positions[best_idx] + positions[best_idx + 1]) / 2.0)

    # Fallback — largest jump anywhere in the scan range that exceeds jump_min.
    biggest_jump = -np.inf
    best_idx = None
    for i in range(lo, hi):
        diff = abs(float(temps[i + 1]) - float(temps[i]))
        if diff > biggest_jump:
            biggest_jump = diff
            best_idx = i
    if best_idx is None or biggest_jump < jump_min:
        return None

    # Linear interpolation at midpoint temperature of the jump (no plateau_hi
    # bracket available here — use the half-jump value as the crossing target).
    T_lo = float(temps[best_idx])
    T_hi = float(temps[best_idx + 1])
    target = 0.5 * (T_lo + T_hi)
    if T_hi != T_lo:
        frac = (target - T_lo) / (T_hi - T_lo)
        return float(positions[best_idx] + frac * (positions[best_idx + 1] - positions[best_idx]))
    return float((positions[best_idx] + positions[best_idx + 1]) / 2.0)


def _lid_bake_through_loaf_interfaces(
    features: dict,
    sensor_names: list,
    positions: np.ndarray,
) -> tuple[float | None, float | None, list[int]]:
    """Detect through-loaf interfaces in lid-bake (all-plateau) cases.

    When all sensors plateau in the [plat_lo, plat_hi] band, the dough/air
    boundary cannot be inferred from terminal temperature alone. We use the
    heat-up speed signature instead: air-side sensors reach 100 °C
    significantly faster than dough sensors (lower ``time_to_100c_seconds``
    and lower ``xcorr_lag_to_oven_proxy_seconds``).

    Returns ``(x_left, x_right, dough_indices)``. Either x may be ``None``
    when no air-side sensor exists on that end.
    """
    n = len(sensor_names)
    if n < 3:
        return None, None, list(range(n))

    # Build the heat-up-speed score per sensor. Smaller score = more air-like.
    # We use ``time_to_60c_seconds`` because it is well-defined for ALL sensors
    # in a lid bake (unlike ``time_to_100c_seconds`` which is None for sensors
    # that plateau just below 100 °C). 60 °C is well within the conduction
    # rise range and discriminates air-side from dough-side robustly.
    def _score(sensor_idx: int) -> float:
        s = sensor_names[sensor_idx]
        feats = features.get(s, {})
        t60 = feats.get("time_to_60c_seconds")
        if t60 is not None:
            return float(t60)
        # Fallback: time_to_100c if available, else infinity.
        t100 = feats.get("time_to_100c_seconds")
        if t100 is not None:
            return float(t100)
        return float("inf")

    times = [_score(i) for i in range(n)]
    times_arr = np.array(times, dtype=float)
    finite_times = times_arr[np.isfinite(times_arr)]
    if finite_times.size == 0:
        return None, None, list(range(n))

    span = float(np.max(finite_times) - np.min(finite_times))
    if span < 100.0:
        # Cluster too tight — no clear air/dough separation.
        return None, None, list(range(n))

    # Walk inward from each end, accepting a sensor as air-side only when
    # the temperature-time gap between it and the next-inward neighbour is
    # significant. The "gap" is measured as a fraction of the total span:
    # 25% of span is the threshold (calibrated from real lidded fixtures
    # where the smallest air-side-vs-dough-side gap is ~25% of the heat-up
    # time spread).
    gap_threshold = max(0.25 * span, 100.0)

    left_air_count = 0
    for i in range(n - 1):
        # Sensor i is air-side if its score is below sensor i+1's by gap_threshold.
        if times_arr[i + 1] - times_arr[i] >= gap_threshold:
            left_air_count = i + 1
            break
    right_air_count = 0
    for j in range(n - 1, 0, -1):
        # Sensor j is air-side if its score is below sensor j-1's by gap_threshold.
        if times_arr[j - 1] - times_arr[j] >= gap_threshold:
            right_air_count = n - j
            break

    x_left = None
    x_right = None
    if left_air_count > 0 and left_air_count < n:
        # Interface midway between last air sensor and first dough sensor.
        idx_a = left_air_count - 1
        idx_b = left_air_count
        x_left = float((positions[idx_a] + positions[idx_b]) / 2.0)
    if right_air_count > 0 and right_air_count < n:
        idx_a = n - right_air_count - 1
        idx_b = n - right_air_count
        x_right = float((positions[idx_a] + positions[idx_b]) / 2.0)

    dough_indices = [
        i for i in range(n)
        if i >= left_air_count and i < n - right_air_count
    ]

    return x_left, x_right, dough_indices


def fit_piecewise(
    features: dict,
    terminal_temps: dict,
    sensor_positions_normalised: tuple,
) -> ProfileFit:
    """Fit a piecewise three-region profile to per-sensor terminal temperatures.

    Returns a :class:`ProfileFit` with ``model="piecewise"``. ``x_dough_air``
    is either a float (single interface), a 2-tuple (through-loaf), or
    ``None`` (full immersion / all-air).
    """
    cfg = ROLE_CLASSIFIER_CONFIG
    jump_min = float(cfg["MONOTONIC_GRADIENT_MIN_JUMP_C"])
    proxy_tol = float(cfg["OVEN_PROXY_TOLERANCE_C"])
    lid_min_gap = float(cfg["LID_TEMP_BELOW_CAVITY_C"])
    lid_max_gap = float(cfg["LID_TEMP_BELOW_CAVITY_MAX_C"])
    plat_lo = float(cfg["PLATEAU_NEAR_100_LOWER_C"])
    plat_hi = float(cfg["PLATEAU_NEAR_100_UPPER_C"])

    # Sensor list aligned with positions tuple. Sensor names are T1..Tn
    # by construction in ``extract_features``.
    sensor_names = sorted(terminal_temps.keys(), key=lambda s: int(s[1:]))
    if len(sensor_names) != len(sensor_positions_normalised):
        # If sensor count differs from the canonical 8 (e.g. a sensor was
        # dropped), trim positions to match.
        positions = np.array(sensor_positions_normalised[: len(sensor_names)], dtype=float)
    else:
        positions = np.array(sensor_positions_normalised, dtype=float)

    temps = np.array([terminal_temps[s] for s in sensor_names], dtype=float)
    cavity_proxy_T = float(np.max(temps))

    # ------------------------------------------------------------------
    # Lid-bake heuristic: when ALL sensors terminate in the plateau band
    # (no sensor crosses plateau_hi), the dough/air boundary cannot be
    # detected from terminal-T alone. Use heat-up-speed instead.
    # ------------------------------------------------------------------
    all_in_plateau = bool(np.all(temps <= plat_hi + 5.0))
    lid_bake_mode = all_in_plateau and bool(np.max(temps) - np.min(temps) < 10.0)

    # ------------------------------------------------------------------
    # Detect through-loaf insertion.
    # ------------------------------------------------------------------
    is_through_loaf = _detect_through_loaf(temps, jump_min=jump_min)
    lid_through_loaf_dough_idx: list[int] | None = None

    # Use the configured plateau-band upper (105°C) for interface detection.
    # Sensors with terminal T ≤ 105 are in the dough region; > 105 = air.
    # The classifier separately uses ``max_temp`` for the surface pick to
    # capture sensors that kink-and-rise even when their terminal cools back
    # toward plateau (e.g. real_1000BA3C_0946: T6 max=107, terminal=105).
    interface_plateau_hi = plat_hi

    if lid_bake_mode:
        x_left, x_right, dough_idx = _lid_bake_through_loaf_interfaces(
            features, sensor_names, positions
        )
        if x_left is not None and x_right is not None:
            x_dough_air = (x_left, x_right)
            is_through_loaf = True
        elif x_left is not None:
            x_dough_air = float(x_left)
        elif x_right is not None:
            x_dough_air = float(x_right)
        else:
            x_dough_air = None
        lid_through_loaf_dough_idx = dough_idx
    elif is_through_loaf:
        x_left = _interface_position(
            positions, temps, side="left", jump_min=jump_min, plateau_hi=interface_plateau_hi
        )
        x_right = _interface_position(
            positions, temps, side="right", jump_min=jump_min, plateau_hi=interface_plateau_hi
        )
        if x_left is not None and x_right is not None:
            x_dough_air = (x_left, x_right)
        elif x_left is not None:
            x_dough_air = float(x_left)
        elif x_right is not None:
            x_dough_air = float(x_right)
        else:
            x_dough_air = None
    else:
        x_single = _interface_position(
            positions, temps, side="single", jump_min=jump_min, plateau_hi=interface_plateau_hi
        )
        x_dough_air = float(x_single) if x_single is not None else None

    # ------------------------------------------------------------------
    # Identify in-dough sensors (terminal T in plateau band OR below it).
    # ------------------------------------------------------------------
    if lid_through_loaf_dough_idx is not None and len(lid_through_loaf_dough_idx) > 0:
        in_dough_idx = np.array(lid_through_loaf_dough_idx, dtype=int)
    elif x_dough_air is None:
        # No interface — entire probe is in one region. Decide which by
        # comparing terminal temps to the plateau band.
        if np.all(temps <= plat_hi):
            # Full immersion in dough.
            in_dough_idx = np.arange(len(sensor_names))
        else:
            # All-air case — not expected to reach here but degrade gracefully.
            in_dough_idx = np.array([], dtype=int)
    elif isinstance(x_dough_air, tuple):
        # Through-loaf: dough sits between the two interfaces.
        x_lo, x_hi = x_dough_air
        in_dough_idx = np.array(
            [i for i, p in enumerate(positions) if x_lo < p < x_hi], dtype=int
        )
    else:
        # Single interface — dough sensors are those with positions on the
        # plateau-bounded side of the interface (using interface_plateau_hi).
        idx_left = np.flatnonzero(positions < x_dough_air)
        idx_right = np.flatnonzero(positions > x_dough_air)
        if idx_left.size and idx_right.size:
            # Pick the side whose median terminal-T is closer to the plateau
            # band — that's the dough side.
            left_med = float(np.median(temps[idx_left]))
            right_med = float(np.median(temps[idx_right]))
            if left_med <= right_med:
                in_dough_idx = idx_left
            else:
                in_dough_idx = idx_right
        elif idx_left.size:
            in_dough_idx = idx_left
        else:
            in_dough_idx = idx_right

    # ------------------------------------------------------------------
    # x_core: position of the slowest-heating dough sensor — the deepest
    # point in the loaf, which conducts heat last. We use ``time_to_60c_seconds``
    # because it's robust across both unlidded (≤100°C plateau) and lidded
    # (no 100°C crossing) bakes; ``time_to_100c_seconds`` is None for lidded
    # cases and degrades to coldest-terminal as a tertiary fallback.
    # ------------------------------------------------------------------
    if in_dough_idx.size > 0:
        # Score each in-dough sensor by heat-up time (larger = more core-like).
        scores = []
        for i in in_dough_idx:
            s = sensor_names[i]
            feats = features.get(s, {})
            t60 = feats.get("time_to_60c_seconds")
            if t60 is None:
                # Fallback: time_to_100c, else NEGATIVE terminal temp (so
                # coldest-terminal still wins among sensors with no t60).
                t100 = feats.get("time_to_100c_seconds")
                if t100 is None:
                    scores.append(-float(temps[i]))
                else:
                    scores.append(float(t100))
            else:
                scores.append(float(t60))
        scores_arr = np.array(scores, dtype=float)
        slow_local = int(np.argmax(scores_arr))
        core_idx = int(in_dough_idx[slow_local])
        # Parabolic vertex interpolation across the GLOBAL position axis using
        # the contiguous in-dough scores. We pad the per-sensor score array
        # with the in-dough scores at their global indices so that boundary
        # anchors degrade to the discrete sensor pick. Score is well-defined
        # only for in-dough sensors; we set out-of-region scores to -inf so
        # the parabola sees only meaningful neighbours when those neighbours
        # are themselves in-dough — at the boundary of the dough region we
        # fall back to the sensor pick (matches the boundary clause in
        # ``_parabolic_vertex``).
        in_dough_set = set(int(i) for i in in_dough_idx.tolist())
        # If the anchor's immediate neighbours are also in-dough, use them;
        # otherwise return the discrete sensor position.
        if (core_idx - 1) in in_dough_set and (core_idx + 1) in in_dough_set:
            # Build a 3-point local window (positions and scores at
            # core_idx-1, core_idx, core_idx+1).
            local_x = positions[core_idx - 1 : core_idx + 2]
            # Look up scores for these three sensors directly.
            def _score_for(i: int) -> float:
                s = sensor_names[i]
                feats = features.get(s, {})
                t60 = feats.get("time_to_60c_seconds")
                if t60 is None:
                    t100 = feats.get("time_to_100c_seconds")
                    return float(t100) if t100 is not None else -float(temps[i])
                return float(t60)

            local_y = np.array(
                [_score_for(core_idx - 1), _score_for(core_idx), _score_for(core_idx + 1)],
                dtype=float,
            )
            # Anchor at local idx 1 (the centre of the 3-point window).
            x_core = _parabolic_vertex(local_x, local_y, 1)
        else:
            x_core = float(positions[core_idx])
    else:
        x_core = None

    # ------------------------------------------------------------------
    # x_lid: sensor plateauing in the lid window (cavity − [lid_min, lid_max]).
    # We pick the most-lid-like position: the sensor whose terminal T sits
    # furthest below the cavity proxy but still inside the lid window.
    # Lid sensors must NOT be classified as dough (T > 100 °C terminal
    # required to distinguish lid-contact from in-dough plateau).
    # ------------------------------------------------------------------
    lid_candidates = []
    for i, T in enumerate(temps):
        gap = cavity_proxy_T - T
        if (
            lid_min_gap <= gap <= lid_max_gap
            and T > plat_hi  # exclude in-dough plateau
            and i not in set(in_dough_idx.tolist())
        ):
            lid_candidates.append((i, gap))
    if lid_candidates:
        # Prefer largest gap (most lid-like) but break ties by lowest
        # position (closer to one end of the probe).
        lid_candidates.sort(key=lambda t: (-t[1], positions[t[0]]))
        lid_idx = lid_candidates[0][0]
        x_lid = float(positions[lid_idx])
    else:
        x_lid = None

    # ------------------------------------------------------------------
    # Fit-quality diagnostic.
    # ------------------------------------------------------------------
    if in_dough_idx.size > 0:
        residual_sse = float(
            np.sum((temps[in_dough_idx] - np.mean(temps[in_dough_idx])) ** 2)
        )
    else:
        residual_sse = 0.0
    # Air indices = sensors not in the dough region (for ambient classification).
    all_idx = set(range(len(sensor_names)))
    air_indices = sorted(all_idx - set(in_dough_idx.tolist()))
    fit_quality = {
        "residual_sse": residual_sse,
        "n_dough_sensors": int(in_dough_idx.size),
        "is_through_loaf": bool(is_through_loaf),
        "cavity_proxy_T": cavity_proxy_T,
        "in_dough_indices": in_dough_idx.tolist(),
        "air_indices": air_indices,
        "lid_bake_mode": bool(lid_bake_mode),
    }

    return ProfileFit(
        model="piecewise",
        sensor_positions_normalised=tuple(sensor_positions_normalised),
        terminal_temps=dict(terminal_temps),
        x_dough_air=x_dough_air,
        x_core=x_core,
        x_lid=x_lid,
        fit_quality=fit_quality,
    )
