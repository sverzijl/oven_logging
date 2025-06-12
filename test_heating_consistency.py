#!/usr/bin/env python3
"""Test heating consistency calculation."""

from src.data.loader import ThermalProfileLoader
from src.analysis.thermal_analysis import ThermalAnalyzer

# Load the file
loader = ThermalProfileLoader()
df = loader.load_csv("ProbeData_1000BA3C_2025-05-30 17_59_37.csv")

# Test each curve
curves = loader.get_all_curves()

for i, curve_info in enumerate(curves):
    print(f"\n{'='*60}")
    print(f"Curve {i+1} Analysis:")
    print(f"{'='*60}")
    
    # Select this curve
    loader.set_current_curve(i)
    curve_data = loader.data
    
    # Analyze
    analyzer = ThermalAnalyzer(curve_data, loader.metadata, loader=loader)
    
    # Get quality metrics
    metrics = analyzer.calculate_quality_metrics()
    
    print(f"Duration: {curve_info['duration']:.1f} minutes")
    print(f"Max temp: {curve_info['max_temp']:.1f}°C")
    print(f"Heating rate consistency: {metrics.get('heating_rate_consistency', 'N/A')}")
    print(f"Core uniformity CV: {metrics['core_uniformity_cv']:.4f}")
    print(f"Quality score: {metrics['quality_score']:.1f}")
    
    # Check heating rates around the end
    rates = analyzer.calculate_heating_rates()
    print(f"\nLast 10 heating rates (°C/s):")
    last_rates = rates['core_rate'].iloc[-10:].tolist()
    for j, rate in enumerate(last_rates):
        print(f"  {j}: {rate:.4f}")
    
    # Check for extreme values
    extreme_rates = rates[abs(rates['core_rate']) > 0.5]
    if not extreme_rates.empty:
        print(f"\nWARNING: Found {len(extreme_rates)} extreme heating rates!")
        print("First few extreme rates:")
        print(extreme_rates.head())