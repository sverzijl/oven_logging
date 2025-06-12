#!/usr/bin/env python3
"""Test curve extraction with the problematic file."""

import pandas as pd
from src.data.loader import ThermalProfileLoader

# Load the file
loader = ThermalProfileLoader()
df = loader.load_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")

# Get all curves
curves = loader.get_all_curves()

print(f"\nTotal curves extracted: {len(curves)}")

# Examine each curve
for curve_info in curves:
    curve_data = curve_info['data']
    print(f"\nCurve {curve_info['curve_number']}:")
    print(f"  Duration: {curve_info['duration']:.1f} minutes")
    print(f"  Max temp: {curve_info['max_temp']:.1f}°C")
    print(f"  Start temp: {curve_data['CoreTemperature'].iloc[0]:.1f}°C")
    print(f"  End temp: {curve_data['CoreTemperature'].iloc[-1]:.1f}°C")
    print(f"  Samples: {curve_info['samples']}")
    
    # Check the end of the curve for rapid drops
    if len(curve_data) > 10:
        last_10 = curve_data['CoreTemperature'].iloc[-10:].tolist()
        print(f"  Last 10 temps: {[f'{t:.1f}' for t in last_10]}")
        
        # Check for rapid drop at the end
        for i in range(len(last_10)-1):
            drop = last_10[i] - last_10[i+1]
            if drop > 10:
                print(f"  WARNING: Rapid drop of {drop:.1f}°C detected at end!")