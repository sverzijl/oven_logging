"""Pin tests for ``ThermalProfileLoader.get_core_confidence`` (M29).

The accessor returns ``(confidence, reason)`` following the same layering as
``get_core_temperature_series`` (both read :meth:`_resolve_core`):
override → Method 4 in-probe → Method 4 past-tip → classifier → fallback.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader  # noqa: E402

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


class TestGetCoreConfidence:

    def test_manual_override_is_high(self, loader):
        loader.set_sensor_override(0, "core", "T1")
        conf, reason = loader.get_core_confidence(0)
        assert conf == "high"
        assert "override" in reason.lower()

    def test_method4_in_probe_is_high(self, loader):
        # pos = insertion - loaf/2 = 70 - 60 = +10 mm (core above tip).
        loader.set_bake_metadata(
            0, {"loaf_thickness_mm": 120.0, "insertion_depth_mm": 70.0}
        )
        conf, reason = loader.get_core_confidence(0)
        assert conf == "high"
        assert "geometric core" in reason.lower()
        assert "via bake metadata" in reason.lower()

    def test_method4_past_tip_is_low(self, loader):
        # pos = 20 - 60 = -40 mm (core past/below the probe tip).
        loader.set_bake_metadata(
            0, {"loaf_thickness_mm": 120.0, "insertion_depth_mm": 20.0}
        )
        conf, reason = loader.get_core_confidence(0)
        assert conf == "low"
        assert "below probe tip" in reason.lower()

    def test_classifier_branch_matches_assignment(self, loader):
        conf, reason = loader.get_core_confidence(0)
        assert conf in {"high", "medium", "low"}
        assert isinstance(reason, str) and reason
        assignment = loader.curve_sensor_assignments.get(0, {}).get("assignment")
        assert conf == assignment.core_assignment.confidence
        assert reason == assignment.core_assignment.reason

    def test_fallback_when_no_assignment(self, loader):
        # Strip the classifier assignment to exercise the final fallback arm.
        loader.curve_sensor_assignments = {}
        conf, reason = loader.get_core_confidence(0)
        assert conf == "low"
        assert "no classifier assignment" in reason.lower()

    def test_override_beats_metadata(self, loader):
        loader.set_bake_metadata(
            0, {"loaf_thickness_mm": 120.0, "insertion_depth_mm": 70.0}
        )
        loader.set_sensor_override(0, "core", "T1")
        conf, reason = loader.get_core_confidence(0)
        assert conf == "high"
        assert "override" in reason.lower()
