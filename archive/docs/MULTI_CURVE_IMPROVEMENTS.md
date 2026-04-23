# Multi-Curve Support Improvements

## Overview
This document describes the improvements made to support multiple baking curves within a single CSV file. This feature addresses the common scenario where users perform multiple baking sessions and download all data in one file.

## Key Features Added

### 1. Automatic Multi-Curve Detection
- The `ThermalProfileLoader` now automatically detects all baking curves in a CSV file
- Detection is based on:
  - PredictionState transitions (primary method)
  - Significant temperature drops (>20°C) indicating product removal
  - Cooling rate validation to confirm end of baking

### 2. Curve Selection Interface
- When multiple curves are detected, a curve selector appears in the sidebar
- Each curve is labeled with:
  - Curve number (1, 2, 3, etc.)
  - Duration in minutes
  - Maximum core temperature
- Users can easily switch between curves for individual analysis

### 3. Curve Comparison Tab
- New "Curve Comparison" tab appears only when multiple curves are present
- Features include:
  - **Temperature Profile Comparison**: Overlay multiple curves on one plot
  - **Comparison Metrics Table**: Side-by-side metrics for selected curves
  - **S-Curve Comparison**: Compare S-curve landmarks across curves
  - Checkbox selection to choose which curves to compare

### 4. Data Structure Enhancements
- `ThermalProfileLoader` class additions:
  - `all_curves`: List storing all detected curves
  - `get_all_curves()`: Returns all curve data and metadata
  - `get_curve_count()`: Returns number of detected curves
  - `set_current_curve(index)`: Switch to a different curve for analysis
  - `get_current_curve_info()`: Get metadata about current curve

## Technical Implementation

### Curve Extraction Algorithm
```python
def _extract_all_baking_curves(self, df: pd.DataFrame) -> list:
    # Parameters
    MIN_CURVE_DURATION = 60  # 5 minutes at 5-second intervals
    MIN_BAKING_TEMP = 80     # Minimum peak temperature
    TEMP_RISE_THRESHOLD = 5  # Temperature rise to detect start
    TEMP_DROP_THRESHOLD = 20 # Temperature drop to separate curves
    
    # Iteratively find all curves
    # Each curve: start → peak → significant drop
    # Next curve starts after previous curve ends
```

### Curve Metadata Structure
Each detected curve contains:
```python
{
    'data': DataFrame,          # Curve data with reset timestamps
    'start_idx': int,          # Original start index
    'end_idx': int,            # Original end index
    'start_time': float,       # Original start timestamp
    'end_time': float,         # Original end timestamp
    'duration': float,         # Duration in minutes
    'max_temp': float,         # Maximum core temperature
    'curve_number': int,       # 1-based curve number
    'samples': int             # Number of data points
}
```

## User Workflow

1. **Upload CSV**: User uploads a CSV file with multiple baking sessions
2. **Automatic Detection**: System detects and reports number of curves found
3. **Curve Selection**: User selects which curve to analyze from dropdown
4. **Individual Analysis**: All existing analysis tabs work on selected curve
5. **Comparison**: User can compare multiple curves in the comparison tab

## Benefits

1. **Efficiency**: No need to manually split CSV files
2. **Comparison**: Easy comparison of multiple baking sessions
3. **Quality Control**: Identify variations between batches
4. **Process Optimization**: Track improvements across multiple runs

## Example Use Case

A user performs 3 baking sessions in one shift:
- Session 1: Standard recipe
- Session 2: Modified temperature profile
- Session 3: Extended bake time

All data is logged continuously and downloaded as one CSV. The application:
1. Automatically identifies all 3 curves
2. Allows individual analysis of each session
3. Enables side-by-side comparison to evaluate changes

## Future Enhancements

Potential improvements for future versions:
1. Automatic curve labeling based on patterns
2. Statistical comparison of curve variations
3. Export individual curves as separate CSV files
4. Batch analysis across all curves
5. Curve clustering and anomaly detection