# Sensor Consistency Implementation Plan

## Overview
This plan addresses the sensor identification inconsistencies by centralizing all sensor role determination in the ThermalProfileLoader, ensuring consistent usage across all modules, and allowing per-curve user overrides for sensor roles.

## Key Requirements
1. **Per-Curve Sensor Assignments**: Each baking curve can have different sensor roles based on probe insertion
2. **User Override Capability**: Users can manually override which sensors are core, surface, and ambient
3. **Limited Display Selection**: "Select Sensors to Display" only appears in Temperature Profile and Curve Comparison tabs
4. **Persistent Overrides**: User selections should persist for each curve during the session

## Implementation Steps

### Step 1: Enhance ThermalProfileLoader API
Add new methods to provide clear sensor role access and support per-curve overrides:

```python
class ThermalProfileLoader:
    def __init__(self):
        # Store sensor overrides per curve
        self._sensor_overrides = {}  # {curve_index: {'core': [...], 'surface': [...], 'ambient': [...]}}
        
    def set_sensor_override(self, curve_index: int, role: str, sensors: List[str]):
        """Allow user to override sensor assignments for a specific curve"""
        if curve_index not in self._sensor_overrides:
            self._sensor_overrides[curve_index] = {}
        self._sensor_overrides[curve_index][role] = sensors
        # Regenerate standard columns for this curve
        self._regenerate_standard_columns(curve_index)
        
    def clear_sensor_overrides(self, curve_index: int):
        """Clear all user overrides for a curve, reverting to automatic detection"""
        if curve_index in self._sensor_overrides:
            del self._sensor_overrides[curve_index]
        self._regenerate_standard_columns(curve_index)
        
    def get_core_sensors(self, curve_index: Optional[int] = None) -> List[str]:
        """Get list of physical sensors identified as core (with override support)"""
        if curve_index is None:
            curve_index = self.current_curve_index
        # Check for user override first
        if curve_index in self._sensor_overrides and 'core' in self._sensor_overrides[curve_index]:
            return self._sensor_overrides[curve_index]['core']
        # Otherwise return automatic detection
        return self._get_automatic_core_sensors(curve_index)
        
    def get_surface_sensors(self, curve_index: Optional[int] = None) -> List[str]:
        """Get list of physical sensors identified as surface (with override support)"""
        # Similar pattern for surface
        
    def get_ambient_sensors(self, curve_index: Optional[int] = None) -> List[str]:
        """Get list of physical sensors identified as ambient (with override support)"""
        # Similar pattern for ambient
        
    def get_sensor_assignments_with_overrides(self, curve_index: Optional[int] = None) -> Dict:
        """Get sensor assignments including override status"""
        assignments = self.get_sensor_assignments()
        if curve_index in self._sensor_overrides:
            assignments['has_overrides'] = True
            assignments['overrides'] = self._sensor_overrides[curve_index]
        return assignments

### Step 2: Standardize Column Generation
Ensure loader always creates these standard columns:
- `CoreTemperature`: Primary core temperature (from virtual or calculated)
- `SurfaceTemperature`: Primary surface temperature (from virtual or calculated)  
- `AmbientTemperature`: Primary ambient temperature (if identifiable)

### Step 3: Update Analysis Modules

#### ThermalAnalyzer
- Remove `_identify_temperature_sources()` method
- Accept loader instance in constructor
- Use loader's sensor assignments for all calculations
- Use standard column names (CoreTemperature, SurfaceTemperature)

#### ZoneAnalyzer
- Remove `_identify_temperature_sources()` and related methods
- Accept loader instance in constructor
- Use loader's sensor assignments for uniformity calculations
- Use standard column names for zone detection

#### SCurveAnalyzer
- Update to use standard CoreTemperature column
- Accept loader instance for consistency

### Step 4: Implement Sensor Override UI

#### Sidebar UI Design
Create a new section in the sidebar for sensor role configuration:

```python
# In app.py sidebar, after curve selection:
if st.session_state.data is not None:
    st.divider()
    st.header("🎯 Sensor Role Configuration")
    
    # Show current assignments
    assignments = st.session_state.loader.get_sensor_assignments_with_overrides(
        st.session_state.current_curve_index
    )
    
    # Display automatic vs override status
    if assignments.get('has_overrides'):
        st.info("📝 Using manual sensor assignments for this curve")
        if st.button("Reset to Automatic Detection"):
            st.session_state.loader.clear_sensor_overrides(st.session_state.current_curve_index)
            st.rerun()
    else:
        st.info("🤖 Using automatic sensor detection")
    
    # Manual override controls
    with st.expander("Override Sensor Assignments", expanded=False):
        st.markdown("Select which sensors represent each role for this specific curve:")
        
        # Core sensors
        current_core = st.session_state.loader.get_core_sensors()
        core_sensors = st.multiselect(
            "Core Sensors (internal temperature)",
            options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
            default=current_core,
            key=f"core_override_{st.session_state.current_curve_index}"
        )
        
        # Surface sensors  
        current_surface = st.session_state.loader.get_surface_sensors()
        surface_sensors = st.multiselect(
            "Surface/Crust Sensors",
            options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
            default=current_surface,
            key=f"surface_override_{st.session_state.current_curve_index}"
        )
        
        # Ambient sensors
        current_ambient = st.session_state.loader.get_ambient_sensors()
        ambient_sensors = st.multiselect(
            "Ambient/Oven Sensors",
            options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
            default=current_ambient,
            key=f"ambient_override_{st.session_state.current_curve_index}"
        )
        
        if st.button("Apply Overrides"):
            # Validate selections
            if not core_sensors:
                st.error("Please select at least one core sensor")
            else:
                # Apply overrides
                st.session_state.loader.set_sensor_override(
                    st.session_state.current_curve_index, 'core', core_sensors
                )
                if surface_sensors:
                    st.session_state.loader.set_sensor_override(
                        st.session_state.current_curve_index, 'surface', surface_sensors
                    )
                if ambient_sensors:
                    st.session_state.loader.set_sensor_override(
                        st.session_state.current_curve_index, 'ambient', ambient_sensors
                    )
                # Recreate analyzers with new assignments
                st.session_state.analyzer = ThermalAnalyzer(
                    st.session_state.data, 
                    st.session_state.metadata,
                    loader=st.session_state.loader
                )
                st.rerun()
```

### Step 5: Fix Visualization

#### ThermalPlotter
- Remove "Select Sensors to Display" from sidebar when not in Temperature Profile or Curve Comparison tabs
- Add visual indicators for sensor roles (e.g., suffix labels like "T1 (Core)")
- Update heating rate plots to use loader's sensor assignments

#### App.py Tab-Specific Controls
```python
# Only show display selection in specific tabs
if current_tab in ['Temperature Profile', 'Curve Comparison']:
    st.divider()
    st.header("📊 Display Options")
    
    show_all_sensors = st.checkbox("Show all sensors", value=False)
    if not show_all_sensors:
        # Get sensor role assignments for labeling
        assignments = st.session_state.loader.get_sensor_assignments_with_overrides()
        
        # Create labels showing sensor roles
        sensor_labels = {}
        for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']:
            roles = []
            if sensor in assignments.get('core', []):
                roles.append('Core')
            if sensor in assignments.get('surface', []):
                roles.append('Surface')
            if sensor in assignments.get('ambient', []):
                roles.append('Ambient')
            
            if roles:
                sensor_labels[sensor] = f"{sensor} ({', '.join(roles)})"
            else:
                sensor_labels[sensor] = sensor
        
        selected_sensors = st.multiselect(
            "Select sensors to display on graph",
            options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
            default=get_default_display_sensors(assignments),
            format_func=lambda x: sensor_labels.get(x, x)
        )
```

### Step 6: Update CLAUDE.md
Add new section explaining:
- How sensor identification works (automatic + manual override)
- That display selection only affects visualization in specific tabs
- How sensor overrides are per-curve
- How to use the sensor role configuration UI

## Benefits

1. **Single Source of Truth**: Loader determines sensor roles once, used everywhere
2. **Consistent Calculations**: All modules use same sensor identification
3. **Per-Curve Flexibility**: Each curve can have different sensor assignments based on probe insertion
4. **User Control**: Manual override capability for cases where automatic detection is incorrect
5. **Clear UI**: Separate controls for sensor roles vs display selection
6. **Maintainable**: Sensor logic in one place, easy to enhance
7. **Backwards Compatible**: Standard columns work with existing code

## UI Flow Summary

### Sidebar Structure:
1. **File Upload**
2. **Curve Selection** (if multiple curves)
3. **Sensor Role Configuration** (NEW)
   - Shows current assignments (automatic or manual)
   - Expandable override controls
   - Per-curve settings
4. **Display Options** (ONLY in Temperature Profile & Curve Comparison tabs)
   - Show all sensors checkbox
   - Select sensors to display (with role labels)

### Key Changes:
- Sensor role configuration is always visible in sidebar
- Display selection only appears in appropriate tabs
- Sensor labels show their assigned roles
- Each curve maintains its own sensor assignments
- Manual overrides are clearly indicated

## Testing Plan

1. Test with files containing virtual sensor assignments
2. Test with files lacking virtual assignments (fallback to thermodynamic)
3. Test manual override functionality:
   - Override sensors for one curve
   - Switch curves and verify assignments are maintained
   - Reset to automatic and verify it works
4. Test unusual probe insertions (shallow, deep, angled)
5. Verify all analysis modules use consistent sensor assignments
6. Verify display selection only appears in correct tabs
7. Test that calculations update when sensor roles are changed

## Migration Notes

- Existing functionality preserved through standard columns
- Sensor overrides stored in session state with loader
- No breaking changes to data format or API
- Gradual implementation possible