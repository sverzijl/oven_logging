"""Method 1 — relaxed parabolic clamp for past-tip core extrapolation
(M18 HMS Vigilant).

The default 3-point parabolic-vertex helper in
:mod:`src.data.spatial_reconstruction.piecewise._parabolic_vertex` clamps
the offset to ±1 half-step so a badly conditioned parabola cannot
extrapolate past the immediate neighbours. That is the right default for
in-dough sensors where the parabola is interpolating between known samples.

When the in-dough core anchor is the boundary T1 (probe tip), however, the
clamp degrades to ``x_arr[0]`` — the spatial fit cannot signal that the
*actual* coldest point is past the tip (deeper into the loaf than T1
reaches). After 17 inverse-problem research missions confirmed a structural
~6 °C information limit on in-dough thermometry alone, the architectural
pivot is simply: *report* the past-boundary position with a low-confidence
``'low_extrapolated'`` label so the UI can flag it as such, and (as a
production complement) accept user-supplied loaf-geometry metadata to
compute the geometric core directly when available.

This module is the Method 1 piece. Method 4 (geometric core) lives in
``loader.py`` (metadata storage) and ``classifier.py`` consumption.

Public API:

* :func:`parabolic_vertex_with_clamp` — returns (vertex_x, confidence_label)
  where confidence_label is one of ``'high'``, ``'medium'``,
  ``'low_extrapolated'``.
"""

from __future__ import annotations

import numpy as np


def _three_point_vertex(
    x0: float, x1: float, x2: float, y0: float, y1: float, y2: float
) -> tuple[float | None, float]:
    """Return ``(vertex_x, denom)`` for the parabola through 3 points.

    Mirrors the algebra in ``piecewise._parabolic_vertex`` but without the
    ±1 clamp. ``vertex_x`` is ``None`` when the parabola is degenerate
    (collinear / zero denominator); the denominator is returned as the
    second tuple element so callers can distinguish degeneracy from a
    valid in-bounds vertex.
    """
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1e-12:
        return None, denom
    offset = 0.5 * (y0 - y2) / denom
    dx = (x2 - x0) / 2.0
    return float(x1 + offset * dx), denom


def parabolic_vertex_with_clamp(
    x_arr: np.ndarray,
    y_arr: np.ndarray,
    anchor_idx: int,
    relaxed_clamp_mode: bool = False,
) -> tuple[float, str]:
    """3-point parabolic vertex with optional relaxed boundary clamp.

    Parameters
    ----------
    x_arr, y_arr:
        Per-sensor position and score arrays (``y_arr[i]`` is the *core*
        score — higher = more core-like).
    anchor_idx:
        Index of the argmax sample in ``y_arr`` (the discrete core pick).
    relaxed_clamp_mode:
        When ``True`` and ``anchor_idx`` is at a boundary, fit the
        2-step-inward parabola through ``(anchor, anchor+1, anchor+2)``
        (or symmetric for the upper boundary) and report the vertex even
        when it lies past the boundary. When ``False`` the boundary anchor
        snaps to ``x_arr[anchor_idx]`` (matches the historic
        ``_parabolic_vertex`` boundary clause).

    Returns
    -------
    (vertex_x, confidence_label):
        ``vertex_x`` is the inferred core x-position. ``confidence_label``
        is one of:

        * ``'high'`` — interior 3-point parabola fitted cleanly OR boundary
          anchor with ``relaxed_clamp_mode=False`` (the historic snap-to-
          sensor case the rest of the pipeline expects).
        * ``'medium'`` — boundary anchor with ``relaxed_clamp_mode=True``
          but the un-clamped vertex did not actually extrapolate past the
          boundary, OR the parabola was degenerate (collinear).
        * ``'low_extrapolated'`` — boundary anchor with
          ``relaxed_clamp_mode=True`` and the un-clamped vertex falls
          *past* the boundary (i.e. signals "true core is off the probe").

    Notes
    -----
    The *strict* boundary-anchor case (``relaxed_clamp_mode=False``) returns
    ``confidence='high'`` because that is the legacy contract every other
    M2a/M3a/M6 caller currently depends on; introducing a confidence drop
    here would cascade into baseline-flip churn outside the M18 mission's
    scope. The relaxed mode is the new opt-in path that signals
    extrapolation explicitly.
    """
    n = len(x_arr)
    if n == 0:
        return 0.0, "medium"
    if anchor_idx < 0:
        anchor_idx = 0
    if anchor_idx >= n:
        anchor_idx = n - 1

    # Interior anchor: 3-point parabola with neighbours.
    if 0 < anchor_idx < n - 1:
        x0 = float(x_arr[anchor_idx - 1])
        x1 = float(x_arr[anchor_idx])
        x2 = float(x_arr[anchor_idx + 1])
        y0 = float(y_arr[anchor_idx - 1])
        y1 = float(y_arr[anchor_idx])
        y2 = float(y_arr[anchor_idx + 1])
        vertex, denom = _three_point_vertex(x0, x1, x2, y0, y1, y2)
        if vertex is None:
            return float(x1), "medium"
        # Mirror the original ±1 half-step clamp for the interior path; this
        # preserves the historic contract (test_parabolic_interpolation_*).
        offset = 0.5 * (y0 - y2) / denom
        if offset > 1.0:
            offset = 1.0
        elif offset < -1.0:
            offset = -1.0
        dx = (x2 - x0) / 2.0
        clamped_vertex = float(x1 + offset * dx)
        return clamped_vertex, "high"

    # Boundary anchor.
    if not relaxed_clamp_mode:
        return float(x_arr[anchor_idx]), "high"

    # relaxed_clamp_mode=True at a boundary: build the 2-step-inward window.
    if n < 3:
        return float(x_arr[anchor_idx]), "medium"

    if anchor_idx == 0:
        idx_a, idx_b, idx_c = 0, 1, 2
        boundary_direction = -1  # past-boundary if vertex < x_arr[0]
    else:  # anchor_idx == n - 1
        idx_a, idx_b, idx_c = n - 3, n - 2, n - 1
        boundary_direction = +1  # past-boundary if vertex > x_arr[-1]

    x_a = float(x_arr[idx_a])
    x_b = float(x_arr[idx_b])
    x_c = float(x_arr[idx_c])
    y_a = float(y_arr[idx_a])
    y_b = float(y_arr[idx_b])
    y_c = float(y_arr[idx_c])

    vertex, denom = _three_point_vertex(x_a, x_b, x_c, y_a, y_b, y_c)
    if vertex is None:
        return float(x_arr[anchor_idx]), "medium"

    boundary_x = float(x_arr[anchor_idx])
    if boundary_direction < 0:
        if vertex < boundary_x:
            return vertex, "low_extrapolated"
        return boundary_x, "medium"
    else:
        if vertex > boundary_x:
            return vertex, "low_extrapolated"
        return boundary_x, "medium"
