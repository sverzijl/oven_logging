#!/usr/bin/env python3
import pandas as pd
import numpy as np

# Read the CSV
df = pd.read_csv('ProbeData_1000BA3C_2025-05-30 17_59_37.csv', skiprows=10)

print("Analyzing temperature patterns in the critical region (23-35 minutes)...\n")

# Focus on the region from minute 23 to 35
start_time = 23 * 60  # 1380 seconds
end_time = 35 * 60    # 2100 seconds

subset = df[(df['Timestamp'] >= start_time) & (df['Timestamp'] <= end_time)]

print("Time(min) | Core Temp | Surf Temp | Amb Temp | Core Sensor | State | Core-Amb Delta")
print("-" * 90)

for i in range(0, len(subset), 6):  # Every 30 seconds
    idx = subset.index[i]
    row = df.iloc[idx]
    time_min = row['Timestamp'] / 60
    core_temp = row['VirtualCoreTemperature']
    surf_temp = row['VirtualSurfaceTemperature']
    amb_temp = row['VirtualAmbientTemperature']
    core_sensor = row['VirtualCoreSensor']
    state = row['PredictionState']
    delta = core_temp - amb_temp
    
    print(f"{time_min:9.1f} | {core_temp:9.1f} | {surf_temp:9.1f} | {amb_temp:8.1f} | {core_sensor:11} | {state:15} | {delta:6.1f}")

# Now let's look for the telltale signs of probe removal and reinsertion
print("\n\nAnalyzing temperature gradients and relationships:")
print("-" * 60)

# Calculate gradients
df['core_ambient_delta'] = df['VirtualCoreTemperature'] - df['VirtualAmbientTemperature']
df['core_surface_delta'] = df['VirtualCoreTemperature'] - df['VirtualSurfaceTemperature']

# Look for anomalies in the gradients
for i in range(len(df) - 10):
    # Check for situations where core-ambient delta becomes very small or negative
    # This indicates the probe is out of the product
    if i > 100:  # Skip the beginning
        delta = df.iloc[i]['core_ambient_delta']
        prev_delta = df.iloc[i-10]['core_ambient_delta']
        
        # Large drop in core-ambient delta suggests probe removal
        if prev_delta > 20 and delta < 5 and df.iloc[i]['VirtualCoreTemperature'] < 40:
            print(f"\nPotential probe removal at index {i} (time {df.iloc[i]['Timestamp']/60:.1f} min):")
            print(f"  Core-Ambient delta dropped from {prev_delta:.1f}°C to {delta:.1f}°C")
            print(f"  Core temp: {df.iloc[i]['VirtualCoreTemperature']:.1f}°C")
            
            # Look ahead for reinsertion
            for j in range(i+1, min(i+100, len(df))):
                future_delta = df.iloc[j]['core_ambient_delta']
                if future_delta > 10 and df.iloc[j]['VirtualCoreTemperature'] > df.iloc[i]['VirtualCoreTemperature'] + 5:
                    print(f"  Potential reinsertion at index {j} (time {df.iloc[j]['Timestamp']/60:.1f} min)")
                    print(f"  Core-Ambient delta increased to {future_delta:.1f}°C")
                    print(f"  Core temp: {df.iloc[j]['VirtualCoreTemperature']:.1f}°C")
                    break

# Look at the rate of change of the core-ambient delta
print("\n\nAnalyzing rate of change of temperature differentials:")
print("-" * 60)

df['delta_change_rate'] = df['core_ambient_delta'].diff()

# Find large negative changes in the delta (probe removal signature)
for i in range(10, len(df) - 10):
    rate = df.iloc[i]['delta_change_rate']
    if rate < -5:  # Large negative change in delta
        print(f"\nLarge delta change at index {i} (time {df.iloc[i]['Timestamp']/60:.1f} min):")
        print(f"  Delta change rate: {rate:.1f}°C")
        print(f"  Core: {df.iloc[i]['VirtualCoreTemperature']:.1f}°C")
        print(f"  Ambient: {df.iloc[i]['VirtualAmbientTemperature']:.1f}°C")
        print(f"  Core-Ambient: {df.iloc[i]['core_ambient_delta']:.1f}°C")