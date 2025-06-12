# Curve Comparison Implementation Plan

## Overview
Refactor the Curve Comparison tab to use role-based comparisons instead of sensor-based comparisons, ensuring visual consistency with other tabs.

## Current Issues
1. Compares sensors by number (T1 vs T1) rather than role (core vs core)
2. Doesn't account for different probe orientations between curves
3. Visual styling inconsistent with other tabs
4. Missing zone analysis comparison
5. Layout not optimized for comparison

## Implementation Strategy

### Phase 1: Architecture & Testing
1. Create new `CurveComparison` class in `src/analysis/curve_comparison.py`
2. Write comprehensive tests first (TDD approach)
3. Encapsulate all comparison logic in the new module

### Phase 2: Core Features
1. **Role-Based Temperature Comparison**
   - Group sensors by role (core, surface, internal, ambient)
   - Use standardized columns (CoreTemperature, SurfaceTemperature, etc.)
   - Apply consistent styling from ThermalPlotter

2. **Zone Analysis Comparison**
   - Compare time spent in each temperature zone
   - Visual bar charts or stacked charts
   - Highlight differences between curves

3. **Enhanced S-Curve Comparison**
   - Improved landmark visualization
   - Better use of color coding
   - Show quality scores for each curve

4. **Heating Rate Comparison**
   - Compare heating consistency metrics
   - Visual representation of rate differences

### Phase 3: Visual Improvements
1. Use metric cards consistent with other tabs
2. Implement proper grid layout
3. Add summary statistics at the top
4. Improve color scheme and legends

### Phase 4: Integration
1. Update app.py to use new comparison module
2. Ensure backward compatibility
3. Test with various multi-curve scenarios

## Risk Mitigation
- Comprehensive test coverage before integration
- Keep original code as fallback initially
- Test with real-world multi-curve files
- Validate sensor role assignments persist correctly

## Success Criteria
- All tests pass
- Visual consistency with other tabs
- Meaningful role-based comparisons
- Improved user experience
- No regression in existing functionality