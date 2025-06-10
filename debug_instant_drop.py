"""Debug the instant drop detection logic."""

import pandas as pd
from src.data.loader import ThermalProfileLoader

# Load just the raw data
loader = ThermalProfileLoader()
loader.metadata = loader._parse_metadata("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")
loader.data = pd.read_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv", skiprows=10)
loader.data = loader._clean_data(loader.data)
full_df = loader.data

# Get core column
core_col = 'CoreTemperature' if 'CoreTemperature' in full_df.columns else 'CoreAverage'

# Focus on the rapid drop area
print("=== Instant drops around timestamp 1470 ===")
for idx in range(290, 300):
    if idx < len(full_df) - 1:
        curr_temp = full_df.iloc[idx][core_col]
        next_temp = full_df.iloc[idx+1][core_col]
        instant_drop = curr_temp - next_temp
        
        timestamp = full_df.iloc[idx]['Timestamp']
        print(f"Index {idx} -> {idx+1}: {curr_temp:.1f}°C -> {next_temp:.1f}°C (drop: {instant_drop:.1f}°C) at time {timestamp:.0f}s")
        
        if instant_drop > 15:
            print(f"  ^^^ This is a >15°C instant drop!")
        elif instant_drop > 5:
            print(f"  ^^^ This is a >5°C drop")

# Now let's trace the exact logic when j=294 (timestamp 1470)
print("\n=== Tracing detection logic at j=294 ===")
j = 294
peak_idx = 293
search_start = 226

lookback = min(5, j - search_start)
print(f"Lookback: {lookback}")

temp = full_df.iloc[j][core_col]
recent_drop = full_df.iloc[j-lookback][core_col] - temp
time_span = full_df.iloc[j]['Timestamp'] - full_df.iloc[j-lookback]['Timestamp']

print(f"j={j}, j-lookback={j-lookback}")
print(f"Temp at j: {temp:.1f}°C")
print(f"Temp at j-{lookback}: {full_df.iloc[j-lookback][core_col]:.1f}°C")
print(f"Recent drop: {recent_drop:.1f}°C over {time_span:.0f}s")

if time_span > 0:
    drop_rate_per_sec = recent_drop / time_span
    print(f"Drop rate: {drop_rate_per_sec:.3f}°C/s")
    
    if drop_rate_per_sec > 2.0:
        print("✓ Drop rate exceeds 2°C/s threshold!")
        
        # Now trace the inner loop
        print("\nChecking instant drops in reverse:")
        for k in range(j, max(j-lookback-5, peak_idx), -1):
            if k > 0:
                instant_drop = full_df.iloc[k-1][core_col] - full_df.iloc[k][core_col]
                print(f"  k={k}: {full_df.iloc[k-1][core_col]:.1f} -> {full_df.iloc[k][core_col]:.1f} (drop: {instant_drop:.1f})")
                
                if instant_drop > 15:
                    print(f"    -> Would set end_idx = {k-1}")
                    break
                elif instant_drop > 5 and k < j:
                    print(f"    -> Would set end_idx = {k}")
                    break

# The issue might be with the lookback calculation
print("\n=== Issue with lookback? ===")
print(f"When j=294:")
print(f"  j - search_start = {j} - {search_start} = {j - search_start}")
print(f"  lookback = min(5, {j - search_start}) = {lookback}")
print(f"  So we're looking at index {j-lookback} to {j}")
print(f"  That's a {lookback * 5} second window")