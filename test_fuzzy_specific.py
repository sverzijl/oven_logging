"""Check fuzzy confidence at specific rows."""

import pandas as pd
from src.data.fuzzy_curve_detector import (
    FuzzyTemperatureClassifier,
    FuzzyGradientClassifier,
    FuzzyAmbientClassifier,
    FuzzyStabilityClassifier,
    FuzzyInferenceEngine
)

# Load CSV
df = pd.read_csv("ProbeData_1000B481_2025-09-19 14_31_39(in) (3).csv", skiprows=10)

# Calculate features
core_col = 'VirtualCoreTemperature'
ambient_col = 'VirtualAmbientTemperature'

df['temp_gradient'] = df[core_col].diff().fillna(0)
df['temp_smooth'] = df[core_col].rolling(window=5, center=True).mean().fillna(df[core_col])
df['temp_stability'] = df[core_col].rolling(window=10, center=True).std().fillna(0)

# Initialize classifiers
temp_min = df[core_col].min()
temp_max = df[core_col].max()
temp_classifier = FuzzyTemperatureClassifier(temp_min, temp_max)
grad_classifier = FuzzyGradientClassifier(5.0)
ambient_classifier = FuzzyAmbientClassifier()
stability_classifier = FuzzyStabilityClassifier()
inference_engine = FuzzyInferenceEngine()

# Check specific rows around oven entry
print("Checking rows around oven entry (962-980):\n")

for i in range(962, 981):
    temp = df.iloc[i][core_col]
    gradient = df.iloc[i]['temp_gradient']
    stability = df.iloc[i]['temp_stability']
    ambient = df.iloc[i][ambient_col]

    # Check for state change
    has_state_change = False
    if i > 0:
        prev_state = df.iloc[i-1].get('PredictionState', '')
        curr_state = df.iloc[i].get('PredictionState', '')
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

    state = df.iloc[i].get('PredictionState', 'N/A')

    print(f"Row {i}: conf={confidence:.2%}, core={temp:.1f}°C, grad={gradient:.3f}, ambient={ambient:.1f}°C, state={state}")

    if confidence > 0.5:
        top_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)[:3]
        print(f"  ✓ Top factors: {', '.join([f'{k}({v:.2%})' for k, v in top_factors])}")

        # Show classifications
        active_temp = {k: v for k, v in temp_class.items() if v > 0.1}
        active_grad = {k: v for k, v in grad_class.items() if v > 0.1}
        active_ambient = {k: v for k, v in ambient_class.items() if v > 0.1}

        print(f"  Temp classes: {active_temp}")
        print(f"  Grad classes: {active_grad}")
        print(f"  Ambient classes: {active_ambient}")
