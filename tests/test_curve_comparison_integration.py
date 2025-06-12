"""Integration tests for Curve Comparison functionality."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from src.data.loader import ThermalProfileLoader
from src.analysis.curve_comparison import CurveComparison
from src.visualization.plots import ThermalPlotter


class TestCurveComparisonIntegration:
    """Integration tests for the complete curve comparison workflow."""
    
    @pytest.fixture
    def sample_curve_data(self):
        """Create sample curve data for testing."""
        time_minutes = np.linspace(0, 20, 100)
        
        # Create three different curves with slightly different profiles
        curves = []
        for i in range(3):
            # Generate temperature data with slight variations
            core_temp = 20 + (100 - 20) / (1 + np.exp(-0.5 * (time_minutes - 10 - i)))
            surface_temp = core_temp + 5 + i * 2
            ambient_temp = np.ones_like(time_minutes) * (25 + i)
            
            # Create internal sensors
            internal_temps = []
            for j in range(4):
                internal_temp = core_temp + (j + 1) * 2 + np.random.normal(0, 0.5, len(time_minutes))
                internal_temps.append(internal_temp)
            
            curve_data = pd.DataFrame({
                'TimeMinutes': time_minutes,
                'CoreTemperature': core_temp,
                'SurfaceTemperature': surface_temp,
                'AmbientTemperature': ambient_temp,
                'T1': core_temp,
                'T2': internal_temps[0],
                'T3': internal_temps[1],
                'T4': internal_temps[2],
                'T5': internal_temps[3],
                'T6': surface_temp,
                'T7': ambient_temp,
                'T8': ambient_temp
            })
            
            curves.append({
                'name': f'Test Curve {i+1}',
                'short_name': f'TC{i+1}',
                'data': curve_data,
                'metadata': {
                    'sample_period_s': 12,
                    'product_type': 'white_pan',
                    'probe_serial': f'TEST{i+1:04d}',
                    'timestamp': datetime.now()
                }
            })
        
        return curves
    
    def test_complete_comparison_workflow(self, sample_curve_data):
        """Test the complete curve comparison workflow."""
        # Prepare curves in the expected format
        curves = []
        for curve in sample_curve_data:
            curves.append({
                'curve_data': {'data': curve['data']},
                'sensor_roles': {},  # Will be auto-detected
                'metadata': curve['metadata'],
                'curve_name': curve['name'],
                'curve_short_name': curve['short_name']
            })
        
        # Create comparison instance
        comparison = CurveComparison(curves)
        
        # Test zone duration comparison
        zone_durations = comparison.compare_zone_durations()
        assert not zone_durations.empty
        assert len(zone_durations) == 3  # Three curves
        assert 'Curve' in zone_durations.columns
        
        # Test S-curve landmark comparison
        landmark_comparison = comparison.compare_s_curve_landmarks()
        assert not landmark_comparison.empty
        assert len(landmark_comparison) == 3
        
        # Test heating rate comparison
        heating_data = comparison.get_heating_rate_comparison()
        assert 'core_rates' in heating_data
        assert 'surface_rates' in heating_data
        assert len(heating_data['core_rates']) == 3
        assert len(heating_data['surface_rates']) == 3
        
        # Test quality metrics comparison
        quality_metrics = comparison.compare_quality_metrics()
        assert not quality_metrics.empty
        assert len(quality_metrics) == 3
        
        # Test role-based data retrieval
        role_data = comparison.get_role_based_data()
        assert 'core' in role_data
        assert 'surface' in role_data
        assert len(role_data['core']) == 3
        
    def test_visualization_integration(self, sample_curve_data):
        """Test that visualizations can be created from comparison data."""
        # Prepare curves in the expected format
        curves = []
        for curve in sample_curve_data:
            curves.append({
                'curve_data': {'data': curve['data']},
                'sensor_roles': {},
                'metadata': curve['metadata'],
                'curve_name': curve['name'],
                'curve_short_name': curve['short_name']
            })
        
        # Create comparison instance
        comparison = CurveComparison(curves)
        
        # Create plotter
        plotter = ThermalPlotter()
        
        # Test zone duration visualizations
        zone_durations = comparison.compare_zone_durations()
        
        # Test grouped bar chart
        fig_grouped = plotter.plot_zone_duration_comparison(zone_durations)
        assert fig_grouped is not None
        assert len(fig_grouped.data) > 0
        
        # Test stacked bar chart
        fig_stacked = plotter.plot_zone_duration_stacked(zone_durations)
        assert fig_stacked is not None
        assert fig_stacked.layout.barmode == 'stack'
        
        # Test heatmap
        fig_heatmap = plotter.plot_zone_duration_heatmap(zone_durations)
        assert fig_heatmap is not None
        assert fig_heatmap.data[0].type == 'heatmap'
        
        # Test heating rate visualization
        heating_data = comparison.get_heating_rate_comparison()
        fig_heating = plotter.plot_heating_rate_comparison(heating_data)
        assert fig_heating is not None
        assert len(fig_heating.data) == 6  # 3 curves x 2 types
        
    def test_empty_comparison(self):
        """Test handling of empty comparison."""
        comparison = CurveComparison([])
        
        # All methods should return empty results gracefully
        assert comparison.compare_zone_durations().empty
        assert comparison.compare_s_curve_landmarks().empty
        assert comparison.compare_quality_metrics().empty
        
        heating_data = comparison.get_heating_rate_comparison()
        assert heating_data['core_rates'] == []
        assert heating_data['surface_rates'] == []
        
    def test_single_curve_comparison(self, sample_curve_data):
        """Test comparison with only one curve."""
        # Prepare only one curve
        curve = sample_curve_data[0]
        curves = [{
            'curve_data': {'data': curve['data']},
            'sensor_roles': {},
            'metadata': curve['metadata'],
            'curve_name': curve['name'],
            'curve_short_name': curve['short_name']
        }]
        
        comparison = CurveComparison(curves)
        
        # Should still work with single curve
        zone_durations = comparison.compare_zone_durations()
        assert len(zone_durations) == 1
        
        quality_metrics = comparison.compare_quality_metrics()
        assert len(quality_metrics) == 1
        
    def test_curve_name_handling(self):
        """Test handling of curve names and short names."""
        # Create simple test data
        data = pd.DataFrame({
            'TimeMinutes': [0, 1, 2],
            'CoreTemperature': [20, 50, 80],
            'SurfaceTemperature': [25, 55, 85],
            'T1': [20, 50, 80],
            'T2': [22, 52, 82],
            'T3': [24, 54, 84],
            'T4': [26, 56, 86],
            'T5': [28, 58, 88],
            'T6': [25, 55, 85],
            'T7': [30, 30, 30],
            'T8': [30, 30, 30]
        })
        
        metadata = {'sample_period_s': 60}
        
        # Create simple test data
        data = pd.DataFrame({
            'TimeMinutes': [0, 1, 2],
            'CoreTemperature': [20, 50, 80],
            'SurfaceTemperature': [25, 55, 85],
            'T1': [20, 50, 80],
            'T2': [22, 52, 82],
            'T3': [24, 54, 84],
            'T4': [26, 56, 86],
            'T5': [28, 58, 88],
            'T6': [25, 55, 85],
            'T7': [30, 30, 30],
            'T8': [30, 30, 30]
        })
        
        metadata = {'sample_period_s': 60}
        
        # Test with long name and short name
        curves = [{
            'curve_data': {'data': data},
            'sensor_roles': {},
            'metadata': metadata,
            'curve_name': 'Very Long Curve Name That Would Compress Charts',
            'curve_short_name': 'VLCN_12:34'
        }]
        
        comparison = CurveComparison(curves)
        
        # Verify that the curve is present (name generation is internal)
        zone_durations = comparison.compare_zone_durations()
        assert len(zone_durations) == 1
        assert 'Curve' in zone_durations.columns
        
        # Test without short name (should use full name)
        curves2 = [{
            'curve_data': {'data': data},
            'sensor_roles': {},
            'metadata': metadata,
            'curve_name': 'Test Curve'
        }]
        
        comparison2 = CurveComparison(curves2)
        
        zone_durations2 = comparison2.compare_zone_durations()
        assert len(zone_durations2) == 1
        # The actual curve name will be generated internally


class TestDataFlowIntegration:
    """Test data flow from loader through comparison to visualization."""
    
    def test_zone_color_consistency(self):
        """Test that zone colors are consistent across all visualizations."""
        # Create simple test data
        zone_data = pd.DataFrame({
            'Curve': ['Curve1', 'Curve2'],
            'Yeast Kill': [2.5, 3.0],
            'Starch Gelatinization': [5.2, 4.8],
            'Maillard Reaction': [8.1, 7.5]
        })
        
        plotter = ThermalPlotter()
        
        # Create all three visualizations
        fig_grouped = plotter.plot_zone_duration_comparison(zone_data)
        fig_stacked = plotter.plot_zone_duration_stacked(zone_data)
        fig_heatmap = plotter.plot_zone_duration_heatmap(zone_data)
        
        # Check that Yeast Kill has same color in grouped and stacked
        yeast_kill_color_grouped = None
        yeast_kill_color_stacked = None
        
        for trace in fig_grouped.data:
            if trace.name == 'Yeast Kill':
                yeast_kill_color_grouped = trace.marker.color
                
        for trace in fig_stacked.data:
            if trace.name == 'Yeast Kill':
                yeast_kill_color_stacked = trace.marker.color
                
        assert yeast_kill_color_grouped == yeast_kill_color_stacked == '#FF6B6B'
        
    def test_error_handling_integration(self):
        """Test error handling across the integration."""
        comparison = CurveComparison([])
        plotter = ThermalPlotter()
        
        # Test with invalid data
        invalid_data = pd.DataFrame({'Wrong': [1, 2, 3]})
        
        # Should handle gracefully
        try:
            curves = [{
                'curve_data': {'data': invalid_data},
                'sensor_roles': {},
                'metadata': {},
                'curve_name': 'Invalid'
            }]
            comparison_with_invalid = CurveComparison(curves)
            # If no exception, check that methods return empty results
            zone_durations = comparison_with_invalid.compare_zone_durations()
            assert zone_durations.empty or len(zone_durations) == 0
        except (KeyError, ValueError):
            # Expected behavior - invalid data should raise exception
            pass