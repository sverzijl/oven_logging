"""Physics-based surface sensor detection for bread baking probes."""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from config.constants import SENSOR_NAMES


def identify_surface_sensor_advanced(df: pd.DataFrame, sample_period_ms: int = 5000) -> Optional[Dict]:
    """
    Advanced algorithm to identify the true surface sensor based on baking physics.
    
    The surface is defined as the boundary where:
    1. Temperature can exceed 100°C (moisture has evaporated)
    2. Heating rate is significantly higher than internal sensors
    3. Temperature variance is higher (affected by oven cycling)
    4. Sharp gradient exists from internal temperatures
    
    Args:
        df: DataFrame containing sensor data (T1-T8)
        sample_period_ms: Sample period in milliseconds (default 5000)
        
    Returns:
        dict: {
            'sensor': str,           # e.g., 'T7'
            'confidence': int,       # 0-100%
            'reasoning': str,        # Human-readable explanation
            'browning_time': float,  # Minutes in 110-180°C range
            'max_temp': float        # Maximum temperature reached
        }
        or None if surface cannot be identified
    """
    sensors = list(SENSOR_NAMES)
    results = {}
    
    # Phase 1: Calculate key metrics for each sensor
    for sensor in sensors:
        if sensor not in df.columns:
            continue
            
        temp_series = df[sensor]
        
        # 1. Maximum temperature reached
        max_temp = temp_series.max()
        
        # 2. Time to reach 100°C (moisture evaporation point)
        time_to_100 = None
        if max_temp >= 100:
            mask = temp_series >= 100
            if mask.any():
                idx_100 = temp_series[mask].index[0]
                time_to_100 = df.loc[idx_100, 'TimeMinutes'] if 'TimeMinutes' in df.columns else idx_100 * sample_period_ms / 60000
        
        # 3. Average heating rate in critical zone (60-100°C)
        critical_zone = temp_series[(temp_series >= 60) & (temp_series <= 100)]
        if len(critical_zone) > 10:
            heating_rate = critical_zone.diff().mean() / (sample_period_ms / 60000)  # °C/min
        else:
            heating_rate = 0
        
        # 4. Temperature variance after reaching 80°C (surface shows more variation)
        high_temp_data = temp_series[temp_series >= 80]
        temp_variance = high_temp_data.var() if len(high_temp_data) > 10 else 0
        
        # 5. "Escape velocity" - how quickly sensor breaks through 100°C ceiling
        escape_velocity = 0
        if max_temp > 105:
            # Find rate of change from 95°C to 105°C
            escape_zone = temp_series[(temp_series >= 95) & (temp_series <= 105)]
            if len(escape_zone) > 5:
                escape_velocity = escape_zone.diff().max() / (sample_period_ms / 60000)
        
        # 6. Time spent above 100°C (dry zone indicator)
        time_above_100 = (temp_series > 100).sum() * sample_period_ms / 60000  # minutes
        
        results[sensor] = {
            'max_temp': max_temp,
            'time_to_100': time_to_100,
            'heating_rate': heating_rate,
            'temp_variance': temp_variance,
            'escape_velocity': escape_velocity,
            'time_above_100': time_above_100,
            'sensor_num': int(sensor[1])
        }
    
    # Phase 2: Identify the surface boundary using gradient analysis
    surface_candidates = []
    
    for i in range(len(sensors) - 1):
        if sensors[i] not in results or sensors[i + 1] not in results:
            continue
            
        curr = results[sensors[i]]
        next = results[sensors[i + 1]]
        
        # Calculate gradient metrics
        temp_gradient = next['max_temp'] - curr['max_temp']
        
        # Strong indicators of surface boundary:
        # 1. Current sensor stays below 100°C, next exceeds it significantly
        is_boundary = (
            curr['max_temp'] < 100 and next['max_temp'] > 110 or
            curr['max_temp'] < 105 and next['max_temp'] > 120
        )
        
        # 2. Sharp increase in heating rate
        rate_increase = next['heating_rate'] / (curr['heating_rate'] + 0.1)  # Avoid division by zero
        
        # 3. Significant increase in temperature variance
        variance_ratio = next['temp_variance'] / (curr['temp_variance'] + 0.1)
        
        # 4. Clear "escape" from 100°C ceiling
        escape_difference = next['escape_velocity'] - curr['escape_velocity']
        
        # Score the boundary transition
        boundary_score = 0
        if is_boundary:
            boundary_score += 10
        if temp_gradient > 15:  # >15°C jump
            boundary_score += 5
        if rate_increase > 1.5:  # 50% faster heating
            boundary_score += 3
        if variance_ratio > 2:  # Double the variance
            boundary_score += 3
        if escape_difference > 2:  # Much faster escape velocity
            boundary_score += 4
        if next['time_above_100'] > 10 and curr['time_above_100'] < 5:
            boundary_score += 5
        
        if boundary_score >= 8:  # Threshold for surface identification
            surface_candidates.append({
                'sensor': sensors[i + 1],
                'score': boundary_score,
                'gradient': temp_gradient,
                'metrics': next
            })
    
    # Phase 3: Select the best surface sensor
    if surface_candidates:
        # Primary criterion: Lowest sensor number that shows clear surface behavior
        # This represents the actual dough/air interface
        best_candidate = min(surface_candidates, key=lambda x: x['metrics']['sensor_num'])
        
        # Validation: Ensure it spends meaningful time in browning zone
        sensor_name = best_candidate['sensor']
        browning_time = ((df[sensor_name] >= 110) & (df[sensor_name] <= 180)).sum() * sample_period_ms / 60000
        
        if browning_time >= 5:  # At least 5 minutes in browning zone
            return {
                'sensor': sensor_name,
                'confidence': min(100, best_candidate['score'] * 5),  # Convert score to percentage
                'reasoning': f"Sharp gradient of {best_candidate['gradient']:.1f}°C from internal sensor",
                'browning_time': browning_time,
                'max_temp': best_candidate['metrics']['max_temp']
            }
    
    # Phase 4: Fallback logic if gradient analysis fails
    # Look for sensors that clearly exhibit surface behavior
    for sensor in ['T4', 'T5', 'T6', 'T7', 'T8']:  # Start from T4 (surface unlikely to be T1-T3)
        if sensor in results:
            if results[sensor]['max_temp'] >= 110 and results[sensor]['time_above_100'] > 10:
                browning_time = ((df[sensor] >= 110) & (df[sensor] <= 180)).sum() * sample_period_ms / 60000
                if browning_time >= 5:
                    return {
                        'sensor': sensor,
                        'confidence': 70,
                        'reasoning': f"Reaches {results[sensor]['max_temp']:.1f}°C with significant browning time",
                        'browning_time': browning_time,
                        'max_temp': results[sensor]['max_temp']
                    }
    
    # Final fallback: Return None to indicate algorithm couldn't identify surface
    return None


def get_baking_physics_metrics(df: pd.DataFrame, sensor_name: str) -> Dict:
    """
    Calculate additional physics-based metrics for validation.
    
    Args:
        df: DataFrame containing sensor data
        sensor_name: Name of the sensor to analyze
        
    Returns:
        dict: Physics-based metrics for the sensor
    """
    if sensor_name not in df.columns:
        return {}
        
    temp_series = df[sensor_name]
    
    # Crust development phases
    phase_metrics = {
        'drying_phase': ((temp_series >= 95) & (temp_series < 110)).sum() * 5 / 60,  # minutes
        'browning_phase': ((temp_series >= 110) & (temp_series < 150)).sum() * 5 / 60,
        'caramelization_phase': (temp_series >= 150).sum() * 5 / 60,
    }
    
    # Oven spring influence (surface expands until ~60°C)
    oven_spring_duration = (temp_series <= 60).sum() * 5 / 60
    
    # Staling prevention (time above 140°C should be limited)
    excessive_heat_time = (temp_series > 140).sum() * 5 / 60
    
    return {
        'phases': phase_metrics,
        'oven_spring_minutes': oven_spring_duration,
        'excessive_heat_minutes': excessive_heat_time,
        'optimal_crust': phase_metrics['browning_phase'] > 10 and excessive_heat_time < 15
    }