"""Core thermal analysis functions for bread baking profiles."""

import pandas as pd
import numpy as np
from scipy import signal
from typing import Dict, List, Tuple, Optional
from config.constants import TEMPERATURE_ZONES, ANALYSIS_PARAMS


class ThermalAnalyzer:
    """Analyze thermal profiles for bread baking optimization."""
    
    def __init__(self, data: pd.DataFrame, metadata: Dict):
        self.data = data
        self.metadata = metadata
        self.sample_period = metadata.get('sample_period_s', 5.0)
        
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
        
        sensors = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
        
        for sensor in sensors:
            if sensor in self.data.columns:
                # Apply smoothing if requested
                if smooth:
                    window = ANALYSIS_PARAMS['smoothing_window']
                    temp_smooth = self.data[sensor].rolling(window=window, center=True).mean()
                else:
                    temp_smooth = self.data[sensor]
                
                # Handle NaN values from rolling mean at edges
                temp_smooth = temp_smooth.bfill().ffill()
                
                # Calculate derivative (heating rate)
                rate = np.gradient(temp_smooth, self.sample_period)
                
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
            core_rate = np.gradient(core_smooth, self.sample_period)
            rates['core_rate'] = np.clip(core_rate, -MAX_REASONABLE_RATE, MAX_REASONABLE_RATE)
        else:
            # Fall back to old method
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
            surface_rate = np.gradient(surface_smooth, self.sample_period)
            rates['surface_rate'] = np.clip(surface_rate, -MAX_REASONABLE_RATE, MAX_REASONABLE_RATE)
        else:
            # Fall back to old method
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
        
        # Core uniformity (standard deviation)
        core_sensors = ['T1', 'T2', 'T3', 'T4']
        gradients['core_uniformity'] = self.data[core_sensors].std(axis=1)
        
        return gradients
    
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
                temp_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
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
        core_sensors = ['T1', 'T2', 'T3', 'T4']
        core_data = self.data[core_sensors]
        
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
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
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
        
        # Probe insertion (first significant temperature rise)
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
        temp_diff = self.data[core_col].diff()
        insertion_idx = temp_diff[temp_diff > 2].index[0] if any(temp_diff > 2) else 0
        events['probe_insertion'] = {
            'time_minutes': self.data.loc[insertion_idx, 'TimeMinutes'],
            'temperature': self.data.loc[insertion_idx, core_col]
        }
        
        # Maximum heating rate
        rates = self.calculate_heating_rates()
        max_rate_idx = rates['core_rate'].idxmax()
        events['max_heating_rate'] = {
            'time_minutes': rates.loc[max_rate_idx, 'TimeMinutes'],
            'rate': rates.loc[max_rate_idx, 'core_rate'],
            'temperature': self.data.loc[max_rate_idx, core_col]
        }
        
        # Temperature plateaus (rate near zero)
        plateau_threshold = 0.05  # °C/s
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
        consistency = metrics['heating_rate_consistency']
        if consistency < 0.7:
            score -= 20
        elif consistency < 0.8:
            score -= 10
        elif consistency < 0.9:
            score -= 5
        
        # Deduct if target temperature not reached
        if metrics['time_to_target_minutes'] is None:
            score -= 25
        
        return max(0, score)
    
    def _identify_temperature_sources(self) -> Dict[str, str]:
        """Identify which columns represent core and surface temperatures."""
        # Get all temperature columns
        temp_cols = [col for col in self.data.columns if col.startswith('T') and col[1:].isdigit()]
        virtual_cols = ['VirtualCoreTemperature', 'VirtualSurfaceTemperature', 'VirtualAmbientTemperature']
        
        # Calculate temperature statistics
        temp_stats = {}
        for col in temp_cols + virtual_cols:
            if col in self.data.columns:
                temp_stats[col] = {
                    'max': self.data[col].max(),
                    'mean': self.data[col].mean()
                }
        
        # Identify core temperature (typically 85-105°C max)
        core_col = None
        if 'VirtualCoreTemperature' in self.data.columns:
            core_col = 'VirtualCoreTemperature'
        elif 'CoreTemperature' in self.data.columns:
            core_col = 'CoreTemperature'
        else:
            # Find sensor with max temp in core range
            for col, stats in temp_stats.items():
                if 85 <= stats['max'] <= 105:
                    core_col = col
                    break
            if not core_col:
                core_col = 'CoreAverage'
        
        # Identify surface temperature (typically 105-180°C max)
        surface_col = None
        surface_candidates = []
        
        # Check all columns for surface temperature range
        for col, stats in temp_stats.items():
            if 105 <= stats['max'] <= 180:
                surface_candidates.append((col, stats['max']))
        
        if surface_candidates:
            # Choose the one with highest max temperature
            surface_col = max(surface_candidates, key=lambda x: x[1])[0]
        else:
            # Check if any virtual column has high enough temperature
            if 'VirtualAmbientTemperature' in temp_stats and temp_stats['VirtualAmbientTemperature']['max'] >= 110:
                surface_col = 'VirtualAmbientTemperature'
            elif 'VirtualSurfaceTemperature' in temp_stats and temp_stats['VirtualSurfaceTemperature']['max'] >= 110:
                surface_col = 'VirtualSurfaceTemperature'
            else:
                # Fallback to T8 or T7
                if 'T8' in self.data.columns:
                    surface_col = 'T8'
                elif 'T7' in self.data.columns:
                    surface_col = 'T7'
                else:
                    surface_col = core_col  # Last resort
        
        return {
            'core': core_col,
            'surface': surface_col
        }