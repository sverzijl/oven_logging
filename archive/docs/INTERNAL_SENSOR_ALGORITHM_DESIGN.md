# Internal Sensor Algorithm Design

## Problem Statement
The current algorithm considers all sensors below the surface sensor as "internal crumb" sensors. However, sensors that exceed 100°C are likely measuring crust or near-crust regions, not true internal crumb.

## Physics-Based Rationale

### 1. Moisture-Limited Temperature
- Bread crumb contains significant moisture (35-45% in finished product)
- As long as moisture is present, temperature is limited by water's boiling point (~100°C)
- This is due to evaporative cooling - energy goes into phase change rather than temperature increase

### 2. Crust Formation
- Crust forms when surface moisture evaporates
- Once dry, crust temperature can exceed 100°C rapidly
- Crust temperatures typically reach 150-200°C for proper browning

### 3. Sensor Positioning Variability
- Manual probe insertion creates variability
- Some "internal" sensors may be close to or in the crust
- Need dynamic identification based on temperature behavior

## Improved Algorithm Design

### Core Logic
```python
def get_internal_sensors(self, curve_index, data):
    # Step 1: Get all sensors below surface (current logic)
    surface_num = int(surface_sensor[1])
    candidate_sensors = [f'T{i}' for i in range(1, surface_num)]
    
    # Step 2: Filter by temperature criteria
    internal_sensors = []
    for sensor in candidate_sensors:
        max_temp = data[sensor].max()
        
        # Check if sensor stays below moisture evaporation point
        if max_temp <= INTERNAL_TEMP_THRESHOLD:  # 103°C (100 + 3°C margin)
            internal_sensors.append(sensor)
    
    # Step 3: Ensure core sensor is always included
    core_sensor = self.get_core_sensor(curve_index)
    if core_sensor not in internal_sensors:
        internal_sensors.append(core_sensor)
    
    return internal_sensors
```

### Configuration
```python
# Temperature threshold for internal sensors
# Sensors exceeding this are likely in crust, not crumb
INTERNAL_SENSOR_TEMP_THRESHOLD = 103.0  # 100°C + 3°C probe accuracy margin

# Alternative: Percentage of time above 100°C
INTERNAL_SENSOR_TIME_THRESHOLD = 0.1  # Max 10% of time above 100°C
```

### Advanced Criteria (Optional)
1. **Time-based filtering**: Exclude if >10% of baking time is spent above 100°C
2. **Rate-based filtering**: Rapid heating rates may indicate crust proximity
3. **End-temperature filtering**: Consider final temperature, not just maximum

## Implementation Plan

### 1. Update Constants
- Add `INTERNAL_SENSOR_TEMP_THRESHOLD` to `config/constants.py`

### 2. Modify `loader.py`
- Update `get_internal_sensors()` to accept data parameter
- Implement temperature-based filtering
- Ensure core sensor is always included

### 3. Update Calling Code
- `app.py`: Pass data when calling `get_internal_sensors()`
- Handle cases where no sensors qualify as internal

### 4. Testing Strategy
- Unit tests with synthetic data
- Test edge cases:
  - All sensors >100°C except core
  - No sensors >100°C
  - Gradual temperature progression
- Real data validation with known probe configurations

## Expected Benefits
1. More accurate internal temperature uniformity metrics
2. Better representation of actual crumb temperatures
3. Clearer distinction between crumb and crust analysis
4. More meaningful baking quality assessments

## Potential Challenges
1. Backward compatibility with existing analyses
2. User confusion if familiar sensors are excluded
3. Edge cases with unusual baking profiles
4. Need clear UI communication about why sensors are excluded