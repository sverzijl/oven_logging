"""Tests for legend positioning in temperature profile plots."""

import pytest
import pandas as pd
import numpy as np
from src.visualization.plots import ThermalPlotter
from src.analysis.curve_comparison import CurveComparison


class TestLegendPositioning:
    """Test legend positioning in temperature profile visualizations."""
    
    def create_sample_role_data(self):
        """Create sample role-based data for testing."""
        time = np.linspace(0, 30, 100)
        temp1 = 20 + 60 * (1 - np.exp(-time/10))
        temp2 = 22 + 58 * (1 - np.exp(-time/12))
        
        return {
            'core': [
                {
                    'time': time,
                    'temperature': temp1,
                    'curve_name': 'ProbeData_100098DE_2025-05-30 13_51_07.csv',
                    'curve_short_name': '98DE_13:51'
                },
                {
                    'time': time,
                    'temperature': temp2,
                    'curve_name': 'ProbeData_1000BA3C_2025-05-30 09_46_16.csv',
                    'curve_short_name': 'BA3C_09:46'
                }
            ],
            'surface': [
                {
                    'time': time,
                    'temperature': temp1 + 5,
                    'curve_name': 'ProbeData_100098DE_2025-05-30 13_51_07.csv',
                    'curve_short_name': '98DE_13:51'
                },
                {
                    'time': time,
                    'temperature': temp2 + 5,
                    'curve_name': 'ProbeData_1000BA3C_2025-05-30 09_46_16.csv',
                    'curve_short_name': 'BA3C_09:46'
                }
            ]
        }
    
    def test_role_based_comparison_legend_position(self):
        """Test that role-based comparison plot has legend positioned below."""
        plotter = ThermalPlotter()
        role_data = self.create_sample_role_data()
        
        # Test core temperature plot
        fig = plotter.plot_role_based_comparison(role_data, role='core')
        
        # Check legend configuration
        assert fig.layout.legend.orientation == 'h'
        assert fig.layout.legend.yanchor == 'top'
        assert fig.layout.legend.y == -0.15
        assert fig.layout.legend.xanchor == 'center'
        assert fig.layout.legend.x == 0.5
        assert fig.layout.margin.b == 100
        
        # Test that short names are used in legend
        legend_names = [trace.name for trace in fig.data if trace.showlegend != False]
        assert '98DE_13:51' in legend_names
        assert 'BA3C_09:46' in legend_names
        
        # Test that full names are in hover templates
        for trace in fig.data:
            if hasattr(trace, 'hovertemplate') and trace.hovertemplate:
                assert ('ProbeData_100098DE_2025-05-30 13_51_07.csv' in trace.hovertemplate or
                        'ProbeData_1000BA3C_2025-05-30 09_46_16.csv' in trace.hovertemplate)
    
    def test_heating_rate_comparison_legend_position(self):
        """Test that heating rate comparison plot has legend positioned below."""
        plotter = ThermalPlotter()
        
        heating_data = {
            'core_rates': [
                {
                    'time': np.linspace(0, 30, 100),
                    'rate': np.random.randn(100) * 0.01 + 0.1,
                    'curve_name': 'ProbeData_100098DE_2025-05-30 13_51_07.csv',
                    'curve_short_name': '98DE_13:51'
                },
                {
                    'time': np.linspace(0, 30, 100),
                    'rate': np.random.randn(100) * 0.01 + 0.12,
                    'curve_name': 'ProbeData_1000BA3C_2025-05-30 09_46_16.csv',
                    'curve_short_name': 'BA3C_09:46'
                }
            ],
            'surface_rates': [
                {
                    'time': np.linspace(0, 30, 100),
                    'rate': np.random.randn(100) * 0.01 + 0.15,
                    'curve_name': 'ProbeData_100098DE_2025-05-30 13_51_07.csv',
                    'curve_short_name': '98DE_13:51'
                },
                {
                    'time': np.linspace(0, 30, 100),
                    'rate': np.random.randn(100) * 0.01 + 0.17,
                    'curve_name': 'ProbeData_1000BA3C_2025-05-30 09_46_16.csv',
                    'curve_short_name': 'BA3C_09:46'
                }
            ]
        }
        
        fig = plotter.plot_heating_rate_comparison(heating_data)
        
        # Check legend configuration
        assert fig.layout.legend.orientation == 'h'
        assert fig.layout.legend.yanchor == 'top'
        assert fig.layout.legend.y == -0.1
        assert fig.layout.legend.xanchor == 'center'
        assert fig.layout.legend.x == 0.5
        assert fig.layout.margin.b == 100
    
    def test_s_curve_comparison_legend_position(self):
        """Test that S-curve comparison plot has legend positioned below."""
        plotter = ThermalPlotter()
        
        curves_data = [
            {
                'data': pd.DataFrame({
                    'TimeMinutes': np.linspace(0, 30, 100),
                    'CoreTemperature': 20 + 60 * (1 - np.exp(-np.linspace(0, 30, 100)/10))
                }),
                'name': '98DE_13:51',
                'landmarks': {}
            },
            {
                'data': pd.DataFrame({
                    'TimeMinutes': np.linspace(0, 30, 100),
                    'CoreTemperature': 22 + 58 * (1 - np.exp(-np.linspace(0, 30, 100)/12))
                }),
                'name': 'BA3C_09:46',
                'landmarks': {}
            }
        ]
        
        fig = plotter.plot_s_curve_comparison(curves_data)
        
        # Check legend configuration
        assert fig.layout.legend.orientation == 'h'
        assert fig.layout.legend.yanchor == 'top'
        assert fig.layout.legend.y == -0.15
        assert fig.layout.legend.xanchor == 'center'
        assert fig.layout.legend.x == 0.5
        assert fig.layout.margin.b == 100