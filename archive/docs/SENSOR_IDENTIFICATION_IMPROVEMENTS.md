# Sensor Identification Improvements

## Overview

The thermal profile analyzer now includes an enhanced sensor identification system that combines the probe's intelligent virtual assignments with thermodynamic validation.

## Key Improvements

### 1. **Primary Method: Virtual Sensor Assignments (Unchanged)**
- Uses the probe firmware's intelligent sensor selection from CSV columns:
  - `VirtualCoreSensor`, `VirtualSurfaceSensor`, `VirtualAmbientSensor`
- Adapts to variations in probe insertion angle and position
- Remains the primary and most accurate method

### 2. **New: Thermodynamic Validation**
When using virtual assignments, the system now validates them by checking:
- **Temperature ordering**: Core < Surface < Ambient (average temperatures)
- **Heating rates**: Each sensor type has expected ranges
  - Core: 0.2-3°C/min
  - Surface: 2-15°C/min
  - Ambient: 10-50°C/min
- **Assignment consistency**: Warns if sensors change frequently (< 80% consistency)

### 3. **Enhanced Fallback: Thermodynamic Classification**
When virtual data is unavailable, the system uses advanced thermodynamic analysis:
- **Multiple heat transfer properties** instead of just maximum temperature
- **Physical principles**: Thermal mass, convection, conduction characteristics
- **Scoring algorithm** that rewards expected thermodynamic behavior

## Thermodynamic Properties Used

1. **Initial heating rate** (0-5 minutes)
2. **Time to reach threshold temperatures** (50°C, 70°C)
3. **Maximum rate of change** (single interval)
4. **Rate change variability** (standard deviation)
5. **Thermal lag** (inflection point timing)
6. **Response sharpness** (max/avg change ratio)
7. **Signal noise** (high-frequency variations)

## Benefits

1. **Better diagnostics**: Warns about probe positioning issues
2. **Validation**: Confirms virtual assignments make thermodynamic sense
3. **Robust fallback**: More accurate than simple temperature sorting
4. **Physical basis**: Uses heat transfer principles, not just statistics

## Example Output

### Normal Operation
```
Using virtual sensor assignments from CSV:
  Core: T1 (94.0% of readings)
  Surface: T6 (100.0% of readings)
  Ambient: T8 (100.0% of readings)
```

### Problematic Probe Insertion
```
Sensor Assignment Validation Warnings:
  ⚠️  Core sensor (T1) has higher average temperature than surface sensor (T4)
  ⚠️  Surface sensor (T4) has unusual heating rate: 1.4°C/min (expected 2-15°C/min)
  ⚠️  Core sensor assignment changes frequently (79.7% consistency) - probe may not be properly inserted

  Alternative thermodynamic classification suggests:
    CORE: T5, T6, T3
    SURFACE: T7, T1, T2
    AMBIENT: T8, T4
```

## Implementation Details

- Located in `src/data/thermodynamic_sensor_classifier.py`
- Integrated into `src/data/loader.py` for validation and fallback
- No breaking changes to existing functionality
- Backward compatible with all existing code