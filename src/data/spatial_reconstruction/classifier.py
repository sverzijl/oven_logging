"""End-to-end role classifier (M2a HMS Indefatigable).

``classify(df, sample_period_ms)`` consumes a per-curve DataFrame and returns
a :class:`SpatialAssignment` with per-role positional assignments. The pipe
is:

1. ``profile.extract_features`` — per-sensor feature vectors.
2. ``piecewise.fit_piecewise`` — three-region spatial fit.
3. Map fit positions back to the nearest sensor names.
4. Apply topology constraints (monotonic role ordering along the probe), but
   relax them when the fit reports through-loaf insertion.

Compared with the legacy classifiers in ``surface_sensor_detector.py`` and
``thermodynamic_sensor_classifier.py``, this module:
- Has a *single* per-sensor feature dict (DRY): all role decisions read from
  it; nobody recomputes per-sensor temps inside score functions.
- Reports ``position_normalised`` *and* ``nearest_sensor`` so future UI can
  show a continuous position; today's tests keep using sensor labels.
- Handles the through-loaf case explicitly so ambient assignments at both
  ends of the probe survive topology validation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config.constants import SENSOR_LIST, ROLE_CLASSIFIER_CONFIG  # noqa: E402

from ._lid import select_lid_cluster
from .geometry import lookup_geometry
from .piecewise import fit_piecewise
from .profile import (
    ProfileFit,
    compute_oven_proxy,
    extract_features,
    interpolate_temperature_series_at,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionalAssignment:
    """Per-role positional assignment.

    ``position_normalised`` is the inferred position along the probe in
    [0, 1]; ``nearest_sensor`` is the closest physical T-sensor (used as the
    override anchor and as the discrete label expected by the contract test
    today).
    """

    role: str
    position_normalised: float
    nearest_sensor: str
    temperature_series: pd.Series
    confidence: str = "medium"
    reason: str = ""


@dataclass(frozen=True)
class SpatialAssignment:
    """Result of ``classify``.

    Equality / comparison tests in ``test_role_classifier_unified.py`` use
    attributes ``core``, ``surface``, ``ambient``, ``lid`` *as sensor labels*
    (e.g. ``result.core == "T4"``). To preserve that contract while still
    reporting the richer positional payload, ``__eq__`` and ``__getattribute__``
    are not overridden — instead we expose a ``core`` property below that
    returns the nearest-sensor string. The full ``PositionalAssignment`` is
    available as ``core_assignment`` etc.
    """

    core_assignment: PositionalAssignment
    surface_assignment: Optional[PositionalAssignment]
    ambient_assignments: list  # list[PositionalAssignment]
    lid_assignment: Optional[PositionalAssignment]
    profile_fit: ProfileFit
    firmware_diagnostic: Optional[dict] = None
    model_used: str = "piecewise"

    # ---- shorthand sensor-label accessors (test contract) -------------
    @property
    def core(self) -> Optional[str]:
        return self.core_assignment.nearest_sensor if self.core_assignment else None

    @property
    def surface(self) -> Optional[str]:
        return (
            self.surface_assignment.nearest_sensor
            if self.surface_assignment is not None
            else None
        )

    @property
    def ambient(self) -> list:
        return [a.nearest_sensor for a in self.ambient_assignments]

    @property
    def lid(self) -> Optional[str]:
        return (
            self.lid_assignment.nearest_sensor
            if self.lid_assignment is not None
            else None
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _segment_longest_curve(df: pd.DataFrame) -> pd.DataFrame:
    """When a multi-curve raw CSV is passed in, run CurveBoundaryDetector
    and return the slice corresponding to the longest curve.

    Falls back to returning the original DataFrame on any failure (we
    prefer noisy results to a crash here — the M2a contract is best-effort
    for multi-curve inputs).
    """
    try:
        from src.data.curve_boundary_detector import CurveBoundaryDetector

        # Use a permissive default config — we don't need fine-grained
        # arbitration here, just an approximate per-bake slice.
        try:
            from config.constants import CURVE_DETECTION_CONFIG  # type: ignore

            cfg = CURVE_DETECTION_CONFIG
        except ImportError:
            cfg = {}
        detector = CurveBoundaryDetector(cfg)
        curves = detector.extract_curves(df)
        if not curves:
            return df
        # Pick the curve with the largest (end - start) range. ``data`` key
        # may carry the slice; fall back to manual slice.
        def _curve_len(c):
            try:
                return int(c.get("end_idx", 0)) - int(c.get("start_idx", 0))
            except (ValueError, TypeError, KeyError):
                return 0

        longest = max(curves, key=_curve_len)
        if "data" in longest and isinstance(longest["data"], pd.DataFrame):
            return longest["data"]
        s = int(longest.get("start_idx", 0))
        e = int(longest.get("end_idx", len(df) - 1))
        return df.iloc[s : e + 1].reset_index(drop=True)
    except (ImportError, ValueError, KeyError) as exc:
        # Best-effort: a malformed multi-curve input degrades to the full
        # DataFrame, but we log it (M28 M5) rather than swallowing silently —
        # a silent broad-except previously hid genuine detector bugs.
        logger.warning(
            "_segment_longest_curve fell back to the full DataFrame: %s", exc
        )
        return df


def _nearest_sensor(
    position: float, sensor_positions: tuple, sensor_names: tuple
) -> tuple[str, int]:
    """Return ``(sensor_name, sensor_index)`` whose position is closest."""
    arr = np.array(sensor_positions, dtype=float)
    idx = int(np.argmin(np.abs(arr - position)))
    return sensor_names[idx], idx


def _build_assignment(
    role: str,
    position: float,
    sensor_positions: tuple,
    sensor_names: tuple,
    df: pd.DataFrame,
    confidence: str = "medium",
    reason: str = "",
    nearest_sensor_override: Optional[str] = None,
) -> PositionalAssignment:
    """Build a :class:`PositionalAssignment` at a continuous ``position``.

    ``nearest_sensor_override`` lets callers (e.g. the surface picker) force
    the override-anchor sensor to a specific sensor name even when the
    continuous ``position`` is closer to a different sensor. This preserves
    the discrete-sensor pick for override-UI purposes while still surfacing
    a continuous ``position_normalised`` and a TRUE per-timestep spatial
    interpolation in ``temperature_series``.
    """
    if nearest_sensor_override is not None:
        nearest = nearest_sensor_override
    else:
        nearest, _ = _nearest_sensor(position, sensor_positions, sensor_names)
    # ``temperature_series`` is the TRUE per-timestep spatial interpolation at
    # the continuous ``position``. When ``position`` lands exactly on a
    # sensor, the interpolation degenerates to that sensor's series — so the
    # off-sensor case and the on-sensor case share one code path. The
    # ``nearest_sensor`` field remains the override-anchor contract.
    series = interpolate_temperature_series_at(
        df, sensor_positions, float(position), sensors=sensor_names
    )
    return PositionalAssignment(
        role=role,
        position_normalised=float(position),
        nearest_sensor=nearest,
        temperature_series=series,
        confidence=confidence,
        reason=reason,
    )


def _topology_compatible(
    core_idx: int, surface_idx: Optional[int], lid_idx: Optional[int]
) -> bool:
    """Check that core_idx < surface_idx ≤ lid_idx (or non-existent)."""
    if surface_idx is not None and not (core_idx < surface_idx):
        return False
    if surface_idx is not None and lid_idx is not None and lid_idx < surface_idx:
        return False
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def classify(
    df: pd.DataFrame,
    sample_period_ms: int = 5000,
    probe_geometry: Optional[dict] = None,
    model: str = "piecewise",
) -> SpatialAssignment:
    """Run the full spatial-reconstruction role classifier on ``df``.

    Parameters
    ----------
    df:
        Single-curve DataFrame (or a raw multi-curve CSV — the longest
        curve is auto-segmented in that case).
    sample_period_ms:
        Sample period in milliseconds (default 5000, matches Combustion
        firmware).
    probe_geometry:
        Optional override; defaults to the ``default_uniform`` 8-sensor
        geometry from :func:`spatial_reconstruction.geometry.lookup_geometry`.
    model:
        Currently only ``"piecewise"`` is wired. ``"stefan"`` is reserved
        for M2b HMS Vanguard.

    Returns
    -------
    SpatialAssignment
    """
    if model not in ("piecewise", "stefan"):
        raise ValueError(
            f"Unknown model={model!r}; expected 'piecewise' or 'stefan'"
        )

    cfg = ROLE_CLASSIFIER_CONFIG

    # Auto-segment if the input is a long multi-curve raw CSV.
    seg_threshold = int(cfg.get("MULTI_CURVE_SEGMENT_THRESHOLD_SAMPLES", 500))
    working_df = df
    if len(df) > seg_threshold:
        working_df = _segment_longest_curve(df)

    if probe_geometry is None:
        probe_geometry = lookup_geometry()
    sensor_positions = tuple(probe_geometry["sensor_positions_normalised"])
    sensor_names = SENSOR_LIST

    # Per-sensor feature dict.
    features = extract_features(working_df, sample_period_ms=sample_period_ms)

    # Build terminal-temps vector aligned with sensor positions.
    terminal_temps = {
        s: features.get(s, {}).get("terminal_temp", float("nan")) for s in sensor_names
    }

    # Run the chosen spatial fit.
    if model == "piecewise":
        fit = fit_piecewise(features, terminal_temps, sensor_positions)
    else:
        # Lazy import — keeps the M2a piecewise path independent of stefan.py.
        from .stefan import fit_stefan
        fit = fit_stefan(features, terminal_temps, sensor_positions)

    # ------------------------------------------------------------------
    # Map fit positions to PositionalAssignments + apply topology.
    # ------------------------------------------------------------------
    # Cavity proxy terminal value used for ambient/lid decisions.
    # nan-aware (fix/deep-review #1): a single dead/NaN sensor terminal must NOT
    # make the proxy NaN — that would make every gap (proxy - T) NaN and
    # silently disable all lid/ambient detection. Guard the all-NaN case.
    _terminal_vals = np.array(list(terminal_temps.values()), dtype=float)
    if np.any(np.isfinite(_terminal_vals)):
        proxy_terminal = float(np.nanmax(_terminal_vals))
    else:
        proxy_terminal = float("nan")

    # core_assignment ---------------------------------------------------
    if fit.x_core is not None:
        # M18 HMS Vigilant — Method 1 relaxed-clamp surface: when the
        # piecewise fitter reports ``core_confidence_label='low_extrapolated'``
        # (T1-anchored core whose un-clamped parabolic vertex falls past the
        # probe tip), drop the core PositionalAssignment confidence to
        # ``"low"`` and tag the reason with the explicit extrapolation
        # signature so the UI can label it as such.
        fit_label = fit.fit_quality.get("core_confidence_label", "high")
        if fit_label == "low_extrapolated":
            core_confidence = "low"
            core_reason = (
                f"extrapolated past probe tip: relaxed parabolic clamp places "
                f"core at x={fit.x_core:.4f} (normalised), past T1. Method 1 "
                f"low-confidence label engaged — operator should provide bake "
                f"metadata for high-accuracy geometric core."
            )
        elif fit_label == "medium":
            core_confidence = "medium"
            core_reason = "boundary anchor; relaxed clamp inactive (vertex inside probe)"
        else:
            core_confidence = "high"
            core_reason = "coldest dough-side sensor in piecewise fit"
        core_assignment = _build_assignment(
            role="core",
            position=fit.x_core,
            sensor_positions=sensor_positions,
            sensor_names=sensor_names,
            df=working_df,
            confidence=core_confidence,
            reason=core_reason,
        )
    else:
        # Fall back to the sensor with the lowest terminal temp.
        # nan-aware (fix/deep-review #2): np.argmin over a NaN-containing
        # terminal vector can return the dead sensor's index. Use nanargmin and
        # guard the all-NaN case (no usable core).
        if np.any(np.isfinite(_terminal_vals)):
            cold_idx = int(np.nanargmin(_terminal_vals))
            core_assignment = _build_assignment(
                role="core",
                position=sensor_positions[cold_idx],
                sensor_positions=sensor_positions,
                sensor_names=sensor_names,
                df=working_df,
                confidence="low",
                reason="degraded fallback: coldest terminal temp",
            )
        else:
            core_assignment = None  # type: ignore[assignment]

    if core_assignment is None:
        # All sensors dead — no usable core. Downstream consumers
        # (isothermal.track_isothermal) already guard core_assignment is None.
        core_sensor_idx = 0
    else:
        core_sensor_idx = sensor_names.index(core_assignment.nearest_sensor)

    # surface_assignment ------------------------------------------------
    # Convention (matches fixture annotations across both modes):
    # - Unlidded canonical bake: the surface is the FIRST AIR-SIDE sensor
    #   past the dough/air interface — the sensor that visibly escapes the
    #   100°C plateau (e.g. real_100098DE_1351: T7 reaches 112°C and is
    #   classified as surface).
    # - Lidded / through-loaf bake: the surface is the LAST DOUGH-SIDE
    #   sensor before the interface — the loaf surface itself, which under
    #   a lid plateaus at the same ~98°C as the rest of the dough cluster
    #   (e.g. wonder_white_10k_lidded: T7 sits at the dough/air boundary on
    #   the high-numbered end; T8 is past the surface in cavity air).
    surface_assignment: Optional[PositionalAssignment] = None
    lid_bake_mode = fit.fit_quality.get("lid_bake_mode", False)
    if fit.x_dough_air is not None:
        if isinstance(fit.x_dough_air, tuple):
            # Through-loaf: pick the right-side (high-numbered-end) interface
            # as the canonical surface anchor — matches fixture convention.
            x_left, x_right = fit.x_dough_air
            x_surface = float(x_right)
        else:
            x_surface = float(fit.x_dough_air)

        # Boundary threshold for "free-rising" (air-side) sensors. We use
        # the configured plateau-band upper (105°C) applied to ``max_temp``
        # — surface is the FIRST sensor that visibly rises above the
        # plateau band at any point during the bake. ``max_temp`` is more
        # robust than ``terminal_temp`` because it captures the kink-and-
        # rise signature even when the sensor cools partially before the
        # log ends (e.g. real_1000BA3C_0946: T6 max=107, terminal=105;
        # surface=T6 by max_temp).
        max_plateau = float(cfg["PLATEAU_NEAR_100_UPPER_C"])
        max_temps = {
            s: features.get(s, {}).get("max_temp", float("nan"))
            for s in sensor_names
        }
        positions_arr = np.array(sensor_positions, dtype=float)
        below_mask = positions_arr < x_surface
        above_mask = positions_arr > x_surface
        idx_above_candidates = np.flatnonzero(above_mask)
        idx_below_candidates = np.flatnonzero(below_mask)

        surface_i = None
        if lid_bake_mode:
            # Lid-bake: prefer the dough-side (below) neighbour.
            if idx_below_candidates.size > 0:
                surface_i = int(idx_below_candidates[-1])
        else:
            # Canonical bake: surface = the FIRST sensor (working from dough
            # outward) whose ``max_temp`` clearly escaped the plateau band.
            # Strategy: first check the dough-side neighbour of the interface;
            # if its max_temp escaped, IT is the surface. Otherwise pick the
            # first air-side sensor past the interface that escaped.
            interface_neighbour_dough = (
                int(idx_below_candidates[-1]) if idx_below_candidates.size > 0 else None
            )
            interface_neighbour_air = (
                int(idx_above_candidates[0]) if idx_above_candidates.size > 0 else None
            )

            def _escaped(i: int) -> bool:
                T_max = max_temps.get(sensor_names[i])
                return T_max is not None and np.isfinite(T_max) and T_max > max_plateau

            if interface_neighbour_dough is not None and _escaped(interface_neighbour_dough):
                # The dough-side neighbour kinked-and-rose (real_1000BA3C_0946:
                # T6 max=107). It IS the surface.
                surface_i = interface_neighbour_dough
            else:
                # The dough-side neighbour stayed plateau-bounded; surface =
                # the first air-side sensor past the interface that escaped
                # the plateau.
                air_side_escapees = [
                    i
                    for i, p in enumerate(sensor_positions)
                    if p > x_surface and _escaped(i)
                ]
                if air_side_escapees:
                    surface_i = min(air_side_escapees, key=lambda i: sensor_positions[i])
                elif interface_neighbour_air is not None:
                    surface_i = interface_neighbour_air

        if surface_i is not None:
            # Continuous-position contract: ``position_normalised`` is the
            # CONTINUOUS dough/air interface ``x_surface`` (off-sensor when
            # the spatial T(x) profile crosses 100°C between sensors), while
            # ``nearest_sensor`` retains the discrete sensor pick used by the
            # override UI. This is the substantive win of M6 hot-fix
            # HMS Penelope.
            surface_assignment = _build_assignment(
                role="surface",
                position=float(x_surface),
                sensor_positions=sensor_positions,
                sensor_names=sensor_names,
                df=working_df,
                confidence="high",
                reason=(
                    "dough-side neighbour of interface (lid bake)"
                    if lid_bake_mode
                    else "first air-side sensor past dough/air interface"
                ),
                nearest_sensor_override=sensor_names[surface_i],
            )

    # ambient_assignments ----------------------------------------------
    # Ambient = sensors flagged "air-side" by the spatial fit, minus the
    # surface sensor itself, minus any lid-contact sensor (handled by
    # ``lid_assignment`` below — re-derive lid here so we can exclude it).
    # This works uniformly across:
    #   - canonical insertion: air_indices = sensors past the interface;
    #     surface = first of them (excluded), rest = ambient.
    #   - through-loaf: air_indices = both ends; ambient drawn from both.
    #   - full immersion: air_indices = []; ambient = [].
    plat_hi = float(cfg["PLATEAU_NEAR_100_UPPER_C"])
    lid_min_gap_pre = float(cfg["LID_TEMP_BELOW_CAVITY_C"])
    lid_max_gap_pre = float(cfg["LID_TEMP_BELOW_CAVITY_MAX_C"])
    surface_sensor = surface_assignment.nearest_sensor if surface_assignment else None
    surface_idx_int = (
        sensor_names.index(surface_sensor) if surface_sensor is not None else None
    )
    is_through_loaf = fit.fit_quality.get("is_through_loaf", False)
    air_indices = fit.fit_quality.get("air_indices", [])

    # Pre-pass: identify lid candidates so we can exclude them from ambient.
    # Mirror the lid-detection logic below — only a multi-sensor 15°C
    # cluster counts as a true lid plateau (a single isolated sensor in
    # the lid window is more likely a cooler-ambient sensor that should
    # remain ambient — e.g. real_1000BA3C_0946: T7=131°C, gap=39°C from
    # cavity proxy 170°C, but no peer sensor in the lid window so it is
    # genuinely ambient).
    excluded_for_lid_idx: set[int] = set()
    in_dough_set_pre = set(fit.fit_quality.get("in_dough_indices", []))
    pre_candidates: list[int] = []
    for i in air_indices:
        s = sensor_names[i]
        T = terminal_temps[s]
        if not np.isfinite(T):
            continue
        gap = proxy_terminal - T
        if (
            lid_min_gap_pre <= gap <= lid_max_gap_pre
            and T > plat_hi
            and i not in in_dough_set_pre
            and (surface_idx_int is None or i != surface_idx_int)
        ):
            pre_candidates.append(i)
    best_cluster_pre = select_lid_cluster(
        pre_candidates, sensor_names, terminal_temps
    )
    if best_cluster_pre:
        excluded_for_lid_idx.update(best_cluster_pre)

    ambient_assignments: list = []
    for i in air_indices:
        s = sensor_names[i]
        T = terminal_temps[s]
        if not np.isfinite(T):
            continue
        # Skip the surface sensor itself.
        if surface_sensor is not None and s == surface_sensor:
            continue
        # Skip lid-contact sensors.
        if i in excluded_for_lid_idx:
            continue
        ambient_assignments.append(
            _build_assignment(
                role="ambient",
                position=sensor_positions[i],
                sensor_positions=sensor_positions,
                sensor_names=sensor_names,
                df=working_df,
                confidence="medium",
                reason="air-side sensor identified by spatial fit",
            )
        )

    # lid_assignment ----------------------------------------------------
    # Re-select lid candidate at the classifier level so we can exclude the
    # surface sensor (which may match the lid window in absolute terms when
    # it kinks at 100 °C and rises to a similar plateau as a true lid sensor).
    lid_assignment: Optional[PositionalAssignment] = None
    lid_min_gap = float(cfg["LID_TEMP_BELOW_CAVITY_C"])
    lid_max_gap = float(cfg["LID_TEMP_BELOW_CAVITY_MAX_C"])
    in_dough_set = set(fit.fit_quality.get("in_dough_indices", []))
    surface_idx_for_lid = (
        sensor_names.index(surface_assignment.nearest_sensor)
        if surface_assignment is not None
        else None
    )
    lid_candidates_classifier: list[tuple[int, float]] = []
    for i, s in enumerate(sensor_names):
        T = terminal_temps[s]
        if not np.isfinite(T):
            continue
        gap = proxy_terminal - T
        if not (lid_min_gap <= gap <= lid_max_gap):
            continue
        if T <= plat_hi:
            continue
        if i in in_dough_set:
            continue
        if surface_idx_for_lid is not None and i == surface_idx_for_lid:
            continue
        lid_candidates_classifier.append((i, gap))
    # A genuine lid plateau is multi-sensor: the lid contacts multiple
    # adjacent sensors at similar plateaued temperatures. A single isolated
    # sensor in the lid window is more likely an unlidded ambient sensor
    # cooler than the cavity proxy (e.g. T7=131°C in real_1000BA3C_0946,
    # which is genuinely in the cavity but reads cooler than T8=170°C).
    # Require ≥ 2 candidates with terminal-T within 15°C of each other.
    best_cluster = select_lid_cluster(
        [i for i, _ in lid_candidates_classifier], sensor_names, terminal_temps
    )
    if best_cluster:
        # Pick the lid candidate with the largest gap from cavity (most
        # lid-like) within the densest cluster; tie-break on highest idx.
        chosen = max(
            best_cluster,
            key=lambda i: (
                proxy_terminal - terminal_temps[sensor_names[i]],
                i,
            ),
        )
        lid_assignment = _build_assignment(
            role="lid",
            position=sensor_positions[chosen],
            sensor_positions=sensor_positions,
            sensor_names=sensor_names,
            df=working_df,
            confidence="medium",
            reason=(
                f"terminal T sits {proxy_terminal - terminal_temps[sensor_names[chosen]]:.1f}°C "
                f"below cavity proxy ({len(best_cluster)} sensors in lid plateau)"
            ),
        )

    # ------------------------------------------------------------------
    # Topology repair (only when not through-loaf): if surface_idx <= core_idx,
    # the unconstrained pick crossed roles. Try restricted-candidate retry
    # by picking the smallest-idx sensor strictly greater than core_idx
    # whose terminal T > plateau band.
    # ------------------------------------------------------------------
    if (
        not is_through_loaf
        and surface_assignment is not None
    ):
        s_idx = sensor_names.index(surface_assignment.nearest_sensor)
        if s_idx <= core_sensor_idx:
            # Look for the next-air-side sensor strictly greater than core idx.
            plat_hi_local = float(cfg["PLATEAU_NEAR_100_UPPER_C"])
            for i in range(core_sensor_idx + 1, len(sensor_names)):
                if terminal_temps[sensor_names[i]] > plat_hi_local:
                    surface_assignment = _build_assignment(
                        role="surface",
                        position=sensor_positions[i],
                        sensor_positions=sensor_positions,
                        sensor_names=sensor_names,
                        df=working_df,
                        confidence="medium",
                        reason="topology-repaired: smallest air-side sensor > core",
                    )
                    break

    # Firmware diagnostic — record the firmware mode-pick if columns present.
    firmware_diagnostic = None
    if "VirtualCoreSensor" in working_df.columns:
        try:
            firmware_diagnostic = {
                "VirtualCoreSensor_mode": (
                    working_df["VirtualCoreSensor"].mode().iat[0]
                    if not working_df["VirtualCoreSensor"].mode().empty
                    else None
                ),
            }
        except Exception:
            firmware_diagnostic = None

    return SpatialAssignment(
        core_assignment=core_assignment,
        surface_assignment=surface_assignment,
        ambient_assignments=ambient_assignments,
        lid_assignment=lid_assignment,
        profile_fit=fit,
        firmware_diagnostic=firmware_diagnostic,
        model_used=model,
    )
