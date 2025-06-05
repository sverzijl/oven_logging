"""
Improved curve detection algorithm that handles cases where the probe
doesn't cool below 20°C between bakes.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple


def detect_curve_boundaries(df: pd.DataFrame) -> List[Dict]:
    """
    Detect baking curve boundaries using multiple indicators:
    1. Core-ambient temperature relationship
    2. Temperature stability at room temperature
    3. Sensor switching patterns
    4. Rate of temperature change
    
    Returns list of curve segments with start/end indices.
    """
    curves = []
    
    # Determine which temperature columns to use
    if 'VirtualCoreTemperature' in df.columns:
        core_col = 'VirtualCoreTemperature'
        ambient_col = 'VirtualAmbientTemperature'
        sensor_col = 'VirtualCoreSensor'
    else:
        # Fallback to calculated averages
        core_col = 'CoreAverage'
        ambient_col = 'AmbientTemperature'
        sensor_col = None
    
    # Calculate key metrics
    df['core_ambient_delta'] = df[core_col] - df[ambient_col]
    df['temp_change'] = df[core_col].diff()
    df['temp_change_rate'] = df['temp_change'] / 5  # Per second for 5-second intervals
    
    # Smooth temperature for stability detection
    df['core_smooth'] = df[core_col].rolling(window=5, center=True).mean().fillna(df[core_col])
    
    # State machine for curve detection
    IDLE = 0
    IN_CURVE = 1
    COOLING = 2
    
    state = IDLE
    curve_start = None
    curve_peak = None
    curve_peak_temp = 0
    
    MIN_CURVE_DURATION = 60  # samples (5 minutes)
    MIN_PEAK_TEMP = 80  # °C
    
    print(f"Debug: Starting detection with {len(df)} samples")
    print(f"Debug: Using columns - core: {core_col}, ambient: {ambient_col}")
    
    for i in range(len(df)):
        temp = df.iloc[i][core_col]
        delta = df.iloc[i]['core_ambient_delta']
        
        if state == IDLE:
            # Look for curve start: rapid temperature rise or positive delta increase
            if i > 0:
                temp_rise = temp - df.iloc[i-1][core_col]
                
                # Start conditions:
                # 1. Temperature rises more than 5°C
                # 2. Core-ambient delta becomes significantly positive (>10°C)
                # 3. PredictionState changes (if available)
                start_detected = False
                
                if temp_rise > 5:
                    start_detected = True
                    print(f"Debug: Start detected at i={i} due to temp rise {temp_rise:.1f}")
                elif i > 10 and delta > 10 and df.iloc[i-10]['core_ambient_delta'] < 5:
                    start_detected = True
                    print(f"Debug: Start detected at i={i} due to delta increase")
                elif 'PredictionState' in df.columns and i > 0:
                    if (df.iloc[i-1]['PredictionState'] == 'Probe Not Inserted' and 
                        df.iloc[i]['PredictionState'] != 'Probe Not Inserted'):
                        start_detected = True
                        print(f"Debug: Start detected at i={i} due to PredictionState change")
                
                if start_detected:
                    curve_start = i
                    curve_peak = i
                    curve_peak_temp = temp
                    state = IN_CURVE
                    
        elif state == IN_CURVE:
            # Track peak temperature
            if temp > curve_peak_temp:
                curve_peak = i
                curve_peak_temp = temp
            
            # Debug output every 100 samples
            if i % 100 == 0:
                print(f"Debug: IN_CURVE at i={i}, temp={temp:.1f}, delta={delta:.1f}, peak={curve_peak_temp:.1f}")
            
            # Look for curve end indicators
            end_detected = False
            reason = ""
            
            # End condition 1: Core-ambient delta becomes negative for extended period
            if i >= 5:
                recent_deltas = df['core_ambient_delta'].iloc[i-5:i+1]
                if (recent_deltas < -5).all() and temp < 60:
                    end_detected = True
                    reason = "negative_delta"
                    print(f"Debug: End condition 1 triggered at i={i}")
            
            # End condition 2: Temperature drops significantly from peak
            if curve_peak_temp - temp > 20:
                end_detected = True
                reason = "temp_drop"
            
            # End condition 3: Extended stability at room temperature
            if i >= 20:
                recent_temps = df['core_smooth'].iloc[i-20:i+1]
                temp_std = recent_temps.std()
                temp_mean = recent_temps.mean()
                if temp_std < 2 and 15 < temp_mean < 30:
                    end_detected = True
                    reason = "room_temp_stable"
            
            # End condition 4: Unusual sensor assignment (if available)
            if sensor_col and sensor_col in df.columns:
                current_sensor = df.iloc[i][sensor_col]
                # T4, T5, T6 are unusual for core readings
                if current_sensor in ['T4', 'T5', 'T6'] and temp < 40:
                    # Look for extended period with unusual sensor
                    if i >= 10:
                        recent_sensors = df[sensor_col].iloc[i-10:i+1]
                        if (recent_sensors.isin(['T4', 'T5', 'T6'])).sum() > 8:
                            end_detected = True
                            reason = "unusual_sensor"
            
            if end_detected:
                # Find the actual end point (before the anomaly)
                if reason == "negative_delta":
                    # Back up to where delta was still positive
                    for j in range(i-5, curve_peak, -1):
                        if df.iloc[j]['core_ambient_delta'] > 5:
                            curve_end = j
                            break
                    else:
                        curve_end = i - 5
                elif reason == "room_temp_stable":
                    # Back up to where temperature started dropping rapidly
                    for j in range(i-20, curve_peak, -1):
                        if df.iloc[j][core_col] > temp_mean + 20:
                            curve_end = j + 5  # Include a bit of the drop
                            break
                    else:
                        curve_end = i - 20
                else:
                    curve_end = i
                
                # Validate curve
                duration = curve_end - curve_start + 1
                print(f"Debug: Curve ended at i={i}, duration={duration}, peak_temp={curve_peak_temp:.1f}, reason={reason}")
                if duration >= MIN_CURVE_DURATION and curve_peak_temp >= MIN_PEAK_TEMP:
                    curves.append({
                        'start_idx': curve_start,
                        'end_idx': curve_end,
                        'peak_idx': curve_peak,
                        'peak_temp': curve_peak_temp,
                        'end_reason': reason
                    })
                    print(f"Debug: Curve added! Total curves: {len(curves)}")
                else:
                    print(f"Debug: Curve rejected - duration or peak temp too low")
                
                state = COOLING
                
        elif state == COOLING:
            # Wait for temperature to stabilize or start rising again
            if i > 0:
                temp_change = temp - df.iloc[i-1][core_col]
                
                # Look for new curve start
                if temp_change > 2 or (delta > 10 and temp > 30):
                    # Check if we're past the cooling phase
                    if curves and i - curves[-1]['end_idx'] > 10:  # At least 50 seconds gap
                        curve_start = i
                        curve_peak = i
                        curve_peak_temp = temp
                        state = IN_CURVE
                    elif not curves:  # First curve already ended, can start new one
                        curve_start = i
                        curve_peak = i
                        curve_peak_temp = temp
                        state = IN_CURVE
    
    # Handle case where last curve doesn't end
    if state == IN_CURVE:
        curve_end = len(df) - 1
        duration = curve_end - curve_start + 1
        if duration >= MIN_CURVE_DURATION and curve_peak_temp >= MIN_PEAK_TEMP:
            curves.append({
                'start_idx': curve_start,
                'end_idx': curve_end,
                'peak_idx': curve_peak,
                'peak_temp': curve_peak_temp,
                'end_reason': 'end_of_data'
            })
    
    return curves


def test_improved_detection():
    """Test the improved detection on the problematic file."""
    import sys
    sys.path.insert(0, '.')
    
    # Read the CSV
    df = pd.read_csv('ProbeData_1000BA3C_2025-05-30 17_59_37.csv', skiprows=10)
    
    # Detect curves
    curves = detect_curve_boundaries(df)
    
    print(f"Detected {len(curves)} curves:\n")
    
    for i, curve in enumerate(curves):
        start_time = df.iloc[curve['start_idx']]['Timestamp']
        end_time = df.iloc[curve['end_idx']]['Timestamp']
        duration = (end_time - start_time) / 60
        
        print(f"Curve {i+1}:")
        print(f"  Start: index {curve['start_idx']} (time {start_time/60:.1f} min)")
        print(f"  End: index {curve['end_idx']} (time {end_time/60:.1f} min)")
        print(f"  Duration: {duration:.1f} minutes")
        print(f"  Peak temp: {curve['peak_temp']:.1f}°C")
        print(f"  End reason: {curve['end_reason']}")
        print()


if __name__ == "__main__":
    test_improved_detection()