"""Loader-integration tests for the memoised isothermal assignment (M30).

``ThermalProfileLoader.isothermal_assignment(curve_index)`` caches the
:class:`IsothermalAssignment` per curve because ``track_isothermal`` runs the
full-bake classifier (~1-2 s) and the Streamlit UI re-renders on every
unrelated widget change. The cache must:

* return the SAME object on consecutive calls (warm path is cheap);
* be invalidated for a curve when its sensor overrides change;
* be cleared wholesale when the curve list is re-indexed (boundary / manual
  curve / expected-duration mutations).

These run the real classifier on the canonical single-bake CSV, so they are
slower than pure-helper tests.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader  # noqa: E402
from src.data.spatial_reconstruction import IsothermalAssignment  # noqa: E402


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BA3C_0946_CSV = os.path.join(
    REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
)


@pytest.fixture()
def loader():
    pytest.importorskip("scipy")
    if not os.path.exists(_BA3C_0946_CSV):
        pytest.skip(f"fixture missing: {_BA3C_0946_CSV}")
    ldr = ThermalProfileLoader()
    ldr.load_csv(file_path=_BA3C_0946_CSV)
    assert ldr.all_curves, "BA3C_0946 must yield at least one curve"
    return ldr


class TestIsothermalAssignmentCache:

    def test_returns_well_formed_assignment(self, loader):
        result = loader.isothermal_assignment(0)
        assert isinstance(result, IsothermalAssignment)
        assert result.isotherm_temps_C == (60.0, 80.0, 100.0, 110.0)

    def test_cached_across_calls_same_identity(self, loader):
        first = loader.isothermal_assignment(0)
        second = loader.isothermal_assignment(0)
        assert first is second, "second call must hit the cache (same object)"

    def test_warm_path_is_cheap(self, loader):
        loader.isothermal_assignment(0)  # cold — populates cache
        t0 = time.perf_counter()
        loader.isothermal_assignment(0)  # warm
        warm_s = time.perf_counter() - t0
        assert warm_s < 0.25, f"warm cache path took {warm_s:.3f}s (cache miss?)"

    def test_defaults_to_current_curve(self, loader):
        loader.current_curve_index = 0
        explicit = loader.isothermal_assignment(0)
        implicit = loader.isothermal_assignment()  # current curve
        assert explicit is implicit

    def test_invalidated_on_override(self, loader):
        first = loader.isothermal_assignment(0)
        # core='T1' is the lowest-x pick — always topology-valid (core_idx=0).
        loader.set_sensor_override(0, "core", "T1")
        second = loader.isothermal_assignment(0)
        assert second is not first, "override must invalidate the cached entry"
        assert isinstance(second, IsothermalAssignment)

    def test_invalidated_on_clear_overrides(self, loader):
        loader.set_sensor_override(0, "core", "T1")
        first = loader.isothermal_assignment(0)
        loader.clear_sensor_overrides(0)
        second = loader.isothermal_assignment(0)
        assert second is not first

    def test_invalidated_on_boundary_change(self, loader):
        first = loader.isothermal_assignment(0)
        n = len(loader.raw_data)
        # Pin a wide slice well inside the raw log.
        loader.set_curve_boundaries(0, 1, n - 2)
        second = loader.isothermal_assignment(0)
        assert second is not first, "boundary change must clear the cache"
