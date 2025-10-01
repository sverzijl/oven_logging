"""
Test script for fuzzy logic curve detection.

This script loads a CSV file and tests both the classic and fuzzy detection methods,
comparing their results.
"""

import sys
import pandas as pd
from src.data.loader import ThermalProfileLoader
from config.constants import FUZZY_DETECTION_CONFIG


def test_fuzzy_detection(csv_path: str):
    """Test fuzzy detection on a CSV file."""
    print(f"{'='*80}")
    print(f"Testing Fuzzy Logic Curve Detection")
    print(f"{'='*80}")
    print(f"\nFile: {csv_path}")
    print(f"Fuzzy Detection: {'ENABLED' if FUZZY_DETECTION_CONFIG['USE_FUZZY_DETECTION'] else 'DISABLED'}")
    print(f"Confidence Threshold: {FUZZY_DETECTION_CONFIG['CONFIDENCE_THRESHOLD']:.2%}")
    print(f"{'='*80}\n")

    # Load data
    loader = ThermalProfileLoader()
    data, metadata = loader.load_csv(csv_path)

    # Get detected curves
    curves = loader.get_all_curves()

    if not curves:
        print("❌ No curves detected!")
        return

    print(f"\n{'='*80}")
    print(f"DETECTION RESULTS")
    print(f"{'='*80}\n")

    # Display results
    for idx, curve in enumerate(curves):
        print(f"Curve {idx + 1}:")
        print(f"  Duration: {curve['duration']:.1f} minutes")
        print(f"  Samples: {curve['samples']}")
        print(f"  Max Temperature: {curve['max_temp']:.1f}°C")
        print(f"  Detection Method: {curve.get('detection_method', 'classic')}")

        if 'start_confidence' in curve:
            print(f"  Start Confidence: {curve['start_confidence']:.2%}")
            print(f"  End Confidence: {curve['end_confidence']:.2%}")

            # Show contributing factors
            factors = curve.get('contributing_factors', {})
            if factors:
                start_factors = factors.get('start', {})
                end_factors = factors.get('end', {})

                if start_factors:
                    top_start = sorted(start_factors.items(), key=lambda x: x[1], reverse=True)[:3]
                    print(f"  Top Start Factors:")
                    for name, value in top_start:
                        print(f"    - {name}: {value:.2%}")

                if end_factors:
                    top_end = sorted(end_factors.items(), key=lambda x: x[1], reverse=True)[:3]
                    print(f"  Top End Factors:")
                    for name, value in top_end:
                        print(f"    - {name}: {value:.2%}")

        print()

    print(f"{'='*80}")
    print(f"Total curves detected: {len(curves)}")
    print(f"{'='*80}\n")


def compare_detection_methods(csv_path: str):
    """Compare classic vs fuzzy detection."""
    print(f"{'='*80}")
    print(f"COMPARING DETECTION METHODS")
    print(f"{'='*80}\n")

    # Test with fuzzy detection
    print("1. Testing with FUZZY DETECTION...\n")
    FUZZY_DETECTION_CONFIG['USE_FUZZY_DETECTION'] = True
    loader_fuzzy = ThermalProfileLoader()
    loader_fuzzy.load_csv(csv_path)
    curves_fuzzy = loader_fuzzy.get_all_curves()

    # Test with classic detection
    print("\n2. Testing with CLASSIC DETECTION...\n")
    FUZZY_DETECTION_CONFIG['USE_FUZZY_DETECTION'] = False
    loader_classic = ThermalProfileLoader()
    loader_classic.load_csv(csv_path)
    curves_classic = loader_classic.get_all_curves()

    # Re-enable fuzzy
    FUZZY_DETECTION_CONFIG['USE_FUZZY_DETECTION'] = True

    # Compare results
    print(f"\n{'='*80}")
    print(f"COMPARISON SUMMARY")
    print(f"{'='*80}\n")

    print(f"Fuzzy Detection:   {len(curves_fuzzy)} curve(s)")
    print(f"Classic Detection: {len(curves_classic)} curve(s)")

    if len(curves_fuzzy) == len(curves_classic):
        print(f"\n✅ Both methods detected the same number of curves")

        # Compare durations
        print(f"\nDuration Comparison:")
        for i in range(len(curves_fuzzy)):
            fuzzy_dur = curves_fuzzy[i]['duration']
            classic_dur = curves_classic[i]['duration']
            diff = fuzzy_dur - classic_dur
            diff_pct = (diff / classic_dur) * 100 if classic_dur > 0 else 0

            print(f"  Curve {i+1}:")
            print(f"    Fuzzy:   {fuzzy_dur:.1f} min")
            print(f"    Classic: {classic_dur:.1f} min")
            print(f"    Diff:    {diff:+.1f} min ({diff_pct:+.1f}%)")
    else:
        print(f"\n⚠️  Methods detected different numbers of curves!")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Use default test file
        csv_path = "ProbeData_1000B481_2025-09-19 14_31_39(in) (3).csv"
        print(f"No file specified, using default: {csv_path}\n")
    else:
        csv_path = sys.argv[1]

    # Run tests
    test_fuzzy_detection(csv_path)

    # Compare methods
    print("\n" * 2)
    compare_detection_methods(csv_path)
