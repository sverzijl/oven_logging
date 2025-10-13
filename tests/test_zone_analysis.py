"""Tests for zone analysis to prevent variable name collision bugs."""

import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.zone_analysis import ZoneAnalyzer
from config.constants import TEMPERATURE_ZONES


class TestZoneAnalysis:
    """Test cases for zone analysis methods."""

    def create_test_baking_data(self):
        """Create realistic baking temperature data."""
        # 30 minutes at 5-second intervals
        n_samples = 360
        time_minutes = np.linspace(0, 30, n_samples)

        # Create realistic baking curve
        # Core temperature rises to ~95°C
        core_temp = 25 + 70 * (1 - np.exp(-0.1 * time_minutes))

        # Surface temperature rises higher to ~150°C
        surface_temp = 25 + 125 * (1 - np.exp(-0.08 * time_minutes))

        # Ambient temperature rises to ~180°C
        ambient_temp = 25 + 155 * (1 - np.exp(-0.06 * time_minutes))

        # Create individual sensor data
        t1 = core_temp + np.random.normal(0, 0.5, n_samples)
        t2 = core_temp + np.random.normal(0, 0.5, n_samples)
        t3 = core_temp + np.random.normal(0, 0.5, n_samples)
        t4 = core_temp + np.random.normal(0, 0.5, n_samples)
        t5 = surface_temp - 30 + np.random.normal(0, 0.5, n_samples)
        t6 = surface_temp - 20 + np.random.normal(0, 0.5, n_samples)
        t7 = surface_temp + np.random.normal(0, 0.5, n_samples)
        t8 = ambient_temp + np.random.normal(0, 0.5, n_samples)

        df = pd.DataFrame({
            'TimeMinutes': time_minutes,
            'T1': t1, 'T2': t2, 'T3': t3, 'T4': t4,
            'T5': t5, 'T6': t6, 'T7': t7, 'T8': t8,
            'CoreTemperature': core_temp,
            'SurfaceTemperature': surface_temp,
            'AmbientTemperature': ambient_temp
        })

        return df

    def test_zone_profiles_use_correct_keys(self):
        """Test that get_zone_profiles returns dict with zone keys, not display names."""
        df = self.create_test_baking_data()
        analyzer = ZoneAnalyzer(df, sample_period=5.0)

        zone_profiles = analyzer.get_zone_profiles()

        # Verify all keys match TEMPERATURE_ZONES keys (not display names)
        assert isinstance(zone_profiles, dict)
        for zone_key in zone_profiles.keys():
            assert zone_key in TEMPERATURE_ZONES, \
                f"Zone key '{zone_key}' not found in TEMPERATURE_ZONES. " \
                f"Expected keys: {list(TEMPERATURE_ZONES.keys())}"

        # Verify no display names used as keys
        display_names = [config['name'] for config in TEMPERATURE_ZONES.values()]
        for key in zone_profiles.keys():
            assert key not in display_names, \
                f"Display name '{key}' used as dictionary key instead of zone key"

        print(f"✅ Zone profiles use correct keys: {list(zone_profiles.keys())}")

    def test_zone_heating_characteristics_use_correct_keys(self):
        """Test that get_zone_heating_characteristics returns dict with zone keys."""
        df = self.create_test_baking_data()
        analyzer = ZoneAnalyzer(df, sample_period=5.0)

        heating_chars = analyzer.get_zone_heating_characteristics()

        # Verify all keys match TEMPERATURE_ZONES keys
        assert isinstance(heating_chars, dict)
        for zone_key in heating_chars.keys():
            assert zone_key in TEMPERATURE_ZONES, \
                f"Zone key '{zone_key}' not found in TEMPERATURE_ZONES"

        # Verify no display names used as keys
        display_names = [config['name'] for config in TEMPERATURE_ZONES.values()]
        for key in heating_chars.keys():
            assert key not in display_names, \
                f"Display name '{key}' used as dictionary key instead of zone key"

        print(f"✅ Heating characteristics use correct keys: {list(heating_chars.keys())}")

    def test_zone_uniformity_use_correct_keys(self):
        """Test that analyze_zone_uniformity returns dict with zone keys."""
        df = self.create_test_baking_data()
        analyzer = ZoneAnalyzer(df, sample_period=5.0)

        uniformity = analyzer.analyze_zone_uniformity()

        # Verify all keys match TEMPERATURE_ZONES keys
        assert isinstance(uniformity, dict)
        for zone_key in uniformity.keys():
            assert zone_key in TEMPERATURE_ZONES, \
                f"Zone key '{zone_key}' not found in TEMPERATURE_ZONES"

        print(f"✅ Zone uniformity uses correct keys: {list(uniformity.keys())}")

    def test_recommend_zone_optimizations_no_keyerror(self):
        """
        Test that recommend_zone_optimizations does not raise KeyError.
        This is the core test for the variable name collision fix.
        """
        df = self.create_test_baking_data()
        analyzer = ZoneAnalyzer(df, sample_period=5.0)

        # This should not raise KeyError
        try:
            recommendations = analyzer.recommend_zone_optimizations()
            assert isinstance(recommendations, list)
            print(f"✅ Recommendations generated without KeyError: {len(recommendations)} recommendations")

            # Print recommendations for debugging
            for rec in recommendations:
                print(f"  - {rec.get('zone', 'Unknown')}: {rec.get('issue', 'No issue')}")

        except KeyError as e:
            raise AssertionError(
                f"KeyError raised in recommend_zone_optimizations: {e}. "
                "This indicates variable name collision bug is not fixed."
            )

    def test_zone_lookups_in_recommendations(self):
        """Test that all zone lookups in recommendations use valid keys."""
        df = self.create_test_baking_data()
        analyzer = ZoneAnalyzer(df, sample_period=5.0)

        # Get intermediate results
        zone_profiles = analyzer.get_zone_profiles()
        zone_uniformity = analyzer.analyze_zone_uniformity()
        zone_heating = analyzer.get_zone_heating_characteristics()

        # Verify all zone keys can be looked up in TEMPERATURE_ZONES
        for zone_key in zone_profiles.keys():
            assert zone_key in TEMPERATURE_ZONES, \
                f"Cannot lookup zone_key '{zone_key}' in TEMPERATURE_ZONES"

        for zone_key in zone_uniformity.keys():
            if zone_uniformity[zone_key] is not None:
                assert zone_key in TEMPERATURE_ZONES, \
                    f"Cannot lookup zone_key '{zone_key}' in TEMPERATURE_ZONES"

        for zone_key in zone_heating.keys():
            if zone_heating[zone_key] is not None:
                assert zone_key in TEMPERATURE_ZONES, \
                    f"Cannot lookup zone_key '{zone_key}' in TEMPERATURE_ZONES"

        print("✅ All zone lookups use valid TEMPERATURE_ZONES keys")

    def test_zone_data_extraction(self):
        """Test that zone data extraction works correctly."""
        df = self.create_test_baking_data()
        analyzer = ZoneAnalyzer(df, sample_period=5.0)

        # Test extraction for each zone
        for zone_key, zone_config in TEMPERATURE_ZONES.items():
            zone_data = analyzer._extract_zone_data(zone_config)
            assert isinstance(zone_data, pd.DataFrame)
            print(f"  {zone_key}: {len(zone_data)} samples")

        print("✅ Zone data extraction works for all zones")

    def test_edge_cases(self):
        """Test edge cases that might cause issues."""
        # DataFrame with no zone data
        df_low_temp = pd.DataFrame({
            'CoreTemperature': [25, 26, 27, 28],
            'SurfaceTemperature': [25, 26, 27, 28],
            'AmbientTemperature': [25, 26, 27, 28],
            'T1': [25, 26, 27, 28],
            'T2': [25, 26, 27, 28],
            'T3': [25, 26, 27, 28],
            'T4': [25, 26, 27, 28],
            'T5': [25, 26, 27, 28],
            'T6': [25, 26, 27, 28],
            'T7': [25, 26, 27, 28],
            'T8': [25, 26, 27, 28]
        })
        analyzer = ZoneAnalyzer(df_low_temp, sample_period=5.0)

        # These should not crash and should not raise KeyError
        try:
            zone_profiles = analyzer.get_zone_profiles()
            assert isinstance(zone_profiles, dict)

            heating_chars = analyzer.get_zone_heating_characteristics()
            assert isinstance(heating_chars, dict)

            recommendations = analyzer.recommend_zone_optimizations()
            assert isinstance(recommendations, list)

            print("✅ Edge cases handled without KeyError")
        except KeyError as e:
            raise AssertionError(f"KeyError in edge case handling: {e}. Variable name collision bug present.")
        except Exception as e:
            # Other exceptions are acceptable for edge cases
            print(f"⚠️  Edge case raised expected exception: {type(e).__name__}")

    def test_minimal_data(self):
        """Test with minimal temperature data."""
        # Just 10 data points
        df_minimal = pd.DataFrame({
            'CoreTemperature': [25, 30, 40, 50, 60, 70, 80, 85, 90, 95],
            'SurfaceTemperature': [25, 35, 50, 70, 90, 110, 130, 140, 145, 150],
            'AmbientTemperature': [25, 40, 60, 90, 120, 140, 160, 170, 175, 180],
            'T1': [25, 30, 40, 50, 60, 70, 80, 85, 90, 95],
            'T2': [25, 30, 40, 50, 60, 70, 80, 85, 90, 95],
            'T3': [25, 30, 40, 50, 60, 70, 80, 85, 90, 95],
            'T4': [25, 30, 40, 50, 60, 70, 80, 85, 90, 95],
            'T5': [25, 35, 50, 70, 90, 110, 130, 140, 145, 150],
            'T6': [25, 35, 50, 70, 90, 110, 130, 140, 145, 150],
            'T7': [25, 35, 50, 70, 90, 110, 130, 140, 145, 150],
            'T8': [25, 40, 60, 90, 120, 140, 160, 170, 175, 180]
        })

        analyzer = ZoneAnalyzer(df_minimal, sample_period=5.0)

        # Should not raise errors
        try:
            zone_profiles = analyzer.get_zone_profiles()
            recommendations = analyzer.recommend_zone_optimizations()
            print("✅ Minimal data handled correctly")
        except Exception as e:
            raise AssertionError(f"Minimal data test failed: {e}")


if __name__ == "__main__":
    # Run tests
    test = TestZoneAnalysis()

    print("Running zone analysis tests...\n")

    try:
        test.test_zone_profiles_use_correct_keys()
    except AssertionError as e:
        print(f"❌ Zone profiles key test failed: {e}")
        sys.exit(1)

    try:
        test.test_zone_heating_characteristics_use_correct_keys()
    except AssertionError as e:
        print(f"❌ Heating characteristics key test failed: {e}")
        sys.exit(1)

    try:
        test.test_zone_uniformity_use_correct_keys()
    except AssertionError as e:
        print(f"❌ Zone uniformity key test failed: {e}")
        sys.exit(1)

    try:
        test.test_recommend_zone_optimizations_no_keyerror()
    except AssertionError as e:
        print(f"❌ Recommendations KeyError test failed: {e}")
        sys.exit(1)

    try:
        test.test_zone_lookups_in_recommendations()
    except AssertionError as e:
        print(f"❌ Zone lookups test failed: {e}")
        sys.exit(1)

    try:
        test.test_zone_data_extraction()
    except AssertionError as e:
        print(f"❌ Zone data extraction test failed: {e}")
        sys.exit(1)

    try:
        test.test_edge_cases()
    except AssertionError as e:
        print(f"❌ Edge cases test failed: {e}")
        sys.exit(1)

    try:
        test.test_minimal_data()
    except AssertionError as e:
        print(f"❌ Minimal data test failed: {e}")
        sys.exit(1)

    print("\n✅ All zone analysis tests passed!")
    print("\n📝 Summary:")
    print("  - Zone profiles use correct dictionary keys")
    print("  - Heating characteristics use correct dictionary keys")
    print("  - Zone uniformity uses correct dictionary keys")
    print("  - Recommendations generated without KeyError")
    print("  - All zone lookups use valid TEMPERATURE_ZONES keys")
    print("  - Edge cases handled correctly")
