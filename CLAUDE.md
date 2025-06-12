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
- **Package Management**: You know you can use pip to install whatever packages you need

## Architecture Overview

The application processes CSV files containing temperature probe data with the following structure:
- 8 temperature sensors (T1-T8) measuring different positions
- Virtual temperature calculations (Core, Surface, Ambient) with dynamic sensor assignments
- Time-series data with 5-second intervals
- Critical temperature zones for bread baking analysis

### Data Transformation Pipeline

The application uses a multi-stage transformation pipeline for temperature data:

1. **Raw Data Loading**: CSV data with Virtual[Core|Surface|Ambient]Temperature columns
2. **Curve Extraction**: Individual baking sessions are identified and extracted
3. **Per-Curve Sensor Identification**: Each curve gets independent sensor role assignment
4. **Physics-Based Correction**: Corrects firmware surface sensor misidentification per curve
5. **Standardized Columns**: Creates CoreTemperature, SurfaceTemperature, AmbientTemperature
6. **Manual Overrides**: Optional user-specified sensor assignments per curve

**Important Architecture Notes**:
- **Per-Curve Identification**: Sensor roles are identified independently for each curve, allowing for different probe positions between baking sessions
- Transformations must be applied in order to prevent overwrites
- The `physics_corrected` flag tracks when surface correction has been applied
- Manual overrides layer on top of physics corrections, not replace them
- Each curve in multi-curve files maintains its own transformation state
- Sensor assignments are stored in `curve_sensor_assignments[curve_index]`

### Critical Code Paths

1. **Initial Load**: `_clean_data()` prepares data, `_extract_all_baking_curves()` identifies curves
2. **Curve Identification**: `_identify_sensor_roles_for_curve()` applies per-curve sensor detection
3. **Physics Correction**: Applied independently for each curve during identification
4. **Curve Switching**: `set_current_curve()` loads curve-specific sensor assignments
5. **Manual Override**: `_regenerate_standard_columns()` respects existing corrections

### Known Vulnerabilities Fixed

1. **Surface Temperature Overwrite**: Physics corrections were being lost when regenerating columns
   - Fixed by checking `physics_corrected` flag before regenerating
   - Ensures SurfaceTemperature reflects the corrected sensor values

2. **Multi-Curve Sensor Assignment**: All curves were sharing the same sensor assignments
   - Fixed by implementing per-curve sensor identification
   - Each curve now independently identifies sensor roles based on its own data
   - Allows for different probe positions between baking sessions

### Best Practices

- Always check for existing transformations before regenerating columns
- Use standardized column names (CoreTemperature, etc.) in analysis code
- Preserve transformation flags when switching between curves
- Test with multi-curve files to ensure transformations persist

### TransformationManager (New Architecture)

A new `TransformationManager` class has been implemented in `src/data/transformation_manager.py` to prevent column overwrite issues:

**Key Features**:
- Centralized transformation logic with explicit state tracking
- Prevents accidental overwrites of physics corrections
- Supports transformation layering (base → physics → manual)
- Comprehensive test coverage proving it prevents the original bug

**Integration Status**: Ready for integration but not yet integrated into main loader

See `TRANSFORMATION_MANAGER_INTEGRATION.md` for integration guide.

## Visualization Features

### Curve Comparison

The application supports comparing multiple thermal curves with enhanced visualization:

#### Legend Positioning
- Legends are positioned **below** graphs to maximize horizontal plotting space
- Horizontal orientation for better readability
- Applies to all comparison plots:
  - Temperature Profiles
  - Heating Rate Analysis
  - S-Curve Comparison

#### Probe Naming Convention
The system automatically generates concise probe identifiers from CSV metadata:

**Format**: `{Last 4 digits of Probe S/N}_{HH:MM}`
- Single curve example: `98DE_13:51`
- Multi-curve example: `F3C1_09:11_C1`, `F3C1_09:11_C2`

**Metadata Sources**:
- Probe S/N from CSV header
- Timestamp from "Created" field in CSV header
- Falls back to filename parsing if metadata unavailable

**Benefits**:
- Short legends prevent graph compression
- Full probe information available in hover tooltips
- Unique identification for multi-curve files