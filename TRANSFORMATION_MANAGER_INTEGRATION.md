# TransformationManager Integration Guide

## Overview

The TransformationManager solves the column overwrite issue by centralizing all data transformation logic and explicitly tracking what transformations have been applied. This prevents bugs like the surface temperature overwrite from happening again.

## Key Benefits

1. **Single Source of Truth**: All column generation happens through one manager
2. **Explicit State Tracking**: Know exactly what transformations are active
3. **Immutable Operations**: Always works on copies, preventing side effects
4. **Clear Order of Operations**: Transformations applied in defined sequence
5. **Easy Testing**: Comprehensive test suite ensures correctness

## Integration Points

To integrate TransformationManager into the existing loader, we would:

### 1. Add TransformationManager to ThermalProfileLoader

```python
def __init__(self):
    # ... existing init code ...
    self.transformation_manager = TransformationManager()
```

### 2. Replace _identify_sensor_roles() logic

```python
def _identify_sensor_roles(self, df: pd.DataFrame) -> pd.DataFrame:
    # Get base assignments
    virtual_assignments = {
        'core': self.sensor_assignments.get('core', 'T1'),
        'surface': self.sensor_assignments.get('surface', 'T6'),
        'ambient': self.sensor_assignments.get('ambient', 'T8')
    }
    
    # Check for physics correction
    physics_correction = None
    if self._should_apply_physics_correction(df):
        corrected_sensor = self._detect_surface_sensor(df)
        if corrected_sensor != virtual_assignments['surface']:
            physics_correction = (virtual_assignments['surface'], corrected_sensor)
    
    # Apply all transformations through manager
    return self.transformation_manager.apply_transformations(
        df,
        curve_index=self.current_curve_index,
        virtual_assignments=virtual_assignments,
        physics_correction=physics_correction
    )
```

### 3. Replace _regenerate_standard_columns()

```python
def _regenerate_standard_columns(self):
    if self.data is None:
        return
    
    # Get current assignments
    virtual_assignments = {
        'core': self.sensor_assignments.get('core', 'T1'),
        'surface': self.sensor_assignments.get('surface', 'T6'),
        'ambient': self.sensor_assignments.get('ambient', 'T8')
    }
    
    # Check for manual overrides
    manual_overrides = None
    if self.current_curve_index in self._sensor_overrides:
        manual_overrides = self._sensor_overrides[self.current_curve_index]
    
    # Apply transformations
    self.data = self.transformation_manager.apply_transformations(
        self.data,
        curve_index=self.current_curve_index,
        virtual_assignments=virtual_assignments,
        manual_overrides=manual_overrides
    )
```

### 4. Update sensor getter methods

```python
def get_surface_sensor(self, curve_index: Optional[int] = None) -> str:
    idx = curve_index if curve_index is not None else self.current_curve_index
    return self.transformation_manager.get_effective_sensor(idx, 'surface')

def get_core_sensor(self, curve_index: Optional[int] = None) -> str:
    idx = curve_index if curve_index is not None else self.current_curve_index
    return self.transformation_manager.get_effective_sensor(idx, 'core')
```

## Testing Results

The TransformationManager has been thoroughly tested:

- ✅ Basic virtual column transformation
- ✅ Physics-based surface correction
- ✅ Manual override handling
- ✅ Transformation persistence
- ✅ Multiple curve support
- ✅ Backward compatibility
- ✅ Real-world scenarios

All tests pass, demonstrating robustness.

## Migration Strategy

1. **Phase 1**: Add TransformationManager alongside existing code
2. **Phase 2**: Gradually migrate column generation to use manager
3. **Phase 3**: Remove old column generation code
4. **Phase 4**: Add additional transformations as needed

## Future Extensions

The TransformationManager architecture makes it easy to add new transformations:

- Temperature smoothing
- Outlier correction
- Sensor calibration
- Custom user transformations

Each would be a new TransformationType with clear application logic.

## Conclusion

The TransformationManager provides a robust solution to prevent column overwrite bugs while maintaining backward compatibility and improving code maintainability. The architecture is extensible and well-tested, making it a solid foundation for future enhancements.