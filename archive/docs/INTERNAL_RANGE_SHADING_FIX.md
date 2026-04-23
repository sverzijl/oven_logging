# Internal Temperature Range Shading Fix

## Overview
Fixed the missing internal temperature range shading in the Curve Comparison tab's S-Curve Analysis section. The shaded region representing the spread of internal sensor temperatures was correctly displayed in the single S-Curve Analysis tab but was missing in the Curve Comparison feature.

## Root Cause
The `plot_s_curve_comparison` function in `src/visualization/plots.py` did not support internal sensor data, while the single-curve `plot_s_curve` function did. Additionally, the Curve Comparison code in `app.py` wasn't extracting internal sensors for each curve.

## Changes Made

### 1. Refactored Shading Logic (`src/visualization/plots.py`)
- **Added `_add_internal_temperature_shading` method**: Extracted the shading logic into a reusable private method to eliminate code duplication
- **Updated `plot_s_curve`**: Now uses the new shared method instead of inline code
- **Enhanced `plot_s_curve_comparison`**: 
  - Added support for `internal_sensors` in the curve data dictionary
  - Applies shading with varying opacity (0.15-0.25) for each curve to prevent visual confusion
  - Groups shading traces with their corresponding curves using `legendgroup`

### 2. Updated Curve Comparison Logic (`app.py`)
- Modified the S-Curve Comparison section (lines 1184-1203) to:
  - Extract internal sensors for each curve using the curve-specific loader
  - Pass internal sensors to the plot function in the curve data structure

### 3. Comprehensive Testing
- **Unit Tests** (`tests/test_thermal_plotter.py`):
  - Tests for the shared `_add_internal_temperature_shading` method
  - Tests for both single and comparison plot functions
  - Edge cases like single sensor, no sensors, and mixed scenarios
  
- **Integration Tests** (`tests/test_internal_range_integration.py`):
  - End-to-end tests simulating the full app flow
  - Consistency checks between single and comparison views
  - Tests with the actual app.py data structures

## Technical Details

### Shading Implementation
The internal temperature range is visualized using Plotly's `fill='tonexty'` feature:
1. An invisible trace plots the maximum temperature values
2. A visible trace plots the minimum temperature values with fill to the previous trace
3. The fill creates a shaded area representing the temperature spread
4. Hover information shows both min and max values

### Multi-Curve Considerations
- Each curve gets its own shading with a unique opacity to prevent overlap confusion
- Legend groups ensure shading traces are associated with their parent curves
- The implementation supports mixed scenarios where some curves have internal sensors and others don't

## Benefits
1. **Consistency**: Both S-Curve Analysis views now show the same visualization
2. **Code Reuse**: Eliminated duplicate shading logic through refactoring
3. **Flexibility**: The shared method supports customization (color, name, legend group)
4. **Robustness**: Comprehensive tests ensure the fix works correctly and prevents regression

## Usage
The internal temperature shading now appears automatically in the Curve Comparison tab when:
1. Multiple curves are selected for comparison
2. The curves have identified internal sensors
3. The user navigates to the "S-Curve Comparison" subtab

The shading provides valuable insight into the temperature gradient within the product during baking, helping identify potential quality issues related to uneven heating.