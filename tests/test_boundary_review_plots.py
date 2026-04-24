"""Plot-helper tests for the Curve Boundary Review screen (M2 HMS Glorious).

Pure structural assertions — verify that figures contain the right
*kind* of trace/shape/marker rather than pixel-level styling.  Browser
smoke (M5 HMS Achilles) validates the visual feel.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.visualization.boundary_review_plots import (
    downsample_for_plot,
    plot_curve_detail,
    plot_raw_log_with_curves,
)


# ---------------------------------------------------------------------------
# Synthetic raw-log + curves builders
# ---------------------------------------------------------------------------


def _synthetic_raw_log(n_samples: int = 600, period_s: float = 5.0) -> pd.DataFrame:
    """Two-bake synthetic log: rise+plateau+drop, idle, rise+plateau+drop.

    Bake-2 is only rendered when ``n_samples >= 600``; for smaller logs
    only bake-1 is present (used by the over-/under-threshold downsample
    tests where the actual curve content is irrelevant).
    """
    t = np.arange(n_samples, dtype=float) * period_s
    vct = np.full(n_samples, 22.0)
    # Bake-1: idx 50..200 (only when n_samples ≥ 200)
    if n_samples >= 200:
        rise1 = np.linspace(22.0, 95.0, 80)
        plateau1 = np.full(40, 95.0)
        fall1 = np.linspace(95.0, 22.0, 30)
        vct[50:130] = rise1
        vct[130:170] = plateau1
        vct[170:200] = fall1
    # Bake-2: idx 350..550 (only when n_samples ≥ 550)
    if n_samples >= 550:
        rise2 = np.linspace(22.0, 97.0, 80)
        plateau2 = np.full(60, 97.0)
        fall2 = np.linspace(97.0, 22.0, 60)
        vct[350:430] = rise2
        vct[430:490] = plateau2
        vct[490:550] = fall2
    df = pd.DataFrame(
        {
            "Timestamp": t,
            "VirtualCoreTemperature": vct,
            "CoreTemperature": vct,
        }
    )
    return df


def _synthetic_curves() -> list[dict]:
    """Curve dicts matching the synthetic log above."""
    df = _synthetic_raw_log()
    return [
        {
            "data": df.iloc[50:200].copy(),
            "start_idx": 50,
            "end_idx": 199,
            "start_time": float(df["Timestamp"].iloc[50]),
            "end_time": float(df["Timestamp"].iloc[199]),
            "duration": (199 - 50) * 5.0 / 60.0,
            "max_temp": 95.0,
            "curve_number": 1,
            "samples": 150,
            "truncated": False,
            "exit_candidate_kind": "probe_pull_cliff",
        },
        {
            "data": df.iloc[350:550].copy(),
            "start_idx": 350,
            "end_idx": 549,
            "start_time": float(df["Timestamp"].iloc[350]),
            "end_time": float(df["Timestamp"].iloc[549]),
            "duration": (549 - 350) * 5.0 / 60.0,
            "max_temp": 97.0,
            "curve_number": 2,
            "samples": 200,
            "truncated": False,
            "exit_candidate_kind": "core_peak_plateau",
        },
    ]


# ---------------------------------------------------------------------------
# Tests: downsample_for_plot
# ---------------------------------------------------------------------------


class TestDownsampleForPlot:

    def test_no_downsample_when_under_threshold(self):
        df = _synthetic_raw_log(n_samples=300)
        out = downsample_for_plot(df, max_points=5000)
        assert len(out) == len(df)
        # Endpoints must match (under-threshold path returns the input
        # unchanged so this is a no-op identity check).
        assert float(out["Timestamp"].iloc[0]) == float(df["Timestamp"].iloc[0])
        assert float(out["Timestamp"].iloc[-1]) == float(df["Timestamp"].iloc[-1])

    def test_downsample_above_threshold(self):
        df = _synthetic_raw_log(n_samples=20000)
        out = downsample_for_plot(df, max_points=5000)
        assert len(out) <= 5001  # endpoint preservation may add 1
        assert len(out) >= 5000 // 4  # can't be too sparse

    def test_downsample_preserves_first_and_last_samples(self):
        df = _synthetic_raw_log(n_samples=20000)
        out = downsample_for_plot(df, max_points=5000)
        assert out["Timestamp"].iloc[0] == df["Timestamp"].iloc[0]
        assert out["Timestamp"].iloc[-1] == df["Timestamp"].iloc[-1]

    def test_downsample_max_points_must_be_positive(self):
        df = _synthetic_raw_log(n_samples=300)
        with pytest.raises(ValueError):
            downsample_for_plot(df, max_points=0)


# ---------------------------------------------------------------------------
# Tests: plot_raw_log_with_curves
# ---------------------------------------------------------------------------


class TestPlotRawLogWithCurves:

    def test_returns_plotly_figure(self):
        fig = plot_raw_log_with_curves(_synthetic_raw_log(), _synthetic_curves())
        assert isinstance(fig, go.Figure)

    def test_one_vrect_per_curve(self):
        curves = _synthetic_curves()
        fig = plot_raw_log_with_curves(_synthetic_raw_log(), curves)
        # vrects appear as layout shapes of type 'rect'
        rects = [s for s in fig.layout.shapes if s.type == "rect"]
        assert len(rects) == len(curves), (
            f"expected {len(curves)} vrects, got {len(rects)}"
        )

    def test_zero_curves_renders_log_without_vrects(self):
        fig = plot_raw_log_with_curves(_synthetic_raw_log(), [])
        rects = [s for s in fig.layout.shapes if s.type == "rect"]
        assert len(rects) == 0
        # And the raw-log scatter trace is present
        assert any(t.type == "scatter" for t in fig.data)

    def test_start_end_markers_per_curve(self):
        curves = _synthetic_curves()
        fig = plot_raw_log_with_curves(_synthetic_raw_log(), curves)
        # We render start/end as scatter markers (one trace each, or two
        # combined).  Count distinct marker traces — there must be at
        # least 2 × n_curves marker points.
        marker_points = 0
        for t in fig.data:
            if getattr(t, "mode", "") and "markers" in t.mode:
                marker_points += len(t.x or []) if t.x is not None else 0
        assert marker_points >= 2 * len(curves), (
            f"expected ≥{2 * len(curves)} marker points, got {marker_points}"
        )

    def test_manual_override_curve_uses_distinct_color(self):
        """Pinned curves (kind='manual_override') must be visually distinct
        from detector-decided curves so the operator can see at a glance
        which curves they've manually adjusted."""
        curves = _synthetic_curves()
        curves[0]["exit_candidate_kind"] = "manual_override"
        fig = plot_raw_log_with_curves(_synthetic_raw_log(), curves)
        rects = [s for s in fig.layout.shapes if s.type == "rect"]
        # Two rects with distinct fillcolors — not asserting which
        # colour is which (that's the styling layer's call), only that
        # they differ.
        assert rects[0].fillcolor != rects[1].fillcolor


# ---------------------------------------------------------------------------
# Tests: plot_curve_detail
# ---------------------------------------------------------------------------


class TestPlotCurveDetail:

    def test_returns_plotly_figure(self):
        df = _synthetic_raw_log()
        curve = _synthetic_curves()[0]
        fig = plot_curve_detail(df, curve)
        assert isinstance(fig, go.Figure)

    def test_marks_detected_start_and_end(self):
        df = _synthetic_raw_log()
        curve = _synthetic_curves()[0]
        fig = plot_curve_detail(df, curve)
        # vline markers at start and end → two layout shapes of type 'line'
        vlines = [s for s in fig.layout.shapes if s.type == "line"]
        assert len(vlines) >= 2

    def test_hint_window_drawn_when_supplied(self):
        df = _synthetic_raw_log()
        curve = _synthetic_curves()[0]
        # 600 s expected duration, ±15% band ~ [510, 690] s
        fig = plot_curve_detail(df, curve, hint_window_s=(510.0, 690.0))
        rects = [s for s in fig.layout.shapes if s.type == "rect"]
        assert len(rects) >= 1, (
            "hint_window_s must produce at least one band vrect"
        )

    def test_override_markers_distinct_from_detected(self):
        """When `override_indices=(start, end)` is supplied, the figure
        must visually distinguish the override from the detector's
        decision (different colour / line style)."""
        df = _synthetic_raw_log()
        curve = _synthetic_curves()[0]
        fig = plot_curve_detail(df, curve, override_indices=(60, 180))
        vlines = [s for s in fig.layout.shapes if s.type == "line"]
        # Detected (2) + override (2) = at least 4 vlines.
        assert len(vlines) >= 4, (
            f"expected ≥4 vlines (detected + override); got {len(vlines)}"
        )

    def test_zoom_range_includes_curve_with_padding(self):
        df = _synthetic_raw_log()
        curve = _synthetic_curves()[0]
        fig = plot_curve_detail(df, curve)
        # x-axis range must cover the curve.  We allow ± padding.
        x0, x1 = fig.layout.xaxis.range
        assert x0 <= curve["start_time"]
        assert x1 >= curve["end_time"]

    def test_no_downsample_artefact_in_detail(self):
        """Detail plot should not aggressively downsample the curve
        region itself — that's where the operator is looking closely."""
        df = _synthetic_raw_log(n_samples=20000)
        curve = {
            "data": df.iloc[5000:6000].copy(),
            "start_idx": 5000,
            "end_idx": 5999,
            "start_time": float(df["Timestamp"].iloc[5000]),
            "end_time": float(df["Timestamp"].iloc[5999]),
            "duration": (5999 - 5000) * 5.0 / 60.0,
            "max_temp": 97.0,
            "curve_number": 1,
            "samples": 1000,
            "truncated": False,
            "exit_candidate_kind": "probe_pull_cliff",
        }
        fig = plot_curve_detail(df, curve)
        # Find the main scatter trace; its x-array length should be
        # comparable to the curve sample count plus padding (not <100).
        scatter_lengths = [
            len(t.x) for t in fig.data if t.type == "scatter" and t.x is not None
        ]
        assert max(scatter_lengths, default=0) >= 500, (
            f"detail plot over-downsampled (max trace length: {max(scatter_lengths, default=0)})"
        )
