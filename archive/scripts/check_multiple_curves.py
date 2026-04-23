#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from src.data.loader import ThermalProfileLoader

# Check each CSV file
csv_files = [
    'ProbeData_1000BA3C_2025-05-30 17_59_37.csv',  # Largest file
    'ProbeData_100098DE_2025-05-30 13_51_07.csv',  # Medium file
    'ProbeData_1000BA3C_2025-05-30 09_46_16.csv'   # Original file
]

for csv_file in csv_files:
    print(f"\n{'='*60}")
    print(f"Analyzing: {csv_file}")
    print('='*60)
    
    try:
        loader = ThermalProfileLoader()
        loader.load_csv(csv_file)
        
        print(f'Number of curves detected: {loader.get_curve_count()}')
        
        for i, curve in enumerate(loader.all_curves):
            print(f'\nCurve {i+1}:')
            print(f'  Duration: {curve["duration"]:.1f} minutes')
            print(f'  Max temp: {curve["max_temp"]:.1f}°C')
            print(f'  Samples: {curve["samples"]}')
            print(f'  Original time range: {curve["start_time"]:.1f}s - {curve["end_time"]:.1f}s')
            
    except Exception as e:
        print(f"Error loading {csv_file}: {e}")