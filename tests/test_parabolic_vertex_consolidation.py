"""H5 — parabolic-vertex consolidation pin tests (M28).

``piecewise._parabolic_vertex`` and ``stefan``'s import of it were deleted;
both now route the interior 3-point vertex through
``extrapolation.parabolic_vertex_with_clamp(..., relaxed_clamp_mode=False)``.
This file pins that the non-relaxed interior path reproduces the historic
±1-half-step-clamped vertex algebra across the degenerate cases, and that the
old private function is gone (single source of truth).
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.extrapolation import (  # noqa: E402
    parabolic_vertex_with_clamp,
)
import src.data.spatial_reconstruction.piecewise as pw  # noqa: E402
import src.data.spatial_reconstruction.stefan as sf  # noqa: E402


class TestInteriorVertexMatchesHistoricAlgebra:

    def test_clean_interior_vertex(self):
        # parabola through (0,0),(1,2),(2,1): offset = 0.5*(0-1)/(0-4+1)=0.1667
        x = np.array([0.0, 1.0, 2.0])
        y = np.array([0.0, 2.0, 1.0])
        vertex, label = parabolic_vertex_with_clamp(x, y, 1, relaxed_clamp_mode=False)
        assert label == "high"
        assert abs(vertex - (1.0 + (1.0 / 6.0))) < 1e-9

    def test_offset_clamped_high(self):
        # offset = 0.5*(3-0)/(3-2+0) = 1.5 -> clamp to +1 -> vertex = x[2]
        x = np.array([0.0, 1.0, 2.0])
        y = np.array([3.0, 1.0, 0.0])
        vertex, label = parabolic_vertex_with_clamp(x, y, 1, relaxed_clamp_mode=False)
        assert label == "high"
        assert abs(vertex - 2.0) < 1e-9

    def test_offset_clamped_low(self):
        # offset = 0.5*(0-3)/(0-2+3) = -1.5 -> clamp to -1 -> vertex = x[0]
        x = np.array([0.0, 1.0, 2.0])
        y = np.array([0.0, 1.0, 3.0])
        vertex, label = parabolic_vertex_with_clamp(x, y, 1, relaxed_clamp_mode=False)
        assert label == "high"
        assert abs(vertex - 0.0) < 1e-9

    def test_collinear_is_degenerate(self):
        # denom = 1 - 4 + 3 = 0 -> returns the anchor x with "medium"
        x = np.array([0.0, 1.0, 2.0])
        y = np.array([1.0, 2.0, 3.0])
        vertex, label = parabolic_vertex_with_clamp(x, y, 1, relaxed_clamp_mode=False)
        assert label == "medium"
        assert abs(vertex - 1.0) < 1e-9

    def test_boundary_anchor_snaps_to_sensor(self):
        # Non-relaxed boundary anchor degrades to the discrete sensor pick.
        x = np.array([0.0, 1.0, 2.0, 3.0])
        y = np.array([5.0, 4.0, 3.0, 2.0])
        vertex, label = parabolic_vertex_with_clamp(x, y, 0, relaxed_clamp_mode=False)
        assert label == "high"
        assert abs(vertex - 0.0) < 1e-9


class TestSingleSourceOfTruth:

    def test_piecewise_no_longer_defines_parabolic_vertex(self):
        assert not hasattr(pw, "_parabolic_vertex")

    def test_stefan_no_longer_imports_parabolic_vertex(self):
        assert not hasattr(sf, "_parabolic_vertex")
