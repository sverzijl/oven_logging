"""Tests for physics-based surface sensor detection."""

import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.surface_sensor_detector import identify_surface_sensor_advanced, get_baking_physics_metrics
from src.data.loader import ThermalProfileLoader


class TestSurfaceSensorDetection:
    """Test cases for surface sensor detection algorithm."""
    
    def create_test_data(self, scenario='normal'):
        """Create test temperature data for different scenarios."""
        # Base time series (30 minutes at 5-second intervals)
        n_samples = 360
        time_minutes = np.linspace(0, 30, n_samples)
        
        if scenario == 'normal':
            # Normal baking curve
            # T1-T4: Core sensors (max ~95°C)
            t1 = 25 + 70 * (1 - np.exp(-0.1 * time_minutes))
            t2 = 25 + 70 * (1 - np.exp(-0.095 * time_minutes))
            t3 = 25 + 71 * (1 - np.exp(-0.09 * time_minutes))
            t4 = 25 + 72 * (1 - np.exp(-0.085 * time_minutes))
            
            # T5-T6: Interface sensors (max ~105°C)
            t5 = 25 + 80 * (1 - np.exp(-0.08 * time_minutes))
            t6 = 25 + 82 * (1 - np.exp(-0.075 * time_minutes))
            
            # T7: Surface sensor (reaches browning zone)
            t7 = 25 + 110 * (1 - np.exp(-0.07 * time_minutes))
            
            # T8: Ambient sensor
            t8 = 25 + 145 * (1 - np.exp(-0.065 * time_minutes))
            
        elif scenario == 'shallow_insertion':
            # Shallow insertion - T1 is actually surface
            t1 = 25 + 105 * (1 - np.exp(-0.08 * time_minutes))  # Surface behavior
            t2 = 25 + 85 * (1 - np.exp(-0.085 * time_minutes))
            t3 = 25 + 75 * (1 - np.exp(-0.09 * time_minutes))
            t4 = 25 + 70 * (1 - np.exp(-0.095 * time_minutes))
            t5 = 25 + 65 * (1 - np.exp(-0.1 * time_minutes))
            t6 = 25 + 60 * (1 - np.exp(-0.105 * time_minutes))
            t7 = 25 + 55 * (1 - np.exp(-0.11 * time_minutes))
            t8 = 25 + 50 * (1 - np.exp(-0.115 * time_minutes))
            
        elif scenario == 'deep_insertion':
            # Deep insertion - surface is T8
            t1 = 25 + 60 * (1 - np.exp(-0.12 * time_minutes))
            t2 = 25 + 65 * (1 - np.exp(-0.115 * time_minutes))
            t3 = 25 + 70 * (1 - np.exp(-0.11 * time_minutes))
            t4 = 25 + 75 * (1 - np.exp(-0.105 * time_minutes))
            t5 = 25 + 80 * (1 - np.exp(-0.1 * time_minutes))
            t6 = 25 + 85 * (1 - np.exp(-0.095 * time_minutes))
            t7 = 25 + 95 * (1 - np.exp(-0.09 * time_minutes))
            t8 = 25 + 115 * (1 - np.exp(-0.085 * time_minutes))  # Surface behavior
            
        elif scenario == 'no_browning':
            # No sensor reaches browning zone
            t1 = 25 + 65 * (1 - np.exp(-0.1 * time_minutes))
            t2 = 25 + 66 * (1 - np.exp(-0.095 * time_minutes))
            t3 = 25 + 67 * (1 - np.exp(-0.09 * time_minutes))
            t4 = 25 + 68 * (1 - np.exp(-0.085 * time_minutes))
            t5 = 25 + 70 * (1 - np.exp(-0.08 * time_minutes))
            t6 = 25 + 75 * (1 - np.exp(-0.075 * time_minutes))
            t7 = 25 + 80 * (1 - np.exp(-0.07 * time_minutes))
            t8 = 25 + 85 * (1 - np.exp(-0.065 * time_minutes))
            
        # Create DataFrame
        df = pd.DataFrame({
            'TimeMinutes': time_minutes,
            'T1': t1,
            'T2': t2,
            'T3': t3,
            'T4': t4,
            'T5': t5,
            'T6': t6,
            'T7': t7,
            'T8': t8
        })
        
        # Add some realistic noise
        for col in ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']:
            df[col] += np.random.normal(0, 0.5, n_samples)
        
        return df
    
    def test_normal_baking_curve(self):
        """Test detection with normal baking curve."""
        df = self.create_test_data('normal')
        result = identify_surface_sensor_advanced(df)
        
        assert result is not None
        assert result['sensor'] == 'T7'
        assert result['confidence'] >= 60
        assert result['max_temp'] > 110
        assert result['browning_time'] > 5
        print(f"Normal curve: {result}")
    
    def test_shallow_insertion(self):
        """Test detection with shallow probe insertion."""
        df = self.create_test_data('shallow_insertion')
        result = identify_surface_sensor_advanced(df)
        
        assert result is not None
        assert result['sensor'] == 'T1'  # Should detect T1 as surface
        assert result['confidence'] >= 60
        assert result['max_temp'] > 110
        print(f"Shallow insertion: {result}")
    
    def test_deep_insertion(self):
        """Test detection with deep probe insertion."""
        df = self.create_test_data('deep_insertion')
        result = identify_surface_sensor_advanced(df)
        
        assert result is not None
        assert result['sensor'] == 'T8'  # Should detect T8 as surface
        assert result['confidence'] >= 60
        assert result['max_temp'] > 110
        print(f"Deep insertion: {result}")
    
    def test_no_browning_zone(self):
        """Test detection when no sensor reaches browning zone."""
        df = self.create_test_data('no_browning')
        result = identify_surface_sensor_advanced(df)
        
        # Should return None or low confidence when no browning detected
        assert result is None or result['confidence'] < 60
        print(f"No browning: {result}")
    
    def test_real_csv_files(self):
        """Test with real CSV files."""
        test_files = [
            'ProbeData_1000BA3C_2025-05-30 09_46_16.csv',
            'ProbeData_1000BA3C_2025-05-30 17_59_37.csv',
            'ProbeData_1000F3C1_2025-05-23 09_11_59.csv',
            'ProbeData_100098DE_2025-05-30 13_51_07.csv'
        ]
        
        for file in test_files:
            if os.path.exists(file):
                print(f"\nTesting {file}:")
                loader = ThermalProfileLoader()
                data, metadata = loader.load_csv(file)
                
                # Get firmware selection
                firmware_sensor = loader.sensor_assignments.get('surface', 'Unknown')
                
                # Run physics-based detection
                result = identify_surface_sensor_advanced(data)
                
                if result:
                    print(f"  Firmware selected: {firmware_sensor}")
                    print(f"  Physics detected: {result['sensor']}")
                    print(f"  Confidence: {result['confidence']}%")
                    print(f"  Max temp: {result['max_temp']:.1f}°C")
                    print(f"  Browning time: {result['browning_time']:.1f} min")
                    
                    # Check if correction was needed
                    if firmware_sensor != result['sensor']:
                        print(f"  ✅ Correction needed and applied!")
                    else:
                        print(f"  ℹ️  Firmware selection was correct")
    
    def test_physics_metrics(self):
        """Test physics metrics calculation."""
        df = self.create_test_data('normal')
        
        # Test with surface sensor
        metrics = get_baking_physics_metrics(df, 'T7')
        
        assert 'phases' in metrics
        assert 'browning_phase' in metrics['phases']
        assert metrics['phases']['browning_phase'] > 0
        assert 'optimal_crust' in metrics
        print(f"Physics metrics: {metrics}")
    
    def test_edge_cases(self):
        """Test edge cases and error handling."""
        # Empty DataFrame
        df_empty = pd.DataFrame()
        result = identify_surface_sensor_advanced(df_empty)
        assert result is None
        
        # Missing sensors
        df_partial = pd.DataFrame({
            'TimeMinutes': [0, 5, 10],
            'T1': [25, 50, 75],
            'T2': [25, 51, 76]
        })
        result = identify_surface_sensor_advanced(df_partial)
        assert result is None
        
        # Single data point
        df_single = pd.DataFrame({
            'TimeMinutes': [0],
            'T1': [25], 'T2': [25], 'T3': [25], 'T4': [25],
            'T5': [25], 'T6': [25], 'T7': [25], 'T8': [25]
        })
        result = identify_surface_sensor_advanced(df_single)
        assert result is None


if __name__ == "__main__":
    # Run tests
    test = TestSurfaceSensorDetection()
    
    print("Running surface sensor detection tests...\n")
    
    try:
        test.test_normal_baking_curve()
        print("✅ Normal baking curve test passed")
    except AssertionError as e:
        print(f"❌ Normal baking curve test failed: {e}")
    
    try:
        test.test_shallow_insertion()
        print("✅ Shallow insertion test passed")
    except AssertionError as e:
        print(f"❌ Shallow insertion test failed: {e}")
    
    try:
        test.test_deep_insertion()
        print("✅ Deep insertion test passed")
    except AssertionError as e:
        print(f"❌ Deep insertion test failed: {e}")
    
    try:
        test.test_no_browning_zone()
        print("✅ No browning zone test passed")
    except AssertionError as e:
        print(f"❌ No browning zone test failed: {e}")
    
    try:
        test.test_physics_metrics()
        print("✅ Physics metrics test passed")
    except AssertionError as e:
        print(f"❌ Physics metrics test failed: {e}")
    
    try:
        test.test_edge_cases()
        print("✅ Edge cases test passed")
    except AssertionError as e:
        print(f"❌ Edge cases test failed: {e}")
    
    print("\nTesting with real CSV files...")
    test.test_real_csv_files()
    
    print("\n✅ All tests completed!")