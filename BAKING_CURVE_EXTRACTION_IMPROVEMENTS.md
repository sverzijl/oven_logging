# Baking Curve Extraction Improvements

## Summary

I've implemented an improved algorithm to automatically extract the actual baking curve from CSV files containing probe data. The previous implementation loaded all data including pre-baking and post-baking periods, which could skew analysis results.

## Key Improvements

### 1. Automatic Start Detection
- **Primary Method**: Uses the `PredictionState` column to detect when the probe transitions from "Probe Not Inserted" to "Probe Inserted" or "Cooking"
- **Backup Method**: Detects rapid temperature rise (>5°C) in the core temperature average
- **Robustness**: Uses the earlier of both methods to ensure accurate start detection

### 2. Intelligent End Detection
- Identifies peak core temperature during baking
- Detects when temperature drops >5°C from peak (indicating removal from oven)
- Validates with cooling rate (>1°C/minute) to confirm rapid cooling
- Falls back to >10°C drop threshold if initial detection doesn't show rapid cooling

### 3. Data Validation
- Ensures minimum baking duration (>5 minutes) to avoid false positives
- Verifies maximum core temperature (>80°C) typical for bread baking
- Falls back to original data if extraction appears invalid
- Provides console output with extraction summary for debugging

### 4. Data Cleanup
- Resets timestamps to start from 0 for the extracted curve
- Recalculates time in minutes based on new zero point
- Resets DataFrame index for clean data access

## Example with Provided CSV

Based on analysis of `ProbeData_100098DE_2025-05-30 13_51_07.csv`:

- **Original data**: 2238 samples (11,190 seconds / 186.5 minutes)
- **Detected start**: Around timestamp 15 seconds (when probe inserted)
- **Detected end**: Around timestamp 1500 seconds (when rapid cooling begins)
- **Extracted curve**: ~297 samples (~25 minutes of actual baking)
- **Temperature range**: ~33°C to ~98°C

This extraction removes:
- Initial ~15 seconds of ambient temperature readings before probe insertion
- Extended cooling period (~160 minutes) after product removal from oven

## Benefits

1. **More Accurate Analysis**: S-curve and zone analyses now focus only on the actual baking period
2. **Better Metrics**: Bake-out percentages and timing landmarks are calculated correctly
3. **Cleaner Visualizations**: Charts show only relevant data without long cooling tails
4. **Improved Recommendations**: Quality assessments based on true baking duration

## Implementation Location

The extraction logic is implemented in:
- `src/data/loader.py`: Added `_extract_baking_curve()` method to `ThermalProfileLoader` class
- Called automatically during data cleaning in `_clean_data()` method

## Testing

Created `test_extraction.py` to verify the extraction works correctly with sample files. The script:
- Loads CSV files
- Reports extracted duration and temperature range
- Identifies key temperature milestones
- Shows first/last rows of extracted data

The improved extraction ensures that all downstream analyses (S-curve, zones, thermal metrics) operate on the actual baking data rather than the full recording session.