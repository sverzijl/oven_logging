"""Heat-and-cool combined-rank core-sensor identifier (curve-boundary detector helper).

Originally this module hosted a full ``ThermodynamicSensorClassifier`` class
that classified all eight sensors into core/surface/ambient roles via
thermodynamic heuristics. M3a (HMS Royal Sovereign) replaced that role
classifier with the spatial-reconstruction classifier in
``src/data/spatial_reconstruction``; M3b (HMS Bellerophon) deleted the class.
The remaining ``identify_core_sensor_combined_rank`` is a low-level helper
used by ``CurveBoundaryDetector`` (and its tests) to pick the slowest-to-heat-
and-slowest-to-cool sensor inside a candidate window — orthogonal to role
classification.

`identify_core_sensor_combined_rank` has two heat-only fallback conditions,
both surfaced as top-level diagnostic keys:

1. `cool_available=False` — the cool window extends past the end of the
   DataFrame (e.g. lidded bakes whose log is cut off near the peak, or short
   truncated logs such as real_1000BA3C_0946). ``retained_c_at_cool_window``
   is None for every sensor. Added mission 2026-04-23_231637_4ed7fcd1 (Iron Duke).

2. `cool_contamination_detected=True` — the operator pulled the probe out of
   the loaf within the cool window. All sensors drop rapidly together and the
   retained-temperature reading becomes dominated by probe-pull mechanics, not
   bread thermal mass. Detected by a sustained drop rate exceeding
   ``PROBE_REMOVAL_RATE_C_PER_SEC`` for ``PROBE_REMOVAL_CONFIRM_SAMPLES``
   consecutive samples with at least ``PROBE_REMOVAL_MIN_SIMULTANEOUS_SENSORS``
   sensors exceeding the threshold on each sample (min_k=2 per Audacious
   red-cell verdict, mission 2026-04-24_015052_25705c7a).
   Added mission 2026-04-24_015052_25705c7a (HMS Vanguard); tightened by Duncan.

Both conditions trigger the same heat-only branch: ``cool_ranks`` collapse to 1
so the combined score reduces to heat rank alone. Callers should consult both
keys before treating cool-rank results as informed.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple

from config.constants import CORE_DETECTION_CONFIG
from src.data._drop_rate_detection import find_confirmed_multi_sensor_drop


def _detect_probe_removal_in_cool_window(
    df: pd.DataFrame,
    common_peak_idx: int,
    cool_window_samples: int,
    sensor_columns: List[str],
    rate_c_s: float,
    confirm_n: int,
    min_k_sensors: int = 2,
) -> Optional[int]:
    """Return the first index in ``[common_peak_idx, common_peak_idx + cool_window_samples)``
    where at least ``min_k_sensors`` sensors simultaneously show a drop rate at or
    above ``rate_c_s``, confirmed for ``confirm_n`` consecutive samples.

    Physics: the operator pulls the WHOLE probe at once — multiple sensors exit
    the loaf simultaneously so ≥2 sensors drop rapidly on the same sample. A
    single-sensor rate exceedance per sample is characteristic of noise, not
    probe extraction. See curve_boundary_detector._candidate_drop_rate for the
    sibling single-series call site.
    """
    scan_end = min(common_peak_idx + cool_window_samples, len(df))
    timestamps = df["Timestamp"].to_numpy(dtype=float, copy=False)[:scan_end]
    sensor_temps = {
        s: df[s].to_numpy(dtype=float, copy=False)[:scan_end]
        for s in sensor_columns
        if s in df.columns
    }
    return find_confirmed_multi_sensor_drop(
        sensor_temps,
        timestamps,
        first_scan=max(common_peak_idx, 1),
        rate_c_s=rate_c_s,
        confirm_n=confirm_n,
        min_k_sensors=min_k_sensors,
    )


def identify_core_sensor_combined_rank(
    df: pd.DataFrame, sensor_columns: List[str]
) -> Tuple[Optional[str], Dict]:
    """Combined-rank core-sensor detector.

    The true core sensor should be slowest BOTH to heat and to cool.
    Heat rank: time-to-reach HEAT_THRESHOLD_C (longer = slower = rank 1).
    Cool rank: retained temperature at common_peak_idx + COOL_WINDOW_SECONDS,
    where common_peak_idx is the LATEST peak across all sensors (post-oven-exit
    reference, avoiding per-sensor-peak bias toward early-peaking sensors).
    Combined score = heat_rank + cool_rank; lowest wins. Ties broken by heat
    rank (heating is the more reliable signal during an active bake).

    Args:
        df: DataFrame with Timestamp column and sensor columns.
        sensor_columns: list of sensor names to rank (e.g. ['T1'..'T8']).

    Returns:
        (best_sensor_name, diagnostic_dict) where diagnostic_dict is keyed by
        sensor name with heat_rank, cool_rank, combined_score,
        time_to_heat_threshold_s, retained_c_at_cool_window, common_peak_idx.
        best_sensor_name is None when fewer than 2 sensors reach the threshold
        or insufficient samples exist after the common peak.

    Raises:
        ValueError: if Timestamp is not monotonically increasing.
    """
    heat_threshold = CORE_DETECTION_CONFIG["HEAT_THRESHOLD_C"]
    cool_window_s = CORE_DETECTION_CONFIG["COOL_WINDOW_SECONDS"]

    if "Timestamp" not in df.columns:
        raise ValueError("DataFrame must contain a Timestamp column")
    ts = df["Timestamp"].to_numpy()
    if len(ts) >= 2 and not np.all(np.diff(ts) >= 0):
        raise ValueError("Timestamp must be monotonically increasing")

    available = [s for s in sensor_columns if s in df.columns]
    if len(available) < 2:
        return None, {}

    dt = float(np.median(np.diff(ts))) if len(ts) >= 2 else 5.0
    if dt <= 0:
        dt = 5.0
    cool_window_samples = max(1, int(round(cool_window_s / dt)))

    n = len(df)
    n_sensors = len(available)

    # Heat metric: time from df start to first sample reaching heat_threshold.
    # Sensors that never reach the threshold get the worst (largest) value.
    time_to_heat: Dict[str, float] = {}
    for s in available:
        series = df[s]
        reached = series >= heat_threshold
        if reached.any():
            first_idx = int(reached.idxmax())
            time_to_heat[s] = float(ts[first_idx] - ts[0])
        else:
            time_to_heat[s] = float("inf")

    reaching = [s for s in available if np.isfinite(time_to_heat[s])]
    if len(reaching) < 2:
        return None, {}

    # Common post-oven-exit reference.  We want the latest-peaking sensor's
    # COOLDOWN-START index — i.e. the last sample at which it holds its max.
    # Rationale: sampling the cool window inside any sensor's plateau biases
    # the rank toward that sensor (it reads its own peak value rather than
    # retained heat during cooldown).  For synthetic fixtures with wide
    # plateaus this means plateau-end; for real data where the peak is a
    # single point the plateau-end collapses to the peak index itself.
    # Tolerance (within 0.2 °C of max, bounded below by 0) handles the noisy
    # drift seen on real CSVs where sensors hover within a fraction of a
    # degree of their max for multiple samples after the true thermal peak.
    def _latest_at_max_idx(series: pd.Series) -> int:
        arr = series.to_numpy()
        max_val = float(np.nanmax(arr))
        hits = np.flatnonzero(arr >= max_val - 0.05)
        return int(hits[-1]) if len(hits) else int(series.idxmax())

    first_peak_indices = [int(df[s].idxmax()) for s in available]
    latest_sensor_pos = int(np.argmax(first_peak_indices))
    latest_sensor = available[latest_sensor_pos]
    common_peak_idx = _latest_at_max_idx(df[latest_sensor])
    cool_sample_idx = common_peak_idx + cool_window_samples

    # Heat-only fallback: lidded bakes frequently end with the curve cut off
    # just past the common peak (no post-plateau cooldown captured). In that
    # case the cool metric carries no information — fall back to heat rank
    # alone rather than disabling the detector. Heat rank is the primary
    # physics signal during an active bake (see briefing rationale).
    cool_available = cool_sample_idx < n
    if not cool_available:
        cool_sample_idx = min(n - 1, common_peak_idx)

    # Second heat-only fallback: probe-removal contamination. When the operator
    # pulls the probe inside the cool window, the retained-temperature reading
    # reflects probe-pull mechanics rather than bread thermal mass — cool-rank
    # scoring becomes meaningless. Detect by scanning for a sustained drop rate
    # on any sensor inside the cool window.
    probe_removal_idx = _detect_probe_removal_in_cool_window(
        df,
        common_peak_idx=common_peak_idx,
        cool_window_samples=cool_window_samples,
        sensor_columns=available,
        rate_c_s=CORE_DETECTION_CONFIG["PROBE_REMOVAL_RATE_C_PER_SEC"],
        confirm_n=CORE_DETECTION_CONFIG["PROBE_REMOVAL_CONFIRM_SAMPLES"],
        min_k_sensors=CORE_DETECTION_CONFIG["PROBE_REMOVAL_MIN_SIMULTANEOUS_SENSORS"],
    )
    cool_contamination_detected = probe_removal_idx is not None

    retained: Dict[str, float] = {
        s: float(df[s].iloc[cool_sample_idx]) for s in available
    }

    # Heat rank: rank 1 = slowest to reach threshold (largest time_to_heat).
    # Sensors that never reach the threshold share the worst rank (n_sensors).
    def _rank_desc(values: Dict[str, float]) -> Dict[str, int]:
        """Rank sensors by value descending; rank 1 = highest value.

        Ties get the same rank (competition ranking): two sensors tied for
        rank 1 both get rank 1, next gets rank 3.
        """
        sorted_items = sorted(values.items(), key=lambda kv: -kv[1])
        ranks: Dict[str, int] = {}
        prev_val = None
        prev_rank = 0
        for i, (sensor, val) in enumerate(sorted_items, start=1):
            if prev_val is not None and val == prev_val:
                ranks[sensor] = prev_rank
            else:
                ranks[sensor] = i
                prev_rank = i
                prev_val = val
        return ranks

    # For heat rank we rank by time_to_heat (larger = slower = rank 1).
    # Non-reaching sensors (inf) naturally sort first; then we cap them at
    # n_sensors rank so they lose combined scoring, per the briefing contract.
    heat_ranks_raw = _rank_desc(time_to_heat)
    heat_ranks: Dict[str, int] = {}
    for s in available:
        if np.isfinite(time_to_heat[s]):
            heat_ranks[s] = heat_ranks_raw[s]
        else:
            heat_ranks[s] = n_sensors

    # Cool rank by retained temperature (higher = slower cooling = rank 1).
    # Collapse to rank 1 for all sensors (so combined score reduces to heat
    # rank) in either heat-only fallback condition: (a) cool window cut off by
    # EOF; (b) probe-removal contamination inside the cool window.
    cool_informative = cool_available and not cool_contamination_detected
    if cool_informative:
        cool_ranks = _rank_desc(retained)
    else:
        cool_ranks = {s: 1 for s in available}

    diagnostics: Dict[str, Dict] = {
        "cool_available": cool_available,
        "cool_contamination_detected": cool_contamination_detected,
    }
    for s in available:
        heat_t = time_to_heat[s]
        diagnostics[s] = {
            "heat_rank": heat_ranks[s],
            "cool_rank": cool_ranks[s],
            "combined_score": heat_ranks[s] + cool_ranks[s],
            "time_to_heat_threshold_s": heat_t if np.isfinite(heat_t) else None,
            "retained_c_at_cool_window": retained[s] if cool_informative else None,
            "common_peak_idx": common_peak_idx,
        }

    # Lowest combined score wins; break ties by better (lower) heat rank.
    best = min(
        available,
        key=lambda s: (diagnostics[s]["combined_score"], diagnostics[s]["heat_rank"]),
    )
    return best, diagnostics

