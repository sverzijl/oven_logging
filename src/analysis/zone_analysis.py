"""Temperature zone analysis for bread baking optimization."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from config.constants import TEMPERATURE_ZONES


class ZoneAnalyzer:
    """Analyze time and behavior in critical temperature zones."""
    
    def __init__(self, data: pd.DataFrame, sample_period: float):
        self.data = data
        self.sample_period = sample_period
        
    def get_zone_profiles(self) -> Dict:
        """Get detailed temperature profiles for each zone."""
        zone_profiles = {}
        
        for zone_name, zone_config in TEMPERATURE_ZONES.items():
            zone_data = self._extract_zone_data(zone_config)
            
            if not zone_data.empty:
                # Use CoreTemperature if available, otherwise fall back to CoreAverage
                core_col = 'CoreTemperature' if 'CoreTemperature' in zone_data.columns else 'CoreAverage'
                zone_profiles[zone_name] = {
                    'data': zone_data,
                    'entry_temp': zone_data.iloc[0][core_col] if len(zone_data) > 0 else None,
                    'exit_temp': zone_data.iloc[-1][core_col] if len(zone_data) > 0 else None,
                    'avg_temp': zone_data[core_col].mean(),
                    'temp_std': zone_data[core_col].std(),
                    'duration_minutes': len(zone_data) * self.sample_period / 60
                }
            else:
                zone_profiles[zone_name] = None
                
        return zone_profiles
    
    def calculate_zone_transitions(self) -> pd.DataFrame:
        """Calculate temperature transition rates between zones."""
        transitions = []
        
        zone_list = list(TEMPERATURE_ZONES.keys())
        
        for i in range(len(zone_list) - 1):
            current_zone = TEMPERATURE_ZONES[zone_list[i]]
            next_zone = TEMPERATURE_ZONES[zone_list[i + 1]]
            
            # Find transition period
            # Use CoreTemperature if available, otherwise fall back to CoreAverage
            core_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
            transition_data = self.data[
                (self.data[core_col] >= current_zone['max']) &
                (self.data[core_col] <= next_zone['min'])
            ]
            
            if not transition_data.empty:
                transition_time = len(transition_data) * self.sample_period / 60
                temp_change = next_zone['min'] - current_zone['max']
                transition_rate = temp_change / transition_time if transition_time > 0 else 0
                
                transitions.append({
                    'from_zone': zone_list[i],
                    'to_zone': zone_list[i + 1],
                    'duration_minutes': transition_time,
                    'temperature_change': temp_change,
                    'rate_c_per_min': transition_rate
                })
        
        return pd.DataFrame(transitions)
    
    def analyze_zone_uniformity(self) -> Dict:
        """Analyze temperature uniformity within each zone."""
        uniformity_analysis = {}
        
        for zone_name, zone_config in TEMPERATURE_ZONES.items():
            zone_data = self._extract_zone_data(zone_config)
            
            if not zone_data.empty:
                # Calculate uniformity for core sensors
                core_sensors = ['T1', 'T2', 'T3', 'T4']
                core_data = zone_data[core_sensors]
                
                uniformity_metrics = {
                    'mean_std': core_data.std(axis=1).mean(),
                    'max_std': core_data.std(axis=1).max(),
                    'cv': (core_data.std(axis=1) / core_data.mean(axis=1)).mean(),
                    'max_spread': core_data.max(axis=1).mean() - core_data.min(axis=1).mean()
                }
                
                uniformity_analysis[zone_name] = uniformity_metrics
            else:
                uniformity_analysis[zone_name] = None
                
        return uniformity_analysis
    
    def get_zone_heating_characteristics(self) -> Dict:
        """Analyze heating characteristics within each zone."""
        heating_chars = {}
        
        for zone_name, zone_config in TEMPERATURE_ZONES.items():
            zone_data = self._extract_zone_data(zone_config)
            
            if len(zone_data) > 1:
                # Calculate heating rate within zone
                # Use CoreTemperature if available, otherwise fall back to CoreAverage
                core_col = 'CoreTemperature' if 'CoreTemperature' in zone_data.columns else 'CoreAverage'
                temp_diff = zone_data[core_col].diff()
                time_diff = self.sample_period
                heating_rate = (temp_diff / time_diff).mean()
                
                # Calculate acceleration
                rate_diff = (temp_diff / time_diff).diff()
                acceleration = rate_diff.mean()
                
                heating_chars[zone_name] = {
                    'avg_heating_rate': heating_rate,
                    'heating_acceleration': acceleration,
                    'rate_variability': (temp_diff / time_diff).std(),
                    'is_stable': abs(heating_rate) < 0.1  # Less than 0.1°C/s
                }
            else:
                heating_chars[zone_name] = None
                
        return heating_chars
    
    def recommend_zone_optimizations(self) -> List[Dict]:
        """Generate recommendations for zone optimization."""
        recommendations = []
        
        zone_profiles = self.get_zone_profiles()
        zone_uniformity = self.analyze_zone_uniformity()
        zone_heating = self.get_zone_heating_characteristics()
        
        # Check yeast kill zone
        if 'YEAST_KILL' in zone_profiles and zone_profiles['YEAST_KILL']:
            duration = zone_profiles['YEAST_KILL']['duration_minutes']
            if duration < 1:
                recommendations.append({
                    'zone': 'Yeast Kill',
                    'issue': 'Insufficient time in yeast kill zone',
                    'recommendation': 'Reduce heating rate or lower oven temperature',
                    'priority': 'High'
                })
        
        # Check starch gelatinization
        if 'STARCH_GELATINIZATION' in zone_profiles and zone_profiles['STARCH_GELATINIZATION']:
            duration = zone_profiles['STARCH_GELATINIZATION']['duration_minutes']
            if duration < 5:
                recommendations.append({
                    'zone': 'Starch Gelatinization',
                    'issue': 'Rapid transition through gelatinization',
                    'recommendation': 'Extend time in 65-82°C range for better crumb structure',
                    'priority': 'High'
                })
        
        # Check uniformity
        for zone_name, uniformity in zone_uniformity.items():
            if uniformity and uniformity['cv'] > 0.05:
                recommendations.append({
                    'zone': TEMPERATURE_ZONES[zone_name]['name'],
                    'issue': f'Poor temperature uniformity (CV: {uniformity["cv"]:.3f})',
                    'recommendation': 'Improve heat distribution or adjust product positioning',
                    'priority': 'Medium'
                })
        
        # Check heating stability
        for zone_name, heating in zone_heating.items():
            if heating and heating['rate_variability'] > 0.5:
                recommendations.append({
                    'zone': TEMPERATURE_ZONES[zone_name]['name'],
                    'issue': 'Unstable heating rate',
                    'recommendation': 'Stabilize oven conditions or review burner cycling',
                    'priority': 'Medium'
                })
        
        return recommendations
    
    def _extract_zone_data(self, zone_config: Dict) -> pd.DataFrame:
        """Extract data for a specific temperature zone."""
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
        return self.data[
            (self.data[core_col] >= zone_config['min']) &
            (self.data[core_col] <= zone_config['max'])
        ].copy()