"""Surface- and lid-sensor annotation presence tests (M1a HMS Truculent).

Pin the schema for the new ``expected_surface_sensor`` and ``expected_lid_sensor``
fields on the real-CSV cases in
:mod:`tests.fixtures.curve_boundary_cases`.  Subsequent missions implementing
the unified role classifier will use these annotations as ground truth.

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


def _real_cases():
    return [c for c in CASES if c.get("source") == "real"]


def _lidded_cases():
    return [c for c in CASES if c.get("name") in _LIDDED_CASE_NAMES]


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
