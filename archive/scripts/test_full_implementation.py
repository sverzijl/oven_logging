#!/usr/bin/env python3
"""Comprehensive test of sensor override implementation."""

import pandas as pd
import numpy as np
from src.data.loader import ThermalProfileLoader
from src.analysis.thermal_analysis import ThermalAnalyzer
from src.analysis.s_curve_analysis import SCurveAnalyzer
from src.visualization.plots import ThermalPlotter

def test_full_implementation():
    """Test the complete sensor override implementation."""
    
    # Load the multi-curve file
    file_path = 'ProbeData_1000BA3C_2025-05-30 17_59_37.csv'
    print(f"\n=== Testing Full Implementation with {file_path} ===")
    
    loader = ThermalProfileLoader()
    data, metadata = loader.load_csv(file_path)
    
    # Test Curve 1
    print("\n=== Testing Curve 1 ===")
    loader.set_current_curve(0)
    data = loader.data
    
    print("\n--- Dynamic Mode ---")
    # Get assignments
    assignments = loader.get_sensor_assignments_with_overrides(0)
    print(f"Core sensor: {assignments['core_sensor']}")
    print(f"Surface sensor: {assignments['surface_sensor']}")
    print(f"Internal sensors: {assignments['internal_sensors']}")
    print(f"Ambient sensors: {assignments['ambient_sensors']}")
    
    # Check temperature columns
    print(f"\nVirtual columns present: {all(col in data.columns for col in ['VirtualCoreTemperature', 'VirtualSurfaceTemperature', 'VirtualAmbientTemperature'])}")
    print(f"Standard columns present: {all(col in data.columns for col in ['CoreTemperature', 'SurfaceTemperature', 'AmbientTemperature'])}")
    
    # Test thermal analysis
    analyzer = ThermalAnalyzer(data, metadata, loader)
    metrics = analyzer.calculate_quality_metrics()
    print(f"\nThermal metrics calculated: {list(metrics.keys())}")
    
    # Test S-curve analysis
    s_curve_analyzer = SCurveAnalyzer(data, metadata, loader)
    report = s_curve_analyzer.generate_optimization_report()
    print(f"S-curve landmarks: {list(report['landmarks'].keys())}")
    
    print("\n--- Override Mode ---")
    # Apply overrides
    loader.set_sensor_override(0, 'core', 'T3')
    loader.set_sensor_override(0, 'surface', 'T6')
    
    # Check updated assignments
    assignments = loader.get_sensor_assignments_with_overrides(0)
    print(f"Core sensor: {assignments['core_sensor']}")
    print(f"Surface sensor: {assignments['surface_sensor']}")
    print(f"Internal sensors: {assignments['internal_sensors']}")
    print(f"Ambient sensors: {assignments['ambient_sensors']}")
    
    # Check temperature values changed
    print(f"\nCore temp (first 5): {data['CoreTemperature'].head().tolist()}")
    print(f"Core temp from T3: {data['T3'].head().tolist()}")
    print(f"Match: {np.allclose(data['CoreTemperature'].head(), data['T3'].head())}")
    
    # Test visualization
    print("\n--- Testing Visualization ---")
    plotter = ThermalPlotter()
    
    # Build sensor roles
    sensor_roles = {}
    for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']:
        if sensor == assignments['core_sensor']:
            sensor_roles[sensor] = 'core'
        elif sensor == assignments['surface_sensor']:
            sensor_roles[sensor] = 'surface'
        elif sensor in assignments['internal_sensors']:
            sensor_roles[sensor] = 'internal'
        elif sensor in assignments['ambient_sensors']:
            sensor_roles[sensor] = 'ambient'
    
    print(f"Sensor roles: {sensor_roles}")
    
    # Test S-curve with internal spread
    internal_sensors = assignments['internal_sensors']
    if len(internal_sensors) > 1:
        print(f"Internal sensors for spread visualization: {internal_sensors}")
        # Check data availability
        internal_data = data[internal_sensors]
        print(f"Internal temp range at start: {internal_data.iloc[0].min():.1f} - {internal_data.iloc[0].max():.1f}°C")
        print(f"Internal temp range at peak: {internal_data.iloc[data['CoreTemperature'].idxmax()].min():.1f} - {internal_data.iloc[data['CoreTemperature'].idxmax()].max():.1f}°C")
    
    # Clear overrides
    loader.clear_sensor_overrides(0)
    print("\n--- After Clearing Overrides ---")
    print(f"Has overrides: {loader.get_sensor_assignments_with_overrides(0)['has_overrides']}")

if __name__ == "__main__":
    test_full_implementation()