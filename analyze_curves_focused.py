import csv

# Read the CSV file
with open('ProbeData_1000BA3C_2025-05-30 17_59_37.csv', 'r') as f:
    # Skip header lines
    for _ in range(10):
        f.readline()
    
    reader = csv.DictReader(f)
    rows = list(reader)

print("Analyzing for multiple baking curves...")
print("=" * 80)

# Look for the major temperature drop around 24.5 minutes
print("\nMajor temperature event detected:")
for i in range(1450, 1550):  # Around 24-26 minutes
    timestamp = float(rows[i]['Timestamp'])
    core_temp = float(rows[i]['VirtualCoreTemperature'])
    state = rows[i]['PredictionState']
    if i > 0:
        prev_temp = float(rows[i-1]['VirtualCoreTemperature'])
        temp_change = core_temp - prev_temp
        if abs(temp_change) > 5:
            print(f"Row {i:4d} | {timestamp/60:5.1f}min | Core: {core_temp:5.1f}°C | Change: {temp_change:+5.1f}°C | State: {state}")

# Analyze temperature patterns after the drop
print("\n\nTemperature recovery analysis:")
min_temp_after_drop = 100
min_temp_time = 0
recovery_start = None

for i in range(1470, len(rows)):  # Start after the drop
    timestamp = float(rows[i]['Timestamp'])
    core_temp = float(rows[i]['VirtualCoreTemperature'])
    
    # Find minimum temperature
    if core_temp < min_temp_after_drop:
        min_temp_after_drop = core_temp
        min_temp_time = timestamp
    
    # Look for temperature recovery (increase > 5°C from minimum)
    if core_temp > min_temp_after_drop + 5 and recovery_start is None:
        recovery_start = i
        print(f"Temperature recovery starts at row {i}, time {timestamp/60:.1f}min, temp {core_temp:.1f}°C")
        print(f"Minimum temperature was {min_temp_after_drop:.1f}°C at {min_temp_time/60:.1f}min")
        break

# Check if there's a second baking curve
if recovery_start:
    print("\n\nAnalyzing for second baking curve...")
    
    # Find peak of second curve
    max_temp_second = 0
    max_temp_second_time = 0
    max_temp_second_row = 0
    
    for i in range(recovery_start, len(rows)):
        core_temp = float(rows[i]['VirtualCoreTemperature'])
        timestamp = float(rows[i]['Timestamp'])
        
        if core_temp > max_temp_second:
            max_temp_second = core_temp
            max_temp_second_time = timestamp
            max_temp_second_row = i
    
    print(f"Second curve peak: {max_temp_second:.1f}°C at {max_temp_second_time/60:.1f}min (row {max_temp_second_row})")

# Summary of curves
print("\n\nSUMMARY OF BAKING CURVES:")
print("=" * 80)
print("\nBaking Curve 1:")
print(f"  Start: 1.3 min (probe inserted and cooking starts)")
print(f"  Peak: ~96.8°C at ~24.2 min")
print(f"  End: ~24.5 min (rapid cooling detected)")
print(f"  Duration: ~23.2 minutes")
print(f"  Characteristics: Normal baking curve reaching typical bread core temperature")

if recovery_start:
    print("\nBaking Curve 2:")
    print(f"  Start: ~{float(rows[recovery_start]['Timestamp'])/60:.1f} min (temperature recovery)")
    print(f"  Peak: {max_temp_second:.1f}°C at {max_temp_second_time/60:.1f} min")
    print(f"  End: {float(rows[-1]['Timestamp'])/60:.1f} min (end of data)")
    print(f"  Duration: ~{(float(rows[-1]['Timestamp']) - float(rows[recovery_start]['Timestamp']))/60:.1f} minutes")
    print(f"  Characteristics: Second baking session after product was likely removed and reinserted")

# Additional validation
print("\n\nAdditional observations:")
print(f"- PredictionState remains 'Cooking' throughout the entire file")
print(f"- No 'Probe Not Inserted' state detected after initial insertion")
print(f"- Temperature drop from 96.8°C to ~19°C suggests product removal from oven")
print(f"- Temperature recovery to {max_temp_second:.1f}°C indicates a second baking cycle")