"""Module for comparing multiple thermal curves with role-based analysis."""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from src.analysis.thermal_analysis import ThermalAnalyzer
from src.analysis.zone_analysis import ZoneAnalyzer
from src.analysis.s_curve_analysis import SCurveAnalyzer
from src.data.column_helpers import get_core_temperature_column
from config.constants import TEMPERATURE_ZONES, SENSOR_LIST


def transform_sensor_assignments_to_roles(sensor_assignments: Dict[str, List[str]]) -> Dict[str, str]:
    """
    Transform sensor assignments from loader format to role mapping format.
    
    Args:
        sensor_assignments: Dict with 'core', 'surface', 'ambient' keys containing lists of sensors
        
    Returns:
        Dict mapping sensor names to their roles
    """
    sensor_roles = {}
    
    # Map each sensor to its role
    for role, sensors in sensor_assignments.items():
        if isinstance(sensors, list):
            for sensor in sensors:
                sensor_roles[sensor] = role
    
    # Add internal sensors (T1-T8 not assigned to other roles)
    all_sensors = list(SENSOR_LIST)
    for sensor in all_sensors:
        if sensor not in sensor_roles:
            sensor_roles[sensor] = 'internal'
    
    return sensor_roles


class CurveComparison:
    """Compare multiple thermal curves using role-based sensor analysis."""
    
    def __init__(self, curves: List[Dict]):
        """
        Initialize with a list of curve data.
        
        Args:
            curves: List of curve dictionaries containing:
                - curve_data: Dict with 'data' key containing DataFrame
                - sensor_roles: Dict mapping sensor names to roles
                - metadata: Dict with product and oven information
                - filename: Source filename
                - file_curve_index: Index within the file
        """
        self.curves = curves
        self.num_curves = len(curves)
    
    def get_role_based_data(self) -> Dict[str, List[Dict]]:
        """
        Extract temperature data organized by sensor role.
        
        Returns:
            Dictionary with roles as keys and list of curve data as values:
            {
                'core': [{'time': [], 'temperature': [], 'curve_name': str, 'sensors': []}, ...],
                'surface': [...],
                'ambient': [...],
                'internal': [...]
            }
        """
        role_data = {
            'core': [],
            'surface': [],
            'ambient': [],
            'internal': []
        }
        
        for i, curve in enumerate(self.curves):
            data = curve['curve_data']['data']
            sensor_roles = curve.get('sensor_roles', {})
            curve_name = self._get_curve_name(curve, i)
            
            # Extract data for each role
            for role in role_data.keys():
                # Find sensors with this role
                role_sensors = [sensor for sensor, sensor_role in sensor_roles.items() 
                              if sensor_role == role]
                
                # Get short name for legends
                short_name = self._get_short_curve_name(curve, i)
                
                # Prepare data based on role
                if role == 'core' and 'CoreTemperature' in data.columns:
                    # Use standardized column
                    role_data[role].append({
                        'time': data['TimeMinutes'].values,
                        'temperature': data['CoreTemperature'].values,
                        'curve_name': curve_name,
                        'curve_short_name': short_name,
                        'sensors': role_sensors
                    })
                elif role == 'surface' and 'SurfaceTemperature' in data.columns:
                    # Use standardized column
                    role_data[role].append({
                        'time': data['TimeMinutes'].values,
                        'temperature': data['SurfaceTemperature'].values,
                        'curve_name': curve_name,
                        'curve_short_name': short_name,
                        'sensors': role_sensors
                    })
                elif role == 'ambient' and 'AmbientTemperature' in data.columns:
                    # Use standardized column
                    role_data[role].append({
                        'time': data['TimeMinutes'].values,
                        'temperature': data['AmbientTemperature'].values,
                        'curve_name': curve_name,
                        'curve_short_name': short_name,
                        'sensors': role_sensors
                    })
                elif role == 'internal' and role_sensors:
                    # For internal sensors, we'll track each one separately
                    internal_temps = []
                    for sensor in role_sensors:
                        if sensor in data.columns:
                            internal_temps.append(data[sensor].values)
                    
                    if internal_temps:
                        # Store all internal sensor data
                        role_data[role].append({
                            'time': data['TimeMinutes'].values,
                            'temperature': np.array(internal_temps).T,  # Time x Sensors
                            'curve_name': curve_name,
                            'curve_short_name': short_name,
                            'sensors': role_sensors
                        })
        
        return role_data
    
    def compare_zone_durations(self) -> pd.DataFrame:
        """
        Compare time spent in each temperature zone across curves.
        
        Returns:
            DataFrame with curves as rows and zones as columns
        """
        zone_data = []
        
        for i, curve in enumerate(self.curves):
            data = curve['curve_data']['data']
            metadata = curve.get('metadata', {})
            
            # Ensure we have a Timestamp column for ThermalAnalyzer
            if 'Timestamp' not in data.columns and 'TimeMinutes' in data.columns:
                # Create a dummy timestamp column
                data = data.copy()
                data['Timestamp'] = pd.Timestamp('2024-01-01') + pd.to_timedelta(data['TimeMinutes'], unit='minutes')
            
            # Run zone analysis through ThermalAnalyzer
            analyzer = ThermalAnalyzer(data, metadata)
            zone_results = analyzer.analyze_temperature_zones()
            
            # Extract durations
            row_data = {'Curve': self._get_short_curve_name(curve, i)}
            
            for zone_name, zone_info in zone_results.items():
                if zone_name in TEMPERATURE_ZONES:
                    duration = zone_info.get('duration', zone_info.get('total_time_minutes', 0))
                    zone_display_name = TEMPERATURE_ZONES[zone_name]['name']
                    row_data[zone_display_name] = duration
            
            zone_data.append(row_data)
        
        return pd.DataFrame(zone_data)
    
    def compare_quality_metrics(self) -> pd.DataFrame:
        """
        Compare quality metrics across curves.
        
        Returns:
            DataFrame with quality metrics for each curve
        """
        metrics_data = []
        
        for i, curve in enumerate(self.curves):
            data = curve['curve_data']['data']
            metadata = curve.get('metadata', {})
            
            # Ensure we have a Timestamp column for ThermalAnalyzer
            if 'Timestamp' not in data.columns and 'TimeMinutes' in data.columns:
                # Create a dummy timestamp column
                data = data.copy()
                data['Timestamp'] = pd.Timestamp('2024-01-01') + pd.to_timedelta(data['TimeMinutes'], unit='minutes')
            
            # Get thermal analysis metrics
            analyzer = ThermalAnalyzer(data, metadata)
            metrics = analyzer.calculate_quality_metrics()
            
            # Extract key metrics. Resolve the core column via the shared helper
            # (CoreTemperature → CoreAverage) rather than falling back to raw T1,
            # which is not guaranteed to be the core sensor (#24).
            duration = data['TimeMinutes'].max()
            max_core_temp = data[get_core_temperature_column(data)].max()
            
            # Time to key temperatures
            time_to_56 = self._get_time_to_temp(data, 56)
            time_to_82 = self._get_time_to_temp(data, 82)
            time_to_93 = self._get_time_to_temp(data, 93)
            
            row_data = {
                'Curve': self._get_short_curve_name(curve, i),
                'Duration': f"{duration:.1f} min",
                'Max Core Temp': f"{max_core_temp:.1f}°C",
                'Time to 56°C': f"{time_to_56:.1f} min" if time_to_56 else "N/A",
                'Time to 82°C': f"{time_to_82:.1f} min" if time_to_82 else "N/A",
                'Time to 93°C': f"{time_to_93:.1f} min" if time_to_93 else "N/A",
                'Quality Score': f"{metrics.get('quality_score', 0):.1f}",
                'Uniformity': metrics.get('core_uniformity_rating', 'N/A')
            }
            
            metrics_data.append(row_data)
        
        return pd.DataFrame(metrics_data)
    
    def compare_s_curve_landmarks(self) -> pd.DataFrame:
        """
        Compare S-curve landmarks across curves.
        
        Returns:
            DataFrame with landmark times and percentages for each curve
        """
        landmark_data = []
        
        for i, curve in enumerate(self.curves):
            data = curve['curve_data']['data']
            metadata = curve.get('metadata', {})
            
            # Get S-curve landmarks
            s_curve_analyzer = SCurveAnalyzer(data, metadata)
            landmarks = s_curve_analyzer.identify_landmarks()
            
            row_data = {'Curve': self._get_short_curve_name(curve, i)}
            
            # Add landmark data
            for landmark_name, landmark in landmarks.items():
                if landmark.time_minutes is not None:
                    row_data[f'{landmark_name} Time'] = f"{landmark.time_minutes:.1f} min"
                    row_data[f'{landmark_name} %'] = f"{landmark.time_percentage:.0f}%"
                    status = "✓" if landmark.is_within_target else "✗"
                    row_data[f'{landmark_name} Status'] = status
                else:
                    row_data[f'{landmark_name} Time'] = "N/A"
                    row_data[f'{landmark_name} %'] = "N/A"
                    row_data[f'{landmark_name} Status'] = "N/A"
            
            landmark_data.append(row_data)
        
        return pd.DataFrame(landmark_data)
    
    def get_heating_rate_comparison(self) -> Dict:
        """
        Get heating rate data for comparison.
        
        Returns:
            Dictionary with heating rate data for core and surface
        """
        heating_data = {
            'core_rates': [],
            'surface_rates': [],
            'consistency_scores': []
        }
        
        for i, curve in enumerate(self.curves):
            data = curve['curve_data']['data']
            metadata = curve.get('metadata', {})
            curve_name = self._get_curve_name(curve, i)
            short_name = self._get_short_curve_name(curve, i)
            
            # Ensure we have a Timestamp column for ThermalAnalyzer
            if 'Timestamp' not in data.columns and 'TimeMinutes' in data.columns:
                # Create a dummy timestamp column
                data = data.copy()
                data['Timestamp'] = pd.Timestamp('2024-01-01') + pd.to_timedelta(data['TimeMinutes'], unit='minutes')
            
            # Calculate heating rates
            analyzer = ThermalAnalyzer(data, metadata)
            rates = analyzer.calculate_heating_rates()
            metrics = analyzer.calculate_quality_metrics()
            
            if rates is not None:
                # Core heating rate
                if 'core_rate' in rates.columns:
                    heating_data['core_rates'].append({
                        'time': rates['TimeMinutes'].values,
                        'rate': rates['core_rate'].values,
                        'curve_name': curve_name,
                        'curve_short_name': short_name
                    })
                
                # Surface heating rate
                if 'surface_rate' in rates.columns:
                    heating_data['surface_rates'].append({
                        'time': rates['TimeMinutes'].values,
                        'rate': rates['surface_rate'].values,
                        'curve_name': curve_name,
                        'curve_short_name': short_name
                    })
                
                # Consistency score
                heating_data['consistency_scores'].append({
                    'curve_name': curve_name,
                    'curve_short_name': short_name,
                    'score': metrics.get('heating_rate_consistency', 0) * 100
                })
        
        return heating_data
    
    def _get_curve_name(self, curve: Dict, index: int) -> str:
        """Generate a descriptive name for the curve."""
        filename = curve.get('filename', f'Curve {index + 1}')
        file_curve_idx = curve.get('file_curve_index', 0)
        
        # Remove extension from filename
        if '.' in filename:
            filename = filename.rsplit('.', 1)[0]
        
        # If multiple curves in file, add curve number
        if 'all_curves' in curve and len(curve['all_curves']) > 1:
            return f"{filename} - Curve {file_curve_idx + 1}"
        
        return filename
    
    def _get_short_curve_name(self, curve: Dict, index: int) -> str:
        """
        Generate a short, legend-friendly name for the curve.
        
        Naming convention:
        - Format: {Last 4 digits of Probe S/N}_{HH:MM}
        - Example: "98DE_13:51" from probe S/N "100098DE" created at 13:51
        - Multi-curve files append curve number: "F3C1_09:11_C1", "F3C1_09:11_C2"
        
        Args:
            curve: Curve dictionary with metadata and filename
            index: Index of curve in comparison list
            
        Returns:
            Short probe identifier string for use in plot legends
        """
        import re
        from datetime import datetime
        
        filename = curve.get('filename', f'Curve {index + 1}')
        metadata = curve.get('metadata', {})
        file_curve_idx = curve.get('file_curve_index', 0)
        
        # Try to use metadata first
        probe_sn = metadata.get('Probe S/N', '')
        created_dt = metadata.get('created_datetime')
        
        if probe_sn and created_dt:
            # Use last 4 characters of probe S/N
            short_sn = probe_sn[-4:].upper()
            time_str = created_dt.strftime('%H:%M')
            legend = f"{short_sn}_{time_str}"
        else:
            # Try to parse from filename
            name = filename.replace('.csv', '')
            match = re.match(r'ProbeData_([0-9A-Fa-f]+)_(?:\d{4}-\d{2}-\d{2} )(\d{2})_(\d{2})_(\d{2})', name)
            
            if match:
                probe_sn = match.group(1)
                hour = match.group(2)
                minute = match.group(3)
                
                # Take last 4 characters of probe S/N
                short_sn = probe_sn[-4:].upper()
                legend = f"{short_sn}_{hour}:{minute}"
            else:
                # Fallback: use index
                legend = f"Probe {index + 1}"
        
        # Add curve number for multi-curve files
        # Check if this file has multiple curves
        from_same_file = [c for c in self.curves if c.get('filename') == filename]
        if len(from_same_file) > 1:
            legend += f"_C{file_curve_idx + 1}"
        
        return legend
    
    def _get_time_to_temp(self, data: pd.DataFrame, temp: float) -> Optional[float]:
        """Get time to reach a specific temperature."""
        # Resolve via the shared helper (CoreTemperature → CoreAverage) rather
        # than falling back to raw T1, which may not be the core sensor (#24).
        core_col = get_core_temperature_column(data)

        mask = data[core_col] >= temp
        if mask.any():
            # Get the index of the first True value
            first_idx = mask.idxmax()
            return data.loc[first_idx, 'TimeMinutes']
        return None