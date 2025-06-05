#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from src.data.loader import ThermalProfileLoader

# Load the CSV
print("Loading CSV file...")
loader = ThermalProfileLoader()
loader.load_csv('ProbeData_1000BA3C_2025-05-30 09_46_16.csv')

# Check what curves were detected
print(f'\nNumber of curves detected: {loader.get_curve_count()}')
print()

# Print info about each curve
for i, curve in enumerate(loader.all_curves):
    print(f'Curve {i+1}:')
    print(f'  Start index: {curve["start_idx"]}')
    print(f'  End index: {curve["end_idx"]}')
    print(f'  Duration: {curve["duration"]:.1f} minutes')
    print(f'  Max temp: {curve["max_temp"]:.1f}°C')
    print(f'  Samples: {curve["samples"]}')
    
    # Check the data at start and end
    data = curve['data']
    print(f'  Start temp: {data.iloc[0]["CoreAverage"]:.1f}°C')
    print(f'  End temp: {data.iloc[-1]["CoreAverage"]:.1f}°C')
    
    # Look at temperature around the end to see if there's another curve
    if i == 0:  # First curve
        print("\n  Checking for potential second curve within first curve:")
        # Look for significant temperature drops
        temps = data['CoreAverage'].values
        for j in range(1, len(temps)):
            if temps[j-1] - temps[j] > 20:  # 20°C drop
                print(f"    Found 20°C drop at index {j}: {temps[j-1]:.1f}°C -> {temps[j]:.1f}°C")
                print(f"    Time: {data.iloc[j]['TimeMinutes']:.1f} minutes")
    print()