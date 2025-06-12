# Sensor Identification Consistency Analysis

## Summary of Issues Found

### 1. Multiple Sensor Identification Methods
The codebase currently has **4 different methods** for identifying sensor roles:

1. **Virtual Sensor Assignments (from CSV)** - Used by ThermalProfileLoader
   - Reads VirtualCoreSensor, VirtualSurfaceSensor, VirtualAmbientSensor columns
   - Most accurate as it uses probe firmware's dynamic classification
   
2. **Thermodynamic Classification** - Used by ThermodynamicSensorClassifier
   - Analyzes heating rates, thermal lag, response sharpness, signal noise
   - Sophisticated but not consistently applied across modules

3. **Temperature Pattern Analysis** - Used by ZoneAnalyzer and ThermalAnalyzer
   - Each module has its own implementation of `_identify_temperature_sources()`
   - Uses temperature ranges: Core (85-105°C), Surface (105-180°C), Ambient (>180°C)
   - Inconsistent thresholds and logic between modules

4. **Position-Based Heuristics** - Fallback in loader
   - Assumes T1-T4 are core, T7-T8 are surface/ambient
   - Least accurate, only used as last resort

### 2. Disconnected Sensor Selection UI
- The "Select Sensors to Display" multiselect only affects visualization in `plot_temperature_profile()`
- Does NOT affect which sensors are used for calculations
- Creates confusion as users expect it to control analysis

### 3. Inconsistent Sensor Usage Across Modules

#### ThermalAnalyzer
- Has its own `_identify_temperature_sources()` method
- Uses hardcoded column names like 'CoreAverage', 'CoreTemperature'
- Falls back to calculated averages of T1-T4

#### ZoneAnalyzer  
- Has separate `_identify_temperature_sources()` method
- Different temperature thresholds than ThermalAnalyzer
- Uses physical sensors (T1-T8) directly for uniformity calculations

#### SCurveAnalyzer
- Expects specific column names ('CoreTemperature' or 'CoreAverage')
- No sensor identification logic of its own

#### Visualization (plots.py)
- Uses sensor selection from UI for display
- But heating rate plots hardcode T1-T4 as core, T5-T8 as surface

### 4. Column Name Dependencies
- Some modules expect 'CoreAverage', 'SurfaceAverage' columns
- Others expect 'CoreTemperature', 'VirtualCoreTemperature'
- Inconsistent fallback behavior when columns missing

## Root Causes

1. **No Central Sensor Role Authority**: Each module makes its own determination
2. **Mixed Responsibilities**: Sensor identification logic scattered across data loading, analysis, and visualization
3. **Legacy Column Names**: Hardcoded expectations from older data formats
4. **No Clear API**: No consistent way to query "which sensors are core/surface/ambient?"

## Recommended Solution

### 1. Centralize Sensor Identification
- ThermalProfileLoader should be the single source of truth
- It already has the most sophisticated logic and access to virtual assignments
- All other modules should query the loader for sensor roles

### 2. Create Clear Sensor Role API
```python
loader.get_core_sensors() -> List[str]  # ['T1', 'T2', 'T3']
loader.get_surface_sensors() -> List[str]  # ['T7', 'T8']
loader.get_ambient_sensors() -> List[str]  # ['T8']
loader.get_core_column() -> str  # 'VirtualCoreTemperature' or calculated
loader.get_surface_column() -> str  # 'VirtualSurfaceTemperature' or calculated
```

### 3. Separate Display from Analysis
- UI sensor selection should ONLY affect visualization
- Analysis should always use the identified sensors from loader
- Make this clear in the UI labeling

### 4. Consistent Column Generation
- Loader should always generate standard columns:
  - 'CoreTemperature' (from virtual or calculated)
  - 'SurfaceTemperature' (from virtual or calculated)
  - 'AmbientTemperature' (if identifiable)
- Analysis modules use these standard columns

### 5. Remove Duplicate Identification Logic
- Remove `_identify_temperature_sources()` from ThermalAnalyzer and ZoneAnalyzer
- Have them use loader's sensor assignments instead