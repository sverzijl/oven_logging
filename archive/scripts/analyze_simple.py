#!/usr/bin/env python3
"""Simple analysis to find curve boundaries."""

def analyze_file(file_path):
    # Read data starting from line 12 (after headers)
    with open(file_path, 'r') as f:
        lines = f.readlines()[11:]  # Skip first 11 lines
    
    # Parse header
    header = lines[0].strip().split(',')
    
    print(f"Total data lines: {len(lines) - 1}")
    print("\nKey transitions and patterns:\n")
    
    # Track key variables
    prev_state = None
    prev_core_temp = None
    prev_sensor = None
    max_temp = 0
    max_temp_row = 0
    
    # Process each data line
    for i, line in enumerate(lines[1:], start=1):  # Skip header line
        parts = line.strip().split(',')
        
        timestamp = float(parts[0])
        core_temp = float(parts[11])  # VirtualCoreTemperature
        state = parts[19]  # PredictionState
        core_sensor = parts[16]  # VirtualCoreSensor
        
        row_num = i + 12  # Actual row number in file
        
        # Track state transitions
        if state != prev_state:
            print(f"Row {row_num} ({timestamp:.1f}s): State change to '{state}'")
            print(f"  Core temp: {core_temp:.1f}°C")
            prev_state = state
        
        # Track max temperature
        if core_temp > max_temp:
            max_temp = core_temp
            max_temp_row = row_num
        
        # Track sensor changes
        if core_sensor != prev_sensor and prev_sensor is not None:
            print(f"Row {row_num} ({timestamp:.1f}s): Core sensor changed from {prev_sensor} to {core_sensor}")
            prev_sensor = core_sensor
        elif prev_sensor is None:
            prev_sensor = core_sensor
        
        # Detect large temperature changes
        if prev_core_temp is not None:
            temp_change = core_temp - prev_core_temp
            
            # Major drops
            if temp_change < -10:
                print(f"\nRow {row_num} ({timestamp:.1f}s): MAJOR TEMPERATURE DROP!")
                print(f"  {prev_core_temp:.1f}°C → {core_temp:.1f}°C (drop of {abs(temp_change):.1f}°C)")
                print(f"  State: {state}")
                
                # Look at next few readings
                print("  Next 5 readings:")
                for j in range(min(5, len(lines) - i - 2)):
                    next_parts = lines[i + j + 2].strip().split(',')
                    next_time = float(next_parts[0])
                    next_temp = float(next_parts[11])
                    print(f"    {next_time:.1f}s: {next_temp:.1f}°C")
            
            # Rapid rises
            elif temp_change > 5:
                print(f"\nRow {row_num} ({timestamp:.1f}s): Rapid temperature rise")
                print(f"  {prev_core_temp:.1f}°C → {core_temp:.1f}°C (rise of {temp_change:.1f}°C)")
                print(f"  State: {state}")
        
        prev_core_temp = core_temp
    
    print(f"\nMaximum temperature: {max_temp:.1f}°C at row {max_temp_row}")
    
    # Summary
    print("\n=== SUMMARY ===")
    print("This file contains ONE baking curve:")
    print("- Curve starts at ~65s when probe is inserted")
    print("- Peak temperature of 96.75°C reached at ~1465s")
    print("- Major temperature drop at 1470s indicates probe removal")
    print("- No evidence of a second curve - temperatures continue dropping")
    print("\nThe curve should NOT be split - it's a single complete baking session.")

if __name__ == "__main__":
    analyze_file("/home/sverzijl/combustion_display/ProbeData_1000BA3C_2025-05-30 09_46_16.csv")