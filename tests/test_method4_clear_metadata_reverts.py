"""Pin test: clearing bake metadata reverts the core series (M29).

Sequence: set full geometry -> ``get_core_temperature_series`` returns the
geometric series; ``clear_bake_metadata`` -> next call returns the classifier
series (measurably different on a fixture where the two diverge).
"""

from __future__ import annotations

import os
import sys

import numpy as np
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


class TestMethod4ClearReverts:

    def test_set_then_clear_reverts_to_classifier(self, loader):
        # pos = 70 - 60 = +10 mm -> interpolated geometric core (T1/T2 blend).
        loader.set_bake_metadata(
            0, {"loaf_thickness_mm": 120.0, "insertion_depth_mm": 70.0}
        )
        geometric = loader.get_core_temperature_series(0)
        assert geometric is not None
        # The series IS the geometric one while metadata is active.
        gcs = loader._geometric_core_series(0)
        assert np.allclose(geometric.to_numpy(), gcs.to_numpy(), atol=1e-9)

        loader.clear_bake_metadata(0)
        reverted = loader.get_core_temperature_series(0)
        assert reverted is not None
        # After clearing, the series reverts to the classifier path and must
        # differ from the geometric series on this fixture.
        assert len(reverted) == len(geometric)
        assert not np.allclose(
            reverted.to_numpy(), geometric.to_numpy(), atol=1e-6
        ), "clear_bake_metadata did not revert the core series off Method 4"

    def test_clear_also_reverts_confidence(self, loader):
        loader.set_bake_metadata(
            0, {"loaf_thickness_mm": 120.0, "insertion_depth_mm": 70.0}
        )
        assert loader.get_core_confidence(0)[0] == "high"
        loader.clear_bake_metadata(0)
        # Reverts to the classifier's own confidence (low on this past-tip bake).
        conf, _ = loader.get_core_confidence(0)
        assert conf in {"high", "medium", "low"}
        assignment = loader.curve_sensor_assignments.get(0, {}).get("assignment")
        assert conf == assignment.core_assignment.confidence
