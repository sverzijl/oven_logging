#!/usr/bin/env python3
import pandas as pd
import sys
sys.path.insert(0, '.')

# Read the CSV directly
df = pd.read_csv('ProbeData_1000BA3C_2025-05-30 09_46_16.csv', skiprows=10)

# Show available columns
print("Available columns:", df.columns.tolist())
print()

# Use VirtualCoreTemperature if available, otherwise use T1-T4 average
if 'VirtualCoreTemperature' in df.columns:
    core_col = 'VirtualCoreTemperature'
else:
    df[core_col] = df[['T1', 'T2', 'T3', 'T4']].mean(axis=1)
    core_col = 'CoreAverage'

# Look at temperature patterns
print(f"Analyzing temperature patterns using {core_col}...\n")

# Find significant temperature changes
for i in range(1, len(df)):
    if i < len(df) - 1:
        temp_diff = df.iloc[i][core_col] - df.iloc[i-1][core_col]
        
        # Look for rapid rises (potential curve starts)
        if temp_diff > 5:
            print(f"Rapid rise at index {i} (time {df.iloc[i]['Timestamp']:.1f}s):")
            print(f"  {df.iloc[i-1][core_col]:.1f}°C -> {df.iloc[i][core_col]:.1f}°C")
            print(f"  PredictionState: {df.iloc[i]['PredictionState']}")
            print()
        
        # Look for rapid drops (potential curve ends/starts)
        if temp_diff < -10:
            print(f"Rapid drop at index {i} (time {df.iloc[i]['Timestamp']:.1f}s):")
            print(f"  {df.iloc[i-1][core_col]:.1f}°C -> {df.iloc[i][core_col]:.1f}°C")
            
            # Look ahead to see if temperature rises again
            if i + 10 < len(df):
                future_temp = df.iloc[i+10][core_col]
                print(f"  Temperature 50s later: {future_temp:.1f}°C")
                if future_temp > df.iloc[i][core_col] + 5:
                    print(f"  ** POTENTIAL NEW CURVE START **")
            print()

# Check for periods of stable low temperature between curves
print("\nLooking for stable low temperature periods (potential gaps between curves):")
stable_start = None
for i in range(1, len(df)):
    temp = df.iloc[i][core_col]
    prev_temp = df.iloc[i-1][core_col]
    
    if abs(temp - prev_temp) < 2 and temp < 40:  # Stable and low
        if stable_start is None:
            stable_start = i
    else:
        if stable_start is not None and i - stable_start > 5:  # At least 25 seconds of stability
            print(f"Stable period from index {stable_start} to {i-1}")
            print(f"  Time: {df.iloc[stable_start]['Timestamp']:.1f}s - {df.iloc[i-1]['Timestamp']:.1f}s")
            print(f"  Temperature: ~{df.iloc[stable_start:i][core_col].mean():.1f}°C")
            print()
        stable_start = None