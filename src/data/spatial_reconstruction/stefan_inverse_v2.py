"""M20 (research-only): 1D Stefan inverse with α + Δ_T_smear freed.

Background — see ``stefan_inverse.py`` for the 4-parameter M9 baseline. The
M19 RCA flotilla identified two systematic mis-pinnings in M9:

* ``alpha_dough`` was effectively pinned 5-7× too low. The 22-25 min real
  bake time requires an effective α in the range 4e-7 to 3e-6 m²/s
  (central estimate ~8e-7 m²/s); M9 was operating at ~1.4e-7 m²/s, which
  cannot heat the centre past ~50 °C in the available bake time. M17
  freed α and the optimiser hit the upper bound (4.91e-6 / 5e-6 cap),
  empirically confirming the diagnosis.

* ``delta_T_smear`` was pinned at 1.0 °C — M9's residual signature on
  BA3C_0946 (lag-1 ρ=0.99 with depth-dependent sign flip: T1 -14 °C,
  T2/T3 +13/+10 °C) is consistent with a Stefan front that propagates
  too fast through the deep dough and over-pins the mid-depth sensors.
  Widening the smear window to 3-10 °C lets the latent-heat trap
  spread across a thicker shell, slowing the front and releasing the
  mid-depth pin.

This module extends :func:`stefan_inverse.fit_stefan_inverse_joint` to a
**5-parameter joint fit**: ``(x_core, alpha_dough, alpha_crust, rhoL_eff,
delta_T_smear)``. The forward solver is unchanged — :func:`solve_stefan_forward`
already accepts ``delta_T_smear`` as a kwarg with default 1.0 °C; we just
thread the fitted value through.

Public API:

* :func:`fit_stefan_inverse_v2` — joint 5-param Nelder-Mead fit with
  bounded log-space transforms on the positive thermal parameters and
  linear transforms on ``x_core`` and ``delta_T_smear``. Hessian-based
  covariance + correlation matrix on the linear parameters.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .heat_equation import _numerical_hessian
from .stefan_inverse import (
    _build_observation_matrix,
    _correlation_matrix,
    solve_stefan_forward,
)


# SI ↔ normalised-position conversion factor. The forward solver works in
# normalised position units where x ∈ [0, 1] across the loaf thickness;
# α_norm = α_SI / loaf_thickness². For a representative half-loaf
# thickness of 50 mm (the same convention used by
# :data:`stefan_inverse.LOAF_THICKNESS_M`), the conversion is
# 1/(0.05)² = 400 [1/m²]. The RCA recommendation's bounds are in SI units;
# we convert to normalised at module load.
LOAF_THICKNESS_M = 0.050  # match stefan_inverse.LOAF_THICKNESS_M
_SI_TO_NORM = 1.0 / (LOAF_THICKNESS_M * LOAF_THICKNESS_M)  # ≈ 400


# Bounds (from M19 RCA recommendation, in SI; converted to normalised
# units below). RCA's reasoning:
#
# * α_dough SI bounds (5e-7, 1e-5) m²/s — central estimate ~8e-7 m²/s
#   for a 22-25 min bake at 50-65 mm slab thickness (Heisler/Fo). M9
#   was effectively pinned at ~1.4e-7 m²/s (3-7× too low to bake in
#   the available time).
# * α_crust SI bounds (1e-7, 5e-6) m²/s — wider range; M17 fitted at
#   ~4.9e-6 m²/s.
# * rhoL_eff is already in normalised-K units in the forward solver;
#   the (10, 1000) range covers M9's ~40 fit and lets the smear-widening
#   experiment shift the latent-heat budget.
# * delta_T_smear (3, 10) °C — M9 used 1 °C; the depth-dependent
#   sign-flip residual on BA3C_0946 implicates a smear that's too narrow.
BOUNDS_V2_SI = {
    "alpha_dough": (5e-7, 1e-5),
    "alpha_crust": (1e-7, 5e-6),
}
BOUNDS_V2 = {
    "x_core_normalised": (-0.10, 0.50),
    "alpha_dough": (
        BOUNDS_V2_SI["alpha_dough"][0] * _SI_TO_NORM,
        BOUNDS_V2_SI["alpha_dough"][1] * _SI_TO_NORM,
    ),
    "alpha_crust": (
        BOUNDS_V2_SI["alpha_crust"][0] * _SI_TO_NORM,
        BOUNDS_V2_SI["alpha_crust"][1] * _SI_TO_NORM,
    ),
    "rhoL_eff": (10.0, 1000.0),
    "delta_T_smear": (3.0, 10.0),
}

# Initial values (RCA's central derived values, also converted SI →
# normalised for the diffusivities).
INIT_V2_SI = {
    "alpha_dough": 8e-7,
    "alpha_crust": 5e-7,
}
INIT_V2 = {
    "x_core": 0.0,
    "alpha_dough": INIT_V2_SI["alpha_dough"] * _SI_TO_NORM,
    "alpha_crust": INIT_V2_SI["alpha_crust"] * _SI_TO_NORM,
    "rhoL_eff": 100.0,
    "delta_T_smear": 5.0,
}

PARAM_NAMES_V2 = (
    "x_core_normalised",
    "alpha_dough",
    "alpha_crust",
    "rhoL_eff",
    "delta_T_smear",
)


def _bound_status(value: float, lo: float, hi: float, tol_frac: float = 0.02) -> str:
    """Return one of ``'lo' | 'hi' | 'interior'`` for a fitted parameter.

    A param is flagged at-bound if it sits within ``tol_frac`` of either
    edge of the bound range (in log space for positive params is checked
    by the caller). For linear params we use the linear range.
    """
    span = hi - lo
    if span <= 0:
        return "interior"
    if value <= lo + tol_frac * span:
        return "lo"
    if value >= hi - tol_frac * span:
        return "hi"
    return "interior"


def fit_stefan_inverse_v2(
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
    max_iter: int = 600,
) -> dict:
    """Joint 5-parameter Nelder-Mead fit for Stefan v2.

    Parameters
    ----------
    df, in_dough_sensors, x_surface_continuous,
    sensor_positions_normalised, sensor_names, sample_period_s,
    downsample_factor, n_spatial, max_iter:
        Same shape as :func:`fit_stefan_inverse_joint`.
    init:
        Optional initial values for ``(x_core, alpha_dough, alpha_crust,
        rhoL_eff, delta_T_smear)``. Defaults to :data:`INIT_V2`.
    bounds:
        Optional bound dict (same keys as :data:`BOUNDS_V2`). Defaults to
        the RCA-recommended values.

    Returns
    -------
    dict
        Same shape as :func:`fit_stefan_inverse_joint` plus:

        * ``delta_T_smear`` — fitted value
        * ``delta_T_smear_se`` — standard error
        * ``param_at_bound`` — dict mapping each linear param name to
          one of ``'lo'``, ``'hi'``, ``'interior'``
        * ``param_names`` — tuple of the 5 param names in fit order
        * ``n_at_bound`` — count of params at lo or hi bound
    """
    from .profile import interpolate_temperature_series_at

    init = {**INIT_V2, **(init or {})}
    bnds = {**BOUNDS_V2, **(bounds or {})}

    x_core_init = float(init["x_core"])
    alpha_dough_init = float(init["alpha_dough"])
    alpha_crust_init = float(init["alpha_crust"])
    rhoL_init = float(init["rhoL_eff"])
    smear_init = float(init["delta_T_smear"])

    # Theta packing:
    #   theta[0] = x_core            (linear)
    #   theta[1] = log(alpha_dough)  (log)
    #   theta[2] = log(alpha_crust)  (log)
    #   theta[3] = log(rhoL_eff)     (log)
    #   theta[4] = delta_T_smear     (linear)
    # The log transform keeps the positive params strictly positive and
    # lets the optimiser walk equally fast across decades. Bounds are
    # enforced via penalty inside the loss.

    xc_lo, xc_hi = bnds["x_core_normalised"]
    ad_lo, ad_hi = bnds["alpha_dough"]
    ac_lo, ac_hi = bnds["alpha_crust"]
    rl_lo, rl_hi = bnds["rhoL_eff"]
    dt_lo, dt_hi = bnds["delta_T_smear"]
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

    def _theta_to_params(theta: np.ndarray) -> tuple[float, float, float, float, float]:
        x_core = float(theta[0])
        alpha_d = float(np.exp(theta[1]))
        alpha_c = float(np.exp(theta[2]))
        rhoL = float(np.exp(theta[3]))
        smear = float(theta[4])
        return x_core, alpha_d, alpha_c, rhoL, smear

    def _loss(theta: np.ndarray) -> float:
        x_core, alpha_d, alpha_c, rhoL, smear = _theta_to_params(theta)
        # Bound enforcement via large penalty (Nelder-Mead doesn't accept
        # bounds directly; this is the standard pattern).
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
        if x_core >= x_surface - 1e-3:
            return 1e10
        try:
            T_pred = solve_stefan_forward(
                x_core=x_core,
                x_surface=x_surface,
                alpha_dough=alpha_d,
                alpha_crust=alpha_c,
                rhoL_eff=rhoL,
                t_grid=t_obs,
                T_surface_series=T_surf_obs,
                T_initial=T_initial,
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

    x_core_hat, alpha_d_hat, alpha_c_hat, rhoL_hat, smear_hat = _theta_to_params(opt.x)
    sse = float(opt.fun)
    n_obs = int(T_obs.size)

    # Hessian-based covariance + linear-param correlation matrix.
    try:
        # Step sizes: x_core O(0.1), log-α/log-ρL O(1), smear O(1).
        H_sse = _numerical_hessian(
            _loss, opt.x, h=[5e-3, 1e-2, 1e-2, 1e-2, 1e-2]
        )
        p_params = 5
        dof = max(n_obs - p_params, 1)
        sigma2 = sse / dof
        cov_inflate = 1.4 ** 2
        Cov_theta = 2.0 * sigma2 * cov_inflate * np.linalg.pinv(H_sse)
        # Delta-method Jacobian. theta = (x_core, log αd, log αc, log ρL,
        # smear); param = (x_core, αd, αc, ρL, smear). Diag Jacobian:
        J = np.diag([1.0, alpha_d_hat, alpha_c_hat, rhoL_hat, 1.0])
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
        stderr_param = np.full(5, np.nan)
        corr_param = np.full((5, 5), np.nan)
        max_off = float("nan")

    rmse = float(np.sqrt(sse / max(n_obs, 1)))
    extrapolated = x_core_hat < float(min(sensor_positions_normalised))

    # Bound classification on the linear parameters.
    param_at_bound = {
        "x_core_normalised": _bound_status(x_core_hat, xc_lo, xc_hi),
        "alpha_dough": _bound_status(alpha_d_hat, ad_lo, ad_hi),
        "alpha_crust": _bound_status(alpha_c_hat, ac_lo, ac_hi),
        "rhoL_eff": _bound_status(rhoL_hat, rl_lo, rl_hi),
        "delta_T_smear": _bound_status(smear_hat, dt_lo, dt_hi),
    }
    n_at_bound = sum(1 for v in param_at_bound.values() if v != "interior")

    return {
        "x_core": x_core_hat,
        "alpha_dough": alpha_d_hat,
        "alpha_crust": alpha_c_hat,
        "rhoL_eff": rhoL_hat,
        "delta_T_smear": smear_hat,
        "x_core_se": float(stderr_param[0]),
        "alpha_dough_se": float(stderr_param[1]),
        "alpha_crust_se": float(stderr_param[2]),
        "rhoL_eff_se": float(stderr_param[3]),
        "delta_T_smear_se": float(stderr_param[4]),
        "full_correlation_matrix": corr_param.tolist(),
        "max_abs_off_diag_correlation": max_off,
        "param_at_bound": param_at_bound,
        "n_at_bound": int(n_at_bound),
        "param_names": PARAM_NAMES_V2,
        "sse": sse,
        "rmse_per_sensor": rmse,
        "n_obs": n_obs,
        "converged": bool(opt.success),
        "n_iter": int(opt.nit) if hasattr(opt, "nit") else 0,
        "T_initial": T_initial,
        "x_surface_continuous": x_surface,
        "extrapolated": bool(extrapolated),
        "bc_source": "interpolated_v2",
        "variant": "stefan_v2_5param",
        "in_dough": list(in_dough_sensors),
    }


__all__ = [
    "BOUNDS_V2",
    "INIT_V2",
    "PARAM_NAMES_V2",
    "fit_stefan_inverse_v2",
]
