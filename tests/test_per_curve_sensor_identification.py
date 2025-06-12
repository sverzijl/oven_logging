"""Test cases for per-curve sensor identification."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from src.data.loader import ThermalProfileLoader
from datetime import datetime


class TestPerCurveSensorIdentification:
    """Test that sensor identification happens independently for each curve."""
    
    def create_test_data_with_different_sensors(self):
        """Create test data where sensor assignments change between curves.
        
        Curve 1: Probe positioned with T4 as surface (sensors 1-3 in bread, 4 at surface, 5-8 in oven)
        Curve 2: Probe positioned with T6 as surface (sensors 1-5 in bread, 6 at surface, 7-8 in oven)
        """
        # Create timestamps for two curves with gap between
        curve1_times = np.arange(0, 1200, 5)  # 20 minutes
        curve2_times = np.arange(1500, 2700, 5)  # 20 minutes, starting after gap
        all_times = np.concatenate([curve1_times, curve2_times])
        
        data = {'Timestamp': all_times}
        
        # Curve 1: T4 is surface (browning at 150°C)
        # T1-T3 are internal (max ~95°C)
        # T5-T8 are ambient (max 180-250°C)
        n1 = len(curve1_times)
        for i in range(1, 9):
            if i <= 3:  # Internal sensors
                # Internal temperature curve
                base_temp = 20 + 75 * (1 - np.exp(-curve1_times / 300))
                noise = np.random.normal(0, 0.5, n1)
                temps = base_temp + noise
                temps = np.clip(temps, 20, 95)
            elif i == 4:  # Surface sensor
                # Surface temperature with browning
                base_temp = 20 + 130 * (1 - np.exp(-curve1_times / 200))
                # Add browning phase
                browning_start = 600  # 10 minutes
                browning_mask = curve1_times >= browning_start
                base_temp[browning_mask] = 150 + 5 * ((curve1_times[browning_mask] - browning_start) / 100)
                noise = np.random.normal(0, 1, n1)
                temps = base_temp + noise
                temps = np.clip(temps, 20, 160)
            else:  # Ambient sensors
                # Ambient temperature
                base_temp = 20 + 180 * (1 - np.exp(-curve1_times / 150))
                # Different max temps for different positions
                max_temp = 180 + (i - 5) * 20  # T5: 180°C, T8: 240°C
                noise = np.random.normal(0, 2, n1)
                temps = base_temp + noise
                temps = np.clip(temps, 20, max_temp)
            
            # Add room temperature period at start
            temps[:10] = 20 + np.random.normal(0, 0.5, 10)
            
            data[f'T{i}'] = temps
        
        # Curve 2: T6 is surface (browning at 150°C)
        # T1-T5 are internal (max ~95°C)
        # T7-T8 are ambient (max 200-250°C)
        n2 = len(curve2_times)
        curve2_times_normalized = curve2_times - curve2_times[0]  # Normalize for calculations
        
        for i in range(1, 9):
            if i <= 5:  # Internal sensors (more sensors internal in curve 2)
                # Internal temperature curve
                base_temp = 20 + 75 * (1 - np.exp(-curve2_times_normalized / 300))
                noise = np.random.normal(0, 0.5, n2)
                temps = base_temp + noise
                temps = np.clip(temps, 20, 95)
            elif i == 6:  # Surface sensor (different from curve 1!)
                # Surface temperature with browning
                base_temp = 20 + 130 * (1 - np.exp(-curve2_times_normalized / 200))
                # Add browning phase
                browning_start = 600  # 10 minutes
                browning_mask = curve2_times_normalized >= browning_start
                base_temp[browning_mask] = 150 + 5 * ((curve2_times_normalized[browning_mask] - browning_start) / 100)
                noise = np.random.normal(0, 1, n2)
                temps = base_temp + noise
                temps = np.clip(temps, 20, 160)
            else:  # Ambient sensors (only T7-T8 in curve 2)
                # Ambient temperature
                base_temp = 20 + 200 * (1 - np.exp(-curve2_times_normalized / 150))
                # Different max temps for different positions
                max_temp = 220 + (i - 7) * 30  # T7: 220°C, T8: 250°C
                noise = np.random.normal(0, 2, n2)
                temps = base_temp + noise
                temps = np.clip(temps, 20, max_temp)
            
            # Store curve 2 data temporarily
            if f'T{i}_curve2' not in data:
                data[f'T{i}_curve2'] = temps
        
        # Add room temperature gap in middle
        gap_times = np.arange(curve1_times[-1] + 5, curve2_times[0], 5)
        gap_data = {
            'Timestamp': gap_times,
        }
        for i in range(1, 9):
            gap_data[f'T{i}'] = 22 + np.random.normal(0, 0.5, len(gap_times))
        
        # Combine all data
        final_times = np.concatenate([curve1_times, gap_times, curve2_times])
        final_data = {'Timestamp': final_times}
        for i in range(1, 9):
            final_data[f'T{i}'] = np.concatenate([
                data[f'T{i}'],  # Curve 1 data
                gap_data[f'T{i}'],  # Gap data
                data[f'T{i}_curve2']  # Curve 2 data
            ])
        
        # Add virtual columns that will be wrong (to test physics correction)
        # Curve 1: Firmware thinks T3 is surface (wrong, should be T4)
        # Curve 2: Firmware thinks T5 is surface (wrong, should be T6)
        n_total = len(final_times)
        virtual_core_sensor = ['T1'] * n_total
        virtual_surface_sensor = ['T3'] * (n1 + len(gap_times)) + ['T5'] * n2
        virtual_ambient_sensor = ['T8'] * n_total
        
        final_data['VirtualCoreSensor'] = virtual_core_sensor
        final_data['VirtualSurfaceSensor'] = virtual_surface_sensor
        final_data['VirtualAmbientSensor'] = virtual_ambient_sensor
        
        # Create DataFrame first
        df = pd.DataFrame(final_data)
        
        # Add virtual temperature columns
        df['VirtualCoreTemperature'] = df['T1']
        df['VirtualSurfaceTemperature'] = pd.Series([
            df['T3'].iloc[i] if i < n1 + len(gap_times) else df['T5'].iloc[i]
            for i in range(n_total)
        ])
        df['VirtualAmbientTemperature'] = df['T8']
        
        return df
    
    def test_different_sensors_per_curve(self):
        """Test that different curves can have different sensor assignments."""
        # Create test data
        df = self.create_test_data_with_different_sensors()
        
        # Create loader and process data
        loader = ThermalProfileLoader()
        
        # Simulate loading process (bypass file reading)
        loader.data = df
        loader.metadata = {'sample_period_ms': 5000}
        
        # This should identify sensors per curve after implementation
        loader.data = loader._clean_data(loader.data)
        print(f"After clean_data, columns: {list(loader.data.columns)}")
        print(f"Has CoreTemperature: {'CoreTemperature' in loader.data.columns}")
        loader.all_curves = loader._extract_all_baking_curves(loader.data)
        print(f"Found {len(loader.all_curves)} curves")
        
        # Verify we found 2 curves
        assert len(loader.all_curves) == 2, f"Expected 2 curves, found {len(loader.all_curves)}"
        
        # Check curve 1 sensor assignments
        loader.set_current_curve(0)
        curve1_assignments = loader.get_sensor_assignments_with_overrides(0)
        
        # With per-curve identification, curve 1 should identify T4 as surface
        assert curve1_assignments['surface_sensor'] == 'T4', \
            f"Curve 1: Expected T4 as surface, got {curve1_assignments['surface_sensor']}"
        
        # Check curve 2 sensor assignments  
        loader.set_current_curve(1)
        curve2_assignments = loader.get_sensor_assignments_with_overrides(1)
        
        # With per-curve identification, curve 2 should identify T6 as surface
        assert curve2_assignments['surface_sensor'] == 'T6', \
            f"Curve 2: Expected T6 as surface, got {curve2_assignments['surface_sensor']}"
        
        # Verify internal sensors are different
        curve1_internal = loader.get_internal_sensors(0)
        curve2_internal = loader.get_internal_sensors(1)
        
        assert 'T1' in curve1_internal and 'T2' in curve1_internal and 'T3' in curve1_internal
        assert 'T4' not in curve1_internal  # T4 is surface in curve 1
        
        assert 'T1' in curve2_internal and 'T5' in curve2_internal
        assert 'T6' not in curve2_internal  # T6 is surface in curve 2
        
    def test_physics_correction_per_curve(self):
        """Test that physics-based surface correction applies per curve."""
        # Create test data where firmware gets it wrong for both curves
        df = self.create_test_data_with_different_sensors()
        
        loader = ThermalProfileLoader()
        loader.data = df
        loader.metadata = {'sample_period_ms': 5000}
        
        # Process data
        loader.data = loader._clean_data(loader.data)
        loader.all_curves = loader._extract_all_baking_curves(loader.data)
        
        # Check that physics correction was applied to each curve
        for i in range(2):
            loader.set_current_curve(i)
            assignments = loader.get_sensor_assignments_with_overrides(i)
            
            # Should have physics_corrected flag
            assert 'physics_corrected' in assignments, \
                f"Curve {i}: Missing physics_corrected flag"
            
            # Physics correction should fix the surface sensor
            if i == 0:
                # Firmware said T3, physics should correct to T4
                assert assignments['surface_sensor'] == 'T4', \
                    f"Curve 0: Physics correction failed, got {assignments['surface_sensor']}"
            else:
                # Firmware said T5, physics should correct to T6
                assert assignments['surface_sensor'] == 'T6', \
                    f"Curve 1: Physics correction failed, got {assignments['surface_sensor']}"
    
    def test_manual_overrides_per_curve(self):
        """Test that manual sensor overrides work independently per curve."""
        df = self.create_test_data_with_different_sensors()
        
        loader = ThermalProfileLoader()
        loader.data = df
        loader.metadata = {'sample_period_ms': 5000}
        loader.data = loader._clean_data(loader.data)
        loader.all_curves = loader._extract_all_baking_curves(loader.data)
        
        # Override surface sensor for curve 0 only
        loader.set_sensor_override(0, 'surface', 'T5')
        
        # Check curve 0 has override
        loader.set_current_curve(0)
        curve0_assignments = loader.get_sensor_assignments_with_overrides(0)
        assert curve0_assignments['surface_sensor'] == 'T5'
        assert curve0_assignments['has_overrides'] == True
        
        # Check curve 1 doesn't have override
        loader.set_current_curve(1)
        curve1_assignments = loader.get_sensor_assignments_with_overrides(1)
        assert curve1_assignments['surface_sensor'] != 'T5'  # Should be T6 from physics
        assert curve1_assignments['has_overrides'] == False
        
    def test_standardized_columns_per_curve(self):
        """Test that standardized temperature columns reflect per-curve sensors."""
        df = self.create_test_data_with_different_sensors()
        
        loader = ThermalProfileLoader()
        loader.data = df
        loader.metadata = {'sample_period_ms': 5000}
        loader.data = loader._clean_data(loader.data)
        loader.all_curves = loader._extract_all_baking_curves(loader.data)
        
        # Check curve 0 surface temperature uses T4
        loader.set_current_curve(0)
        curve0_data = loader.data
        # Surface temperature should match T4 values
        assert np.allclose(curve0_data['SurfaceTemperature'].values, 
                          curve0_data['T4'].values, rtol=0.01)
        
        # Check curve 1 surface temperature uses T6
        loader.set_current_curve(1)
        curve1_data = loader.data
        # Surface temperature should match T6 values
        assert np.allclose(curve1_data['SurfaceTemperature'].values,
                          curve1_data['T6'].values, rtol=0.01)
    
    def test_backward_compatibility_single_curve(self):
        """Test that single-curve files still work correctly."""
        # Create single curve data
        times = np.arange(0, 1200, 5)
        n = len(times)
        
        data = {
            'Timestamp': times,
            'VirtualCoreSensor': ['T1'] * n,
            'VirtualSurfaceSensor': ['T5'] * n,
            'VirtualAmbientSensor': ['T8'] * n,
        }
        
        # Add temperature data
        for i in range(1, 9):
            if i <= 4:
                # Internal
                temps = 20 + 75 * (1 - np.exp(-times / 300))
            elif i == 5:
                # Surface
                temps = 20 + 150 * (1 - np.exp(-times / 200))
            else:
                # Ambient
                temps = 20 + 200 * (1 - np.exp(-times / 150))
            
            data[f'T{i}'] = temps + np.random.normal(0, 0.5, n)
        
        # Add virtual temperature columns
        data['VirtualCoreTemperature'] = data['T1']
        data['VirtualSurfaceTemperature'] = data['T5']
        data['VirtualAmbientTemperature'] = data['T8']
        
        df = pd.DataFrame(data)
        
        loader = ThermalProfileLoader()
        loader.data = df
        loader.metadata = {'sample_period_ms': 5000}
        loader.data = loader._clean_data(loader.data)
        loader.all_curves = loader._extract_all_baking_curves(loader.data)
        
        # Should find exactly one curve
        assert len(loader.all_curves) == 1
        
        # Check sensor assignments
        assignments = loader.get_sensor_assignments_with_overrides(0)
        assert assignments['surface_sensor'] == 'T5'
        assert assignments['core_sensor'] == 'T1'
        assert assignments['ambient_sensors'] == ['T8']


if __name__ == "__main__":
    # Run tests
    test = TestPerCurveSensorIdentification()
    
    print("Testing different sensors per curve...")
    test.test_different_sensors_per_curve()
    print("✓ Passed")
    
    print("\nTesting physics correction per curve...")
    test.test_physics_correction_per_curve()
    print("✓ Passed")
    
    print("\nTesting manual overrides per curve...")
    test.test_manual_overrides_per_curve()
    print("✓ Passed")
    
    print("\nTesting standardized columns per curve...")
    test.test_standardized_columns_per_curve()
    print("✓ Passed")
    
    print("\nTesting backward compatibility...")
    test.test_backward_compatibility_single_curve()
    print("✓ Passed")
    
    print("\nAll tests passed!")