"""HMS Endeavour — M17 Luikov-Dirichlet hybrid inverse.

This module combines the best of:
  - **M9 Stefan with Dirichlet top BC**: surface temperature anchored to the
    M2a-detected per-timestep spatial-interpolated surface, no fitted top
    convective coefficient. M9 produced 5-11 °C main-bake RMSE — the best
    of the inverse-problem missions.
  - **M15 Luikov-tin moisture/asymmetric physics**: coupled heat+mass via
    Luikov, asymmetric bottom BC for tin contact, ε·L_v/c phase-change
    coupling.
  - **M16 α(T) profile**: piecewise thermal-diffusivity drop during oven
    spring (α_pre at T<50°C, α_pre·alpha_ratio at T>65°C, linear between).

Hypothesis: the surface-Dirichlet BC was the right top BC choice all along;
M9's 5-11 °C floor is bottlenecked by missing moisture/tin/α(T) physics,
not by BC misspecification. Adding the M15 corrections to M9's BC choice
should give a fit below 4 °C with parameters interior — IF any formulation
can break the floor.

Geometry
--------

Loaf coordinate ``x ∈ [x_surface_in_loaf, L]`` with ``x = 0`` (conceptual)
at the loaf top and ``x = L`` at the bottom (tin contact). The surface in
loaf-frame is

    x_surface_in_loaf = D - x_surface_continuous_normalised * 0.095

where ``x_surface_continuous_normalised`` is the M2a-detected continuous
position normalised to the probe span (0 = T1/tip, 1 = T8/stem) and the
probe span is 95 mm. The dough domain is therefore the loaf region from
the M2a interface down to the tin floor — we do NOT model the air region
above the surface.

Boundary conditions
-------------------

* **Top (x = x_surface_in_loaf, oven-facing surface)** — Dirichlet anchored
  to the spatially-interpolated observed surface temperature::

      T(x_surface_in_loaf, t) = T_surface_observed_t

  No fitted parameters; the BC is pinned to the observation.

* **Bottom (x = L, tin contact)** — conductive coupling::

      −k · ∂T/∂x|_{x=L} = q_bottom_eff · (T_initial − T(L, t))

  Single free parameter ``q_bottom_eff`` (W/m²·K) combines tin-side
  coefficient and effective tin temperature gap. Same form as M16.

* **Moisture top** — Dirichlet u = 0 at the surface (free evaporation).
* **Moisture bottom** — Neumann ∂u/∂x = 0 (no moisture loss through tin).

α(T) profile
------------

Same as M16::

    α(T) = α_pre               for T < spring_temp_lower_K (50 °C default)
    α(T) = α_pre · α_ratio     for T > spring_temp_upper_K (65 °C default)
    linear interpolation between.

Free parameters (5)
-------------------

==================  ====================  ========  ==========================
parameter           bounds                init      role
==================  ====================  ========  ==========================
``L_m``             (0.060, 0.200)        0.100     full loaf thickness (m)
``D_m``             (0.054, 0.095)        0.070     probe insertion depth (m)
``Lu``              (1e-4, 5)             0.15      Luikov number
``q_bottom_eff``    (0, 200)              20.0      bottom-BC coupling W/m²·K
``alpha_ratio``     (0.2, 1.0)            0.4       α_post/α_pre during spring
==================  ====================  ========  ==========================

NO ``T_oven_eff``, NO ``Bi_top``, NO ``T_tin_eff`` (subsumed into
``q_bottom_eff``). Top BC is fully observed; the model fits internal
dough physics + bottom coupling only.

Public API
----------

* :func:`solve_luikov_dirichlet_hybrid_forward` — forward solver.
* :func:`fit_luikov_dirichlet_hybrid_inverse` — 5-parameter Nelder-Mead.
* :func:`infer_core_depth_from_forward` — derived core-depth helper.
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
# Pinned physical constants (shared with luikov_tin / luikov_tin_observed)
# ---------------------------------------------------------------------------

ALPHA_PRE_M2_S = 1.0e-6          # effective thermal diffusivity (pre-spring), m²/s
                                 # Real bread bakes in 30-60 min through ~50 mm,
                                 # which requires α_eff ≈ 5e-7 to 2e-6 m²/s. The
                                 # molecular thermal diffusivity of dough alone is
                                 # ~1.4e-7 m²/s, but evaporation-diffusion-
                                 # condensation (EDC) carries ~60% of the effective
                                 # heat (Halder-Datta). Pin at mid-range effective
                                 # value 1e-6. The Lu coupling on top of this α
                                 # captures additional moisture-transport effects.
                                 # Pinning at the molecular value 1.4e-7 (M17 v1)
                                 # gave 5x-too-slow heat propagation and broken fits.
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
PROBE_T_SPAN_M = 0.095
SENSOR_PITCH_MM = PROBE_T_SPAN_MM / 7.0  # 13.5714... mm
SENSOR_POSITIONS_MM_FROM_TIP = tuple(
    (i - 1) * SENSOR_PITCH_MM for i in range(1, 9)
)
SENSOR_NAMES_DEFAULT = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")


# ---------------------------------------------------------------------------
# Forward solver
# ---------------------------------------------------------------------------


@dataclass
class LuikovDirichletHybridForward:
    """Output of :func:`solve_luikov_dirichlet_hybrid_forward`."""

    T_field_K: np.ndarray   # (n_t, n_sample) — sampled at sample_x_m
    u_field: np.ndarray
    t_grid_s: np.ndarray
    x_grid_m: np.ndarray    # (n_spatial,) — uniform grid on [x_surface, L]
    T_full_K: np.ndarray    # (n_t, n_spatial) — full field
    converged: bool


def _alpha_profile(
    T_K: np.ndarray,
    alpha_pre: float,
    alpha_ratio: float,
    spring_temp_lower_K: float = SPRING_TEMP_LOWER_K,
    spring_temp_upper_K: float = SPRING_TEMP_UPPER_K,
) -> np.ndarray:
    """Smooth piecewise α(T): α_pre at T < lower, α_pre·ratio at T > upper.

    Linear interpolation in between.
    """
    span = max(spring_temp_upper_K - spring_temp_lower_K, 1e-9)
    r = np.clip((T_K - spring_temp_lower_K) / span, 0.0, 1.0)
    return alpha_pre * (1.0 - r * (1.0 - alpha_ratio))


def solve_luikov_dirichlet_hybrid_forward(
    *,
    L_m: float,
    D_m: float,
    Lu: float,
    q_bottom_eff: float,
    alpha_ratio: float,
    t_grid_s: np.ndarray,
    T_surface_K_t: np.ndarray,
    x_surface_continuous_normalised: float,
    T_initial_K: float = 295.0,
    n_spatial: int = 60,
    sample_x_m: Optional[np.ndarray] = None,
    alpha_pre_m2_s: float = ALPHA_PRE_M2_S,
    c: float = C_DOUGH_J_KGK,
    L_v: float = L_VAP_J_KG,
    epsilon: float = EPSILON,
    Ko: float = KO_PINNED,
    u_initial: float = U_INITIAL,
    delta_soret: float = DELTA_POSNOV,
    spring_temp_lower_K: float = SPRING_TEMP_LOWER_K,
    spring_temp_upper_K: float = SPRING_TEMP_UPPER_K,
    rtol: float = 1e-5,
    atol: float = 1e-7,
    method: str = "LSODA",
) -> LuikovDirichletHybridForward:
    """Solve coupled Luikov heat+mass on the dough domain with Dirichlet top.

    Domain ``x ∈ [x_surface_in_loaf_m, L_m]`` where::

        x_surface_in_loaf_m = D_m - x_surface_continuous_normalised * 0.095

    Boundary conditions:

    * Top (Dirichlet): ``T(x_surface, t) = T_surface_K_t`` (observed,
      enforced by stiff clamping in the heat ODE).
    * Bottom (Robin/conductive): ``-k · ∂T/∂x|_L = q_bottom_eff ·
      (T_initial − T(L, t))``.
    * Moisture: ``u = 0`` at top (Dirichlet, stiff clamp), ``∂u/∂x = 0``
      at bottom (Neumann).

    α(T) is the M16 piecewise profile.
    """
    if alpha_pre_m2_s <= 0:
        raise ValueError("alpha_pre_m2_s must be > 0")
    if Lu <= 0:
        raise ValueError("Lu must be > 0")
    if L_m <= 0:
        raise ValueError("L_m must be > 0")
    if alpha_ratio <= 0 or alpha_ratio > 5:
        raise ValueError("alpha_ratio out of plausible range")

    L = float(L_m)
    D = float(D_m)
    x_surface_in_loaf_m = D - float(x_surface_continuous_normalised) * PROBE_T_SPAN_M
    if x_surface_in_loaf_m < 0:
        # Surface above top of loaf — clamp to 0 (full immersion, surface = top).
        x_surface_in_loaf_m = 0.0
    if x_surface_in_loaf_m >= L - 1e-4:
        raise ValueError(
            f"x_surface_in_loaf_m={x_surface_in_loaf_m:.4f} >= L_m={L:.4f}; "
            f"D_m={D}, x_surface_norm={x_surface_continuous_normalised}"
        )

    N = int(n_spatial)
    if N < 6:
        raise ValueError(f"n_spatial must be >= 6, got {N}")

    x_grid = np.linspace(x_surface_in_loaf_m, L, N)
    dx = float(x_grid[1] - x_grid[0])
    dx2 = dx * dx

    Lu_val = float(Lu)
    q_bot = float(q_bottom_eff)
    alpha_pre = float(alpha_pre_m2_s)
    alpha_ratio_val = float(alpha_ratio)

    # Phase-change coupling: ε·L_v/c expressed via Ko·ΔT_ref/u_init.
    # Use the observed surface range as ΔT_ref for nondim consistency.
    T_surf_arr_full = np.asarray(T_surface_K_t, dtype=float)
    T_surf_max = float(np.nanmax(T_surf_arr_full)) if T_surf_arr_full.size else 450.0
    delta_T_ref = max(T_surf_max - float(T_initial_K), 1.0)
    L_over_c_eff = float(Ko) * delta_T_ref / max(float(u_initial), 1e-6)
    coupling_eps_Lv_c = float(epsilon) * L_over_c_eff
    delta_soret_val = float(delta_soret) * float(u_initial) / delta_T_ref

    t_grid_arr = np.asarray(t_grid_s, dtype=float)
    if t_grid_arr.size < 2:
        raise ValueError("t_grid_s must have at least 2 samples")
    if T_surf_arr_full.shape != t_grid_arr.shape:
        raise ValueError(
            f"T_surface_K_t must have shape {t_grid_arr.shape}; "
            f"got {T_surf_arr_full.shape}"
        )

    def _interp_surface(t: float) -> float:
        return float(np.interp(t, t_grid_arr, T_surf_arr_full))

    # Stiff Dirichlet relaxation timescale (small fraction of dx²/α).
    tau_T_clamp = 0.05 * dx2 / max(alpha_pre, 1e-12)
    tau_u_clamp = 0.05 * dx2 / max(alpha_pre * Lu_val, 1e-12)

    def _laplacian_T(T: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        Lap = np.empty(N, dtype=float)
        if N > 2:
            Lap[1:-1] = (T[:-2] - 2.0 * T[1:-1] + T[2:]) / dx2
        # Top BC at i=0: Dirichlet — laplacian still computed centered using
        # the imposed-temperature ghost. Ghost T_{-1} = 2·T_imposed - T[0].
        # Since T[0] is held to T_imposed by stiff clamp, this reduces to
        # standard centred laplacian using T[1] and T_{-1}=T_imposed (as a
        # one-sided extrapolation).
        # Concretely: Lap[0] = (2·T_imposed - 2·T[0] + T[1] - T[1]) / dx2
        # is undefined geometrically. Use mirrored ghost: T_{-1} = T[0] (no
        # heat flux at the boundary cell — Lap[0] won't drive T[0] since
        # the stiff clamp dominates).
        Lap[0] = (T[0] - 2.0 * T[0] + T[1]) / dx2  # = (T[1] - T[0]) / dx2

        # Bottom BC at i=N-1: -k·dT/dx|_L = q_bot · (T_initial - T_last)
        # Outward normal at x=L is +x → standard discrete ghost:
        # T_N = T_{N-1} + dx · q_bot · (T_initial - T_last) / k
        T_last = T[-1]
        ghost_bot = T_last + dx * q_bot * (T_initial_K - T_last) / K_DOUGH_W_MK
        Lap[-1] = (T[-2] - 2.0 * T_last + ghost_bot) / dx2

        alpha_arr = _alpha_profile(
            T, alpha_pre, alpha_ratio_val,
            spring_temp_lower_K, spring_temp_upper_K,
        )
        return Lap, alpha_arr

    def _laplacian_u(u: np.ndarray) -> np.ndarray:
        Lap = np.empty(N, dtype=float)
        if N > 2:
            Lap[1:-1] = (u[:-2] - 2.0 * u[1:-1] + u[2:]) / dx2
        # Dirichlet u=0 at top: ghost u_{-1} = -u[0]
        Lap[0] = (-u[0] - 2.0 * u[0] + u[1]) / dx2
        # Neumann at bottom: ghost u_N = u[N-2]
        Lap[-1] = (u[-2] - 2.0 * u[-1] + u[-2]) / dx2
        return Lap

    n_state = 2 * N

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        T = y[:N]
        u = y[N:]
        d2T, alpha_arr = _laplacian_T(T)
        d2u = _laplacian_u(u)
        du_dt = alpha_arr * Lu_val * d2u + alpha_arr * Lu_val * delta_soret_val * d2T
        dT_dt = alpha_arr * d2T + coupling_eps_Lv_c * du_dt
        # Stiff Dirichlet clamp on T[0] (top, observed surface).
        T_imposed = _interp_surface(t)
        dT_dt[0] = (T_imposed - T[0]) / tau_T_clamp
        # Stiff Dirichlet clamp on u[0] (top, free evap).
        du_dt[0] = (0.0 - u[0]) / tau_u_clamp
        out = np.empty(n_state, dtype=float)
        out[:N] = dT_dt
        out[N:] = du_dt
        return out

    y0 = np.empty(n_state, dtype=float)
    y0[:N] = float(T_initial_K)
    y0[N:] = float(u_initial)
    # Initialise top to first observed surface T (avoids transient blast).
    y0[0] = float(T_surf_arr_full[0])
    y0[N] = 0.0

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

    return LuikovDirichletHybridForward(
        T_field_K=T_sample,
        u_field=u_sample,
        t_grid_s=t_grid_arr,
        x_grid_m=x_grid,
        T_full_K=T_xt,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Derived core depth
# ---------------------------------------------------------------------------


def infer_core_depth_from_forward(
    T_full_K: np.ndarray,
    x_grid_m: np.ndarray,
    t_grid_s: np.ndarray,
    sample_frac: float = 0.5,
) -> float:
    """Position (mm from top of loaf) of T-min at mid-bake snapshot."""
    n_t = T_full_K.shape[0]
    i_mid = max(0, min(int(sample_frac * n_t), n_t - 1))
    T_snap = T_full_K[i_mid]
    j_min = int(np.argmin(T_snap))
    return float(x_grid_m[j_min] * 1000.0)


# ---------------------------------------------------------------------------
# Inverse fit
# ---------------------------------------------------------------------------


PARAM_NAMES_HYBRID = ("L_m", "D_m", "Lu", "q_bottom_eff", "alpha_ratio", "alpha_pre")


def fit_luikov_dirichlet_hybrid_inverse(
    df: pd.DataFrame,
    in_dough_sensors: list,
    T_surface_K_t: np.ndarray,
    x_surface_continuous_normalised: float,
    sensor_positions_mm: tuple = SENSOR_POSITIONS_MM_FROM_TIP,
    sensor_names: tuple = SENSOR_NAMES_DEFAULT,
    init: Optional[dict] = None,
    bounds: Optional[dict] = None,
    sample_period_s: float = 5.0,
    downsample_factor: int = 4,
    n_spatial: int = 60,
    startup_skip_frac: float = 0.20,
    max_iter: int = 600,
    rtol: float = 1e-5,
    atol: float = 1e-7,
    method: str = "LSODA",
) -> dict:
    """5-parameter Nelder-Mead inverse fit with M2a-Dirichlet top BC.

    Parameters
    ----------
    df:
        DataFrame with ``Timestamp`` (seconds) and the sensor columns.
    in_dough_sensors:
        Names of the in-dough sensors used in the fit (M2a output).
    T_surface_K_t:
        Per-timestep observed surface temperature (Kelvin) from the
        per-timestep linear spatial interpolation at the M2a surface
        position. Shape must match ``df`` length.
    x_surface_continuous_normalised:
        M2a-detected continuous surface position, normalised to the probe
        span (0 = T1/tip, 1 = T8/stem).
    """
    init = init or {}
    bounds = bounds or {}

    init_vals = {
        "L_m": float(init.get("L_m", 0.100)),
        "D_m": float(init.get("D_m", 0.070)),
        "Lu": float(init.get("Lu", 0.15)),
        "q_bottom_eff": float(init.get("q_bottom_eff", 20.0)),
        "alpha_ratio": float(init.get("alpha_ratio", 0.4)),
        "alpha_pre": float(init.get("alpha_pre", 1.0e-6)),
    }
    bnd = {
        "L_m": bounds.get("L_m", (0.060, 0.200)),
        "D_m": bounds.get("D_m", (0.054, 0.095)),
        "Lu": bounds.get("Lu", (1e-4, 5.0)),
        "q_bottom_eff": bounds.get("q_bottom_eff", (0.0, 200.0)),
        "alpha_ratio": bounds.get("alpha_ratio", (0.2, 1.0)),
        # alpha_pre bounds span literature for bread effective α:
        # 1e-7 (molecular dough lower) to 5e-6 (high-EDC upper)
        "alpha_pre": bounds.get("alpha_pre", (1.0e-7, 5.0e-6)),
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

    # Resample surface series onto the downsampled t_obs grid.
    surf_full = np.asarray(T_surface_K_t, dtype=float)
    if len(surf_full) != len(t_full):
        raise ValueError(
            f"T_surface_K_t length {len(surf_full)} must match df length {len(t_full)}"
        )
    surf_obs = surf_full[sl]
    if not np.all(np.isfinite(surf_obs)):
        finite = np.isfinite(surf_obs)
        if finite.any():
            idx = np.arange(len(surf_obs))
            surf_obs = np.interp(idx, idx[finite], surf_obs[finite])
        else:
            surf_obs = np.full_like(surf_obs, T_initial_K)

    n_t_total = len(t_obs)
    n_skip = max(int(startup_skip_frac * n_t_total), 0)
    if n_skip >= n_t_total - 5:
        n_skip = max(n_t_total // 4, 0)

    p_m = np.asarray(sensor_positions_mm, dtype=float) / 1000.0
    pos_by_name = dict(zip(sensor_names, p_m))
    p_obs_m = np.array([pos_by_name[s] for s in in_dough_sensors], dtype=float)

    x_surf_norm = float(x_surface_continuous_normalised)

    # Reparametrise: linear on L_m, D_m, q_bottom_eff, alpha_ratio; log on Lu and alpha_pre.
    def _theta_to_params(theta: np.ndarray) -> dict:
        return {
            "L_m": float(theta[0]),
            "D_m": float(theta[1]),
            "Lu": float(np.exp(theta[2])),
            "q_bottom_eff": float(theta[3]),
            "alpha_ratio": float(theta[4]),
            "alpha_pre": float(np.exp(theta[5])),
        }

    def _bounds_penalty(p: dict) -> float:
        for name, val in p.items():
            lo, hi = bnd[name]
            if not (lo <= val <= hi):
                return 1e10
        return 0.0

    def _x_surface_in_loaf(p: dict) -> float:
        return p["D_m"] - x_surf_norm * PROBE_T_SPAN_M

    def _loss(theta: np.ndarray) -> float:
        p = _theta_to_params(theta)
        pen = _bounds_penalty(p)
        if pen > 0:
            return pen
        # Sensor depths in loaf frame: d_i = D - p_i (top of loaf at x=0).
        d_obs_m = p["D_m"] - p_obs_m
        if np.any(d_obs_m < -1e-4):
            return 1e9
        if np.any(d_obs_m > p["L_m"] + 1e-4):
            return 1e9
        # Surface must be inside [0, L) for the dough domain to make sense.
        x_surf_loaf = _x_surface_in_loaf(p)
        if x_surf_loaf >= p["L_m"] - 1e-4:
            return 1e9
        if x_surf_loaf < -1e-4:
            return 1e9
        x_surf_loaf_clipped = max(0.0, x_surf_loaf)
        # Sensors must lie inside [x_surface_in_loaf, L].
        if np.any(d_obs_m < x_surf_loaf_clipped - 1e-4):
            return 1e9
        d_clipped = np.clip(d_obs_m, x_surf_loaf_clipped, p["L_m"])
        try:
            fwd = solve_luikov_dirichlet_hybrid_forward(
                L_m=p["L_m"],
                D_m=p["D_m"],
                Lu=p["Lu"],
                q_bottom_eff=p["q_bottom_eff"],
                alpha_ratio=p["alpha_ratio"],
                alpha_pre_m2_s=p["alpha_pre"],
                t_grid_s=t_obs,
                T_surface_K_t=surf_obs,
                x_surface_continuous_normalised=x_surf_norm,
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

    theta0 = np.array(
        [
            init_vals["L_m"],
            init_vals["D_m"],
            float(np.log(max(init_vals["Lu"], 1e-6))),
            init_vals["q_bottom_eff"],
            init_vals["alpha_ratio"],
            float(np.log(max(init_vals["alpha_pre"], 1e-9))),
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

    # Re-run forward at fitted params for x_core inference.
    d_obs_m = p_hat["D_m"] - p_obs_m
    x_surf_loaf_hat = max(0.0, _x_surface_in_loaf(p_hat))
    d_clipped = np.clip(d_obs_m, x_surf_loaf_hat, p_hat["L_m"])
    try:
        fwd_full = solve_luikov_dirichlet_hybrid_forward(
            L_m=p_hat["L_m"],
            D_m=p_hat["D_m"],
            Lu=p_hat["Lu"],
            q_bottom_eff=p_hat["q_bottom_eff"],
            alpha_ratio=p_hat["alpha_ratio"],
            alpha_pre_m2_s=p_hat["alpha_pre"],
            t_grid_s=t_obs,
            T_surface_K_t=surf_obs,
            x_surface_continuous_normalised=x_surf_norm,
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
    h_per = [2e-3, 2e-3, 0.05, 1.0, 0.02, 0.05]
    n_param = 6
    try:
        H = _numerical_hessian(_loss, opt.x, h=h_per)
        dof = max(n_obs_fit - n_param, 1)
        sigma2 = sse / dof
        cov_inflate = 1.4 ** 2
        Cov_theta = 2.0 * sigma2 * cov_inflate * np.linalg.pinv(H)
        # Delta-method jacobian: param = J · theta. Lu and alpha_pre via log.
        J = np.diag([1.0, 1.0, p_hat["Lu"], 1.0, 1.0, p_hat["alpha_pre"]])
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

    bound_status = {n: _at_bound(n, p_hat[n]) for n in PARAM_NAMES_HYBRID}
    n_interior = sum(1 for v in bound_status.values() if v == "interior")

    se_dict = {
        f"{name}_se": float(stderr[i])
        for i, name in enumerate(PARAM_NAMES_HYBRID)
    }

    out = {
        **p_hat,
        **se_dict,
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
        "x_surface_in_loaf_mm": float(x_surf_loaf_hat * 1000.0),
        "x_surface_continuous_normalised": float(x_surf_norm),
        "param_at_bound": bound_status,
        "n_interior_params": n_interior,
        "param_names": list(PARAM_NAMES_HYBRID),
        "n_param": n_param,
    }
    return out
