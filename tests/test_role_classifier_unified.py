"""Surface-, lid-, and ambient-sensor annotation presence tests + classifier contract.

M1a HMS Truculent landed surface and lid annotations on the real-CSV cases.
M1b HMS Pelican (this file) extends the schema with ``expected_ambient_sensors``
on real-CSV cases, four new synthetic role-classification fixtures, and a
failing-on-main contract test for ``src.data.spatial_reconstruction.classifier``
(which M2a HMS Indefatigable will satisfy).

Contract
--------
* Every real-CSV case has ``expected_surface_sensor`` set to a string in
  ``{'T1', ..., 'T8'}``.  For multi-curve real cases the value is a
  ``list[str]`` with one entry per curve (length must equal
  ``expected_n_curves``).
* The two known lidded real cases (``wonder_white_10k_lidded`` and
  ``post_wonder_meal_lidded``) carry an ``expected_lid_sensor`` key whose value
  is either a member of the T1..T8 set or explicitly ``None`` (some lidded
  bakes do not contact any sensor against the lid).
* Every real-CSV case has ``expected_ambient_sensors`` set to a list of
  T1..T8 strings (single-curve) or a list-of-lists (multi-curve).  An empty
  list ``[]`` is permitted when no sensor is canonically in the cavity air
  (e.g. lidded cases where every sensor reads near the cavity proxy).
* Four synthetic role cases (``synthetic_shallow_insertion``,
  ``synthetic_full_immersion``, ``synthetic_lid_touch``,
  ``synthetic_probe_pull_mid_bake``) carry the full role schema:
  ``expected_core_sensor``, ``expected_surface_sensor``,
  ``expected_ambient_sensors``, ``expected_lid_sensor``,
  ``expected_x_dough_air_normalised``.
* ``TestClassifierReturnsExpectedRoles`` is the contract M2a will satisfy —
  it imports ``src.data.spatial_reconstruction.classifier.classify`` (which
  does not exist on main) and is therefore expected to FAIL on main with a
  clear ``ImportError`` per parametrized case.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402

_VALID_SENSORS = {f"T{i}" for i in range(1, 9)}

# Case names that correspond to the six real CSV fixture entries the
# annotator was run over.  ``real_1000BA3C_1759`` is multi-curve (3 bakes);
# its surface annotation is therefore a per-curve list.
_REAL_CASE_NAMES = {
    "real_100098DE_1351",
    "real_1000BA3C_0946",
    "real_1000BA3C_1759",
    "wonder_white_10k_lidded",
    "post_wonder_meal_lidded",
}

_LIDDED_CASE_NAMES = {
    "wonder_white_10k_lidded",
    "post_wonder_meal_lidded",
}

# Synthetic cases added by M1b that carry the full role-classification schema.
_SYNTHETIC_ROLE_CASE_NAMES = [
    "synthetic_shallow_insertion",
    "synthetic_full_immersion",
    "synthetic_lid_touch",
    "synthetic_probe_pull_mid_bake",
]


def _real_cases():
    return [c for c in CASES if c.get("source") == "real"]


def _lidded_cases():
    return [c for c in CASES if c.get("name") in _LIDDED_CASE_NAMES]


def _synthetic_role_cases():
    return [c for c in CASES if c.get("name") in _SYNTHETIC_ROLE_CASE_NAMES]


class TestSurfaceAnnotationPresent:
    """Schema-shape contract for ``expected_surface_sensor``."""

    @pytest.mark.parametrize("case", _real_cases(), ids=lambda c: c["name"])
    def test_surface_annotation_present(self, case):
        assert "expected_surface_sensor" in case, (
            f"{case['name']}: real-CSV case missing 'expected_surface_sensor'"
        )

        value = case["expected_surface_sensor"]
        n_curves = case["expected_n_curves"]

        if n_curves > 1:
            assert isinstance(value, list), (
                f"{case['name']}: multi-curve case must use a list of length "
                f"{n_curves} for expected_surface_sensor, got {type(value).__name__}"
            )
            assert len(value) == n_curves, (
                f"{case['name']}: expected_surface_sensor length {len(value)} "
                f"!= expected_n_curves {n_curves}"
            )
            for i, sensor in enumerate(value):
                assert sensor in _VALID_SENSORS, (
                    f"{case['name']} curve {i}: expected_surface_sensor "
                    f"{sensor!r} not in T1..T8"
                )
        else:
            assert value in _VALID_SENSORS, (
                f"{case['name']}: expected_surface_sensor {value!r} not in T1..T8"
            )


class TestLidAnnotationPresent:
    """Schema-shape contract for ``expected_lid_sensor`` on lidded cases."""

    @pytest.mark.parametrize("case", _lidded_cases(), ids=lambda c: c["name"])
    def test_lid_annotation_present(self, case):
        assert "expected_lid_sensor" in case, (
            f"{case['name']}: lidded case missing 'expected_lid_sensor' key"
        )

        value = case["expected_lid_sensor"]
        # Lidded bakes may have no sensor against the lid — explicit None is OK.
        assert value is None or value in _VALID_SENSORS, (
            f"{case['name']}: expected_lid_sensor {value!r} must be None or "
            f"a member of T1..T8"
        )


class TestAmbientAnnotationPresent:
    """Schema-shape contract for ``expected_ambient_sensors`` on real-CSV cases.

    The field is a list of T1..T8 strings for single-curve cases, or a
    list-of-lists for multi-curve cases (one inner list per curve, length
    equals ``expected_n_curves``). An empty list is permitted (some lidded
    cases have no sensor canonically in the cavity air).
    """

    @pytest.mark.parametrize("case", _real_cases(), ids=lambda c: c["name"])
    def test_ambient_annotation_present(self, case):
        assert "expected_ambient_sensors" in case, (
            f"{case['name']}: real-CSV case missing 'expected_ambient_sensors'"
        )

        value = case["expected_ambient_sensors"]
        n_curves = case["expected_n_curves"]

        assert isinstance(value, list), (
            f"{case['name']}: expected_ambient_sensors must be a list, got "
            f"{type(value).__name__}"
        )

        if n_curves > 1:
            assert len(value) == n_curves, (
                f"{case['name']}: expected_ambient_sensors length {len(value)} "
                f"!= expected_n_curves {n_curves}"
            )
            for i, inner in enumerate(value):
                assert isinstance(inner, list), (
                    f"{case['name']} curve {i}: per-curve ambient list must be "
                    f"a list, got {type(inner).__name__}"
                )
                for sensor in inner:
                    assert sensor in _VALID_SENSORS, (
                        f"{case['name']} curve {i}: ambient sensor {sensor!r} "
                        f"not in T1..T8"
                    )
        else:
            for sensor in value:
                assert sensor in _VALID_SENSORS, (
                    f"{case['name']}: ambient sensor {sensor!r} not in T1..T8"
                )


class TestSyntheticAnnotations:
    """Per-case schema check on the four synthetic role-classification fixtures.

    Each synthetic fixture must declare the four expected_* role keys
    (core, surface, ambient, lid) plus expected_x_dough_air_normalised. A
    None value is permitted on full-immersion (no surface, no interface) and
    on cases with no lid contact.
    """

    @pytest.mark.parametrize("case_name", _SYNTHETIC_ROLE_CASE_NAMES)
    def test_synthetic_has_role_annotations(self, case_name):
        case = next((c for c in CASES if c["name"] == case_name), None)
        assert case is not None, (
            f"Synthetic role case {case_name!r} not found in CASES registry"
        )

        # All four role keys must be present (value may be None).
        for key in (
            "expected_core_sensor",
            "expected_surface_sensor",
            "expected_ambient_sensors",
            "expected_lid_sensor",
            "expected_x_dough_air_normalised",
        ):
            assert key in case, f"{case_name}: missing {key!r}"

        # Type checks.
        core = case["expected_core_sensor"]
        assert core is None or core in _VALID_SENSORS, (
            f"{case_name}: expected_core_sensor {core!r} not in T1..T8 or None"
        )

        surface = case["expected_surface_sensor"]
        assert surface is None or surface in _VALID_SENSORS, (
            f"{case_name}: expected_surface_sensor {surface!r} not in T1..T8 "
            f"or None"
        )

        ambient = case["expected_ambient_sensors"]
        assert isinstance(ambient, list), (
            f"{case_name}: expected_ambient_sensors must be list, got "
            f"{type(ambient).__name__}"
        )
        for sensor in ambient:
            assert sensor in _VALID_SENSORS, (
                f"{case_name}: ambient sensor {sensor!r} not in T1..T8"
            )

        lid = case["expected_lid_sensor"]
        assert lid is None or lid in _VALID_SENSORS, (
            f"{case_name}: expected_lid_sensor {lid!r} not in T1..T8 or None"
        )

        x = case["expected_x_dough_air_normalised"]
        assert x is None or (isinstance(x, (int, float)) and 0.0 <= x <= 1.0), (
            f"{case_name}: expected_x_dough_air_normalised {x!r} must be None "
            f"or a float in [0.0, 1.0]"
        )


class TestClassifierReturnsExpectedRoles:
    """Failing-on-main contract — satisfied by M2a HMS Indefatigable.

    Imports ``src.data.spatial_reconstruction.classifier.classify`` which
    does not exist yet. Every parametrized case is expected to FAIL with
    ``ImportError`` (or ``AttributeError`` if the module exists but the
    function is missing). Once M2a lands the piecewise classifier, this
    test will start passing.

    Per-test-body import pattern is used so each parametrized case fails
    individually — gives M2a a per-case progress bar.
    """

    @pytest.mark.parametrize(
        "case",
        _real_cases() + _synthetic_role_cases(),
        ids=lambda c: c["name"],
    )
    def test_classifier_returns_expected_roles(self, case):
        # Import inside the test body so each parametrized case fails
        # with its own ImportError until M2a lands the module.
        from src.data.spatial_reconstruction.classifier import classify  # noqa: F401

        df = case["df"]
        # Sample period: real CSVs are 5000 ms = 5 s; synthetic builders also
        # use period=5.0 s (matching existing ``_make_timestamps`` default).
        sample_period_ms = 5000

        result = classify(df, sample_period_ms=sample_period_ms)

        # Result is expected to expose .core / .surface / .ambient / .lid
        # attributes (or dict keys) — exact API is M2a's call. We just check
        # the values match the fixture annotations.
        n_curves = case.get("expected_n_curves", 1)

        if n_curves > 1:
            # Multi-curve case: result is expected to be a list of per-curve
            # role assignments. Each entry has the role attributes.
            assert len(result) == n_curves, (
                f"{case['name']}: classifier returned {len(result)} curves, "
                f"expected {n_curves}"
            )
            expected_surface = case["expected_surface_sensor"]
            expected_ambient = case["expected_ambient_sensors"]
            for i, per_curve in enumerate(result):
                assert per_curve.surface == expected_surface[i]
                assert sorted(per_curve.ambient) == sorted(expected_ambient[i])
        else:
            assert result.core == case["expected_core_sensor"]
            assert result.surface == case["expected_surface_sensor"]
            assert sorted(result.ambient) == sorted(case["expected_ambient_sensors"])
            assert result.lid == case["expected_lid_sensor"]
