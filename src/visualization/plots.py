"""Visualization components for thermal profile analysis."""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from config.constants import TEMPERATURE_ZONES, SENSOR_NAMES, S_CURVE_ZONES, S_CURVE_BENCHMARKS
from src.analysis.s_curve_analysis import SCurveLandmark, BakeOutAnalysis


class ThermalPlotter:
    """Create interactive visualizations for thermal profiles."""
    
    def __init__(self):
        self.default_layout = {
            'template': 'plotly_white',
            'hovermode': 'x unified',
            'height': 600
        }
    
    def plot_temperature_profile(self, data: pd.DataFrame, 
                               show_zones: bool = True,
                               sensors: Optional[List[str]] = None) -> go.Figure:
        """
        Create main temperature profile plot.
        
        Args:
            data: Temperature data
            show_zones: Show critical temperature zones
            sensors: List of sensors to plot (default: all)
        """
        if sensors is None:
            sensors = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
        
        fig = go.Figure()
        
        # Add temperature traces
        for sensor in sensors:
            if sensor in data.columns:
                fig.add_trace(go.Scatter(
                    x=data['TimeMinutes'],
                    y=data[sensor],
                    name=SENSOR_NAMES.get(sensor, sensor),
                    mode='lines',
                    line=dict(width=2)
                ))
        
        # Add temperature zones as horizontal bands
        if show_zones:
            for zone_name, zone_config in TEMPERATURE_ZONES.items():
                fig.add_hrect(
                    y0=zone_config['min'],
                    y1=zone_config['max'],
                    fillcolor=zone_config['color'],
                    opacity=0.2,
                    layer="below",
                    line_width=0,
                    annotation_text=zone_config['name'],
                    annotation_position="right"
                )
        
        # Update layout
        fig.update_layout(
            title="Temperature Profile Analysis",
            xaxis_title="Time (minutes)",
            yaxis_title="Temperature (°C)",
            **self.default_layout
        )
        
        return fig
    
    def plot_heating_rates(self, rates: pd.DataFrame) -> go.Figure:
        """Plot heating rates over time."""
        fig = make_subplots(
            rows=2, cols=1,
            subplot_titles=("Core Heating Rate", "Surface Heating Rate"),
            shared_xaxes=True,
            vertical_spacing=0.1
        )
        
        # Core heating rate
        fig.add_trace(
            go.Scatter(
                x=rates['TimeMinutes'],
                y=rates['core_rate'],
                name='Core Average',
                line=dict(color='red', width=2)
            ),
            row=1, col=1
        )
        
        # Add individual core sensors
        for sensor in ['T1_rate', 'T2_rate', 'T3_rate', 'T4_rate']:
            if sensor in rates.columns:
                fig.add_trace(
                    go.Scatter(
                        x=rates['TimeMinutes'],
                        y=rates[sensor],
                        name=sensor.replace('_rate', ''),
                        line=dict(width=1, dash='dot'),
                        opacity=0.5
                    ),
                    row=1, col=1
                )
        
        # Surface heating rate
        fig.add_trace(
            go.Scatter(
                x=rates['TimeMinutes'],
                y=rates['surface_rate'],
                name='Surface Average',
                line=dict(color='blue', width=2)
            ),
            row=2, col=1
        )
        
        # Update layout
        fig.update_xaxes(title_text="Time (minutes)", row=2, col=1)
        fig.update_yaxes(title_text="Heating Rate (°C/s)", row=1, col=1)
        fig.update_yaxes(title_text="Heating Rate (°C/s)", row=2, col=1)
        
        # Create layout without conflicting height
        layout_params = {k: v for k, v in self.default_layout.items() if k != 'height'}
        fig.update_layout(
            title="Heating Rate Analysis",
            height=800,
            **layout_params
        )
        
        return fig
    
    def plot_temperature_gradient_heatmap(self, data: pd.DataFrame) -> go.Figure:
        """Create heatmap showing temperature gradients across sensors."""
        # Prepare data for heatmap
        sensors = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
        heatmap_data = []
        
        for sensor in sensors:
            if sensor in data.columns:
                heatmap_data.append(data[sensor].values)
        
        heatmap_array = np.array(heatmap_data)
        
        fig = go.Figure(data=go.Heatmap(
            z=heatmap_array,
            x=data['TimeMinutes'],
            y=[SENSOR_NAMES.get(s, s) for s in sensors if s in data.columns],
            colorscale='RdYlBu_r',
            colorbar=dict(title="Temperature (°C)")
        ))
        
        fig.update_layout(
            title="Temperature Distribution Heatmap",
            xaxis_title="Time (minutes)",
            yaxis_title="Sensor Position",
            **self.default_layout
        )
        
        return fig
    
    def plot_zone_duration_chart(self, zone_analysis: Dict) -> go.Figure:
        """Create bar chart of time spent in each temperature zone."""
        zones = []
        durations = []
        colors = []
        
        for zone_name, analysis in zone_analysis.items():
            if analysis['total_time_minutes'] > 0:
                zones.append(TEMPERATURE_ZONES[zone_name]['name'])
                durations.append(analysis['total_time_minutes'])
                colors.append(TEMPERATURE_ZONES[zone_name]['color'])
        
        fig = go.Figure(data=[
            go.Bar(
                x=zones,
                y=durations,
                marker_color=colors,
                text=[f"{d:.1f} min" for d in durations],
                textposition='auto'
            )
        ])
        
        fig.update_layout(
            title="Time in Temperature Zones",
            xaxis_title="Temperature Zone",
            yaxis_title="Duration (minutes)",
            **self.default_layout
        )
        
        return fig
    
    def plot_quality_metrics_gauge(self, metrics: Dict) -> go.Figure:
        """Create gauge charts for quality metrics."""
        fig = make_subplots(
            rows=1, cols=3,
            subplot_titles=("Temperature Uniformity", "Heating Consistency", "Quality Score"),
            specs=[[{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}]]
        )
        
        # Temperature uniformity (inverse of CV for better visualization)
        uniformity_score = max(0, 100 * (1 - metrics['core_uniformity_cv']))
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=uniformity_score,
                title={'text': f"{metrics['core_uniformity_rating']}"},
                gauge={'axis': {'range': [0, 100]},
                       'bar': {'color': "darkgreen" if uniformity_score > 80 else "orange" if uniformity_score > 60 else "red"},
                       'steps': [
                           {'range': [0, 60], 'color': "lightgray"},
                           {'range': [60, 80], 'color': "gray"},
                           {'range': [80, 100], 'color': "lightgreen"}
                       ],
                       'threshold': {'line': {'color': "red", 'width': 4},
                                   'thickness': 0.75, 'value': 90}}
            ),
            row=1, col=1
        )
        
        # Heating consistency
        consistency = metrics['heating_rate_consistency'] * 100
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=consistency,
                gauge={'axis': {'range': [0, 100]},
                       'bar': {'color': "darkblue" if consistency > 80 else "orange" if consistency > 60 else "red"}}
            ),
            row=1, col=2
        )
        
        # Overall quality score
        fig.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=metrics['quality_score'],
                gauge={'axis': {'range': [0, 100]},
                       'bar': {'color': "darkgreen" if metrics['quality_score'] > 80 else "orange" if metrics['quality_score'] > 60 else "red"}}
            ),
            row=1, col=3
        )
        
        # Create layout without conflicting height
        layout_params = {k: v for k, v in self.default_layout.items() if k != 'height'}
        fig.update_layout(
            title="Quality Metrics Dashboard",
            height=400,
            **layout_params
        )
        
        return fig
    
    def plot_temperature_uniformity(self, data: pd.DataFrame) -> go.Figure:
        """Plot temperature uniformity over time."""
        # Calculate statistics for core sensors
        core_sensors = ['T1', 'T2', 'T3', 'T4']
        core_data = data[core_sensors]
        
        fig = go.Figure()
        
        # Add mean line
        fig.add_trace(go.Scatter(
            x=data['TimeMinutes'],
            y=core_data.mean(axis=1),
            name='Core Mean',
            line=dict(color='black', width=3)
        ))
        
        # Add standard deviation band
        mean_temp = core_data.mean(axis=1)
        std_temp = core_data.std(axis=1)
        
        fig.add_trace(go.Scatter(
            x=data['TimeMinutes'],
            y=mean_temp + std_temp,
            mode='lines',
            line=dict(width=0),
            showlegend=False
        ))
        
        fig.add_trace(go.Scatter(
            x=data['TimeMinutes'],
            y=mean_temp - std_temp,
            mode='lines',
            line=dict(width=0),
            fill='tonexty',
            fillcolor='rgba(0,100,80,0.2)',
            name='±1 Std Dev'
        ))
        
        # Add individual sensor lines
        for sensor in core_sensors:
            fig.add_trace(go.Scatter(
                x=data['TimeMinutes'],
                y=data[sensor],
                name=SENSOR_NAMES.get(sensor, sensor),
                line=dict(width=1, dash='dot'),
                opacity=0.5
            ))
        
        fig.update_layout(
            title="Core Temperature Uniformity Analysis",
            xaxis_title="Time (minutes)",
            yaxis_title="Temperature (°C)",
            **self.default_layout
        )
        
        return fig
    
    def plot_s_curve(self, data: pd.DataFrame, landmarks: Dict[str, SCurveLandmark],
                     zones: Dict[str, Dict], show_targets: bool = True) -> go.Figure:
        """
        Plot the S-curve with zones and landmarks.
        
        Args:
            data: Temperature data
            landmarks: S-curve landmarks
            zones: Zone analysis results
            show_targets: Show target benchmark ranges
        """
        fig = go.Figure()
        
        # Main S-curve (core temperature vs time)
        fig.add_trace(go.Scatter(
            x=data['TimeMinutes'],
            y=data['CoreAverage'],
            name='Core Temperature (S-Curve)',
            line=dict(color='darkblue', width=3),
            hovertemplate='Time: %{x:.1f} min<br>Temp: %{y:.1f}°C<extra></extra>'
        ))
        
        # Add S-curve zones as colored backgrounds
        max_time = data['TimeMinutes'].max()
        
        # Oven Spring Zone
        if 'oven_spring' in zones:
            fig.add_vrect(
                x0=0,
                x1=zones['oven_spring']['duration_minutes'],
                fillcolor=S_CURVE_ZONES['OVEN_SPRING']['color'],
                opacity=0.2,
                layer="below",
                annotation_text="Oven Spring",
                annotation_position="top left"
            )
        
        # Critical Change Zone
        if 'critical_change' in zones:
            start = zones.get('oven_spring', {}).get('duration_minutes', 0)
            fig.add_vrect(
                x0=start,
                x1=start + zones['critical_change']['duration_minutes'],
                fillcolor=S_CURVE_ZONES['CRITICAL_CHANGE']['color'],
                opacity=0.2,
                layer="below",
                annotation_text="Critical Change",
                annotation_position="top left"
            )
        
        # Bake-Out Zone
        if 'bake_out' in zones:
            start = max_time - zones['bake_out']['duration_minutes']
            fig.add_vrect(
                x0=start,
                x1=max_time,
                fillcolor=S_CURVE_ZONES['BAKE_OUT']['color'],
                opacity=0.2,
                layer="below",
                annotation_text="Bake-Out",
                annotation_position="top left"
            )
        
        # Add landmarks
        for landmark_name, landmark in landmarks.items():
            color = 'green' if landmark.is_within_target else 'red'
            symbol = 'circle' if landmark.is_within_target else 'x'
            
            fig.add_trace(go.Scatter(
                x=[landmark.time_minutes],
                y=[landmark.temperature],
                mode='markers+text',
                name=landmark.name,
                marker=dict(size=12, color=color, symbol=symbol),
                text=[f"{landmark.name}<br>{landmark.time_percentage:.1f}% of bake"],
                textposition="top center",
                hovertemplate=f'{landmark.name}<br>Time: {landmark.time_minutes:.1f} min<br>' +
                             f'Percentage: {landmark.time_percentage:.1f}%<br>' +
                             f'Target: {landmark.target_percentage_range[0]}-{landmark.target_percentage_range[1]}%<extra></extra>'
            ))
            
            # Show target ranges
            if show_targets:
                target_min = max_time * landmark.target_percentage_range[0] / 100
                target_max = max_time * landmark.target_percentage_range[1] / 100
                
                fig.add_shape(
                    type="rect",
                    x0=target_min, x1=target_max,
                    y0=landmark.temperature - 2, y1=landmark.temperature + 2,
                    fillcolor=color, opacity=0.1,
                    line=dict(color=color, width=1, dash="dash")
                )
        
        # Add horizontal lines for key temperatures
        fig.add_hline(y=56, line_dash="dot", line_color="gray", 
                     annotation_text="Yeast Kill (56°C)")
        fig.add_hline(y=82, line_dash="dot", line_color="gray", 
                     annotation_text="Starch Complete (82°C)")
        fig.add_hline(y=93, line_dash="dot", line_color="gray", 
                     annotation_text="Arrival Temp (93°C)")
        
        fig.update_layout(
            title="S-Curve Analysis with Landmarks and Zones",
            xaxis_title="Time (minutes)",
            yaxis_title="Core Temperature (°C)",
            **self.default_layout
        )
        
        return fig
    
    def plot_bakeout_analysis(self, bakeout: BakeOutAnalysis, data: pd.DataFrame) -> go.Figure:
        """Create visualization for bake-out analysis."""
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=("Bake-Out Temperature Profile", "Moisture Loss Estimation",
                          "Bake-Out Percentage", "Quality Assessment"),
            specs=[[{'type': 'scatter'}, {'type': 'scatter'}],
                   [{'type': 'indicator'}, {'type': 'table'}]],
            vertical_spacing=0.15,
            horizontal_spacing=0.1
        )
        
        # Bake-out temperature profile
        bakeout_data = data[data['TimeMinutes'] >= bakeout.start_time_minutes]
        if not bakeout_data.empty:
            fig.add_trace(
                go.Scatter(
                    x=bakeout_data['TimeMinutes'],
                    y=bakeout_data['CoreAverage'],
                    name='Core Temp',
                    line=dict(color='red', width=2)
                ),
                row=1, col=1
            )
            fig.add_hline(y=93, line_dash="dash", line_color="gray", row=1, col=1)
        
        # Moisture loss over time - simplified linear approximation for visualization
        if bakeout.duration_minutes > 0:
            time_points = np.linspace(0, bakeout.duration_minutes, 50)
            # Simple linear approximation based on average rate
            initial = bakeout.final_moisture_estimate + (bakeout.moisture_loss_rate * bakeout.duration_minutes)
            moisture = initial - (bakeout.moisture_loss_rate * time_points)
            
            fig.add_trace(
                go.Scatter(
                    x=time_points,
                    y=moisture,
                    name='Moisture %',
                    line=dict(color='blue', width=2),
                    hovertemplate='Time: %{x:.1f} min<br>Moisture: %{y:.1f}%<extra></extra>'
                ),
                row=1, col=2
            )
            
            # Add final moisture point
            fig.add_trace(
                go.Scatter(
                    x=[bakeout.duration_minutes],
                    y=[bakeout.final_moisture_estimate],
                    mode='markers',
                    name='Final Moisture',
                    marker=dict(size=10, color='red', symbol='circle'),
                    showlegend=False
                ),
                row=1, col=2
            )
        
        # Bake-out percentage gauge
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=bakeout.percentage_of_bake,
                title={'text': "Bake-Out %"},
                delta={'reference': 15, 'increasing': {'color': "red"}},
                gauge={
                    'axis': {'range': [0, 30]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [0, 10], 'color': "lightgray"},
                        {'range': [10, 20], 'color': "gray"},
                        {'range': [20, 30], 'color': "lightcoral"}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': 20
                    }
                }
            ),
            row=2, col=1
        )
        
        # Quality assessment table
        fig.add_trace(
            go.Table(
                header=dict(
                    values=['Metric', 'Value'],
                    fill_color='paleturquoise',
                    align='left'
                ),
                cells=dict(
                    values=[
                        ['Quality', 'Duration', 'Final Moisture', 'Recommendation'],
                        [bakeout.quality_assessment,
                         f'{bakeout.duration_minutes:.1f} min',
                         f'{bakeout.final_moisture_estimate:.1f}%',
                         bakeout.recommendations[0] if bakeout.recommendations else 'Optimal']
                    ],
                    fill_color='lavender',
                    align='left',
                    height=30
                )
            ),
            row=2, col=2
        )
        
        # Update axes
        fig.update_xaxes(title_text="Time (minutes)", row=1, col=1)
        fig.update_yaxes(title_text="Temperature (°C)", row=1, col=1)
        fig.update_xaxes(title_text="Bake-Out Time (minutes)", row=1, col=2)
        fig.update_yaxes(title_text="Moisture Content (%)", row=1, col=2)
        
        layout_params = {k: v for k, v in self.default_layout.items() if k != 'height'}
        fig.update_layout(
            title="Bake-Out Analysis Dashboard",
            height=800,
            showlegend=False,
            **layout_params
        )
        
        return fig
    
    def plot_quality_diagnostics(self, issues: List[Dict], score: float) -> go.Figure:
        """Create visualization for quality diagnostics."""
        if not issues:
            # No issues found
            fig = go.Figure()
            fig.add_annotation(
                text=f"No Quality Issues Detected<br>S-Curve Score: {score:.1f}/100",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=24, color="green")
            )
            fig.update_layout(
                title="Quality Diagnostics",
                **self.default_layout
            )
            return fig
        
        # Sort issues by severity
        severity_order = {'High': 0, 'Medium': 1, 'Low': 2}
        issues_sorted = sorted(issues, key=lambda x: severity_order.get(x['severity'], 3))
        
        # Create sunburst chart for issues
        labels = ['All Issues']
        parents = ['']
        values = [len(issues)]
        colors = [f'rgb({255 - score*2.55}, {score*2.55}, 0)']
        
        for severity in ['High', 'Medium', 'Low']:
            severity_issues = [i for i in issues if i['severity'] == severity]
            if severity_issues:
                labels.append(severity)
                parents.append('All Issues')
                values.append(len(severity_issues))
                colors.append('red' if severity == 'High' else 'orange' if severity == 'Medium' else 'yellow')
                
                for issue in severity_issues:
                    labels.append(issue['issue'])
                    parents.append(severity)
                    values.append(1)
                    colors.append('red' if severity == 'High' else 'orange' if severity == 'Medium' else 'yellow')
        
        fig = go.Figure(go.Sunburst(
            labels=labels,
            parents=parents,
            values=values,
            marker=dict(colors=colors),
            textinfo="label+percent parent",
            hovertemplate='<b>%{label}</b><br>Count: %{value}<extra></extra>'
        ))
        
        # Add score annotation
        fig.add_annotation(
            text=f"S-Curve Score: {score:.1f}/100",
            xref="paper", yref="paper",
            x=0.5, y=1.1, showarrow=False,
            font=dict(size=18)
        )
        
        fig.update_layout(
            title="Quality Issues Breakdown",
            **self.default_layout
        )
        
        return fig