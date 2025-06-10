# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Streamlit-based thermal profile analyzer for optimizing bread baking processes in manufacturing environments. The application analyzes temperature data from multi-sensor probes to provide insights on baking quality, efficiency, and yield.

## Key Commands

### Setup and Installation
```bash
# Create virtual environment (requires Python 3)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# IMPORTANT: Always activate the virtual environment first
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Run Streamlit app
streamlit run app.py

# Run with specific port
streamlit run app.py --server.port 8080
```

### Testing
```bash
# IMPORTANT: Always activate the virtual environment first
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Run all tests
pytest

# Run specific test file
pytest tests/test_thermal_analysis.py

# Run with coverage
pytest --cov=src tests/
```

### Code Quality
```bash
# IMPORTANT: Always activate the virtual environment first
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Format code
black .

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

### Python Environment
- **Python Version**: This project requires Python 3 (use `python3` command)
- **Virtual Environment**: Always use the virtual environment (`venv`) to avoid dependency conflicts
- **Activation**: Remember to activate the virtual environment before running any commands

## Architecture Overview

The application processes CSV files containing temperature probe data with the following structure:
- 8 temperature sensors (T1-T8) measuring different positions
- Virtual temperature calculations (Core, Surface, Ambient) with dynamic sensor assignments
- VirtualCoreSensor, VirtualSurfaceSensor, VirtualAmbientSensor columns indicating which physical sensors are used
- Time-series data with 5-second intervals
- Critical temperature zones for bread baking analysis

**Important - Probe Insertion Variability**: 
- The probe is manually inserted into the dough with T1 first, but insertion depth and angle vary significantly between uses
- **Shallow insertion**: T1 may be in the crust rather than core, with actual core being T3-T4
- **Deep insertion**: T1 may punch through the bread, with T3-T4 being the actual core
- **Variable depth**: Different bread sizes and probe positioning affect which sensors measure what
- The probe firmware attempts to identify sensor roles dynamically, but may misclassify them
- The outermost sensor (T8) might measure either surface/crust temperature OR ambient oven temperature depending on insertion depth

**Zone Analysis Temperature Selection**:
The zone analyzer now uses intelligent temperature source identification that:
1. Analyzes temperature patterns rather than relying solely on sensor positions or virtual assignments
2. Identifies surface sensors by looking for temperatures in the 110-180°C range (crust formation)
3. Identifies core sensors by looking for temperatures in the 85-105°C range
4. Distinguishes between surface and ambient by heating rates and maximum temperatures
5. Applies appropriate temperature sources for each zone:
   - **Core zones**: Yeast Kill, Starch Gelatinization, Protein Denaturation, Target Core
   - **Surface zones**: Crust Formation, Maillard Reaction, Caramelization

**Recent Improvements**:

*Zone Analysis*:
1. **Dynamic Temperature Source Detection**: Both `zone_analysis.py` and `thermal_analysis.py` now intelligently identify which sensors/columns represent core vs surface temperatures based on temperature patterns
2. **Zone-Specific Uniformity Analysis**: Uniformity is now calculated using appropriate sensors for each zone type (core sensors for core zones, surface sensors for surface zones)
3. **Separated Zone Transitions**: Core and surface zone transitions are calculated separately to avoid invalid comparisons between different temperature sources
4. **Temperature-Type Aware Recommendations**: Optimization recommendations now consider whether issues are related to core or surface temperatures, providing more targeted advice
5. **Additional Surface Zones**: Added Maillard Reaction (105-150°C) and Caramelization (150-200°C) zones for comprehensive surface analysis

*Curve Extraction and Data Quality*:
1. **Improved Probe Removal Detection**: Enhanced curve extraction to detect rapid temperature drops (>15°C in 5 seconds) indicating probe removal from oven
2. **Robust Heating Consistency**: Fixed bug where heating consistency showed 0.0% when probe removal was included in data:
   - Added IQR-based outlier detection to remove statistical anomalies
   - Rate limiting clips extreme values at ±1.0°C/s (±60°C/min)
   - Proper handling of insufficient data points
3. **Better Peak Detection**: Curve extraction now correctly identifies peak temperature and stops when massive drops occur
4. **Immediate Drop Detection**: Removed artificial delays that prevented detection of rapid drops immediately after peak temperature

*User Interface*:
1. **Beautiful Metric Cards**: Quality metrics now display with visual indicators, color coding, and expandable explanations
2. **Zone Analysis Cards**: Each temperature zone shows with status indicators, timing assessment, and detailed explanations of the biochemical processes
3. **Interactive Explanations**: All metrics and zones include expandable sections explaining what they measure, why they matter, and how to interpret them
4. **Visual Quality Indicators**: Color-coded ratings (Excellent/Good/Acceptable/Poor) with specific thresholds
5. **Context-Aware Help**: Tooltips and info boxes throughout the interface to guide users
6. **Professional Styling**: Gradient backgrounds, icons, and consistent color schemes for better visual hierarchy

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
   - Detects rapid temperature drops indicating probe removal:
     - Instant drops >15°C in one 5-second interval
     - Sustained drop rates >2°C/second (120°C/min)
   - Identifies when temperature drops >20°C from peak (indicating product removal)
   - Validates with cooling rate to confirm product removal from oven
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