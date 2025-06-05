"""
Improved curve detection algorithm V2 - handles complex cases better.
"""

import pandas as pd
import numpy as np
from typing import List, Dict


def detect_curve_boundaries_v2(df: pd.DataFrame) -> List[Dict]:
    """
    Detect baking curve boundaries using a more robust approach.
    
    Key insights:
    1. During baking, core temp should be significantly lower than ambient
    2. When probe is removed, core and ambient converge quickly
    3. Room temperature periods show stable temps around 20-30°C
    """
    curves = []
    
    # Determine columns
    if 'VirtualCoreTemperature' in df.columns:
        core_col = 'VirtualCoreTemperature'
        ambient_col = 'VirtualAmbientTemperature'
        sensor_col = 'VirtualCoreSensor'
    else:
        core_col = 'CoreAverage'
        ambient_col = 'AmbientTemperature'
        sensor_col = None
    
    # Calculate metrics
    df['core_ambient_delta'] = df[core_col] - df[ambient_col]
    df['temp_change'] = df[core_col].diff()
    
    # Parameters
    MIN_CURVE_DURATION = 60  # 5 minutes
    MIN_PEAK_TEMP = 80
    
    i = 0
    while i < len(df):
        # Find curve start
        start_idx = None
        
        # Look for temperature rise or state change
        for j in range(i, len(df) - 1):
            temp_rise = df.iloc[j+1][core_col] - df.iloc[j][core_col]
            
            # Start conditions
            if temp_rise > 5:
                start_idx = j
                break
            elif 'PredictionState' in df.columns:
                if (j > 0 and 
                    df.iloc[j-1]['PredictionState'] == 'Probe Not Inserted' and 
                    df.iloc[j]['PredictionState'] != 'Probe Not Inserted'):
                    start_idx = j
                    break
        
        if start_idx is None:
            break
        
        # Find curve peak
        peak_idx = start_idx
        peak_temp = df.iloc[start_idx][core_col]
        
        for j in range(start_idx, len(df)):
            if df.iloc[j][core_col] > peak_temp:
                peak_temp = df.iloc[j][core_col]
                peak_idx = j
        
        # Find curve end - look for signs of probe removal
        end_idx = None
        
        # Start looking after we've reached at least 60°C
        search_start = peak_idx
        for j in range(start_idx, peak_idx + 1):
            if df.iloc[j][core_col] > 60:
                search_start = j
                break
        
        for j in range(search_start, len(df)):
            temp = df.iloc[j][core_col]
            delta = df.iloc[j]['core_ambient_delta']
            
            # Multiple end conditions
            end_detected = False
            
            # 1. Temperature drop from peak > 20°C
            if peak_temp - temp > 20:
                end_detected = True
            
            # 2. Extended negative delta (probe in air)
            elif j >= search_start + 10:
                # Check last 10 samples
                recent_deltas = df['core_ambient_delta'].iloc[j-10:j+1]
                recent_temps = df[core_col].iloc[j-10:j+1]
                
                # Negative delta with low temperature = probe removed
                if (recent_deltas.mean() < -20 and recent_temps.max() < 50):
                    end_detected = True
                
                # Stable low temperature (room temp)
                elif (recent_temps.std() < 2 and 
                      18 < recent_temps.mean() < 30 and
                      j - search_start > 100):  # Been cooling for a while
                    end_detected = True
            
            # 3. Unusual sensor for extended period
            if sensor_col and sensor_col in df.columns and j >= search_start + 20:
                recent_sensors = df[sensor_col].iloc[j-20:j+1]
                unusual_count = recent_sensors.isin(['T4', 'T5', 'T6']).sum()
                if unusual_count > 15 and temp < 40:
                    end_detected = True
            
            if end_detected:
                # Back up to find the actual removal point
                # Look for where temperature started dropping rapidly
                for k in range(j, search_start, -1):
                    if k > 0:
                        drop_rate = df.iloc[k][core_col] - df.iloc[k-1][core_col]
                        if drop_rate < -10:  # 10°C drop in one interval
                            end_idx = k - 1
                            break
                
                if end_idx is None:
                    end_idx = j
                break
        
        if end_idx is None:
            end_idx = len(df) - 1
        
        # Validate and store curve
        duration = end_idx - start_idx + 1
        if duration >= MIN_CURVE_DURATION and peak_temp >= MIN_PEAK_TEMP:
            curves.append({
                'start_idx': start_idx,
                'end_idx': end_idx,
                'peak_idx': peak_idx,
                'peak_temp': peak_temp
            })
        
        # Move past this curve
        i = end_idx + 1
    
    return curves


def test_v2_detection():
    """Test V2 detection on the problematic file."""
    import sys
    sys.path.insert(0, '.')
    
    # Read the CSV
    df = pd.read_csv('ProbeData_1000BA3C_2025-05-30 17_59_37.csv', skiprows=10)
    
    # Detect curves
    curves = detect_curve_boundaries_v2(df)
    
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
        
        # Show some key temps
        start_temp = df.iloc[curve['start_idx']]['VirtualCoreTemperature']
        end_temp = df.iloc[curve['end_idx']]['VirtualCoreTemperature']
        print(f"  Start temp: {start_temp:.1f}°C")
        print(f"  End temp: {end_temp:.1f}°C")
        print()


if __name__ == "__main__":
    test_v2_detection()