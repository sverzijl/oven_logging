"""Test UI helper functions for fuzzy detection display."""

# Test helper functions
def format_contributing_factors(factors_dict, top_n=3):
    """Format contributing factors for display in UI."""
    if not factors_dict:
        return []
    sorted_factors = sorted(factors_dict.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return sorted_factors

def get_confidence_color(confidence):
    """Get color for confidence score."""
    if confidence >= 0.90:
        return "green"
    elif confidence >= 0.75:
        return "blue"
    elif confidence >= 0.65:
        return "normal"
    else:
        return "orange"

def get_confidence_label(confidence):
    """Get label for confidence score."""
    if confidence >= 0.90:
        return "Excellent"
    elif confidence >= 0.75:
        return "Good"
    elif confidence >= 0.65:
        return "Acceptable"
    else:
        return "Low (Fallback)"

# Test the functions
print("Testing UI Helper Functions")
print("=" * 60)

# Test format_contributing_factors
test_factors = {
    'ambient_oven_transition': 0.92,
    'cold_rapid_oven': 0.87,
    'warm_heating_oven': 0.72,
    'sustained_heating': 0.45,
    'cool_warming_volatile': 0.30
}

print("\n1. Testing format_contributing_factors:")
print(f"   Input: {test_factors}")
top_3 = format_contributing_factors(test_factors, top_n=3)
print(f"   Top 3: {top_3}")
assert len(top_3) == 3, "Should return 3 factors"
assert top_3[0][0] == 'ambient_oven_transition', "Should be sorted by value"
assert top_3[0][1] == 0.92, "Should have correct value"
print("   ✅ PASSED")

# Test get_confidence_color
print("\n2. Testing get_confidence_color:")
test_cases = [
    (0.95, "green", "Excellent confidence"),
    (0.82, "blue", "Good confidence"),
    (0.68, "normal", "Acceptable confidence"),
    (0.45, "orange", "Low confidence")
]
for conf, expected_color, desc in test_cases:
    color = get_confidence_color(conf)
    print(f"   {conf:.0%} -> {color} ({desc})")
    assert color == expected_color, f"Expected {expected_color}, got {color}"
print("   ✅ PASSED")

# Test get_confidence_label
print("\n3. Testing get_confidence_label:")
test_cases = [
    (0.95, "Excellent"),
    (0.82, "Good"),
    (0.68, "Acceptable"),
    (0.45, "Low (Fallback)")
]
for conf, expected_label in test_cases:
    label = get_confidence_label(conf)
    print(f"   {conf:.0%} -> {label}")
    assert label == expected_label, f"Expected {expected_label}, got {label}"
print("   ✅ PASSED")

print("\n" + "=" * 60)
print("✅ All UI helper function tests passed!")
print("=" * 60)
