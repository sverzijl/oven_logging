"""Test that Temperature Profiles internal range uses correctly filtered sensors."""
import pytest
import pandas as pd
import numpy as np
from src.data.loader import ThermalProfileLoader
from src.analysis.curve_comparison import CurveComparison
from src.visualization.plots import ThermalPlotter


def create_test_data_with_hot_sensors():
    """Create test data where some internal sensors exceed temperature threshold."""
    time_points = 100
    time_minutes = np.linspace(0, 20, time_points)
    
    # Create temperature data
    # T1-T3: True internal sensors (stay below 100°C)
    t1 = 20 + 70 * (1 - np.exp(-time_minutes / 5))  # Max ~90°C
    t2 = 20 + 75 * (1 - np.exp(-time_minutes / 5))  # Max ~95°C
    t3 = 20 + 78 * (1 - np.exp(-time_minutes / 5))  # Max ~98°C
    
    # T4: Borderline sensor (reaches just over 100°C)
    t4 = 20 + 85 * (1 - np.exp(-time_minutes / 5))  # Max ~105°C
    
    # T5: Surface sensor
    t5 = 20 + 130 * (1 - np.exp(-time_minutes / 4))  # Max ~150°C
    
    # T6-T8: External sensors (should not be included in internal range)
    t6 = 20 + 110 * (1 - np.exp(-time_minutes / 4))  # Max ~130°C
    t7 = 20 + 100 * (1 - np.exp(-time_minutes / 4))  # Max ~120°C
    t8 = 20 + 140 * (1 - np.exp(-time_minutes / 3))  # Max ~160°C (ambient)
    
    data = pd.DataFrame({
        'TimeMinutes': time_minutes,
        'T1': t1,
        'T2': t2,
        'T3': t3,
        'T4': t4,
        'T5': t5,
        'T6': t6,
        'T7': t7,
        'T8': t8,
        'VirtualCoreTemperature': (t1 + t2) / 2,
        'VirtualSurfaceTemperature': t5,
        'VirtualAmbientTemperature': t8
    })
    
    return data


def test_internal_sensor_filtering():
    """Test that get_internal_sensors properly filters out hot sensors."""
    data = create_test_data_with_hot_sensors()
    
    # Create loader
    loader = ThermalProfileLoader()
    loader.data = data
    loader.all_curves = [{'data': data}]
    loader.current_curve_index = 0
    
    # Set sensor assignments
    loader.curve_sensor_assignments = [{
        'core': ['T1', 'T2'],
        'surface': ['T5'],
        'ambient': ['T8']
    }]
    
    # Get internal sensors
    internal_sensors = loader.get_internal_sensors(0, data)
    
    # Should only include T1, T2, T3 (below surface and below temp threshold)
    # T4 should be excluded as it exceeds 103°C
    assert 'T1' in internal_sensors
    assert 'T2' in internal_sensors
    assert 'T3' in internal_sensors
    assert 'T4' not in internal_sensors  # Exceeds temperature threshold
    assert 'T6' not in internal_sensors  # Above surface sensor
    assert 'T7' not in internal_sensors  # Above surface sensor


def test_role_based_comparison_all_internals():
    """Test that role-based comparison includes all non-assigned sensors as internal."""
    data = create_test_data_with_hot_sensors()
    
    # Create curve info with sensor roles
    sensor_roles = {
        'T1': 'core',
        'T2': 'core',
        'T5': 'surface',
        'T8': 'ambient',
        # T3, T4, T6, T7 will be marked as 'internal' by default
        'T3': 'internal',
        'T4': 'internal',
        'T6': 'internal',
        'T7': 'internal'
    }
    
    curves = [{
        'curve_data': {'data': data},
        'sensor_roles': sensor_roles,
        'metadata': {'Product': 'Test', 'Probe S/N': '1234'}
    }]
    
    # Create comparison
    comparison = CurveComparison(curves)
    role_data = comparison.get_role_based_data()
    
    # Check that internal includes all non-assigned sensors
    internal_data = role_data['internal'][0]
    assert len(internal_data['sensors']) == 4  # T3, T4, T6, T7
    assert 'T3' in internal_data['sensors']
    assert 'T4' in internal_data['sensors']
    assert 'T6' in internal_data['sensors']
    assert 'T7' in internal_data['sensors']


def test_temperature_range_visualization():
    """Test that the visualization correctly shows the temperature range."""
    data = create_test_data_with_hot_sensors()
    
    # Create plotter
    plotter = ThermalPlotter()
    
    # Test with all internal sensors (incorrect behavior)
    all_internal_sensors = ['T3', 'T4', 'T6', 'T7']
    role_data = {
        'internal': [{
            'time': data['TimeMinutes'].values,
            'temperature': data[all_internal_sensors].values.T,
            'curve_name': 'Test - All Internals',
            'curve_short_name': 'All',
            'sensors': all_internal_sensors
        }]
    }
    
    # This would show a range from T3 (min) to T7 (max), which is too wide
    fig_all = plotter.plot_role_based_comparison(role_data, 'internal', False)
    
    # Test with filtered internal sensors (correct behavior)
    filtered_internal_sensors = ['T1', 'T2', 'T3']  # Only true internal sensors
    role_data_filtered = {
        'internal': [{
            'time': data['TimeMinutes'].values,
            'temperature': data[filtered_internal_sensors].values.T,
            'curve_name': 'Test - Filtered Internals',
            'curve_short_name': 'Filtered',
            'sensors': filtered_internal_sensors
        }]
    }
    
    # This would show a range from T1 (min) to T3 (max), which is correct
    fig_filtered = plotter.plot_role_based_comparison(role_data_filtered, 'internal', False)
    
    # Both figures should be created successfully
    assert fig_all is not None
    assert fig_filtered is not None
    
    # The filtered version should have a narrower temperature range
    # (We can't easily test the actual plotted values without rendering)


if __name__ == "__main__":
    test_internal_sensor_filtering()
    test_role_based_comparison_all_internals()
    test_temperature_range_visualization()
    print("All tests passed!")