"""Debug script to understand why curve extraction misses the rapid drop at 1470 seconds."""

import pandas as pd
import numpy as np
from src.data.loader import ThermalProfileLoader

# Load the data
loader = ThermalProfileLoader()
df, metadata = loader.load_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")

# Get the full data before curve extraction
loader_full = ThermalProfileLoader()
# Read data without curve extraction
loader_full.metadata = loader_full._parse_metadata("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")
loader_full.data = pd.read_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv", skiprows=10)
loader_full.data = loader_full._clean_data(loader_full.data)
full_df = loader_full.data

# Focus on the area around the rapid drop
drop_area = full_df[(full_df['Timestamp'] >= 1450) & (full_df['Timestamp'] <= 1500)].copy()

print("=== Data around the rapid drop (1450-1500 seconds) ===")
print(f"Rows in this range: {len(drop_area)}")
print("\nTimestamp  TimeMin  CoreTemp  T1      T2      Drop")
print("-" * 60)

prev_core = None
for idx, row in drop_area.iterrows():
    core_temp = row['CoreTemperature'] if 'CoreTemperature' in row else row['VirtualCoreTemperature']
    drop = core_temp - prev_core if prev_core is not None else 0
    print(f"{row['Timestamp']:8.0f}  {row['TimeMinutes']:7.1f}  {core_temp:7.1f}  {row['T1']:6.1f}  {row['T2']:6.1f}  {drop:6.1f}")
    prev_core = core_temp

# Now let's trace through the curve extraction logic
print("\n=== Tracing curve extraction logic ===")

# Get core column
core_col = 'CoreTemperature' if 'CoreTemperature' in full_df.columns else 'CoreAverage'
print(f"Using core column: {core_col}")

# Add the temp metrics
full_df['temp_change'] = full_df[core_col].diff()
full_df['temp_smooth'] = full_df[core_col].rolling(window=5, center=True).mean().fillna(full_df[core_col])

# Find the peak
peak_idx = full_df[core_col].idxmax()
peak_temp = full_df[core_col].max()
peak_time = full_df.loc[peak_idx, 'Timestamp']
print(f"\nPeak: {peak_temp:.1f}°C at index {peak_idx} (timestamp {peak_time:.0f}s)")

# Check what happens in the rapid drop detection
print("\n=== Checking End Condition 3 (rapid drop) ===")

# The search should start after reaching 70°C
search_start = None
for j in range(0, peak_idx):
    if full_df.iloc[j][core_col] > 70:
        search_start = j
        break

print(f"Search start index: {search_start} (timestamp {full_df.iloc[search_start]['Timestamp']:.0f}s)")

# Now check the drop detection around timestamp 1470
target_timestamp = 1470
target_idx = full_df[full_df['Timestamp'] == target_timestamp].index[0] if len(full_df[full_df['Timestamp'] == target_timestamp]) > 0 else None

if target_idx is not None:
    print(f"\nTarget index (1470s): {target_idx}")
    
    # Check if we meet the condition j > peak_idx + 10
    if target_idx > peak_idx + 10:
        print(f"✓ Condition met: {target_idx} > {peak_idx} + 10")
        
        # Calculate drop rate
        lookback = min(5, target_idx - search_start)
        print(f"Lookback: {lookback}")
        
        if lookback > 0:
            temp = full_df.iloc[target_idx][core_col]
            recent_drop = full_df.iloc[target_idx-lookback][core_col] - temp
            time_span = full_df.iloc[target_idx]['Timestamp'] - full_df.iloc[target_idx-lookback]['Timestamp']
            
            print(f"Temperature at index {target_idx}: {temp:.1f}°C")
            print(f"Temperature at index {target_idx-lookback}: {full_df.iloc[target_idx-lookback][core_col]:.1f}°C")
            print(f"Recent drop: {recent_drop:.1f}°C over {time_span:.0f}s")
            
            if time_span > 0:
                drop_rate_per_sec = recent_drop / time_span
                print(f"Drop rate: {drop_rate_per_sec:.2f}°C/second ({drop_rate_per_sec*60:.1f}°C/min)")
                
                if drop_rate_per_sec > 2.0:
                    print("✓ Drop rate exceeds 2°C/second threshold!")
                    
                    # Check the instant drops
                    print("\nChecking instant drops:")
                    for k in range(target_idx, max(target_idx-lookback-5, peak_idx), -1):
                        if k > 0:
                            instant_drop = full_df.iloc[k-1][core_col] - full_df.iloc[k][core_col]
                            print(f"  Index {k-1} -> {k}: {full_df.iloc[k-1][core_col]:.1f} -> {full_df.iloc[k][core_col]:.1f} (drop: {instant_drop:.1f}°C)")
                            if instant_drop > 15:
                                print(f"    ✓ Found instant drop > 15°C at index {k-1}!")
                                break
                            elif instant_drop > 5 and k < target_idx:
                                print(f"    ✓ Found sustained drop > 5°C at index {k}!")
                                break
    else:
        print(f"✗ Condition NOT met: {target_idx} <= {peak_idx} + 10")

# Check the actual curves that were extracted
print("\n=== Extracted curves ===")
curves = loader.get_all_curves()
for i, curve in enumerate(curves):
    print(f"\nCurve {i+1}:")
    print(f"  Start time: {curve['start_time']:.1f}s")
    print(f"  End time: {curve['end_time']:.1f}s") 
    print(f"  Duration: {curve['duration']:.1f} minutes")
    print(f"  Max temp: {curve['max_temp']:.1f}°C")
    print(f"  End index in original data: {curve['end_idx']}")
    
    # Check what temperature is at the end
    if curve['end_idx'] < len(full_df):
        end_temp = full_df.iloc[curve['end_idx']][core_col]
        print(f"  Temperature at end: {end_temp:.1f}°C")