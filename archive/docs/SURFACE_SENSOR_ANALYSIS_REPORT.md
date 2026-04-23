# Surface Sensor Selection Analysis Report

## Executive Summary

Analysis of three CSV files reveals a **consistent pattern of surface sensor misidentification** by the probe firmware. In all cases, the firmware selects lower-numbered sensors (T1-T4) as the surface sensor, despite these sensors never reaching browning/crust formation temperatures (110-180°C). The actual surface temperatures are measured by sensors T6-T8, but these are rarely or never selected as the VirtualSurfaceSensor.

## Detailed Analysis

### File 1: ProbeData_1000BA3C_2025-05-30 17_59_37.csv
- **Duration**: ~6.2 hours (31065 seconds)
- **Probe**: 1000BA3C (FW v1.5.3)

#### VirtualSurfaceSensor Assignments:
- T1: 5966 times (96.7%)
- T2: 198 times (3.2%)
- T3: 1 time
- T4: 46 times
- T6: 3 times (0.05%)

#### Maximum Temperatures Reached:
- **Lower sensors (selected as surface):**
  - T1: 98.15°C
  - T2: 98.10°C
  - T3: 98.20°C
  - T4: 98.55°C
- **Higher sensors (actual surface):**
  - T5: 99.30°C
  - T6: 111.35°C ✓ (reaches browning zone)
  - T7: 137.65°C ✓ (reaches browning zone)
  - T8: 176.20°C ✓ (reaches browning zone)

**Issue**: T1 is selected as surface sensor 96.7% of the time but never exceeds 98.15°C. The actual surface sensors (T6-T8) reach proper browning temperatures but are almost never selected.

### File 2: ProbeData_1000F3C1_2025-05-23 09_11_59.csv
- **Duration**: ~8 minutes (480 seconds, appears to be a shorter test)
- **Probe**: 1000F3C1 (FW v2.2.1, newer firmware)

#### VirtualSurfaceSensor Assignments:
- T1: 47 times (9.8%)
- T2: 360 times (74.8%)
- T3: 58 times (12.1%)
- T4: 16 times (3.3%)
- T5: 0 times
- T6: 0 times

#### Maximum Temperatures Reached:
- **Lower sensors (selected as surface):**
  - T1: 97.2°C
  - T2: 97.15°C
  - T3: 97.15°C
  - T4: 97.35°C
- **Higher sensors (actual surface):**
  - T5: 100.95°C
  - T6: 114.85°C ✓ (reaches browning zone)
  - T7: 152.9°C ✓ (reaches browning zone)
  - T8: 234.45°C ✓ (reaches browning zone)

**Issue**: Despite having newer firmware (v2.2.1), the problem persists. T2 is selected as surface sensor 74.8% of the time but never exceeds 97.15°C. Sensors T6-T8 reach proper surface temperatures but are never selected.

### File 3: ProbeData_100098DE_2025-05-30 13_51_07.csv
- **Duration**: ~3.9 hours (14135 seconds)
- **Probe**: 100098DE (FW v1.5.4)

#### VirtualSurfaceSensor Assignments:
- T1: 1785 times (79.5%)
- T2: 21 times (0.9%)
- T3: 15 times (0.7%)
- T4: 410 times (18.3%)
- T5: 8 times (0.4%)
- T6: 0 times

#### Maximum Temperatures Reached:
- **Lower sensors (selected as surface):**
  - T1: 98.65°C
  - T2: 98.25°C
  - T3: 98.05°C
  - T4: 97.85°C
- **Higher sensors (actual surface):**
  - T5: 98.00°C
  - T6: 100.75°C (borderline, just below browning)
  - T7: 112.35°C ✓ (reaches browning zone)
  - T8: 139.15°C ✓ (reaches browning zone)

**Issue**: T1 is selected as surface sensor 79.5% of the time but never exceeds 98.65°C. T7-T8 reach proper surface temperatures but are never selected. T6 is borderline at 100.75°C.

## Key Findings

1. **Consistent Misidentification Pattern**: All three files show the firmware consistently selecting lower-numbered sensors (T1-T4) as the surface sensor, despite these sensors measuring core/internal temperatures.

2. **Temperature Range Mismatch**: 
   - Selected "surface" sensors: 97-99°C range (typical for bread core)
   - Actual surface sensors: 111-234°C range (typical for bread crust)

3. **Firmware Version Independence**: The issue appears in both older (v1.5.3, v1.5.4) and newer (v2.2.1) firmware versions, suggesting this is a fundamental algorithm issue rather than a bug fixed in updates.

4. **Surface Sensor Selection Logic**: The firmware appears to be using incorrect criteria for surface sensor selection, possibly:
   - Selecting sensors with moderate temperatures rather than highest temperatures
   - Not checking if selected sensors reach browning zone temperatures
   - Possibly confusing surface with internal sensors

## Recommendations

1. **Immediate Solution**: Implement manual sensor override functionality in the application to allow users to correct misidentified sensors.

2. **Firmware Fix Needed**: The probe firmware needs to be updated to:
   - Check if selected surface sensors reach temperatures >110°C
   - Prefer higher-numbered sensors (T6-T8) for surface role when they show higher temperatures
   - Validate that surface temperature > core temperature

3. **Application-Level Correction**: Until firmware is fixed, the application should:
   - Automatically detect when VirtualSurfaceSensor never exceeds 100°C
   - Suggest using the highest temperature sensor (typically T7 or T8) as surface
   - Provide warnings when surface sensor selection appears incorrect

4. **Zone Analysis Impact**: Current zone analysis for surface-specific zones (Crust Formation, Maillard Reaction, Caramelization) is likely inaccurate due to using core temperatures instead of actual surface temperatures.