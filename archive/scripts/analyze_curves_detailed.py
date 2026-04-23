import csv

# Read the CSV file
with open('ProbeData_1000BA3C_2025-05-30 17_59_37.csv', 'r') as f:
    # Skip header lines
    for _ in range(10):
        f.readline()
    
    reader = csv.DictReader(f)
    rows = list(reader)

print("Detailed Analysis of Temperature Patterns")
print("=" * 80)

# Track all significant temperature events
temp_events = []
curves = []
current_curve = None

# Analyze temperature patterns
for i in range(1, len(rows)):
    timestamp = float(rows[i]['Timestamp'])
    core_temp = float(rows[i]['VirtualCoreTemperature'])
    prev_temp = float(rows[i-1]['VirtualCoreTemperature'])
    temp_change = core_temp - prev_temp
    
    # Detect start of heating (temp increase > 2°C in 5 seconds)
    if temp_change > 2 and current_curve is None:
        current_curve = {
            'start_row': i,
            'start_time': timestamp,
            'start_temp': prev_temp,
            'max_temp': core_temp,
            'max_temp_time': timestamp,
            'max_temp_row': i
        }
    
    # Update max temp during heating
    elif current_curve is not None and core_temp > current_curve['max_temp']:
        current_curve['max_temp'] = core_temp
        current_curve['max_temp_time'] = timestamp
        current_curve['max_temp_row'] = i
    
    # Detect end of curve (rapid cooling > 10°C drop in 30 seconds)
    elif current_curve is not None and i >= 6:
        temp_30s_ago = float(rows[i-6]['VirtualCoreTemperature'])
        if temp_30s_ago - core_temp > 10:
            current_curve['end_row'] = i
            current_curve['end_time'] = timestamp
            current_curve['end_temp'] = core_temp
            current_curve['duration'] = (current_curve['max_temp_time'] - current_curve['start_time']) / 60
            curves.append(current_curve)
            current_curve = None

# Check if last curve is still ongoing
if current_curve is not None:
    current_curve['end_row'] = len(rows) - 1
    current_curve['end_time'] = float(rows[-1]['Timestamp'])
    current_curve['end_temp'] = float(rows[-1]['VirtualCoreTemperature'])
    current_curve['duration'] = (current_curve['max_temp_time'] - current_curve['start_time']) / 60
    curves.append(current_curve)

print(f"\nFound {len(curves)} baking curve(s):\n")

for i, curve in enumerate(curves):
    print(f"BAKING CURVE {i+1}:")
    print(f"  Start: Row {curve['start_row']:5d} at {curve['start_time']/60:6.1f} min (Temp: {curve['start_temp']:5.1f}°C)")
    print(f"  Peak:  Row {curve['max_temp_row']:5d} at {curve['max_temp_time']/60:6.1f} min (Temp: {curve['max_temp']:5.1f}°C)")
    print(f"  End:   Row {curve['end_row']:5d} at {curve['end_time']/60:6.1f} min (Temp: {curve['end_temp']:5.1f}°C)")
    print(f"  Heating duration: {curve['duration']:5.1f} minutes")
    print(f"  Temperature rise: {curve['max_temp'] - curve['start_temp']:5.1f}°C")
    print()

# Analyze the gap between curves
if len(curves) >= 2:
    print("\nGAP ANALYSIS BETWEEN CURVES:")
    gap_start = curves[0]['end_time']
    gap_end = curves[1]['start_time']
    gap_duration = (gap_end - gap_start) / 60
    
    print(f"  Gap duration: {gap_duration:.1f} minutes")
    print(f"  From {gap_start/60:.1f} min to {gap_end/60:.1f} min")
    
    # Find minimum temperature during gap
    min_temp_gap = 100
    for i in range(curves[0]['end_row'], curves[1]['start_row']):
        temp = float(rows[i]['VirtualCoreTemperature'])
        if temp < min_temp_gap:
            min_temp_gap = temp
    
    print(f"  Minimum temperature during gap: {min_temp_gap:.1f}°C")
    print(f"  Temperature drop: {curves[0]['max_temp'] - min_temp_gap:.1f}°C")

# Additional details about the data
print("\n\nADDITIONAL DATA INSIGHTS:")
print("=" * 80)

# Check for any gaps in timestamps
max_gap = 0
gap_location = 0
for i in range(1, len(rows)):
    time_diff = float(rows[i]['Timestamp']) - float(rows[i-1]['Timestamp'])
    if time_diff > max_gap:
        max_gap = time_diff
        gap_location = i

print(f"Maximum time gap between readings: {max_gap:.1f}s at row {gap_location}")
print(f"Total data points: {len(rows)}")
print(f"Expected data points (5s intervals): {int(float(rows[-1]['Timestamp'])/5) + 1}")
print(f"Data continuity: {'Continuous' if max_gap <= 10 else 'Has gaps'}")