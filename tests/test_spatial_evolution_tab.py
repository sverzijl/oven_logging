"""Pure-helper tests for the Spatial Evolution tab (M30).

The repo has no Streamlit AppTest harness, so the tab's testable surface is
its pure helpers: the isotherm metadata table, the two plotly figure builders
in ``src/visualization/spatial_evolution_plots.py``, and the confidence-banner
predicate in ``tabs/spatial_evolution.py``. The ``render()`` entry point is
verified by visual inspection / the empirical red-cell sweep, not here.
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.isothermal import (  # noqa: E402
    DEFAULT_ISOTHERMS_C,
    IsothermalAssignment,
)
from src.visualization.spatial_evolution_plots import (  # noqa: E402
    ISOTHERM_META,
    isotherm_coverage_warning,
    plot_isothermal_positions,
    plot_fixed_position_temperatures,
)


def _make_assignment(
    n: int = 20,
    isotherms=DEFAULT_ISOTHERMS_C,
    all_nan: bool = False,
) -> IsothermalAssignment:
    """Build a synthetic IsothermalAssignment with finite (or all-NaN) data."""
    t_grid = np.arange(n, dtype=float) * 30.0
    positions = {}
    positions_raw = {}
    for k, T in enumerate(isotherms):
        if all_nan:
            arr = np.full(n, np.nan, dtype=float)
        else:
            # Higher isotherms sit nearer the surface (higher x); all drift in.
            base = 0.9 - 0.1 * k
            arr = np.clip(base - np.linspace(0.0, 0.4, n), 0.0, 1.0)
        positions[T] = arr
        positions_raw[T] = arr.copy()
    return IsothermalAssignment(
        t_grid_s=t_grid,
        isotherm_temps_C=tuple(isotherms),
        isotherm_positions=positions,
        isotherm_positions_raw=positions_raw,
        fixed_core_x=0.1,
        fixed_surface_x=0.8,
        T_at_fixed_core_t=np.linspace(25.0, 96.0, n),
        T_at_fixed_surface_t=np.linspace(25.0, 108.0, n),
        classification=None,  # type: ignore[arg-type]
    )


class TestIsothermMeta:

    def test_isotherm_meta_covers_default_isotherms(self):
        assert set(ISOTHERM_META) == set(DEFAULT_ISOTHERMS_C)

    def test_isotherm_meta_entries_are_label_colour_pairs(self):
        for T, meta in ISOTHERM_META.items():
            assert isinstance(T, float)
            label, colour = meta
            assert isinstance(label, str) and label
            assert isinstance(colour, str) and colour.startswith("#")

    def test_100C_labelled_as_moisture_front(self):
        label, _ = ISOTHERM_META[100.0]
        assert "stefan" in label.lower() or "latent" in label.lower()


class TestPlotIsothermalPositions:

    def test_returns_two_traces_per_isotherm(self):
        assignment = _make_assignment()
        fig = plot_isothermal_positions(assignment)
        # One smoothed-line + one raw-marker trace per isotherm.
        assert len(fig.data) == 2 * len(DEFAULT_ISOTHERMS_C)

    def test_each_isotherm_temperature_named_in_legend(self):
        assignment = _make_assignment()
        fig = plot_isothermal_positions(assignment)
        names_blob = " ".join(str(tr.name) for tr in fig.data)
        for T in DEFAULT_ISOTHERMS_C:
            assert f"{int(T)}" in names_blob

    def test_y_axis_clamped_to_unit_interval(self):
        assignment = _make_assignment()
        fig = plot_isothermal_positions(assignment)
        assert tuple(fig.layout.yaxis.range) == (0.0, 1.0)

    def test_handles_all_nan_without_error(self):
        assignment = _make_assignment(all_nan=True)
        fig = plot_isothermal_positions(assignment)  # must not raise
        assert len(fig.data) == 2 * len(DEFAULT_ISOTHERMS_C)


class TestIsothermCoverageWarning:

    def test_moving_fronts_have_no_warning(self):
        assignment = _make_assignment()  # fronts drift inward -> trackable
        assert isotherm_coverage_warning(assignment) is None

    def test_all_nan_fronts_warn_about_crust(self):
        assignment = _make_assignment(all_nan=True)
        msg = isotherm_coverage_warning(assignment)
        assert msg is not None
        assert "crust" in msg.lower()
        assert "full-immersion" in msg.lower()
        assert "never enter" in msg.lower()

    def test_flat_at_tip_warns_about_probe_tip(self):
        # All fronts pinned at x=0 (every sensor hotter than the targets).
        n = 20
        t_grid = np.arange(n, dtype=float) * 30.0
        positions = {T: np.zeros(n, dtype=float) for T in DEFAULT_ISOTHERMS_C}
        assignment = IsothermalAssignment(
            t_grid_s=t_grid,
            isotherm_temps_C=tuple(DEFAULT_ISOTHERMS_C),
            isotherm_positions=positions,
            isotherm_positions_raw={T: a.copy() for T, a in positions.items()},
            fixed_core_x=0.1,
            fixed_surface_x=0.8,
            T_at_fixed_core_t=np.full(n, 99.0),
            T_at_fixed_surface_t=np.full(n, 99.0),
            classification=None,  # type: ignore[arg-type]
        )
        msg = isotherm_coverage_warning(assignment)
        assert msg is not None
        assert "probe tip" in msg.lower()


class TestPlotFixedPositionTemperatures:

    def test_returns_core_and_surface_traces(self):
        assignment = _make_assignment()
        fig = plot_fixed_position_temperatures(assignment)
        assert len(fig.data) >= 2
        names_blob = " ".join(str(tr.name).lower() for tr in fig.data)
        assert "core" in names_blob
        assert "surface" in names_blob
