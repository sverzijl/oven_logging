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

    # ------------------------------------------------------------------
    # fix/deep-review #6 — a gradual air-side gradient must NOT register as a
    # multi-sensor lid plateau. The old "within tolerance of ONE anchor"
    # grouping accepted a smooth ramp where the extremes are far apart so long
    # as every step was small; require the accepted cluster to be internally
    # coherent (max-min within tolerance) AND index-adjacent (a real lid
    # touches physically adjacent sensors).
    # ------------------------------------------------------------------

    def test_monotone_gradient_not_accepted_as_lid(self):
        # A 5-sensor monotone ramp 100,110,120,130,140. Adjacent steps are
        # 10 C (< 15 C tolerance) but the cluster span is 40 C — this is a
        # cavity-air gradient, not a lid plateau. Must NOT be accepted.
        terminal = {"T4": 100.0, "T5": 110.0, "T6": 120.0, "T7": 130.0, "T8": 140.0}
        result = select_lid_cluster([3, 4, 5, 6, 7], SENSORS, terminal)
        # The returned cluster (if any) must be internally coherent: its own
        # terminal span must be within tolerance. A 5-wide span-40 ramp must
        # not slip through as a valid lid.
        if result:
            temps = [terminal[SENSORS[i]] for i in result]
            assert (max(temps) - min(temps)) <= LID_CLUSTER_TOLERANCE_C, (
                f"gradient accepted as lid: {result} span "
                f"{max(temps) - min(temps)} > {LID_CLUSTER_TOLERANCE_C}"
            )

    def test_coherent_adjacent_pair_within_gradient_is_ok(self):
        # Two genuinely-close adjacent sensors at the top of the ramp form a
        # real (coherent + adjacent) cluster and ARE accepted.
        terminal = {"T6": 128.0, "T7": 130.0, "T8": 131.0}
        result = sorted(select_lid_cluster([5, 6, 7], SENSORS, terminal))
        assert result == [5, 6, 7]

    def test_non_adjacent_cluster_not_accepted(self):
        # Two sensors with similar temps but NOT index-adjacent (T6 and T8 with
        # a hot T7 between) is not a contiguous lid contact.
        terminal = {"T6": 130.0, "T7": 200.0, "T8": 131.0}
        # Only T6 and T8 are within tolerance, but they straddle a hot T7 —
        # not a contiguous lid. Must be rejected.
        assert select_lid_cluster([5, 7], SENSORS, terminal) == []
