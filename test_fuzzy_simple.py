"""Simple direct test of fuzzy detection."""

import pandas as pd
from src.data.fuzzy_curve_detector import detect_curves_fuzzy

# Load CSV
print("Loading CSV...")
df = pd.read_csv("ProbeData_1000B481_2025-09-19 14_31_39(in) (3).csv", skiprows=10)

print(f"Loaded {len(df)} rows")
print(f"Columns: {list(df.columns)}")
print(f"Temperature range: {df['T1'].min():.1f}°C to {df['T1'].max():.1f}°C")

# Run fuzzy detection
print("\nRunning fuzzy detection...")
try:
    results = detect_curves_fuzzy(
        df,
        sample_period_ms=5000,
        min_duration=60,
        min_peak_temp=80.0,
        confidence_threshold=0.65
    )

    print(f"\n✅ Fuzzy detection succeeded!")
    print(f"Found {len(results)} curve(s)")

    for i, result in enumerate(results):
        print(f"\nCurve {i+1}:")
        print(f"  Start index: {result.start_idx}")
        print(f"  End index: {result.end_idx}")
        print(f"  Duration: {(result.end_idx - result.start_idx) * 5 / 60:.1f} minutes")
        print(f"  Peak temp: {result.peak_temp:.1f}°C")
        print(f"  Start confidence: {result.start_confidence:.2%}")
        print(f"  End confidence: {result.end_confidence:.2%}")
        print(f"  Detection method: {result.detection_method}")

        # Show contributing factors
        if result.contributing_factors:
            start_factors = result.contributing_factors.get('start', {})
            end_factors = result.contributing_factors.get('end', {})

            if start_factors:
                top_start = sorted(start_factors.items(), key=lambda x: x[1], reverse=True)[:3]
                print(f"  Top start factors:")
                for name, value in top_start:
                    print(f"    - {name}: {value:.2%}")

            if end_factors:
                top_end = sorted(end_factors.items(), key=lambda x: x[1], reverse=True)[:3]
                print(f"  Top end factors:")
                for name, value in top_end:
                    print(f"    - {name}: {value:.2%}")

except Exception as e:
    print(f"\n❌ Fuzzy detection failed:")
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
