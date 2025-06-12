# Refactoring Analysis: Data Transformation Architecture

## UPDATE: Solution Implemented ✅

A **TransformationManager** has been implemented and tested to solve the column overwrite issues. See implementation details below.

## Current Issues

### 1. **Multiple Points of Column Generation/Modification**
The standardized columns (CoreTemperature, SurfaceTemperature, AmbientTemperature) are created/modified in multiple places:
- Initial load from Virtual columns (line 259-261)
- Physics-based surface correction (line 347)
- Manual override regeneration (line 1233-1305)
- During curve extraction (line 814, 1044)

**Problem**: Each modification point must remember to preserve previous transformations, leading to bugs like the surface temperature overwrite.

### 2. **Order-Dependent Transformations**
Current transformations must be applied in a specific order:
1. Load Virtual columns
2. Apply physics-based correction
3. Apply manual overrides (if any)

**Problem**: If any step accidentally regenerates columns, it can undo previous steps.

### 3. **Inconsistent State Management**
- `self.data` may not always represent the current curve
- `get_internal_sensors()` relies on data being passed or uses `self.data`
- No clear separation between "raw" and "processed" data

### 4. **Repeated Patterns That Could Fail**
Similar to the surface temperature issue, these patterns could fail:

#### a) Internal Sensor Filtering
- `get_internal_sensors()` is called dynamically
- If called with wrong data or at wrong time, could return incorrect sensors
- No caching of results per curve

#### b) Backward Compatibility Columns
- CoreAverage/SurfaceAverage created in multiple places
- Could be inconsistent if regenerated after corrections

#### c) Curve Extraction
- Each curve gets `.copy()` of data
- Columns are regenerated for each curve
- Physics corrections might not persist

## Root Cause Analysis

The fundamental issue is **mutable state being modified in multiple places without clear ownership**. The data transformation pipeline lacks:
1. **Immutability**: Transformations modify existing data instead of creating new
2. **Clear Pipeline**: No enforced order of operations
3. **Single Responsibility**: Multiple methods can modify the same columns
4. **Validation**: No checks that transformations are preserved

## Proposed Refactoring Solutions

### Solution 1: Immutable Transformation Pipeline
Create a clear, immutable pipeline where each transformation returns new data:

```python
class DataTransformationPipeline:
    def __init__(self, raw_data):
        self.raw_data = raw_data
        self.transformations = []
    
    def apply_virtual_columns(self):
        # Returns new DataFrame with virtual columns
        pass
    
    def apply_physics_correction(self):
        # Returns new DataFrame with corrected surface
        pass
    
    def apply_manual_overrides(self, overrides):
        # Returns new DataFrame with overrides
        pass
    
    def get_transformed_data(self):
        # Applies all transformations in order
        data = self.raw_data.copy()
        for transform in self.transformations:
            data = transform(data)
        return data
```

### Solution 2: Sensor Assignment Manager
Centralize all sensor role management:

```python
class SensorAssignmentManager:
    def __init__(self):
        self.base_assignments = {}  # From CSV
        self.physics_corrections = {}  # Physics-based
        self.manual_overrides = {}  # User overrides
        self._cache = {}  # Cache computed results
    
    def get_effective_assignments(self, curve_index):
        # Returns final assignments considering all layers
        if curve_index in self._cache:
            return self._cache[curve_index]
        
        # Start with base
        assignments = self.base_assignments[curve_index].copy()
        
        # Apply physics corrections
        if curve_index in self.physics_corrections:
            assignments.update(self.physics_corrections[curve_index])
        
        # Apply manual overrides
        if curve_index in self.manual_overrides:
            assignments.update(self.manual_overrides[curve_index])
        
        self._cache[curve_index] = assignments
        return assignments
    
    def invalidate_cache(self, curve_index=None):
        # Clear cache when assignments change
        pass
```

### Solution 3: Column Generation Strategy Pattern
Use strategy pattern for column generation:

```python
class ColumnGenerationStrategy:
    def generate_columns(self, data, sensor_assignments):
        raise NotImplementedError

class StandardColumnStrategy(ColumnGenerationStrategy):
    def generate_columns(self, data, sensor_assignments):
        # Generate CoreTemperature, etc.
        pass

class PhysicsCorrectedStrategy(ColumnGenerationStrategy):
    def __init__(self, base_strategy):
        self.base_strategy = base_strategy
    
    def generate_columns(self, data, sensor_assignments):
        # First apply base
        data = self.base_strategy.generate_columns(data, sensor_assignments)
        # Then apply physics corrections
        return self._apply_physics_corrections(data, sensor_assignments)
```

### Solution 4: Data Version Control
Track data transformations with versioning:

```python
class DataVersion:
    def __init__(self, data, version_info):
        self.data = data
        self.version = version_info
        self.transformations_applied = []
    
    def has_transformation(self, transformation_name):
        return transformation_name in self.transformations_applied
    
    def apply_transformation(self, name, transform_func):
        if self.has_transformation(name):
            return self  # Already applied
        
        new_data = transform_func(self.data.copy())
        new_version = DataVersion(new_data, self.version + 1)
        new_version.transformations_applied = self.transformations_applied + [name]
        return new_version
```

## Recommended Approach

### Phase 1: Immediate Fixes (Low Risk)
1. **Add transformation flags** to track what's been applied
2. **Create single column generation method** that respects all transformations
3. **Add validation** to ensure transformations aren't lost

### Phase 2: Medium-term Refactoring (Medium Risk)
1. **Implement SensorAssignmentManager** to centralize sensor role logic
2. **Create clear transformation pipeline** with defined order
3. **Add comprehensive tests** for transformation combinations

### Phase 3: Long-term Architecture (Higher Risk)
1. **Make data transformations immutable**
2. **Implement proper caching** for expensive computations
3. **Use event-driven updates** instead of regenerating

## Specific Vulnerabilities to Address

1. **Surface Temperature Overwrite** (FIXED)
   - Already addressed in loader.py

2. **Internal Sensor Filtering**
   - Currently recomputed each time
   - Should cache results per curve
   - Should validate data parameter matches curve

3. **Curve Switching**
   - `_regenerate_standard_columns()` should preserve all transformations
   - Need to track transformation state per curve

4. **Manual Overrides**
   - Should layer on top of physics corrections, not replace them
   - Need clear precedence rules

5. **Multi-curve Files**
   - Each curve should maintain its own transformation state
   - Switching curves shouldn't lose transformations

## Testing Strategy

1. **Unit Tests**
   - Test each transformation in isolation
   - Test transformation combinations
   - Test preservation across operations

2. **Integration Tests**
   - Test full pipeline with all transformations
   - Test curve switching
   - Test manual overrides with physics corrections

3. **Property-based Tests**
   - Transformations should be idempotent
   - Order of independent transformations shouldn't matter
   - Transformations should preserve data integrity

## Conclusion

The current architecture's main weakness is **mutable shared state** being modified in multiple places. The proposed refactoring would:
1. Make transformations explicit and traceable
2. Prevent accidental overwrites
3. Improve testability and maintainability
4. Make the codebase more robust to future changes

The phased approach allows for incremental improvements while maintaining backward compatibility.

## Implementation Update

### TransformationManager Created ✅

A complete implementation of the TransformationManager has been created in `src/data/transformation_manager.py` with the following features:

1. **Centralized Transformation Logic**
   - Single entry point for all column transformations
   - Clear order of operations: Virtual → Physics → Manual → Compatibility

2. **Explicit State Tracking**
   - Tracks which transformations have been applied per curve
   - Preserves physics corrections when regenerating columns
   - Handles manual override layering correctly

3. **Comprehensive Testing**
   - 7 test scenarios all passing
   - Verified prevention of the original surface temperature bug
   - Tested complex multi-curve scenarios

### Test Results

```
✅ Basic virtual column transformation
✅ Physics-based surface correction
✅ Manual override handling
✅ Transformation persistence
✅ Multiple curve support
✅ Backward compatibility
✅ Real-world scenarios
```

### Integration Guide

A complete integration guide has been created in `TRANSFORMATION_MANAGER_INTEGRATION.md` showing how to integrate this into the existing loader with minimal changes.

### Key Achievement

The TransformationManager **successfully prevents the original bug** where physics corrections were lost during column regeneration. It ensures transformations are:
- Applied in the correct order
- Tracked explicitly
- Never accidentally overwritten
- Easy to test and debug