"""Pin test: Method 4 trumps Method 1's confidence (M29).

On a curve where the classifier extrapolated past the probe tip and reported
``confidence="low"``, supplying full bake metadata (with the geometric core
in-probe) must promote ``get_core_confidence`` to ``("high", reason)`` where
the reason names the geometric core and the bake-metadata source — because a
deterministic operator-supplied geometry beats a thermal extrapolation.
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
    assert ldr.all_curves
    return ldr


class TestMethod4OverridesMethod1Confidence:

    def test_metadata_promotes_low_classifier_to_high(self, loader):
        # Baseline: BA3C_0946 curve 0 anchors the core at the probe tip, so
        # the classifier reports a low-confidence (extrapolated) core.
        conf0, reason0 = loader.get_core_confidence(0)
        assert conf0 == "low", (
            f"fixture precondition: expected classifier 'low', got {conf0!r} "
            f"({reason0!r})"
        )

        # Supply Method 4 geometry with the core in-probe (pos = +10 mm).
        loader.set_bake_metadata(
            0, {"loaf_thickness_mm": 120.0, "insertion_depth_mm": 70.0}
        )
        conf1, reason1 = loader.get_core_confidence(0)
        assert conf1 == "high", "Method 4 must trump the classifier's low confidence"
        assert "geometric core" in reason1.lower()
        assert "via bake metadata" in reason1.lower()
        # The position in mm is surfaced so the operator knows which model feeds
        # the trace.
        assert "mm" in reason1.lower()
