"""Check what happens at j=295 and beyond."""

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

peak_idx = 293
search_start = 226

# Check multiple iterations
print("=== Checking drop rate at each iteration ===")
for j in range(294, 300):
    if j < len(full_df):
        lookback = min(5, j - search_start)
        temp = full_df.iloc[j][core_col]
        recent_drop = full_df.iloc[j-lookback][core_col] - temp
        time_span = full_df.iloc[j]['Timestamp'] - full_df.iloc[j-lookback]['Timestamp']
        
        if time_span > 0:
            drop_rate_per_sec = recent_drop / time_span
            
            print(f"\nj={j} (time={full_df.iloc[j]['Timestamp']:.0f}s):")
            print(f"  Current temp: {temp:.1f}°C")
            print(f"  Lookback to j-{lookback}: {full_df.iloc[j-lookback][core_col]:.1f}°C")
            print(f"  Drop: {recent_drop:.1f}°C over {time_span:.0f}s")
            print(f"  Rate: {drop_rate_per_sec:.3f}°C/s ({drop_rate_per_sec*60:.1f}°C/min)")
            
            if drop_rate_per_sec > 2.0:
                print("  ✓ EXCEEDS 2°C/s threshold!")
                
                # Check where it would find the end
                for k in range(j, max(j-lookback-5, peak_idx), -1):
                    if k > 0:
                        instant_drop = full_df.iloc[k-1][core_col] - full_df.iloc[k][core_col]
                        if instant_drop > 15:
                            print(f"  -> Would set end_idx = {k-1} (time={full_df.iloc[k-1]['Timestamp']:.0f}s)")
                            break
                        elif instant_drop > 5 and k < j:
                            print(f"  -> Would set end_idx = {k} (time={full_df.iloc[k]['Timestamp']:.0f}s)")
                            break