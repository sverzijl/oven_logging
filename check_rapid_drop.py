#!/usr/bin/env python3
"""Check for rapid drops in the original data."""

import pandas as pd

# Read the raw CSV
df = pd.read_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv", skiprows=10)

# Find where curve 2 should end based on timestamps
# According to our earlier analysis, the rapid drop happens around line 957 (4725s)
target_time = 4720.0

# Find rows around this time
mask = (df['Timestamp'] >= 4700) & (df['Timestamp'] <= 4750)
subset = df[mask]

print("Data around the rapid drop (Curve 2 end):")
print("Index | Time(s) | VirtualCore | T1    | T2    | T3    | T4    | T5    | T6    | T7    | T8")
print("-" * 100)

for idx, row in subset.iterrows():
    print(f"{idx:5d} | {row['Timestamp']:7.1f} | {row['VirtualCoreTemperature']:11.2f} | "
          f"{row['T1']:5.2f} | {row['T2']:5.2f} | {row['T3']:5.2f} | {row['T4']:5.2f} | "
          f"{row['T5']:5.2f} | {row['T6']:5.2f} | {row['T7']:5.2f} | {row['T8']:5.2f}")
    
    # Check for rapid drops
    if idx > 0:
        prev_core = df.loc[idx-1, 'VirtualCoreTemperature']
        curr_core = row['VirtualCoreTemperature']
        drop = prev_core - curr_core
        if drop > 10:
            print(f"      >>> RAPID DROP DETECTED: {drop:.1f}°C in 5 seconds! <<<")

# Now check where curve 2 actually ends according to the loader
print("\n" + "="*100 + "\n")
print("Now checking what the loader extracted for curve 2...")

from src.data.loader import ThermalProfileLoader
loader = ThermalProfileLoader()
df_loaded = loader.load_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")
curves = loader.get_all_curves()

curve2 = curves[1]['data']
print(f"\nCurve 2 ends at timestamp: {curve2['Timestamp'].iloc[-1]:.1f}s")
print(f"Last 5 rows of curve 2:")
print(curve2[['Timestamp', 'CoreTemperature', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']].tail())