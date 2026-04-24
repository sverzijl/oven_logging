"""
Thermodynamic-based sensor classification for identifying core, surface, and ambient sensors
without calibration, using heat transfer principles.

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


class ThermodynamicSensorClassifier:
    """Classifies temperature sensors based on thermodynamic properties."""
    
    def __init__(self, df: pd.DataFrame, sensor_columns: List[str]):
        self.df = df
        self.sensor_columns = sensor_columns
        
    def classify_sensors(self) -> Dict[str, List[str]]:
        """
        Classify sensors into core, surface, and ambient based on thermodynamic behavior.
        
        Returns:
            Dictionary mapping role to list of sensor names
        """
        # Calculate thermodynamic features for each sensor
        features = self._calculate_sensor_features()
        
        # Score each sensor based on thermodynamic properties
        scores = self._calculate_thermodynamic_scores(features)
        
        # Classify sensors based on scores
        return self._assign_sensor_roles(scores)
    
    def _calculate_sensor_features(self) -> Dict[str, Dict[str, float]]:
        """Calculate thermodynamic features for each sensor."""
        features = {}
        
        for sensor in self.sensor_columns:
            temp_data = self.df[sensor].dropna()
            if len(temp_data) < 10:
                continue
                
            # Calculate time in minutes from first timestamp
            time_minutes = self.df['TimeMinutes'].values
            
            features[sensor] = {
                # Basic statistics
                'max_temp': temp_data.max(),
                'temp_range': temp_data.max() - temp_data.min(),
                
                # Initial heating characteristics (first 5 minutes)
                'initial_heating_rate': self._calculate_initial_heating_rate(temp_data, time_minutes),
                
                # Response time metrics
                'time_to_50C': self._time_to_temperature(temp_data, time_minutes, 50),
                'time_to_70C': self._time_to_temperature(temp_data, time_minutes, 70),
                
                # Rate of change statistics
                'max_rate_change': self._calculate_max_rate_change(temp_data),
                'rate_change_std': self._calculate_rate_change_variability(temp_data),
                
                # Heat transfer characteristics
                'thermal_lag': self._calculate_thermal_lag(temp_data, time_minutes),
                'response_sharpness': self._calculate_response_sharpness(temp_data),
                
                # Noise/oscillation (surface sensors show moderate noise)
                'signal_noise': self._calculate_signal_noise(temp_data),
            }
            
        return features
    
    def _calculate_initial_heating_rate(self, temp_data: pd.Series, time_minutes: np.ndarray) -> float:
        """Calculate average heating rate in first 5 minutes."""
        mask = time_minutes <= 5.0
        if mask.sum() < 2:
            return 0.0
            
        temps = temp_data.iloc[mask]
        times = time_minutes[mask]
        
        if len(temps) < 2:
            return 0.0
            
        # Linear regression for heating rate
        coeffs = np.polyfit(times, temps, 1)
        return coeffs[0]  # Slope = heating rate in °C/min
    
    def _time_to_temperature(self, temp_data: pd.Series, time_minutes: np.ndarray, target_temp: float) -> float:
        """Calculate time to reach target temperature."""
        mask = temp_data >= target_temp
        if not mask.any():
            return float('inf')
        
        first_idx = mask.idxmax()
        return time_minutes[first_idx]
    
    def _calculate_max_rate_change(self, temp_data: pd.Series) -> float:
        """Calculate maximum single-interval temperature change."""
        diffs = temp_data.diff().abs()
        return diffs.max() if len(diffs) > 0 else 0.0
    
    def _calculate_rate_change_variability(self, temp_data: pd.Series) -> float:
        """Calculate standard deviation of temperature rate changes."""
        diffs = temp_data.diff().dropna()
        return diffs.std() if len(diffs) > 0 else 0.0
    
    def _calculate_thermal_lag(self, temp_data: pd.Series, time_minutes: np.ndarray) -> float:
        """
        Calculate thermal lag by finding inflection point timing.
        Earlier inflection = less thermal mass = surface/ambient.
        """
        if len(temp_data) < 10:
            return 0.0
            
        # Calculate second derivative to find inflection
        first_deriv = temp_data.diff()
        second_deriv = first_deriv.diff().dropna()
        
        # Find maximum acceleration point (heating inflection)
        # Get corresponding time values for valid second derivative indices
        valid_indices = second_deriv.index
        time_subset = time_minutes[valid_indices]
        
        mask = (second_deriv.values > 0) & (time_subset < 10)  # First 10 minutes
        if mask.any():
            # Get the index where second derivative is maximum
            max_idx = np.argmax(second_deriv.values[mask])
            actual_idx = valid_indices[mask][max_idx]
            return time_minutes[actual_idx]
        
        return 10.0  # Default if no clear inflection
    
    def _calculate_response_sharpness(self, temp_data: pd.Series) -> float:
        """
        Calculate how sharply sensor responds to temperature changes.
        Higher value = sharper response = closer to heat source.
        """
        diffs = temp_data.diff().dropna()
        if len(diffs) < 2:
            return 0.0
            
        # Ratio of max change to average change
        avg_change = diffs.abs().mean()
        max_change = diffs.abs().max()
        
        return max_change / avg_change if avg_change > 0 else 0.0
    
    def _calculate_signal_noise(self, temp_data: pd.Series) -> float:
        """
        Calculate high-frequency noise in temperature signal.
        Surface sensors show moderate noise due to convection.
        """
        if len(temp_data) < 10:
            return 0.0
            
        # Apply simple smoothing and calculate residuals
        smoothed = temp_data.rolling(window=3, center=True).mean()
        residuals = (temp_data - smoothed).dropna()
        
        return residuals.std()
    
    def _calculate_thermodynamic_scores(self, features: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        """
        Calculate scores for each sensor being core, surface, or ambient.
        Based on thermodynamic principles of heat transfer.
        """
        scores = {}
        
        for sensor, feat in features.items():
            # Core sensor characteristics:
            # - Slowest heating rate (high thermal mass, insulated)
            # - Longest time to reach temperatures
            # - Lowest max temperature
            # - Smoothest signal (least noise)
            # - Latest thermal lag (inflection point)
            core_score = (
                (1 / (feat['initial_heating_rate'] + 1)) * 30 +  # Inverse heating rate
                min(feat['time_to_50C'] / 10, 1) * 20 +         # Longer time = higher score
                (1 / (feat['max_rate_change'] + 1)) * 15 +      # Lower max change
                (1 / (feat['signal_noise'] + 0.1)) * 10 +       # Less noise
                min(feat['thermal_lag'] / 10, 1) * 15 +         # Later inflection
                (1 / (feat['response_sharpness'] + 1)) * 10     # Gentler response
            )
            
            # Ambient sensor characteristics:
            # - Fastest heating rate (direct oven exposure)
            # - Quickest to reach temperatures
            # - Highest max temperature
            # - Most noise (turbulent convection)
            # - Earliest thermal lag
            # - Sharpest response
            ambient_score = (
                min(feat['initial_heating_rate'] / 20, 1) * 25 +  # High heating rate
                (1 / (feat['time_to_50C'] + 0.1)) * 20 +         # Quick to heat
                min(feat['max_rate_change'] / 10, 1) * 15 +      # High max change
                min(feat['signal_noise'] * 5, 1) * 10 +          # More noise
                (1 / (feat['thermal_lag'] + 1)) * 15 +           # Early inflection
                min(feat['response_sharpness'] / 5, 1) * 15       # Sharp response
            )
            
            # Surface sensor characteristics:
            # - Intermediate heating rate
            # - Moderate time to temperatures
            # - Intermediate max temperature
            # - Moderate noise (some convection effects)
            # - Middle thermal lag
            # Balance between core and ambient
            
            # Surface score rewards intermediate values
            heating_rate_factor = 1 - abs(feat['initial_heating_rate'] - 8) / 8  # Peak at ~8°C/min
            time_factor = 1 - abs(feat['time_to_50C'] - 2.5) / 2.5  # Peak at ~2.5 min
            noise_factor = 1 - abs(feat['signal_noise'] - 0.5) / 0.5  # Moderate noise
            
            surface_score = (
                max(heating_rate_factor, 0) * 30 +
                max(time_factor, 0) * 25 +
                max(noise_factor, 0) * 15 +
                (1 - abs(feat['thermal_lag'] - 3) / 3) * 15 +  # Peak at ~3 min
                (1 - abs(feat['response_sharpness'] - 3) / 3) * 15  # Moderate sharpness
            )
            
            scores[sensor] = {
                'core': core_score,
                'surface': surface_score,
                'ambient': ambient_score
            }
            
        return scores
    
    def _assign_sensor_roles(self, scores: Dict[str, Dict[str, float]]) -> Dict[str, List[str]]:
        """Assign sensors to roles based on thermodynamic scores."""
        # Create list of (sensor, role, score) tuples
        sensor_role_scores = []
        for sensor, role_scores in scores.items():
            for role, score in role_scores.items():
                sensor_role_scores.append((sensor, role, score))
        
        # Sort by score (highest first)
        sensor_role_scores.sort(key=lambda x: x[2], reverse=True)
        
        # Assign sensors to roles
        assignments = {'core': [], 'surface': [], 'ambient': []}
        assigned_sensors = set()
        
        # First pass: assign clear winners
        for sensor, role, score in sensor_role_scores:
            if sensor not in assigned_sensors:
                if len(assignments[role]) < 2:  # Max 2 sensors per role initially
                    assignments[role].append(sensor)
                    assigned_sensors.add(sensor)
        
        # Second pass: assign remaining sensors based on next best score
        for sensor, role, score in sensor_role_scores:
            if sensor not in assigned_sensors:
                # Find which role needs more sensors
                for r in ['surface', 'core', 'ambient']:  # Prioritize surface
                    if len(assignments[r]) < 3:
                        assignments[r].append(sensor)
                        assigned_sensors.add(sensor)
                        break
        
        return assignments