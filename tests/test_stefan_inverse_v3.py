"""M21 HMS Onslaught — tests for the 6-param Stefan inverse v3 (with
distributed side-heat source).

Four tests:

1. ``test_forward_S_zero_reproduces_v2`` — with ``Q_side=0``, the v3
   forward output matches the M9 ``solve_stefan_forward`` (v2 reuses)
   within 0.01 K at every timestep / position.

2. ``test_forward_S_nonzero_warms_interior`` — with a meaningfully large
   Q_side, the mid-depth temperature trajectory is everywhere ≥ the
   Q_side=0 case, with a non-trivial gap during the bake.

3. ``test_inverse_recovers_synthetic_Q_side`` — synthesise a bake with
   a known Q_side, recover via the inverter, check 30% relative recovery.

4. ``test_single_fixture_BA3C_0946_decision_gate`` — load BA3C_0946,
   run the v3 fitter, assert main-bake RMSE < 4 °C AND ≥4/6 params
   interior. **This is the M21 decision gate.**
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.stefan_inverse import (  # noqa: E402
    solve_stefan_forward,
)
from src.data.spatial_reconstruction.stefan_inverse_v3 import (  # noqa: E402
    fit_stefan_inverse_v3,
    solve_stefan_forward_v3,
)
from tests.test_heat_equation_research import (  # noqa: E402
    REAL_FIXTURES,
    SENSOR_NAMES,
    SENSOR_POSITIONS,
    _segmented_real_fixture,
)


def _segment_main_mask(n_t: int) -> np.ndarray:
    idx = np.arange(n_t)
    frac = idx / max(n_t - 1, 1)
    return (frac >= 0.10) & (frac < 0.90)


# ---------------------------------------------------------------------------
# Forward sanity
# ---------------------------------------------------------------------------


def test_forward_S_zero_reproduces_v2():
    """``solve_stefan_forward_v3(Q_side=0)`` must equal the M9 solver."""
    t = np.linspace(0.0, 1500.0, 200)
    surf = np.linspace(25.0, 200.0, 200)
    sample_x = np.array([0.0, 0.2, 0.4, 0.6])

    common = dict(
        x_core=-0.05,
        x_surface=0.7,
        alpha_dough=8e-7,
        alpha_crust=5e-7,
        rhoL_eff=100.0,
        t_grid=t,
        T_surface_series=surf,
        T_initial=25.0,
        n_spatial=40,
        sample_x=sample_x,
        delta_T_smear=5.0,
    )
    T_v2 = solve_stefan_forward(**common)
    T_v3 = solve_stefan_forward_v3(**common, Q_side=0.0)
    assert T_v2.shape == T_v3.shape
    # Tolerance 0.01 K covers the ODE solver's repeated runs being seeded
    # at the same step pattern under the same RHS — exact equality isn't
    # guaranteed because BDF uses adaptive step heuristics.
    diff = np.max(np.abs(T_v2 - T_v3))
    assert diff < 0.01, f"v3 with Q_side=0 deviates from v2 by {diff:.4f} K"


def test_forward_S_nonzero_warms_interior():
    """A non-zero Q_side must warm the interior vs the Q_side=0 case."""
    t = np.linspace(0.0, 1500.0, 200)
    surf = np.linspace(25.0, 200.0, 200)
    # Sample the interior including mid-depth (where w(x) peaks at 1).
    sample_x = np.array([0.0, 0.15, 0.30, 0.45, 0.6])
    # Ramp the oven driving signal to roughly mirror the surface BC.
    g_t = np.clip((surf - 25.0) / (200.0 - 25.0), 0.0, 1.0)

    common = dict(
        x_core=-0.05,
        x_surface=0.7,
        alpha_dough=8e-7,
        alpha_crust=5e-7,
        rhoL_eff=100.0,
        t_grid=t,
        T_surface_series=surf,
        T_initial=25.0,
        n_spatial=40,
        sample_x=sample_x,
        delta_T_smear=5.0,
        g_oven_series=g_t,
    )
    T_zero = solve_stefan_forward_v3(**common, Q_side=0.0)
    T_high = solve_stefan_forward_v3(**common, Q_side=1e5)

    # At every interior sample the high-source bake is at least as warm
    # as the no-source bake.
    delta = T_high - T_zero
    assert np.all(delta >= -1e-6), (
        f"Q_side=1e5 produces colder interior than Q_side=0 somewhere; "
        f"min delta = {delta.min():.3f} K"
    )
    # And the gap is non-trivial at mid-depth (sample index 2 ≈ x=0.30,
    # mid-depth of [-0.05, 0.7] is ≈ 0.325). At least 1 K warmer somewhere.
    assert delta.max() > 1.0, (
        f"Q_side=1e5 fails to warm interior by > 1 K anywhere; "
        f"max delta = {delta.max():.3f} K"
    )


# ---------------------------------------------------------------------------
# Inverse recovery on a synthetic
# ---------------------------------------------------------------------------


def test_inverse_recovers_synthetic_Q_side():
    """Synthesise at known Q_side, check inverse recovers within 30%.

    Note on units: ``alpha_dough/_crust`` are in **normalised** position
    units (α_SI / loaf_thickness²). The v3 bounds are in normalised units
    (centred near α_norm ≈ 3e-4), so the synthetic uses values inside
    those bounds so the inverter can land on the truth without bouncing
    off boundaries. Q_side stays in W/m³ throughout.
    """
    Q_side_true = 5e4  # W/m³
    alpha_dough_true = 5e-4  # normalised; within BOUNDS_V3["alpha_dough"]
    alpha_crust_true = 3e-4  # normalised; within BOUNDS_V3["alpha_crust"]
    rhoL_true = 100.0
    smear_true = 5.0
    x_core_true = -0.02
    x_surface = 0.7

    n_t = 240
    period_s = 5.0
    t = np.arange(n_t, dtype=float) * period_s
    half = n_t // 2
    surf = np.empty(n_t)
    surf[:half] = np.linspace(25.0, 200.0, half)
    surf[half:] = 200.0

    in_dough = ("T1", "T2", "T3", "T4", "T5")
    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs = np.array([pos_map[s] for s in in_dough])

    # Oven-driving signal: shape similar to a real bake — ramp then plateau.
    g_t = np.clip((surf - 25.0) / (200.0 - 25.0), 0.0, 1.0)

    T_synth = solve_stefan_forward_v3(
        x_core=x_core_true,
        x_surface=x_surface,
        alpha_dough=alpha_dough_true,
        alpha_crust=alpha_crust_true,
        rhoL_eff=rhoL_true,
        t_grid=t,
        T_surface_series=surf,
        T_initial=25.0,
        Q_side=Q_side_true,
        g_oven_series=g_t,
        n_spatial=80,
        sample_x=x_obs,
        delta_T_smear=smear_true,
    )
    rng = np.random.default_rng(123)
    T_synth = T_synth + rng.normal(0.0, 0.3, size=T_synth.shape)

    df = pd.DataFrame({"Timestamp": t})
    for k, s in enumerate(in_dough):
        df[s] = T_synth[:, k]
    # Fill remaining sensors with the surface BC so the surface
    # interpolator and the ambient-extractor have plausible inputs.
    for s in SENSOR_NAMES:
        if s not in df.columns:
            df[s] = surf

    # Pre-pass g_t to the inverter (the synthetic ambient is just `surf`,
    # so the inferred g would equal g_t — but we pass explicitly to make
    # the test independent of the inference path).
    g_full = g_t.copy()

    result = fit_stefan_inverse_v3(
        df=df,
        in_dough_sensors=list(in_dough),
        x_surface_continuous=x_surface,
        downsample_factor=4,
        n_spatial=30,
        max_iter=900,
        g_oven_series=g_full,
    )

    # 30% recovery on Q_side.
    Q_fit = result["Q_side"]
    rel_err_Q = abs(Q_fit - Q_side_true) / Q_side_true
    assert rel_err_Q < 0.30, (
        f"Q_side recovery: fit={Q_fit:.3e} vs true={Q_side_true:.3e}; "
        f"rel_err={rel_err_Q:.2%}"
    )
    # In-sample RMSE on a clean synthetic should be modest.
    assert result["rmse_per_sensor"] < 3.0, (
        f"synthetic RMSE = {result['rmse_per_sensor']:.2f} °C; expected < 3"
    )


# ---------------------------------------------------------------------------
# Decision gate
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_single_fixture_BA3C_0946_decision_gate():
    """M21 decision gate: BA3C_0946 main-bake RMSE < 4 °C AND ≥4/6 interior."""
    spec = next(s for s in REAL_FIXTURES if s["label"] == "BA3C_0946")
    df = _segmented_real_fixture(spec)
    x_surface_continuous = 0.6786994367639527  # M9-cached, apples-to-apples

    result = fit_stefan_inverse_v3(
        df=df,
        in_dough_sensors=spec["in_dough"],
        x_surface_continuous=x_surface_continuous,
        downsample_factor=4,
        n_spatial=30,
        max_iter=700,
    )

    # Recompute main-bake RMSE.
    from src.data.spatial_reconstruction.profile import (
        interpolate_temperature_series_at,
    )

    pos_map = dict(zip(SENSOR_NAMES, SENSOR_POSITIONS))
    x_obs = np.array([pos_map[s] for s in spec["in_dough"]])
    t_full = df["Timestamp"].to_numpy(dtype=float)
    sl = slice(0, len(t_full), 4)
    t_obs = t_full[sl]
    T_cols = [df[s].to_numpy(dtype=float)[sl] for s in spec["in_dough"]]
    T_obs = np.column_stack(T_cols)
    surface_full = interpolate_temperature_series_at(
        df,
        positions=SENSOR_POSITIONS,
        x_target=x_surface_continuous,
        sensors=SENSOR_NAMES,
    ).to_numpy(dtype=float)
    T_surf_obs = np.interp(t_obs, t_full, surface_full)
    T_initial = float(np.mean(T_obs[0, :]))

    # Re-build g_obs at t_obs using the same path as the fitter.
    from src.data.spatial_reconstruction.stefan_inverse_v3 import (
        _build_g_oven_from_ambient,
    )

    g_obs = _build_g_oven_from_ambient(
        df=df,
        sensor_names=SENSOR_NAMES,
        sensor_positions_normalised=SENSOR_POSITIONS,
        x_surface_continuous=x_surface_continuous,
        t_target=t_obs,
        T_initial_dough=T_initial,
    )

    T_pred = solve_stefan_forward_v3(
        x_core=result["x_core"],
        x_surface=x_surface_continuous,
        alpha_dough=result["alpha_dough"],
        alpha_crust=result["alpha_crust"],
        rhoL_eff=result["rhoL_eff"],
        t_grid=t_obs,
        T_surface_series=T_surf_obs,
        T_initial=T_initial,
        Q_side=result["Q_side"],
        g_oven_series=g_obs,
        n_spatial=30,
        sample_x=x_obs,
        delta_T_smear=result["delta_T_smear"],
    )
    residual = T_pred - T_obs
    main_mask = _segment_main_mask(residual.shape[0])
    rmse_main = float(np.sqrt(np.mean(residual[main_mask, :] ** 2)))

    n_at_bound = int(result.get("n_at_bound", 99))
    n_interior = 6 - n_at_bound

    assert rmse_main < 4.0 and n_interior >= 4, (
        f"M21 decision gate: BA3C_0946 main-bake RMSE = {rmse_main:.2f} °C, "
        f"n_interior = {n_interior}/6 (bar: RMSE < 4 °C AND interior ≥ 4). "
        f"Fitted: x_core={result['x_core']:.3f}, "
        f"alpha_dough={result['alpha_dough']:.2e}, "
        f"alpha_crust={result['alpha_crust']:.2e}, "
        f"rhoL_eff={result['rhoL_eff']:.1f}, "
        f"smear={result['delta_T_smear']:.2f}, "
        f"Q_side={result['Q_side']:.3e} W/m³. "
        f"param_at_bound={result['param_at_bound']}"
    )
