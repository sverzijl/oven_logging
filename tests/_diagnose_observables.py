"""HMS Daring — M16 Phase 1 observables diagnostic.

For each of the 7 real-CSV fixtures, extract:
  - Steam-phase detection: contiguous interval in first 10 min where the
    M2a-flagged surface sensor reads in [98, 102] °C with duration >= 60 s.
  - Oven-spring window: bulk dough temperature passing through [50, 65] °C.
  - T_air(t): time series of the M2a-flagged ambient sensor (mean if multiple).
  - h_eff(t): extracted from surface energy balance with literature
    k_dough = 0.5 W/(m·K), smoothed with 60-s moving average.

This is a fast standalone diagnostic (~10-30 s wall-time). Outputs per-fixture
summary statistics + smoothed time-series arrays to
``tests/baselines/observables_diagnostic.json``.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from src.data.spatial_reconstruction.luikov_tin import (  # noqa: E402
    SENSOR_NAMES_DEFAULT,
    SENSOR_POSITIONS_MM_FROM_TIP,
)
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    _segmented_real_fixture,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON_PATH = os.path.join(
    BASE_DIR, "baselines", "observables_diagnostic.json"
)

K_DOUGH_W_MK = 0.5  # literature thermal conductivity (W/m·K)


# ---------------------------------------------------------------------------
# Fixture-specific ambient (M2a-flagged) sensor lookup
# ---------------------------------------------------------------------------

# Per the curve_boundary_cases.py M2a annotations:
# - 100098DE_1351:        ambient = [T8],          surface = T7
# - BA3C_0946:            ambient = [T7, T8],      surface = T6
# - BA3C_1759 (3 bakes):  ambient = [T7, T8],      surface = T6
# - wonder_white_10k:     ambient = [T1, T8],      surface = T7   (through-loaf)
# - post_wonder_meal:     ambient = [T1, T8],      surface = T7   (through-loaf)
#
# For wonder_white and post_wonder_meal the "ambient" T1 is on the OPPOSITE
# side of the loaf to T8 (probe pierces through). For the air-side
# T_air(t) extraction we want only the high-T (oven-side) ambient — T8.
# Otherwise multi-ambient is averaged.
FIXTURE_AMBIENT_SENSORS: dict[str, list[str]] = {
    "BA3C_0946": ["T7", "T8"],
    "BA3C_1759_C0": ["T7", "T8"],
    "BA3C_1759_C1": ["T7", "T8"],
    "BA3C_1759_C2": ["T7", "T8"],
    "100098DE_1351": ["T8"],
    "wonder_white": ["T8"],          # through-loaf: T1 is on other side
    "post_wonder_meal": ["T8"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _moving_average(x: np.ndarray, window_s: float, dt_s: float) -> np.ndarray:
    """Centred moving average; preserves length via reflection padding."""
    n = max(int(round(window_s / max(dt_s, 1e-6))), 1)
    if n <= 1:
        return x.copy()
    pad = n // 2
    xp = np.concatenate([
        x[: min(pad, len(x))][::-1],
        x,
        x[-min(pad, len(x)):][::-1],
    ]) if len(x) >= pad else x.copy()
    kern = np.ones(n) / n
    smoothed_full = np.convolve(xp, kern, mode="same")
    if len(x) >= pad:
        return smoothed_full[pad : pad + len(x)]
    return smoothed_full[: len(x)]


def _extract_steam_phase(
    surface_T_C: np.ndarray,
    t_s: np.ndarray,
    band_lo: float = 98.0,
    band_hi: float = 102.0,
    window_s: float = 600.0,
    min_duration_s: float = 60.0,
) -> dict:
    """Find the longest contiguous interval in the first ``window_s`` seconds
    where surface sensor reads in [band_lo, band_hi] °C.
    """
    mask_window = t_s <= window_s
    if not mask_window.any():
        return {
            "steam_detected": False,
            "steam_start_s": float("nan"),
            "steam_end_s": float("nan"),
            "steam_duration_s": 0.0,
        }
    t_w = t_s[mask_window]
    T_w = surface_T_C[mask_window]
    in_band = (T_w >= band_lo) & (T_w <= band_hi)
    if not in_band.any():
        return {
            "steam_detected": False,
            "steam_start_s": float("nan"),
            "steam_end_s": float("nan"),
            "steam_duration_s": 0.0,
        }

    # Find longest contiguous True run
    runs: list[tuple[int, int]] = []
    in_run = False
    run_start = 0
    for i, b in enumerate(in_band):
        if b and not in_run:
            in_run = True
            run_start = i
        elif not b and in_run:
            in_run = False
            runs.append((run_start, i - 1))
    if in_run:
        runs.append((run_start, len(in_band) - 1))

    if not runs:
        return {
            "steam_detected": False,
            "steam_start_s": float("nan"),
            "steam_end_s": float("nan"),
            "steam_duration_s": 0.0,
        }
    # Longest run
    run = max(runs, key=lambda r: r[1] - r[0])
    s_start = float(t_w[run[0]])
    s_end = float(t_w[run[1]])
    duration = s_end - s_start
    return {
        "steam_detected": bool(duration >= min_duration_s),
        "steam_start_s": s_start,
        "steam_end_s": s_end,
        "steam_duration_s": duration,
    }


def _extract_spring_window(
    bulk_T_C: np.ndarray,
    t_s: np.ndarray,
    lower_C: float = 50.0,
    upper_C: float = 65.0,
) -> dict:
    """Find the time window where bulk dough temperature passes [50, 65] °C.

    Returns the first time `T_bulk >= lower_C` (spring_start) and the first
    time `T_bulk >= upper_C` (spring_end). If never reached, returns NaN.
    """
    above_lo_idx = np.where(bulk_T_C >= lower_C)[0]
    above_hi_idx = np.where(bulk_T_C >= upper_C)[0]
    if above_lo_idx.size == 0:
        spring_start = float("nan")
    else:
        spring_start = float(t_s[above_lo_idx[0]])
    if above_hi_idx.size == 0:
        spring_end = float("nan")
    else:
        spring_end = float(t_s[above_hi_idx[0]])
    return {
        "spring_start_s": spring_start,
        "spring_end_s": spring_end,
        "spring_detected": bool(np.isfinite(spring_start) and np.isfinite(spring_end)),
    }


def _extract_T_air(
    df: pd.DataFrame,
    ambient_sensors: list[str],
) -> np.ndarray:
    """Mean of M2a-flagged ambient sensor temperature columns, in °C."""
    cols = [df[s].to_numpy(dtype=float) for s in ambient_sensors if s in df.columns]
    if not cols:
        return np.full(len(df), float("nan"))
    return np.mean(np.column_stack(cols), axis=1)


def _extract_h_eff(
    surface_T_C: np.ndarray,
    next_T_C: np.ndarray,
    air_T_C: np.ndarray,
    depth_surface_m: float,
    depth_next_m: float,
    t_s: np.ndarray,
    smoothing_s: float = 60.0,
) -> tuple[np.ndarray, dict]:
    """Extract h_eff(t) from surface energy balance.

    q_into_dough(t) ≈ -k_dough · (T_surface(t) - T_next(t)) / (depth_next - depth_surface)
    h_eff(t) ≈ q_into_dough(t) / (T_air(t) - T_surface(t))

    Smooth with a 60-s moving average. Mask out samples where the temperature
    difference (T_air - T_surface) is below 5 K (denominator too small).
    """
    if abs(depth_next_m - depth_surface_m) < 1e-6:
        h_eff = np.full_like(surface_T_C, float("nan"))
        return h_eff, {"h_eff_median": float("nan"), "h_eff_iqr": float("nan")}

    dT_into_dough = surface_T_C - next_T_C  # °C; usually positive once heat enters
    dx = depth_next_m - depth_surface_m
    q_into_dough = -K_DOUGH_W_MK * (next_T_C - surface_T_C) / dx
    # That is q = -k * (T_next - T_surf)/dx (heat from surface inward).
    # Equivalently +k*(T_surf - T_next)/dx when T_surf > T_next. W/m².

    dT_air = air_T_C - surface_T_C
    h_eff_raw = np.full_like(surface_T_C, float("nan"))
    valid = (dT_air > 5.0) & np.isfinite(q_into_dough) & np.isfinite(dT_air)
    h_eff_raw[valid] = q_into_dough[valid] / dT_air[valid]

    # Replace inf/extreme values
    h_eff_raw = np.where(np.isfinite(h_eff_raw), h_eff_raw, np.nan)
    # Smoothing only on valid region
    finite_mask = np.isfinite(h_eff_raw)
    if finite_mask.sum() < 3:
        return h_eff_raw, {"h_eff_median": float("nan"), "h_eff_iqr": float("nan")}

    # Compute a sample period
    if len(t_s) < 2:
        dt = 5.0
    else:
        dt = float(np.median(np.diff(t_s)))

    # Smooth: linear-interpolate over NaN gaps, then moving average, then re-mask
    # the originally-invalid samples to NaN.
    idx = np.arange(len(h_eff_raw))
    h_filled = np.interp(idx, idx[finite_mask], h_eff_raw[finite_mask])
    h_smoothed = _moving_average(h_filled, smoothing_s, dt)
    h_smoothed = np.where(finite_mask, h_smoothed, np.nan)

    finite_smoothed = h_smoothed[np.isfinite(h_smoothed)]
    if finite_smoothed.size > 0:
        # Clip to physical range [0, 500] W/m²·K to suppress noise spikes
        # at the very start where dT_air is small.
        finite_smoothed = finite_smoothed[(finite_smoothed >= 0) & (finite_smoothed <= 500.0)]
    if finite_smoothed.size == 0:
        return h_smoothed, {"h_eff_median": float("nan"), "h_eff_iqr": float("nan")}

    stats = {
        "h_eff_median": float(np.median(finite_smoothed)),
        "h_eff_iqr": float(
            np.subtract(*np.percentile(finite_smoothed, [75, 25]))
        ),
        "h_eff_p10": float(np.percentile(finite_smoothed, 10)),
        "h_eff_p90": float(np.percentile(finite_smoothed, 90)),
    }
    return h_smoothed, stats


# ---------------------------------------------------------------------------
# Per-fixture diagnostic
# ---------------------------------------------------------------------------


def diagnose_fixture(spec: dict) -> dict:
    """Run the diagnostic phase on a single fixture spec."""
    label = spec["label"]
    df = _segmented_real_fixture(spec)
    t_s = df["Timestamp"].to_numpy(dtype=float)

    # Surface sensor (M2a-flagged)
    surface_sensor = spec["surface"]
    if surface_sensor not in df.columns:
        return {
            "label": label,
            "error": f"surface sensor {surface_sensor} not in df columns",
        }
    surface_T_C = df[surface_sensor].to_numpy(dtype=float)

    # Next-deeper sensor: the deepest in_dough sensor
    in_dough = list(spec["in_dough"])
    # Find which probe sensor index corresponds to surface.
    surface_idx = SENSOR_NAMES_DEFAULT.index(surface_sensor)
    # The "next deeper" sensor is the in-dough sensor closest to surface
    # (the one with highest probe index that is still in dough).
    in_dough_indices = sorted(
        [SENSOR_NAMES_DEFAULT.index(s) for s in in_dough]
    )
    if not in_dough_indices:
        return {"label": label, "error": "no in_dough sensors"}
    # Pick the in-dough sensor with the highest index < surface_idx
    candidates = [i for i in in_dough_indices if i < surface_idx]
    if not candidates:
        return {"label": label, "error": "no in_dough sensor below surface"}
    next_idx = max(candidates)
    next_sensor = SENSOR_NAMES_DEFAULT[next_idx]
    next_T_C = df[next_sensor].to_numpy(dtype=float)

    # Probe-frame depth offsets (mm from tip)
    p_mm = np.asarray(SENSOR_POSITIONS_MM_FROM_TIP, dtype=float)
    # Loaf-frame depth: d_i = D - (i-1)*13.571.
    # We don't know D, but we know the SPACING between two sensors in
    # the loaf is exactly the same as the spacing between them on the probe
    # (sensors are co-linear). So depth_surface - depth_next = -(p_surface - p_next),
    # i.e., the deeper-in-loaf sensor has smaller p (closer to tip).
    # depth_next - depth_surface = p_surface - p_next > 0 if next is deeper
    depth_diff_mm = p_mm[surface_idx] - p_mm[next_idx]
    # We pass relative depths into _extract_h_eff — only the difference matters.
    depth_surface_m = 0.0
    depth_next_m = depth_diff_mm / 1000.0  # next is deeper by this much (m)

    # Bulk dough = mean of in-dough sensors
    bulk_cols = [df[s].to_numpy(dtype=float) for s in in_dough]
    bulk_T_C = np.mean(np.column_stack(bulk_cols), axis=1)

    # T_air from M2a-flagged ambient sensors
    ambient_sensors = FIXTURE_AMBIENT_SENSORS.get(label, [])
    if not ambient_sensors:
        return {"label": label, "error": "no ambient sensors mapped"}
    available = [s for s in ambient_sensors if s in df.columns]
    if not available:
        return {"label": label, "error": "no ambient columns in df"}
    air_T_C = _extract_T_air(df, available)

    # Phase extractions
    steam = _extract_steam_phase(surface_T_C, t_s)
    spring = _extract_spring_window(bulk_T_C, t_s)
    h_eff_t, h_stats = _extract_h_eff(
        surface_T_C, next_T_C, air_T_C,
        depth_surface_m, depth_next_m, t_s,
    )

    # Air-temperature stats
    air_finite = air_T_C[np.isfinite(air_T_C)]
    air_stats = {
        "T_air_min_C": float(np.min(air_finite)) if air_finite.size else float("nan"),
        "T_air_max_C": float(np.max(air_finite)) if air_finite.size else float("nan"),
        "T_air_median_C": float(np.median(air_finite)) if air_finite.size else float("nan"),
    }

    return {
        "label": label,
        "surface_sensor": surface_sensor,
        "next_sensor": next_sensor,
        "ambient_sensors": ambient_sensors,
        "n_t": int(len(t_s)),
        "dt_s": float(np.median(np.diff(t_s))) if len(t_s) > 1 else 5.0,
        "depth_diff_mm": float(depth_diff_mm),
        # Phase 1 deliverables
        **steam,
        **spring,
        **air_stats,
        **h_stats,
        # Time-series arrays (compact representation)
        "t_grid_s": t_s.tolist(),
        "T_air_K_t": (air_T_C + 273.15).tolist(),
        "T_surface_K_t": (surface_T_C + 273.15).tolist(),
        "T_bulk_K_t": (bulk_T_C + 273.15).tolist(),
        "h_eff_t": [float(v) if np.isfinite(v) else None for v in h_eff_t],
    }


def main() -> None:
    overall_t0 = time.time()
    print(f"=== M16 Phase 1 — observables diagnostic ({len(REAL_FIXTURES)} fixtures) ===")
    out: dict = {
        "mission": "HMS Daring M16 — Phase 1 observables diagnostic",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fixtures": {},
    }

    for spec in REAL_FIXTURES:
        t0 = time.time()
        try:
            d = diagnose_fixture(spec)
            elapsed = time.time() - t0
            out["fixtures"][spec["label"]] = d
            if "error" in d:
                print(f"  {spec['label']:>20}: ERROR {d['error']}  ({elapsed:.1f}s)")
            else:
                steam_str = (
                    f"steam {d['steam_start_s']:.0f}-{d['steam_end_s']:.0f}s "
                    f"({d['steam_duration_s']:.0f}s)"
                    if d["steam_detected"]
                    else "no-steam"
                )
                spring_str = (
                    f"spring {d['spring_start_s']:.0f}-{d['spring_end_s']:.0f}s"
                    if d["spring_detected"]
                    else "no-spring"
                )
                print(
                    f"  {spec['label']:>20}: "
                    f"{steam_str:>30}  {spring_str:>26}  "
                    f"T_air [{d['T_air_min_C']:.0f}-{d['T_air_max_C']:.0f}]°C  "
                    f"h_eff med={d['h_eff_median']:.1f} W/m²·K  "
                    f"({elapsed:.1f}s)"
                )
        except Exception as exc:
            elapsed = time.time() - t0
            out["fixtures"][spec["label"]] = {
                "label": spec["label"], "error": str(exc),
            }
            print(f"  {spec['label']:>20}: ERROR {exc}  ({elapsed:.1f}s)")

    out["wall_seconds"] = time.time() - overall_t0
    os.makedirs(os.path.dirname(OUT_JSON_PATH), exist_ok=True)
    with open(OUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\n  total wall-time: {out['wall_seconds']:.1f}s")
    print(f"  wrote {OUT_JSON_PATH}")


if __name__ == "__main__":
    main()
