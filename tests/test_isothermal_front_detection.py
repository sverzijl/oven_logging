"""Front-detection correctness pin tests for ``_find_isotherm_position``
(fix/deep-review, the #16 fix).

The old implementation assumed the highest-x sensor is the hottest and the
profile is monotone decreasing toward the core. On an INVERTED / non-monotonic
profile (e.g. Wonder full-crumb, where the probe-tip sensor T1 is hottest and
the spatial profile is a shallow U) it short-circuited:

* ``temps[surface_end] < target`` -> NaN (even when the target IS bracketed
  elsewhere in the array), and
* ``min(temps) > target`` -> snap to 0.0 (reporting a front at the probe tip
  that is not actually there).

The corrected contract: scan EVERY adjacent (position-ordered) sensor pair for
a bracket ``min(t0,t1) <= target <= max(t0,t1)`` and linearly interpolate
(the same pattern ``piecewise._crossing_position`` uses). Return NaN when no
pair brackets the target -- never snap to 0.0. When several crossings exist,
pick the one nearest the surface (highest x).
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from src.data.spatial_reconstruction.isothermal import (  # noqa: E402
    _find_isotherm_position,
    track_isothermal,
)

POS8 = np.array([i / 7.0 for i in range(8)], dtype=float)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WONDER_CSV = os.path.join(REPO_ROOT, "wonder white 10k 13.01.2026.csv")
_BA3C_CSV = os.path.join(
    REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
)


class TestInvertedProfile:
    """Inverted / non-monotonic profile: probe-tip (x=0) hottest, shallow U."""

    def test_inverted_not_bracketed_returns_nan_not_zero(self):
        # All sensors above target on an inverted profile: the OLD code's
        # min(temps) > target snap-to-0.0 path would (wrongly) report 0.0.
        # Genuinely unbracketed (every sensor >= 60) -> must be NaN.
        temps = np.array([100.2, 98.3, 97.9, 97.8, 97.5, 97.7, 98.1, 99.3])
        # 60 C is below every sensor -> not bracketed -> NaN (NOT 0.0).
        assert np.isnan(_find_isotherm_position(POS8, temps, 60.0))
        # 80 C likewise below every sensor -> NaN.
        assert np.isnan(_find_isotherm_position(POS8, temps, 80.0))

    def test_inverted_above_all_returns_nan(self):
        # 100 C front above all sensors (max 99.3) -> not bracketed -> NaN.
        temps = np.array([100.2, 98.3, 97.9, 97.8, 97.5, 97.7, 98.1, 99.3])
        # 100 is above all but T1=100.2; 100 IS bracketed between T1=100.2 and
        # T2=98.3 (descending). So this should be ~near x=0 region, finite.
        r = _find_isotherm_position(POS8, temps, 100.0)
        assert np.isfinite(r)
        # And 101 C is above every sensor -> NaN.
        assert np.isnan(_find_isotherm_position(POS8, temps, 101.0))

    def test_inverted_u_shape_bracket_found(self):
        # U-shape (Wonder mid-bake): hot at both ends, cold in the middle.
        # T1=88.8 (x=0) ... T5=46.5 (cold) ... T8=75.2 (x=1).
        temps = np.array([88.8, 74.2, 62.2, 52.5, 46.5, 48.4, 58.5, 75.2])
        # 60 C is bracketed twice: once on the descending left limb (between
        # T3=62.2 and T4=52.5) and once on the ascending right limb (between
        # T7=58.5 and T8=75.2). The documented rule picks the crossing nearest
        # the surface (highest x) -> the right-limb crossing.
        r = _find_isotherm_position(POS8, temps, 60.0)
        assert np.isfinite(r)
        # Right-limb crossing lies between T7 (x=6/7=0.857) and T8 (x=1.0).
        assert r > 6.0 / 7.0
        # 60 between 58.5 and 75.2: frac = (60-58.5)/(75.2-58.5)=0.0898
        expected = 6.0 / 7.0 + 0.0898 * (1.0 - 6.0 / 7.0)
        assert abs(r - expected) < 1e-3


class TestThroughLoafTwoFronts:
    """Through-loaf: two 80 C crossings; pick the one nearest the surface."""

    def test_two_crossings_pick_highest_x(self):
        # High-low-high: T1=120 (air), descend to T4=60 (dough core), rise to
        # T8=130 (air). The 100 C front is bracketed on both limbs.
        temps = np.array([120.0, 95.0, 75.0, 60.0, 70.0, 90.0, 110.0, 130.0])
        r = _find_isotherm_position(POS8, temps, 100.0)
        assert np.isfinite(r)
        # Right limb crossing between T6=90 (x=5/7) and T7=110 (x=6/7) is the
        # highest-x crossing; should be chosen over the left-limb one.
        assert r > 4.0 / 7.0


class TestExactOnTip:
    """Target sits exactly on a sensor."""

    def test_exact_on_sensor_descending(self):
        # Monotone descending toward core; 100 C exactly on T5 (x=4/7).
        temps = np.array([40.0, 55.0, 70.0, 85.0, 100.0, 115.0, 130.0, 145.0])
        r = _find_isotherm_position(POS8, temps, 100.0)
        assert abs(r - 4.0 / 7.0) < 1e-6

    def test_exact_on_probe_tip(self):
        # T1 (probe tip, x=0) sits exactly on target; monotone increasing
        # toward surface. The crossing should resolve at x=0.
        temps = np.array([100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0])
        r = _find_isotherm_position(POS8, temps, 100.0)
        assert abs(r - 0.0) < 1e-6


class TestCanonicalMonotone:
    """Canonical monotone-increasing-toward-surface profile still works."""

    def test_monotone_increasing_middle_target(self):
        # T1=20 (core) ... T8=150 (surface). 100 C between T5=90 and T6=110.
        temps = np.array([20.0, 35.0, 50.0, 70.0, 90.0, 110.0, 130.0, 150.0])
        r = _find_isotherm_position(POS8, temps, 100.0)
        # Between x=4/7 and x=5/7, halfway (110-100)/(110-90)=0.5.
        expected = 4.5 / 7.0
        assert abs(r - expected) < 1e-6

    def test_below_all_returns_nan(self):
        temps = np.array([30.0, 32.0, 35.0, 38.0, 42.0, 47.0, 53.0, 60.0])
        assert np.isnan(_find_isotherm_position(POS8, temps, 100.0))

    def test_nan_sensor_dropped(self):
        # A NaN sensor mid-array must be dropped, not break the scan.
        temps = np.array([20.0, 35.0, np.nan, 70.0, 90.0, 110.0, 130.0, 150.0])
        r = _find_isotherm_position(POS8, temps, 100.0)
        assert np.isfinite(r)
        assert abs(r - 4.5 / 7.0) < 1e-6


# ---------------------------------------------------------------------------
# Real-CSV integration: the corrected detector must NOT fabricate x=0.0
# positions, and the moisture front (100/110 C) on the full-crumb Wonder bake
# must be (essentially) absent rather than mis-located at the probe tip.
# ---------------------------------------------------------------------------


class TestRealWonderInverted:

    @pytest.fixture(scope="class")
    def wonder_tracked(self):
        pytest.importorskip("scipy")
        if not os.path.exists(_WONDER_CSV):
            pytest.skip(f"fixture missing: {_WONDER_CSV}")
        from src.data.loader import ThermalProfileLoader

        loader = ThermalProfileLoader()
        loader.load_csv(file_path=_WONDER_CSV)
        df = loader.all_curves[0]["data"]
        return track_isothermal(df, sample_period_ms=5000)

    def test_110c_never_bracketed_is_nan_not_zero(self, wonder_tracked):
        # Wonder crumb tops out ~100 C; 110 C is never reached by any sensor,
        # so the 110 C front must be entirely NaN — NOT a fabricated x=0.0.
        raw = wonder_tracked.isotherm_positions_raw[110.0]
        assert np.isfinite(raw).sum() == 0, (
            "110 C front should never be located on the full-crumb Wonder bake"
        )

    def test_no_front_is_fabricated_at_probe_tip_when_unbracketed(self, wonder_tracked):
        # The OLD bug snapped under-target fronts to exactly x=0.0. After the
        # fix, any finite position must correspond to a genuine bracket — there
        # must be no run of fronts pinned at exactly 0.0 across the whole bake
        # for an isotherm that is otherwise unbracketed (110 C).
        raw110 = wonder_tracked.isotherm_positions_raw[110.0]
        assert not np.any(raw110 == 0.0), "110 C must not be snapped to x=0.0"

    def test_100c_front_is_degenerate_on_full_crumb(self, wonder_tracked):
        # The 100 C moisture/Stefan front barely exists on Wonder (only the
        # probe-tip T1 grazes 100 C). It must be near-absent — far fewer points
        # than a real advancing front, and not a sustained inward sweep.
        raw100 = wonder_tracked.isotherm_positions_raw[100.0]
        n_fin = int(np.isfinite(raw100).sum())
        assert n_fin <= 8, (
            f"100 C front should be near-absent on full-crumb Wonder; got {n_fin} pts"
        )


class TestWonderNoTeleportNoOutOfLoaf:
    """RESIDUAL #2b — on the full-crumb Wonder bake the "pick highest-x
    crossing" rule (a) teleported the 60/80 C front from the hot probe-tip limb
    to the cool surface the instant the surface sensor grazed the target, and
    (b) reported positions OUTSIDE the classifier's ``fixed_surface_x`` (a front
    located outside the loaf). The fix enforces front CONTINUITY across strides
    (pick the crossing nearest the previous stride's position, seeded from the
    surface-most in-bounds crossing), so the 60/80 C fronts stay continuous and
    in-bounds.
    """

    @pytest.fixture(scope="class")
    def wonder_tracked(self):
        pytest.importorskip("scipy")
        if not os.path.exists(_WONDER_CSV):
            pytest.skip(f"fixture missing: {_WONDER_CSV}")
        from src.data.loader import ThermalProfileLoader

        loader = ThermalProfileLoader()
        loader.load_csv(file_path=_WONDER_CSV)
        df = loader.all_curves[0]["data"]
        return track_isothermal(df, sample_period_ms=5000)

    def test_60c_no_teleport_and_in_bounds(self, wonder_tracked):
        raw = wonder_tracked.isotherm_positions_raw[60.0]
        surf = wonder_tracked.fixed_surface_x
        finite = raw[np.isfinite(raw)]
        assert finite.size > 0
        # (a) No finite position beyond the inferred surface.
        assert np.all(finite <= surf + 1e-6), (
            f"60 C front escaped the loaf: max={finite.max():.3f} > "
            f"fixed_surface_x={surf:.3f}"
        )
        # (b) No discontinuous single-stride jump (the teleport was ~0.86).
        diffs = np.abs(np.diff(raw))
        max_jump = float(np.nanmax(diffs[np.isfinite(diffs)])) if np.any(np.isfinite(diffs)) else 0.0
        assert max_jump <= 0.5, f"60 C front teleported: max single-stride jump {max_jump:.3f}"

    def test_80c_no_teleport_and_in_bounds(self, wonder_tracked):
        raw = wonder_tracked.isotherm_positions_raw[80.0]
        surf = wonder_tracked.fixed_surface_x
        finite = raw[np.isfinite(raw)]
        assert finite.size > 0
        assert np.all(finite <= surf + 1e-6), (
            f"80 C front escaped the loaf: max={finite.max():.3f} > "
            f"fixed_surface_x={surf:.3f}"
        )
        diffs = np.abs(np.diff(raw))
        max_jump = float(np.nanmax(diffs[np.isfinite(diffs)])) if np.any(np.isfinite(diffs)) else 0.0
        assert max_jump <= 0.5, f"80 C front teleported: max single-stride jump {max_jump:.3f}"


class TestRealBA3CMonotoneInward:

    def test_100c_front_advances_monotone_inward(self):
        pytest.importorskip("scipy")
        if not os.path.exists(_BA3C_CSV):
            pytest.skip(f"fixture missing: {_BA3C_CSV}")
        from src.data.loader import ThermalProfileLoader

        loader = ThermalProfileLoader()
        loader.load_csv(file_path=_BA3C_CSV)
        df = loader.all_curves[0]["data"]
        result = track_isothermal(df, sample_period_ms=5000)
        front = result.isotherm_positions[100.0]
        valid = front[np.isfinite(front)]
        assert valid.size >= 20
        n = valid.size
        head = float(np.mean(valid[: max(1, n // 5)]))
        tail = float(np.mean(valid[-max(1, n // 5):]))
        # Head near the surface (~0.9), tail well inward (~0.6); strictly
        # inward overall.
        assert head > 0.85, f"head should start near the surface; got {head:.3f}"
        assert tail < 0.65, f"tail should advance inward; got {tail:.3f}"
        assert tail < head, f"100 C front must advance inward: head={head:.3f} tail={tail:.3f}"
