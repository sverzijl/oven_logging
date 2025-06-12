# Internal Sensor Algorithm Implementation Summary

## Overview
Successfully implemented a physics-based algorithm to better identify internal crumb sensors by excluding sensors that exceed the moisture evaporation point (100°C + margin).

## Key Changes

### 1. Configuration (config/constants.py)
Added `INTERNAL_SENSOR_CONFIG` with:
- `TEMP_THRESHOLD`: 103.0°C (100°C + 3°C probe accuracy margin)
- `TIME_THRESHOLD`: 0.1 (10% of time above 100°C)
- `USE_TIME_BASED_FILTERING`: False (optional additional criterion)
- `ALWAYS_INCLUDE_CORE`: True (ensures core sensor is never excluded)

### 2. Algorithm Update (src/data/loader.py)
Modified `get_internal_sensors()` method to:
- Accept optional `data` parameter for temperature analysis
- Filter out sensors whose maximum temperature exceeds 103°C
- Always include the core sensor regardless of temperature
- Maintain backward compatibility when no data is provided

### 3. Calling Code Updates
- Updated `app.py` to pass curve data when available
- Maintained backward compatibility for cases where data isn't readily available

## Physics Rationale
- **Moisture-Limited Temperature**: Internal bread crumb contains moisture throughout baking
- **Evaporative Cooling**: As long as moisture is present, temperature is limited to ~100°C
- **Crust Identification**: Sensors exceeding 100°C are likely in or near the crust where moisture has evaporated

## Test Results

### Synthetic Data Tests
All tests pass, including:
- Sensors below threshold are included
- Sensors above 103°C are excluded
- Core sensor is always included even if >103°C
- Edge cases handled properly

### Real Data Analysis
Analyzed 5 production CSV files with significant improvements:

#### Example: ProbeData_1000BA3C_2025-05-30 09_46_16.csv
- **Old method**: Used 6 sensors (T1-T6) for internal uniformity
- **New method**: Used 5 sensors (T1-T5), excluded T6 (max 107.3°C)
- **Temperature uniformity improvement**: 4.2°C → 1.0°C standard deviation
- **Correctly identified**: T6 was measuring crust/near-crust, not internal crumb

#### Example: ProbeData_100098DE_2025-05-30 13_51_07.csv
- **Excluded**: T7 (max 112.3°C, spent 9.2 minutes >100°C)
- **Temperature uniformity improvement**: 5.4°C → 1.2°C standard deviation

## Benefits
1. **More Accurate Metrics**: Internal temperature uniformity now reflects true crumb temperatures
2. **Better Quality Assessment**: Crust sensors no longer skew crumb analysis
3. **Adaptive Algorithm**: Automatically adjusts to different probe insertion depths
4. **Maintained Compatibility**: Works with existing codebase and UI

## Usage
The algorithm works automatically - no user configuration required. The system will:
- Identify which sensors are truly measuring internal crumb
- Exclude sensors that are likely in the crust
- Provide more accurate baking uniformity metrics
- Show temperature spread only for true internal sensors in visualizations

## Future Enhancements
Consider adding:
- UI indication showing which sensors were excluded and why
- Option to adjust temperature threshold for specific product types
- Time-based filtering for sensors that briefly spike above 100°C