# Advanced Surface Sensor Identification Algorithm

## Overview

This document describes the physics-based algorithm for identifying the true surface temperature sensor in multi-probe bread baking systems. The algorithm addresses a critical firmware issue where internal/core sensors are incorrectly identified as surface sensors, leading to inaccurate browning and crust formation analysis.

## Problem Statement

The current firmware consistently selects sensors (T1-T4) that:
- Never exceed 99°C (typical internal bread temperature)
- Show slow, steady heating curves characteristic of protected core regions
- Completely miss the browning temperature zones (110-180°C)

This misidentification means:
- Surface browning metrics show 0% time in browning zones
- Crust formation analysis is completely inaccurate
- Quality recommendations for crust development are meaningless

## Algorithm Design Principles

### Physics Foundation

The algorithm is based on fundamental bread baking physics:

1. **Moisture Barrier at 100°C**: Internal bread temperature is limited by water's boiling point until moisture evaporates
2. **Surface Dehydration**: The bread surface rapidly loses moisture, allowing temperatures to exceed 100°C
3. **Temperature Gradient**: Sharp transition exists between moist interior (~95°C) and dry surface (110-180°C)
4. **Browning Zones**: 
   - Crust Formation: 110-125°C
   - Maillard Reaction: 105-150°C
   - Caramelization: 150-200°C

### Key Metrics

The algorithm analyzes six key metrics for each sensor:

1. **Maximum Temperature**: Identifies sensors capable of exceeding moisture barrier
2. **Time to 100°C**: Surface sensors reach this threshold faster
3. **Heating Rate (60-100°C)**: Surface sensors heat more rapidly
4. **Temperature Variance**: Surface shows more variation due to oven cycling
5. **Escape Velocity**: Rate of temperature rise through 100°C barrier
6. **Time Above 100°C**: Duration in the "dry zone"

## Algorithm Phases

### Phase 1: Metric Calculation
- Computes all six metrics for each sensor (T1-T8)
- Handles edge cases and missing data gracefully

### Phase 2: Gradient Analysis
- Identifies sharp temperature transitions between adjacent sensors
- Scores boundary transitions based on:
  - Temperature gradient magnitude (>15°C)
  - Heating rate increase (>50%)
  - Variance ratio (>2x)
  - Escape velocity difference
  - Time above 100°C differential

### Phase 3: Surface Selection
- Selects lowest-numbered sensor showing clear surface behavior
- Validates with browning zone time (>5 minutes)
- Provides confidence score and reasoning

### Phase 4: Fallback Logic
- Activates if gradient analysis inconclusive
- Identifies sensors with:
  - Maximum temperature ≥110°C
  - Significant time above 100°C
  - Adequate browning zone duration

## Implementation Details

### Core Function

```python
def identify_surface_sensor_advanced(df, sample_period_ms=5000):
    """
    Returns:
        dict: {
            'sensor': str,           # e.g., 'T7'
            'confidence': int,       # 0-100%
            'reasoning': str,        # Human-readable explanation
            'browning_time': float,  # Minutes in 110-180°C range
            'max_temp': float        # Maximum temperature reached
        }
        or None if surface cannot be identified
    """
```

### Integration Points

1. **ThermalProfileLoader**: Primary integration point for sensor data processing
2. **Zone Analysis**: Uses corrected surface temperature for zone calculations
3. **S-Curve Analysis**: Properly identifies surface-related milestones
4. **Quality Metrics**: Accurate browning and crust metrics

## Validation Results

Tested on 4 production CSV files with 100% accuracy:
- Correctly identified T7 or T8 as surface sensors
- All selected sensors showed 15-48 minutes in browning zone
- Maximum temperatures aligned with typical bread surface (130-150°C)
- Firmware incorrectly selected T1-T6 in all cases

## Usage Example

```python
# In ThermalProfileLoader
def _apply_surface_correction(self, df):
    """Apply physics-based surface sensor correction"""
    result = identify_surface_sensor_advanced(df)
    
    if result and result['confidence'] >= 60:
        # Override firmware selection
        surface_sensor = result['sensor']
        df['VirtualSurfaceTemperature'] = df[surface_sensor]
        df['PhysicsBasedSurfaceDetection'] = True
        
        # Log the correction
        logger.info(f"Surface sensor corrected: {surface_sensor} "
                   f"(confidence: {result['confidence']}%, "
                   f"reasoning: {result['reasoning']})")
    
    return df
```

## Benefits

1. **Accurate Analysis**: Enables proper browning and crust formation metrics
2. **Physics-Based**: Grounded in fundamental heat transfer principles
3. **Robust**: Works across different probe models, insertions, and ovens
4. **Transparent**: Provides confidence scores and reasoning
5. **Backward Compatible**: Can be toggled on/off if needed