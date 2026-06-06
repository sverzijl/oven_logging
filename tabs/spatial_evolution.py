"""Spatial Evolution tab (M30) — the moisture-front timeline.

Surfaces the M24 isothermal-front tracker interactively. The headline view
(Panel B) is the spatial position of the 60/80/100/110 °C isotherms over time;
the **100 °C front is the latent-heat / Stefan boundary**, the physical proxy
for the drying/moisture front advancing inward through the loaf.

The inverse-problem effort (M7–M21) established that moisture *content* cannot
be reconstructed from the probe temperatures (a structural ~6 °C information
floor), so this tab shows the directly-measurable front positions instead of an
inferred moisture field.

Layout:
  • conditional core-confidence banner + full-immersion note
  • metrics row (fixed core/surface position, end core/surface temperature)
  • Panel A — raw sensor temperatures (reuses ThermalPlotter)
  • Panel B — isotherm fronts over time  [headline]
  • Panel C — temperature at the fixed core / surface positions
  • footer with tracking parameters + recompute wall time
"""

from __future__ import annotations

import time
from typing import Optional

import numpy as np
import streamlit as st

from src.ui.sensor_role_helpers import build_sensor_role_map
from src.visualization.plots import ThermalPlotter
from src.visualization.spatial_evolution_plots import (
    plot_fixed_position_temperatures,
    plot_isothermal_positions,
)


def confidence_banner_text(
    confidence: Optional[str], reason: Optional[str]
) -> tuple:
    """Map a core-confidence label to a (banner_kind, message) pair.

    The classifier collapses Method 1's ``low_extrapolated`` to the plain
    ``"low"`` enum (the qualifier survives in ``reason``). Mapping:

    * ``"low"``    -> ``("warning", ...)`` — invite bake-metadata entry.
    * ``"medium"`` -> ``("caption", reason)`` — boundary estimate.
    * anything else (``"high"`` / ``None``) -> ``(None, None)`` — no banner.
    """
    if confidence == "low":
        message = (
            "⚠️ Core position extrapolated past the probe tip. Enter loaf "
            "thickness and probe insertion depth in the sidebar **Bake "
            "Metadata** expander for a high-accuracy geometric core."
        )
        if reason:
            message += f"  ({reason})"
        return ("warning", message)
    if confidence == "medium":
        return ("caption", reason or "Core position is a boundary estimate.")
    return (None, None)


def _core_confidence(assignment) -> tuple:
    """Read (confidence, reason) from the embedded full-bake classification."""
    classification = getattr(assignment, "classification", None)
    if classification is None:
        return (None, None)
    core = getattr(classification, "core_assignment", None)
    if core is None:
        return (None, None)
    return (getattr(core, "confidence", None), getattr(core, "reason", None))


def _last_finite(arr) -> float:
    a = np.asarray(arr, dtype=float)
    finite = a[np.isfinite(a)]
    return float(finite[-1]) if finite.size else float("nan")


def _fmt_temp(value: float) -> str:
    return f"{value:.1f} °C" if np.isfinite(value) else "—"


def render():
    st.header("🌡️ Spatial Evolution — moisture-front timeline")
    st.caption(
        "Tracks where the 60 / 80 / 100 / 110 °C isotherms sit along the probe "
        "over time. The 100 °C front is the latent-heat / Stefan boundary — the "
        "physical proxy for the drying / moisture front."
    )

    loader = st.session_state.loader
    curve_index = st.session_state.current_curve_index
    data = st.session_state.data

    t0 = time.perf_counter()
    assignment = loader.isothermal_assignment(curve_index)
    compute_s = time.perf_counter() - t0

    if assignment is None or np.asarray(assignment.t_grid_s).size == 0:
        st.info(
            "Not enough samples in this curve to track isotherm fronts "
            "(the bake is shorter than one tracking stride)."
        )
        return

    # --- Confidence banner (core) + full-immersion note -------------------
    confidence, reason = _core_confidence(assignment)
    kind, message = confidence_banner_text(confidence, reason)
    if kind == "warning":
        st.warning(message)
    elif kind == "caption":
        st.caption(message)

    classification = getattr(assignment, "classification", None)
    if classification is not None and getattr(
        classification, "surface_assignment", None
    ) is None:
        st.info(
            "Full-immersion bake — no dough/air interface detected; the "
            "surface reference is anchored at the probe stem (x = 1)."
        )

    # --- Metrics row ------------------------------------------------------
    T_core_end = _last_finite(assignment.T_at_fixed_core_t)
    T_surf_end = _last_finite(assignment.T_at_fixed_surface_t)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Core position x", f"{assignment.fixed_core_x:.3f}")
    if confidence:
        c1.caption(f"core confidence: {confidence}")
    c2.metric("Surface position x", f"{assignment.fixed_surface_x:.3f}")
    c3.metric("Core T (end)", _fmt_temp(T_core_end))
    c4.metric("Surface T (end)", _fmt_temp(T_surf_end))

    sensor_roles = build_sensor_role_map(loader, curve_index)

    # --- Panel A — raw sensor temperatures (reuse ThermalPlotter) ---------
    st.subheader("Sensor temperatures")
    plotter = ThermalPlotter()
    fig_a = plotter.plot_temperature_profile(
        data,
        show_zones=st.session_state.get("show_zones", True),
        sensor_roles=sensor_roles,
    )
    st.plotly_chart(fig_a, use_container_width=True)

    # --- Panel B — isotherm fronts (headline) -----------------------------
    st.subheader("Isotherm fronts — 100 °C is the moisture / Stefan front")
    fig_b = plot_isothermal_positions(assignment, sensor_roles=sensor_roles)
    st.plotly_chart(fig_b, use_container_width=True)

    # --- Panel C — fixed-position temperatures ----------------------------
    st.subheader("Temperature at the fixed core / surface positions")
    fig_c = plot_fixed_position_temperatures(assignment)
    st.plotly_chart(fig_c, use_container_width=True)

    # --- Footer -----------------------------------------------------------
    footer = (
        f"Tracked at 30 s stride · 120 s Savitzky-Golay window · "
        f"recompute {compute_s:.2f} s"
    )
    if compute_s > 2.0:
        footer += "  ⚠️ above the 2 s budget"
    st.caption(footer)
