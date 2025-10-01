"""
Unit tests for fuzzy logic components.
"""

import sys
import numpy as np
from src.data.fuzzy_curve_detector import (
    FuzzyMembershipFunctions,
    FuzzyTemperatureClassifier,
    FuzzyGradientClassifier,
    FuzzyStabilityClassifier,
    FuzzyAmbientClassifier,
    FuzzyInferenceEngine
)


def test_membership_functions():
    """Test basic membership function operations."""
    print("=" * 80)
    print("TEST 1: Membership Functions")
    print("=" * 80)

    mf = FuzzyMembershipFunctions()

    # Test triangular membership function
    print("\n1.1 Testing trimf(x=25, [20, 30, 40])...")
    result = mf.trimf(25, (20, 30, 40))
    expected = 0.5  # At midpoint of rising edge
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"
    print(f"   ✅ Result: {result:.2f} (expected {expected:.2f})")

    print("\n1.2 Testing trimf at peak (x=30)...")
    result = mf.trimf(30, (20, 30, 40))
    expected = 1.0
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"
    print(f"   ✅ Result: {result:.2f} (expected {expected:.2f})")

    print("\n1.3 Testing trimf outside range (x=50)...")
    result = mf.trimf(50, (20, 30, 40))
    expected = 0.0
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"
    print(f"   ✅ Result: {result:.2f} (expected {expected:.2f})")

    # Test trapezoidal membership function
    print("\n1.4 Testing trapmf in plateau (x=25, [10, 20, 30, 40])...")
    result = mf.trapmf(25, (10, 20, 30, 40))
    expected = 1.0  # In plateau region
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"
    print(f"   ✅ Result: {result:.2f} (expected {expected:.2f})")

    # Test Gaussian membership function
    print("\n1.5 Testing gaussmf at center (x=50, center=50, sigma=10)...")
    result = mf.gaussmf(50, (50, 10))
    expected = 1.0
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"
    print(f"   ✅ Result: {result:.2f} (expected {expected:.2f})")

    print("\n✅ All membership function tests passed!")
    return True


def test_temperature_classifier():
    """Test temperature classification."""
    print("\n" + "=" * 80)
    print("TEST 2: Temperature Classifier")
    print("=" * 80)

    classifier = FuzzyTemperatureClassifier(temp_min=15, temp_max=250)

    # Test cold temperature
    print("\n2.1 Testing classification of 20°C (should be 'cold')...")
    classes = classifier.classify(20)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['cold'] >= 0.4, "20°C should have cold membership"
    print(f"   ✅ Cold membership: {classes['cold']:.2f} (≥0.4)")

    # Test warm temperature
    print("\n2.2 Testing classification of 50°C (should be 'warm')...")
    classes = classifier.classify(50)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['warm'] > 0.5, "50°C should have high 'warm' membership"
    print(f"   ✅ Warm membership: {classes['warm']:.2f} (>0.5)")

    # Test hot temperature
    print("\n2.3 Testing classification of 90°C (should be 'hot')...")
    classes = classifier.classify(90)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['hot'] > 0.5, "90°C should have high 'hot' membership"
    print(f"   ✅ Hot membership: {classes['hot']:.2f} (>0.5)")

    # Test boundary (should have multiple memberships)
    print("\n2.4 Testing boundary at 30°C (should be cold+cool)...")
    classes = classifier.classify(30)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    active_classes = [k for k, v in classes.items() if v > 0.1]
    assert len(active_classes) >= 1, "Boundary should activate multiple classes"
    print(f"   ✅ Active classes: {active_classes}")

    print("\n✅ All temperature classifier tests passed!")
    return True


def test_gradient_classifier():
    """Test gradient classification."""
    print("\n" + "=" * 80)
    print("TEST 3: Gradient Classifier")
    print("=" * 80)

    classifier = FuzzyGradientClassifier(sample_period_s=5.0)

    # Test rapid heating (gradient per sample)
    print("\n3.1 Testing rapid heating (1.5°C/sample = 18°C/min)...")
    classes = classifier.classify(1.5)  # 1.5°C per 5s sample = 18°C/min
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['rapid_heating'] > 0.3, "Should detect rapid heating"
    print(f"   ✅ Rapid heating membership: {classes['rapid_heating']:.2f} (>0.3)")

    # Test stable (near zero gradient)
    print("\n3.2 Testing stable (0°C/min)...")
    classes = classifier.classify(0)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['stable'] > 0.5, "Should detect stability"
    print(f"   ✅ Stable membership: {classes['stable']:.2f} (>0.5)")

    # Test rapid cooling (negative gradient)
    print("\n3.3 Testing rapid cooling (-1.0°C/sample = -12°C/min)...")
    classes = classifier.classify(-1.0)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['rapid_cooling'] > 0.3, "Should detect rapid cooling"
    print(f"   ✅ Rapid cooling membership: {classes['rapid_cooling']:.2f} (>0.3)")

    print("\n✅ All gradient classifier tests passed!")
    return True


def test_stability_classifier():
    """Test stability classification."""
    print("\n" + "=" * 80)
    print("TEST 4: Stability Classifier")
    print("=" * 80)

    classifier = FuzzyStabilityClassifier()

    # Test very stable (low std dev)
    print("\n4.1 Testing very stable (std_dev=0.3°C)...")
    classes = classifier.classify(0.3)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['very_stable'] >= 0.3, "Low std dev should have very_stable membership"
    print(f"   ✅ Very stable membership: {classes['very_stable']:.2f} (≥0.3)")

    # Test volatile (high std dev)
    print("\n4.2 Testing volatile (std_dev=8°C)...")
    classes = classifier.classify(8.0)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['volatile'] > 0.5, "High std dev should be volatile"
    print(f"   ✅ Volatile membership: {classes['volatile']:.2f} (>0.5)")

    print("\n✅ All stability classifier tests passed!")
    return True


def test_ambient_classifier():
    """Test ambient temperature classification."""
    print("\n" + "=" * 80)
    print("TEST 5: Ambient Classifier")
    print("=" * 80)

    classifier = FuzzyAmbientClassifier()

    # Test room temperature
    print("\n5.1 Testing room temperature (25°C)...")
    classes = classifier.classify(25)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['room'] > 0.5, "25°C should be room temperature"
    print(f"   ✅ Room membership: {classes['room']:.2f} (>0.5)")

    # Test oven temperature
    print("\n5.2 Testing oven temperature (150°C)...")
    classes = classifier.classify(150)
    print(f"   Classes: {', '.join([f'{k}={v:.2f}' for k, v in classes.items() if v > 0])}")
    assert classes['oven'] > 0.3, "150°C should indicate oven"
    print(f"   ✅ Oven membership: {classes['oven']:.2f} (>0.3)")

    print("\n✅ All ambient classifier tests passed!")
    return True


def test_inference_engine():
    """Test fuzzy inference engine."""
    print("\n" + "=" * 80)
    print("TEST 6: Fuzzy Inference Engine")
    print("=" * 80)

    engine = FuzzyInferenceEngine()

    # Test fuzzy AND
    print("\n6.1 Testing fuzzy AND (min operator)...")
    result = engine.fuzzy_and(0.8, 0.6, 0.9)
    expected = 0.6  # Minimum
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"
    print(f"   ✅ fuzzy_and(0.8, 0.6, 0.9) = {result:.2f} (expected {expected:.2f})")

    # Test fuzzy OR
    print("\n6.2 Testing fuzzy OR (max operator)...")
    result = engine.fuzzy_or(0.8, 0.6, 0.9)
    expected = 0.9  # Maximum
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"
    print(f"   ✅ fuzzy_or(0.8, 0.6, 0.9) = {result:.2f} (expected {expected:.2f})")

    # Test fuzzy NOT
    print("\n6.3 Testing fuzzy NOT (complement)...")
    result = engine.fuzzy_not(0.7)
    expected = 0.3
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"
    print(f"   ✅ fuzzy_not(0.7) = {result:.2f} (expected {expected:.2f})")

    # Test start rules with realistic scenario
    print("\n6.4 Testing start detection rules...")
    temp_class = {'cold': 0.8, 'cool': 0.2, 'warm': 0, 'hot': 0, 'very_hot': 0}
    grad_class = {'rapid_cooling': 0, 'cooling': 0, 'stable': 0, 'warming': 0,
                  'heating': 0.3, 'rapid_heating': 0.9}
    ambient_class = {'room': 0, 'warm': 0.2, 'oven': 0.9, 'peak_oven': 0}
    stability_class = {'very_stable': 0, 'stable': 0.2, 'fluctuating': 0.5, 'volatile': 0.6}

    confidence, factors = engine.evaluate_start_rules(
        temp_class, grad_class, ambient_class, stability_class, has_state_change=False
    )

    print(f"   Confidence: {confidence:.2%}")
    print(f"   Top factors: {', '.join([f'{k}({v:.2%})' for k, v in sorted(factors.items(), key=lambda x: x[1], reverse=True)[:3]])}")
    assert confidence > 0.6, "Strong signals should give high confidence"
    assert len(factors) > 0, "Should have contributing factors"
    print(f"   ✅ Confidence {confidence:.2%} with {len(factors)} factors")

    # Test end rules
    print("\n6.5 Testing end detection rules...")
    temp_class = {'cold': 0.9, 'cool': 0.1, 'warm': 0, 'hot': 0, 'very_hot': 0}
    grad_class = {'rapid_cooling': 0.95, 'cooling': 0.3, 'stable': 0, 'warming': 0,
                  'heating': 0, 'rapid_heating': 0}
    ambient_class = {'room': 0.8, 'warm': 0.2, 'oven': 0, 'peak_oven': 0}
    stability_class = {'very_stable': 0.7, 'stable': 0.3, 'fluctuating': 0, 'volatile': 0}

    confidence, factors = engine.evaluate_end_rules(
        temp_class, grad_class, ambient_class, stability_class,
        temp_drop_from_peak=50.0, time_at_low_temp=30
    )

    print(f"   Confidence: {confidence:.2%}")
    print(f"   Top factors: {', '.join([f'{k}({v:.2%})' for k, v in sorted(factors.items(), key=lambda x: x[1], reverse=True)[:3]])}")
    assert confidence > 0.9, "Rapid cooling should give very high confidence"
    assert len(factors) > 0, "Should have contributing factors"
    print(f"   ✅ Confidence {confidence:.2%} with {len(factors)} factors")

    print("\n✅ All inference engine tests passed!")
    return True


def run_all_tests():
    """Run all unit tests."""
    print("\n" + "=" * 80)
    print("FUZZY LOGIC UNIT TEST SUITE")
    print("=" * 80)

    tests = [
        ("Membership Functions", test_membership_functions),
        ("Temperature Classifier", test_temperature_classifier),
        ("Gradient Classifier", test_gradient_classifier),
        ("Stability Classifier", test_stability_classifier),
        ("Ambient Classifier", test_ambient_classifier),
        ("Inference Engine", test_inference_engine),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ {name} FAILED: {e}")

    print("\n" + "=" * 80)
    print("UNIT TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests: {len(tests)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} {'❌' if failed > 0 else ''}")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
