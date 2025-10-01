"""Debug fuzzy detection to see what's happening."""

import pandas as pd
import numpy as np
from src.data.fuzzy_curve_detector import (
    FuzzyCurveDetector,
    FuzzyTemperatureClassifier,
    FuzzyGradientClassifier,
    FuzzyAmbientClassifier,
    FuzzyStabilityClassifier,
    FuzzyInferenceEngine
)

# Load CSV
print("Loading CSV...")
df = pd.read_csv("ProbeData_1000B481_2025-09-19 14_31_39(in) (3).csv", skiprows=10)

print(f"Loaded {len(df)} rows")
print(f"Temperature range: {df['T1'].min():.1f}°C to {df['T1'].max():.1f}°C\n")

# Create detector
detector = FuzzyCurveDetector(sample_period_ms=5000)

# Prepare data (minimal version of what detect_curves does)
core_col = 'VirtualCoreTemperature'
ambient_col = 'VirtualAmbientTemperature'

# Calculate features
print("Calculating features...")
df_features = df.copy()
df_features['temp_gradient'] = df[core_col].diff().fillna(0)
df_features['temp_smooth'] = df[core_col].rolling(window=5, center=True).mean().fillna(df[core_col])
df_features['temp_stability'] = df[core_col].rolling(window=10, center=True).std().fillna(0)
df_features['ambient_temp'] = df[ambient_col]

print(f"Gradient range: {df_features['temp_gradient'].min():.3f} to {df_features['temp_gradient'].max():.3f}°C/sample")
print(f"Stability range: {df_features['temp_stability'].min():.3f} to {df_features['temp_stability'].max():.3f}°C")

# Initialize classifiers
temp_min = df[core_col].min()
temp_max = df[core_col].max()
temp_classifier = FuzzyTemperatureClassifier(temp_min, temp_max)
grad_classifier = FuzzyGradientClassifier(5.0)
ambient_classifier = FuzzyAmbientClassifier()
stability_classifier = FuzzyStabilityClassifier()
inference_engine = FuzzyInferenceEngine()

# Scan through data looking for start signals
print("\nScanning for start signals (showing first 10 with confidence >0.5)...")
count = 0
for i in range(0, min(len(df_features), 1000)):
    temp = df_features.iloc[i]['temp_smooth']
    gradient = df_features.iloc[i]['temp_gradient']
    stability = df_features.iloc[i]['temp_stability']
    ambient = df_features.iloc[i]['ambient_temp']

    # Check for state change
    has_state_change = False
    if 'PredictionState' in df_features.columns and i > 0:
        prev_state = df_features.iloc[i-1]['PredictionState']
        curr_state = df_features.iloc[i]['PredictionState']
        has_state_change = (prev_state == 'Probe Not Inserted' and
                           curr_state != 'Probe Not Inserted')

    # Classify
    temp_class = temp_classifier.classify(temp)
    grad_class = grad_classifier.classify(gradient)
    ambient_class = ambient_classifier.classify(ambient)
    stability_class = stability_classifier.classify(stability)

    # Evaluate rules
    confidence, factors = inference_engine.evaluate_start_rules(
        temp_class, grad_class, ambient_class, stability_class, has_state_change
    )

    if confidence > 0.5:
        print(f"Row {i}: temp={temp:.1f}°C, grad={gradient:.3f}, ambient={ambient:.1f}°C")
        print(f"  Confidence: {confidence:.2%}")
        top_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)[:2]
        print(f"  Top factors: {', '.join([f'{k}({v:.2%})' for k, v in top_factors])}")
        count += 1
        if count >= 10:
            break

if count == 0:
    print("  No high-confidence start signals found in first 1000 rows")

# Check if there's a peak temperature
peak_idx = df[core_col].idxmax()
peak_temp = df[core_col].max()
print(f"\nPeak temperature: {peak_temp:.1f}°C at row {peak_idx}")

# Check data around peak
print(f"\nData around peak (rows {max(0, peak_idx-5)} to {min(len(df), peak_idx+5)}):")
for i in range(max(0, peak_idx-5), min(len(df), peak_idx+5)):
    temp = df.iloc[i][core_col]
    ambient = df.iloc[i][ambient_col]
    print(f"  Row {i}: core={temp:.1f}°C, ambient={ambient:.1f}°C")
