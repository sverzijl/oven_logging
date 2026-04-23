#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from src.data.loader import ThermalProfileLoader

# Test on the problematic file
print("Testing improved curve detection on ProbeData_1000BA3C_2025-05-30 17_59_37.csv")
print("=" * 70)

loader = ThermalProfileLoader()
loader.load_csv('ProbeData_1000BA3C_2025-05-30 17_59_37.csv')

print(f'\n\nSummary: Detected {loader.get_curve_count()} curves')

for i, curve in enumerate(loader.all_curves):
    print(f"\nCurve {i+1} details:")
    print(f"  Original time range: {curve['start_time']/60:.1f} - {curve['end_time']/60:.1f} minutes")
    
    # Show start and end temperatures
    data = curve['data']
    start_temp = data.iloc[0]['CoreAverage']
    end_temp = data.iloc[-1]['CoreAverage']
    print(f"  Temperature range: {start_temp:.1f}°C -> {curve['max_temp']:.1f}°C -> {end_temp:.1f}°C")