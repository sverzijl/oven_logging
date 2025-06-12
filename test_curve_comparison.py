#!/usr/bin/env python3
"""Test curve comparison with mixed sensor modes."""

import pandas as pd
from src.data.loader import ThermalProfileLoader

def test_curve_comparison():
    """Test that curve comparison respects individual curve settings."""
    
    # Load the multi-curve file
    file_path = 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'
    print(f"\n=== Testing Curve Comparison with {file_path} ===")
    
    loader = ThermalProfileLoader()
    data, metadata = loader.load_csv(file_path)
    
    # Set up different modes for each curve
    print("\n--- Setting up curves with different modes ---")
    
    # Curve 1: Keep dynamic mode (default)
    print("\nCurve 1: Dynamic mode")
    loader.set_current_curve(0)
    assignments1 = loader.get_sensor_assignments_with_overrides(0)
    print(f"  Core: {assignments1['core_sensor']} (dynamic)")
    print(f"  Surface: {assignments1['surface_sensor']} (dynamic)")
    
    # Curve 2: Override with different sensors
    print("\nCurve 2: Override mode")
    loader.set_sensor_override(1, 'core', 'T2')
    loader.set_sensor_override(1, 'surface', 'T5')
    loader.set_current_curve(1)
    assignments2 = loader.get_sensor_assignments_with_overrides(1)
    print(f"  Core: {assignments2['core_sensor']} (override)")
    print(f"  Surface: {assignments2['surface_sensor']} (override)")
    
    # Curve 3: Different override
    print("\nCurve 3: Override mode (different sensors)")
    loader.set_sensor_override(2, 'core', 'T3')
    loader.set_sensor_override(2, 'surface', 'T7')
    loader.set_current_curve(2)
    assignments3 = loader.get_sensor_assignments_with_overrides(2)
    print(f"  Core: {assignments3['core_sensor']} (override)")
    print(f"  Surface: {assignments3['surface_sensor']} (override)")
    
    # Now switch between curves and verify settings persist
    print("\n--- Verifying settings persist when switching curves ---")
    
    # Switch to curve 1
    loader.set_current_curve(0)
    data1 = loader.data
    check1 = loader.get_sensor_assignments_with_overrides(0)
    print(f"\nCurve 1: Has overrides = {check1['has_overrides']}")
    print(f"  Core temp uses: {'VirtualCoreTemperature' if not check1['has_overrides'] else check1['core_sensor']}")
    
    # Switch to curve 2
    loader.set_current_curve(1)
    data2 = loader.data
    check2 = loader.get_sensor_assignments_with_overrides(1)
    print(f"\nCurve 2: Has overrides = {check2['has_overrides']}")
    print(f"  Core temp from T2: {data2['T2'].iloc[0]:.1f}°C")
    print(f"  CoreTemperature: {data2['CoreTemperature'].iloc[0]:.1f}°C")
    print(f"  Match: {abs(data2['T2'].iloc[0] - data2['CoreTemperature'].iloc[0]) < 0.01}")
    
    # Switch to curve 3
    loader.set_current_curve(2)
    data3 = loader.data
    check3 = loader.get_sensor_assignments_with_overrides(2)
    print(f"\nCurve 3: Has overrides = {check3['has_overrides']}")
    print(f"  Core temp from T3: {data3['T3'].iloc[0]:.1f}°C")
    print(f"  CoreTemperature: {data3['CoreTemperature'].iloc[0]:.1f}°C")
    print(f"  Match: {abs(data3['T3'].iloc[0] - data3['CoreTemperature'].iloc[0]) < 0.01}")
    
    # For curve comparison visualization
    print("\n--- Data for Curve Comparison ---")
    print("Each curve maintains its own sensor configuration:")
    print(f"  Curve 1: {assignments1['core_sensor']} (dynamic) -> uses VirtualCoreTemperature")
    print(f"  Curve 2: {assignments2['core_sensor']} (override) -> uses T2 values")
    print(f"  Curve 3: {assignments3['core_sensor']} (override) -> uses T3 values")
    
    # Verify that all curves have standardized columns
    print("\n--- Standardized columns available for all curves ---")
    for i in range(3):
        loader.set_current_curve(i)
        has_std_cols = all(col in loader.data.columns for col in ['CoreTemperature', 'SurfaceTemperature', 'AmbientTemperature'])
        print(f"Curve {i+1}: Standardized columns present = {has_std_cols}")

if __name__ == "__main__":
    test_curve_comparison()