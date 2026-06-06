"""Lid-cluster detection helper (M28 H3 consolidation).

A genuine lid touches *multiple* adjacent sensors at similar plateaued
temperatures, whereas a single isolated sensor in the lid-gap window is more
likely an unlidded ambient sensor that reads cooler than the cavity proxy.
The classifier therefore accepts a lid only when >= 2 candidate sensors share
a terminal-temperature cluster.

This "densest temperature cluster" search was previously inlined twice in
``classifier.py`` (the ambient-exclusion pre-pass and the lid-selection
block). It is hoisted here so both call sites — and any future consumer —
share one implementation and one tolerance constant.
"""

from __future__ import annotations

from typing import Optional, Sequence

from config.constants import LID_CLUSTER_TOLERANCE_C


def select_lid_cluster(
    candidate_indices: Sequence[int],
    sensor_names: Sequence[str],
    terminal_temps: dict,
    tolerance_c: Optional[float] = None,
) -> list:
    """Return the densest terminal-temperature cluster among the candidates.

    Parameters
    ----------
    candidate_indices:
        Sensor indices already filtered to the lid-gap window by the caller
        (the candidate-filtering rules differ per call site, so they stay with
        the caller; only the clustering is shared).
    sensor_names:
        Index -> sensor-name list, so ``terminal_temps[sensor_names[i]]``
        resolves each candidate's terminal temperature.
    terminal_temps:
        ``{sensor_name: terminal_temperature_C}``.
    tolerance_c:
        Cluster width in °C; defaults to
        :data:`config.constants.LID_CLUSTER_TOLERANCE_C`.

    Returns
    -------
    list[int]
        The sensor indices forming the densest cluster whose pairwise terminal
        temperatures fall within ``tolerance_c`` of a common member, or ``[]``
        when no cluster of >= 2 sensors exists.
    """
    if tolerance_c is None:
        tolerance_c = LID_CLUSTER_TOLERANCE_C
    if len(candidate_indices) < 2:
        return []
    cand_temps = sorted(
        (terminal_temps[sensor_names[i]], i) for i in candidate_indices
    )
    best_cluster: list = []
    for j in range(len(cand_temps)):
        cluster_at_j = [
            idx for T, idx in cand_temps
            if abs(T - cand_temps[j][0]) <= tolerance_c
        ]
        if len(cluster_at_j) > len(best_cluster):
            best_cluster = cluster_at_j
    return best_cluster if len(best_cluster) >= 2 else []
