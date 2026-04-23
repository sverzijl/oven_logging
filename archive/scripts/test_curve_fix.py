"""Test script to verify the curve extraction fix."""

import pandas as pd
from src.data.loader import ThermalProfileLoader

# Load the data with the fixed extraction method
loader = ThermalProfileLoader()
df, metadata = loader.load_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")

# Check the extracted curves
print("=== Extracted curves with fix ===")
curves = loader.get_all_curves()
for i, curve in enumerate(curves):
    print(f"\nCurve {i+1}:")
    print(f"  Start time: {curve['start_time']:.1f}s")
    print(f"  End time: {curve['end_time']:.1f}s") 
    print(f"  Duration: {curve['duration']:.1f} minutes")
    print(f"  Max temp: {curve['max_temp']:.1f}°C")
    print(f"  Samples: {curve['samples']}")
    
    # Check if the rapid drop at 1470s is now properly handled
    if curve['curve_number'] == 1:
        curve_data = curve['data']
        # Find the last few timestamps
        last_timestamps = curve_data['Timestamp'].tail(5).values
        print(f"  Last 5 timestamps in curve: {last_timestamps}")
        
        # Check if curve ends before or near the rapid drop
        if curve['end_time'] <= 1470:
            print("  ✓ SUCCESS: Curve 1 now ends at or before the rapid drop!")
        else:
            print("  ✗ FAIL: Curve 1 still extends past the rapid drop")
            
        # Show temperature at the end
        end_temp = curve_data['CoreTemperature'].iloc[-1] if 'CoreTemperature' in curve_data.columns else curve_data['CoreAverage'].iloc[-1]
        print(f"  Temperature at curve end: {end_temp:.1f}°C")