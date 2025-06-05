#!/usr/bin/env python3
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '.')

# Read the problematic CSV
df = pd.read_csv('ProbeData_1000BA3C_2025-05-30 17_59_37.csv', skiprows=10)

# Use VirtualCoreTemperature
core_col = 'VirtualCoreTemperature'

print("Analyzing the 77-minute curve to find where it should be split...\n")

# Calculate temperature derivatives (rate of change)
df['temp_change'] = df[core_col].diff()
df['temp_change_rate'] = df['temp_change'] / 5  # Per second (5-second intervals)

# Look for specific patterns that indicate curve boundaries
print("1. Looking for cooling/heating rate anomalies:")
print("-" * 60)

# Find periods of rapid cooling followed by heating
for i in range(10, len(df) - 10):
    # Check if we're in a potential transition zone
    # Look for: cooling -> minimum -> heating pattern
    
    # Get a window of data
    window_temps = df[core_col].iloc[i-5:i+5].values
    window_changes = np.diff(window_temps)
    
    # Check if we have a V-shape (cooling then heating)
    if i < len(df) - 20:
        recent_avg_change = df['temp_change'].iloc[i-5:i].mean()
        future_avg_change = df['temp_change'].iloc[i:i+5].mean()
        
        # Significant cooling followed by heating
        if recent_avg_change < -2 and future_avg_change > 1:
            print(f"\nPotential curve boundary at index {i} (time {df.iloc[i]['Timestamp']:.1f}s):")
            print(f"  Temperature: {df.iloc[i][core_col]:.1f}°C")
            print(f"  Recent trend: {recent_avg_change:.2f}°C/interval (cooling)")
            print(f"  Future trend: {future_avg_change:.2f}°C/interval (heating)")
            
            # Check minimum temperature in this region
            min_idx = df[core_col].iloc[i-10:i+10].idxmin()
            min_temp = df.iloc[min_idx][core_col]
            print(f"  Local minimum: {min_temp:.1f}°C at time {df.iloc[min_idx]['Timestamp']:.1f}s")

print("\n\n2. Analyzing sensor assignment changes:")
print("-" * 60)

# Check for VirtualCoreSensor changes
sensor_changes = []
prev_sensor = df.iloc[0]['VirtualCoreSensor']
for i in range(1, len(df)):
    curr_sensor = df.iloc[i]['VirtualCoreSensor']
    if curr_sensor != prev_sensor:
        sensor_changes.append({
            'index': i,
            'time': df.iloc[i]['Timestamp'],
            'from_sensor': prev_sensor,
            'to_sensor': curr_sensor,
            'temperature': df.iloc[i][core_col]
        })
        prev_sensor = curr_sensor

for change in sensor_changes:
    print(f"\nSensor change at index {change['index']} (time {change['time']:.1f}s):")
    print(f"  From {change['from_sensor']} to {change['to_sensor']}")
    print(f"  Temperature: {change['temperature']:.1f}°C")

print("\n\n3. Looking for extended plateaus or unusual patterns:")
print("-" * 60)

# Find periods where temperature is relatively stable (possible gap between curves)
window_size = 10  # 50 seconds
for i in range(window_size, len(df) - window_size):
    window = df[core_col].iloc[i-window_size:i+window_size]
    std_dev = window.std()
    mean_temp = window.mean()
    
    # Low standard deviation indicates stable temperature
    if std_dev < 2.0 and 20 < mean_temp < 60:  # Stable and in intermediate range
        # Check if this is preceded by cooling and followed by heating
        before_trend = df[core_col].iloc[i-window_size*2:i-window_size].mean()
        after_trend = df[core_col].iloc[i+window_size:i+window_size*2].mean()
        
        if before_trend > mean_temp + 10 and after_trend > mean_temp + 5:
            print(f"\nStable period at index {i} (time {df.iloc[i]['Timestamp']:.1f}s):")
            print(f"  Temperature: {mean_temp:.1f}°C ± {std_dev:.1f}°C")
            print(f"  Before: {before_trend:.1f}°C (cooling from)")
            print(f"  After: {after_trend:.1f}°C (heating to)")

print("\n\n4. Analyzing the specific region around 30-40 minutes:")
print("-" * 60)

# Focus on the likely split point (around 30-40 minutes)
time_30min = 1800  # seconds
time_40min = 2400  # seconds

subset = df[(df['Timestamp'] >= time_30min) & (df['Timestamp'] <= time_40min)]
if len(subset) > 0:
    print(f"\nTemperature profile from 30-40 minutes:")
    for i in range(0, len(subset), 12):  # Every minute
        idx = subset.index[i]
        print(f"  {df.iloc[idx]['Timestamp']/60:.1f} min: {df.iloc[idx][core_col]:.1f}°C, "
              f"change: {df.iloc[idx]['temp_change']:.1f}°C, "
              f"sensor: {df.iloc[idx]['VirtualCoreSensor']}")