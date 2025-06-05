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
from config.constants import TEMPERATURE_ZONES, QUALITY_THRESHOLDS, SENSOR_NAMES, BAKEOUT_TARGETS

# Page configuration
st.set_page_config(
    page_title="Thermal Profile Analyzer",
    page_icon="🍞",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

# Title and description
st.title("🍞 Thermal Profile Analyzer")
st.markdown("### Optimize bread baking processes through advanced thermal analysis")

# Sidebar for file upload and settings
with st.sidebar:
    st.header("📊 Data Input")
    
    uploaded_file = st.file_uploader(
        "Upload CSV file",
        type=['csv'],
        help="Upload a thermal profile CSV from Combustion Inc. probe"
    )
    
    if uploaded_file is not None:
        # Load data
        with st.spinner("Loading and validating data..."):
            try:
                # Load data directly from uploaded file buffer
                loader = ThermalProfileLoader()
                data, metadata = loader.load_csv(file_buffer=uploaded_file)
                
                # Validate data
                is_valid, issues = validate_thermal_data(data)
                
                if is_valid:
                    st.session_state.loader = loader
                    st.session_state.metadata = metadata
                    
                    # Check if multiple curves were detected
                    num_curves = loader.get_curve_count()
                    if num_curves > 1:
                        st.success(f"✅ Data loaded successfully! Found {num_curves} baking curves.")
                    else:
                        st.success("✅ Data loaded successfully!")
                    
                    # Set initial data to first curve
                    st.session_state.data = data
                    st.session_state.analyzer = ThermalAnalyzer(data, metadata)
                    st.session_state.s_curve_analyzer = SCurveAnalyzer(data, metadata)
                    st.session_state.current_curve_index = 0
                    
                    # Display metadata
                    with st.expander("📋 File Metadata"):
                        for key, value in metadata.items():
                            if key not in ['sample_period_ms', 'sample_period_s', 'created_datetime']:
                                st.text(f"{key}: {value}")
                else:
                    st.error("❌ Data validation failed:")
                    for issue in issues:
                        st.warning(issue)
                        
            except Exception as e:
                st.error(f"Error loading file: {str(e)}")
    
    # Curve selection for multiple curves
    if st.session_state.loader is not None and st.session_state.loader.get_curve_count() > 1:
        st.divider()
        st.header("📊 Curve Selection")
        
        # Get all curves info
        all_curves = st.session_state.loader.get_all_curves()
        
        # Create curve options
        curve_options = []
        for i, curve in enumerate(all_curves):
            curve_label = f"Curve {i+1}: {curve['duration']:.1f} min, Max {curve['max_temp']:.0f}°C"
            curve_options.append(curve_label)
        
        # Curve selector
        selected_curve_label = st.selectbox(
            "Select baking curve to analyze",
            options=curve_options,
            index=st.session_state.current_curve_index
        )
        
        # Update selection if changed
        new_index = curve_options.index(selected_curve_label)
        if new_index != st.session_state.current_curve_index:
            st.session_state.current_curve_index = new_index
            st.session_state.data = st.session_state.loader.set_current_curve(new_index)
            st.session_state.analyzer = ThermalAnalyzer(st.session_state.data, st.session_state.metadata)
            st.session_state.s_curve_analyzer = SCurveAnalyzer(st.session_state.data, st.session_state.metadata)
        
        # Display current curve info
        current_curve_info = st.session_state.loader.get_current_curve_info()
        if current_curve_info:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Duration", f"{current_curve_info['duration']:.1f} min")
            with col2:
                st.metric("Max Temperature", f"{current_curve_info['max_temp']:.1f}°C")
            with col3:
                st.metric("Data Points", current_curve_info['samples'])
    
    # Analysis settings
    if st.session_state.data is not None:
        st.divider()
        st.header("⚙️ Analysis Settings")
        
        show_all_sensors = st.checkbox("Show all sensors", value=False)
        if not show_all_sensors:
            selected_sensors = st.multiselect(
                "Select sensors to display",
                options=['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8'],
                default=['T1', 'T4', 'T6', 'T8'],
                format_func=lambda x: f"{x} - {SENSOR_NAMES[x]}"
            )
        else:
            selected_sensors = None
        
        show_zones = st.checkbox("Show temperature zones", value=True)
        smooth_data = st.checkbox("Apply smoothing", value=True)
        
        # Product type selection for bake-out analysis
        st.subheader("🍞 Product Type")
        product_type = st.selectbox(
            "Select product type",
            options=list(BAKEOUT_TARGETS.keys()),
            format_func=lambda x: x.replace('_', ' ').title(),
            help="Product type affects bake-out target percentages"
        )

# Main content area
if st.session_state.data is None:
    # Welcome screen
    st.info("👆 Please upload a thermal profile CSV file to begin analysis")
    
    # Instructions
    with st.expander("📖 How to use this application"):
        st.markdown("""
        1. **Upload Data**: Use the sidebar to upload a CSV file from a Combustion Inc. temperature probe
        2. **Analyze**: The application will automatically analyze the thermal profile
        3. **Explore**: Navigate through different tabs to view various analyses
        4. **Optimize**: Review recommendations for process improvements
        
        **Key Features:**
        - Real-time temperature profile visualization
        - S-Curve analysis with landmark identification
        - Bake-out percentage calculation and optimization
        - Critical zone analysis (yeast kill, starch gelatinization, etc.)
        - Quality metrics and uniformity analysis
        - Process optimization recommendations
        - Product-specific quality diagnostics
        """)
else:
    # Analysis tabs - add comparison tab if multiple curves
    if st.session_state.loader and st.session_state.loader.get_curve_count() > 1:
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
        
        # Zone duration chart
        fig_zones = plotter.plot_zone_duration_chart(zone_analysis)
        st.plotly_chart(fig_zones, use_container_width=True)
        
        # Zone details
        st.subheader("Zone Details")
        
        cols = st.columns(3)
        for i, (zone_name, analysis) in enumerate(zone_analysis.items()):
            col = cols[i % 3]
            with col:
                zone_config = TEMPERATURE_ZONES[zone_name]
                st.markdown(f"""
                <div class="metric-card">
                    <h4 style="color: {zone_config['color']}">{zone_config['name']}</h4>
                    <p><b>Temperature Range:</b> {analysis['temperature_range']}</p>
                    <p><b>Time in Zone:</b> {analysis['total_time_minutes']:.1f} min</p>
                    <p><b>% of Bake:</b> {analysis['percentage_of_bake']:.1f}%</p>
                </div>
                """, unsafe_allow_html=True)
        
        # Zone transitions
        st.subheader("Zone Transitions")
        transitions = zone_analyzer.calculate_zone_transitions()
        if not transitions.empty:
            st.dataframe(transitions, use_container_width=True)
        
    with tab4:
        st.header("Quality Metrics Analysis")
        
        # Calculate quality metrics
        quality_metrics = st.session_state.analyzer.calculate_quality_metrics()
        
        # Quality gauge charts
        fig_quality = plotter.plot_quality_metrics_gauge(quality_metrics)
        st.plotly_chart(fig_quality, use_container_width=True)
        
        # Uniformity analysis
        st.subheader("Temperature Uniformity")
        fig_uniformity = plotter.plot_temperature_uniformity(st.session_state.data)
        st.plotly_chart(fig_uniformity, use_container_width=True)
        
        # Detailed metrics
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Core Metrics")
            st.metric("Max Core Temperature", f"{quality_metrics['max_core_temp']:.1f}°C")
            st.metric("Final Core Temperature", f"{quality_metrics['final_core_temp']:.1f}°C")
            if quality_metrics['time_to_target_minutes']:
                st.metric("Time to 93°C", f"{quality_metrics['time_to_target_minutes']:.1f} min")
            else:
                st.metric("Time to 93°C", "Not reached")
        
        with col2:
            st.markdown("### Uniformity Metrics")
            st.metric("Uniformity Rating", quality_metrics['core_uniformity_rating'])
            st.metric("Uniformity CV", f"{quality_metrics['core_uniformity_cv']:.3f}")
            st.metric("Heating Consistency", f"{quality_metrics['heating_rate_consistency']:.2%}")
            
    with tab5:
        st.header("Heating Rate Analysis")
        
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
    if st.session_state.loader and st.session_state.loader.get_curve_count() > 1:
        with tab8:
            st.header("Curve Comparison")
            
            # Get all curves
            all_curves = st.session_state.loader.get_all_curves()
            
            # Allow selection of curves to compare
            st.subheader("Select curves to compare")
            
            curve_checkboxes = []
            for i, curve in enumerate(all_curves):
                checked = st.checkbox(
                    f"Curve {i+1} ({curve['duration']:.1f} min, Max {curve['max_temp']:.0f}°C)",
                    value=i == st.session_state.current_curve_index,
                    key=f"curve_check_{i}"
                )
                curve_checkboxes.append(checked)
            
            # Get selected curves
            selected_curves = [i for i, checked in enumerate(curve_checkboxes) if checked]
            
            if len(selected_curves) < 2:
                st.info("📊 Please select at least 2 curves to compare")
            else:
                # Create comparison plot
                fig_compare = go.Figure()
                
                colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown']
                
                for idx, curve_idx in enumerate(selected_curves):
                    curve_data = all_curves[curve_idx]['data']
                    color = colors[idx % len(colors)]
                    
                    # Plot core temperature
                    fig_compare.add_trace(go.Scatter(
                        x=curve_data['TimeMinutes'],
                        y=curve_data['CoreTemperature'],
                        mode='lines',
                        name=f'Curve {curve_idx+1} - Core',
                        line=dict(color=color, width=2),
                        legendgroup=f'curve{curve_idx}'
                    ))
                    
                    # Plot surface temperature
                    fig_compare.add_trace(go.Scatter(
                        x=curve_data['TimeMinutes'],
                        y=curve_data['SurfaceTemperature'],
                        mode='lines',
                        name=f'Curve {curve_idx+1} - Surface',
                        line=dict(color=color, width=2, dash='dash'),
                        legendgroup=f'curve{curve_idx}'
                    ))
                
                # Add temperature zones
                if show_zones:
                    for zone_name, zone_temp in TEMPERATURE_ZONES.items():
                        fig_compare.add_hline(
                            y=zone_temp,
                            line_dash="dot",
                            line_color="gray",
                            annotation_text=zone_name,
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
                for curve_idx in selected_curves:
                    curve_info = all_curves[curve_idx]
                    curve_data = curve_info['data']
                    
                    # Calculate metrics
                    max_core = curve_data['CoreTemperature'].max()
                    time_to_56 = curve_data[curve_data['CoreTemperature'] >= 56]['TimeMinutes'].min() if any(curve_data['CoreTemperature'] >= 56) else None
                    time_to_93 = curve_data[curve_data['CoreTemperature'] >= 93]['TimeMinutes'].min() if any(curve_data['CoreTemperature'] >= 93) else None
                    
                    comparison_data.append({
                        'Curve': f"Curve {curve_idx+1}",
                        'Duration (min)': f"{curve_info['duration']:.1f}",
                        'Max Core Temp (°C)': f"{max_core:.1f}",
                        'Time to 56°C (min)': f"{time_to_56:.1f}" if time_to_56 else "N/A",
                        'Time to 93°C (min)': f"{time_to_93:.1f}" if time_to_93 else "N/A",
                        'Samples': curve_info['samples']
                    })
                
                st.table(pd.DataFrame(comparison_data))
                
                # S-curve comparison
                st.subheader("S-Curve Comparison")
                
                fig_s_compare = go.Figure()
                
                for idx, curve_idx in enumerate(selected_curves):
                    curve_data = all_curves[curve_idx]['data']
                    color = colors[idx % len(colors)]
                    
                    # Create S-curve analyzer for this curve
                    temp_analyzer = SCurveAnalyzer(curve_data, st.session_state.metadata)
                    landmarks = temp_analyzer.identify_s_curve_landmarks()
                    
                    # Plot S-curve
                    fig_s_compare.add_trace(go.Scatter(
                        x=curve_data['TimeMinutes'],
                        y=curve_data['CoreTemperature'],
                        mode='lines',
                        name=f'Curve {curve_idx+1}',
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