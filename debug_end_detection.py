"""Debug the end detection logic more carefully."""

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

# Add the temp metrics
full_df['temp_change'] = full_df[core_col].diff()
full_df['temp_smooth'] = full_df[core_col].rolling(window=5, center=True).mean().fillna(full_df[core_col])

# Focus on curve 1
start_idx = 13  # Known start
peak_idx = 293  # Known peak at 1465s

# Search start (after 70°C)
search_start = None
for j in range(start_idx, peak_idx):
    if full_df.iloc[j][core_col] > 70:
        search_start = j
        break

print(f"Search start: index {search_start} (timestamp {full_df.iloc[search_start]['Timestamp']:.0f}s)")
print(f"Peak: index {peak_idx} (timestamp {full_df.iloc[peak_idx]['Timestamp']:.0f}s)")

# Now trace through the end detection logic
print("\n=== Tracing end detection logic ===")

# The rapid drop happens at index 294 (timestamp 1470)
rapid_drop_idx = 294
print(f"\nRapid drop at index {rapid_drop_idx} (timestamp {full_df.iloc[rapid_drop_idx]['Timestamp']:.0f}s)")
print(f"Temperature: {full_df.iloc[rapid_drop_idx-1][core_col]:.1f}°C -> {full_df.iloc[rapid_drop_idx][core_col]:.1f}°C")

# Check condition 3 logic
j = rapid_drop_idx
print(f"\nChecking condition 3 at j={j}:")
print(f"  j > peak_idx + 10? {j} > {peak_idx + 10} = {j > peak_idx + 10}")

if j > peak_idx + 10:
    lookback = min(5, j - search_start)
    print(f"  Lookback: {lookback}")
    
    temp = full_df.iloc[j][core_col]
    recent_drop = full_df.iloc[j-lookback][core_col] - temp
    time_span = full_df.iloc[j]['Timestamp'] - full_df.iloc[j-lookback]['Timestamp']
    
    print(f"  Temp at j={j}: {temp:.1f}°C")
    print(f"  Temp at j-{lookback}={j-lookback}: {full_df.iloc[j-lookback][core_col]:.1f}°C")
    print(f"  Recent drop: {recent_drop:.1f}°C over {time_span}s")
    
    if time_span > 0:
        drop_rate_per_sec = recent_drop / time_span
        print(f"  Drop rate: {drop_rate_per_sec:.3f}°C/s ({drop_rate_per_sec*60:.1f}°C/min)")
        print(f"  Exceeds 2°C/s threshold? {drop_rate_per_sec > 2.0}")

# The issue is that j=294 is only 1 more than peak_idx=293
# So j > peak_idx + 10 is False!

print("\n=== The issue ===")
print(f"The rapid drop occurs immediately after the peak!")
print(f"Peak at index {peak_idx}, drop at index {rapid_drop_idx}")
print(f"Difference: {rapid_drop_idx - peak_idx} samples")
print("The condition 'j > peak_idx + 10' prevents detecting drops that occur soon after the peak.")

# Let's check what the actual end_idx ends up being
print("\n=== Checking where the curve actually ends ===")
# Run through the full logic
end_idx = None
for j in range(search_start + 1, len(full_df)):
    temp = full_df.iloc[j][core_col]
    
    # Check all conditions
    # Condition 1: Room temperature
    if j >= search_start + 20 and temp < 35 and peak_idx > 0 and full_df.iloc[peak_idx][core_col] - temp > 50:
        print(f"\nCondition 1 triggered at index {j}")
        break
        
    # Condition 3: Rapid drop (but with the problematic j > peak_idx + 10 check)
    if j > peak_idx + 10:
        lookback = min(5, j - search_start)
        if lookback > 0:
            recent_drop = full_df.iloc[j-lookback][core_col] - temp
            time_span = full_df.iloc[j]['Timestamp'] - full_df.iloc[j-lookback]['Timestamp']
            if time_span > 0:
                drop_rate_per_sec = recent_drop / time_span
                if drop_rate_per_sec > 2.0:
                    print(f"\nCondition 3 would trigger at index {j}")
                    # But let's keep checking...
                    
    # Show some key points
    if j in [294, 300, 304, 310]:
        print(f"  Index {j}: temp={temp:.1f}°C, time={full_df.iloc[j]['Timestamp']:.0f}s")