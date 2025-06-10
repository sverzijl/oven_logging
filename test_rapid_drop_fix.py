"""Test specifically for the rapid drop issue."""

import pandas as pd
from src.data.loader import ThermalProfileLoader

# Load the data
loader = ThermalProfileLoader()
df, metadata = loader.load_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")

# Get all curves
curves = loader.get_all_curves()

print("=== Testing rapid drop detection fix ===")
print(f"Number of curves found: {len(curves)}")

# Check curve 1 specifically
if len(curves) > 0:
    curve1 = curves[0]
    print(f"\nCurve 1 details:")
    print(f"  Start time: {curve1['start_time']:.1f}s ({curve1['start_time']/60:.1f} min)")
    print(f"  End time: {curve1['end_time']:.1f}s ({curve1['end_time']/60:.1f} min)")
    print(f"  Duration: {curve1['duration']:.1f} minutes")
    print(f"  Max temperature: {curve1['max_temp']:.1f}°C")
    
    # Check if it ends before the rapid drop at 1470s
    if curve1['end_time'] < 1470:
        print(f"\n✓ SUCCESS: Curve ends at {curve1['end_time']:.0f}s, before the rapid drop at 1470s")
        print(f"  The curve properly ends {1470 - curve1['end_time']:.0f} seconds before the drop")
    else:
        print(f"\n✗ FAIL: Curve ends at {curve1['end_time']:.0f}s, AFTER the rapid drop at 1470s")
    
    # Show the last few data points
    curve_data = curve1['data']
    print(f"\nLast 5 data points in curve 1:")
    print("Time(s) | Time(min) | CoreTemp | T1")
    print("-" * 40)
    for idx in range(-5, 0):
        row = curve_data.iloc[idx]
        print(f"{row['Timestamp']:7.0f} | {row['TimeMinutes']:9.1f} | {row['CoreTemperature']:8.1f} | {row['T1']:6.1f}")

# Also check the original problem statement
print("\n=== Original problem check ===")
print("The test showed:")
print("- Maximum temperature drop: -20.0°C at 23.4 minutes")
print("- Drop rate: -240.6°C/min")
print("- Expected: Curve should end before 23.4 minutes")
print(f"\nActual result: Curve 1 duration is {curve1['duration']:.1f} minutes")
if curve1['duration'] < 23.4:
    print("✓ SUCCESS: Curve ends before the rapid drop point!")
else:
    print("✗ FAIL: Curve still extends past the rapid drop point")