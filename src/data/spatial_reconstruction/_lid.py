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
        The sensor indices forming the densest cluster that is BOTH internally
        coherent (terminal max - min within ``tolerance_c``) AND index-adjacent
        (a real lid touches physically adjacent sensors), or ``[]`` when no such
        cluster of >= 2 sensors exists.

    Notes
    -----
    fix/deep-review #6: the previous rule grouped sensors "within tolerance of
    ONE anchor", which let a gradual air-side gradient (e.g. 100, 110, 120, 130,
    140 — every adjacent step < 15 C but a 40 C span) register as a multi-sensor
    lid plateau. A genuine lid is a tight, contiguous plateau: we now require
    the accepted cluster's own terminal span to be within ``tolerance_c`` AND
    its members to be index-adjacent.
    """
    if tolerance_c is None:
        tolerance_c = LID_CLUSTER_TOLERANCE_C
    if len(candidate_indices) < 2:
        return []

    # Sort candidates by sensor index so we can scan contiguous index runs.
    idx_sorted = sorted(candidate_indices)

    best_cluster: list = []
    # Scan every contiguous-by-index run; within each run take the longest
    # sub-run whose terminal span stays within tolerance (sliding window).
    n = len(idx_sorted)
    start = 0
    while start < n:
        # Extend a maximal index-adjacent run.
        end = start
        while end + 1 < n and idx_sorted[end + 1] == idx_sorted[end] + 1:
            end += 1
        run = idx_sorted[start : end + 1]
        # Within this index-adjacent run, find the longest window whose terminal
        # max - min <= tolerance_c (coherence). Sliding window over the run.
        w_lo = 0
        for w_hi in range(len(run)):
            # Shrink the window from the left until coherent.
            while w_lo <= w_hi:
                window = run[w_lo : w_hi + 1]
                temps = [terminal_temps[sensor_names[i]] for i in window]
                if (max(temps) - min(temps)) <= tolerance_c:
                    break
                w_lo += 1
            window = run[w_lo : w_hi + 1]
            if len(window) > len(best_cluster):
                best_cluster = list(window)
        start = end + 1

    return best_cluster if len(best_cluster) >= 2 else []
