"""Core thermal analysis functions for bread baking profiles."""

import pandas as pd
import numpy as np
from scipy import signal
from typing import Dict, List, Tuple, Optional
from config.constants import TEMPERATURE_ZONES, ANALYSIS_PARAMS, SENSOR_NAMES
from src.data.column_helpers import get_core_temperature_column


class ThermalAnalyzer:
    """Analyze thermal profiles for bread baking optimization."""
    
    def __init__(self, data: pd.DataFrame, metadata: Dict, loader=None):
        self.data = data
        self.metadata = metadata
        self.sample_period = metadata.get('sample_period_s', 5.0)
        self.loader = loader

    def _safe_gradient(self, series: pd.Series) -> np.ndarray:
        """Compute np.gradient with a guard for fewer than 2 samples.

        np.gradient requires at least (edge_order + 1) == 2 elements; on
        single-sample or empty bakes it raises ValueError. In that degenerate
        case the heating rate is undefined, so we return zeros of the matching
        length (rate of an instantaneous bake is treated as 0 °C/s).
        """
        arr = np.asarray(series, dtype=float)
        if arr.shape[0] < 2:
            return np.zeros_like(arr)
        return np.gradient(arr, self.sample_period)

    def calculate_heating_rates(self, smooth: bool = True) -> pd.DataFrame:
        """
        Calculate heating rates for all sensors with safeguards for extreme values.
        
        Args:
            smooth: Apply smoothing to reduce noise
            
        Returns:
            DataFrame with heating rates (°C/s)
        """
        rates = pd.DataFrame()
        rates['Timestamp'] = self.data['Timestamp']
        rates['TimeMinutes'] = self.data['TimeMinutes']
        
        # Define reasonable rate limits for bread baking
        MAX_REASONABLE_RATE = 1.0  # 60°C/min - absolute maximum for any sensor

        # Assign the smoothing window once, outside the sensor loop, so the
        # core/surface gradient blocks below still reference a defined name even
        # when no T1..T8 sensor columns exist (#21 — was a NameError).
        window = ANALYSIS_PARAMS['smoothing_window']

        sensors = list(SENSOR_NAMES)

        for sensor in sensors:
            if sensor in self.data.columns:
                # Apply smoothing if requested
                if smooth:
                    temp_smooth = self.data[sensor].rolling(window=window, center=True).mean()
                else:
                    temp_smooth = self.data[sensor]

                # Handle NaN values from rolling mean at edges
                temp_smooth = temp_smooth.bfill().ffill()

                # Calculate derivative (heating rate); guarded for <2 samples (#9)
                rate = self._safe_gradient(temp_smooth)

                # Clip extreme values that are likely sensor errors
                rate = np.clip(rate, -MAX_REASONABLE_RATE, MAX_REASONABLE_RATE)

                rates[f'{sensor}_rate'] = rate
        
        # Calculate zone-specific rates
        # Use new temperature columns if available
        if 'CoreTemperature' in self.data.columns:
            if smooth:
                core_smooth = self.data['CoreTemperature'].rolling(window=window, center=True).mean()
                core_smooth = core_smooth.bfill().ffill()
            else:
                core_smooth = self.data['CoreTemperature']
            core_rate = self._safe_gradient(core_smooth)
            rates['core_rate'] = np.clip(core_rate, -MAX_REASONABLE_RATE, MAX_REASONABLE_RATE)
        else:
            # Fall back using loader if available
            if self.loader:
                core_sensors = self.loader.get_core_sensors()
                core_rate_cols = [f'{s}_rate' for s in core_sensors if f'{s}_rate' in rates.columns]
                if core_rate_cols:
                    rates['core_rate'] = rates[core_rate_cols].mean(axis=1)
            else:
                # Last resort: use traditional sensors
                core_rate_cols = ['T1_rate', 'T2_rate', 'T3_rate', 'T4_rate']
                existing_cols = [col for col in core_rate_cols if col in rates.columns]
                if existing_cols:
                    rates['core_rate'] = rates[existing_cols].mean(axis=1)
            
        if 'SurfaceTemperature' in self.data.columns:
            if smooth:
                surface_smooth = self.data['SurfaceTemperature'].rolling(window=window, center=True).mean()
                surface_smooth = surface_smooth.bfill().ffill()
            else:
                surface_smooth = self.data['SurfaceTemperature']
            surface_rate = self._safe_gradient(surface_smooth)
            rates['surface_rate'] = np.clip(surface_rate, -MAX_REASONABLE_RATE, MAX_REASONABLE_RATE)
        else:
            # Fall back using loader if available
            if self.loader:
                surface_sensors = self.loader.get_surface_sensors()
                surface_rate_cols = [f'{s}_rate' for s in surface_sensors if f'{s}_rate' in rates.columns]
                if surface_rate_cols:
                    rates['surface_rate'] = rates[surface_rate_cols].mean(axis=1)
            else:
                # Last resort: use traditional sensors
                surface_rate_cols = ['T7_rate', 'T8_rate']
                existing_cols = [col for col in surface_rate_cols if col in rates.columns]
                if existing_cols:
                    rates['surface_rate'] = rates[existing_cols].mean(axis=1)
        
        return rates
    
    def calculate_temperature_gradients(self) -> pd.DataFrame:
        """Calculate spatial temperature gradients."""
        gradients = pd.DataFrame()
        gradients['Timestamp'] = self.data['Timestamp']
        gradients['TimeMinutes'] = self.data['TimeMinutes']
        
        # Surface to core gradient
        # Use new temperature columns if available
        if 'SurfaceTemperature' in self.data.columns and 'CoreTemperature' in self.data.columns:
            gradients['surface_core_gradient'] = self.data['SurfaceTemperature'] - self.data['CoreTemperature']
        else:
            # Fall back to old method
            gradients['surface_core_gradient'] = self.data['T8'] - self.data['CoreAverage']
        
        # Radial gradients
        gradients['radial_gradient_1'] = self.data['T8'] - self.data['T1']
        gradients['radial_gradient_2'] = self.data['T7'] - self.data['T3']
        gradients['radial_gradient_3'] = self.data['T6'] - self.data['T4']
        
        # Core uniformity (standard deviation) — T1-T4 are the deep/core sensors
        core_sensors = [s for s in SENSOR_NAMES if s in ('T1', 'T2', 'T3', 'T4')]
        gradients['core_uniformity'] = self.data[core_sensors].std(axis=1)
        
        return gradients
    
    def _identify_temperature_sources(self) -> Dict[str, str]:
        """Identify which columns represent core and surface temperatures."""
        temp_sources = {
            'core': None,
            'surface': None,
            'ambient': None
        }
        
        # First, use standardized column names if available
        if 'CoreTemperature' in self.data.columns:
            temp_sources['core'] = 'CoreTemperature'
        elif 'CoreAverage' in self.data.columns:
            temp_sources['core'] = 'CoreAverage'
        else:
            # Fallback to using loader or traditional sensors
            if self.loader:
                core_sensors = self.loader.get_core_sensors()
                if core_sensors and all(s in self.data.columns for s in core_sensors):
                    # Create a temporary average column
                    temp_sources['core'] = core_sensors[0]  # Use first core sensor
            else:
                # Last resort: use T1
                temp_sources['core'] = 'T1' if 'T1' in self.data.columns else None
        
        if 'SurfaceTemperature' in self.data.columns:
            temp_sources['surface'] = 'SurfaceTemperature'
        else:
            # Fallback to using loader or traditional sensors
            if self.loader:
                surface_sensors = self.loader.get_surface_sensors()
                if surface_sensors and all(s in self.data.columns for s in surface_sensors):
                    temp_sources['surface'] = surface_sensors[0]  # Use first surface sensor
            else:
                # Last resort: use T8
                temp_sources['surface'] = 'T8' if 'T8' in self.data.columns else None
        
        if 'AmbientTemperature' in self.data.columns:
            temp_sources['ambient'] = 'AmbientTemperature'
        
        return temp_sources
    
    def analyze_temperature_zones(self) -> Dict:
        """Analyze time spent in critical temperature zones."""
        zone_analysis = {}
        
        # Identify temperature sources intelligently
        temp_sources = self._identify_temperature_sources()
        
        for zone_name, zone_config in TEMPERATURE_ZONES.items():
            # Determine which temperature to use based on zone type
            zone_type = zone_config.get('name', '')
            if zone_type in ['Crust Formation', 'Maillard Reaction', 'Caramelization']:
                # Surface zones
                temp_col = temp_sources['surface']
            else:
                # Core zones
                temp_col = temp_sources['core']
            
            # Get temperature data
            if temp_col and temp_col in self.data.columns:
                temp_data = self.data[temp_col]
            else:
                # Fallback to core temperature
                temp_col = get_core_temperature_column(self.data)
                temp_data = self.data[temp_col]
            
            # Find when temperature is in zone
            in_zone = (temp_data >= zone_config['min']) & (temp_data <= zone_config['max'])
            
            # Calculate metrics
            time_in_zone = in_zone.sum() * self.sample_period
            
            # Find entry and exit times
            zone_changes = in_zone.astype(int).diff()
            entries = self.data[zone_changes == 1]['TimeMinutes'].tolist()
            exits = self.data[zone_changes == -1]['TimeMinutes'].tolist()
            
            zone_analysis[zone_name] = {
                'name': zone_config['name'],
                'min': zone_config['min'],
                'max': zone_config['max'],
                'duration': time_in_zone / 60.0,
                'percentage': (time_in_zone / (len(self.data) * self.sample_period)) * 100,
                'entry_times': entries,
                'exit_times': exits,
                'temperature_source': temp_col,
                'temperature_type': 'surface' if zone_type in ['Crust Formation', 'Maillard Reaction', 'Caramelization'] else 'core'
            }
        
        return zone_analysis
    
    def calculate_quality_metrics(self) -> Dict:
        """Calculate quality metrics for the baking process."""
        metrics = {}
        
        # Temperature uniformity metrics
        if self.loader:
            core_sensors = self.loader.get_core_sensors()
        else:
            # T1-T4 are the deep/core sensors in a Combustion Inc. 8-sensor probe
            core_sensors = [s for s in SENSOR_NAMES if s in ('T1', 'T2', 'T3', 'T4')]

        # Only use sensors that exist in the data
        available_core = [s for s in core_sensors if s in self.data.columns]

        if not available_core:
            available_core = [
                s for s in SENSOR_NAMES
                if s in ('T1', 'T2', 'T3', 'T4') and s in self.data.columns
            ]
        
        core_data = self.data[available_core]
        
        # Coefficient of variation for core uniformity
        core_std = core_data.std(axis=1)
        core_mean = core_data.mean(axis=1)
        cv = (core_std / core_mean).mean()
        
        metrics['core_uniformity_cv'] = cv
        metrics['core_uniformity_rating'] = self._rate_uniformity(cv)
        
        # Heating consistency - using normalized approach to avoid negative values
        rates = self.calculate_heating_rates()
        
        # Filter out extreme values that might be noise or data errors
        core_rates = rates['core_rate'].copy()
        
        # Remove NaN values
        core_rates = core_rates.dropna()
        
        if len(core_rates) < 10:
            # Not enough data points for meaningful calculation
            metrics['heating_rate_consistency'] = None
        else:
            # Expected heating rate parameters for bread (°C/s)
            EXPECTED_MAX_RATE = 0.1  # 6°C/min is reasonable for bread baking
            EXTREME_RATE_THRESHOLD = 0.5  # 30°C/min - anything above this is likely noise
            
            # Filter out extreme outliers that are likely sensor errors
            # Use IQR method for robust outlier detection
            q1 = core_rates.quantile(0.25)
            q3 = core_rates.quantile(0.75)
            iqr = q3 - q1
            
            # Define outlier bounds (typical 1.5 * IQR, but we'll be more conservative)
            lower_bound = q1 - 3 * iqr
            upper_bound = q3 + 3 * iqr
            
            # Also apply absolute threshold
            upper_bound = min(upper_bound, EXTREME_RATE_THRESHOLD)
            lower_bound = max(lower_bound, -EXTREME_RATE_THRESHOLD)
            
            # Filter rates
            filtered_rates = core_rates[(core_rates >= lower_bound) & (core_rates <= upper_bound)]
            
            if len(filtered_rates) < 10:
                # Too many outliers removed, data might be problematic
                metrics['heating_rate_consistency'] = 0.0
            else:
                # Calculate normalized standard deviation using filtered data
                normalized_std = filtered_rates.std() / EXPECTED_MAX_RATE
                
                # Ensure result is between 0 and 1
                rate_consistency = 1 - min(normalized_std, 1.0)
                rate_consistency = max(0, rate_consistency)  # Ensure non-negative
                
                metrics['heating_rate_consistency'] = rate_consistency
        
        # Maximum core temperature achieved
        # Always use standardized CoreTemperature column
        core_col = 'CoreTemperature'
        if core_col not in self.data.columns:
            # Should not happen with new loader, but graceful fallback
            core_col = 'CoreAverage' if 'CoreAverage' in self.data.columns else available_core[0]
        
        metrics['max_core_temp'] = self.data[core_col].max()
        metrics['final_core_temp'] = self.data[core_col].iloc[-1]
        
        # Time to reach target temperature (93°C)
        target_temp = 93
        reached_target = self.data[self.data[core_col] >= target_temp]
        if not reached_target.empty:
            metrics['time_to_target_minutes'] = reached_target.iloc[0]['TimeMinutes']
        else:
            metrics['time_to_target_minutes'] = None
        
        # Overall quality score
        metrics['quality_score'] = self._calculate_quality_score(metrics)
        
        return metrics
    
    def identify_process_events(self) -> Dict:
        """Identify key events in the baking process."""
        events = {}

        # Nothing to identify on an empty frame.
        if len(self.data) == 0:
            return events

        # Probe insertion (first significant temperature rise)
        core_col = get_core_temperature_column(self.data)
        temp_diff = self.data[core_col].diff()
        insertion_idx = temp_diff[temp_diff > 2].index[0] if any(temp_diff > 2) else self.data.index[0]
        events['probe_insertion'] = {
            'time_minutes': self.data.loc[insertion_idx, 'TimeMinutes'],
            'temperature': self.data.loc[insertion_idx, core_col]
        }

        # Maximum heating rate.
        # idxmax raises on an all-NA series, so only emit this event when at
        # least one valid (non-NaN) core rate exists (#22).
        rates = self.calculate_heating_rates()
        if 'core_rate' in rates.columns and rates['core_rate'].notna().any():
            max_rate_idx = rates['core_rate'].idxmax()
            events['max_heating_rate'] = {
                'time_minutes': rates.loc[max_rate_idx, 'TimeMinutes'],
                'rate': rates.loc[max_rate_idx, 'core_rate'],
                'temperature': self.data.loc[max_rate_idx, core_col]
            }

        # Temperature plateaus (rate near zero)
        plateau_threshold = 0.05  # °C/s
        if 'core_rate' not in rates.columns:
            return events
        plateaus = rates[abs(rates['core_rate']) < plateau_threshold]
        if len(plateaus) > 10:  # Significant plateau
            events['temperature_plateau'] = {
                'start_time': plateaus.iloc[0]['TimeMinutes'],
                'duration_minutes': len(plateaus) * self.sample_period / 60,
                'temperature': self.data.loc[plateaus.index[0], core_col]
            }
        
        return events
    
    def _rate_uniformity(self, cv: float) -> str:
        """Rate temperature uniformity based on coefficient of variation."""
        if cv < 0.02:
            return "Excellent"
        elif cv < 0.05:
            return "Good"
        elif cv < 0.1:
            return "Acceptable"
        else:
            return "Poor"
    
    def _calculate_quality_score(self, metrics: Dict) -> float:
        """Calculate overall quality score (0-100)."""
        score = 100.0
        
        # Deduct for poor uniformity
        cv = metrics['core_uniformity_cv']
        if cv > 0.1:
            score -= 30
        elif cv > 0.05:
            score -= 15
        elif cv > 0.02:
            score -= 5
        
        # Deduct for inconsistent heating
        consistency = metrics.get('heating_rate_consistency')
        if consistency is not None:
            if consistency < 0.7:
                score -= 20
            elif consistency < 0.8:
                score -= 10
            elif consistency < 0.9:
                score -= 5
        else:
            # No heating rate consistency data available
            score -= 10  # Moderate penalty for missing data
        
        # Deduct if target temperature not reached
        if metrics['time_to_target_minutes'] is None:
            score -= 25
        
        return max(0, score)
    
