"""
Thermodynamic-based sensor classification for identifying core, surface, and ambient sensors
without calibration, using heat transfer principles.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


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