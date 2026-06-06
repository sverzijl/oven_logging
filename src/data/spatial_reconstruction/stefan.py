"""Stefan-physics-constrained spatial fit (M2b HMS Vanguard).

Where the piecewise model (M2a) fits each region's slope independently, the
Stefan model treats the dough/air interface as a moving evaporation front
pinned at exactly T = 100 °C — the latent-heat plateau. The crust slope is
constrained by a single effective thermal-diffusivity coupling parameter
``alpha_crust`` so the air-side rise from 100 °C toward T_cavity is
*physically coupled* rather than arbitrarily fit.

Three regions:

1. **Dough region** (x < x_stefan_front) — T(x) ≤ 100 °C, monotonically
   approaching 100 °C at the front.
2. **Crust/air region** (x_stefan_front ≤ x < x_lid_or_end) — T(x) rises from
   100 °C toward T_cavity following

       T(x) = 100 + (T_cavity - 100) × (1 - exp(-α (x - x_front)))

   where α is fit globally per-curve.
3. **Lid region (optional)** (x ≥ x_lid) — T plateau at T_lid below T_cavity.

Free parameters:
- ``x_stefan_front`` (one or two — through-loaf yields two)
- ``alpha_crust``
- ``T_cavity`` (anchored to ``max(T_i)``)
- ``x_lid``, ``T_lid_plateau`` (optional)

Why fewer parameters than piecewise? Piecewise fits an independent slope per
region and a free plateau temperature. Stefan pins the plateau at 100 °C and
couples the crust slope through one global α. On n=5 real fixtures with 8
sensors each this halves the degrees of freedom and reduces overfit risk —
that's the empirical bet this model makes; the comparison harness in
``comparison.py`` measures whether it pays off.

The output is a :class:`ProfileFit` with ``model="stefan"`` and the same
field semantics as the piecewise variant, so downstream consumers
(``classifier.classify``, the comparison harness) can swap models without
plumbing changes.
"""

from __future__ import annotations

import numpy as np

from config.constants import ROLE_CLASSIFIER_CONFIG  # noqa: E402

from .extrapolation import parabolic_vertex_with_clamp
from .profile import ProfileFit, _heat_up_score


# ---------------------------------------------------------------------------
# Stefan-front candidate detection
# ---------------------------------------------------------------------------


def _find_100c_crossings(
    positions: np.ndarray, temps: np.ndarray
) -> list[float]:
    """Locate every position where the linear-spline through (x_i, T_i)
    crosses T = 100 °C.

    Returns a list of 0, 1 or 2+ crossings (the through-loaf case typically
    yields exactly 2). A sensor sitting *exactly* on 100 °C counts as a
    crossing at that sensor position.
    """
    crossings: list[float] = []
    n = len(temps)
    if n < 2:
        return crossings

    # Detect bracket-crossings between adjacent sensors.
    for i in range(n - 1):
        T_lo = float(temps[i])
        T_hi = float(temps[i + 1])
        x_lo = float(positions[i])
        x_hi = float(positions[i + 1])

        # Exact-on or sign-change bracket.
        if T_lo == 100.0 and T_hi != 100.0:
            crossings.append(x_lo)
            continue
        if T_hi == 100.0 and T_lo != 100.0:
            # Defer: will be picked up at the next iteration's T_lo.
            # We still need to add it once if it's the last sensor.
            if i + 1 == n - 1:
                crossings.append(x_hi)
            continue
        if (T_lo - 100.0) * (T_hi - 100.0) < 0.0:
            # Linear interpolate.
            frac = (100.0 - T_lo) / (T_hi - T_lo)
            crossings.append(x_lo + frac * (x_hi - x_lo))

    # Deduplicate near-duplicates within 1e-6.
    crossings.sort()
    deduped: list[float] = []
    for c in crossings:
        if not deduped or abs(c - deduped[-1]) > 1e-6:
            deduped.append(c)
    return deduped


# ---------------------------------------------------------------------------
# alpha fit on the air side
# ---------------------------------------------------------------------------


def _fit_alpha_crust(
    air_positions: np.ndarray,
    air_temps: np.ndarray,
    x_front: float,
    T_cavity: float,
    side: str = "right",
) -> tuple[float, float]:
    """Fit ``alpha_crust`` to minimise SSE of the Stefan air-region model
    against (air_positions, air_temps).

    Model:
        T(x) = 100 + (T_cavity - 100) × (1 - exp(-α × |x - x_front|))

    ``side="right"`` means air sensors lie at x > x_front (canonical
    insertion); ``side="left"`` means air sensors lie at x < x_front
    (through-loaf left interface).

    Returns (alpha, sse). If alpha cannot be bracketed, returns
    (default_alpha, sse_at_default).
    """
    if air_positions.size == 0 or T_cavity <= 100.0 + 1e-6:
        return (1.0, 0.0)

    if side == "right":
        d = air_positions - x_front
    else:
        d = x_front - air_positions
    # Clip to non-negative — sensors on the wrong side contribute zero rise.
    d = np.clip(d, 0.0, None)

    # Linearise: log((T_cavity - T) / (T_cavity - 100)) = -α × d.
    # → α = -slope of [d → log((T_cavity - T) / (T_cavity - 100))], constrained
    # through origin (slope only, no intercept).
    rng_T = T_cavity - 100.0
    norm_residual = np.clip(T_cavity - air_temps, 1e-3, None) / rng_T
    # Ignore points with effectively zero distance from the front (they are
    # at the pin and don't constrain α).
    mask = d > 1e-6
    if mask.sum() < 1:
        return (1.0, 0.0)
    log_r = np.log(np.clip(norm_residual[mask], 1e-9, 1.0))
    d_eff = d[mask]
    # Constrained-through-origin OLS: alpha = -sum(d * log_r) / sum(d**2).
    denom = float(np.sum(d_eff * d_eff))
    if denom <= 1e-12:
        return (1.0, 0.0)
    alpha = float(-np.sum(d_eff * log_r) / denom)
    # Clamp to sensible range — pathological inputs can produce α≤0.
    alpha = max(alpha, 0.05)
    alpha = min(alpha, 100.0)

    # Compute SSE in temperature space.
    T_pred = 100.0 + rng_T * (1.0 - np.exp(-alpha * d))
    sse = float(np.sum((T_pred - air_temps) ** 2))
    return (alpha, sse)


# ---------------------------------------------------------------------------
# Lid detection — same physics gate as piecewise, but evaluated against the
# Stefan-predicted T_cavity. (Reused config keys.)
# ---------------------------------------------------------------------------


def _detect_lid_index(
    temps: np.ndarray,
    positions: np.ndarray,
    T_cavity: float,
    in_dough_idx: set[int],
    cfg: dict,
) -> int | None:
    """Pick a lid sensor index, mirroring the piecewise rule.

    A sensor is a lid candidate when:
      - terminal T sits in [T_cavity - LID_MAX, T_cavity - LID_MIN]
      - terminal T > plateau_hi (excludes in-dough plateau)
      - it is not flagged as in-dough.
    Tie-breaker: largest gap (most lid-like).
    """
    plat_hi = float(cfg["PLATEAU_NEAR_100_UPPER_C"])
    lid_min = float(cfg["LID_TEMP_BELOW_CAVITY_C"])
    lid_max = float(cfg["LID_TEMP_BELOW_CAVITY_MAX_C"])
    candidates: list[tuple[int, float]] = []
    for i, T in enumerate(temps):
        if i in in_dough_idx:
            continue
        gap = T_cavity - float(T)
        if lid_min <= gap <= lid_max and T > plat_hi:
            candidates.append((i, gap))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (-t[1], positions[t[0]]))
    return int(candidates[0][0])


# ---------------------------------------------------------------------------
# Lid-bake heat-up-speed split (reused from piecewise via duck-typing — but
# kept local to avoid a cross-module private import. The Stefan model only
# needs this for through-loaf lid bakes where every terminal sits in the
# plateau band and the front cannot be located by terminal-T crossings.)
# ---------------------------------------------------------------------------


def _lid_bake_through_loaf(
    features: dict,
    sensor_names: list,
    positions: np.ndarray,
) -> tuple[float | None, float | None, list[int]]:
    """Split a lid-bake (all-plateau) curve by heat-up speed.

    Identical algorithm to piecewise._lid_bake_through_loaf_interfaces — copied
    here rather than imported to keep the Stefan model independent. The
    piecewise version is the source-of-truth; if its scoring rule changes, the
    Stefan version should follow.
    """
    n = len(sensor_names)
    if n < 3:
        return None, None, list(range(n))

    def _score(i: int) -> float:
        s = sensor_names[i]
        feats = features.get(s, {})
        t60 = feats.get("time_to_60c_seconds")
        if t60 is not None:
            return float(t60)
        t100 = feats.get("time_to_100c_seconds")
        if t100 is not None:
            return float(t100)
        return float("inf")

    times = np.array([_score(i) for i in range(n)], dtype=float)
    finite = times[np.isfinite(times)]
    if finite.size == 0:
        return None, None, list(range(n))
    span = float(np.max(finite) - np.min(finite))
    if span < 100.0:
        return None, None, list(range(n))
    gap_threshold = max(0.25 * span, 100.0)

    left_air_count = 0
    for i in range(n - 1):
        if times[i + 1] - times[i] >= gap_threshold:
            left_air_count = i + 1
            break
    right_air_count = 0
    for j in range(n - 1, 0, -1):
        if times[j - 1] - times[j] >= gap_threshold:
            right_air_count = n - j
            break

    x_left = None
    x_right = None
    if 0 < left_air_count < n:
        x_left = float((positions[left_air_count - 1] + positions[left_air_count]) / 2.0)
    if 0 < right_air_count < n:
        x_right = float((positions[n - right_air_count - 1] + positions[n - right_air_count]) / 2.0)

    dough_idx = [
        i for i in range(n)
        if i >= left_air_count and i < n - right_air_count
    ]
    return x_left, x_right, dough_idx


# ---------------------------------------------------------------------------
# Public fit entry point.
# ---------------------------------------------------------------------------


def fit_stefan(
    features: dict,
    terminal_temps: dict,
    sensor_positions_normalised: tuple,
) -> ProfileFit:
    """Fit a Stefan-physics-constrained spatial profile.

    Returns a :class:`ProfileFit` with ``model="stefan"``. The semantics of
    ``x_dough_air``, ``x_core``, ``x_lid`` match the piecewise model so that
    callers (e.g. ``classify``) can swap implementations.
    """
    cfg = ROLE_CLASSIFIER_CONFIG
    plat_hi = float(cfg["PLATEAU_NEAR_100_UPPER_C"])

    sensor_names = sorted(terminal_temps.keys(), key=lambda s: int(s[1:]))
    if len(sensor_names) != len(sensor_positions_normalised):
        positions = np.array(sensor_positions_normalised[: len(sensor_names)], dtype=float)
    else:
        positions = np.array(sensor_positions_normalised, dtype=float)
    temps = np.array([terminal_temps[s] for s in sensor_names], dtype=float)
    n = len(sensor_names)

    # T_cavity anchor — the proxy. The Stefan air-region model converges to
    # this asymptote as α(x − x_front) → ∞.
    T_cavity = float(np.max(temps))

    # ------------------------------------------------------------------
    # Detect "lid bake" mode: every terminal sits in the plateau band and
    # the spread is < 10 °C. In this regime no terminal-T crossing of 100°C
    # is meaningful; we fall back to heat-up-speed splitting.
    # ------------------------------------------------------------------
    all_in_plateau = bool(np.all(temps <= plat_hi + 5.0))
    lid_bake_mode = all_in_plateau and bool(np.max(temps) - np.min(temps) < 10.0)

    crossings = _find_100c_crossings(positions, temps)

    is_through_loaf = False
    x_dough_air: float | tuple | None = None
    in_dough_idx: list[int] = []
    alpha = None
    air_sse = 0.0

    if lid_bake_mode:
        x_left, x_right, dough_idx = _lid_bake_through_loaf(
            features, sensor_names, positions
        )
        if x_left is not None and x_right is not None:
            x_dough_air = (x_left, x_right)
            is_through_loaf = True
        elif x_left is not None:
            x_dough_air = float(x_left)
        elif x_right is not None:
            x_dough_air = float(x_right)
        in_dough_idx = list(dough_idx)
        # alpha undefined in lid-bake mode (all-plateau) — record None.
    elif len(crossings) >= 2:
        # Through-loaf — left & right Stefan fronts.
        x_left = float(crossings[0])
        x_right = float(crossings[-1])
        x_dough_air = (x_left, x_right)
        is_through_loaf = True
        in_dough_idx = [
            i for i, p in enumerate(positions) if x_left < p < x_right
        ]
        air_left_mask = positions <= x_left
        air_right_mask = positions >= x_right
        # Fit alpha jointly on both sides (parameter is symmetric).
        air_pos = np.concatenate([positions[air_left_mask], positions[air_right_mask]])
        air_T = np.concatenate([temps[air_left_mask], temps[air_right_mask]])
        # For the joint fit, |x − front_nearest| is the relevant distance.
        d_left = np.where(air_left_mask, x_left - positions, 0.0)[air_left_mask]
        d_right = np.where(air_right_mask, positions - x_right, 0.0)[air_right_mask]
        d = np.concatenate([d_left, d_right])
        rng_T = T_cavity - 100.0
        if rng_T > 1e-6 and d.size > 0:
            norm_resid = np.clip(T_cavity - air_T, 1e-3, None) / rng_T
            mask = d > 1e-6
            if mask.any():
                log_r = np.log(np.clip(norm_resid[mask], 1e-9, 1.0))
                d_eff = d[mask]
                denom = float(np.sum(d_eff * d_eff))
                if denom > 1e-12:
                    alpha = float(-np.sum(d_eff * log_r) / denom)
                    alpha = float(max(0.05, min(100.0, alpha)))
                    T_pred = 100.0 + rng_T * (1.0 - np.exp(-alpha * d))
                    air_sse = float(np.sum((T_pred - air_T) ** 2))
    elif len(crossings) == 1:
        # Canonical single-interface insertion.
        x_front = float(crossings[0])
        x_dough_air = x_front
        is_through_loaf = False
        # Dough side = sensors at positions ≤ x_front whose terminal ≤ 100°C.
        # Air side = sensors at positions > x_front (or below if temps invert).
        if positions[0] <= x_front:
            in_dough_idx = [
                i for i, p in enumerate(positions) if p <= x_front and temps[i] <= 100.5
            ]
            air_positions = positions[positions > x_front]
            air_temps = temps[positions > x_front]
            alpha, air_sse = _fit_alpha_crust(
                air_positions, air_temps, x_front, T_cavity, side="right"
            )
        else:
            in_dough_idx = [
                i for i, p in enumerate(positions) if p >= x_front and temps[i] <= 100.5
            ]
            air_positions = positions[positions < x_front]
            air_temps = temps[positions < x_front]
            alpha, air_sse = _fit_alpha_crust(
                air_positions, air_temps, x_front, T_cavity, side="left"
            )
    else:
        # No 100°C crossing — full immersion (all temps ≤100) or all-air.
        x_dough_air = None
        if np.all(temps <= plat_hi):
            in_dough_idx = list(range(n))
        else:
            in_dough_idx = []

    # ------------------------------------------------------------------
    # x_core — slowest-heating dough sensor (matches piecewise heuristic).
    # ------------------------------------------------------------------
    if in_dough_idx:
        scores = [
            _heat_up_score(features, sensor_names[i], float(temps[i]))
            for i in in_dough_idx
        ]
        slow_local = int(np.argmax(np.array(scores)))
        core_idx = int(in_dough_idx[slow_local])
        # Parabolic vertex interpolation across in-dough neighbours when both
        # immediate neighbours are themselves in-dough; boundary or single-
        # neighbour cases degrade to the discrete sensor pick (matches the
        # boundary clause in ``extrapolation.parabolic_vertex_with_clamp``).
        in_dough_set = set(in_dough_idx)

        def _score_for(j: int) -> float:
            return _heat_up_score(features, sensor_names[j], float(temps[j]))

        if (core_idx - 1) in in_dough_set and (core_idx + 1) in in_dough_set:
            local_x = positions[core_idx - 1 : core_idx + 2]
            local_y = np.array(
                [_score_for(core_idx - 1), _score_for(core_idx), _score_for(core_idx + 1)],
                dtype=float,
            )
            # Interior (non-relaxed) path = the historic ±1-clamped vertex.
            x_core, _ = parabolic_vertex_with_clamp(
                local_x, local_y, 1, relaxed_clamp_mode=False
            )
        else:
            x_core = float(positions[core_idx])
    else:
        x_core = None

    # ------------------------------------------------------------------
    # x_lid — multi-sensor plateau gated on cavity gap.
    # ------------------------------------------------------------------
    in_dough_set = set(in_dough_idx)
    lid_idx = _detect_lid_index(temps, positions, T_cavity, in_dough_set, cfg)
    x_lid = float(positions[lid_idx]) if lid_idx is not None else None

    # ------------------------------------------------------------------
    # Air-side indices — for the classifier's ambient/surface logic.
    # ------------------------------------------------------------------
    all_idx = set(range(n))
    air_indices = sorted(all_idx - in_dough_set)

    # Residual SSE — total prediction error against the terminal vector.
    # Dough region predicted at min(T_i, 100), air region predicted by
    # Stefan curve, lid sensors unpredicted (excluded).
    residual_sse = float(air_sse)
    if in_dough_idx:
        # Dough is predicted at its mean (the Stefan model is non-committal
        # about the dough-side profile shape — only the front is pinned).
        dough_T = temps[in_dough_idx]
        residual_sse += float(np.sum((dough_T - np.mean(dough_T)) ** 2))

    fit_quality = {
        "residual_sse": residual_sse,
        "alpha_crust": alpha,
        "T_cavity": T_cavity,
        "n_dough_sensors": len(in_dough_idx),
        "is_through_loaf": is_through_loaf,
        "cavity_proxy_T": T_cavity,
        "in_dough_indices": list(in_dough_idx),
        "air_indices": air_indices,
        "lid_bake_mode": bool(lid_bake_mode),
        "n_crossings_100c": len(crossings),
    }

    return ProfileFit(
        model="stefan",
        sensor_positions_normalised=tuple(sensor_positions_normalised),
        terminal_temps=dict(terminal_temps),
        x_dough_air=x_dough_air,
        x_core=x_core,
        x_lid=x_lid,
        fit_quality=fit_quality,
    )
