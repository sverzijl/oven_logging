import csv

# Read the CSV file
with open('ProbeData_1000BA3C_2025-05-30 17_59_37.csv', 'r') as f:
    # Skip header lines
    for _ in range(11):
        f.readline()
    
    reader = csv.DictReader(f)
    rows = list(reader)

# Track state changes
prev_state = None
transitions = []
row_num = 0

for row in rows:
    current_state = row['PredictionState']
    if current_state != prev_state:
        transitions.append({
            'row': row_num,
            'timestamp': float(row['Timestamp']),
            'from_state': prev_state,
            'to_state': current_state,
            'core_temp': float(row['VirtualCoreTemperature'])
        })
        prev_state = current_state
    row_num += 1

print("State Transitions Found:")
print("=" * 80)
for t in transitions:
    print(f"Row {t['row']:6d} | Time {t['timestamp']:10.1f}s ({t['timestamp']/60:6.1f}min) | {str(t['from_state']):20s} -> {t['to_state']:20s} | Core: {t['core_temp']:.1f}°C")

# Find significant temperature changes
print("\n\nAnalyzing temperature patterns for multiple curves...")
print("=" * 80)

# Look for patterns that indicate multiple baking sessions
cooking_periods = []
current_cooking = None

for i, row in enumerate(rows):
    state = row['PredictionState']
    timestamp = float(row['Timestamp'])
    core_temp = float(row['VirtualCoreTemperature'])
    
    if state == 'Cooking' and current_cooking is None:
        # Start of cooking period
        current_cooking = {
            'start_row': i,
            'start_time': timestamp,
            'start_temp': core_temp,
            'max_temp': core_temp
        }
    elif state == 'Cooking' and current_cooking is not None:
        # Update max temp during cooking
        current_cooking['max_temp'] = max(current_cooking['max_temp'], core_temp)
    elif state != 'Cooking' and current_cooking is not None:
        # End of cooking period
        current_cooking['end_row'] = i - 1
        current_cooking['end_time'] = float(rows[i-1]['Timestamp'])
        current_cooking['end_temp'] = float(rows[i-1]['VirtualCoreTemperature'])
        current_cooking['duration'] = current_cooking['end_time'] - current_cooking['start_time']
        cooking_periods.append(current_cooking)
        current_cooking = None

# Handle case where file ends while still cooking
if current_cooking is not None:
    current_cooking['end_row'] = len(rows) - 1
    current_cooking['end_time'] = float(rows[-1]['Timestamp'])
    current_cooking['end_temp'] = float(rows[-1]['VirtualCoreTemperature'])
    current_cooking['duration'] = current_cooking['end_time'] - current_cooking['start_time']
    cooking_periods.append(current_cooking)

print(f"\nFound {len(cooking_periods)} cooking period(s):")
for i, period in enumerate(cooking_periods):
    print(f"\nCooking Period {i+1}:")
    print(f"  Start: Row {period['start_row']} at {period['start_time']:.1f}s ({period['start_time']/60:.1f}min)")
    print(f"  End:   Row {period['end_row']} at {period['end_time']:.1f}s ({period['end_time']/60:.1f}min)")
    print(f"  Duration: {period['duration']:.1f}s ({period['duration']/60:.1f}min)")
    print(f"  Temperature range: {period['start_temp']:.1f}°C - {period['max_temp']:.1f}°C")

# Summary
print("\n\nDataset Summary:")
print("=" * 80)
print(f"Total duration: {float(rows[-1]['Timestamp']) / 60:.1f} minutes")
print(f"Total rows: {len(rows)}")

# Count states
state_counts = {}
for row in rows:
    state = row['PredictionState']
    state_counts[state] = state_counts.get(state, 0) + 1

print(f"\nPredictionState counts:")
for state, count in sorted(state_counts.items()):
    print(f"  {state}: {count} rows")