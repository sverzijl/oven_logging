"""Test fuzzy detection with lower confidence threshold."""

import pandas as pd
from src.data.fuzzy_curve_detector import detect_curves_fuzzy

# Load CSV
df = pd.read_csv("ProbeData_1000B481_2025-09-19 14_31_39(in) (3).csv", skiprows=10)

print("Testing fuzzy detection with different confidence thresholds:\n")

for threshold in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65]:
    results = detect_curves_fuzzy(
        df,
        sample_period_ms=5000,
        min_duration=60,
        min_peak_temp=80.0,
        confidence_threshold=threshold
    )

    print(f"Threshold {threshold:.2%}: Found {len(results)} curve(s)")

    if results:
        for i, result in enumerate(results):
            duration = (result.end_idx - result.start_idx) * 5 / 60
            print(f"  Curve {i+1}: rows {result.start_idx}-{result.end_idx}, "
                  f"duration={duration:.1f}min, "
                  f"start_conf={result.start_confidence:.2%}, "
                  f"end_conf={result.end_confidence:.2%}")
