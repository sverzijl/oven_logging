#!/usr/bin/env python3
"""Test script to diagnose zone analysis issue."""

import pandas as pd
from src.data.loader import ThermalProfileLoader
from src.analysis.zone_analysis import ZoneAnalyzer

# Load a sample file
loader = ThermalProfileLoader()
data, metadata = loader.load_csv("ProbeData_100098DE_2025-05-30 13_51_07.csv")

print("Temperature ranges in data:")
print(f"Core temperature: {data['CoreTemperature'].min():.1f}°C to {data['CoreTemperature'].max():.1f}°C")
print(f"Surface temperature: {data['SurfaceTemperature'].min():.1f}°C to {data['SurfaceTemperature'].max():.1f}°C")
print(f"Ambient temperature: {data['AmbientTemperature'].min():.1f}°C to {data['AmbientTemperature'].max():.1f}°C")
print()

# Check T8 (typically surface sensor)
print(f"T8 temperature: {data['T8'].min():.1f}°C to {data['T8'].max():.1f}°C")
print(f"T7 temperature: {data['T7'].min():.1f}°C to {data['T7'].max():.1f}°C")
print()

# Check how many readings exceed 110°C for each
print("Readings above 110°C (crust formation threshold):")
print(f"CoreTemperature: {(data['CoreTemperature'] >= 110).sum()} readings")
print(f"SurfaceTemperature: {(data['SurfaceTemperature'] >= 110).sum()} readings")
print(f"T8: {(data['T8'] >= 110).sum()} readings")
print(f"T7: {(data['T7'] >= 110).sum()} readings")
print()

# Initialize zone analyzer
analyzer = ZoneAnalyzer(data, metadata['sample_period_s'])

# Test the _extract_zone_data method directly for crust formation
from config.constants import TEMPERATURE_ZONES
crust_zone_config = TEMPERATURE_ZONES['CRUST_FORMATION']
print(f"Crust Formation zone config: {crust_zone_config}")

# Manually check what temperature column would be used
if crust_zone_config.get('name') == 'Crust Formation':
    temp_col = 'SurfaceTemperature' if 'SurfaceTemperature' in data.columns else 'SurfaceAverage'
    if temp_col not in data.columns:
        temp_col = 'T8' if 'T8' in data.columns else 'T7'
    print(f"Temperature column selected for Crust Formation: {temp_col}")
    
    # Check the data for this zone
    zone_data = data[
        (data[temp_col] >= crust_zone_config['min']) &
        (data[temp_col] <= crust_zone_config['max'])
    ]
    print(f"Rows in crust formation zone: {len(zone_data)}")