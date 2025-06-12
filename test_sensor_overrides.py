#!/usr/bin/env python3
"""Test script for sensor override functionality."""

import pandas as pd
from src.data.loader import ThermalProfileLoader

def test_sensor_overrides():
    """Test the sensor override functionality with multi-curve file."""
    
    # Load the multi-curve file
    file_path = 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'
    print(f"\n=== Loading file: {file_path} ===")
    
    loader = ThermalProfileLoader()
    data, metadata = loader.load_csv(file_path)
    
    # Check how many curves were found
    num_curves = loader.get_curve_count()
    print(f"\nFound {num_curves} curves in the file")
    
    # Test each curve
    for curve_idx in range(num_curves):
        print(f"\n=== Testing Curve {curve_idx + 1} ===")
        
        # Set current curve
        loader.set_current_curve(curve_idx)
        curve_info = loader.get_current_curve_info()
        print(f"Duration: {curve_info['duration']:.1f} minutes")
        print(f"Max temp: {curve_info['max_temp']:.1f}°C")
        
        # Get automatic assignments
        print("\n--- Automatic (Dynamic) Mode ---")
        
        # Show raw sensor assignments first
        raw_assignments = loader.get_sensor_assignments()
        print(f"Raw assignments from CSV:")
        print(f"  Core: {raw_assignments.get('core')}")
        print(f"  Surface: {raw_assignments.get('surface')}")
        print(f"  Ambient: {raw_assignments.get('ambient')}")
        
        auto_assignments = loader.get_sensor_assignments_with_overrides(curve_idx)
        print(f"\nProcessed assignments:")
        print(f"  Core sensor: {auto_assignments.get('core_sensor')}")
        print(f"  Surface sensor: {auto_assignments.get('surface_sensor')}")
        print(f"  Internal sensors: {auto_assignments.get('internal_sensors')}")
        print(f"  Ambient sensors: {auto_assignments.get('ambient_sensors')}")
        
        # Test manual override
        print("\n--- Testing Manual Override ---")
        # Set overrides: core=T2, surface=T5
        loader.set_sensor_override(curve_idx, 'core', 'T2')
        loader.set_sensor_override(curve_idx, 'surface', 'T5')
        
        # Get assignments after override
        override_assignments = loader.get_sensor_assignments_with_overrides(curve_idx)
        print(f"Has overrides: {override_assignments.get('has_overrides')}")
        print(f"Core sensor: {override_assignments.get('core_sensor')}")
        print(f"Surface sensor: {override_assignments.get('surface_sensor')}")
        print(f"Internal sensors: {override_assignments.get('internal_sensors')}")
        print(f"Ambient sensors: {override_assignments.get('ambient_sensors')}")
        
        # Check temperature columns
        print("\n--- Temperature Columns ---")
        data = loader.data
        
        # Show what's being used for temperature calculations
        if curve_idx in loader._sensor_overrides:
            print("Using override mode")
            print(f"  Core from sensor: {loader.get_core_sensor(curve_idx)}")
            print(f"  Surface from sensor: {loader.get_surface_sensor(curve_idx)}")
            print(f"  Ambient from max of: {loader.get_ambient_sensors(curve_idx)}")
        else:
            print("Using dynamic mode (Virtual*Temperature columns)")
            # Show which sensors are active at start
            if 'VirtualCoreSensor' in data.columns:
                print(f"  Core sensor at start: {data['VirtualCoreSensor'].iloc[0]}")
                print(f"  Surface sensor at start: {data['VirtualSurfaceSensor'].iloc[0]}")
                print(f"  Ambient sensor at start: {data['VirtualAmbientSensor'].iloc[0]}")
        
        print(f"\nTemperature values:")
        print(f"  CoreTemperature (first 5): {data['CoreTemperature'].head().tolist()}")
        print(f"  SurfaceTemperature (first 5): {data['SurfaceTemperature'].head().tolist()}")
        if 'AmbientTemperature' in data.columns:
            print(f"  AmbientTemperature (first 5): {data['AmbientTemperature'].head().tolist()}")
        
        # Clear overrides
        print("\n--- Clearing Overrides ---")
        loader.clear_sensor_overrides(curve_idx)
        reset_assignments = loader.get_sensor_assignments_with_overrides(curve_idx)
        print(f"Has overrides after reset: {reset_assignments.get('has_overrides')}")
        print(f"Core sensor after reset: {reset_assignments.get('core_sensor')}")

if __name__ == "__main__":
    test_sensor_overrides()