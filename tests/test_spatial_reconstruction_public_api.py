"""Pin the public API of the spatial_reconstruction package (M27).

After the research-only inverse-problem purge, the package exports the live
classifier + the M24 isothermal tracker, and NO LONGER exports the archived
``classify_temporal`` / ``TemporalAssignment`` (superseded by
``track_isothermal`` / ``IsothermalAssignment``). This test pins ``__all__``
so a regression (re-adding a dead export, or dropping a live one) fails loudly.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.data.spatial_reconstruction as sr  # noqa: E402


EXPECTED_PRESENT = {
    "classify",
    "SpatialAssignment",
    "PositionalAssignment",
    "ProfileFit",
    "extract_features",
    "compute_oven_proxy",
    "PROBE_GEOMETRIES",
    "lookup_geometry",
    "fit_piecewise",
    "fit_stefan",
    "track_isothermal",
    "IsothermalAssignment",
    "ModelComparison",
    "benchmark_fixture",
    "benchmark_all_cases",
    "write_comparison_report",
}

# Archived (moved to research/) — must not be on the runtime package surface.
EXPECTED_ABSENT = {"classify_temporal", "TemporalAssignment"}


class TestSpatialReconstructionPublicAPI:

    def test_all_contains_expected(self):
        missing = EXPECTED_PRESENT - set(sr.__all__)
        assert not missing, f"__all__ is missing live exports: {missing}"

    def test_all_excludes_archived(self):
        leaked = EXPECTED_ABSENT & set(sr.__all__)
        assert not leaked, f"__all__ still exports archived names: {leaked}"

    def test_every_exported_name_is_importable(self):
        for name in sr.__all__:
            assert hasattr(sr, name), f"__all__ lists {name!r} but it is not importable"

    def test_isothermal_api_importable(self):
        from src.data.spatial_reconstruction import (  # noqa: F401
            track_isothermal,
            IsothermalAssignment,
        )
        assert callable(track_isothermal)

    def test_archived_temporal_not_on_package(self):
        for name in EXPECTED_ABSENT:
            assert not hasattr(sr, name), (
                f"{name!r} is still importable from the package; it should be "
                "archived under research/"
            )

    def test_dead_inverse_modules_are_gone(self):
        import importlib

        for mod in (
            "heat_equation",
            "luikov",
            "luikov_tin",
            "luikov_tin_observed",
            "luikov_dirichlet_hybrid",
            "stefan_inverse",
            "stefan_inverse_v2",
            "stefan_inverse_v3",
            "zurcher",
            "temporal",
        ):
            try:
                importlib.import_module(
                    f"src.data.spatial_reconstruction.{mod}"
                )
            except ModuleNotFoundError:
                continue
            else:
                raise AssertionError(
                    f"src.data.spatial_reconstruction.{mod} still exists; "
                    "it should be deleted (or archived for temporal)."
                )
