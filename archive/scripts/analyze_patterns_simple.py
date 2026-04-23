#!/usr/bin/env python3
"""Simple analysis of temperature patterns without external dependencies."""

import csv

def analyze_temperature_patterns(file_path):
    """Analyze temperature data to identify potential curve boundaries."""
    
    data = []
    with open(file_path, 'r') as f:
        # Skip header lines
        for _ in range(11):
            next(f)
        
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    
    print(f"Total data points: {len(data)}")
    print(f"Time range: {data[0]['Timestamp']}s to {data[-1]['Timestamp']}s")
    
    # Analyze PredictionState transitions
    print("\nPredictionState Transitions:")
    prev_state = None
    for i, row in enumerate(data):
        curr_state = row['PredictionState']
        if curr_state != prev_state:
            print(f"  Row {i+12}, Time {row['Timestamp']}s: {curr_state}")
            print(f"    Core temp: {row['VirtualCoreTemperature']}°C")
        prev_state = curr_state
    
    # Find temperature patterns
    print("\nCore Temperature Patterns:")
    max_temp = 0
    max_row = 0
    max_time = 0
    
    for i, row in enumerate(data):
        temp = float(row['VirtualCoreTemperature'])
        if temp > max_temp:
            max_temp = temp
            max_row = i + 12
            max_time = row['Timestamp']
    
    print(f"  Peak temperature: {max_temp:.2f}°C at {max_time}s (row {max_row})")
    
    # Look for significant drops
    print("\nSignificant Temperature Changes:")
    prev_temp = None
    
    for i, row in enumerate(data):
        curr_temp = float(row['VirtualCoreTemperature'])
        
        if prev_temp is not None:
            change = curr_temp - prev_temp
            
            # Large drops (>10°C)
            if change < -10:
                print(f"  MAJOR DROP at row {i+12}, time {row['Timestamp']}s:")
                print(f"    {prev_temp:.1f}°C → {curr_temp:.1f}°C (drop of {abs(change):.1f}°C)")
                print(f"    PredictionState: {row['PredictionState']}")
                
                # Check next few rows for continued drop or rise
                print("    Following temperatures:")
                for j in range(min(5, len(data) - i - 1)):
                    next_row = data[i + j + 1]
                    next_temp = float(next_row['VirtualCoreTemperature'])
                    print(f"      {next_row['Timestamp']}s: {next_temp:.1f}°C")
            
            # Rapid rises (>5°C)
            elif change > 5:
                print(f"  Rapid rise at row {i+12}, time {row['Timestamp']}s:")
                print(f"    {prev_temp:.1f}°C → {curr_temp:.1f}°C (rise of {change:.1f}°C)")
                print(f"    PredictionState: {row['PredictionState']}")
        
        prev_temp = curr_temp
    
    # Analyze sensor assignments
    print("\nVirtual Sensor Assignments:")
    sensor_changes = []
    prev_core_sensor = None
    
    for i, row in enumerate(data):
        curr_core_sensor = row['VirtualCoreSensor']
        if curr_core_sensor != prev_core_sensor:
            sensor_changes.append((i+12, row['Timestamp'], curr_core_sensor))
        prev_core_sensor = curr_core_sensor
    
    for row, time, sensor in sensor_changes:
        print(f"  Row {row}, time {time}s: Core sensor = {sensor}")
    
    # Look for potential second curve
    print("\nSearching for potential second curve after major drop...")
    found_major_drop = False
    drop_index = 0
    
    for i, row in enumerate(data[1:], 1):
        curr_temp = float(row['VirtualCoreTemperature'])
        prev_temp = float(data[i-1]['VirtualCoreTemperature'])
        
        if curr_temp - prev_temp < -10:
            found_major_drop = True
            drop_index = i
            break
    
    if found_major_drop:
        print(f"  Major drop found at index {drop_index + 11}")
        
        # Check if temperature rises again after drop
        min_temp_after_drop = float('inf')
        min_index = drop_index
        
        for i in range(drop_index, len(data)):
            temp = float(data[i]['VirtualCoreTemperature'])
            if temp < min_temp_after_drop:
                min_temp_after_drop = temp
                min_index = i
        
        print(f"  Minimum temp after drop: {min_temp_after_drop:.1f}°C at row {min_index + 12}")
        
        # Check for rises after minimum
        rises_after_min = []
        for i in range(min_index + 1, len(data)):
            curr_temp = float(data[i]['VirtualCoreTemperature'])
            prev_temp = float(data[i-1]['VirtualCoreTemperature'])
            if curr_temp - prev_temp > 2:
                rises_after_min.append((i+12, data[i]['Timestamp'], curr_temp - prev_temp))
        
        if rises_after_min:
            print("  Temperature rises after minimum:")
            for row, time, rise in rises_after_min:
                print(f"    Row {row}, time {time}s: +{rise:.1f}°C")
        else:
            print("  No significant rises after minimum - single curve detected")

if __name__ == "__main__":
    file_path = "/home/sverzijl/combustion_display/ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
    analyze_temperature_patterns(file_path)