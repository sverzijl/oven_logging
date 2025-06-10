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
    
    assignments = loader.get_sensor_assignments()
    defaults = []
    
    # Add primary core sensor
    if 'core' in assignments and assignments['core'] and assignments['core'].startswith('T'):
        defaults.append(assignments['core'])
    else:
        defaults.append('T1')  # Fallback
    
    # Add primary surface sensor
    if 'surface' in assignments and assignments['surface'] and assignments['surface'].startswith('T'):
        defaults.append(assignments['surface'])
    else:
        defaults.append('T8')  # Fallback
    
    # Add primary ambient sensor if different from surface
    if 'ambient' in assignments and assignments['ambient'] and assignments['ambient'].startswith('T'):
        if assignments['ambient'] not in defaults:
            defaults.append(assignments['ambient'])
    
    # Add a middle sensor if we don't have enough
    if len(defaults) < 3:
        for sensor in ['T4', 'T5', 'T6']:
            if sensor not in defaults:
                defaults.append(sensor)
                if len(defaults) >= 3:
                    break
    
    # Ensure we have at least 4 sensors for good visualization
    all_sensors = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
    for sensor in all_sensors:
        if sensor not in defaults and len(defaults) < 4:
            defaults.append(sensor)
    
    return defaults[:4]  # Return max 4 sensors

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
                st.session_state.analyzer = ThermalAnalyzer(st.session_state.data, st.session_state.metadata)
                st.session_state.s_curve_analyzer = SCurveAnalyzer(st.session_state.data, st.session_state.metadata)
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
            st.session_state.analyzer = ThermalAnalyzer(st.session_state.data, st.session_state.metadata)
            st.session_state.s_curve_analyzer = SCurveAnalyzer(st.session_state.data, st.session_state.metadata)
        
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
    
    # Analysis settings
    if st.session_state.data is not None:
        st.divider()
        st.header("⚙️ Analysis Settings")
        
        show_all_sensors = st.checkbox("Show all sensors", value=False)
        if not show_all_sensors:
            # Get dynamic sensor names and defaults based on actual assignments
            dynamic_sensor_names = get_dynamic_sensor_names(st.session_state.loader)
            default_sensors = get_default_sensors(st.session_state.loader)
            
            selected_sensors = st.multiselect(
                "Select sensors to display",
                options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
                default=default_sensors,
                format_func=lambda x: f"{x} - {dynamic_sensor_names.get(x, SENSOR_NAMES.get(x, 'Unknown'))}"
            )
        else:
            selected_sensors = None
        
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
        
        # Create main temperature plot
        plotter = ThermalPlotter()
        fig_temp = plotter.plot_temperature_profile(
            st.session_state.data,
            show_zones=show_zones,
            sensors=selected_sensors
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
        
        # Plot S-curve
        fig_s_curve = plotter.plot_s_curve(
            st.session_state.data,
            landmarks,
            zones,
            show_targets=True
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
            st.session_state.metadata['sample_period_s']
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
                # Create comparison plot
                fig_compare = go.Figure()
                
                colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown']
                
                for idx, global_curve_idx in enumerate(selected_curves):
                    curve_info = st.session_state.all_curves[global_curve_idx]
                    curve_data = curve_info['curve_data']['data']
                    filename = curve_info['filename']
                    file_curve_idx = curve_info['file_curve_index']
                    color = colors[idx % len(colors)]
                    
                    # Create descriptive name
                    if len(st.session_state.files[filename]['curves']) > 1:
                        curve_name = f"{filename} - Curve {file_curve_idx+1}"
                    else:
                        curve_name = filename
                    
                    # Plot core temperature
                    fig_compare.add_trace(go.Scatter(
                        x=curve_data['TimeMinutes'],
                        y=curve_data['CoreTemperature'],
                        mode='lines',
                        name=f'{curve_name} - Core',
                        line=dict(color=color, width=2),
                        legendgroup=f'curve{global_curve_idx}'
                    ))
                    
                    # Plot surface temperature
                    fig_compare.add_trace(go.Scatter(
                        x=curve_data['TimeMinutes'],
                        y=curve_data['SurfaceTemperature'],
                        mode='lines',
                        name=f'{curve_name} - Surface',
                        line=dict(color=color, width=2, dash='dash'),
                        legendgroup=f'curve{global_curve_idx}'
                    ))
                
                # Add temperature zones
                if show_zones:
                    for zone_name, zone_config in TEMPERATURE_ZONES.items():
                        fig_compare.add_hline(
                            y=zone_config["min"],
                            line_dash="dot",
                            line_color=zone_config.get("color", "gray"),
                            annotation_text=zone_config["name"],
                            annotation_position="right"
                        )
                
                fig_compare.update_layout(
                    title="Temperature Profile Comparison",
                    xaxis_title="Time (minutes)",
                    yaxis_title="Temperature (°C)",
                    height=600,
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig_compare, use_container_width=True)
                
                # Comparison metrics
                st.subheader("Curve Comparison Metrics")
                
                comparison_data = []
                for global_curve_idx in selected_curves:
                    curve_info = st.session_state.all_curves[global_curve_idx]
                    curve_data = curve_info['curve_data']['data']
                    filename = curve_info['filename']
                    file_curve_idx = curve_info['file_curve_index']
                    
                    # Create descriptive name
                    if len(st.session_state.files[filename]['curves']) > 1:
                        curve_name = f"{filename} - Curve {file_curve_idx+1}"
                    else:
                        curve_name = filename
                    
                    # Calculate metrics
                    max_core = curve_data['CoreTemperature'].max()
                    time_to_56 = curve_data[curve_data['CoreTemperature'] >= 56]['TimeMinutes'].min() if any(curve_data['CoreTemperature'] >= 56) else None
                    time_to_93 = curve_data[curve_data['CoreTemperature'] >= 93]['TimeMinutes'].min() if any(curve_data['CoreTemperature'] >= 93) else None
                    
                    comparison_data.append({
                        'Curve': curve_name,
                        'Duration (min)': f"{curve_info['curve_data']['duration']:.1f}",
                        'Max Core Temp (°C)': f"{max_core:.1f}",
                        'Time to 56°C (min)': f"{time_to_56:.1f}" if time_to_56 else "N/A",
                        'Time to 93°C (min)': f"{time_to_93:.1f}" if time_to_93 else "N/A",
                        'Samples': curve_info['curve_data']['samples']
                    })
                
                st.table(pd.DataFrame(comparison_data))
                
                # S-curve comparison
                st.subheader("S-Curve Comparison")
                
                fig_s_compare = go.Figure()
                
                for idx, global_curve_idx in enumerate(selected_curves):
                    curve_info = st.session_state.all_curves[global_curve_idx]
                    curve_data = curve_info['curve_data']['data']
                    metadata = curve_info['metadata']
                    filename = curve_info['filename']
                    file_curve_idx = curve_info['file_curve_index']
                    color = colors[idx % len(colors)]
                    
                    # Create descriptive name
                    if len(st.session_state.files[filename]['curves']) > 1:
                        curve_name = f"{filename} - Curve {file_curve_idx+1}"
                    else:
                        curve_name = filename
                    
                    # Create S-curve analyzer for this curve
                    temp_analyzer = SCurveAnalyzer(curve_data, metadata)
                    landmarks = temp_analyzer.identify_landmarks()
                    
                    # Plot S-curve
                    fig_s_compare.add_trace(go.Scatter(
                        x=curve_data['TimeMinutes'],
                        y=curve_data['CoreTemperature'],
                        mode='lines',
                        name=curve_name,
                        line=dict(color=color, width=2)
                    ))
                    
                    # Add landmarks for this curve
                    for landmark_name, landmark in landmarks.items():
                        if landmark.time_minutes is not None:
                            fig_s_compare.add_trace(go.Scatter(
                                x=[landmark.time_minutes],
                                y=[landmark.temperature],
                                mode='markers+text',
                                marker=dict(size=10, color=color),
                                text=[f"{landmark.time_percentage:.0f}%"],
                                textposition="top center",
                                showlegend=False,
                                hovertext=f"{landmark_name}: {landmark.temperature}°C at {landmark.time_minutes:.1f} min"
                            ))
                
                # Add reference lines
                for temp in [56, 82, 93]:
                    fig_s_compare.add_hline(
                        y=temp,
                        line_dash="dot",
                        line_color="gray",
                        annotation_text=f"{temp}°C",
                        annotation_position="right"
                    )
                
                fig_s_compare.update_layout(
                    title="S-Curve Comparison with Landmarks",
                    xaxis_title="Time (minutes)",
                    yaxis_title="Core Temperature (°C)",
                    height=600,
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig_s_compare, use_container_width=True)

# Footer
st.divider()
st.markdown("""
<div style="text-align: center; color: #666;">
    Thermal Profile Analyzer v1.0 | Optimize your baking process with data-driven insights
</div>
""", unsafe_allow_html=True)