"""Pin tests for the sidebar Bake Metadata status line (M29).

``bake_metadata_status_line(loader, curve_idx)`` returns
``(active_model, detail)`` declaring which model feeds the current core
trace. Every returned ``active_model`` must have a render kind in
``STATUS_RENDER_KIND``.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader  # noqa: E402
from src.ui.core_confidence_banner import (  # noqa: E402
    STATUS_RENDER_KIND,
    bake_metadata_status_line,
)

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
    assert ldr.all_curves
    return ldr


class TestBakeMetadataStatusLine:

    def test_manual_override(self, loader):
        loader.set_sensor_override(0, "core", "T1")
        model, detail = bake_metadata_status_line(loader, 0)
        assert model == "manual_override"
        assert detail

    def test_method_4_in_probe(self, loader):
        loader.set_bake_metadata(
            0, {"loaf_thickness_mm": 120.0, "insertion_depth_mm": 70.0}
        )
        model, detail = bake_metadata_status_line(loader, 0)
        assert model == "method_4"
        assert "geometric core" in detail.lower()

    def test_method_4_degraded(self, loader):
        loader.set_bake_metadata(
            0, {"loaf_thickness_mm": 120.0, "insertion_depth_mm": 20.0}
        )
        model, detail = bake_metadata_status_line(loader, 0)
        assert model == "method_4_degraded"
        assert "below probe tip" in detail.lower()

    def test_classifier_branch(self, loader):
        model, detail = bake_metadata_status_line(loader, 0)
        assert model in {"method_1_high", "method_1_medium", "method_1_low"}
        assert detail

    def test_fallback(self, loader):
        loader.curve_sensor_assignments = {}
        model, detail = bake_metadata_status_line(loader, 0)
        assert model == "fallback"

    def test_every_active_model_has_a_render_kind(self):
        for model in (
            "manual_override",
            "method_4",
            "method_4_degraded",
            "method_1_high",
            "method_1_medium",
            "method_1_low",
            "fallback",
        ):
            assert model in STATUS_RENDER_KIND
            assert STATUS_RENDER_KIND[model] in {
                "success",
                "warning",
                "info",
                "caption",
            }
