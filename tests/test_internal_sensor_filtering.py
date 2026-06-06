"""Tests for the improved internal sensor filtering algorithm."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.data.loader import ThermalProfileLoader


class TestInternalSensorFiltering:
    """Test the temperature-based internal sensor filtering."""
    
    @pytest.fixture
    def loader(self):
        """Create a loader instance for testing."""
        return ThermalProfileLoader()
    
    @pytest.fixture
    def base_data(self):
        """Create base test data with time and sensor columns."""
        # Create 30 minutes of data at 5-second intervals
        n_samples = 360
        time_index = pd.date_range(start='2025-01-06 10:00:00', periods=n_samples, freq='5s')
        
        data = pd.DataFrame({
            'Timestamp': time_index,
            'TimeMinutes': np.arange(n_samples) * 5 / 60,
            'T1': np.zeros(n_samples),
            'T2': np.zeros(n_samples),
            'T3': np.zeros(n_samples),
            'T4': np.zeros(n_samples),
            'T5': np.zeros(n_samples),
            'T6': np.zeros(n_samples),
            'T7': np.zeros(n_samples),
            'T8': np.zeros(n_samples),
            'VirtualCoreTemperature': np.zeros(n_samples),
            'VirtualSurfaceTemperature': np.zeros(n_samples),
            'VirtualAmbientTemperature': np.zeros(n_samples),
        })
        
        return data
    
    def test_all_sensors_below_threshold(self, loader, base_data):
        """Test when all internal sensors stay below 100°C."""
        # Setup: T5 is surface, T1-T4 are internal candidates
        # All stay below 100°C
        data = base_data.copy()
        data['T1'] = np.linspace(25, 95, len(data))  # Core
        data['T2'] = np.linspace(25, 96, len(data))
        data['T3'] = np.linspace(25, 98, len(data))
        data['T4'] = np.linspace(25, 99, len(data))
        data['T5'] = np.linspace(25, 150, len(data))  # Surface
        
        loader.data = data
        loader._sensor_overrides[0] = {'surface': 'T5'}
        
        internal_sensors = loader.get_internal_sensors(curve_index=0, data=data)
        
        # All sensors T1-T4 should be included
        assert set(internal_sensors) == {'T1', 'T2', 'T3', 'T4'}
    
    def test_some_sensors_exceed_threshold(self, loader, base_data):
        """Test when some internal sensors exceed 103°C."""
        # Setup: T5 is surface, T3 and T4 exceed threshold
        data = base_data.copy()
        data['T1'] = np.linspace(25, 95, len(data))   # Stays below
        data['T2'] = np.linspace(25, 101, len(data))  # Just at limit
        data['T3'] = np.linspace(25, 105, len(data))  # Exceeds
        data['T4'] = np.linspace(25, 110, len(data))  # Exceeds
        data['T5'] = np.linspace(25, 150, len(data))  # Surface
        
        loader.data = data
        loader._sensor_overrides[0] = {'surface': 'T5'}
        
        internal_sensors = loader.get_internal_sensors(curve_index=0, data=data)
        
        # Only T1 and T2 should be included (T2 max is 101, below 103 threshold)
        assert set(internal_sensors) == {'T1', 'T2'}
    
    def test_core_sensor_always_included(self, loader, base_data):
        """Test that core sensor is always included even if it exceeds threshold."""
        # Setup: T1 is core but exceeds threshold
        data = base_data.copy()
        data['T1'] = np.linspace(25, 106, len(data))  # Core, exceeds threshold
        data['T2'] = np.linspace(25, 95, len(data))
        data['T3'] = np.linspace(25, 96, len(data))
        data['T4'] = np.linspace(25, 150, len(data))  # Surface
        
        loader.data = data
        loader._sensor_overrides[0] = {'core': 'T1', 'surface': 'T4'}
        
        internal_sensors = loader.get_internal_sensors(curve_index=0, data=data)
        
        # T1 should be included despite exceeding threshold
        assert 'T1' in internal_sensors
        # T2 and T3 should also be included
        assert set(internal_sensors) == {'T1', 'T2', 'T3'}
    
    def test_no_sensors_below_threshold_except_core(self, loader, base_data):
        """Test when all sensors except core exceed threshold."""
        # Setup: All internal sensors exceed threshold
        data = base_data.copy()
        data['T1'] = np.linspace(25, 95, len(data))   # Core, stays below
        data['T2'] = np.linspace(25, 108, len(data))  # Exceeds
        data['T3'] = np.linspace(25, 110, len(data))  # Exceeds
        data['T4'] = np.linspace(25, 150, len(data))  # Surface
        
        loader.data = data
        loader._sensor_overrides[0] = {'core': 'T1', 'surface': 'T4'}
        
        internal_sensors = loader.get_internal_sensors(curve_index=0, data=data)
        
        # Only T1 (core) should be included
        assert internal_sensors == ['T1']
    
    def test_realistic_baking_profile(self, loader, base_data):
        """Test with a realistic baking temperature profile."""
        # Simulate realistic baking curve
        data = base_data.copy()
        time_points = len(data)
        
        # T1: Core sensor - reaches ~95°C
        data['T1'] = 25 + 70 * (1 - np.exp(-np.arange(time_points) / 120))
        
        # T2: Deep internal - reaches ~98°C
        data['T2'] = 25 + 73 * (1 - np.exp(-np.arange(time_points) / 110))
        
        # T3: Near crust internal - reaches ~108°C (exceeds 103°C threshold).
        # NB the exponential only *approaches* 25+coeff asymptotically, so the
        # coefficient must be large enough that the achieved max over the 360
        # samples clears 103 (25 + 85*(1-e^-3.59) ≈ 107.7°C); the previous
        # coeff of 80 only reached 102.8°C, leaving T3 below the threshold.
        data['T3'] = 25 + 85 * (1 - np.exp(-np.arange(time_points) / 100))
        
        # T4: Very near crust - reaches 115°C (exceeds threshold)
        data['T4'] = 25 + 90 * (1 - np.exp(-np.arange(time_points) / 90))
        
        # T5: Surface - reaches 160°C
        data['T5'] = 25 + 135 * (1 - np.exp(-np.arange(time_points) / 80))
        
        loader.data = data
        loader._sensor_overrides[0] = {'surface': 'T5'}
        
        internal_sensors = loader.get_internal_sensors(curve_index=0, data=data)
        
        # Only T1 and T2 should be included (stay below 103°C)
        assert set(internal_sensors) == {'T1', 'T2'}
    
    def test_backward_compatibility_no_data(self, loader, base_data):
        """Test backward compatibility when no data is provided."""
        # Setup loader with basic structure
        loader.data = base_data
        loader._sensor_overrides[0] = {'surface': 'T5'}
        
        # Call without data parameter
        internal_sensors = loader.get_internal_sensors(curve_index=0)
        
        # Should return all candidates (no temperature filtering)
        # This tests the fallback behavior
        assert len(internal_sensors) > 0
    
    def test_surface_sensor_t1(self, loader, base_data):
        """Test edge case where surface sensor is T1."""
        data = base_data.copy()
        loader.data = data
        loader._sensor_overrides[0] = {'surface': 'T1'}
        
        internal_sensors = loader.get_internal_sensors(curve_index=0, data=data)
        
        # No internal sensors when surface is T1
        assert internal_sensors == []
    
    def test_missing_sensor_columns(self, loader, base_data):
        """Test handling of missing sensor columns."""
        data = base_data.copy()
        # Remove some sensor columns
        data = data.drop(['T3', 'T4'], axis=1)
        
        data['T1'] = np.linspace(25, 95, len(data))
        data['T2'] = np.linspace(25, 96, len(data))
        data['T5'] = np.linspace(25, 150, len(data))  # Surface
        
        loader.data = data
        loader._sensor_overrides[0] = {'surface': 'T5'}
        
        internal_sensors = loader.get_internal_sensors(curve_index=0, data=data)
        
        # Should only include existing sensors
        assert set(internal_sensors) == {'T1', 'T2'}
    
    def test_temperature_spike_handling(self, loader, base_data):
        """Test handling of temporary temperature spikes."""
        data = base_data.copy()
        
        # T2 has a brief spike above 103°C
        temp_profile = np.linspace(25, 95, len(data))
        temp_profile[100:110] = 105  # Brief spike
        data['T2'] = temp_profile
        
        data['T1'] = np.linspace(25, 92, len(data))
        data['T3'] = np.linspace(25, 96, len(data))
        data['T4'] = np.linspace(25, 150, len(data))  # Surface
        
        loader.data = data
        loader._sensor_overrides[0] = {'surface': 'T4'}

        internal_sensors = loader.get_internal_sensors(curve_index=0, data=data)

        # T2 should be excluded due to spike exceeding 103°C
        assert set(internal_sensors) == {'T1', 'T3'}


class TestInternalSensorCurveZeroResolution:
    """Finding 3: for curve_index=0 the falsy-zero check must not silently
    fall through to current_curve_index, and the candidate sensors must be
    enumerated from the CHOSEN curve's DataFrame, not self.data."""

    @pytest.fixture
    def loader(self):
        return ThermalProfileLoader()

    def _curve_df(self, surface_max, t1_max=95.0, t2_max=96.0, t3_max=98.0):
        n = 360
        df = pd.DataFrame({
            'Timestamp': np.arange(n) * 5.0,
            'TimeMinutes': np.arange(n) * 5.0 / 60,
            'T1': np.linspace(25, t1_max, n),
            'T2': np.linspace(25, t2_max, n),
            'T3': np.linspace(25, t3_max, n),
            'T4': np.linspace(25, surface_max, n),  # surface
        })
        return df

    def test_curve_zero_uses_its_own_df_not_self_data(self, loader):
        """With no explicit ``data`` arg, curve 0 must resolve via
        all_curves[0]['data'], and the candidate enumeration must come from
        that df — even when self.data is a DIFFERENT (wrong-shaped) frame."""
        curve0 = self._curve_df(surface_max=150.0)
        # all_curves[0] holds curve 0's df; self.data is a deliberately
        # different frame missing the lower sensors so that enumerating from
        # it (the bug) would return the wrong set.
        loader.all_curves = [{'data': curve0}]
        loader.current_curve_index = 0
        loader.data = curve0.drop(columns=['T2', 'T3'])
        loader._sensor_overrides[0] = {'surface': 'T4'}

        internal = loader.get_internal_sensors(curve_index=0)
        # Curve 0 has T1, T2, T3 below the T4 surface; all stay <103.
        assert set(internal) == {'T1', 'T2', 'T3'}

    def test_curve_zero_distinct_from_current_curve_index(self, loader):
        """curve_index=0 must select curve 0 even when current_curve_index
        points at a different curve."""
        curve0 = self._curve_df(surface_max=150.0, t1_max=95.0, t2_max=96.0,
                                t3_max=98.0)
        # Curve 1 has T3 above threshold, so a falsy-zero fall-through to
        # current_curve_index=1 would drop T3 and reveal the bug.
        curve1 = self._curve_df(surface_max=150.0, t1_max=95.0, t2_max=96.0,
                                t3_max=110.0)
        loader.all_curves = [{'data': curve0}, {'data': curve1}]
        loader.current_curve_index = 1
        loader.data = curve1
        loader._sensor_overrides[0] = {'surface': 'T4'}
        loader._sensor_overrides[1] = {'surface': 'T4'}

        internal0 = loader.get_internal_sensors(curve_index=0)
        assert set(internal0) == {'T1', 'T2', 'T3'}, (
            "curve 0's internal sensors must reflect curve 0's data, not "
            "current_curve_index"
        )

    def test_guards_when_curve_df_is_none(self, loader):
        """No KeyError/AttributeError when the chosen curve has no df."""
        loader.all_curves = [{'data': None}]
        loader.current_curve_index = 0
        loader.data = None
        loader._sensor_overrides[0] = {'surface': 'T4'}
        assert loader.get_internal_sensors(curve_index=0) == []