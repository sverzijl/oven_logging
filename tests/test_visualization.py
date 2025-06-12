"""Unit tests for visualization functions."""

import pytest
import pandas as pd
import numpy as np
from src.visualization.plots import ThermalPlotter
from src.visualization.visualization_config import VisualizationConfig


class TestVisualizationConfig:
    """Test the VisualizationConfig class."""
    
    def test_get_zone_color(self):
        """Test zone color retrieval."""
        # Test known zones
        assert VisualizationConfig.get_zone_color('Yeast Kill') == '#FF6B6B'
        assert VisualizationConfig.get_zone_color('Starch Gelatinization') == '#4ECDC4'
        assert VisualizationConfig.get_zone_color('Maillard Reaction') == '#D2691E'
        
        # Test unknown zone
        assert VisualizationConfig.get_zone_color('Unknown Zone') == '#999999'
        
    def test_get_curve_color(self):
        """Test curve color cycling."""
        colors = VisualizationConfig.CURVE_COLORS
        
        # Test normal indexing
        assert VisualizationConfig.get_curve_color(0) == colors[0]
        assert VisualizationConfig.get_curve_color(1) == colors[1]
        
        # Test cycling behavior
        num_colors = len(colors)
        assert VisualizationConfig.get_curve_color(num_colors) == colors[0]
        assert VisualizationConfig.get_curve_color(num_colors + 1) == colors[1]
        
    def test_format_methods(self):
        """Test formatting methods."""
        assert VisualizationConfig.format_duration(2.5) == '2.5'
        assert VisualizationConfig.format_temperature(93.6) == '93.6°C'
        assert VisualizationConfig.format_percentage(85.234) == '85.2%'
        assert VisualizationConfig.format_rate(0.12345) == '0.123°C/s'


class TestThermalPlotter:
    """Test the ThermalPlotter class."""
    
    @pytest.fixture
    def plotter(self):
        """Create a ThermalPlotter instance."""
        return ThermalPlotter()
    
    @pytest.fixture
    def sample_zone_data(self):
        """Create sample zone comparison data."""
        return pd.DataFrame({
            'Curve': ['Curve1', 'Curve2', 'Curve3'],
            'Yeast Kill': [2.5, 3.0, 2.8],
            'Starch Gelatinization': [5.2, 4.8, 5.5],
            'Maillard Reaction': [8.1, 7.5, 8.3]
        })
    
    def test_plot_zone_duration_comparison(self, plotter, sample_zone_data):
        """Test zone duration comparison plot."""
        fig = plotter.plot_zone_duration_comparison(sample_zone_data)
        
        # Check that figure was created
        assert fig is not None
        
        # Check number of traces (one per zone)
        assert len(fig.data) == 3
        
        # Check that each trace has correct properties
        for i, trace in enumerate(fig.data):
            assert trace.type == 'bar'
            assert len(trace.x) == 3  # Number of curves
            assert len(trace.y) == 3  # Number of curves
            
        # Check trace names match zones
        zone_names = ['Yeast Kill', 'Starch Gelatinization', 'Maillard Reaction']
        for i, zone_name in enumerate(zone_names):
            assert fig.data[i].name == zone_name
            
        # Check colors are correctly assigned
        assert fig.data[0].marker.color == '#FF6B6B'  # Yeast Kill
        assert fig.data[1].marker.color == '#4ECDC4'  # Starch Gelatinization
        assert fig.data[2].marker.color == '#D2691E'  # Maillard Reaction
        
    def test_plot_zone_duration_comparison_empty(self, plotter):
        """Test with empty dataframe."""
        empty_df = pd.DataFrame()
        fig = plotter.plot_zone_duration_comparison(empty_df)
        
        # Should return empty figure
        assert fig is not None
        assert len(fig.data) == 0
        
    def test_plot_zone_duration_stacked(self, plotter, sample_zone_data):
        """Test stacked zone duration plot."""
        fig = plotter.plot_zone_duration_stacked(sample_zone_data)
        
        # Check that figure was created
        assert fig is not None
        
        # Check number of traces (one per zone)
        assert len(fig.data) == 3
        
        # Check layout barmode
        assert fig.layout.barmode == 'stack'
        
        # Check colors are correctly assigned
        assert fig.data[0].marker.color == '#FF6B6B'  # Yeast Kill
        assert fig.data[1].marker.color == '#4ECDC4'  # Starch Gelatinization
        assert fig.data[2].marker.color == '#D2691E'  # Maillard Reaction
        
    def test_plot_zone_duration_heatmap(self, plotter, sample_zone_data):
        """Test zone duration heatmap."""
        fig = plotter.plot_zone_duration_heatmap(sample_zone_data)
        
        # Check that figure was created
        assert fig is not None
        
        # Check that it's a heatmap
        assert len(fig.data) == 1
        assert fig.data[0].type == 'heatmap'
        
        # Check dimensions
        assert fig.data[0].z.shape == (3, 3)  # 3 curves x 3 zones
        
        # Check colorscale (plotly converts list of lists to tuple of tuples)
        expected_colorscale = tuple(tuple(item) for item in VisualizationConfig.HEATMAP_COLORSCALE)
        assert fig.data[0].colorscale == expected_colorscale
        
    def test_plot_heating_rate_comparison(self, plotter):
        """Test heating rate comparison plot."""
        # Create sample heating data
        time = np.linspace(0, 10, 50)
        heating_data = {
            'core_rates': [
                {
                    'curve_name': 'Test Curve 1',
                    'curve_short_name': 'TC1',
                    'time': time,
                    'rate': np.sin(time) * 0.5
                },
                {
                    'curve_name': 'Test Curve 2',
                    'curve_short_name': 'TC2',
                    'time': time,
                    'rate': np.cos(time) * 0.5
                }
            ],
            'surface_rates': [
                {
                    'curve_name': 'Test Curve 1',
                    'curve_short_name': 'TC1',
                    'time': time,
                    'rate': np.sin(time) * 0.8
                },
                {
                    'curve_name': 'Test Curve 2',
                    'curve_short_name': 'TC2',
                    'time': time,
                    'rate': np.cos(time) * 0.8
                }
            ],
            'consistency_scores': []
        }
        
        fig = plotter.plot_heating_rate_comparison(heating_data)
        
        # Check that figure was created
        assert fig is not None
        
        # Check number of traces (2 curves x 2 types)
        assert len(fig.data) == 4
        
        # Check that curves have consistent colors
        assert fig.data[0].line.color == 'blue'  # TC1 core
        assert fig.data[2].line.color == 'blue'  # TC1 surface
        assert fig.data[1].line.color == 'red'   # TC2 core
        assert fig.data[3].line.color == 'red'   # TC2 surface
        
        # Check legend visibility (only core rates should show in legend)
        assert fig.data[0].showlegend is True
        assert fig.data[1].showlegend is True
        assert fig.data[2].showlegend is False
        assert fig.data[3].showlegend is False


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.fixture
    def plotter(self):
        """Create a ThermalPlotter instance."""
        return ThermalPlotter()
    
    def test_single_curve_comparison(self, plotter):
        """Test with only one curve."""
        single_curve_data = pd.DataFrame({
            'Curve': ['OnlyCurve'],
            'Yeast Kill': [2.5],
            'Starch Gelatinization': [5.2]
        })
        
        fig = plotter.plot_zone_duration_comparison(single_curve_data)
        
        assert fig is not None
        assert len(fig.data) == 2  # Two zones
        
    def test_many_curves_comparison(self, plotter):
        """Test with many curves (more than available colors)."""
        many_curves_data = pd.DataFrame({
            'Curve': [f'Curve{i}' for i in range(15)],
            'Yeast Kill': np.random.rand(15) * 5
        })
        
        fig = plotter.plot_zone_duration_comparison(many_curves_data)
        
        assert fig is not None
        assert len(fig.data) == 1  # One zone
        
        # Check x-axis rotation for many curves
        assert fig.layout.xaxis.tickangle == -45
        
    def test_unknown_zone_handling(self, plotter):
        """Test handling of unknown zones."""
        unknown_zone_data = pd.DataFrame({
            'Curve': ['Curve1', 'Curve2'],
            'Unknown Zone 1': [1.5, 2.0],
            'Unknown Zone 2': [3.5, 4.0]
        })
        
        fig = plotter.plot_zone_duration_comparison(unknown_zone_data)
        
        # Should handle unknown zones gracefully
        assert fig is not None
        assert len(fig.data) == 2
        
        # Unknown zones should get default color
        assert fig.data[0].marker.color == '#999999'
        assert fig.data[1].marker.color == '#999999'