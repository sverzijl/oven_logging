# Admiral Addendum to M2b HMS Vanguard Captain's Log

**Action taken after Vanguard's report**: Admiral applied the annotation reconciliation Vanguard recommended.

## Reconciled annotations (`tests/fixtures/curve_boundary_cases.py`)

`post_wonder_meal_lidded` updated to match `wonder_white_10k_lidded` convention:

| Field | M1a/M1b annotation | M2b reconciled value |
|---|---|---|
| `expected_surface_sensor` | `"T8"` (first air-side) | `"T7"` (last dough-side at Stefan front) |
| `expected_ambient_sensors` | `["T1"]` | `["T1", "T8"]` |

Rationale recorded in code comments. Justifications:
1. Both lidded fixtures are physically identical (lid-suppressed, through-loaf insertion).
2. Both piecewise and Stefan classifiers independently converge on `surface=T7`, `ambient=["T1","T8"]` for both fixtures.
3. The annotation conflict was at the convention layer — air-side vs dough-side — and the dough-side convention (Stefan-front-anchored) is the more physically defensible choice.

## Result

`tests/test_role_classifier_unified.py::TestClassifierReturnsExpectedRoles`: 9/9 pass (up from 8/9 before reconciliation). Per-role:

| Role | Piecewise | Stefan |
|---|---:|---:|
| core | 9/9 | 9/9 |
| surface | 9/9 | 9/9 (now consistent across both lidded fixtures) |
| ambient | 9/9 | 8/9 (Stefan still misclassifies ambient on `real_100098DE_1351` due to T6 terminal=100.4 °C crossing the strict 100 °C pin — documented in comparison report) |
| lid | 9/9 | 9/9 |

## Decision rationale

The user's plan endorsed *physically defensible* over *convenient*. Reconciling to the Stefan-front-anchored convention puts both lidded fixtures in alignment with what *both* models compute and removes a per-fixture annotation inconsistency that would have polluted M4 perturbation analysis.

The unilateral admiral edit is bounded: only the annotation values change; the reasoning comments preserve a record of the M1a Truculent original choice and the M2b empirical motivation for the change. Easy to revert if the user disagrees.
