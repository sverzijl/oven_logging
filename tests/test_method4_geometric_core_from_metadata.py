"""Method 4: bake metadata + geometric core (M18 HMS Vigilant).

When the operator provides loaf-thickness and probe-insertion-depth metadata,
the classifier can compute the *geometric* core position from physical
geometry alone — no inverse problem, no thermal extrapolation.

Geometric formula:
    geometric_core_depth_below_top = loaf_thickness_mm / 2
    position_below_probe_tip       = insertion_depth_mm - geometric_core_depth_below_top

A positive ``position_below_probe_tip`` means the geometric core is *past*
the probe tip (deeper into the loaf than T1 reaches); a negative value
means the geometric core is *above* the probe tip (i.e. between T1 and the
loaf's top crust).

These tests pin the loader's bake-metadata API and the geometric override
behaviour BEFORE either exists (TDD failing-first).
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO = pathlib.Path(__file__).resolve().parents[1]
SINGLE_CURVE_CSV = REPO / "ProbeData_1000F3C1_2025-05-23 09_11_59.csv"


def _make_loader():
    from src.data.loader import ThermalProfileLoader

    loader = ThermalProfileLoader()
    loader.load_csv(str(SINGLE_CURVE_CSV))
    return loader


# ---------------------------------------------------------------------------
# Loader API surface for bake metadata
# ---------------------------------------------------------------------------


class TestBakeMetadataLoaderAPI:
    def test_set_and_get_bake_metadata_round_trip(self):
        loader = _make_loader()
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 100.0,
            "insertion_depth_mm": 70.0,
            "oven_setpoint_C": 230.0,
            "lid_state": "tin",
            "steam_phase_minutes": 5.0,
        })
        meta = loader.get_bake_metadata(0)
        assert meta["loaf_thickness_mm"] == pytest.approx(100.0)
        assert meta["insertion_depth_mm"] == pytest.approx(70.0)
        assert meta["oven_setpoint_C"] == pytest.approx(230.0)
        assert meta["lid_state"] == "tin"
        assert meta["steam_phase_minutes"] == pytest.approx(5.0)

    def test_get_bake_metadata_default_is_empty_dict(self):
        loader = _make_loader()
        meta = loader.get_bake_metadata(0)
        assert meta == {}

    def test_clear_bake_metadata(self):
        loader = _make_loader()
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 100.0,
            "insertion_depth_mm": 70.0,
        })
        loader.clear_bake_metadata(0)
        assert loader.get_bake_metadata(0) == {}


# ---------------------------------------------------------------------------
# Geometric core computation
# ---------------------------------------------------------------------------


class TestGeometricCorePosition:
    def test_geometric_core_past_tip(self):
        """loaf_thickness=100 mm, insertion_depth=70 mm
        → geometric core depth below top = 50 mm
        → position below probe tip      = 70 - 50 = +20 mm (past tip).
        """
        loader = _make_loader()
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 100.0,
            "insertion_depth_mm": 70.0,
        })
        position_mm = loader.get_geometric_core_position_mm_from_tip(0)
        assert position_mm == pytest.approx(20.0)

    def test_geometric_core_above_tip(self):
        """loaf_thickness=120 mm, insertion_depth=30 mm
        → geometric core depth below top = 60 mm
        → position below probe tip      = 30 - 60 = -30 mm (above tip).
        """
        loader = _make_loader()
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 120.0,
            "insertion_depth_mm": 30.0,
        })
        position_mm = loader.get_geometric_core_position_mm_from_tip(0)
        assert position_mm == pytest.approx(-30.0)

    def test_geometric_core_when_metadata_partial_returns_none(self):
        """Only one of (thickness, depth) → cannot compute → None."""
        loader = _make_loader()
        loader.set_bake_metadata(0, {"loaf_thickness_mm": 100.0})
        assert loader.get_geometric_core_position_mm_from_tip(0) is None
        loader.clear_bake_metadata(0)
        loader.set_bake_metadata(0, {"insertion_depth_mm": 50.0})
        assert loader.get_geometric_core_position_mm_from_tip(0) is None

    def test_geometric_core_when_metadata_absent_returns_none(self):
        loader = _make_loader()
        assert loader.get_geometric_core_position_mm_from_tip(0) is None


# ---------------------------------------------------------------------------
# Integration: classifier output reflects geometric core when metadata set
# ---------------------------------------------------------------------------


class TestGeometricCoreOverridesClassifier:
    def test_get_core_temperature_series_reflects_geometry(self):
        """When metadata is set with the geometric core falling between T1
        and T2, ``get_core_temperature_series`` returns a series that is a
        non-trivial blend of T1 and T2 — proving the geometric position
        engaged spatial interpolation rather than snapping to T1.
        """
        loader = _make_loader()
        df = loader.all_curves[0]["data"]
        # Probe 8-sensor span = 95 mm, so 95/7 ≈ 13.571 mm/step. Half-step
        # is ~6.79 mm. Pick metadata that lands the geometric core ~6.79 mm
        # past T1 (i.e. halfway between T1 and T2).
        # geometric_core_depth_below_top = loaf_thickness/2
        # We want position_below_probe_tip = +6.79 mm
        # ⇒ insertion_depth - loaf_thickness/2 = 6.79
        # Pick loaf_thickness=100 mm ⇒ insertion_depth = 56.79 mm
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 100.0,
            "insertion_depth_mm": 56.79,
        })
        series = loader.get_core_temperature_series(0)
        assert series is not None
        # Mean of geometric core series should differ from both T1's mean
        # and T2's mean (it's a half-and-half blend).
        t1_mean = float(df["T1"].mean())
        t2_mean = float(df["T2"].mean())
        core_mean = float(series.mean())
        assert abs(core_mean - t1_mean) > 0.1, (
            "Geometric series at +6.79 mm past tip must not coincide with T1 "
            f"(t1_mean={t1_mean:.3f}, core_mean={core_mean:.3f})"
        )
        assert abs(core_mean - t2_mean) > 0.1, (
            "Geometric series at +6.79 mm past tip must not coincide with T2 "
            f"(t2_mean={t2_mean:.3f}, core_mean={core_mean:.3f})"
        )

    def test_clear_bake_metadata_reverts_to_classifier(self):
        """After clearing metadata, ``get_core_temperature_series`` must
        revert to the classifier's interpolated series (NOT the geometric
        series)."""
        loader = _make_loader()
        loader.set_bake_metadata(0, {
            "loaf_thickness_mm": 100.0,
            "insertion_depth_mm": 56.79,
        })
        with_meta = loader.get_core_temperature_series(0)
        loader.clear_bake_metadata(0)
        without_meta = loader.get_core_temperature_series(0)
        # Two series mean values differ → metadata path actually overrode.
        assert abs(float(with_meta.mean()) - float(without_meta.mean())) > 0.01, (
            "Clearing metadata should change the returned core series."
        )

    def test_partial_metadata_does_not_override_classifier(self):
        """When only one of the two required fields is present, the
        classifier path is taken (geometric formula is unavailable)."""
        loader = _make_loader()
        baseline = loader.get_core_temperature_series(0)
        loader.set_bake_metadata(0, {"loaf_thickness_mm": 100.0})
        with_partial = loader.get_core_temperature_series(0)
        # Means must match — partial metadata cannot trigger geometric path.
        assert abs(float(baseline.mean()) - float(with_partial.mean())) < 1e-9


# ---------------------------------------------------------------------------
# Sidebar widget-key ghost test (parity with M3b override-keys)
# ---------------------------------------------------------------------------


class TestSidebarBakeMetadataWidgetKeys:
    """Per-(filename, curve_idx) widget keys must scope each metadata field.

    The sidebar pattern (mirrored from M3b sensor overrides) prevents a
    metadata value entered for one CSV from ghosting into the same field on
    another CSV.
    """

    def test_widget_key_format_includes_filename_and_curve_idx(self):
        # Same shape as M3b's override keys: f"<field>_{file_key}_{curve_idx}".
        file_key = "myfile_csv"
        curve_idx = 2
        expected_keys = {
            f"loaf_thickness_{file_key}_{curve_idx}",
            f"insertion_depth_{file_key}_{curve_idx}",
            f"oven_setpoint_{file_key}_{curve_idx}",
            f"lid_state_{file_key}_{curve_idx}",
            f"steam_minutes_{file_key}_{curve_idx}",
            f"apply_metadata_{file_key}_{curve_idx}",
        }
        # Read sidebar.py and assert each expected literal appears in the
        # widget-key set (the format string is what we want to pin).
        sidebar_path = REPO / "sidebar.py"
        sidebar_text = sidebar_path.read_text(encoding="utf-8")
        for k in [
            "loaf_thickness_",
            "insertion_depth_",
            "oven_setpoint_",
            "lid_state_",
            "steam_minutes_",
            "apply_metadata_",
        ]:
            assert k in sidebar_text, (
                f"Sidebar must use widget key prefix {k!r} for the bake "
                "metadata expander."
            )
        # The {file_key}_{curve_idx} suffix pattern is the same as overrides.
        assert "f\"loaf_thickness_{file_key}_{curve_idx}\"" in sidebar_text or (
            "loaf_thickness_{file_key}_{curve_idx}" in sidebar_text
        ), "Bake metadata widget keys must include both filename and curve_idx scoping."
