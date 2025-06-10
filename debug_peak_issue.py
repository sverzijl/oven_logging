"""Debug script to understand the peak detection issue."""

import pandas as pd
import numpy as np
from src.data.loader import ThermalProfileLoader

# Load the full data
loader = ThermalProfileLoader()
loader.metadata = loader._parse_metadata("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")
loader.data = pd.read_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv", skiprows=10)
loader.data = loader._clean_data(loader.data)
full_df = loader.data

# Get core column
core_col = 'CoreTemperature' if 'CoreTemperature' in full_df.columns else 'CoreAverage'

# Let's check the temperature profile
print("=== Temperature peaks in the data ===")
print("\nFinding all local maxima...")

# Group by approximate curves based on timestamps
curve1_data = full_df[full_df['Timestamp'] < 2000]
curve2_data = full_df[(full_df['Timestamp'] >= 3000) & (full_df['Timestamp'] < 5000)]
curve3_data = full_df[full_df['Timestamp'] >= 29000]

print(f"\nCurve 1 (0-2000s):")
if len(curve1_data) > 0:
    peak1_idx = curve1_data[core_col].idxmax()
    peak1_temp = curve1_data[core_col].max()
    peak1_time = curve1_data.loc[peak1_idx, 'Timestamp']
    print(f"  Peak: {peak1_temp:.1f}°C at index {peak1_idx} (timestamp {peak1_time:.0f}s)")

print(f"\nCurve 2 (3000-5000s):")
if len(curve2_data) > 0:
    peak2_idx = curve2_data[core_col].idxmax()
    peak2_temp = curve2_data[core_col].max()
    peak2_time = curve2_data.loc[peak2_idx, 'Timestamp']
    print(f"  Peak: {peak2_temp:.1f}°C at index {peak2_idx} (timestamp {peak2_time:.0f}s)")

print(f"\nCurve 3 (29000+s):")
if len(curve3_data) > 0:
    peak3_idx = curve3_data[core_col].idxmax()
    peak3_temp = curve3_data[core_col].max()
    peak3_time = curve3_data.loc[peak3_idx, 'Timestamp']
    print(f"  Peak: {peak3_temp:.1f}°C at index {peak3_idx} (timestamp {peak3_time:.0f}s)")

# Now let's trace what's happening in the extraction method
print("\n=== Simulating curve extraction for first curve ===")

# Start at beginning
i = 0
start_idx = None

# Find curve start
for j in range(i, len(full_df) - 1):
    if full_df[core_col].iloc[j+1] - full_df[core_col].iloc[j] > 5:
        start_idx = j
        break

print(f"Start index: {start_idx} (timestamp {full_df.iloc[start_idx]['Timestamp']:.0f}s)")

# Here's the bug - the original code finds peak across ALL data, not just from start_idx
print("\nBUG FOUND: Original code searches for peak in entire dataset!")
peak_idx_wrong = full_df[core_col].idxmax()
print(f"Wrong peak: index {peak_idx_wrong} (timestamp {full_df.iloc[peak_idx_wrong]['Timestamp']:.0f}s)")

# Correct approach - find peak from start_idx forward until temperature drops significantly
print("\nCorrect approach - search for peak from start_idx:")
peak_idx = start_idx
peak_temp = full_df[core_col].iloc[start_idx]

# Search forward from start until we find a significant drop
consecutive_drops = 0
for j in range(start_idx + 1, len(full_df)):
    current_temp = full_df[core_col].iloc[j]
    
    if current_temp > peak_temp:
        peak_temp = current_temp
        peak_idx = j
        consecutive_drops = 0
    elif peak_temp - current_temp > 20:  # Significant drop from peak
        print(f"Found significant drop at index {j} (timestamp {full_df.iloc[j]['Timestamp']:.0f}s)")
        print(f"Temperature dropped from {peak_temp:.1f}°C to {current_temp:.1f}°C")
        break
    
    # Stop if we've gone too far (e.g., into next curve)
    if j > start_idx + 500 and current_temp < 40:  # If temp drops to room temp
        break

print(f"Correct peak for curve 1: {peak_temp:.1f}°C at index {peak_idx} (timestamp {full_df.iloc[peak_idx]['Timestamp']:.0f}s)")

# Now check the rapid drop detection with correct peak
target_timestamp = 1470
target_idx = full_df[full_df['Timestamp'] == target_timestamp].index[0] if len(full_df[full_df['Timestamp'] == target_timestamp]) > 0 else None

if target_idx is not None and peak_idx < target_idx:
    print(f"\n=== Checking rapid drop with correct peak ===")
    print(f"Target index (1470s): {target_idx}")
    print(f"Peak index: {peak_idx}")
    print(f"Check: {target_idx} > {peak_idx} + 10? {target_idx > peak_idx + 10}")
    
    if target_idx > peak_idx + 10:
        print("✓ Now the condition is met!")