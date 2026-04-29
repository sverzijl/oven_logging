"""M21 (research-only): 1D Stefan inverse with distributed side-heat source.

Background — see ``stefan_inverse_v2.py`` for the M20 5-parameter baseline.
Eighteen prior inverse-problem missions (M7-M20) all assumed strictly 1D
conduction along the probe axis. M20 freed α_dough and Δ_T_smear in their
RCA-recommended bounds and produced main-bake RMSE = 5.73 °C on BA3C_0946
(M9 baseline 5.76 °C) — no improvement. The structural information limit
verdict survived the test.

The hypothesis nobody had tested until now: **heat enters from the sides
of the tin too**. The tin walls are heated by oven air; lateral conduction
through the dough is comparable in magnitude to vertical conduction;
deeper sensors receive heat from sidewalls that 1D-from-top cannot
explain. M21 extends the M20 forward + inverse with a position-dependent
volumetric heat source ``S(x, t)`` representing the sidewall flux:

    ρ·c_p · ∂T/∂t = k · ∂²T/∂x² + S(x, t)

In α-form (since α = k / (ρ·c_p)) this becomes:

    ∂T/∂t = α · ∂²T/∂x² + S(x, t) / (ρ·c_p)

The source is parametrised as::

    S(x, t) = Q_side · w(x) · g_oven(t)

where:

* ``Q_side`` (W/m³) — magnitude, the new free parameter (6th total).
* ``w(x)`` — position weighting; tent function peaked at mid-depth:
  ``w(x) = 1 - 2·|x_norm/L_norm - 0.5|``. A linear taper from 1 at
  mid-depth to 0 at top and bottom. Captures the physical intuition
  that sidewall flux is uniformly distributed along the probe axis,
  with zero at the corners where the tin floor meets walls.
* ``g_oven(t)`` — temporal profile; uses the observed ambient sensor
  series normalised to [0, 1]: ``g(t) = (T_air(t) - T_initial) /
  (T_air_max - T_initial)``. Couples the side-heat injection to the
  observed oven temperature curve.

Hardcoded thermophysical constants (matching M9 / M20 conventions for
density and heat capacity of dough): ρ = 1000 kg/m³, c_p = 2000 J/(kg·K).
``S_norm = Q_side / (ρ·c_p)`` carries units of K/s and is added directly
to ``dT/dt`` in the method-of-lines RHS — no further normalisation needed
because the LHS of the heat equation is already in K/s.

Public API:

* :func:`solve_stefan_forward_v3` — forward solver with side-source term;
  copies the M9 enthalpy-method body and adds the source inline.
* :func:`fit_stefan_inverse_v3` — joint 6-parameter Nelder-Mead fit.
* :data:`PARAM_NAMES_V3`, :data:`BOUNDS_V3`, :data:`INIT_V3`.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import minimize

from .heat_equation import _numerical_hessian
from .stefan_inverse import (
    T_FRONT_C,
    _alpha_eff_factory,
    _build_observation_matrix,
)
from .stefan_inverse_v2 import BOUNDS_V2, INIT_V2, _SI_TO_NORM, _bound_status


# Pinned thermophysical constants for the side-source unit conversion.
# RHO * CP = 2.0e6 J/(m³·K). With Q_side in W/m³, S_norm = Q_side / (RHO_CP)
# carries units of K/s — the rate at which a unit of volumetric heat
# adds to the local temperature. This is added directly to dT/dt.
RHO_DOUGH = 1000.0  # kg/m³
CP_DOUGH = 2000.0  # J/(kg·K)
RHO_CP_DOUGH = RHO_DOUGH * CP_DOUGH  # 2.0e6 J/(m³·K)


# Bounds. Reuse M20's bounds for the first five params; add Q_side.
# Q_side ∈ (0, 5e5) W/m³ — rough order-of-magnitude estimate from the
# briefing: h ~ 50 W/(m²K) · ΔT ~ 150 K · (perimeter/area ~ 100/m) ≈ 7.5e5
# W/m³ at the upper end. Lower bound 0 lets the fit recover the no-side-
# heat case (returning to M20 behaviour).
BOUNDS_V3 = {
    **BOUNDS_V2,
    "Q_side": (0.0, 5e5),
}

# Initial values. Re-use M20's central inits; start Q_side at 1e4 W/m³
# (a small but non-zero value so the optimiser sees a finite gradient
# in the source-term direction immediately).
INIT_V3 = {
    **INIT_V2,
    "Q_side": 1e4,
}

PARAM_NAMES_V3 = (
    "x_core_normalised",
    "alpha_dough",
    "alpha_crust",
    "rhoL_eff",
    "delta_T_smear",
    "Q_side",
)


# ---------------------------------------------------------------------------
# Forward solver — M9 body + distributed side-source
# ---------------------------------------------------------------------------


def solve_stefan_forward_v3(
    x_core: float,
    x_surface: float,
    alpha_dough: float,
    alpha_crust: float,
    rhoL_eff: float,
    t_grid: np.ndarray,
    T_surface_series: np.ndarray,
    T_initial: float,
    Q_side: float = 0.0,
    g_oven_series: Optional[np.ndarray] = None,
    n_spatial: int = 60,
    sample_x: Optional[np.ndarray] = None,
    delta_T_smear: float = 1.0,
) -> np.ndarray:
    """Solve the 1D Stefan + distributed side-source problem.

    Same geometry/BCs/numerics as :func:`solve_stefan_forward` but with
    an extra source term in the method-of-lines RHS::

        dT/dt[i] = α_eff(T[i]) · T_xx[i] + S_norm · w(x[i]) · g(t)

    where ``S_norm = Q_side / (ρ·c_p)``, ``w(x) = 1 - 2·|x_n - 0.5|``
    with ``x_n = (x - x_core) / (x_surface - x_core)`` (the normalised
    position within the dough column), and ``g(t)`` is the oven-driven
    temporal profile passed via ``g_oven_series`` (interpolated onto t).

    Parameters
    ----------
    Q_side:
        Side-source magnitude in W/m³. Set to 0 to disable (this branch
        must reproduce :func:`solve_stefan_forward` exactly).
    g_oven_series:
        Optional temporal profile sampled at ``t_grid``. Should already
        be normalised to roughly [0, 1] (the side-source magnitude lives
        in ``Q_side``). If ``None`` a constant 1.0 profile is used.

    Returns
    -------
    np.ndarray, shape ``(len(t_grid), len(sample_x))``
    """
    # Argument validation matches M9 + add Q_side ≥ 0.
    if alpha_dough <= 0:
        raise ValueError(f"alpha_dough must be > 0, got {alpha_dough}")
    if alpha_crust <= 0:
        raise ValueError(f"alpha_crust must be > 0, got {alpha_crust}")
    if rhoL_eff < 0:
        raise ValueError(f"rhoL_eff must be >= 0, got {rhoL_eff}")
    if Q_side < 0:
        raise ValueError(f"Q_side must be >= 0, got {Q_side}")
    if x_surface <= x_core:
        raise ValueError(
            f"x_surface ({x_surface}) must exceed x_core ({x_core})"
        )
    t_grid = np.asarray(t_grid, dtype=float)
    T_surface_series = np.asarray(T_surface_series, dtype=float)
    if t_grid.size != T_surface_series.size:
        raise ValueError(
            "t_grid and T_surface_series must be the same length"
        )
    if t_grid.size < 2:
        raise ValueError("t_grid needs at least 2 samples")

    N = int(n_spatial)
    if N < 6:
        raise ValueError(f"n_spatial must be >= 6 for Stefan, got {N}")

    x_grid = np.linspace(x_core, x_surface, N)
    dx = float(x_grid[1] - x_grid[0])
    dx2 = dx * dx

    alpha_eff = _alpha_eff_factory(
        alpha_dough=alpha_dough,
        alpha_crust=alpha_crust,
        rhoL_eff=rhoL_eff,
        delta_T_smear=delta_T_smear,
    )

    t0 = float(t_grid[0])
    t_end = float(t_grid[-1])

    def _surface_at(t: float) -> float:
        if t <= t0:
            return float(T_surface_series[0])
        if t >= t_end:
            return float(T_surface_series[-1])
        return float(np.interp(t, t_grid, T_surface_series))

    # Side-source machinery: precompute w(x) once on the spatial grid,
    # build a g(t) interpolant if provided, fold the unit conversion into
    # S_norm.
    S_norm = float(Q_side) / RHO_CP_DOUGH  # K/s when w·g = 1

    # w(x): normalised position within the dough column,
    #   x_n = (x - x_core) / (x_surface - x_core) ∈ [0, 1]
    # tent peaked at 0.5: w = 1 - 2·|x_n - 0.5|
    column_len = x_surface - x_core
    x_norm = (x_grid - x_core) / column_len
    w_x = 1.0 - 2.0 * np.abs(x_norm - 0.5)
    w_x = np.clip(w_x, 0.0, 1.0)

    if g_oven_series is None:
        # Default: constant unity (S_norm dominates).
        def _g_at(t: float) -> float:
            return 1.0
    else:
        g_oven_series = np.asarray(g_oven_series, dtype=float)
        if g_oven_series.size != t_grid.size:
            raise ValueError(
                "g_oven_series must match t_grid length"
            )

        def _g_at(t: float) -> float:
            if t <= t0:
                return float(g_oven_series[0])
            if t >= t_end:
                return float(g_oven_series[-1])
            return float(np.interp(t, t_grid, g_oven_series))

    alpha_max = float(max(alpha_dough, alpha_crust))

    # Precompute the source contribution at each node — it depends only
    # on x (w_x) and t (g_t), not on T, so we can split α·T_xx (T-dependent)
    # from S·w·g (T-independent) cleanly.
    def _rhs(t: float, T: np.ndarray) -> np.ndarray:
        a_local = alpha_eff(T)
        dTdt = np.empty_like(T)
        # Neumann at core (i=0): ghost cell T[-1] = T[1].
        dTdt[0] = a_local[0] * 2.0 * (T[1] - T[0]) / dx2
        # Interior central differences with frozen-coefficient α.
        dTdt[1:-1] = a_local[1:-1] * (T[:-2] - 2.0 * T[1:-1] + T[2:]) / dx2
        # Dirichlet stiff clamp at the surface.
        T_surf = _surface_at(t)
        tau = 0.05 * dx2 / max(alpha_max, 1e-9)
        dTdt[-1] = (T_surf - T[-1]) / tau
        # Add the side source. The surface node is dominated by the stiff
        # clamp (Dirichlet); we deliberately leave it out of the source
        # injection to preserve BC consistency.
        if S_norm > 0:
            g_t = _g_at(t)
            src = S_norm * w_x * g_t
            dTdt[:-1] = dTdt[:-1] + src[:-1]
        return dTdt

    T0 = np.full(N, float(T_initial))
    T0[-1] = float(T_surface_series[0])

    sol = solve_ivp(
        _rhs,
        t_span=(t0, t_end),
        y0=T0,
        t_eval=t_grid,
        method="BDF",
        rtol=1e-4,
        atol=1e-5,
        dense_output=False,
    )
    if not sol.success:
        raise RuntimeError(f"solve_ivp failed: {sol.message}")

    T_xt = sol.y.T  # (n_t, N)
    if sample_x is None:
        return T_xt
    sample_x = np.asarray(sample_x, dtype=float)
    out = np.empty((T_xt.shape[0], sample_x.size), dtype=float)
    for i in range(T_xt.shape[0]):
        out[i, :] = np.interp(sample_x, x_grid, T_xt[i, :])
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_g_oven_from_ambient(
    df: pd.DataFrame,
    sensor_names: tuple,
    sensor_positions_normalised: tuple,
    x_surface_continuous: float,
    t_target: np.ndarray,
    T_initial_dough: float,
) -> np.ndarray:
    """Build the normalised oven-temperature profile g(t) from the data.

    The "ambient" channel is taken as the warmest sensor outside the
    dough column — i.e. the maximum across sensors whose normalised
    positions lie strictly above ``x_surface_continuous``. This treats
    the in-air thermometry as a measurement of the oven-driving curve.
    Normalisation: ``g(t) = (T_air(t) - T_init) / max(T_air - T_init)``.
    Clipped to [0, 1] to keep the source term non-negative.
    """
    pos_map = dict(zip(sensor_names, sensor_positions_normalised))
    air_sensors = [
        s for s, p in pos_map.items() if p > x_surface_continuous + 1e-3
    ]
    t_full = df["Timestamp"].to_numpy(dtype=float)
    if not air_sensors:
        # No ambient sensor available — fall back to the surface column
        # as the proxy. This is a graceful degradation; in practice every
        # real fixture has at least one ambient sensor.
        air_proxy = df[sensor_names[-1]].to_numpy(dtype=float)
    else:
        # Take the elementwise max across the ambient sensors at each
        # timestep — the sensor closest to the oven-air sees the cleanest
        # driving signal but at any moment another may briefly lead.
        air_proxy = np.max(
            np.column_stack(
                [df[s].to_numpy(dtype=float) for s in air_sensors]
            ),
            axis=1,
        )
    air_at_target = np.interp(t_target, t_full, air_proxy)
    span = float(np.max(air_at_target) - T_initial_dough)
    if span <= 1e-6:
        return np.zeros_like(air_at_target)
    g = (air_at_target - T_initial_dough) / span
    return np.clip(g, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Inverse fitter — 6-param joint Nelder-Mead
# ---------------------------------------------------------------------------


def fit_stefan_inverse_v3(
    df: pd.DataFrame,
    in_dough_sensors: list[str],
    x_surface_continuous: float,
    sensor_positions_normalised: tuple = (
        0 / 7,
        1 / 7,
        2 / 7,
        3 / 7,
        4 / 7,
        5 / 7,
        6 / 7,
        7 / 7,
    ),
    sensor_names: tuple = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"),
    init: Optional[dict] = None,
    bounds: Optional[dict] = None,
    sample_period_s: float = 5.0,
    downsample_factor: int = 4,
    n_spatial: int = 60,
    max_iter: int = 700,
    g_oven_series: Optional[np.ndarray] = None,
) -> dict:
    """Joint 6-parameter Nelder-Mead fit (Stefan v3 with side-source).

    Mirror of :func:`stefan_inverse_v2.fit_stefan_inverse_v2` with
    ``Q_side`` added as a 6th free parameter (linear-space, kept in
    W/m³ for interpretability — log scaling would compress the small-Q
    end where the prior puts most plausible mass).

    Parameters
    ----------
    g_oven_series:
        Optional precomputed normalised oven-driving profile sampled at
        ``df['Timestamp']`` (NOT at the downsampled grid). If ``None``
        the helper :func:`_build_g_oven_from_ambient` infers it from the
        ambient sensors above ``x_surface_continuous``.

    Returns
    -------
    dict
        Same shape as :func:`fit_stefan_inverse_v2` plus:

        * ``Q_side`` — fitted volumetric side-heat source (W/m³)
        * ``Q_side_se`` — standard error
        * ``param_at_bound`` — extended to 6 params
        * ``n_at_bound`` — over 6 params
        * ``param_names`` — :data:`PARAM_NAMES_V3`
    """
    from .profile import interpolate_temperature_series_at

    init = {**INIT_V3, **(init or {})}
    bnds = {**BOUNDS_V3, **(bounds or {})}

    x_core_init = float(init["x_core"])
    alpha_dough_init = float(init["alpha_dough"])
    alpha_crust_init = float(init["alpha_crust"])
    rhoL_init = float(init["rhoL_eff"])
    smear_init = float(init["delta_T_smear"])
    Q_side_init = float(init["Q_side"])

    xc_lo, xc_hi = bnds["x_core_normalised"]
    ad_lo, ad_hi = bnds["alpha_dough"]
    ac_lo, ac_hi = bnds["alpha_crust"]
    rl_lo, rl_hi = bnds["rhoL_eff"]
    dt_lo, dt_hi = bnds["delta_T_smear"]
    qs_lo, qs_hi = bnds["Q_side"]
    log_ad_lo, log_ad_hi = float(np.log(ad_lo)), float(np.log(ad_hi))
    log_ac_lo, log_ac_hi = float(np.log(ac_lo)), float(np.log(ac_hi))
    log_rl_lo, log_rl_hi = float(np.log(rl_lo)), float(np.log(rl_hi))

    t_obs, T_obs, x_obs = _build_observation_matrix(
        df=df,
        in_dough_sensors=in_dough_sensors,
        sensor_names=sensor_names,
        sensor_positions_normalised=sensor_positions_normalised,
        downsample_factor=downsample_factor,
    )
    surface_full = interpolate_temperature_series_at(
        df,
        positions=sensor_positions_normalised,
        x_target=float(x_surface_continuous),
        sensors=sensor_names,
    ).to_numpy(dtype=float)
    t_full = df["Timestamp"].to_numpy(dtype=float)
    T_surf_obs = np.interp(t_obs, t_full, surface_full)

    T_initial = float(np.mean(T_obs[0, :]))
    x_surface = float(x_surface_continuous)

    # Build g_oven once at the observation grid.
    if g_oven_series is None:
        g_obs = _build_g_oven_from_ambient(
            df=df,
            sensor_names=sensor_names,
            sensor_positions_normalised=sensor_positions_normalised,
            x_surface_continuous=x_surface_continuous,
            t_target=t_obs,
            T_initial_dough=T_initial,
        )
    else:
        g_oven_series = np.asarray(g_oven_series, dtype=float)
        if g_oven_series.size == t_full.size:
            g_obs = np.interp(t_obs, t_full, g_oven_series)
        elif g_oven_series.size == t_obs.size:
            g_obs = g_oven_series
        else:
            raise ValueError(
                "g_oven_series must match either df['Timestamp'] or the "
                "downsampled t_obs length"
            )

    # Theta packing:
    #   theta[0] = x_core            (linear)
    #   theta[1] = log(alpha_dough)  (log)
    #   theta[2] = log(alpha_crust)  (log)
    #   theta[3] = log(rhoL_eff)     (log)
    #   theta[4] = delta_T_smear     (linear)
    #   theta[5] = Q_side            (linear)
    def _theta_to_params(theta: np.ndarray) -> tuple:
        x_core = float(theta[0])
        alpha_d = float(np.exp(theta[1]))
        alpha_c = float(np.exp(theta[2]))
        rhoL = float(np.exp(theta[3]))
        smear = float(theta[4])
        Q_side = float(theta[5])
        return x_core, alpha_d, alpha_c, rhoL, smear, Q_side

    def _loss(theta: np.ndarray) -> float:
        x_core, alpha_d, alpha_c, rhoL, smear, Q_side = _theta_to_params(theta)
        if x_core < xc_lo or x_core > xc_hi:
            return 1e10
        if theta[1] < log_ad_lo or theta[1] > log_ad_hi:
            return 1e10
        if theta[2] < log_ac_lo or theta[2] > log_ac_hi:
            return 1e10
        if theta[3] < log_rl_lo or theta[3] > log_rl_hi:
            return 1e10
        if smear < dt_lo or smear > dt_hi:
            return 1e10
        if Q_side < qs_lo or Q_side > qs_hi:
            return 1e10
        if x_core >= x_surface - 1e-3:
            return 1e10
        try:
            T_pred = solve_stefan_forward_v3(
                x_core=x_core,
                x_surface=x_surface,
                alpha_dough=alpha_d,
                alpha_crust=alpha_c,
                rhoL_eff=rhoL,
                t_grid=t_obs,
                T_surface_series=T_surf_obs,
                T_initial=T_initial,
                Q_side=Q_side,
                g_oven_series=g_obs,
                n_spatial=n_spatial,
                sample_x=x_obs,
                delta_T_smear=smear,
            )
        except Exception:
            return 1e10
        diff = (T_pred - T_obs).ravel()
        return float(np.sum(diff * diff))

    theta0 = np.array(
        [
            x_core_init,
            float(np.log(alpha_dough_init)),
            float(np.log(alpha_crust_init)),
            float(np.log(rhoL_init)),
            smear_init,
            Q_side_init,
        ],
        dtype=float,
    )

    opt = minimize(
        _loss,
        theta0,
        method="Nelder-Mead",
        options={
            "xatol": 1e-3,
            "fatol": 1e-2,
            "maxiter": max_iter,
            "adaptive": True,
        },
    )

    x_core_hat, alpha_d_hat, alpha_c_hat, rhoL_hat, smear_hat, Q_side_hat = (
        _theta_to_params(opt.x)
    )
    sse = float(opt.fun)
    n_obs = int(T_obs.size)

    # Hessian-based covariance + linear-param correlation matrix.
    # Step sizes: x_core O(0.1), log-α/log-ρL O(1), smear O(1), Q_side O(1e3).
    try:
        # For Q_side at Q ~ 1e4 W/m³, h=100 gives ≈1% relative perturbation,
        # which is the right order for 5-point central differences.
        H_sse = _numerical_hessian(
            _loss, opt.x, h=[5e-3, 1e-2, 1e-2, 1e-2, 1e-2, 100.0]
        )
        p_params = 6
        dof = max(n_obs - p_params, 1)
        sigma2 = sse / dof
        cov_inflate = 1.4 ** 2
        Cov_theta = 2.0 * sigma2 * cov_inflate * np.linalg.pinv(H_sse)
        # Delta-method Jacobian. theta = (x_core, log αd, log αc, log ρL,
        # smear, Q_side); param same with α/ρL un-logged.
        J = np.diag(
            [1.0, alpha_d_hat, alpha_c_hat, rhoL_hat, 1.0, 1.0]
        )
        Cov_param = J @ Cov_theta @ J.T
        diag_p = np.diag(Cov_param).copy()
        diag_p = np.maximum(diag_p, 0.0)
        stderr_param = np.sqrt(diag_p)
        denom = np.outer(stderr_param, stderr_param)
        with np.errstate(divide="ignore", invalid="ignore"):
            corr_param = np.where(denom > 0, Cov_param / denom, np.nan)
        n = corr_param.shape[0]
        off = np.abs(corr_param.copy())
        for i in range(n):
            off[i, i] = 0.0
        max_off = float(np.nanmax(off)) if np.any(np.isfinite(off)) else float("nan")
    except Exception:
        stderr_param = np.full(6, np.nan)
        corr_param = np.full((6, 6), np.nan)
        max_off = float("nan")

    rmse = float(np.sqrt(sse / max(n_obs, 1)))
    extrapolated = x_core_hat < float(min(sensor_positions_normalised))

    param_at_bound = {
        "x_core_normalised": _bound_status(x_core_hat, xc_lo, xc_hi),
        "alpha_dough": _bound_status(alpha_d_hat, ad_lo, ad_hi),
        "alpha_crust": _bound_status(alpha_c_hat, ac_lo, ac_hi),
        "rhoL_eff": _bound_status(rhoL_hat, rl_lo, rl_hi),
        "delta_T_smear": _bound_status(smear_hat, dt_lo, dt_hi),
        "Q_side": _bound_status(Q_side_hat, qs_lo, qs_hi),
    }
    n_at_bound = sum(1 for v in param_at_bound.values() if v != "interior")

    return {
        "x_core": x_core_hat,
        "alpha_dough": alpha_d_hat,
        "alpha_crust": alpha_c_hat,
        "rhoL_eff": rhoL_hat,
        "delta_T_smear": smear_hat,
        "Q_side": Q_side_hat,
        "x_core_se": float(stderr_param[0]),
        "alpha_dough_se": float(stderr_param[1]),
        "alpha_crust_se": float(stderr_param[2]),
        "rhoL_eff_se": float(stderr_param[3]),
        "delta_T_smear_se": float(stderr_param[4]),
        "Q_side_se": float(stderr_param[5]),
        "full_correlation_matrix": corr_param.tolist(),
        "max_abs_off_diag_correlation": max_off,
        "param_at_bound": param_at_bound,
        "n_at_bound": int(n_at_bound),
        "param_names": PARAM_NAMES_V3,
        "sse": sse,
        "rmse_per_sensor": rmse,
        "n_obs": n_obs,
        "converged": bool(opt.success),
        "n_iter": int(opt.nit) if hasattr(opt, "nit") else 0,
        "T_initial": T_initial,
        "x_surface_continuous": x_surface,
        "extrapolated": bool(extrapolated),
        "bc_source": "interpolated_v2",
        "variant": "stefan_v3_6param_side_source",
        "in_dough": list(in_dough_sensors),
        "rho_cp_dough": RHO_CP_DOUGH,
    }


__all__ = [
    "BOUNDS_V3",
    "INIT_V3",
    "PARAM_NAMES_V3",
    "RHO_CP_DOUGH",
    "solve_stefan_forward_v3",
    "fit_stefan_inverse_v3",
    "_build_g_oven_from_ambient",
]
