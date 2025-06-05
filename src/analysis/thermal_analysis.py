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
        Calculate heating rates for all sensors.
        
        Args:
            smooth: Apply smoothing to reduce noise
            
        Returns:
            DataFrame with heating rates (°C/s)
        """
        rates = pd.DataFrame()
        rates['Timestamp'] = self.data['Timestamp']
        rates['TimeMinutes'] = self.data['TimeMinutes']
        
        sensors = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
        
        for sensor in sensors:
            if sensor in self.data.columns:
                # Apply smoothing if requested
                if smooth:
                    window = ANALYSIS_PARAMS['smoothing_window']
                    temp_smooth = self.data[sensor].rolling(window=window, center=True).mean()
                else:
                    temp_smooth = self.data[sensor]
                
                # Calculate derivative (heating rate)
                rate = np.gradient(temp_smooth, self.sample_period)
                rates[f'{sensor}_rate'] = rate
        
        # Calculate zone-specific rates
        # Use new temperature columns if available
        if 'CoreTemperature' in self.data.columns:
            if smooth:
                core_smooth = self.data['CoreTemperature'].rolling(window=window, center=True).mean()
            else:
                core_smooth = self.data['CoreTemperature']
            rates['core_rate'] = np.gradient(core_smooth, self.sample_period)
        else:
            # Fall back to old method
            rates['core_rate'] = rates[['T1_rate', 'T2_rate', 'T3_rate', 'T4_rate']].mean(axis=1)
            
        if 'SurfaceTemperature' in self.data.columns:
            if smooth:
                surface_smooth = self.data['SurfaceTemperature'].rolling(window=window, center=True).mean()
            else:
                surface_smooth = self.data['SurfaceTemperature']
            rates['surface_rate'] = np.gradient(surface_smooth, self.sample_period)
        else:
            # Fall back to old method
            rates['surface_rate'] = rates[['T7_rate', 'T8_rate']].mean(axis=1)
        
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
        
        # Use core temperature for zone analysis
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
        core_temp = self.data[core_col]
        
        for zone_name, zone_config in TEMPERATURE_ZONES.items():
            # Find when temperature is in zone
            in_zone = (core_temp >= zone_config['min']) & (core_temp <= zone_config['max'])
            
            # Calculate metrics
            time_in_zone = in_zone.sum() * self.sample_period
            
            # Find entry and exit times
            zone_changes = in_zone.astype(int).diff()
            entries = self.data[zone_changes == 1]['TimeMinutes'].tolist()
            exits = self.data[zone_changes == -1]['TimeMinutes'].tolist()
            
            zone_analysis[zone_name] = {
                'total_time_seconds': time_in_zone,
                'total_time_minutes': time_in_zone / 60.0,
                'percentage_of_bake': (time_in_zone / (len(self.data) * self.sample_period)) * 100,
                'entry_times': entries,
                'exit_times': exits,
                'temperature_range': f"{zone_config['min']}-{zone_config['max']}°C"
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
        
        # Heating consistency
        rates = self.calculate_heating_rates()
        rate_consistency = 1 - (rates['core_rate'].std() / rates['core_rate'].mean())
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
            'temperature': self.data.loc[max_rate_idx, 'CoreAverage']
        }
        
        # Temperature plateaus (rate near zero)
        plateau_threshold = 0.05  # °C/s
        plateaus = rates[abs(rates['core_rate']) < plateau_threshold]
        if len(plateaus) > 10:  # Significant plateau
            events['temperature_plateau'] = {
                'start_time': plateaus.iloc[0]['TimeMinutes'],
                'duration_minutes': len(plateaus) * self.sample_period / 60,
                'temperature': self.data.loc[plateaus.index[0], 'CoreAverage']
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