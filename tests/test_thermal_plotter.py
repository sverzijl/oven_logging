"""Unit tests for ThermalPlotter visualization components."""

import pytest
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from dataclasses import dataclass
from typing import Tuple
from src.visualization.plots import ThermalPlotter
from src.analysis.s_curve_analysis import SCurveLandmark


class TestThermalPlotter:
    """Test suite for ThermalPlotter class."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample temperature data for testing."""
        time_minutes = np.linspace(0, 30, 100)
        return pd.DataFrame({
            'TimeMinutes': time_minutes,
            'T1': 20 + 60 * (1 - np.exp(-time_minutes / 10)),  # Core sensor
            'T2': 20 + 55 * (1 - np.exp(-time_minutes / 12)),  # Internal sensor 1
            'T3': 20 + 52 * (1 - np.exp(-time_minutes / 13)),  # Internal sensor 2
            'T4': 20 + 50 * (1 - np.exp(-time_minutes / 14)),  # Internal sensor 3
            'T5': 20 + 70 * (1 - np.exp(-time_minutes / 8)),   # Surface sensor
            'T6': 20 + 2 * np.sin(time_minutes / 5),           # Ambient sensor
            'T7': 20 + 58 * (1 - np.exp(-time_minutes / 11)),  # Extra sensor
            'T8': 20 + 56 * (1 - np.exp(-time_minutes / 11.5)),  # Extra sensor
            'CoreTemperature': 20 + 60 * (1 - np.exp(-time_minutes / 10)),
            'SurfaceTemperature': 20 + 70 * (1 - np.exp(-time_minutes / 8)),
            'AmbientTemperature': 20 + 2 * np.sin(time_minutes / 5)
        })
    
    @pytest.fixture
    def plotter(self):
        """Create ThermalPlotter instance."""
        return ThermalPlotter()
    
    def test_internal_temperature_shading_single_sensor(self, plotter, sample_data):
        """Test that shading is not added with only one internal sensor."""
        fig = go.Figure()
        initial_traces = len(fig.data)
        
        # Add shading with only one sensor
        plotter._add_internal_temperature_shading(fig, sample_data, ['T2'])
        
        # Should not add any traces
        assert len(fig.data) == initial_traces
    
    def test_internal_temperature_shading_multiple_sensors(self, plotter, sample_data):
        """Test that shading is correctly added with multiple internal sensors."""
        fig = go.Figure()
        initial_traces = len(fig.data)
        
        # Add shading with multiple sensors
        internal_sensors = ['T2', 'T3', 'T4']
        plotter._add_internal_temperature_shading(fig, sample_data, internal_sensors)
        
        # Should add exactly 2 traces (max and min with fill)
        assert len(fig.data) == initial_traces + 2
        
        # Check the first trace (max, invisible)
        max_trace = fig.data[-2]
        assert max_trace.showlegend == False
        assert max_trace.hoverinfo == 'skip'
        assert max_trace.fill is None
        
        # Check the second trace (min, with fill)
        min_trace = fig.data[-1]
        assert min_trace.fill == 'tonexty'
        assert min_trace.name == 'Internal Temperature Range'
        assert min_trace.fillcolor == 'rgba(70, 130, 180, 0.2)'
        assert min_trace.showlegend == True
        
        # Verify the data values
        internal_data = sample_data[internal_sensors].values
        expected_min = np.min(internal_data, axis=1)
        expected_max = np.max(internal_data, axis=1)
        
        np.testing.assert_array_equal(max_trace.y, expected_max)
        np.testing.assert_array_equal(min_trace.y, expected_min)
        np.testing.assert_array_equal(min_trace.customdata, expected_max)
    
    def test_internal_temperature_shading_custom_parameters(self, plotter, sample_data):
        """Test shading with custom name, color, and legend group."""
        fig = go.Figure()
        
        # Add shading with custom parameters
        internal_sensors = ['T2', 'T3', 'T4']
        custom_name = 'Custom Range'
        custom_color = 'rgba(255, 0, 0, 0.3)'
        custom_group = 'group1'
        
        plotter._add_internal_temperature_shading(
            fig, sample_data, internal_sensors,
            name=custom_name,
            color=custom_color,
            legendgroup=custom_group
        )
        
        # Check custom parameters were applied
        min_trace = fig.data[-1]
        assert min_trace.name == custom_name
        assert min_trace.fillcolor == custom_color
        assert min_trace.legendgroup == custom_group
        
        # Both traces should have the same legend group
        max_trace = fig.data[-2]
        assert max_trace.legendgroup == custom_group
    
    def test_plot_s_curve_with_internal_sensors(self, plotter, sample_data):
        """Test that plot_s_curve correctly includes internal temperature shading."""
        landmarks = {
            'yeast_kill': SCurveLandmark(
                name='yeast_kill',
                time_minutes=5.0,
                time_percentage=16.7,
                temperature=56.0,
                target_percentage_range=(10, 20),
                is_within_target=False
            )
        }
        zones = {'zone1': {'duration': 10, 'average_temp': 50}}
        internal_sensors = ['T2', 'T3', 'T4']
        
        # Create S-curve plot with internal sensors
        fig = plotter.plot_s_curve(
            sample_data, 
            landmarks, 
            zones,
            internal_sensors=internal_sensors
        )
        
        # Find the internal temperature range traces
        internal_range_traces = [
            trace for trace in fig.data 
            if hasattr(trace, 'name') and trace.name == 'Internal Temperature Range'
        ]
        
        # Should have exactly one internal range trace
        assert len(internal_range_traces) == 1
        
        # Verify it has the correct fill properties
        range_trace = internal_range_traces[0]
        assert range_trace.fill == 'tonexty'
        assert range_trace.fillcolor == 'rgba(70, 130, 180, 0.2)'
    
    def test_plot_s_curve_benchmark_lines_from_config(self, plotter, sample_data):
        """#19: the S-curve reference hlines must be driven by
        config.constants.S_CURVE_BENCHMARKS, not hardcoded 56/82/93.

        Empirically verified by perturbing a benchmark temperature: the
        rendered hline must track the config value, not a hardcoded literal.
        """
        from unittest.mock import patch

        import src.visualization.plots as plots_mod

        landmarks = {
            'yeast_kill': SCurveLandmark(
                name='yeast_kill', time_minutes=5.0, time_percentage=16.7,
                temperature=56.0, target_percentage_range=(10, 20),
                is_within_target=False,
            )
        }
        zones = {'zone1': {'duration': 10, 'average_temp': 50}}

        # Perturbed benchmark set with NON-default temperatures so a hardcoded
        # 56/82/93 implementation would FAIL this test.
        perturbed = {
            "YEAST_KILL": {"temperature": 50, "target_percentage": (45, 55), "critical": True},
            "STARCH_COMPLETE": {"temperature": 77, "target_percentage": (55, 65), "critical": True},
            "ARRIVAL_TEMP": {"temperature": 88, "target_percentage": (80, 90), "critical": True},
        }
        with patch.object(plots_mod, "S_CURVE_BENCHMARKS", perturbed):
            fig = plotter.plot_s_curve(sample_data, landmarks, zones)

        hline_ys = {
            round(float(s.y0), 3)
            for s in fig.layout.shapes
            if getattr(s, 'y0', None) is not None
            and getattr(s, 'y1', None) is not None
            and float(s.y0) == float(s.y1)
        }
        expected = {50.0, 77.0, 88.0}
        assert expected.issubset(hline_ys), (
            f"benchmark hlines must track S_CURVE_BENCHMARKS; expected "
            f"{expected} but got {hline_ys} (hardcoded literals suspected)"
        )
        annotation_blob = " ".join(
            str(a.text) for a in fig.layout.annotations if a.text
        )
        for t in (50, 77, 88):
            assert str(t) in annotation_blob, (
                f"perturbed benchmark {t}°C must appear in an annotation"
            )

    def test_plot_s_curve_comparison_with_internal_sensors(self, plotter, sample_data):
        """Test that plot_s_curve_comparison correctly includes shading for multiple curves."""
        # Prepare data for two curves
        curves_data = [
            {
                'data': sample_data,
                'landmarks': {},
                'name': 'Curve 1',
                'internal_sensors': ['T2', 'T3', 'T4']
            },
            {
                'data': sample_data.copy(),  # Use copy to simulate different curve
                'landmarks': {},
                'name': 'Curve 2',
                'internal_sensors': ['T7', 'T8']
            }
        ]
        
        # Create comparison plot
        fig = plotter.plot_s_curve_comparison(curves_data)
        
        # Find all internal range traces
        internal_range_traces = [
            trace for trace in fig.data 
            if hasattr(trace, 'name') and trace.name and 'Internal Range' in trace.name
        ]
        
        # Should have two internal range traces (one for each curve)
        assert len(internal_range_traces) == 2
        
        # Verify names
        trace_names = [trace.name for trace in internal_range_traces]
        assert 'Curve 1 - Internal Range' in trace_names
        assert 'Curve 2 - Internal Range' in trace_names
        
        # Verify different opacities
        opacities = []
        for trace in internal_range_traces:
            # Extract opacity from rgba color
            color = trace.fillcolor
            opacity = float(color.split(',')[-1].strip(' )'))
            opacities.append(opacity)
        
        # Opacities should be different
        assert opacities[0] != opacities[1]
        
        # Both should be in expected range
        for opacity in opacities:
            assert 0.15 <= opacity <= 0.25
    
    def test_plot_s_curve_comparison_without_internal_sensors(self, plotter, sample_data):
        """Test that plot_s_curve_comparison works without internal sensors."""
        # Prepare data without internal sensors
        curves_data = [
            {
                'data': sample_data,
                'landmarks': {},
                'name': 'Curve 1'
                # No internal_sensors key
            }
        ]
        
        # Create comparison plot
        fig = plotter.plot_s_curve_comparison(curves_data)
        
        # Find all internal range traces
        internal_range_traces = [
            trace for trace in fig.data 
            if hasattr(trace, 'name') and trace.name and 'Internal Range' in str(trace.name)
        ]
        
        # Should have no internal range traces
        assert len(internal_range_traces) == 0
    
    def test_plot_s_curve_comparison_mixed_sensors(self, plotter, sample_data):
        """Test comparison with some curves having internal sensors and others not."""
        curves_data = [
            {
                'data': sample_data,
                'landmarks': {},
                'name': 'Curve 1',
                'internal_sensors': ['T2', 'T3', 'T4']
            },
            {
                'data': sample_data.copy(),
                'landmarks': {},
                'name': 'Curve 2'
                # No internal sensors
            },
            {
                'data': sample_data.copy(),
                'landmarks': {},
                'name': 'Curve 3',
                'internal_sensors': ['T7', 'T8']
            }
        ]
        
        # Create comparison plot
        fig = plotter.plot_s_curve_comparison(curves_data)
        
        # Find all internal range traces
        internal_range_traces = [
            trace for trace in fig.data 
            if hasattr(trace, 'name') and trace.name and 'Internal Range' in trace.name
        ]
        
        # Should have two internal range traces (for curves 1 and 3)
        assert len(internal_range_traces) == 2
        
        # Verify correct curves have shading
        trace_names = [trace.name for trace in internal_range_traces]
        assert 'Curve 1 - Internal Range' in trace_names
        assert 'Curve 2 - Internal Range' not in trace_names
        assert 'Curve 3 - Internal Range' in trace_names