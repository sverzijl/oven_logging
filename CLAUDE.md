# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Streamlit-based thermal profile analyzer for optimizing bread baking processes in manufacturing environments. The application analyzes temperature data from multi-sensor probes to provide insights on baking quality, efficiency, and yield.

## Key Commands

### Setup and Installation
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Run Streamlit app
streamlit run app.py

# Run with specific port
streamlit run app.py --server.port 8080
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_thermal_analysis.py

# Run with coverage
pytest --cov=src tests/
```

### Code Quality
```bash
# Format code
black .

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

## Architecture Overview

The application processes CSV files containing temperature probe data with the following structure:
- 8 temperature sensors (T1-T8) measuring different positions
- Virtual temperature calculations (Core, Surface, Ambient) with dynamic sensor assignments
- VirtualCoreSensor, VirtualSurfaceSensor, VirtualAmbientSensor columns indicating which physical sensors are used
- Time-series data with 5-second intervals
- Critical temperature zones for bread baking analysis

**Important**: The probe firmware dynamically selects which sensors represent core, surface, and ambient based on actual temperature readings. This accounts for variations in probe insertion angle and position. The application should use these virtual assignments rather than assuming fixed sensor mappings.

### Core Analysis Modules

1. **Thermal Analysis**: Calculates heating rates, temperature gradients, and heat penetration efficiency
2. **Zone Analysis**: Identifies time spent in critical temperature zones (yeast kill at 56°C, starch gelatinization at 65-82°C, protein denaturation at 71-85°C)
3. **S-Curve Analysis**: Generates and analyzes the characteristic S-curve showing internal product temperature vs. time, identifying three major zones:
   - **Oven Spring Zone** (up to ~56°C): Final fermentation and volume expansion
   - **Critical Change Zone** (56-93°C): Yeast kill, starch gelatinization, protein denaturation
   - **Bake-Out Zone** (above 93°C): Moisture loss and final texture development
4. **Quality Metrics**: Evaluates temperature uniformity, baking consistency, and deviation from ideal profiles
5. **Optimization**: Provides recommendations for process improvements based on S-curve landmarks

### S-Curve Landmarks and Quality Indicators

Key S-curve milestones as percentage of total bake time:
- **Yeast Kill** (~56°C): Should occur at 45-55% of bake time
- **Starch Gelatinization Complete** (~82°C): Target ~60% of bake time
- **Arrival Temperature** (~93°C): Should reach at 80-90% of bake time
- **Bake-Out Percentage**: Time after reaching 93°C as % of total bake

Common quality issues diagnosed via S-curve:
- **Dry/Crumbly**: Bake-out >20% (reduce time/temp in final zones)
- **Gummy/Under-baked**: Insufficient bake-out (increase by ~3%)
- **Poor Volume**: Early yeast kill (adjust initial zone temps)
- **Excessive Molding**: High moisture (increase bake-out by ~5%)

### Data Format

Input CSV files must contain:
- Header section with probe metadata
- Column headers including: Timestamp, T1-T8, VirtualCoreTemperature, VirtualSurfaceTemperature, VirtualAmbientTemperature
- Temperature values in Celsius
- Sample period in milliseconds
- Optional: PredictionState column for automatic curve extraction

### Baking Curve Extraction

The application automatically extracts baking curves from the full dataset using the following methodology:

#### Single Curve Extraction (Legacy)
The `_extract_baking_curve()` method is maintained for backward compatibility but now uses the multi-curve extraction internally and returns the first curve.

#### Multiple Curve Extraction
The `_extract_all_baking_curves()` method detects and extracts all baking curves in a dataset:

1. **Start Detection**:
   - Primary method: Identifies when PredictionState changes from "Probe Not Inserted" to "Probe Inserted" or "Cooking"
   - Backup method: Detects rapid temperature rise (>5°C) in CoreAverage
   - Searches iteratively through the entire dataset for multiple curves

2. **End Detection**:
   - Finds peak core temperature for each curve
   - Identifies when temperature drops >20°C from peak (indicating product removal and potential new curve)
   - Validates with cooling rate (>1°C/minute) to confirm product removal from oven
   - Each curve end becomes the starting point for searching the next curve

3. **Validation**:
   - Ensures minimum baking duration (>5 minutes per curve)
   - Verifies maximum core temperature (>80°C) typical for bread baking
   - Removes invalid curve segments

4. **Data Adjustment**:
   - Resets timestamps to start from 0 for each curve
   - Recalculates TimeMinutes based on new zero point
   - Stores metadata for each curve (duration, max temp, sample count)
   - Provides console output with extraction summary for all curves

#### Multi-Curve Interface
When multiple curves are detected:
- A curve selector appears in the sidebar
- Users can switch between curves for individual analysis
- A "Curve Comparison" tab enables side-by-side analysis
- Each curve is labeled with its duration and maximum temperature

## Development Notes

- The application uses Plotly for interactive visualizations
- Session state management is crucial for handling multiple file uploads
- Temperature zone definitions are configurable in config/constants.py
- All analysis functions should handle missing or invalid data gracefully
- File uploads are handled directly from buffer to avoid cross-platform file system issues