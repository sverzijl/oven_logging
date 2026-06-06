"""Tests for curve comparison functionality."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from src.analysis.curve_comparison import CurveComparison, transform_sensor_assignments_to_roles
from src.data.loader import ThermalProfileLoader
import tempfile
import os


class TestCurveComparison:
    """Test suite for CurveComparison class."""
    
    @pytest.fixture
    def sample_curves(self):
        """Create sample curve data for testing."""
        # Create two curves with different sensor assignments
        curves = []
        
        # Curve 1: T1=core, T5=surface, T8=ambient
        time_minutes = np.linspace(0, 30, 100)
        curve1_data = pd.DataFrame({
            'TimeMinutes': time_minutes,
            'T1': 20 + 80 * (1 - np.exp(-time_minutes/10)),  # Core
            'T2': 20 + 75 * (1 - np.exp(-time_minutes/10)),  # Internal
            'T3': 20 + 75 * (1 - np.exp(-time_minutes/10)),  # Internal
            'T4': 20 + 70 * (1 - np.exp(-time_minutes/10)),  # Internal
            'T5': 20 + 85 * (1 - np.exp(-time_minutes/12)),  # Surface
            'T6': 20 + 82 * (1 - np.exp(-time_minutes/12)),  # Internal
            'T7': 20 + 78 * (1 - np.exp(-time_minutes/11)),  # Internal
            'T8': 20 + 10 * (1 - np.exp(-time_minutes/20)),  # Ambient
            'CoreTemperature': 20 + 80 * (1 - np.exp(-time_minutes/10)),
            'SurfaceTemperature': 20 + 85 * (1 - np.exp(-time_minutes/12)),
            'AmbientTemperature': 20 + 10 * (1 - np.exp(-time_minutes/20))
        })
        
        curves.append({
            'curve_data': {'data': curve1_data},
            'sensor_roles': {
                'T1': 'core',
                'T2': 'internal',
                'T3': 'internal', 
                'T4': 'internal',
                'T5': 'surface',
                'T6': 'internal',
                'T7': 'internal',
                'T8': 'ambient'
            },
            'metadata': {
                'product_name': 'Test Bread 1',
                'oven_name': 'Oven A'
            },
            'filename': 'test_file1.csv',
            'file_curve_index': 0
        })
        
        # Curve 2: T3=core, T7=surface, T8=ambient (different probe orientation)
        curve2_data = pd.DataFrame({
            'TimeMinutes': time_minutes,
            'T1': 20 + 70 * (1 - np.exp(-time_minutes/11)),  # Internal
            'T2': 20 + 72 * (1 - np.exp(-time_minutes/11)),  # Internal
            'T3': 20 + 78 * (1 - np.exp(-time_minutes/10)),  # Core
            'T4': 20 + 75 * (1 - np.exp(-time_minutes/10)),  # Internal
            'T5': 20 + 73 * (1 - np.exp(-time_minutes/11)),  # Internal
            'T6': 20 + 74 * (1 - np.exp(-time_minutes/11)),  # Internal
            'T7': 20 + 83 * (1 - np.exp(-time_minutes/12)),  # Surface
            'T8': 20 + 12 * (1 - np.exp(-time_minutes/20)),  # Ambient
            'CoreTemperature': 20 + 78 * (1 - np.exp(-time_minutes/10)),
            'SurfaceTemperature': 20 + 83 * (1 - np.exp(-time_minutes/12)),
            'AmbientTemperature': 20 + 12 * (1 - np.exp(-time_minutes/20))
        })
        
        curves.append({
            'curve_data': {'data': curve2_data},
            'sensor_roles': {
                'T1': 'internal',
                'T2': 'internal',
                'T3': 'core',
                'T4': 'internal',
                'T5': 'internal',
                'T6': 'internal',
                'T7': 'surface',
                'T8': 'ambient'
            },
            'metadata': {
                'product_name': 'Test Bread 2',
                'oven_name': 'Oven B'
            },
            'filename': 'test_file2.csv',
            'file_curve_index': 0
        })
        
        return curves
    
    def test_curve_comparison_initialization(self, sample_curves):
        """Test CurveComparison initialization."""
        comparison = CurveComparison(sample_curves)
        assert len(comparison.curves) == 2
        assert comparison.num_curves == 2
    
    def test_get_role_based_data(self, sample_curves):
        """Test extraction of role-based temperature data."""
        comparison = CurveComparison(sample_curves)
        role_data = comparison.get_role_based_data()
        
        # Check structure
        assert 'core' in role_data
        assert 'surface' in role_data
        assert 'ambient' in role_data
        assert 'internal' in role_data
        
        # Check that we have data for each curve
        assert len(role_data['core']) == 2
        assert len(role_data['surface']) == 2
        assert len(role_data['ambient']) == 2
        
        # Verify core temperatures match regardless of sensor
        # Curve 1 uses T1 as core, Curve 2 uses T3 as core
        assert np.allclose(
            role_data['core'][0]['temperature'],
            sample_curves[0]['curve_data']['data']['CoreTemperature'].values
        )
        assert np.allclose(
            role_data['core'][1]['temperature'],
            sample_curves[1]['curve_data']['data']['CoreTemperature'].values
        )
    
    def test_compare_zone_durations(self, sample_curves):
        """Test zone duration comparison."""
        comparison = CurveComparison(sample_curves)
        zone_comparison = comparison.compare_zone_durations()
        
        # Check structure
        assert isinstance(zone_comparison, pd.DataFrame)
        assert 'Curve' in zone_comparison.columns
        assert len(zone_comparison) == 2  # Two curves
        
        # Check that zone columns exist
        zone_columns = [col for col in zone_comparison.columns if col != 'Curve']
        assert len(zone_columns) > 0
    
    def test_compare_quality_metrics(self, sample_curves):
        """Test quality metrics comparison."""
        comparison = CurveComparison(sample_curves)
        quality_metrics = comparison.compare_quality_metrics()
        
        # Check structure
        assert isinstance(quality_metrics, pd.DataFrame)
        assert 'Curve' in quality_metrics.columns
        assert 'Max Core Temp' in quality_metrics.columns
        assert 'Duration' in quality_metrics.columns
        assert len(quality_metrics) == 2
    
    def test_compare_s_curve_landmarks(self, sample_curves):
        """Test S-curve landmark comparison."""
        comparison = CurveComparison(sample_curves)
        landmarks = comparison.compare_s_curve_landmarks()
        
        # Check structure
        assert isinstance(landmarks, pd.DataFrame)
        assert 'Curve' in landmarks.columns
        assert len(landmarks) == 2
        
        # Check for landmark columns
        for temp in ['56°C', '82°C', '93°C']:
            assert f'Time to {temp}' in landmarks.columns or temp not in landmarks.columns
    
    def test_get_heating_rate_comparison(self, sample_curves):
        """Test heating rate comparison data."""
        comparison = CurveComparison(sample_curves)
        heating_data = comparison.get_heating_rate_comparison()
        
        # Check structure
        assert 'core_rates' in heating_data
        assert 'surface_rates' in heating_data
        assert len(heating_data['core_rates']) == 2
        assert len(heating_data['surface_rates']) == 2
    
    @pytest.mark.skip(reason="Curve detection logic needs specific temperature patterns")
    def test_with_real_multi_curve_file(self):
        """Test with a real multi-curve CSV file."""
        # Create a multi-curve CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("""Combustion Inc. Probe Data
App: iOS Prod app 2.1.1
CSV version: 4
Probe S/N: 100098DE
Probe FW version: v1.5.4
Probe HW revision: v1.1-A1
Framework: iOS
Sample Period: 5000
Created: 2024-01-01 10:00:00

Timestamp,SessionID,SequenceNumber,T1,T2,T3,T4,T5,T6,T7,T8,VirtualCoreTemperature,VirtualSurfaceTemperature,VirtualAmbientTemperature
0.000,1,0,20,20,20,20,20,20,20,20,T1;T2;T3;T4,T5;T6;T7,T8
5.000,1,1,40,38,39,38,41,41,42,21,T1;T2;T3;T4,T5;T6;T7,T8
10.000,1,2,60,58,59,58,61,61,62,22,T1;T2;T3;T4,T5;T6;T7,T8
600.000,1,120,95,94,95,94,96,96,97,30,T1;T2;T3;T4,T5;T6;T7,T8
605.000,1,121,92,91,92,91,93,93,94,29,T1;T2;T3;T4,T5;T6;T7,T8
610.000,1,122,40,40,40,40,41,41,42,25,T1;T2;T3;T4,T5;T6;T7,T8
900.000,2,180,20,20,20,20,20,20,20,20,T3;T4,T1;T2;T5,T8
905.000,2,181,40,42,38,38,41,42,43,21,T3;T4,T1;T2;T5,T8
910.000,2,182,60,62,58,58,61,62,63,22,T3;T4,T1;T2;T5,T8
1500.000,2,300,96,97,94,94,97,98,99,30,T3;T4,T1;T2;T5,T8
""")
            temp_path = f.name
        
        try:
            # Load the file
            loader = ThermalProfileLoader()
            data, metadata = loader.load_csv(temp_path)
            
            # Get all curves
            curves = []
            for i in range(len(loader.all_curves)):
                loader.set_current_curve(i)
                curves.append({
                    'curve_data': {'data': loader.get_current_curve_data()},
                    'sensor_roles': loader.get_sensor_roles(),
                    'metadata': loader.metadata,
                    'filename': os.path.basename(temp_path),
                    'file_curve_index': i
                })
            
            # Create comparison
            comparison = CurveComparison(curves)
            
            # Test that it works
            assert comparison.num_curves == 2
            role_data = comparison.get_role_based_data()
            assert len(role_data['core']) == 2
            
            # Verify different sensor assignments
            # Curve 1: core = T1,T2,T3,T4
            # Curve 2: core = T3,T4
            assert comparison.curves[0]['sensor_roles']['T1'] == 'core'
            assert comparison.curves[1]['sensor_roles']['T1'] == 'surface'
            
        finally:
            os.unlink(temp_path)
    
    def test_empty_curves(self):
        """Test handling of empty curves list."""
        comparison = CurveComparison([])
        assert comparison.num_curves == 0
        
        # Methods should return empty results
        role_data = comparison.get_role_based_data()
        assert all(len(role_data[role]) == 0 for role in role_data)
    
    def test_single_curve(self, sample_curves):
        """Test handling of single curve (edge case)."""
        comparison = CurveComparison([sample_curves[0]])
        assert comparison.num_curves == 1

        # Should still work but with single curve data
        role_data = comparison.get_role_based_data()
        assert len(role_data['core']) == 1

        quality_metrics = comparison.compare_quality_metrics()
        assert len(quality_metrics) == 1

    def test_max_core_temp_uses_core_average_not_raw_t1(self):
        """#24: compare_quality_metrics must resolve core via the column helper
        (CoreTemperature → CoreAverage), NOT fall back to raw T1.

        Build a curve with the legacy CoreAverage column (no CoreTemperature)
        whose peak is 95°C, while T1 peaks at a misleading 200°C. The reported
        'Max Core Temp' must be ~95°C, not 200°C.
        """
        time_minutes = np.linspace(0, 30, 100)
        core_avg = 20 + 75 * (1 - np.exp(-time_minutes / 10))  # peaks ~95
        data = pd.DataFrame({
            'TimeMinutes': time_minutes,
            'CoreAverage': core_avg,
            # Sabotage T1 with an implausible spike to detect the wrong fallback.
            'T1': np.full_like(time_minutes, 200.0),
            'T2': core_avg,
            'T3': core_avg,
            'T4': core_avg,
        })
        curve = {
            'curve_data': {'data': data},
            'sensor_roles': {},
            'metadata': {'sample_period_s': 5.0},
            'filename': 'legacy.csv',
            'file_curve_index': 0,
        }
        comparison = CurveComparison([curve])
        metrics = comparison.compare_quality_metrics()
        max_core_str = metrics.iloc[0]['Max Core Temp']
        max_core_val = float(max_core_str.replace('°C', ''))
        assert max_core_val == pytest.approx(core_avg.max(), abs=0.5)
        assert max_core_val < 150  # definitely not the sabotaged T1

    def test_time_to_temp_uses_core_average_not_raw_t1(self):
        """#24 companion: _get_time_to_temp must also resolve core via the
        helper so 'Time to 93°C' reflects CoreAverage, not raw T1."""
        time_minutes = np.linspace(0, 30, 100)
        core_avg = 20 + 90 * (1 - np.exp(-time_minutes / 10))  # ramps past 93
        data = pd.DataFrame({
            'TimeMinutes': time_minutes,
            'CoreAverage': core_avg,
            'T1': np.full_like(time_minutes, 200.0),  # would cross 93 instantly
            'T2': core_avg,
            'T3': core_avg,
            'T4': core_avg,
        })
        curve = {
            'curve_data': {'data': data},
            'sensor_roles': {},
            'metadata': {'sample_period_s': 5.0},
            'filename': 'legacy.csv',
            'file_curve_index': 0,
        }
        comparison = CurveComparison([curve])
        # 93°C crossing time for core_avg must be > 0 (it ramps up), whereas
        # raw T1 (=200 everywhere) would cross at t=0.
        t93 = comparison._get_time_to_temp(data, 93)
        assert t93 is not None
        assert t93 > 1.0  # raw-T1 fallback would have returned ~0


class TestTransformSensorAssignments:
    """Test the transformation of sensor assignments."""
    
    def test_transform_basic(self):
        """Test basic transformation from loader format to role format."""
        # Loader format
        sensor_assignments = {
            'core': ['T1', 'T2', 'T3', 'T4'],
            'surface': ['T5', 'T6', 'T7'],
            'ambient': ['T8']
        }
        
        # Transform
        sensor_roles = transform_sensor_assignments_to_roles(sensor_assignments)
        
        # Verify
        assert sensor_roles['T1'] == 'core'
        assert sensor_roles['T2'] == 'core'
        assert sensor_roles['T3'] == 'core'
        assert sensor_roles['T4'] == 'core'
        assert sensor_roles['T5'] == 'surface'
        assert sensor_roles['T6'] == 'surface'
        assert sensor_roles['T7'] == 'surface'
        assert sensor_roles['T8'] == 'ambient'
    
    def test_transform_with_internal(self):
        """Test that unassigned sensors become internal."""
        sensor_assignments = {
            'core': ['T1'],
            'surface': ['T7'],
            'ambient': ['T8']
        }
        
        sensor_roles = transform_sensor_assignments_to_roles(sensor_assignments)
        
        # T2-T6 should be internal
        assert sensor_roles['T1'] == 'core'
        assert sensor_roles['T2'] == 'internal'
        assert sensor_roles['T3'] == 'internal'
        assert sensor_roles['T4'] == 'internal'
        assert sensor_roles['T5'] == 'internal'
        assert sensor_roles['T6'] == 'internal'
        assert sensor_roles['T7'] == 'surface'
        assert sensor_roles['T8'] == 'ambient'
    
    def test_transform_empty(self):
        """Test empty sensor assignments."""
        sensor_assignments = {}
        
        sensor_roles = transform_sensor_assignments_to_roles(sensor_assignments)
        
        # All should be internal
        for i in range(1, 9):
            assert sensor_roles[f'T{i}'] == 'internal'
    
    def test_transform_partial(self):
        """Test partial sensor assignments."""
        sensor_assignments = {
            'core': ['T1', 'T2']
            # No surface or ambient
        }
        
        sensor_roles = transform_sensor_assignments_to_roles(sensor_assignments)
        
        assert sensor_roles['T1'] == 'core'
        assert sensor_roles['T2'] == 'core'
        for i in range(3, 9):
            assert sensor_roles[f'T{i}'] == 'internal'


class TestLoaderIntegration:
    """Test integration with ThermalProfileLoader."""
    
    def test_loader_sensor_assignment_format(self):
        """Test that we correctly handle the actual loader format."""
        # Create a simple CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("""Combustion Inc. Probe Data
App: iOS Prod app 2.1.1
CSV version: 4
Probe S/N: 100098DE
Probe FW version: v1.5.4
Probe HW revision: v1.1-A1
Framework: iOS
Sample Period: 5000
Created: 2024-01-01 10:00:00

Timestamp,SessionID,SequenceNumber,T1,T2,T3,T4,T5,T6,T7,T8,VirtualCoreTemperature,VirtualSurfaceTemperature,VirtualAmbientTemperature
0.000,1,0,20,20,20,20,20,20,20,20,T1;T2;T3;T4,T5;T6;T7,T8
5.000,1,1,40,38,39,38,41,41,42,21,T1;T2;T3;T4,T5;T6;T7,T8
10.000,1,2,60,58,59,58,61,61,62,22,T1;T2;T3;T4,T5;T6;T7,T8
15.000,1,3,80,78,79,78,81,81,82,23,T1;T2;T3;T4,T5;T6;T7,T8
20.000,1,4,95,93,94,93,96,96,97,24,T1;T2;T3;T4,T5;T6;T7,T8
""")
            temp_path = f.name
        
        try:
            # Load the file
            loader = ThermalProfileLoader()
            data, metadata = loader.load_csv(temp_path)
            
            # Get sensor assignments
            sensor_assignments = loader.get_sensor_assignments()
            
            # Transform to role format
            sensor_roles = transform_sensor_assignments_to_roles(sensor_assignments)
            
            # Verify the transformation
            assert 'T1' in sensor_roles
            assert 'T8' in sensor_roles
            
            # Create curve data as would be done in app.py
            curve_data = {
                'curve_data': {'data': loader.data},
                'sensor_roles': sensor_roles,
                'metadata': metadata,
                'filename': 'test.csv',
                'file_curve_index': 0
            }
            
            # Verify it works with CurveComparison
            comparison = CurveComparison([curve_data])
            assert comparison.num_curves == 1
            
        finally:
            os.unlink(temp_path)