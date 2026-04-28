"""HMS Daring — M16 Luikov-tin with OBSERVED top BC and alpha(T) profile.

This module reformulates M15's asymmetric-tin Luikov inverse to take T_air(t)
and h_eff(t) as observed time-series inputs (rather than fitting T_oven_eff
and Bi_top), and adds a piecewise alpha(T) profile to capture the thermal-
diffusivity drop during oven spring.

Physics changes vs M15
----------------------

* **Top BC (x=0)** — convective with OBSERVED h_eff(t) and T_air(t):
  ``-k · ∂T/∂x|_0 = h_eff(t) · (T_air(t) - T_surface)``
  These come from sensor data (M2a-flagged ambient sensor for T_air,
  surface energy balance for h_eff). NOT fitted parameters.

* **Bottom BC (x=L)** — conductive coupling parametrised by ``q_bottom_eff``:
  ``-k · ∂T/∂x|_L = q_bottom_eff · (T_observed_initial - T_bottom)``
  Single parameter that combines tin temperature × heat-transfer coefficient.

* **Internal alpha(T)** — piecewise:
    - α = α_pre for T < 50°C (323.15 K)
    - α = α_pre · alpha_ratio for T > 65°C (338.15 K)
    - linear interpolation in between
  Captures ~2-3× drop in thermal diffusivity during oven spring as dough
  becomes porous.

Free parameters (4 or 5)
------------------------

==============  ====================  ========  ==========================
parameter       bounds                init      role
==============  ====================  ========  ==========================
``L_m``         (0.060, 0.200)        0.100     full loaf thickness (m)
``D_m``         (0.054, 0.095)        0.075     probe insertion depth (m)
``Lu``          (1e-4, 5)             0.15      Luikov number
``q_bottom_eff``(0.0, 200.0)          20.0      bottom-BC coupling W/m²·K
``alpha_ratio`` (0.2, 1.0)            0.4       α_post/α_pre (free or pinned)
==============  ====================  ========  ==========================

``Ko`` is pinned at 4.0 (Zürcher-typical).
``T_oven_eff_K`` and ``Bi_top`` are gone — derived from observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import minimize

from .heat_equation import _numerical_hessian


# ---------------------------------------------------------------------------
# Pinned physical constants (shared with luikov_tin)
# ---------------------------------------------------------------------------

ALPHA_PRE_M2_S = 1.4e-7          # thermal diffusivity (pre-spring), m²/s
C_DOUGH_J_KGK = 2.0e3            # specific heat, J/(kg·K)
L_VAP_J_KG = 2.26e6              # latent heat of vaporisation, J/kg
U_INITIAL = 0.4                  # initial moisture mass fraction
EPSILON = 0.5                    # phase-change criterion
DELTA_POSNOV = 2.0               # Posnov number
K_DOUGH_W_MK = 0.5               # thermal conductivity, W/(m·K)
KO_PINNED = 4.0                  # Kossovitch (pinned at Zürcher-typical)

SPRING_TEMP_LOWER_K = 323.15     # 50 °C
SPRING_TEMP_UPPER_K = 338.15     # 65 °C

# Probe geometry
PROBE_T_SPAN_MM = 95.0
SENSOR_PITCH_MM = PROBE_T_SPAN_MM / 7.0  # 13.5714... mm
SENSOR_POSITIONS_MM_FROM_TIP = tuple(
    (i - 1) * SENSOR_PITCH_MM for i in range(1, 9)
)
SENSOR_NAMES_DEFAULT = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")


# ---------------------------------------------------------------------------
# Forward solver
# ---------------------------------------------------------------------------


@dataclass
class LuikovTinObservedForward:
    T_field_K: np.ndarray
    u_field: np.ndarray
    t_grid_s: np.ndarray
    x_grid_m: np.ndarray
    T_full_K: np.ndarray
    converged: bool


def _alpha_profile(T_K: np.ndarray, alpha_pre: float, alpha_ratio: float) -> np.ndarray:
    """Smooth piecewise alpha(T): α_pre at T<50C, α_pre*ratio at T>65C, linear between."""
    r = np.clip(
        (T_K - SPRING_TEMP_LOWER_K) / (SPRING_TEMP_UPPER_K - SPRING_TEMP_LOWER_K),
        0.0, 1.0,
    )
    # Linear blend: α = α_pre * (1 - r * (1 - alpha_ratio))
    return alpha_pre * (1.0 - r * (1.0 - alpha_ratio))


def solve_luikov_tin_observed(
    *,
    L_m: float,
    Lu: float,
    q_bottom_eff: float,
    alpha_ratio: float,
    t_grid_s: np.ndarray,
    T_air_K_t: np.ndarray,
    h_eff_t: np.ndarray,
    T_initial_K: float = 295.0,
    spring_temp_lower_K: float = SPRING_TEMP_LOWER_K,
    spring_temp_upper_K: float = SPRING_TEMP_UPPER_K,
    n_spatial: int = 60,
    sample_x_m: Optional[np.ndarray] = None,
    alpha_pre_m2_s: float = ALPHA_PRE_M2_S,
    Ko: float = KO_PINNED,
    epsilon: float = EPSILON,
    u_initial: float = U_INITIAL,
    delta_posnov: float = DELTA_POSNOV,
    rtol: float = 1e-5,
    atol: float = 1e-7,
    method: str = "LSODA",
) -> LuikovTinObservedForward:
    """Solve Luikov-tin with OBSERVED top BC and alpha(T) profile.

    Top BC: ``-k · ∂T/∂x|_0 = h_eff(t) · (T_air(t) - T_surface)``.
    Bottom BC: ``-k · ∂T/∂x|_L = q_bottom_eff · (T_initial - T_bottom)``.
    """
    if alpha_pre_m2_s <= 0:
        raise ValueError(f"alpha_pre_m2_s must be > 0")
    if Lu <= 0:
        raise ValueError(f"Lu must be > 0")
    if L_m <= 0:
        raise ValueError(f"L_m must be > 0")
    if alpha_ratio <= 0 or alpha_ratio > 5:
        raise ValueError(f"alpha_ratio out of plausible range")

    L = float(L_m)
    N = int(n_spatial)
    if N < 6:
        raise ValueError(f"n_spatial must be >= 6, got {N}")

    x_grid = np.linspace(0.0, L, N)
    dx = float(x_grid[1] - x_grid[0])
    dx2 = dx * dx

    Lu_val = float(Lu)
    q_bot = float(q_bottom_eff)
    alpha_pre = float(alpha_pre_m2_s)
    alpha_ratio_val = float(alpha_ratio)

    # Coupling for phase change
    delta_T_ref = max(450.0 - float(T_initial_K), 1.0)  # nominal Δ for Ko nondim
    L_over_c_eff = float(Ko) * delta_T_ref / max(float(u_initial), 1e-6)
    coupling_eps_Lv_c = float(epsilon) * L_over_c_eff
    delta_soret = float(delta_posnov) * float(u_initial) / delta_T_ref

    t_grid_arr = np.asarray(t_grid_s, dtype=float)
    T_air_arr = np.asarray(T_air_K_t, dtype=float)
    h_eff_arr = np.asarray(h_eff_t, dtype=float)

    if T_air_arr.shape != t_grid_arr.shape or h_eff_arr.shape != t_grid_arr.shape:
        raise ValueError(
            f"T_air_K_t and h_eff_t must have shape {t_grid_arr.shape}; "
            f"got {T_air_arr.shape} and {h_eff_arr.shape}"
        )

    # Precompute interpolators (linear)
    def _interp_air(t: float) -> float:
        return float(np.interp(t, t_grid_arr, T_air_arr))

    def _interp_h(t: float) -> float:
        return float(np.interp(t, t_grid_arr, h_eff_arr))

    def _laplacian_T(T: np.ndarray, t: float) -> tuple[np.ndarray, np.ndarray]:
        """Return (LapT, alpha_arr)."""
        Lap = np.empty(N, dtype=float)
        if N > 2:
            Lap[1:-1] = (T[:-2] - 2.0 * T[1:-1] + T[2:]) / dx2
        # Top BC at i=0: q_top = h_eff(t) * (T_air(t) - T0)
        T0 = T[0]
        T_air = _interp_air(t)
        h_eff = _interp_h(t)
        # Cap h_eff to avoid runaway when extracted noisy h is unreasonable.
        if not np.isfinite(h_eff):
            h_eff = 10.0
        h_eff = max(0.0, min(h_eff, 500.0))
        q_top = h_eff * (T_air - T0)
        ghost_top = T0 + dx * q_top / K_DOUGH_W_MK
        Lap[0] = (ghost_top - 2.0 * T0 + T[1]) / dx2
        # Bottom BC at i=N-1: -k * dT/dx|_L = q_bottom_eff * (T_initial - T_bot)
        # outward normal at bottom is +x: heat into body when (T_init - T_bot) > 0
        # is questionable. Standard convention with q_bot * (T_tin_eff - T_bot):
        # We implement as: heat flux INTO body from below = q_bot * (T_initial_K - T_bot).
        # Note this allows the bottom to either gain (if T_init < T_bot) or
        # lose heat — typically the tin warms slowly so T_init is a fair proxy
        # for the ambient cool side initially; q_bottom_eff captures the
        # combined coupling magnitude.
        T_last = T[-1]
        # Heat flowing IN at bottom (W/m²) = q_bot * (T_initial - T_last)
        # In Robin form: -k * dT/dx|_L = -q_bot*(T_initial - T_last)
        # Wait — sign: outward normal at x=L is +x.
        # Energy balance: outward flux = q_bot * (T_last - T_initial) → heat
        # leaves when T_last > T_initial. But during a bake the bread interior
        # is hotter than the tin floor, so heat does leave through the tin.
        # The standard formulation: -k * dT/dx |_L = -q_bot*(T_init - T_last).
        # Equivalently:  k * dT/dx|_L = q_bot * (T_init - T_last).
        # For a discrete ghost cell: (T_N - T_{N-1})/dx ≈ dT/dx |_L.
        # So T_N = T_{N-1} + dx * q_bot/k * (T_init - T_last).
        ghost_bot = T_last + dx * q_bot * (T_initial_K - T_last) / K_DOUGH_W_MK
        Lap[-1] = (T[-2] - 2.0 * T_last + ghost_bot) / dx2

        alpha_arr = _alpha_profile(T, alpha_pre, alpha_ratio_val)
        return Lap, alpha_arr

    def _laplacian_u(u: np.ndarray) -> np.ndarray:
        Lap = np.empty(N, dtype=float)
        if N > 2:
            Lap[1:-1] = (u[:-2] - 2.0 * u[1:-1] + u[2:]) / dx2
        ghost_top = -u[0]
        Lap[0] = (ghost_top - 2.0 * u[0] + u[1]) / dx2
        Lap[-1] = (u[-2] - 2.0 * u[-1] + u[-2]) / dx2
        return Lap

    tau_u = 0.05 * dx2 / max(alpha_pre * Lu_val, 1e-12)

    n_state = 2 * N

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        T = y[:N]
        u = y[N:]
        d2T, alpha_arr = _laplacian_T(T, t)
        d2u = _laplacian_u(u)
        du_dt = alpha_arr * Lu_val * d2u + alpha_arr * Lu_val * delta_soret * d2T
        dT_dt = alpha_arr * d2T + coupling_eps_Lv_c * du_dt
        du_dt[0] = (0.0 - u[0]) / tau_u
        out = np.empty(n_state, dtype=float)
        out[:N] = dT_dt
        out[N:] = du_dt
        return out

    y0 = np.empty(n_state, dtype=float)
    y0[:N] = float(T_initial_K)
    y0[N:] = float(u_initial)
    y0[N] = 0.0

    if t_grid_arr.size < 2:
        raise ValueError("t_grid_s must have at least 2 samples")
    t_span = (float(t_grid_arr[0]), float(t_grid_arr[-1]))

    sol = solve_ivp(
        rhs,
        t_span,
        y0,
        t_eval=t_grid_arr,
        method=method,
        rtol=rtol,
        atol=atol,
    )

    converged = bool(sol.success)
    if not converged:
        T_xt = np.full((t_grid_arr.size, N), float(T_initial_K), dtype=float)
        u_xt = np.full((t_grid_arr.size, N), float(u_initial), dtype=float)
        n_used = sol.y.shape[1] if sol.y.size else 0
        if n_used > 0:
            T_xt[:n_used] = sol.y[:N, :].T
            u_xt[:n_used] = sol.y[N:, :].T
            T_xt[n_used:] = T_xt[n_used - 1]
            u_xt[n_used:] = u_xt[n_used - 1]
    else:
        T_xt = sol.y[:N, :].T
        u_xt = sol.y[N:, :].T

    if sample_x_m is None:
        T_sample = T_xt
        u_sample = u_xt
    else:
        sample = np.asarray(sample_x_m, dtype=float)
        T_sample = np.empty((t_grid_arr.size, sample.size), dtype=float)
        u_sample = np.empty((t_grid_arr.size, sample.size), dtype=float)
        for i in range(t_grid_arr.size):
            T_sample[i, :] = np.interp(sample, x_grid, T_xt[i, :])
            u_sample[i, :] = np.interp(sample, x_grid, u_xt[i, :])

    return LuikovTinObservedForward(
        T_field_K=T_sample,
        u_field=u_sample,
        t_grid_s=t_grid_arr,
        x_grid_m=x_grid,
        T_full_K=T_xt,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Inverse fit
# ---------------------------------------------------------------------------


PARAM_NAMES_OBSERVED = ("L_m", "D_m", "Lu", "q_bottom_eff", "alpha_ratio")


def infer_core_depth_from_forward(
    T_full_K: np.ndarray,
    x_grid_m: np.ndarray,
    t_grid_s: np.ndarray,
    sample_frac: float = 0.5,
) -> float:
    n_t = T_full_K.shape[0]
    i_mid = max(0, min(int(sample_frac * n_t), n_t - 1))
    T_snap = T_full_K[i_mid]
    j_min = int(np.argmin(T_snap))
    return float(x_grid_m[j_min] * 1000.0)


def fit_luikov_tin_observed_inverse(
    df: pd.DataFrame,
    in_dough_sensors: list,
    T_air_K_t: np.ndarray,
    h_eff_t: np.ndarray,
    sensor_positions_mm: tuple = SENSOR_POSITIONS_MM_FROM_TIP,
    sensor_names: tuple = SENSOR_NAMES_DEFAULT,
    init: Optional[dict] = None,
    bounds: Optional[dict] = None,
    fit_alpha_ratio: bool = True,
    pinned_alpha_ratio: float = 0.4,
    downsample_factor: int = 4,
    n_spatial: int = 60,
    startup_skip_frac: float = 0.20,
    max_iter: int = 600,
    rtol: float = 1e-5,
    atol: float = 1e-7,
    method: str = "LSODA",
) -> dict:
    """4-5 parameter inverse fit with observed top BC.

    Free params:
      - L_m, D_m, Lu, q_bottom_eff
      - alpha_ratio (if ``fit_alpha_ratio=True``); else pinned at
        ``pinned_alpha_ratio``.
    """
    init = init or {}
    bounds = bounds or {}

    init_vals = {
        "L_m": float(init.get("L_m", 0.100)),
        "D_m": float(init.get("D_m", 0.075)),
        "Lu": float(init.get("Lu", 0.15)),
        "q_bottom_eff": float(init.get("q_bottom_eff", 20.0)),
        "alpha_ratio": float(init.get("alpha_ratio", 0.4)),
    }
    bnd = {
        "L_m": bounds.get("L_m", (0.060, 0.200)),
        "D_m": bounds.get("D_m", (0.054, 0.095)),
        "Lu": bounds.get("Lu", (1e-4, 5.0)),
        "q_bottom_eff": bounds.get("q_bottom_eff", (0.0, 200.0)),
        "alpha_ratio": bounds.get("alpha_ratio", (0.2, 1.0)),
    }

    # Build observation matrix
    t_full = df["Timestamp"].to_numpy(dtype=float)
    if downsample_factor < 1:
        downsample_factor = 1
    sl = slice(0, len(t_full), int(downsample_factor))
    t_obs = t_full[sl]
    T_cols = [df[s].to_numpy(dtype=float)[sl] for s in in_dough_sensors]
    T_obs_C = np.column_stack(T_cols)
    T_obs_K = T_obs_C + 273.15
    T_initial_K = float(np.mean(T_obs_K[0, :]))

    # Resample T_air, h_eff onto the downsampled t_obs grid
    t_air_full = np.asarray(T_air_K_t, dtype=float)
    h_eff_full = np.asarray(h_eff_t, dtype=float)
    if len(t_air_full) != len(t_full) or len(h_eff_full) != len(t_full):
        raise ValueError(
            f"T_air and h_eff series must match df length {len(t_full)}; "
            f"got {len(t_air_full)} and {len(h_eff_full)}"
        )
    t_air_obs = t_air_full[sl]
    h_eff_obs = h_eff_full[sl]
    # Replace NaNs in h_eff with median interpolation (fall back: 10.0)
    if not np.all(np.isfinite(h_eff_obs)):
        finite = np.isfinite(h_eff_obs)
        if finite.any():
            idx = np.arange(len(h_eff_obs))
            h_eff_obs = np.interp(idx, idx[finite], h_eff_obs[finite])
        else:
            h_eff_obs = np.full_like(h_eff_obs, 10.0)
    if not np.all(np.isfinite(t_air_obs)):
        # Linear fallback
        finite = np.isfinite(t_air_obs)
        if finite.any():
            idx = np.arange(len(t_air_obs))
            t_air_obs = np.interp(idx, idx[finite], t_air_obs[finite])
        else:
            t_air_obs = np.full_like(t_air_obs, 423.15)

    n_t_total = len(t_obs)
    n_skip = max(int(startup_skip_frac * n_t_total), 0)
    if n_skip >= n_t_total - 5:
        n_skip = max(n_t_total // 4, 0)

    p_m = np.asarray(sensor_positions_mm, dtype=float) / 1000.0
    pos_by_name = dict(zip(sensor_names, p_m))
    p_obs_m = np.array([pos_by_name[s] for s in in_dough_sensors], dtype=float)

    # Reparametrise: linear on L_m, D_m, q_bottom_eff, alpha_ratio; log on Lu.
    def _theta_to_params(theta: np.ndarray) -> dict:
        if fit_alpha_ratio:
            return {
                "L_m": float(theta[0]),
                "D_m": float(theta[1]),
                "Lu": float(np.exp(theta[2])),
                "q_bottom_eff": float(theta[3]),
                "alpha_ratio": float(theta[4]),
            }
        return {
            "L_m": float(theta[0]),
            "D_m": float(theta[1]),
            "Lu": float(np.exp(theta[2])),
            "q_bottom_eff": float(theta[3]),
            "alpha_ratio": float(pinned_alpha_ratio),
        }

    def _bounds_penalty(p: dict) -> float:
        for name, val in p.items():
            lo, hi = bnd[name]
            if not (lo <= val <= hi):
                return 1e10
        return 0.0

    def _loss(theta: np.ndarray) -> float:
        p = _theta_to_params(theta)
        pen = _bounds_penalty(p)
        if pen > 0:
            return pen
        d_obs_m = p["D_m"] - p_obs_m
        if np.any(d_obs_m < -1e-4):
            return 1e9
        if np.any(d_obs_m > p["L_m"] + 1e-4):
            return 1e9
        d_clipped = np.clip(d_obs_m, 0.0, p["L_m"])
        try:
            fwd = solve_luikov_tin_observed(
                L_m=p["L_m"],
                Lu=p["Lu"],
                q_bottom_eff=p["q_bottom_eff"],
                alpha_ratio=p["alpha_ratio"],
                t_grid_s=t_obs,
                T_air_K_t=t_air_obs,
                h_eff_t=h_eff_obs,
                T_initial_K=T_initial_K,
                sample_x_m=d_clipped,
                n_spatial=n_spatial,
                rtol=rtol,
                atol=atol,
                method=method,
            )
        except Exception:
            return 1e10
        if not fwd.converged:
            return 1e9
        diff = (fwd.T_field_K[n_skip:] - T_obs_K[n_skip:]).ravel()
        if not np.all(np.isfinite(diff)):
            return 1e10
        return float(np.sum(diff * diff))

    if fit_alpha_ratio:
        theta0 = np.array(
            [
                init_vals["L_m"],
                init_vals["D_m"],
                float(np.log(max(init_vals["Lu"], 1e-6))),
                init_vals["q_bottom_eff"],
                init_vals["alpha_ratio"],
            ],
            dtype=float,
        )
    else:
        theta0 = np.array(
            [
                init_vals["L_m"],
                init_vals["D_m"],
                float(np.log(max(init_vals["Lu"], 1e-6))),
                init_vals["q_bottom_eff"],
            ],
            dtype=float,
        )

    opt = minimize(
        _loss,
        theta0,
        method="Nelder-Mead",
        options={
            "xatol": 0.005,
            "fatol": 0.5,
            "maxiter": int(max_iter),
            "adaptive": True,
        },
    )

    p_hat = _theta_to_params(opt.x)
    sse = float(opt.fun)
    n_obs_fit = int(T_obs_K[n_skip:].size)
    n_obs_total = int(T_obs_K.size)
    rmse = float(np.sqrt(sse / max(n_obs_fit, 1)))

    # Re-run forward at fitted params for x_core inference
    d_obs_m = p_hat["D_m"] - p_obs_m
    d_clipped = np.clip(d_obs_m, 0.0, p_hat["L_m"])
    try:
        fwd_full = solve_luikov_tin_observed(
            L_m=p_hat["L_m"],
            Lu=p_hat["Lu"],
            q_bottom_eff=p_hat["q_bottom_eff"],
            alpha_ratio=p_hat["alpha_ratio"],
            t_grid_s=t_obs,
            T_air_K_t=t_air_obs,
            h_eff_t=h_eff_obs,
            T_initial_K=T_initial_K,
            sample_x_m=d_clipped,
            n_spatial=n_spatial,
        )
        x_core_inferred_mm = infer_core_depth_from_forward(
            fwd_full.T_full_K, fwd_full.x_grid_m, fwd_full.t_grid_s
        )
    except Exception:
        x_core_inferred_mm = float("nan")

    # Hessian → covariance → SEs
    if fit_alpha_ratio:
        h_per = [2e-3, 2e-3, 0.05, 1.0, 0.02]
        n_param = 5
    else:
        h_per = [2e-3, 2e-3, 0.05, 1.0]
        n_param = 4
    try:
        H = _numerical_hessian(_loss, opt.x, h=h_per)
        dof = max(n_obs_fit - n_param, 1)
        sigma2 = sse / dof
        cov_inflate = 1.4 ** 2
        Cov_theta = 2.0 * sigma2 * cov_inflate * np.linalg.pinv(H)
        if fit_alpha_ratio:
            J = np.diag([1.0, 1.0, p_hat["Lu"], 1.0, 1.0])
        else:
            J = np.diag([1.0, 1.0, p_hat["Lu"], 1.0])
        Cov_param = J @ Cov_theta @ J.T
        diag_p = np.maximum(np.diag(Cov_param), 0.0)
        stderr = np.sqrt(diag_p)
        denom = np.outer(stderr, stderr)
        with np.errstate(divide="ignore", invalid="ignore"):
            corr = np.where(denom > 0, Cov_param / denom, np.nan)
        off = np.abs(corr.copy())
        for i in range(off.shape[0]):
            off[i, i] = 0.0
        max_off = float(np.nanmax(off)) if np.any(np.isfinite(off)) else float("nan")
    except Exception:
        stderr = np.full(n_param, np.nan)
        corr = np.full((n_param, n_param), np.nan)
        max_off = float("nan")

    # Sensor depths
    sensor_depths_mm = p_hat["D_m"] * 1000.0 - np.asarray(
        sensor_positions_mm, dtype=float
    )
    any_below_loaf = bool(
        np.any(sensor_depths_mm > p_hat["L_m"] * 1000.0 + 0.1)
    )

    def _at_bound(name: str, val: float) -> str:
        lo, hi = bnd[name]
        width = max(hi - lo, 1e-9)
        if abs(val - lo) < max(0.01 * width, 1e-6):
            return "lo"
        if abs(val - hi) < max(0.01 * width, 1e-6):
            return "hi"
        return "interior"

    if fit_alpha_ratio:
        param_names_used = list(PARAM_NAMES_OBSERVED)
    else:
        param_names_used = list(PARAM_NAMES_OBSERVED[:-1])
    bound_status = {n: _at_bound(n, p_hat[n]) for n in param_names_used}
    n_interior = sum(1 for v in bound_status.values() if v == "interior")

    se_dict: dict = {}
    for i, name in enumerate(param_names_used):
        se_dict[f"{name}_se"] = float(stderr[i])

    out = {
        **p_hat,
        **se_dict,
        "fit_alpha_ratio": bool(fit_alpha_ratio),
        "pinned_alpha_ratio": float(pinned_alpha_ratio) if not fit_alpha_ratio else None,
        "full_correlation_matrix": corr.tolist(),
        "max_abs_off_diag_correlation": max_off,
        "sse": sse,
        "rmse_per_sensor": rmse,
        "n_obs": n_obs_fit,
        "n_obs_total": n_obs_total,
        "n_skip": int(n_skip),
        "startup_skip_frac": float(startup_skip_frac),
        "converged": bool(opt.success),
        "n_iter": int(opt.nit) if hasattr(opt, "nit") else 0,
        "T_initial_K": T_initial_K,
        "n_spatial": int(n_spatial),
        "in_dough": list(in_dough_sensors),
        "sensor_positions_mm": list(map(float, sensor_positions_mm)),
        "sensor_depths_mm": list(map(float, sensor_depths_mm)),
        "any_sensor_below_loaf": any_below_loaf,
        "x_core_depth_inferred_mm": float(x_core_inferred_mm),
        "param_at_bound": bound_status,
        "n_interior_params": n_interior,
        "param_names": param_names_used,
        "n_param": n_param,
    }
    return out
