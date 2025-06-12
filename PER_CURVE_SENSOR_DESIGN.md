# Per-Curve Sensor Identification Design

## Problem Statement
Currently, sensor identification (including physics-based surface correction) happens once at the file level. All curves within a multi-curve file share the same sensor assignments, which is problematic when probes are positioned differently between baking sessions.

## Proposed Solution

### 1. Architecture Changes

#### A. Move sensor identification from file-level to curve-level
- Remove sensor identification from `_clean_data()`
- Add sensor identification to each curve after extraction
- Each curve will have its own `sensor_assignments` dictionary

#### B. Data Structure Changes
```python
# Current structure
self.sensor_assignments = {...}  # Single assignment for all curves

# New structure
self.curve_sensor_assignments = {
    0: {  # Curve index
        'core': 'T1',
        'surface': 'T5',
        'ambient': 'T8',
        'physics_corrected': True,
        'surface_detection': {...}
    },
    1: {  # Different assignments for curve 1
        'core': 'T2',
        'surface': 'T6',
        'ambient': 'T8',
        'physics_corrected': True,
        'surface_detection': {...}
    }
}
```

### 2. Implementation Plan

#### Phase 1: Refactor sensor identification
1. Create `_identify_sensor_roles_for_curve(curve_data)` method
2. Move physics-based correction into per-curve identification
3. Store assignments per curve

#### Phase 2: Update curve extraction
1. After extracting each curve, run sensor identification
2. Store sensor assignments with curve metadata
3. Apply standardized columns per curve

#### Phase 3: Update accessor methods
1. Modify all getter methods to use curve-specific assignments
2. Update manual override system to work per-curve
3. Ensure backward compatibility

### 3. Key Methods to Modify

1. **`_clean_data()`** - Remove sensor identification
2. **`_extract_all_baking_curves()`** - Add sensor identification per curve
3. **`_identify_sensor_roles()`** - Rename to `_identify_sensor_roles_for_curve()`
4. **`set_current_curve()`** - Load curve-specific assignments
5. **All sensor getter methods** - Use curve-specific assignments

### 4. Benefits

1. **Accuracy**: Each curve gets accurate sensor identification based on its own data
2. **Flexibility**: Different probe positions between sessions are handled correctly
3. **Consistency**: Physics-based corrections apply to the specific curve data
4. **Debugging**: Easier to track and debug sensor assignments per curve

### 5. Testing Strategy

1. Create test file with multiple curves where probe position changes
2. Verify each curve gets different sensor assignments
3. Test physics-based correction works per curve
4. Ensure manual overrides still work correctly
5. Verify backward compatibility with single-curve files