"""Integration tests for internal temperature range visualization across tabs."""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from src.data.loader import ThermalProfileLoader
from src.visualization.plots import ThermalPlotter
from src.analysis.s_curve_analysis import SCurveAnalyzer


class TestInternalRangeIntegration:
    """Integration tests for internal temperature range shading."""
    
    @pytest.fixture
    def sample_curve_data(self):
        """Create sample curve data with proper structure."""
        time_minutes = np.linspace(0, 30, 100)
        data = pd.DataFrame({
            'TimeMinutes': time_minutes,
            'T1': 20 + 60 * (1 - np.exp(-time_minutes / 10)),  # Core
            'T2': 20 + 55 * (1 - np.exp(-time_minutes / 12)),  # Internal 1
            'T3': 20 + 52 * (1 - np.exp(-time_minutes / 13)),  # Internal 2
            'T4': 20 + 50 * (1 - np.exp(-time_minutes / 14)),  # Internal 3
            'T5': 20 + 70 * (1 - np.exp(-time_minutes / 8)),   # Surface
            'T6': 20 + 2 * np.sin(time_minutes / 5),           # Ambient
            'T7': 20 + 58 * (1 - np.exp(-time_minutes / 11)),  # Internal 4
            'T8': 20 + 56 * (1 - np.exp(-time_minutes / 11.5)),  # Internal 5
            'CoreTemperature': 20 + 60 * (1 - np.exp(-time_minutes / 10)),
            'SurfaceTemperature': 20 + 70 * (1 - np.exp(-time_minutes / 8)),
            'AmbientTemperature': 20 + 2 * np.sin(time_minutes / 5)
        })
        return data
    
    @pytest.fixture
    def mock_loader(self):
        """Create a mock data loader with proper sensor assignment."""
        loader = MagicMock(spec=ThermalProfileLoader)
        
        # Configure get_internal_sensors to return appropriate sensors
        def get_internal_sensors(curve_idx, data):
            if curve_idx == 0:
                return ['T2', 'T3', 'T4']
            else:
                return ['T7', 'T8']
        
        loader.get_internal_sensors.side_effect = get_internal_sensors
        return loader
    
    def test_single_curve_s_curve_analysis_shading(self, sample_curve_data, mock_loader):
        """Test that S-Curve Analysis tab correctly shows internal temperature shading."""
        plotter = ThermalPlotter()
        analyzer = SCurveAnalyzer(sample_curve_data, {})
        
        # Get analysis results
        report = analyzer.generate_optimization_report()
        landmarks = report['landmarks']
        zones = report['zone_analysis']
        
        # Get internal sensors
        internal_sensors = mock_loader.get_internal_sensors(0, sample_curve_data)
        
        # Create S-curve plot as done in app.py
        fig = plotter.plot_s_curve(
            sample_curve_data,
            landmarks,
            zones,
            show_targets=True,
            internal_sensors=internal_sensors
        )
        
        # Verify shading is present
        internal_range_traces = [
            trace for trace in fig.data 
            if hasattr(trace, 'name') and trace.name == 'Internal Temperature Range'
        ]
        
        assert len(internal_range_traces) == 1
        assert internal_range_traces[0].fillcolor == 'rgba(70, 130, 180, 0.2)'
        
        # Verify the shading uses correct sensors
        internal_data = sample_curve_data[internal_sensors].values
        expected_min = np.min(internal_data, axis=1)
        expected_max = np.max(internal_data, axis=1)
        
        # Find the min trace (has fill='tonexty')
        min_trace = next(t for t in fig.data if hasattr(t, 'fill') and t.fill == 'tonexty')
        np.testing.assert_array_equal(min_trace.y, expected_min)
        np.testing.assert_array_equal(min_trace.customdata, expected_max)
    
    def test_curve_comparison_shading_multiple_curves(self, sample_curve_data, mock_loader):
        """Test that Curve Comparison correctly shows shading for multiple curves."""
        plotter = ThermalPlotter()
        
        # Simulate the curve comparison data structure
        curve1_data = sample_curve_data.copy()
        curve2_data = sample_curve_data.copy()
        
        # Create curve info structures as they would be in app.py
        curves_data = []
        for idx, (data, name) in enumerate([(curve1_data, 'File1.csv'), (curve2_data, 'File2.csv')]):
            # Get landmarks
            analyzer = SCurveAnalyzer(data, {})
            landmarks = analyzer.identify_landmarks()
            
            # Get internal sensors from loader
            internal_sensors = mock_loader.get_internal_sensors(idx, data)
            
            curves_data.append({
                'data': data,
                'landmarks': landmarks,
                'name': name,
                'internal_sensors': internal_sensors
            })
        
        # Create comparison plot
        fig = plotter.plot_s_curve_comparison(curves_data)
        
        # Verify both curves have shading
        internal_range_traces = [
            trace for trace in fig.data 
            if hasattr(trace, 'name') and trace.name and 'Internal Range' in trace.name
        ]
        
        assert len(internal_range_traces) == 2
        
        # Verify different curves use different sensors
        trace_names = sorted([t.name for t in internal_range_traces])
        assert trace_names == ['File1.csv - Internal Range', 'File2.csv - Internal Range']
        
        # Verify each has different opacity
        opacities = []
        for trace in internal_range_traces:
            color = trace.fillcolor
            opacity = float(color.split(',')[-1].strip(' )'))
            opacities.append(opacity)
        
        assert len(set(opacities)) == 2  # Two different opacities
        assert all(0.15 <= op <= 0.25 for op in opacities)
    
    def test_shading_consistency_between_tabs(self, sample_curve_data, mock_loader):
        """Test that shading data is consistent between single and comparison views."""
        plotter = ThermalPlotter()
        analyzer = SCurveAnalyzer(sample_curve_data, {})
        
        # Get analysis results
        report = analyzer.generate_optimization_report()
        landmarks = report['landmarks']
        zones = report['zone_analysis']
        internal_sensors = mock_loader.get_internal_sensors(0, sample_curve_data)
        
        # Create single S-curve plot
        single_fig = plotter.plot_s_curve(
            sample_curve_data,
            landmarks,
            zones,
            internal_sensors=internal_sensors
        )
        
        # Create comparison plot with same data
        curves_data = [{
            'data': sample_curve_data,
            'landmarks': landmarks,
            'name': 'Test Curve',
            'internal_sensors': internal_sensors
        }]
        comparison_fig = plotter.plot_s_curve_comparison(curves_data)
        
        # Extract shading data from both figures
        single_shading = next(
            t for t in single_fig.data 
            if hasattr(t, 'fill') and t.fill == 'tonexty'
        )
        comparison_shading = next(
            t for t in comparison_fig.data 
            if hasattr(t, 'fill') and t.fill == 'tonexty'
        )
        
        # Verify the shading data is the same
        np.testing.assert_array_equal(single_shading.y, comparison_shading.y)
        np.testing.assert_array_equal(single_shading.customdata, comparison_shading.customdata)
    
    def test_app_integration_curve_info_structure(self, sample_curve_data, mock_loader):
        """Test the integration with app.py curve_info structure."""
        plotter = ThermalPlotter()
        
        # Simulate the app.py curve_info structure
        curve_info = {
            'filename': 'test_file.csv',
            'file_curve_index': 0,
            'curve_data': {
                'data': sample_curve_data
            },
            'loader': mock_loader,
            'metadata': {}
        }
        
        # Simulate the s_curve_data preparation as in app.py
        curve_data = curve_info['curve_data']['data']
        s_curve_analyzer = SCurveAnalyzer(curve_data, curve_info.get('metadata', {}))
        landmarks = s_curve_analyzer.identify_landmarks()
        
        # Get internal sensors using the loader
        curve_loader = curve_info['loader']
        internal_sensors = curve_loader.get_internal_sensors(
            curve_info['file_curve_index'], 
            curve_data
        )
        
        s_curve_data = [{
            'data': curve_data,
            'landmarks': landmarks,
            'name': curve_info['filename'],
            'internal_sensors': internal_sensors
        }]
        
        # Create the plot
        fig = plotter.plot_s_curve_comparison(s_curve_data)
        
        # Verify shading was added correctly
        internal_range_traces = [
            trace for trace in fig.data 
            if hasattr(trace, 'name') and trace.name and 'Internal Range' in trace.name
        ]
        
        assert len(internal_range_traces) == 1
        assert internal_sensors == ['T2', 'T3', 'T4']  # Based on mock_loader logic
    
    def test_empty_internal_sensors_handling(self, sample_curve_data):
        """Test graceful handling when no internal sensors are available."""
        plotter = ThermalPlotter()
        analyzer = SCurveAnalyzer(sample_curve_data, {})
        
        # Get analysis results
        report = analyzer.generate_optimization_report()
        landmarks = report['landmarks']
        zones = report['zone_analysis']
        
        # Test with empty internal sensors
        fig = plotter.plot_s_curve(
            sample_curve_data,
            landmarks,
            zones,
            internal_sensors=[]
        )
        
        # Verify no shading traces were added
        shading_traces = [
            trace for trace in fig.data 
            if hasattr(trace, 'fill') and trace.fill == 'tonexty'
        ]
        
        assert len(shading_traces) == 0
    
    def test_legend_grouping_in_comparison(self, sample_curve_data, mock_loader):
        """Test that legend groups are properly set for shading in comparison plots."""
        plotter = ThermalPlotter()
        
        # Create two curves with internal sensors
        curves_data = []
        for idx in range(2):
            analyzer = SCurveAnalyzer(sample_curve_data, {})
            landmarks = analyzer.identify_landmarks()
            internal_sensors = mock_loader.get_internal_sensors(idx, sample_curve_data)
            
            curves_data.append({
                'data': sample_curve_data,
                'landmarks': landmarks,
                'name': f'Curve {idx + 1}',
                'internal_sensors': internal_sensors
            })
        
        # Create comparison plot
        fig = plotter.plot_s_curve_comparison(curves_data)
        
        # Check legend groups
        for idx, curve_info in enumerate(curves_data):
            # Find traces for this curve
            curve_traces = [
                t for t in fig.data 
                if hasattr(t, 'legendgroup') and t.legendgroup == f'curve{idx}'
            ]
            
            # Should have at least 3 traces: shading max (hidden), shading min, main curve
            assert len(curve_traces) >= 3
            
            # All should have the same legend group
            legend_groups = [t.legendgroup for t in curve_traces]
            assert all(lg == f'curve{idx}' for lg in legend_groups)