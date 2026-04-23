# Zone Analysis Fix Implementation Plan

## Issues Identified

### 1. Zone Status Logic Issues
- **Problem**: Only YEAST_KILL zone has proper timing assessment logic
- **Impact**: Other zones show "Normal" status even when duration differs significantly from ideal
- **Location**: `src/visualization/zone_cards.py` lines 85-113

### 2. Potential Sensor Selection Issues
- **Problem**: Two separate zone analysis implementations (ZoneAnalyzer and ThermalAnalyzer)
- **Impact**: Possible inconsistencies in sensor selection for surface zones
- **Location**: 
  - `src/analysis/zone_analysis.py` - primary implementation
  - `src/analysis/thermal_analysis.py` - secondary implementation

### 3. UI Layout Issues
- **Problem**: Excessive vertical scrolling due to individual zone cards
- **Impact**: Poor user experience, difficult to see all zones at once
- **Location**: `src/visualization/zone_cards.py` create_zone_summary_dashboard()

### 4. Code Duplication
- **Problem**: Zone analysis logic exists in both ZoneAnalyzer and ThermalAnalyzer
- **Impact**: Maintenance burden, potential for inconsistencies
- **Location**: Both analysis modules

## Implementation Plan

### Phase 1: Fix Zone Status Logic
1. Add proper duration checking for all zones based on ideal ranges
2. Implement consistent status determination logic
3. Color-code based on deviation from ideal

### Phase 2: Consolidate Zone Analysis
1. Use ZoneAnalyzer as the single source of truth
2. Remove duplicate zone analysis from ThermalAnalyzer
3. Ensure consistent sensor selection

### Phase 3: Improve UI Layout
1. Create a compact zone summary view
2. Use columns for better space utilization
3. Keep expandable details but reduce default height

### Phase 4: Testing
1. Create test cases for each zone type
2. Verify sensor selection for surface zones
3. Test with multiple curve files

## Testing Strategy

### Unit Tests
1. Test zone duration assessment logic
2. Test sensor selection for surface vs core zones
3. Test status determination for various scenarios

### Integration Tests
1. Test with sample CSV files
2. Verify UI displays correct information
3. Test with manual sensor overrides

### Manual Testing Checklist
- [ ] Load sample file with all zones present
- [ ] Verify crust formation uses surface sensor
- [ ] Check status shows correct assessment (not just "Normal")
- [ ] Confirm UI requires minimal scrolling
- [ ] Test with multiple curves
- [ ] Test with sensor overrides

## Success Criteria
1. All zones show accurate status based on ideal duration ranges
2. Surface zones consistently use surface temperature sensors
3. UI fits on standard screen without excessive scrolling
4. No code duplication between analyzers
5. All tests pass