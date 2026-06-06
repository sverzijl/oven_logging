"""Plotly figure builders for the Spatial Evolution tab (M30).

Consumes the :class:`~src.data.spatial_reconstruction.isothermal.IsothermalAssignment`
produced by ``track_isothermal`` and renders the moisture-front diagnostic:

* :func:`plot_isothermal_positions` — the HEADLINE view. The normalised
  spatial position of each tracked isotherm (60/80/100/110 °C) over time.
  The **100 °C front is the latent-heat / Stefan boundary** — the physical
  proxy for the drying/moisture front advancing inward through the dough.
* :func:`plot_fixed_position_temperatures` — temperature over time at the
  (time-invariant) geometric core and surface positions, with the S-curve
  landmark temperatures drawn as reference lines.

These are pure functions (no Streamlit) so they are unit-testable and reusable
by any future report.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import plotly.graph_objects as go

from config.constants import S_CURVE_BENCHMARKS
from src.visualization.visualization_config import VisualizationConfig


# Isotherm -> (human label with bread-chemistry meaning, vivid line colour).
# Vivid colours (not the pale S_CURVE_ZONES fills) so the four fronts read as
# distinct lines; the 100 °C moisture front is deliberately the prominent red.
ISOTHERM_META: dict = {
    60.0: ("Yeast kill (oven-spring end)", "#2ca02c"),
    80.0: ("Starch gelatinisation complete", "#ff7f0e"),
    100.0: ("Latent-heat / Stefan moisture front", "#d62728"),
    110.0: ("Browning / crust-onset", "#9467bd"),
}

# 110 °C crust-onset reference for the surface panel (no S_CURVE benchmark).
_CRUST_ONSET_C = 110.0

# The 100 °C latent-heat / Stefan boundary is the headline moisture front the
# tab promises; its absence is worth flagging even when lower isotherms move.
_MOISTURE_FRONT_C = 100.0


def _isotherm_label(temp_c: float) -> tuple:
    """Return (label, colour) for ``temp_c``, falling back gracefully."""
    return ISOTHERM_META.get(temp_c, (f"{int(temp_c)} °C", "#7f7f7f"))


def _front_state(arr) -> str:
    """Classify one isotherm's position track: ``never`` (no finite points),
    ``passed`` (flat at the probe tip x=0), ``stationary`` (flat elsewhere),
    or ``tracked`` (advances through a real range)."""
    fin = np.asarray(arr, dtype=float)
    fin = fin[np.isfinite(fin)]
    if fin.size == 0:
        return "never"
    if float(fin.max() - fin.min()) <= 1e-6:
        return "passed" if float(fin.max()) <= 1e-6 else "stationary"
    return "tracked"


def isotherm_coverage_warning(assignment) -> Optional[str]:
    """Explain when the isotherm fronts don't tell the moisture-front story.

    A front is *trackable* only if it has >= 2 finite stride positions spanning
    a real range (i.e. it advances through the probe).

    Two distinct degeneracies are surfaced:

    1. **No front moves at all** — every tracked isotherm is all-NaN (never
       enters the probe) or pinned flat (saturated at the probe tip). Panel B is
       all flat lines. That is the full-immersion case (the probe sits entirely
       inside the crumb plateauing ~98-100 °C from latent-heat boiling), so the
       crust-side drying front is beyond the sensors' reach.

    2. **The 100 °C moisture / Stefan front specifically is absent/degenerate**
       even though lower isotherms (60/80 °C) move (WAVE-A FOLLOW-UP a). This is
       the full-crumb (Wonder) bake: the headline 100 °C front the tab promises
       never reaches a sensor, so the operator must be told even though Panel B
       is not entirely flat.

    Returns a human explanation in either case, else ``None``.
    """
    states = {
        float(temp_c): _front_state(assignment.isotherm_positions[temp_c])
        for temp_c in assignment.isotherm_temps_C
    }
    never = [f"{int(t)} °C" for t, s in states.items() if s == "never"]
    passed = [f"{int(t)} °C" for t, s in states.items() if s == "passed"]
    stationary = [f"{int(t)} °C" for t, s in states.items() if s == "stationary"]
    tracked = [f"{int(t)} °C" for t, s in states.items() if s == "tracked"]

    # Case 2: at least one front moves, but the 100 °C moisture front does not.
    moisture_state = states.get(_MOISTURE_FRONT_C)
    if tracked and moisture_state is not None and moisture_state != "tracked":
        moving = ", ".join(sorted(tracked, key=lambda s: int(s.split()[0])))
        if moisture_state == "never":
            why = (
                "it never enters the probe (no sensor reaches 100 °C — the "
                "crumb plateaus just below boiling)"
            )
        elif moisture_state == "passed":
            why = "it sits pinned at the probe tip (every sensor is already hotter)"
        else:
            why = "it does not advance through the probe span"
        return (
            "The 100 °C moisture / Stefan front — the headline this tab tracks "
            f"— is not resolved on this bake: {why}. Lower isotherms ({moving}) "
            "do move, so Panel B is not entirely flat, but the drying front "
            "itself lives at the **crust**, beyond these sensors. This is the "
            "full-crumb case (e.g. the Wonder bakes). To capture the moisture "
            "front, insert the probe so its outer sensors pass through the "
            "crust into the oven air (the outer channels should read "
            "~120-180 °C)."
        )

    if tracked:
        return None

    parts = []
    if passed:
        parts.append(
            f"the {', '.join(passed)} front{'s' if len(passed) > 1 else ''} "
            "already sit at the probe tip (every sensor is hotter than that)"
        )
    if stationary:
        parts.append(
            f"the {', '.join(stationary)} front{'s' if len(stationary) > 1 else ''} "
            "do not move"
        )
    if never:
        parts.append(
            f"the {', '.join(never)} front{'s' if len(never) > 1 else ''} never "
            "enter the probe (no sensor gets that hot)"
        )
    detail = "; ".join(parts)
    return (
        "No temperature front moves through the probe span on this bake, so the "
        f"trajectories below are flat — {detail}.\n\n"
        "This is the full-immersion case: the probe sits entirely inside the "
        "crumb (which plateaus near 98-100 °C from latent-heat boiling), so the "
        "100 °C drying front — which lives at the **crust** — is outside the "
        "sensors' reach. To capture the moisture front, insert the probe so its "
        "outer sensors pass through the crust into the oven air (the outer "
        "channels should read ~120-180 °C, as in the ProbeData_1000BA3C bakes)."
    )


def plot_isothermal_positions(
    assignment,
    sensor_roles: Optional[dict] = None,
) -> go.Figure:
    """Panel B — isotherm spatial position (normalised x in [0, 1]) over time.

    For each tracked isotherm two traces are drawn: a smoothed line and the
    raw per-stride markers. The fixed core/surface positions are overlaid as
    dashed horizontal reference lines. ``x = 0`` is the probe tip (deepest /
    core side); ``x = 1`` is the probe stem (surface side). A front sitting at
    ``x = 0`` has advanced to the probe tip; NaN means the front is not present
    in the probe at that time.

    ``sensor_roles`` is accepted for signature parity with the other plotters
    (it can drive future role annotations) but is not required.
    """
    t_min = np.asarray(assignment.t_grid_s, dtype=float) / 60.0
    fig = go.Figure()

    for temp_c in assignment.isotherm_temps_C:
        label, colour = _isotherm_label(float(temp_c))
        smoothed = np.asarray(assignment.isotherm_positions[temp_c], dtype=float)
        raw = np.asarray(assignment.isotherm_positions_raw[temp_c], dtype=float)
        legend_name = f"{int(temp_c)} °C — {label}"

        # Raw markers (faint, no legend entry — the line carries the legend).
        fig.add_trace(
            go.Scatter(
                x=t_min,
                y=raw,
                mode="markers",
                name=f"{int(temp_c)} °C raw",
                marker=dict(color=colour, size=4, opacity=0.35),
                showlegend=False,
                hovertemplate=(
                    f"{int(temp_c)} °C<br>t=%{{x:.1f}} min"
                    "<br>x=%{y:.3f}<extra>raw</extra>"
                ),
            )
        )
        # Smoothed line.
        fig.add_trace(
            go.Scatter(
                x=t_min,
                y=smoothed,
                mode="lines",
                name=legend_name,
                line=dict(color=colour, width=2.5),
                connectgaps=False,
                hovertemplate=(
                    f"{legend_name}<br>t=%{{x:.1f}} min"
                    "<br>x=%{y:.3f}<extra></extra>"
                ),
            )
        )

    # Fixed core / surface reference lines (probe doesn't move).
    core_x = float(assignment.fixed_core_x)
    surf_x = float(assignment.fixed_surface_x)
    if np.isfinite(core_x):
        fig.add_hline(
            y=core_x,
            line=dict(color="#1f77b4", width=1.5, dash="dash"),
            annotation_text=f"core x = {core_x:.3f}",
            annotation_position="bottom left",
        )
    if np.isfinite(surf_x):
        fig.add_hline(
            y=surf_x,
            line=dict(color="#8c564b", width=1.5, dash="dash"),
            annotation_text=f"surface x = {surf_x:.3f}",
            annotation_position="top left",
        )

    layout = dict(VisualizationConfig.DEFAULT_LAYOUT)
    layout.update(
        title="Isotherm fronts — normalised position along the probe over time",
        xaxis_title="Time (minutes)",
        yaxis_title="Normalised position  (0 = probe tip / core,  1 = stem / surface)",
        legend=VisualizationConfig.HORIZONTAL_LEGEND,
    )
    fig.update_layout(**layout)
    # Clamp the y-axis to the probe domain so SavGol overshoot never escapes.
    fig.update_yaxes(range=[0.0, 1.0])
    return fig


def plot_fixed_position_temperatures(assignment) -> go.Figure:
    """Panel C — temperature at the fixed core and surface positions over time.

    Overlays the S-curve landmark temperatures (yeast kill, starch complete,
    arrival) and the 110 °C crust-onset reference as horizontal lines so the
    operator can read off when the core crosses each chemistry threshold.
    """
    t_min = np.asarray(assignment.t_grid_s, dtype=float) / 60.0
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=np.asarray(assignment.T_at_fixed_core_t, dtype=float),
            mode="lines",
            name="T at fixed core",
            line=dict(color="#1f77b4", width=2.5),
            hovertemplate="core<br>t=%{x:.1f} min<br>%{y:.1f} °C<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=t_min,
            y=np.asarray(assignment.T_at_fixed_surface_t, dtype=float),
            mode="lines",
            name="T at fixed surface",
            line=dict(color="#8c564b", width=2.5),
            hovertemplate="surface<br>t=%{x:.1f} min<br>%{y:.1f} °C<extra></extra>",
        )
    )

    # S-curve landmark reference temperatures + crust onset.
    for key, spec in S_CURVE_BENCHMARKS.items():
        temp = float(spec["temperature"])
        fig.add_hline(
            y=temp,
            line=dict(color="#999999", width=1, dash="dot"),
            annotation_text=f"{key.replace('_', ' ').title()} ({temp:.0f} °C)",
            annotation_position="right",
        )
    fig.add_hline(
        y=_CRUST_ONSET_C,
        line=dict(color="#9467bd", width=1, dash="dot"),
        annotation_text=f"Crust onset ({_CRUST_ONSET_C:.0f} °C)",
        annotation_position="right",
    )

    layout = dict(VisualizationConfig.DEFAULT_LAYOUT)
    layout.update(
        title="Temperature at fixed core / surface positions",
        xaxis_title="Time (minutes)",
        yaxis_title="Temperature (°C)",
        legend=VisualizationConfig.HORIZONTAL_LEGEND,
    )
    fig.update_layout(**layout)
    return fig
