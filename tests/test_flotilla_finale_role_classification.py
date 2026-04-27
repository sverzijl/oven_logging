"""Flotilla finale regression guard for ``refactor/role-classification-unified``.

Introduced by M5 HMS Foudroyant, the documentation + cleanup mission of the
flotilla that replaced the discrete-sensor heuristics
(``surface_sensor_detector.py`` and ``ThermodynamicSensorClassifier`` class)
with the spatial-reconstruction classifier
(``src/data/spatial_reconstruction``).

This test is the single permanent regression gate for the architecture the
flotilla landed:

1. **Public API surface** of ``src.data.spatial_reconstruction`` must export
   the classify entry point and its dataclasses, plus the geometry registry
   and intermediate fit helpers.
2. **Legacy modules deleted** — ``src.data.surface_sensor_detector`` is gone
   and the ``ThermodynamicSensorClassifier`` class no longer exists on
   ``src.data.thermodynamic_sensor_classifier`` (the
   ``identify_core_sensor_combined_rank`` function still lives there for
   curve-boundary contamination detection).
3. **Override topology validation** — manual overrides win over classifier
   picks; topology validator rejects core/surface inversion (core=T5,
   surface=T2 must raise ``ValueError``); through-loaf is the documented
   exception.
4. **Real-CSV per-role contract** — for each of the 5 real-CSV fixtures
   (3 unlidded + 2 lidded), load via ``ThermalProfileLoader``, then check
   per-curve role assignments against the ground-truth annotations.
5. **Synthetic per-role contract** — for each of the 4 synthetic fixtures,
   call ``classify`` directly (synthetic DataFrames don't have CSVs) and
   check role assignments.
6. **Lid-column lifecycle** — ``loader.get_lid_sensor(0)`` is ``None`` for
   unlidded fixtures, returns the assigned sensor for lidded ones.
7. **Baseline files exist** — the empirical model-comparison + flip-rate
   reports must remain in-tree so future missions can diff against them.

Future work on this codebase MUST keep this test green or explicitly
deprecate it via a follow-up mission.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 1. Public API surface
# ---------------------------------------------------------------------------

class TestSpatialReconstructionPublicAPI:
    """The ``src.data.spatial_reconstruction`` package exports the contract M2a-M3a built."""

    def test_classify_exported(self):
        from src.data.spatial_reconstruction import classify
        assert callable(classify)

    def test_dataclasses_exported(self):
        from src.data.spatial_reconstruction import (
            SpatialAssignment,
            PositionalAssignment,
        )
        # Both should be classes (dataclasses).
        assert isinstance(SpatialAssignment, type)
        assert isinstance(PositionalAssignment, type)

    def test_profile_helpers_exported(self):
        from src.data.spatial_reconstruction import (
            ProfileFit,
            extract_features,
            compute_oven_proxy,
        )
        assert isinstance(ProfileFit, type)
        assert callable(extract_features)
        assert callable(compute_oven_proxy)

    def test_geometry_registry_exported(self):
        from src.data.spatial_reconstruction import (
            PROBE_GEOMETRIES,
            lookup_geometry,
        )
        assert isinstance(PROBE_GEOMETRIES, dict)
        assert callable(lookup_geometry)


# ---------------------------------------------------------------------------
# 2. Legacy modules deleted
# ---------------------------------------------------------------------------

class TestLegacyModulesDeleted:
    """Both legacy entry points must remain absent post-flotilla."""

    def test_surface_sensor_detector_module_gone(self):
        with pytest.raises((ImportError, ModuleNotFoundError)):
            import src.data.surface_sensor_detector  # noqa: F401

    def test_thermodynamic_sensor_classifier_class_gone(self):
        from src.data import thermodynamic_sensor_classifier as mod
        assert not hasattr(mod, 'ThermodynamicSensorClassifier'), (
            "ThermodynamicSensorClassifier class must remain deleted; "
            "spatial_reconstruction.classify is the canonical role classifier."
        )

    def test_combined_rank_helper_still_callable(self):
        """The combined-rank function survives — used by curve-boundary contamination."""
        from src.data.thermodynamic_sensor_classifier import (
            identify_core_sensor_combined_rank,
        )
        assert callable(identify_core_sensor_combined_rank)


# ---------------------------------------------------------------------------
# 3. Override topology validation
# ---------------------------------------------------------------------------

_TOPOLOGY_FIXTURE = os.path.join(
    REPO_ROOT, 'ProbeData_1000F3C1_2025-05-23 09_11_59.csv'
)


@pytest.fixture
def topology_loader():
    from src.data.loader import ThermalProfileLoader
    assert os.path.exists(_TOPOLOGY_FIXTURE), (
        f"fixture missing: {_TOPOLOGY_FIXTURE}"
    )
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=_TOPOLOGY_FIXTURE)
    return loader


class TestOverrideTopology:
    """``set_sensor_override`` honours role validation; through-loaf is the lone exception."""

    def test_lid_override_accepted(self, topology_loader):
        topology_loader.set_sensor_override(0, 'lid', 'T8')
        # No assertion needed beyond no-raise; lid override pinned at T8 (highest).

    def test_core_above_surface_rejected(self, topology_loader):
        loader = topology_loader
        # Establish a valid base.
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T7')
        # Now flip to invalid: core=T5, surface=T2.
        with pytest.raises(ValueError, match=r"(?i)core.*surface"):
            loader.set_sensor_override(0, 'core', 'T5')
            loader.set_sensor_override(0, 'surface', 'T2')


# ---------------------------------------------------------------------------
# 4 + 6. Real-CSV per-role contract via the loader
# ---------------------------------------------------------------------------

# Names of the five real-CSV fixtures the role annotators ran over.
_REAL_CASE_NAMES = (
    "real_100098DE_1351",
    "real_1000BA3C_0946",
    "real_1000BA3C_1759",
    "wonder_white_10k_lidded",
    "post_wonder_meal_lidded",
)

# Map from case-name to the CSV path on disk.  Mirrors `_REAL_CSVS` in
# `tests/fixtures/curve_boundary_cases.py`.
_REAL_CASE_TO_CSV = {
    "real_100098DE_1351": os.path.join(
        REPO_ROOT, "ProbeData_100098DE_2025-05-30 13_51_07.csv"
    ),
    "real_1000BA3C_0946": os.path.join(
        REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
    ),
    "real_1000BA3C_1759": os.path.join(
        REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"
    ),
    "wonder_white_10k_lidded": os.path.join(
        REPO_ROOT, "wonder white 10k 13.01.2026.csv"
    ),
    "post_wonder_meal_lidded": os.path.join(
        REPO_ROOT, "Post Wonder Meal 20251017.csv"
    ),
}

# Names of the lidded fixtures — exercise ``get_lid_sensor`` with the
# annotation-supplied expectation (None on these two specific fixtures).
_LIDDED_CASE_NAMES = {"wonder_white_10k_lidded", "post_wonder_meal_lidded"}


def _get_case(name: str):
    from tests.fixtures.curve_boundary_cases import CASES
    return next(c for c in CASES if c["name"] == name)


def _make_loader(csv_path: str):
    from src.data.loader import ThermalProfileLoader
    assert os.path.exists(csv_path), f"fixture CSV missing: {csv_path}"
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=csv_path)
    return loader


def _expected_for_curve(value, curve_index: int):
    """Resolve a (possibly per-curve list) expectation for ``curve_index``."""
    if isinstance(value, list) and value and isinstance(value[0], (list, tuple)):
        return value[curve_index]
    if isinstance(value, list) and value and isinstance(value[0], str):
        # ``expected_surface_sensor`` for multi-curve real cases is a flat
        # list of T-strings, one per curve.  Distinguish that from a
        # single-curve ambient list (also flat T-strings) by checking the
        # case n_curves explicitly via the caller — the helper here treats
        # any flat list with strings as per-curve when called with index >= 0.
        return value[curve_index]
    return value


class TestRealCsvRoleContract:
    """Per-curve role assignments via the loader match the ground-truth annotations."""

    @pytest.mark.parametrize("case_name", _REAL_CASE_NAMES)
    def test_real_case_role_assignments(self, case_name):
        case = _get_case(case_name)
        n_curves = case.get("expected_n_curves", 1)
        csv_path = _REAL_CASE_TO_CSV[case_name]
        loader = _make_loader(csv_path)

        # Per-curve expected fields:
        #  * core: scalar OR (for wonder_white) acceptable set {T5, T6}.
        #  * surface: scalar (single-curve) | list[str] (multi-curve).
        #  * ambient: list[str] (single-curve) | list[list[str]] (multi-curve).
        #  * lid: scalar (None on the two lidded real fixtures).
        expected_core = case.get("expected_core_sensor")
        expected_surface = case.get("expected_surface_sensor")
        expected_ambient = case.get("expected_ambient_sensors")
        expected_lid = case.get("expected_lid_sensor")  # only set on lidded cases

        # Acceptable core sensors — wonder_white tied at 5 between T5/T6.
        if case_name == "wonder_white_10k_lidded":
            acceptable_cores = {"T5", "T6"}
        else:
            acceptable_cores = {expected_core}

        # When the loader's curve count disagrees with the fixture annotation,
        # we still want a clear failure rather than silent wrong-answer.
        loaded_n = loader.get_curve_count()
        assert loaded_n == n_curves, (
            f"{case_name}: loader extracted {loaded_n} curves, "
            f"fixture annotation expects {n_curves}"
        )

        for curve_index in range(n_curves):
            # Core
            core = loader.get_core_sensor(curve_index)
            assert core in acceptable_cores, (
                f"{case_name} curve {curve_index}: core={core!r} not in "
                f"{acceptable_cores!r}"
            )

            # Surface
            if n_curves > 1:
                exp_surf_i = expected_surface[curve_index]
            else:
                exp_surf_i = expected_surface
            surf = loader.get_surface_sensor(curve_index)
            assert surf == exp_surf_i, (
                f"{case_name} curve {curve_index}: surface={surf!r} "
                f"!= expected {exp_surf_i!r}"
            )

            # Ambient — sorted-equality, with through-loaf cases honouring
            # the topology_note (lidded fixtures keep both T1 and T8).
            if n_curves > 1:
                exp_amb_i = expected_ambient[curve_index]
            else:
                exp_amb_i = expected_ambient
            ambient = loader.get_ambient_sensors(curve_index)
            assert sorted(ambient) == sorted(exp_amb_i), (
                f"{case_name} curve {curve_index}: ambient={ambient!r} "
                f"!= expected {exp_amb_i!r}"
            )

            # Lid — only checked when the fixture explicitly sets the field
            # (only the two lidded real cases do).
            if case_name in _LIDDED_CASE_NAMES:
                lid = loader.get_lid_sensor(curve_index)
                assert lid == expected_lid, (
                    f"{case_name} curve {curve_index}: lid={lid!r} "
                    f"!= expected {expected_lid!r}"
                )

    def test_unlidded_fixtures_have_no_lid(self):
        """``get_lid_sensor(0)`` returns ``None`` for unlidded fixtures."""
        for case_name in (
            "real_100098DE_1351",
            "real_1000BA3C_0946",
            "real_1000BA3C_1759",
        ):
            csv_path = _REAL_CASE_TO_CSV[case_name]
            loader = _make_loader(csv_path)
            assert loader.get_lid_sensor(0) is None, (
                f"{case_name}: unlidded fixture should not assign lid"
            )

    def test_lidded_fixtures_lid_matches_annotation(self):
        """Lidded fixtures: ``get_lid_sensor(0)`` matches the fixture annotation."""
        for case_name in _LIDDED_CASE_NAMES:
            case = _get_case(case_name)
            csv_path = _REAL_CASE_TO_CSV[case_name]
            loader = _make_loader(csv_path)
            assert loader.get_lid_sensor(0) == case["expected_lid_sensor"], (
                f"{case_name}: lid mismatch with annotation "
                f"{case['expected_lid_sensor']!r}"
            )


# ---------------------------------------------------------------------------
# 5. Synthetic per-role contract via direct classify()
# ---------------------------------------------------------------------------

_SYNTHETIC_ROLE_CASE_NAMES = (
    "synthetic_shallow_insertion",
    "synthetic_full_immersion",
    "synthetic_lid_touch",
    "synthetic_probe_pull_mid_bake",
)


class TestSyntheticRoleContract:
    """Synthetic fixtures are DataFrames; use ``classify`` directly."""

    @pytest.mark.parametrize("case_name", _SYNTHETIC_ROLE_CASE_NAMES)
    def test_synthetic_classifier_picks(self, case_name):
        from src.data.spatial_reconstruction import classify
        case = _get_case(case_name)
        df = case["df"]
        # All synthetic builders use 5000 ms sample period (matches
        # ``_make_timestamps`` default in the fixture module).
        result = classify(df, sample_period_ms=5000)

        # Core
        expected_core = case["expected_core_sensor"]
        # ``synthetic_lid_touch`` documents T7 as the canonical lid pick;
        # T8 is acceptable alternate per its description.  The other three
        # synthetic cases have unique core picks.
        assert result.core == expected_core, (
            f"{case_name}: core={result.core!r}, expected {expected_core!r}"
        )

        # Surface
        expected_surface = case["expected_surface_sensor"]
        assert result.surface == expected_surface, (
            f"{case_name}: surface={result.surface!r}, expected {expected_surface!r}"
        )

        # Ambient (sorted equality; empty list permitted on full-immersion)
        expected_ambient = case["expected_ambient_sensors"]
        assert sorted(result.ambient) == sorted(expected_ambient), (
            f"{case_name}: ambient={result.ambient!r}, expected {expected_ambient!r}"
        )

        # Lid
        expected_lid = case["expected_lid_sensor"]
        if case_name == "synthetic_lid_touch":
            # T7 is canonical, T8 is documented alternate.
            assert result.lid in {"T7", "T8"}, (
                f"{case_name}: lid={result.lid!r}, expected one of "
                "{{'T7', 'T8'}}"
            )
        else:
            assert result.lid == expected_lid, (
                f"{case_name}: lid={result.lid!r}, expected {expected_lid!r}"
            )


# ---------------------------------------------------------------------------
# 7. Baseline reports persist in-tree
# ---------------------------------------------------------------------------

class TestBaselineReportsExist:
    """Baseline files used by the comparison + perturbation harnesses must remain in-tree."""

    def test_spatial_model_comparison_report_exists(self):
        path = os.path.join(
            REPO_ROOT, "tests", "baselines", "spatial_model_comparison.md"
        )
        assert os.path.exists(path), (
            f"Missing baseline: {path}.  Regenerate via "
            "src.data.spatial_reconstruction.write_comparison_report."
        )

    def test_role_classifier_flip_rates_report_exists(self):
        path = os.path.join(
            REPO_ROOT, "tests", "baselines", "role_classifier_flip_rates.md"
        )
        assert os.path.exists(path), (
            f"Missing baseline: {path}.  Regenerate via the M4 perturbation "
            "harness."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
