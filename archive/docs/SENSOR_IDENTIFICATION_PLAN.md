# Sensor Identification Improvement Plan

## Current Issue

The current code incorrectly assumes fixed sensor assignments:
- Core: Average of T1-T4
- Surface: Average of T7-T8
- Ambient: Not explicitly calculated

This is incorrect because:
1. The probe can be inserted at different angles/positions
2. Sensors end up in different thermal zones based on insertion
3. The CSV already contains dynamic sensor identification from the probe firmware

## Discovery

Analysis of `ProbeData_100098DE_2025-05-30 13_51_07.csv` reveals:

1. **The CSV contains virtual sensor assignments** that change dynamically:
   - `VirtualCoreTemperature` with `VirtualCoreSensor` 
   - `VirtualSurfaceTemperature` with `VirtualSurfaceSensor`
   - `VirtualAmbientTemperature` with `VirtualAmbientSensor`

2. **Common sensor assignment patterns observed**:
   - T1,T4,T8 (1416 times) - Most common
   - T4,T6,T8 (410 times) 
   - T1,T4,T6 (290 times)
   - Various other combinations

3. **Temperature characteristics**:
   - **Ambient sensors**: Highest temperatures (closest to oven environment)
   - **Core sensors**: Lowest temperatures (center of bread)
   - **Surface sensors**: Intermediate temperatures (bread surface/crust)

## Proposed Solution

### Option 1: Use Virtual Sensor Assignments (Recommended)
Since the probe firmware already performs intelligent sensor selection:

1. **Primary approach**: Use the CSV's virtual sensor data directly
   - Use `VirtualCoreTemperature` instead of calculating averages
   - Use `VirtualSurfaceTemperature` and `VirtualAmbientTemperature`
   - Track which physical sensors are assigned to each role

2. **Benefits**:
   - Leverages probe manufacturer's expertise
   - Handles dynamic conditions automatically
   - More accurate than fixed assumptions

### Option 2: Dynamic Sensor Classification (Fallback)
If virtual data is unavailable, classify sensors dynamically:

1. **Temperature-based classification**:
   ```
   For each time point:
   - Sort sensors by temperature
   - Lowest 2-3 sensors → Core candidates
   - Highest 1-2 sensors → Ambient candidates
   - Middle sensors → Surface candidates
   ```

2. **Characteristics to consider**:
   - **Heating rate**: Ambient heats fastest, core slowest
   - **Temperature range**: Ambient has widest range
   - **Final temperature**: Core reaches 90-100°C, ambient can exceed 120°C
   - **Variability**: Surface shows more fluctuation than core

### Option 3: Hybrid Approach
Combine both methods for robustness:
1. Use virtual assignments when available
2. Validate with temperature-based logic
3. Fall back to dynamic classification if needed

## Implementation Steps

1. **Update data loader** (`src/data/loader.py`):
   ```python
   def _identify_sensor_roles(self, df):
       """Identify which sensors represent core, surface, and ambient."""
       
       # Option 1: Use virtual assignments if available
       if all(col in df.columns for col in ['VirtualCoreTemperature', 
                                              'VirtualCoreSensor']):
           # Use the CSV's intelligent sensor selection
           df['CoreTemperature'] = df['VirtualCoreTemperature']
           df['SurfaceTemperature'] = df['VirtualSurfaceTemperature']
           df['AmbientTemperature'] = df['VirtualAmbientTemperature']
           
           # Track sensor assignments for visualization
           self.sensor_assignments = {
               'core': df['VirtualCoreSensor'].mode()[0],
               'surface': df['VirtualSurfaceSensor'].mode()[0],
               'ambient': df['VirtualAmbientSensor'].mode()[0]
           }
       else:
           # Option 2: Dynamic classification
           df = self._classify_sensors_dynamically(df)
   ```

2. **Remove hardcoded averages**:
   - Remove `CoreAverage = mean(T1-T4)`
   - Remove `SurfaceAverage = mean(T7-T8)`
   - Use identified temperatures instead

3. **Update analysis modules** to use new temperature columns:
   - `CoreTemperature` instead of `CoreAverage`
   - `SurfaceTemperature` instead of `SurfaceAverage`
   - `AmbientTemperature` (new capability)

4. **Add validation**:
   - Ensure core < surface < ambient (generally)
   - Check for reasonable temperature ranges
   - Log sensor assignments for debugging

## Benefits

1. **Accuracy**: Correctly identifies actual temperature zones regardless of probe placement
2. **Flexibility**: Handles different insertion angles and positions
3. **Reliability**: Uses manufacturer's built-in intelligence
4. **Transparency**: Can show which sensors are used for each zone
5. **Robustness**: Fallback methods ensure functionality even with incomplete data

## Testing

1. Verify with provided CSV that virtual assignments are used correctly
2. Test fallback classification with modified CSV (virtual columns removed)
3. Validate temperature relationships (core < surface < ambient)
4. Check S-curve analysis with corrected sensor identification