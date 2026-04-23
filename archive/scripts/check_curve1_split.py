#!/usr/bin/env python3
import pandas as pd

# Read the CSV
df = pd.read_csv('ProbeData_1000BA3C_2025-05-30 17_59_37.csv', skiprows=10)

# Look at the region where curve 1 is being split (around index 213, 17.8 min)
print("Examining why curve 1 is being split around 17.8 minutes...")
print("\nData around index 213:")
print("Index | Time(min) | Core Temp | Ambient | Delta | Sensor")
print("-" * 60)

for i in range(200, 230):
    row = df.iloc[i]
    time_min = row['Timestamp'] / 60
    core = row['VirtualCoreTemperature']
    ambient = row['VirtualAmbientTemperature']
    delta = core - ambient
    sensor = row['VirtualCoreSensor']
    
    # Mark the split point
    marker = " <-- Split here" if i == 213 else ""
    print(f"{i:5} | {time_min:9.1f} | {core:9.1f} | {ambient:7.1f} | {delta:6.1f} | {sensor}{marker}")

# Now look at what happens between curves 1 and 2
print("\n\nData between end of 'curve 1' and start of 'curve 2':")
print("Index | Time(min) | Core Temp | State")
print("-" * 40)

for i in range(213, 644, 50):  # Every 50 samples
    if i < len(df):
        row = df.iloc[i]
        time_min = row['Timestamp'] / 60
        core = row['VirtualCoreTemperature']
        state = row['PredictionState']
        print(f"{i:5} | {time_min:9.1f} | {core:9.1f} | {state}")

# Check if the temperature continues rising after index 213
print("\n\nChecking if temperature continues rising after the split:")
temps_after_split = df.iloc[214:300]['VirtualCoreTemperature']
max_after = temps_after_split.max()
max_idx = temps_after_split.idxmax()
print(f"Max temperature after split: {max_after:.1f}°C at index {max_idx} (time {df.iloc[max_idx]['Timestamp']/60:.1f} min)")

# This should show that curves 1 and 2 are actually the same curve