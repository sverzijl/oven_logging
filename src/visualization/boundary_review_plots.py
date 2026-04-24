"""Plot helpers for the Curve Boundary Review screen (M2 HMS Glorious).

Two public figures + one helper:

* :func:`plot_raw_log_with_curves` — full pre-extraction CSV log plotted
  on a single time axis, with each detected bake drawn as a translucent
  vrect band coloured by ``exit_candidate_kind`` and start/end markers
  pinned at the detected sample indices.

* :func:`plot_curve_detail` — zoomed view of a single curve's
  neighbourhood (±20% padding), with detected start/end as solid
  vlines, optional hint-window vrect, and optional manual-override
  vlines distinct in colour and dash style.

* :func:`downsample_for_plot` — ``iloc[::stride]`` helper that preserves
  the first and last samples.  Reused by both figures when the raw log
  is large (~6,200 samples for BA3C_1759).

Pure module: no Streamlit imports; consumed by
``tabs/boundary_review.py`` (M3 HMS Indomitable).
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.visualization.visualization_config import VisualizationConfig


# ---------------------------------------------------------------------------
# Style vocabulary
# ---------------------------------------------------------------------------


# Per-kind fillcolor for the raw-log vrect bands.  RGBA so the underlying
# trace remains visible.  ``manual_override`` is deliberately the most
# saturated so the operator immediately notices a pinned curve.
_KIND_FILLCOLOR: dict[str, str] = {
    "probe_pull_cliff": "rgba(78, 205, 196, 0.20)",   # teal
    "core_peak_plateau": "rgba(69, 183, 209, 0.20)",   # blue
    "drop_rate": "rgba(255, 165, 0, 0.20)",            # orange
    "cool_to_ambient": "rgba(255, 165, 0, 0.20)",      # orange
    "room_temp_plateau": "rgba(255, 165, 0, 0.20)",    # orange
    "dip_with_rerise": "rgba(150, 150, 150, 0.20)",    # grey
    "manual_override": "rgba(245, 158, 11, 0.35)",     # amber, more saturated
}
_KIND_FALLBACK_FILLCOLOR = "rgba(150, 150, 150, 0.20)"

_DETECTED_BOUNDARY_COLOR = "#0066CC"   # detector decision
_OVERRIDE_BOUNDARY_COLOR = "#F59E0B"   # operator decision
_HINT_WINDOW_COLOR = "rgba(180, 212, 255, 0.30)"
_RAW_TRACE_COLOR = "#333333"


# ---------------------------------------------------------------------------
# downsample
# ---------------------------------------------------------------------------


def downsample_for_plot(df: pd.DataFrame, *, max_points: int = 5000) -> pd.DataFrame:
    """Stride-downsample ``df`` to at most ``max_points`` rows while
    preserving the first and last samples.

    When ``len(df) <= max_points``, returns the input unchanged.
    Otherwise picks ``stride = ceil(len(df) / max_points)`` and selects
    every ``stride``-th row, then ensures the very last row is present
    (Plotly viewers will visually clip the right edge of a long log
    otherwise).
    """
    if max_points <= 0:
        raise ValueError(f"max_points must be > 0; got {max_points}")
    n = len(df)
    if n <= max_points:
        return df
    stride = int(np.ceil(n / max_points))
    out = df.iloc[::stride]
    last_row = df.iloc[[-1]]
    if out.index[-1] != last_row.index[0]:
        out = pd.concat([out, last_row])
    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_core_column(df: pd.DataFrame) -> str | None:
    for c in ("CoreTemperature", "VirtualCoreTemperature"):
        if c in df.columns:
            return c
    return None


def _kind_color(kind: str | None) -> str:
    if kind is None:
        return _KIND_FALLBACK_FILLCOLOR
    return _KIND_FILLCOLOR.get(kind, _KIND_FALLBACK_FILLCOLOR)


def _curve_sort_key(curve: dict[str, Any]) -> int:
    return int(curve.get("start_idx", 0))


# ---------------------------------------------------------------------------
# plot_raw_log_with_curves
# ---------------------------------------------------------------------------


def plot_raw_log_with_curves(
    raw_df: pd.DataFrame,
    curves: Iterable[dict[str, Any]],
    *,
    downsample_to: int = 5000,
) -> go.Figure:
    """Plot the full raw CSV log with each detected curve drawn as a
    translucent vrect band coloured by ``exit_candidate_kind``.

    Adds start and end scatter markers per curve so the operator can
    see exactly which samples the detector picked.
    """
    fig = go.Figure()
    if raw_df is None or len(raw_df) == 0:
        fig.update_layout(
            **VisualizationConfig.DEFAULT_LAYOUT,
            title="No data loaded",
        )
        return fig

    plot_df = downsample_for_plot(raw_df, max_points=downsample_to)
    core_col = _resolve_core_column(plot_df)
    timestamps = plot_df["Timestamp"].to_numpy(dtype=float)

    # Main raw-log trace.
    if core_col is not None:
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=plot_df[core_col].to_numpy(dtype=float),
                mode="lines",
                name="Core temperature (raw)",
                line=dict(color=_RAW_TRACE_COLOR, width=1.5),
                hovertemplate="t=%{x:.0f}s<br>T=%{y:.2f}°C<extra></extra>",
            )
        )

    # vrect band per curve, plus start/end markers.  Use the FULL raw_df
    # for index lookups (the downsampled plot_df may have skipped the
    # exact start/end samples).
    full_ts = raw_df["Timestamp"].to_numpy(dtype=float)
    full_core = (
        raw_df[core_col].to_numpy(dtype=float)
        if core_col and core_col in raw_df.columns
        else None
    )

    sorted_curves = sorted(list(curves), key=_curve_sort_key)
    for curve in sorted_curves:
        s = int(curve["start_idx"])
        e = int(curve["end_idx"])
        kind = curve.get("exit_candidate_kind")
        fig.add_vrect(
            x0=float(full_ts[s]),
            x1=float(full_ts[e]),
            fillcolor=_kind_color(kind),
            line_width=0,
            layer="below",
            annotation_text=(
                f"Bake {curve.get('curve_number', '?')} "
                f"({kind or 'unknown'})"
            ),
            annotation_position="top left",
        )
        if full_core is not None:
            fig.add_trace(
                go.Scatter(
                    x=[float(full_ts[s]), float(full_ts[e])],
                    y=[float(full_core[s]), float(full_core[e])],
                    mode="markers",
                    name=f"Bake {curve.get('curve_number', '?')} bounds",
                    marker=dict(
                        size=10,
                        symbol="diamond",
                        color=_DETECTED_BOUNDARY_COLOR,
                        line=dict(width=2, color="white"),
                    ),
                    showlegend=False,
                    hovertemplate="t=%{x:.0f}s<br>T=%{y:.2f}°C<extra></extra>",
                )
            )

    fig.update_layout(
        **VisualizationConfig.DEFAULT_LAYOUT,
        title="Raw CSV log with detected bake windows",
        xaxis_title="Time (s)",
        yaxis_title="Core temperature (°C)",
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# plot_curve_detail
# ---------------------------------------------------------------------------


def plot_curve_detail(
    raw_df: pd.DataFrame,
    curve: dict[str, Any],
    *,
    hint_window_s: tuple[float, float] | None = None,
    override_indices: tuple[int, int] | None = None,
) -> go.Figure:
    """Zoomed plot of one curve's neighbourhood with overlays.

    * Detected start/end are drawn as solid blue vlines.
    * ``hint_window_s = (lo, hi)`` (in absolute log seconds) draws a
      translucent blue vrect for the operator's expected-end window.
    * ``override_indices = (start, end)`` (raw_df index space) draws
      dashed amber vlines distinct from the detector's decision.
    """
    fig = go.Figure()
    if raw_df is None or len(raw_df) == 0:
        return fig
    core_col = _resolve_core_column(raw_df)
    full_ts = raw_df["Timestamp"].to_numpy(dtype=float)

    s = int(curve["start_idx"])
    e = int(curve["end_idx"])
    span_s = max(float(full_ts[e]) - float(full_ts[s]), 1.0)
    pad = 0.20 * span_s
    lo_t = float(full_ts[s]) - pad
    hi_t = float(full_ts[e]) + pad

    # Window of raw_df rows in [lo_t, hi_t] for the line trace.
    mask = (full_ts >= lo_t) & (full_ts <= hi_t)
    window_df = raw_df.loc[mask]

    if core_col is not None:
        fig.add_trace(
            go.Scatter(
                x=window_df["Timestamp"].to_numpy(dtype=float),
                y=window_df[core_col].to_numpy(dtype=float),
                mode="lines",
                name="Core temperature",
                line=dict(color=_RAW_TRACE_COLOR, width=1.5),
                hovertemplate="t=%{x:.0f}s<br>T=%{y:.2f}°C<extra></extra>",
            )
        )

    # Hint band (drawn first so it sits below the vlines).
    if hint_window_s is not None:
        lo_h, hi_h = hint_window_s
        fig.add_vrect(
            x0=float(lo_h),
            x1=float(hi_h),
            fillcolor=_HINT_WINDOW_COLOR,
            line_width=0,
            layer="below",
            annotation_text="Hint window",
            annotation_position="top right",
        )

    # Detected start / end vlines.
    fig.add_vline(
        x=float(full_ts[s]),
        line=dict(color=_DETECTED_BOUNDARY_COLOR, width=2),
        annotation_text="Detected start",
        annotation_position="top left",
    )
    fig.add_vline(
        x=float(full_ts[e]),
        line=dict(color=_DETECTED_BOUNDARY_COLOR, width=2),
        annotation_text="Detected end",
        annotation_position="top right",
    )

    # Manual-override vlines, dashed and amber so the operator
    # distinguishes them at a glance.
    if override_indices is not None:
        os_, oe_ = override_indices
        if 0 <= os_ < len(full_ts):
            fig.add_vline(
                x=float(full_ts[os_]),
                line=dict(
                    color=_OVERRIDE_BOUNDARY_COLOR, width=2, dash="dash"
                ),
                annotation_text="Override start",
                annotation_position="bottom left",
            )
        if 0 <= oe_ < len(full_ts):
            fig.add_vline(
                x=float(full_ts[oe_]),
                line=dict(
                    color=_OVERRIDE_BOUNDARY_COLOR, width=2, dash="dash"
                ),
                annotation_text="Override end",
                annotation_position="bottom right",
            )

    fig.update_layout(
        **VisualizationConfig.DEFAULT_LAYOUT,
        title=f"Bake {curve.get('curve_number', '?')} detail",
        xaxis=dict(range=[lo_t, hi_t], title="Time (s)"),
        yaxis_title="Core temperature (°C)",
        hovermode="x unified",
    )
    return fig


__all__ = [
    "downsample_for_plot",
    "plot_raw_log_with_curves",
    "plot_curve_detail",
]
