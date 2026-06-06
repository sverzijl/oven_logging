"""Method 1: relaxed parabolic clamp for past-tip core extrapolation
(M18 HMS Vigilant).

Today's piecewise core fitter clamps the parabolic vertex to ``[-1, +1]``
half-step offsets around the anchor (see
``piecewise._parabolic_vertex``). When the anchor is the boundary T1 (probe
tip), the clamp degrades to ``x_arr[0]`` — the spatial fit cannot signal
that the actual coldest point is *past* the tip (deeper into the loaf).

Method 1 introduces a *relaxed* parabolic-vertex helper that, when the anchor
is at a boundary, fits the 3-point parabola through ``(anchor, anchor+1,
anchor+2)`` (or symmetric on the other end), computes the un-clamped vertex,
and *reports* the past-boundary position with a low-confidence
``'low_extrapolated'`` label so the UI can flag it as such.

This file pins the relaxed-clamp behaviour BEFORE it exists (TDD failing-first).
"""

from __future__ import annotations

import os
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# parabolic_vertex_with_clamp helper
# ---------------------------------------------------------------------------


class TestParabolicVertexWithClamp:
    """Direct unit tests for the relaxed-clamp helper."""

    def test_relaxed_clamp_extrapolates_past_t1(self):
        """Synthetic time_to_60c monotonically increasing toward T1.

        The interior parabola through (T1, T2, T3) has its vertex past T1
        (x < 0) — relaxed_clamp_mode=True must REPORT that vertex with
        confidence_label='low_extrapolated'.
        """
        from src.data.spatial_reconstruction.extrapolation import (
            parabolic_vertex_with_clamp,
        )

        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        # Score is *higher* for more core-like sensors. Past-tip extrapolation
        # means the true argmax is at x < 0 (off the probe), so we construct a
        # parabola whose vertex is at x = -0.1 and whose argmax among sampled
        # sensors is therefore T1 (the closest sample to -0.1).
        x_vertex_true = -0.1
        ys = -100.0 * (positions - x_vertex_true) ** 2 + 50.0
        # T1 is the argmax (anchor).
        anchor = int(np.argmax(ys))
        assert anchor == 0, "fixture sanity: T1 should anchor"

        vertex_x, label = parabolic_vertex_with_clamp(
            positions, ys, anchor, relaxed_clamp_mode=True
        )
        assert vertex_x < positions[0], (
            f"Expected vertex past T1 (x < 0), got {vertex_x:.4f}"
        )
        assert label == "low_extrapolated", (
            f"Expected confidence_label='low_extrapolated', got {label!r}"
        )

    def test_strict_clamp_default_no_extrapolation(self):
        """Same synthetic data with relaxed_clamp_mode=False → snap to T1."""
        from src.data.spatial_reconstruction.extrapolation import (
            parabolic_vertex_with_clamp,
        )

        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        x_vertex_true = -0.1
        ys = -100.0 * (positions - x_vertex_true) ** 2 + 50.0
        anchor = int(np.argmax(ys))

        vertex_x, label = parabolic_vertex_with_clamp(
            positions, ys, anchor, relaxed_clamp_mode=False
        )
        assert vertex_x == pytest.approx(positions[0]), (
            f"Strict clamp must snap to T1, got {vertex_x:.4f}"
        )
        # Confidence in the snap is 'high' (degenerate boundary, normal pre-M18
        # behaviour), per spec.
        assert label == "high"

    def test_relaxed_clamp_when_vertex_inside_probe_returns_medium(self):
        """Boundary anchor with relaxed_clamp on, but the parabola's vertex
        falls INSIDE the probe (i.e. between T1 and T2) — return T1 (the
        anchor) with confidence='medium' since the un-clamped vertex did
        not actually extrapolate past the boundary."""
        from src.data.spatial_reconstruction.extrapolation import (
            parabolic_vertex_with_clamp,
        )

        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        # Vertex at x = +0.05 — slightly INSIDE the probe; not past T1 but
        # near the tip. T1 is still the argmax sample.
        x_vertex_true = 0.05
        ys = -100.0 * (positions - x_vertex_true) ** 2 + 50.0
        anchor = int(np.argmax(ys))
        assert anchor == 0

        vertex_x, label = parabolic_vertex_with_clamp(
            positions, ys, anchor, relaxed_clamp_mode=True
        )
        assert vertex_x == pytest.approx(positions[0]), (
            f"Vertex inside probe → snap back to T1; got {vertex_x:.4f}"
        )
        assert label == "medium"

    def test_interior_anchor_unchanged_behaviour(self):
        """Interior anchor → behaves exactly like the clamped helper."""
        from src.data.spatial_reconstruction.extrapolation import (
            parabolic_vertex_with_clamp,
        )

        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        x_vertex_true = 0.42
        ys = -100.0 * (positions - x_vertex_true) ** 2 + 50.0
        anchor = int(np.argmax(ys))

        vertex_x, label = parabolic_vertex_with_clamp(
            positions, ys, anchor, relaxed_clamp_mode=True
        )
        assert abs(vertex_x - x_vertex_true) < 0.005
        assert label == "high"

    def test_interior_anchor_collinear_returns_medium(self):
        """Interior degenerate (collinear) → medium confidence (sensor pos)."""
        from src.data.spatial_reconstruction.extrapolation import (
            parabolic_vertex_with_clamp,
        )

        positions = np.array([i / 7.0 for i in range(8)], dtype=float)
        ys = np.linspace(10.0, 50.0, 8)
        vertex_x, label = parabolic_vertex_with_clamp(
            positions, ys, 4, relaxed_clamp_mode=True
        )
        assert vertex_x == pytest.approx(positions[4])
        assert label == "medium"


# ---------------------------------------------------------------------------
# Real-CSV smoke: T1-anchored core must surface as low- or medium-confidence
# ---------------------------------------------------------------------------


class TestRealCSVRelaxedClamp:
    """Real-CSV smoke: when the classifier picks T1 as the core anchor, the
    classifier's core PositionalAssignment must reflect lowered confidence
    and the 'extrapolated' reason — not a flat 'high'.
    """

    def test_t1_anchored_core_is_low_confidence_with_extrapolation_reason(self):
        from src.data.loader import ThermalProfileLoader

        loader = ThermalProfileLoader()
        loader.load_csv(
            str(REPO / "ProbeData_1000BA3C_2025-05-30 09_46_16.csv")
        )
        # On BA3C 0946 the core anchor is T1 (verified empirically across M11+).
        # Find the curve whose classifier core picked T1.
        found = False
        for curve_index in range(len(loader.all_curves)):
            assignment = loader.curve_sensor_assignments.get(
                curve_index, {}
            ).get("assignment")
            if assignment is None or assignment.core_assignment is None:
                continue
            if assignment.core_assignment.nearest_sensor != "T1":
                continue
            found = True
            core = assignment.core_assignment
            assert core.confidence in ("low", "medium"), (
                f"T1-anchored core must be low/medium confidence; got "
                f"{core.confidence!r}"
            )
            if core.confidence == "low":
                assert "extrapol" in core.reason.lower(), (
                    f"low-confidence T1 core should mention extrapolation: "
                    f"{core.reason!r}"
                )
        assert found, (
            "Fixture invariant: BA3C 0946 should have at least one curve "
            "with core anchored at T1."
        )
