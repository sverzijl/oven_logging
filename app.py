"""
Thermal Profile Analyzer for Bread Baking Optimization
A Streamlit application for analyzing temperature profiles in manufacturing environments.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import io
from pathlib import Path
import plotly.graph_objects as go

# Import custom modules
from src.data.loader import ThermalProfileLoader, validate_thermal_data
from src.analysis.thermal_analysis import ThermalAnalyzer
from src.analysis.zone_analysis import ZoneAnalyzer
from src.analysis.s_curve_analysis import SCurveAnalyzer
from src.analysis.curve_comparison import CurveComparison, transform_sensor_assignments_to_roles
from src.visualization.plots import ThermalPlotter
from src.visualization.metric_cards import create_metric_card, create_metric_dashboard, create_simple_metric
from src.visualization.zone_cards import create_zone_summary_dashboard
from config.constants import TEMPERATURE_ZONES, QUALITY_THRESHOLDS, SENSOR_NAMES, BAKEOUT_TARGETS

# Page configuration
st.set_page_config(
    page_title="Thermal Profile Analyzer",
    page_icon="🍞",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Helper function to get dynamic sensor names based on actual assignments
def get_dynamic_sensor_names(loader):
    """
    Generate sensor names based on actual sensor role assignments.
    
    Args:
        loader: ThermalProfileLoader instance
        
    Returns:
        dict: Mapping of sensor names to their actual roles
    """
    sensor_names = dict(SENSOR_NAMES)  # Start with default names
    
    if loader:
        assignments = loader.get_sensor_assignments()
        
        # If we have assignment info, update sensor names
        if 'core_info' in assignments:
            core_sensors = assignments['core_info'].get('all_sensors', {})
            for sensor, count in core_sensors.items():
                if sensor and sensor.startswith('T'):
                    sensor_names[sensor] = f"Core (Primary)" if sensor == assignments.get('core') else "Core"
                    
        if 'surface_info' in assignments:
            surface_sensors = assignments['surface_info'].get('all_sensors', {})
            for sensor, count in surface_sensors.items():
                if sensor and sensor.startswith('T'):
                    sensor_names[sensor] = f"Surface (Primary)" if sensor == assignments.get('surface') else "Surface"
                    
        if 'ambient_info' in assignments:
            ambient_sensors = assignments['ambient_info'].get('all_sensors', {})
            for sensor, count in ambient_sensors.items():
                if sensor and sensor.startswith('T'):
                    sensor_names[sensor] = f"Ambient (Primary)" if sensor == assignments.get('ambient') else "Ambient"
    
    return sensor_names

# Helper function to get default sensors based on assignments
def get_default_sensors(loader):
    """
    Get default sensors to display based on actual assignments.
    
    Args:
        loader: ThermalProfileLoader instance
        
    Returns:
        list: List of sensor names to display by default
    """
    if not loader:
        return ['T1', 'T4', 'T6', 'T8']  # Fallback defaults
    
    defaults = []
    
    # Get current curve index from session state if available
    curve_index = st.session_state.get('current_curve_index', 0) if hasattr(st, 'session_state') else 0
    
    # Add core sensor
    core_sensor = loader.get_core_sensor(curve_index)
    if core_sensor:
        defaults.append(core_sensor)
    
    # Add surface sensor
    surface_sensor = loader.get_surface_sensor(curve_index)
    if surface_sensor and surface_sensor not in defaults:
        defaults.append(surface_sensor)
    
    # Add one or two internal sensors (not core) for showing spread
    internal_sensors = loader.get_internal_sensors(curve_index)
    for sensor in internal_sensors:
        if sensor != core_sensor and sensor not in defaults:
            defaults.append(sensor)
            if len(defaults) >= 3:  # Limit to show core + surface + 1 internal
                break
    
    # Add one ambient sensor if space
    if len(defaults) < 4:
        ambient_sensors = loader.get_ambient_sensors(curve_index)
        if ambient_sensors and ambient_sensors[0] not in defaults:
            defaults.append(ambient_sensors[0])
    
    # Ensure we have at least some sensors
    if not defaults:
        defaults = ['T1', 'T4', 'T7']
    
    return sorted(defaults, key=lambda x: int(x[1]))

# Custom CSS
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding-left: 20px;
        padding-right: 20px;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'data' not in st.session_state:
    st.session_state.data = None
if 'metadata' not in st.session_state:
    st.session_state.metadata = None
if 'analyzer' not in st.session_state:
    st.session_state.analyzer = None
if 'loader' not in st.session_state:
    st.session_state.loader = None
if 'current_curve_index' not in st.session_state:
    st.session_state.current_curve_index = 0
# Multi-file support
if 'files' not in st.session_state:
    st.session_state.files = {}  # {filename: {'loader': loader, 'metadata': metadata, 'curves': curves}}
if 'all_curves' not in st.session_state:
    st.session_state.all_curves = []  # List of all curves from all files
if 'current_file' not in st.session_state:
    st.session_state.current_file = None
if 'global_curve_index' not in st.session_state:
    st.session_state.global_curve_index = 0

# Title and description
st.title("🍞 Thermal Profile Analyzer")
st.markdown("### Optimize bread baking processes through advanced thermal analysis")

# Initialize analysis settings
show_zones = True
smooth_data = True
selected_sensors = None
product_type = 'white_pan'

# Sidebar for file upload and settings
with st.sidebar:
    st.header("📊 Data Input")
    
    uploaded_files = st.file_uploader(
        "Upload CSV files",
        type=['csv'],
        accept_multiple_files=True,
        help="Upload one or more thermal profile CSVs from Combustion Inc. probe"
    )
    
    if uploaded_files:
        # Process new files that haven't been loaded yet
        new_files_loaded = False
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in st.session_state.files:
                with st.spinner(f"Loading {uploaded_file.name}..."):
                    try:
                        # Load data directly from uploaded file buffer
                        loader = ThermalProfileLoader()
                        data, metadata = loader.load_csv(file_buffer=uploaded_file)
                        
                        # Validate data
                        is_valid, issues = validate_thermal_data(data)
                        
                        if is_valid:
                            # Store file info
                            st.session_state.files[uploaded_file.name] = {
                                'loader': loader,
                                'metadata': metadata,
                                'curves': loader.get_all_curves()
                            }
                            
                            num_curves = loader.get_curve_count()
                            if num_curves > 1:
                                st.success(f"✅ {uploaded_file.name}: Found {num_curves} baking curves.")
                            else:
                                st.success(f"✅ {uploaded_file.name}: Loaded successfully!")
                            
                            new_files_loaded = True
                        else:
                            st.error(f"❌ {uploaded_file.name}: Data validation failed:")
                            for issue in issues:
                                st.warning(issue)
                    except Exception as e:
                        st.error(f"Error loading {uploaded_file.name}: {str(e)}")
        
        # Rebuild all curves list when new files are loaded
        if new_files_loaded or not st.session_state.all_curves:
            st.session_state.all_curves = []
            for filename, file_info in st.session_state.files.items():
                for curve_idx, curve in enumerate(file_info['curves']):
                    st.session_state.all_curves.append({
                        'filename': filename,
                        'file_curve_index': curve_idx,
                        'curve_data': curve,
                        'loader': file_info['loader'],
                        'metadata': file_info['metadata']
                    })
            
            # Set initial curve if this is the first load
            if st.session_state.data is None and st.session_state.all_curves:
                first_curve = st.session_state.all_curves[0]
                st.session_state.current_file = first_curve['filename']
                st.session_state.loader = first_curve['loader']
                st.session_state.metadata = first_curve['metadata']
                st.session_state.data = first_curve['curve_data']['data']
                st.session_state.analyzer = ThermalAnalyzer(st.session_state.data, st.session_state.metadata, st.session_state.loader)
                st.session_state.s_curve_analyzer = SCurveAnalyzer(st.session_state.data, st.session_state.metadata, st.session_state.loader)
                st.session_state.global_curve_index = 0
    
    # File and curve selection
    if st.session_state.all_curves:
        st.divider()
        st.header("📊 Curve Selection")
        
        # Display loaded files
        st.subheader("Loaded Files")
        for filename in st.session_state.files.keys():
            num_curves = len(st.session_state.files[filename]['curves'])
            st.text(f"📄 {filename} ({num_curves} curve{'s' if num_curves > 1 else ''})")
        
        # Create curve options with file names
        curve_options = []
        for i, curve_info in enumerate(st.session_state.all_curves):
            curve_data = curve_info['curve_data']
            file_curve_idx = curve_info['file_curve_index']
            filename = curve_info['filename']
            
            # Create descriptive label
            if len(st.session_state.files[filename]['curves']) > 1:
                curve_label = f"{filename} - Curve {file_curve_idx+1}: {curve_data['duration']:.1f} min, Max {curve_data['max_temp']:.0f}°C"
            else:
                curve_label = f"{filename}: {curve_data['duration']:.1f} min, Max {curve_data['max_temp']:.0f}°C"
            curve_options.append(curve_label)
        
        # Curve selector
        selected_curve_label = st.selectbox(
            "Select baking curve to analyze",
            options=curve_options,
            index=st.session_state.global_curve_index
        )
        
        # Update selection if changed
        new_index = curve_options.index(selected_curve_label)
        if new_index != st.session_state.global_curve_index:
            st.session_state.global_curve_index = new_index
            selected_curve = st.session_state.all_curves[new_index]
            
            # Update session state with selected curve
            st.session_state.current_file = selected_curve['filename']
            st.session_state.loader = selected_curve['loader']
            st.session_state.metadata = selected_curve['metadata']
            st.session_state.data = selected_curve['curve_data']['data']
            st.session_state.current_curve_index = selected_curve['file_curve_index']
            
            # Set curve in loader
            st.session_state.loader.set_current_curve(selected_curve['file_curve_index'])
            
            # Recreate analyzers
            st.session_state.analyzer = ThermalAnalyzer(st.session_state.data, st.session_state.metadata, st.session_state.loader)
            st.session_state.s_curve_analyzer = SCurveAnalyzer(st.session_state.data, st.session_state.metadata, st.session_state.loader)
        
        # Display current curve info
        if st.session_state.global_curve_index < len(st.session_state.all_curves):
            current_curve = st.session_state.all_curves[st.session_state.global_curve_index]
            curve_info = current_curve['curve_data']
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Duration", f"{curve_info['duration']:.1f} min")
            with col2:
                st.metric("Max Temperature", f"{curve_info['max_temp']:.1f}°C")
            with col3:
                st.metric("Data Points", curve_info['samples'])
            
            # Display file metadata
            with st.expander("📋 File Metadata"):
                metadata = current_curve['metadata']
                for key, value in metadata.items():
                    if key not in ['sample_period_ms', 'sample_period_s', 'created_datetime']:
                        st.text(f"{key}: {value}")
            
            # Display sensor assignments
            if st.session_state.loader:
                with st.expander("🌡️ Sensor Role Assignments"):
                    assignments = st.session_state.loader.get_sensor_assignments()
                    if assignments:
                        if 'core' in assignments:
                            st.text(f"Core: {assignments['core']}")
                        if 'surface' in assignments:
                            st.text(f"Surface: {assignments['surface']}")
                        if 'ambient' in assignments:
                            st.text(f"Ambient: {assignments['ambient']}")
                        if 'method' in assignments:
                            st.text(f"Method: {assignments['method']}")
                        
                        # Show detailed info if available
                        for role in ['core_info', 'surface_info', 'ambient_info']:
                            if role in assignments:
                                role_name = role.replace('_info', '').title()
                                info = assignments[role]
                                if 'all_sensors' in info:
                                    st.text(f"\n{role_name} sensor usage:")
                                    for sensor, count in sorted(info['all_sensors'].items()):
                                        percentage = (count / sum(info['all_sensors'].values())) * 100
                                        st.text(f"  {sensor}: {percentage:.1f}%")
                    else:
                        st.info("Sensor assignments not available for this dataset")
    
    # Sensor Role Configuration
    if st.session_state.data is not None and st.session_state.loader:
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
                # Recreate analyzers with new assignments
                st.session_state.analyzer = ThermalAnalyzer(
                    st.session_state.data, 
                    st.session_state.metadata,
                    st.session_state.loader
                )
                st.session_state.s_curve_analyzer = SCurveAnalyzer(
                    st.session_state.data,
                    st.session_state.metadata,
                    st.session_state.loader
                )
                st.rerun()
        else:
            st.info("🤖 Using automatic sensor detection")
        
        # Manual override controls
        with st.expander("Override Sensor Assignments", expanded=False):
            st.markdown("Select which sensors represent each role for this specific curve:")
            st.markdown("*Note: Internal and ambient sensors are automatically inferred based on surface position*")
            
            # Core sensor (single selection)
            current_core = st.session_state.loader.get_core_sensor(st.session_state.current_curve_index)
            core_sensor = st.selectbox(
                "Core Sensor (single sensor for core temperature)",
                options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
                index=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'].index(current_core) if current_core else 0,
                key=f"core_override_{st.session_state.current_curve_index}",
                help="Select the sensor that best represents the core temperature"
            )
            
            # Surface sensor (single selection)
            current_surface = st.session_state.loader.get_surface_sensor(st.session_state.current_curve_index)
            surface_sensor = st.selectbox(
                "Surface/Crust Sensor (interface between core and ambient)",
                options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
                index=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'].index(current_surface) if current_surface else 6,
                key=f"surface_override_{st.session_state.current_curve_index}",
                help="Select the sensor at the bread surface. Internal sensors (below) and ambient sensors (above) will be automatically determined."
            )
            
            # Show inferred sensor groups based on surface selection
            st.markdown("### Inferred Sensor Groups")
            if surface_sensor:
                surface_num = int(surface_sensor[1])
                
                # Internal sensors (below surface)
                internal_sensors = [f'T{i}' for i in range(1, surface_num)]
                if internal_sensors:
                    st.info(f"**Internal sensors**: {', '.join(internal_sensors)} (all sensors below surface)")
                else:
                    st.warning("No internal sensors (surface is T1)")
                
                # Surface
                st.info(f"**Surface sensor**: {surface_sensor}")
                
                # Ambient sensors (above surface)
                ambient_sensors = [f'T{i}' for i in range(surface_num + 1, 9)]
                if ambient_sensors:
                    st.info(f"**Ambient sensors**: {', '.join(ambient_sensors)} (all sensors above surface)")
                else:
                    st.warning("No ambient sensors (surface is T8)")
            
            if st.button("Apply Overrides"):
                # Validation function
                def validate_sensor_assignments(core, surface):
                    errors = []
                    
                    # Check for required selections
                    if not core:
                        errors.append("Please select a core sensor")
                    if not surface:
                        errors.append("Please select a surface sensor")
                    
                    # Check that sensors are different
                    if core and surface and core == surface:
                        errors.append("Core and surface sensors must be different")
                    
                    # Check logical order: core < surface
                    if core and surface:
                        core_num = int(core[1])
                        surface_num = int(surface[1])
                        
                        if core_num >= surface_num:
                            errors.append("Core sensor must have a lower number than surface sensor")
                    
                    return errors
                
                # Validate selections
                errors = validate_sensor_assignments(core_sensor, surface_sensor)
                
                if errors:
                    for error in errors:
                        st.error(error)
                else:
                    # Apply overrides (single sensors)
                    st.session_state.loader.set_sensor_override(
                        st.session_state.current_curve_index, 'core', core_sensor
                    )
                    st.session_state.loader.set_sensor_override(
                        st.session_state.current_curve_index, 'surface', surface_sensor
                    )
                    # Recreate analyzers with new assignments
                    st.session_state.analyzer = ThermalAnalyzer(
                        st.session_state.data, 
                        st.session_state.metadata,
                        st.session_state.loader
                    )
                    st.session_state.s_curve_analyzer = SCurveAnalyzer(
                        st.session_state.data,
                        st.session_state.metadata,
                        st.session_state.loader
                    )
                    st.rerun()
    
    # Analysis settings
    if st.session_state.data is not None:
        st.divider()
        st.header("⚙️ Analysis Settings")
        
        # Move sensor display selection to tabs
        show_zones = st.checkbox("Show temperature zones", value=show_zones)
        smooth_data = st.checkbox("Apply smoothing", value=smooth_data)
        
        # Product type selection for bake-out analysis
        st.subheader("🍞 Product Type")
        product_type = st.selectbox(
            "Select product type",
            options=list(BAKEOUT_TARGETS.keys()),
            format_func=lambda x: x.replace('_', ' ').title(),
            help="Product type affects bake-out target percentages",
            index=0
        )
        
        # File management
        if st.session_state.files:
            st.divider()
            st.header("📁 File Management")
            
            files_to_remove = []
            for filename in st.session_state.files.keys():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.text(f"📄 {filename}")
                with col2:
                    if st.button("🗑", key=f"remove_{filename}", help=f"Remove {filename}"):
                        files_to_remove.append(filename)
            
            # Remove files and rebuild curve list
            if files_to_remove:
                for filename in files_to_remove:
                    del st.session_state.files[filename]
                
                # Rebuild all curves list
                st.session_state.all_curves = []
                for fname, file_info in st.session_state.files.items():
                    for curve_idx, curve in enumerate(file_info['curves']):
                        st.session_state.all_curves.append({
                            'filename': fname,
                            'file_curve_index': curve_idx,
                            'curve_data': curve,
                            'loader': file_info['loader'],
                            'metadata': file_info['metadata']
                        })
                
                # Reset to first curve if current curve was removed
                if st.session_state.all_curves:
                    if st.session_state.global_curve_index >= len(st.session_state.all_curves):
                        st.session_state.global_curve_index = 0
                    first_curve = st.session_state.all_curves[0]
                    st.session_state.current_file = first_curve['filename']
                    st.session_state.loader = first_curve['loader']
                    st.session_state.metadata = first_curve['metadata']
                    st.session_state.data = first_curve['curve_data']['data']
                    st.session_state.analyzer = ThermalAnalyzer(st.session_state.data, st.session_state.metadata)
                    st.session_state.s_curve_analyzer = SCurveAnalyzer(st.session_state.data, st.session_state.metadata)
                else:
                    # No curves left, reset everything
                    st.session_state.data = None
                    st.session_state.metadata = None
                    st.session_state.analyzer = None
                    st.session_state.loader = None
                    st.session_state.current_curve_index = 0
                    st.session_state.global_curve_index = 0
                    st.session_state.current_file = None
                
                st.rerun()

# Main content area
if st.session_state.data is None:
    # Welcome screen
    st.info("👆 Please upload one or more thermal profile CSV files to begin analysis")
    
    # Instructions
    with st.expander("📖 How to use this application"):
        st.markdown("""
        1. **Upload Data**: Use the sidebar to upload one or more CSV files from Combustion Inc. temperature probes
        2. **Analyze**: The application will automatically detect and analyze all baking curves in each file
        3. **Compare**: When multiple curves are available (from one or multiple files), use the comparison tab
        4. **Explore**: Navigate through different tabs to view various analyses
        5. **Optimize**: Review recommendations for process improvements
        
        **Key Features:**
        - Multi-file support for comparing different baking sessions
        - Automatic detection of multiple curves within each file
        - Real-time temperature profile visualization
        - S-Curve analysis with landmark identification
        - Bake-out percentage calculation and optimization
        - Critical zone analysis (yeast kill, starch gelatinization, etc.)
        - Quality metrics and uniformity analysis
        - Process optimization recommendations
        - Product-specific quality diagnostics
        """)
else:
    # Analysis tabs - add comparison tab if multiple curves from any source
    if len(st.session_state.all_curves) > 1:
        tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
            "📈 Temperature Profile",
            "📉 S-Curve Analysis",
            "🎯 Zone Analysis", 
            "📊 Quality Metrics",
            "🔥 Heating Analysis",
            "💧 Bake-Out Analysis",
            "💡 Recommendations",
            "🔄 Curve Comparison"
        ])
    else:
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "📈 Temperature Profile",
            "📉 S-Curve Analysis",
            "🎯 Zone Analysis", 
            "📊 Quality Metrics",
            "🔥 Heating Analysis",
            "💧 Bake-Out Analysis",
            "💡 Recommendations"
        ])
    
    with tab1:
        st.header("Temperature Profile Analysis")
        
        # Display options for this tab
        col1, col2 = st.columns([1, 3])
        with col1:
            show_all_sensors = st.checkbox("Show all sensors", value=False, key="temp_profile_show_all")
        
        if not show_all_sensors:
            with col2:
                # Get sensor role assignments for labeling
                assignments = st.session_state.loader.get_sensor_assignments_with_overrides(st.session_state.current_curve_index)
                
                # Create labels showing sensor roles
                sensor_labels = {}
                core_sensor = assignments.get('core_sensor')
                surface_sensor = assignments.get('surface_sensor')
                internal_sensors = assignments.get('internal_sensors', [])
                ambient_sensors = assignments.get('ambient_sensors', [])
                
                for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']:
                    if sensor == core_sensor:
                        sensor_labels[sensor] = f"{sensor} (Core)"
                    elif sensor == surface_sensor:
                        sensor_labels[sensor] = f"{sensor} (Surface)"
                    elif sensor in internal_sensors:
                        sensor_labels[sensor] = f"{sensor} (Internal)"
                    elif sensor in ambient_sensors:
                        sensor_labels[sensor] = f"{sensor} (Ambient)"
                    else:
                        sensor_labels[sensor] = sensor
                
                default_sensors = get_default_sensors(st.session_state.loader)
                selected_sensors = st.multiselect(
                    "Select sensors to display on graph",
                    options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
                    default=default_sensors,
                    format_func=lambda x: sensor_labels.get(x, x),
                    key="temp_profile_sensor_select"
                )
        else:
            selected_sensors = None
        
        # Build sensor roles dictionary for visualization
        sensor_roles = {}
        assignments = st.session_state.loader.get_sensor_assignments_with_overrides()
        core_sensor = assignments.get('core_sensor')
        surface_sensor = assignments.get('surface_sensor')
        internal_sensors = assignments.get('internal_sensors', [])
        ambient_sensors = assignments.get('ambient_sensors', [])
        
        for sensor in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']:
            if sensor == core_sensor:
                sensor_roles[sensor] = 'core'
            elif sensor == surface_sensor:
                sensor_roles[sensor] = 'surface'
            elif sensor in internal_sensors:
                sensor_roles[sensor] = 'internal'
            elif sensor in ambient_sensors:
                sensor_roles[sensor] = 'ambient'
        
        # Create main temperature plot
        plotter = ThermalPlotter()
        fig_temp = plotter.plot_temperature_profile(
            st.session_state.data,
            show_zones=show_zones,
            sensors=selected_sensors,
            sensor_roles=sensor_roles
        )
        st.plotly_chart(fig_temp, use_container_width=True)
        
        # Temperature gradient heatmap
        st.subheader("Temperature Distribution Heatmap")
        fig_heatmap = plotter.plot_temperature_gradient_heatmap(st.session_state.data)
        st.plotly_chart(fig_heatmap, use_container_width=True)
        
    with tab2:
        st.header("S-Curve Analysis")
        
        # Calculate S-curve analysis
        s_curve_report = st.session_state.s_curve_analyzer.generate_optimization_report()
        landmarks = s_curve_report['landmarks']
        zones = s_curve_report['zone_analysis']
        
        # Get internal sensors for temperature spread visualization
        internal_sensors = st.session_state.loader.get_internal_sensors(
            st.session_state.current_curve_index, 
            st.session_state.data
        )
        
        # Plot S-curve
        fig_s_curve = plotter.plot_s_curve(
            st.session_state.data,
            landmarks,
            zones,
            show_targets=True,
            internal_sensors=internal_sensors
        )
        st.plotly_chart(fig_s_curve, use_container_width=True)
        
        # Landmark summary
        st.subheader("S-Curve Landmarks")
        
        landmark_cols = st.columns(3)
        for i, (name, landmark) in enumerate(landmarks.items()):
            col = landmark_cols[i % 3]
            with col:
                status_emoji = "✅" if landmark.is_within_target else "⚠️"
                st.markdown(f"""
                <div class="metric-card">
                    <h4>{status_emoji} {landmark.name}</h4>
                    <p><b>Temperature:</b> {landmark.temperature}°C</p>
                    <p><b>Time:</b> {landmark.time_minutes:.1f} min ({landmark.time_percentage:.1f}%)</p>
                    <p><b>Target:</b> {landmark.target_percentage_range[0]}-{landmark.target_percentage_range[1]}%</p>
                </div>
                """, unsafe_allow_html=True)
        
        # Zone summary
        st.subheader("S-Curve Zones")
        zone_data = []
        for zone_name, zone_info in zones.items():
            zone_data.append({
                'Zone': zone_name.replace('_', ' ').title(),
                'Duration (min)': f"{zone_info['duration_minutes']:.1f}",
                'Percentage': f"{zone_info['percentage_of_bake']:.1f}%",
                'Max Temp': f"{zone_info.get('max_temp_reached', 0):.1f}°C"
            })
        st.dataframe(pd.DataFrame(zone_data), use_container_width=True)
        
        # Overall score
        score = s_curve_report['overall_score']
        st.metric("S-Curve Quality Score", f"{score:.1f}/100")
        
    with tab3:
        st.header("Temperature Zone Analysis")
        
        # Zone analysis
        zone_analyzer = ZoneAnalyzer(
            st.session_state.data,
            st.session_state.metadata['sample_period_s'],
            st.session_state.loader
        )
        zone_analysis = st.session_state.analyzer.analyze_temperature_zones()
        
        # Create beautiful zone dashboard
        create_zone_summary_dashboard(zone_analysis)
        
        # Zone duration chart
        st.markdown("### Zone Duration Timeline")
        fig_zones = plotter.plot_zone_duration_chart(zone_analysis)
        st.plotly_chart(fig_zones, use_container_width=True)
        
        # Zone transitions
        st.markdown("### Zone Transitions")
        transitions = zone_analyzer.calculate_zone_transitions()
        
        if not transitions.empty:
            # Add explanation for transitions
            with st.expander("ℹ️ Understanding Zone Transitions", expanded=False):
                st.markdown("""
                Zone transitions show how quickly the product moves between critical temperature ranges:
                
                • **Duration**: Time spent transitioning between zones
                • **Rate**: How fast temperature changes (°C/min)
                • **Type**: Whether measuring core (internal) or surface temperature
                
                Smooth, controlled transitions generally produce better quality.
                """)
            
            # Display transitions with better formatting
            for _, trans in transitions.iterrows():
                temp_type_icon = "🎯" if trans['temperature_type'] == 'core' else "🌡️"
                rate_color = "#52c41a" if 0.5 <= trans['rate_c_per_min'] <= 2.0 else "#faad14"
                
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.markdown(f"{temp_type_icon} **{trans['from_zone']} → {trans['to_zone']}**")
                with col2:
                    st.markdown(f"Duration: {trans['duration_minutes']:.1f} min")
                with col3:
                    st.markdown(f"<span style='color: {rate_color}'>Rate: {trans['rate_c_per_min']:.1f}°C/min</span>", unsafe_allow_html=True)
        else:
            st.info("No zone transitions detected - this may indicate rapid heating or missing temperature zones.")
        
    with tab4:
        st.header("Quality Metrics Analysis")
        
        # Calculate quality metrics
        quality_metrics = st.session_state.analyzer.calculate_quality_metrics()
        
        # Convert time to target to percentage if available
        if quality_metrics.get('time_to_target_minutes') is not None:
            total_time = st.session_state.data['TimeMinutes'].max()
            time_to_target_pct = quality_metrics['time_to_target_minutes'] / total_time
        else:
            time_to_target_pct = None
        
        # Create beautiful metric dashboard
        metrics_for_dashboard = {
            'core_uniformity_cv': quality_metrics.get('core_uniformity_cv'),
            'heating_rate_consistency': quality_metrics.get('heating_rate_consistency'),
            'max_core_temp': quality_metrics.get('max_core_temp'),
            'quality_score': quality_metrics.get('quality_score')
        }
        
        create_metric_dashboard(metrics_for_dashboard)
        
        # Additional metrics in a cleaner format
        st.markdown("### Additional Measurements")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Time to target with proper percentage
            if time_to_target_pct is not None:
                create_metric_card(
                    'time_to_target_minutes',
                    time_to_target_pct,
                    custom_label=f"Time to 93°C ({quality_metrics['time_to_target_minutes']:.1f} min)"
                )
            else:
                create_simple_metric("Time to 93°C", "Not reached", "#ff4d4f", "⏱️")
            
            # Final core temperature
            final_temp_color = "#52c41a" if 93 <= quality_metrics['final_core_temp'] <= 98 else "#faad14"
            create_simple_metric(
                "Final Core Temperature",
                f"{quality_metrics['final_core_temp']:.1f}°C",
                final_temp_color,
                "🎯"
            )
        
        with col2:
            # Uniformity rating
            rating_colors = {
                "Excellent": "#52c41a",
                "Good": "#73d13d",
                "Acceptable": "#faad14",
                "Poor": "#ff4d4f"
            }
            rating_color = rating_colors.get(quality_metrics['core_uniformity_rating'], "#d9d9d9")
            create_simple_metric(
                "Uniformity Rating",
                quality_metrics['core_uniformity_rating'],
                rating_color,
                "📊"
            )
        
        # Visual charts section
        st.markdown("### Visual Analysis")
        
        # Quality gauge charts
        fig_quality = plotter.plot_quality_metrics_gauge(quality_metrics)
        st.plotly_chart(fig_quality, use_container_width=True)
        
        # Uniformity analysis
        st.subheader("Temperature Uniformity Over Time")
        fig_uniformity = plotter.plot_temperature_uniformity(st.session_state.data)
        st.plotly_chart(fig_uniformity, use_container_width=True)
            
    with tab5:
        st.header("Heating Rate Analysis")
        
        # Add explanation
        with st.expander("📊 Understanding Heating Rates", expanded=False):
            st.markdown("""
            Heating rates show how quickly temperatures change throughout baking:
            
            **What to look for:**
            • **Consistent rates**: Indicate stable oven conditions
            • **Rapid changes**: May signal oven cycling or zone transitions
            • **Negative rates**: Normal during cooling or when moving between zones
            
            **Typical values:**
            • Initial heating: 2-6°C/min (aggressive)
            • Mid-bake: 0.5-2°C/min (controlled)
            • Final stage: 0-0.5°C/min (gentle)
            
            Erratic heating rates often indicate equipment issues or poor heat distribution.
            """)
        
        # Calculate heating rates
        rates = st.session_state.analyzer.calculate_heating_rates(smooth=smooth_data)
        
        # Heating rate plots
        fig_rates = plotter.plot_heating_rates(rates)
        st.plotly_chart(fig_rates, use_container_width=True)
        
        # Temperature gradients
        st.subheader("Temperature Gradients")
        gradients = st.session_state.analyzer.calculate_temperature_gradients()
        
        # Create gradient plot
        fig_gradient = go.Figure()
        fig_gradient.add_trace(go.Scatter(
            x=gradients['TimeMinutes'],
            y=gradients['surface_core_gradient'],
            name='Surface-Core Gradient',
            line=dict(color='red', width=2)
        ))
        fig_gradient.add_trace(go.Scatter(
            x=gradients['TimeMinutes'],
            y=gradients['core_uniformity'],
            name='Core Uniformity (Std Dev)',
            yaxis='y2',
            line=dict(color='blue', width=2)
        ))
        fig_gradient.update_layout(
            title="Temperature Gradients Over Time",
            xaxis_title="Time (minutes)",
            yaxis_title="Surface-Core Gradient (°C)",
            yaxis2=dict(
                title="Core Uniformity (°C)",
                overlaying='y',
                side='right'
            ),
            hovermode='x unified'
        )
        st.plotly_chart(fig_gradient, use_container_width=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                "Avg Surface-Core Gradient",
                f"{gradients['surface_core_gradient'].mean():.1f}°C"
            )
        with col2:
            st.metric(
                "Max Surface-Core Gradient",
                f"{gradients['surface_core_gradient'].max():.1f}°C"
            )
        with col3:
            st.metric(
                "Avg Core Uniformity",
                f"{gradients['core_uniformity'].mean():.2f}°C"
            )
            
    with tab6:
        st.header("Bake-Out Analysis")
        
        # Perform bake-out analysis
        bakeout = st.session_state.s_curve_analyzer.analyze_bake_out(product_type)
        
        # Bake-out visualization
        fig_bakeout = plotter.plot_bakeout_analysis(bakeout, st.session_state.data)
        st.plotly_chart(fig_bakeout, use_container_width=True)
        
        # Bake-out recommendations
        if bakeout.recommendations:
            st.subheader("Bake-Out Recommendations")
            for rec in bakeout.recommendations:
                if "increase" in rec.lower():
                    st.warning(f"⚠️ {rec}")
                elif "reduce" in rec.lower():
                    st.warning(f"⚠️ {rec}")
                else:
                    st.success(f"✅ {rec}")
        
        # Product-specific targets
        target_range = BAKEOUT_TARGETS[product_type]
        st.info(f"Target bake-out percentage for {product_type.replace('_', ' ').title()}: {target_range[0]}-{target_range[1]}%")
        
    with tab7:
        st.header("Process Optimization Recommendations")
        
        # Get S-curve diagnostics
        s_curve_issues = s_curve_report['quality_issues']
        s_curve_recommendations = s_curve_report['recommendations']
        
        # Quality diagnostics visualization
        fig_diagnostics = plotter.plot_quality_diagnostics(s_curve_issues, s_curve_report['overall_score'])
        st.plotly_chart(fig_diagnostics, use_container_width=True)
        
        # S-curve based recommendations
        if s_curve_recommendations:
            st.subheader("🎯 S-Curve Optimization Recommendations")
            for rec in s_curve_recommendations:
                if rec['priority'] == 'High':
                    st.error(f"""
                    **High Priority**: {rec['action']}
                    
                    Expected Result: {rec['expected_result']}
                    """)
                else:
                    st.warning(f"""
                    **{rec['priority']} Priority**: {rec['action']}
                    
                    Expected Result: {rec['expected_result']}
                    """)
        
        # Zone-based recommendations
        st.subheader("🌡️ Zone-Based Recommendations")
        recommendations = zone_analyzer.recommend_zone_optimizations()
        
        if recommendations:
            # Group by priority
            high_priority = [r for r in recommendations if r['priority'] == 'High']
            medium_priority = [r for r in recommendations if r['priority'] == 'Medium']
            low_priority = [r for r in recommendations if r['priority'] == 'Low']
            
            if high_priority:
                st.markdown("### 🔴 High Priority")
                for rec in high_priority:
                    st.warning(f"""
                    **{rec['zone']}**: {rec['issue']}
                    
                    💡 **Recommendation**: {rec['recommendation']}
                    """)
            
            if medium_priority:
                st.markdown("### 🟡 Medium Priority")
                for rec in medium_priority:
                    st.info(f"""
                    **{rec['zone']}**: {rec['issue']}
                    
                    💡 **Recommendation**: {rec['recommendation']}
                    """)
            
            if low_priority:
                st.markdown("### 🟢 Low Priority")
                for rec in low_priority:
                    st.success(f"""
                    **{rec['zone']}**: {rec['issue']}
                    
                    💡 **Recommendation**: {rec['recommendation']}
                    """)
        else:
            st.success("✅ No zone-based issues found.")
        
        # Display summary
        st.divider()
        st.markdown(f"### 📋 Analysis Summary")
        st.markdown(s_curve_report['summary'])
        
        # Process events
        st.subheader("Key Process Events")
        events = st.session_state.analyzer.identify_process_events()
        
        event_data = []
        for event_name, event_info in events.items():
            if isinstance(event_info, dict) and 'time_minutes' in event_info:
                event_data.append({
                    'Event': event_name.replace('_', ' ').title(),
                    'Time (min)': f"{event_info['time_minutes']:.1f}",
                    'Temperature (°C)': f"{event_info.get('temperature', 'N/A'):.1f}" if event_info.get('temperature') else 'N/A',
                    'Details': f"Rate: {event_info.get('rate', 0):.2f}°C/s" if 'rate' in event_info else ''
                })
        
        if event_data:
            st.table(pd.DataFrame(event_data))
    
    # Comparison tab (only if multiple curves)
    if len(st.session_state.all_curves) > 1:
        with tab8:
            st.header("Curve Comparison")
            
            # Allow selection of curves to compare
            st.subheader("Select curves to compare")
            
            # Group curves by file for better organization
            files_dict = {}
            for i, curve in enumerate(st.session_state.all_curves):
                filename = curve['filename']
                if filename not in files_dict:
                    files_dict[filename] = []
                files_dict[filename].append((i, curve))
            
            # Create checkboxes grouped by file
            curve_checkboxes = {}
            for filename, curves in files_dict.items():
                st.markdown(f"**{filename}**")
                for global_idx, curve_info in curves:
                    curve_data = curve_info['curve_data']
                    file_curve_idx = curve_info['file_curve_index']
                    
                    # Create label
                    if len(curves) > 1:
                        label = f"Curve {file_curve_idx+1} ({curve_data['duration']:.1f} min, Max {curve_data['max_temp']:.0f}°C)"
                    else:
                        label = f"{curve_data['duration']:.1f} min, Max {curve_data['max_temp']:.0f}°C"
                    
                    checked = st.checkbox(
                        label,
                        value=global_idx == st.session_state.global_curve_index,
                        key=f"curve_check_{global_idx}"
                    )
                    curve_checkboxes[global_idx] = checked
                st.write("")  # Add space between files
            
            # Get selected curves
            selected_curves = [idx for idx, checked in curve_checkboxes.items() if checked]
            
            if len(selected_curves) < 2:
                st.info("📊 Please select at least 2 curves to compare")
            else:
                # Prepare curves for comparison
                curves_for_comparison = []
                for idx in selected_curves:
                    curve_info = st.session_state.all_curves[idx]
                    
                    # Get sensor roles for this curve
                    sensor_roles = {}
                    if 'loader' in curve_info:
                        # Temporarily set to this curve to get sensor roles
                        original_idx = curve_info['loader'].current_curve_index
                        curve_info['loader'].set_current_curve(curve_info['file_curve_index'])
                        sensor_assignments = curve_info['loader'].get_sensor_assignments()
                        sensor_roles = transform_sensor_assignments_to_roles(sensor_assignments)
                        curve_info['loader'].set_current_curve(original_idx)
                    
                    curves_for_comparison.append({
                        'curve_data': {'data': curve_info['curve_data']['data']},
                        'sensor_roles': sensor_roles,
                        'metadata': curve_info.get('metadata', {}),
                        'filename': curve_info['filename'],
                        'file_curve_index': curve_info['file_curve_index']
                    })
                
                # Create comparison object
                comparison = CurveComparison(curves_for_comparison)
                
                # Create tabs for different comparison views
                comp_tab1, comp_tab2, comp_tab3, comp_tab4, comp_tab5 = st.tabs([
                    "Temperature Profiles", "Zone Analysis", "S-Curve Analysis", 
                    "Heating Rates", "Quality Metrics"
                ])
                
                # Temperature Profile Comparison
                with comp_tab1:
                    st.subheader("Role-Based Temperature Comparison")
                    
                    # Get role-based data
                    role_data = comparison.get_role_based_data()
                    
                    # For internal sensors, we need to get the properly filtered list from each curve
                    # This ensures we only show sensors that are actually inside the loaf
                    internal_data_filtered = []
                    for idx in selected_curves:
                        curve_info = st.session_state.all_curves[idx]
                        curve_data = curve_info['curve_data']['data']
                        curve_loader = curve_info['loader']
                        
                        # Get filtered internal sensors using the same logic as S-curve analysis
                        internal_sensors = curve_loader.get_internal_sensors(
                            curve_info['file_curve_index'], 
                            curve_data
                        )
                        
                        if internal_sensors:
                            # Extract temperature data for these sensors
                            internal_temps = []
                            for sensor in internal_sensors:
                                if sensor in curve_data.columns:
                                    internal_temps.append(curve_data[sensor].values)
                            
                            if internal_temps:
                                # Get curve name from existing role_data
                                curve_name = None
                                curve_short_name = None
                                for existing_data in role_data.get('internal', []):
                                    # Match by time array length (simple but effective)
                                    if len(existing_data['time']) == len(curve_data['TimeMinutes']):
                                        curve_name = existing_data['curve_name']
                                        curve_short_name = existing_data['curve_short_name']
                                        break
                                
                                if curve_name:
                                    internal_data_filtered.append({
                                        'time': curve_data['TimeMinutes'].values,
                                        'temperature': np.array(internal_temps).T,  # Time x Sensors
                                        'curve_name': curve_name,
                                        'curve_short_name': curve_short_name,
                                        'sensors': internal_sensors
                                    })
                    
                    # Replace the internal data with filtered version
                    role_data['internal'] = internal_data_filtered
                    
                    # Create columns for different roles
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        # Core temperature comparison
                        st.markdown("### Core Temperature")
                        fig_core = plotter.plot_role_based_comparison(role_data, 'core', show_zones)
                        st.plotly_chart(fig_core, use_container_width=True)
                        
                        # Ambient temperature comparison
                        st.markdown("### Ambient Temperature")
                        fig_ambient = plotter.plot_role_based_comparison(role_data, 'ambient', False)
                        st.plotly_chart(fig_ambient, use_container_width=True)
                    
                    with col2:
                        # Surface temperature comparison
                        st.markdown("### Surface Temperature")
                        fig_surface = plotter.plot_role_based_comparison(role_data, 'surface', show_zones)
                        st.plotly_chart(fig_surface, use_container_width=True)
                        
                        # Internal temperature comparison
                        st.markdown("### Internal Temperature Range")
                        fig_internal = plotter.plot_role_based_comparison(role_data, 'internal', False)
                        st.plotly_chart(fig_internal, use_container_width=True)
                
                # Zone Analysis Comparison
                with comp_tab2:
                    st.subheader("Temperature Zone Duration Comparison")
                    
                    # Get zone comparison data
                    zone_comparison = comparison.compare_zone_durations()
                    
                    # Display zone comparison chart
                    fig_zones = plotter.plot_zone_duration_comparison(zone_comparison)
                    st.plotly_chart(fig_zones, use_container_width=True)
                    
                    # Display zone comparison table
                    st.markdown("### Zone Duration Details")
                    st.dataframe(zone_comparison, use_container_width=True)
                
                # S-Curve Analysis Comparison
                with comp_tab3:
                    st.subheader("S-Curve Comparison with Landmarks")
                    
                    # Prepare S-curve data
                    s_curve_data = []
                    landmark_comparison = comparison.compare_s_curve_landmarks()
                    
                    for idx in selected_curves:
                        curve_info = st.session_state.all_curves[idx]
                        curve_data = curve_info['curve_data']['data']
                        
                        # Get landmarks for this curve
                        s_curve_analyzer = SCurveAnalyzer(curve_data, curve_info.get('metadata', {}))
                        landmarks = s_curve_analyzer.identify_landmarks()
                        
                        # Get internal sensors for this curve
                        # Note: We need to get the curve-specific sensor assignments
                        curve_loader = curve_info['loader']
                        internal_sensors = curve_loader.get_internal_sensors(
                            curve_info['file_curve_index'], 
                            curve_data
                        )
                        
                        # Create descriptive name
                        if len(st.session_state.files[curve_info['filename']]['curves']) > 1:
                            curve_name = f"{curve_info['filename']} - Curve {curve_info['file_curve_index']+1}"
                        else:
                            curve_name = curve_info['filename']
                        
                        s_curve_data.append({
                            'data': curve_data,
                            'landmarks': landmarks,
                            'name': curve_name,
                            'internal_sensors': internal_sensors
                        })
                    
                    # Plot S-curve comparison
                    fig_s_curve = plotter.plot_s_curve_comparison(s_curve_data)
                    st.plotly_chart(fig_s_curve, use_container_width=True)
                    
                    # Display landmark comparison table
                    st.markdown("### Landmark Comparison")
                    st.dataframe(landmark_comparison, use_container_width=True)
                
                # Heating Rate Comparison
                with comp_tab4:
                    st.subheader("Heating Rate Analysis")
                    
                    # Get heating rate data
                    heating_data = comparison.get_heating_rate_comparison()
                    
                    # Plot heating rate comparison
                    fig_heating = plotter.plot_heating_rate_comparison(heating_data)
                    st.plotly_chart(fig_heating, use_container_width=True)
                    
                    # Display consistency scores
                    if heating_data['consistency_scores']:
                        st.markdown("### Heating Consistency Scores")
                        consistency_df = pd.DataFrame(heating_data['consistency_scores'])
                        
                        # Create metric columns
                        cols = st.columns(len(consistency_df))
                        for idx, (col, row) in enumerate(zip(cols, consistency_df.itertuples())):
                            with col:
                                st.metric(
                                    label=row.curve_name,
                                    value=f"{row.score:.1f}%",
                                    delta=None
                                )
                
                # Quality Metrics Comparison
                with comp_tab5:
                    st.subheader("Quality Metrics Comparison")
                    
                    # Get quality metrics
                    quality_metrics = comparison.compare_quality_metrics()
                    
                    # Display metrics table
                    st.dataframe(quality_metrics, use_container_width=True)
                    
                    # Create visual metrics dashboard
                    st.markdown("### Quality Score Overview")
                    
                    # Extract quality scores for visualization
                    quality_scores = []
                    for _, row in quality_metrics.iterrows():
                        try:
                            score = float(row['Quality Score'])
                            quality_scores.append({
                                'Curve': row['Curve'],
                                'Score': score
                            })
                        except:
                            pass
                    
                    if quality_scores:
                        # Create bar chart of quality scores
                        scores_df = pd.DataFrame(quality_scores)
                        fig_quality = go.Figure(data=[
                            go.Bar(
                                x=scores_df['Curve'],
                                y=scores_df['Score'],
                                marker_color=['green' if s >= 80 else 'orange' if s >= 60 else 'red' 
                                            for s in scores_df['Score']],
                                text=[f"{s:.1f}" for s in scores_df['Score']],
                                textposition='auto'
                            )
                        ])
                        
                        fig_quality.update_layout(
                            title="Quality Score Comparison",
                            xaxis_title="Curve",
                            yaxis_title="Quality Score",
                            yaxis=dict(range=[0, 100]),
                            showlegend=False
                        )
                        
                        st.plotly_chart(fig_quality, use_container_width=True)

# Footer
st.divider()
st.markdown("""
<div style="text-align: center; color: #666;">
    Thermal Profile Analyzer v1.0 | Optimize your baking process with data-driven insights
</div>
""", unsafe_allow_html=True)