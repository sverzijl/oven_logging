"""H3 — lid-cluster detection pin tests (M28).

``_lid.select_lid_cluster`` is the single source of the densest-temperature
cluster search the classifier previously inlined in both the ambient-exclusion
pre-pass and the lid-selection block.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.constants import LID_CLUSTER_TOLERANCE_C  # noqa: E402
from src.data.spatial_reconstruction._lid import select_lid_cluster  # noqa: E402

SENSORS = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]


class TestSelectLidCluster:

    def test_two_close_sensors_form_a_cluster(self):
        terminal = {"T6": 130.0, "T7": 132.0}  # within 15 °C
        assert sorted(select_lid_cluster([5, 6], SENSORS, terminal)) == [5, 6]

    def test_single_candidate_is_not_a_cluster(self):
        assert select_lid_cluster([5], SENSORS, {"T6": 130.0}) == []

    def test_two_far_sensors_are_not_a_cluster(self):
        terminal = {"T6": 130.0, "T7": 160.0}  # 30 °C apart > tolerance
        assert select_lid_cluster([5, 6], SENSORS, terminal) == []

    def test_densest_cluster_excludes_the_outlier(self):
        # T6/T7/T8 are within 15 °C of each other; T5 is the cold outlier.
        terminal = {"T5": 100.0, "T6": 131.0, "T7": 133.0, "T8": 135.0}
        result = select_lid_cluster([4, 5, 6, 7], SENSORS, terminal)
        assert set(result) == {5, 6, 7}

    def test_tolerance_override(self):
        terminal = {"T6": 130.0, "T7": 150.0}  # 20 °C apart
        # Default tolerance (15) rejects; a 25 °C tolerance accepts.
        assert select_lid_cluster([5, 6], SENSORS, terminal) == []
        assert sorted(
            select_lid_cluster([5, 6], SENSORS, terminal, tolerance_c=25.0)
        ) == [5, 6]

    def test_default_tolerance_is_the_constant(self):
        # A pair exactly at the tolerance boundary clusters; just beyond does not.
        at = {"T6": 100.0, "T7": 100.0 + LID_CLUSTER_TOLERANCE_C}
        beyond = {"T6": 100.0, "T7": 100.0 + LID_CLUSTER_TOLERANCE_C + 0.5}
        assert sorted(select_lid_cluster([5, 6], SENSORS, at)) == [5, 6]
        assert select_lid_cluster([5, 6], SENSORS, beyond) == []
