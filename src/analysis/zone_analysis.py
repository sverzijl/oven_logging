"""Temperature zone analysis for bread baking optimization."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from config.constants import TEMPERATURE_ZONES


class ZoneAnalyzer:
    """Analyze time and behavior in critical temperature zones."""
    
    def __init__(self, data: pd.DataFrame, sample_period: float, loader=None):
        self.data = data
        self.sample_period = sample_period
        self.loader = loader
        # Use standardized column names
        self.core_temp_column = 'CoreTemperature'
        self.surface_temp_column = 'SurfaceTemperature'
        self.ambient_temp_column = 'AmbientTemperature'
        
    def get_zone_profiles(self) -> Dict:
        """Get detailed temperature profiles for each zone."""
        zone_profiles = {}
        
        for zone_key, zone_config in TEMPERATURE_ZONES.items():
            zone_data = self._extract_zone_data(zone_config)
            
            if not zone_data.empty:
                # Determine which temperature column to use based on zone type
                zone_name = zone_config.get('name', '')
                if zone_name in ['Crust Formation', 'Maillard Reaction', 'Caramelization']:
                    temp_col = self.surface_temp_column
                else:
                    temp_col = self.core_temp_column
                
                # Ensure the column exists
                if temp_col is None or temp_col not in zone_data.columns:
                    temp_col = 'CoreTemperature' if 'CoreTemperature' in zone_data.columns else 'CoreAverage'
                
                zone_profiles[zone_key] = {
                    'data': zone_data,
                    'entry_temp': zone_data.iloc[0][temp_col] if len(zone_data) > 0 else None,
                    'exit_temp': zone_data.iloc[-1][temp_col] if len(zone_data) > 0 else None,
                    'avg_temp': zone_data[temp_col].mean(),
                    'temp_std': zone_data[temp_col].std(),
                    'duration_minutes': len(zone_data) * self.sample_period / 60,
                    'temperature_type': 'surface' if zone_config.get('name') in ['Crust Formation', 'Maillard Reaction', 'Caramelization'] else 'core'
                }
            else:
                zone_profiles[zone_key] = None
                
        return zone_profiles
    
    def calculate_zone_transitions(self) -> pd.DataFrame:
        """Calculate temperature transition rates between zones, handling core/surface separation."""
        transitions = []
        
        # Separate zones by temperature type
        core_zones = []
        surface_zones = []
        
        for zone_name, zone_config in TEMPERATURE_ZONES.items():
            zone_info = {
                'name': zone_name,
                'config': zone_config,
                'type': 'surface' if zone_config['name'] in ['Crust Formation', 'Maillard Reaction', 'Caramelization'] else 'core'
            }
            
            if zone_info['type'] == 'core':
                core_zones.append(zone_info)
            else:
                surface_zones.append(zone_info)
        
        # Sort zones by minimum temperature
        core_zones.sort(key=lambda x: x['config']['min'])
        surface_zones.sort(key=lambda x: x['config']['min'])
        
        # Calculate transitions for core zones
        if len(core_zones) > 1:
            transitions.extend(self._calculate_transitions_for_zones(core_zones, self.core_temp_column, 'core'))
        
        # Calculate transitions for surface zones
        if len(surface_zones) > 1:
            transitions.extend(self._calculate_transitions_for_zones(surface_zones, self.surface_temp_column, 'surface'))
        
        return pd.DataFrame(transitions)
    
    def _calculate_transitions_for_zones(self, zones: List[Dict], temp_column: str, temp_type: str) -> List[Dict]:
        """Calculate transitions between zones of the same temperature type."""
        transitions = []
        
        if not temp_column or temp_column not in self.data.columns:
            return transitions
        
        for i in range(len(zones) - 1):
            current_zone = zones[i]['config']
            next_zone = zones[i + 1]['config']
            
            # Find transition period
            transition_data = self.data[
                (self.data[temp_column] >= current_zone['max']) &
                (self.data[temp_column] <= next_zone['min'])
            ]
            
            if not transition_data.empty:
                transition_time = len(transition_data) * self.sample_period / 60
                temp_change = next_zone['min'] - current_zone['max']
                transition_rate = temp_change / transition_time if transition_time > 0 else 0
                
                transitions.append({
                    'from_zone': zones[i]['name'],
                    'to_zone': zones[i + 1]['name'],
                    'duration_minutes': transition_time,
                    'temperature_change': temp_change,
                    'rate_c_per_min': transition_rate,
                    'temperature_type': temp_type
                })
        
        return transitions
    
    def analyze_zone_uniformity(self) -> Dict:
        """Analyze temperature uniformity within each zone."""
        uniformity_analysis = {}
        
        # Get all physical sensor columns
        all_sensors = [col for col in self.data.columns if col.startswith('T') and col[1:].isdigit()]
        
        for zone_name, zone_config in TEMPERATURE_ZONES.items():
            zone_data = self._extract_zone_data(zone_config)
            
            if not zone_data.empty:
                # Determine which sensors to analyze based on zone type
                zone_type = zone_config.get('name', '')
                if zone_type in ['Crust Formation', 'Maillard Reaction', 'Caramelization']:
                    # Surface zones - analyze surface sensors
                    sensors_to_analyze = self._get_surface_sensors()
                else:
                    # Core zones - analyze core sensors
                    sensors_to_analyze = self._get_core_sensors()
                
                # Ensure we have sensors to analyze
                if sensors_to_analyze and all(s in zone_data.columns for s in sensors_to_analyze):
                    sensor_data = zone_data[sensors_to_analyze]
                    
                    # Calculate uniformity metrics only if we have multiple sensors
                    if len(sensors_to_analyze) > 1:
                        uniformity_metrics = {
                            'mean_std': sensor_data.std(axis=1).mean(),
                            'max_std': sensor_data.std(axis=1).max(),
                            'cv': (sensor_data.std(axis=1) / sensor_data.mean(axis=1)).mean(),
                            'max_spread': sensor_data.max(axis=1).mean() - sensor_data.min(axis=1).mean(),
                            'sensors_analyzed': sensors_to_analyze,
                            'sensor_count': len(sensors_to_analyze)
                        }
                    else:
                        # Single sensor - uniformity is perfect by definition
                        uniformity_metrics = {
                            'mean_std': 0.0,
                            'max_std': 0.0,
                            'cv': 0.0,
                            'max_spread': 0.0,
                            'sensors_analyzed': sensors_to_analyze,
                            'sensor_count': 1,
                            'note': 'Single sensor - uniformity not applicable'
                        }
                else:
                    uniformity_metrics = {
                        'error': 'No valid sensors for analysis',
                        'sensors_analyzed': [],
                        'sensor_count': 0
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
                # Determine which temperature column to use based on zone type
                zone_name = zone_config.get('name', '')
                if zone_name in ['Crust Formation', 'Maillard Reaction', 'Caramelization']:
                    temp_col = self.surface_temp_column
                else:
                    temp_col = self.core_temp_column
                
                # Ensure the column exists
                if temp_col is None or temp_col not in zone_data.columns:
                    temp_col = 'CoreTemperature' if 'CoreTemperature' in zone_data.columns else 'CoreAverage'
                
                # Calculate heating rate within zone
                temp_diff = zone_data[temp_col].diff()
                time_diff = self.sample_period
                heating_rate = (temp_diff / time_diff).mean()
                
                # Calculate acceleration
                rate_diff = (temp_diff / time_diff).diff()
                acceleration = rate_diff.mean()
                
                heating_chars[zone_name] = {
                    'avg_heating_rate': heating_rate,
                    'heating_acceleration': acceleration,
                    'rate_variability': (temp_diff / time_diff).std(),
                    'is_stable': abs(heating_rate) < 0.1,  # Less than 0.1°C/s
                    'temperature_type': 'surface' if zone_config.get('name') in ['Crust Formation', 'Maillard Reaction', 'Caramelization'] else 'core'
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
        
        # Core zone recommendations
        # Check yeast kill zone
        if 'YEAST_KILL' in zone_profiles and zone_profiles['YEAST_KILL']:
            duration = zone_profiles['YEAST_KILL']['duration_minutes']
            if duration < 1:
                recommendations.append({
                    'zone': 'Yeast Kill',
                    'issue': 'Insufficient time in yeast kill zone',
                    'recommendation': 'Reduce heating rate in early baking stages or adjust zone 1 temperature',
                    'priority': 'High',
                    'temperature_type': 'core'
                })
        
        # Check starch gelatinization
        if 'STARCH_GELATINIZATION' in zone_profiles and zone_profiles['STARCH_GELATINIZATION']:
            duration = zone_profiles['STARCH_GELATINIZATION']['duration_minutes']
            if duration < 5:
                recommendations.append({
                    'zone': 'Starch Gelatinization',
                    'issue': 'Rapid transition through gelatinization',
                    'recommendation': 'Extend time in 65-82°C range by reducing zone 2-3 temperatures',
                    'priority': 'High',
                    'temperature_type': 'core'
                })
        
        # Surface zone recommendations
        # Check crust formation
        if 'CRUST_FORMATION' in zone_profiles and zone_profiles['CRUST_FORMATION']:
            duration = zone_profiles['CRUST_FORMATION']['duration_minutes']
            if duration < 3:
                recommendations.append({
                    'zone': 'Crust Formation',
                    'issue': 'Insufficient crust development time',
                    'recommendation': 'Increase oven temperature or extend bake time in final zones',
                    'priority': 'Medium',
                    'temperature_type': 'surface'
                })
            elif duration > 10:
                recommendations.append({
                    'zone': 'Crust Formation',
                    'issue': 'Excessive crust formation',
                    'recommendation': 'Reduce oven temperature in final zones or add steam',
                    'priority': 'Medium',
                    'temperature_type': 'surface'
                })
        
        # Check uniformity with temperature-specific recommendations
        for zone_name, uniformity in zone_uniformity.items():
            if uniformity and 'cv' in uniformity and uniformity['cv'] > 0.05:
                zone_config = TEMPERATURE_ZONES[zone_name]
                temp_type = 'surface' if zone_config['name'] in ['Crust Formation', 'Maillard Reaction', 'Caramelization'] else 'core'
                
                if temp_type == 'core':
                    recommendation = 'Improve heat penetration: check product density or increase zone temperatures'
                else:
                    recommendation = 'Improve air circulation or rotate products during baking'
                
                recommendations.append({
                    'zone': zone_config['name'],
                    'issue': f'Poor temperature uniformity (CV: {uniformity["cv"]:.3f})',
                    'recommendation': recommendation,
                    'priority': 'Medium',
                    'temperature_type': temp_type
                })
        
        # Check heating stability with temperature-specific recommendations
        for zone_name, heating in zone_heating.items():
            if heating and heating['rate_variability'] > 0.5:
                zone_config = TEMPERATURE_ZONES[zone_name]
                temp_type = heating.get('temperature_type', 'core')
                
                if temp_type == 'surface':
                    recommendation = 'Check oven air circulation and burner patterns'
                else:
                    recommendation = 'Stabilize oven conditions or adjust conveyor speed'
                
                recommendations.append({
                    'zone': zone_config['name'],
                    'issue': 'Unstable heating rate',
                    'recommendation': recommendation,
                    'priority': 'Medium',
                    'temperature_type': temp_type
                })
        
        return recommendations
    
    def _get_core_sensors(self) -> List[str]:
        """Get list of physical sensors identified as core sensors."""
        if self.loader:
            return self.loader.get_core_sensors()
        else:
            # Fallback to traditional sensors
            return ['T1', 'T2', 'T3', 'T4']
    
    def _get_surface_sensors(self) -> List[str]:
        """Get list of physical sensors identified as surface sensors."""
        if self.loader:
            return self.loader.get_surface_sensors()
        else:
            # Fallback to traditional sensors
            return ['T7', 'T8']
    
    
    
    def _extract_zone_data(self, zone_config: Dict) -> pd.DataFrame:
        """Extract data for a specific temperature zone."""
        # Determine which temperature column to use based on zone type
        zone_name = zone_config.get('name', '')
        
        # Surface processes (crust formation, browning reactions)
        if zone_name in ['Crust Formation', 'Maillard Reaction', 'Caramelization']:
            temp_col = self.surface_temp_column
        # Core processes (internal transformations)
        else:
            temp_col = self.core_temp_column
        
        if temp_col is None or temp_col not in self.data.columns:
            # Fallback to core temperature if identification failed
            temp_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
        
        return self.data[
            (self.data[temp_col] >= zone_config['min']) &
            (self.data[temp_col] <= zone_config['max'])
        ].copy()