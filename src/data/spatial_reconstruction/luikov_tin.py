"""HMS Sirius — M15 Luikov inverse with corrected geometry and asymmetric tin BCs.

This module is the post-flotilla research reformulation that addresses three
compounding methodology errors in M14 (HMS Lively):

1. **Loaf thickness** — sandwich loaves are ~100 mm, not 50 mm.
2. **Probe geometry** — the Combustion probe T1-T8 span a fixed 95 mm
   (13.571 mm sensor pitch) regardless of loaf size. The previous model
   normalised sensor positions to the loaf, which conflated probe and
   loaf scales.
3. **Boundary conditions** — bread is in a tin: radiative-convective top
   to oven, conductive bottom through the tin. Symmetric Neumann at the
   "deep" end is wrong physics.

Geometry
--------

Loaf coordinate ``x ∈ [0, L]`` with ``x=0`` at the **top** (oven-facing)
surface and ``x=L`` at the **bottom** (tin contact). Probe sits along the
vertical axis with the tip at depth ``D`` below the top. Sensor i (T_i)
is at probe-relative ``p_i = (i-1) · 13.571 mm`` from the tip, so its
loaf-frame depth is ``d_i = D − p_i``. T1 is deepest, T8 is closest to
the probe stem.

Sensors with ``d_i < 0`` are above the loaf (in air) → excluded from
fitting (M2a role classification handles this upstream). Sensors with
``d_i > L`` are below the loaf bottom → unphysical → triggers a sanity
flag (``D`` too large for assumed ``L``).

Forward model
-------------

Coupled heat and moisture transport (Luikov 1966) on ``x ∈ [0, L]``:

.. math::

   \\frac{\\partial T}{\\partial t}
       &= \\alpha \\frac{\\partial^2 T}{\\partial x^2}
          + \\frac{\\varepsilon L_v}{c} \\frac{\\partial u}{\\partial t}\\\\
   \\frac{\\partial u}{\\partial t}
       &= \\alpha \\, \\mathrm{Lu} \\, \\frac{\\partial^2 u}{\\partial x^2}
          + \\alpha \\, \\mathrm{Lu} \\, \\delta
            \\frac{\\partial^2 T}{\\partial x^2}

with constants pinned per the briefing: ``α = 1.4e-7 m²/s``,
``c = 2000 J/(kg·K)``, ``L_v = 2.26e6 J/kg``, ``u_init = 0.4``,
``ε = 0.5``, ``δ = 2.0``.

Boundary conditions
-------------------

* **Top (x = 0, oven-facing)** — convective + radiative coupling::

      −k · ∂T/∂x|_{x=0} = h_top · (T_oven − T) + ε_rad · σ · (T_oven⁴ − T⁴)

  where ``Bi_top = h_top · L / k`` and ``T_oven_eff_K`` are free.

* **Bottom (x = L, tin contact)** — convective coupling through the tin::

      +k · ∂T/∂x|_{x=L} = h_bottom · (T_tin − T)

  with ``Bi_bottom = h_bottom · L / k`` and ``T_tin_eff_K`` free. The
  ``+`` sign on the gradient is because the outward normal points in
  ``+x`` at the bottom; energy flowing IN from the tin makes ``T``
  rise.

* **Moisture (top)** — Dirichlet ``u(0, t) = 0`` (free evaporation from
  crust).

* **Moisture (bottom)** — Neumann ``∂u/∂x|_{L} = 0`` (no moisture loss
  through the tin).

Free parameters (8)
-------------------

==============  ====================  ========  ==========================
parameter       bounds                init      role
==============  ====================  ========  ==========================
``L_m``         (0.060, 0.150)        0.100     full loaf thickness (m)
``D_m``         (0.054, 0.095)        0.070     probe insertion depth (m)
``Lu``          (1e-4, 5)             0.15      Luikov number
``Ko``          (0.05, 100)           4.0       Kossovitch number
``Bi_top``      (0.5, 500)            10        top heat transfer
``Bi_bottom``   (0.05, 200)           2         tin heat transfer
``T_oven_K``    (350, 600)            450       top oven eff. temp
``T_tin_K``     (340, 600)            410       tin eff. temp
==============  ====================  ========  ==========================

A soft penalty enforces ``T_tin_K ≤ T_oven_K`` so the optimizer can
explore the boundary without a hard constraint.

Derived quantity: **``x_core_depth_inferred_mm``**
--------------------------------------------------

The core depth is *not* a parameter. After fitting, we report the
position ``x*`` along the loaf where the rate of temperature increase
during the mid-bake is minimised — the slowest-rising point. With
asymmetric BCs the geometric core is no longer at ``L/2``; the value of
``x*`` is the actual physical answer the user wants.

Public API
----------

* :func:`solve_luikov_tin_forward` — coupled-PDE forward solver (LSODA,
  method-of-lines).
* :func:`fit_luikov_tin_inverse` — 8-parameter Nelder-Mead joint fit.
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
# Pinned physical constants
# ---------------------------------------------------------------------------

ALPHA_M2_S = 1.4e-7              # thermal diffusivity, m²/s
C_DOUGH_J_KGK = 2.0e3            # specific heat, J/(kg·K)
L_VAP_J_KG = 2.26e6              # latent heat of vaporisation, J/kg
U_INITIAL = 0.4                  # initial moisture mass fraction
EPSILON = 0.5                    # phase-change criterion (vapour fraction)
DELTA_POSNOV = 2.0               # Posnov number
EPSILON_RAD = 0.85               # crust emissivity (typical)
SIGMA_SB = 5.670374419e-8        # Stefan-Boltzmann, W/(m²·K⁴)
K_DOUGH_W_MK = 0.5               # thermal conductivity, W/(m·K)

# Probe geometry (briefing — exact numbers).
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
class LuikovTinForward:
    """Output of :func:`solve_luikov_tin_forward`."""

    T_field_K: np.ndarray   # (n_t, n_sample)
    u_field: np.ndarray
    t_grid_s: np.ndarray
    x_grid_m: np.ndarray    # full spatial grid [0, L]
    T_full_K: np.ndarray    # (n_t, n_spatial) — for core inference
    converged: bool


def solve_luikov_tin_forward(
    *,
    L_m: float,
    Lu: float,
    Ko: float,
    Bi_top: float,
    Bi_bottom: float,
    T_oven_K: float,
    T_tin_K: float,
    t_grid_s: np.ndarray,
    T_initial_K: float,
    sample_x_m: Optional[np.ndarray] = None,
    u_initial: float = U_INITIAL,
    epsilon: float = EPSILON,
    delta_posnov: float = DELTA_POSNOV,
    alpha_m2_s: float = ALPHA_M2_S,
    epsilon_rad: float = EPSILON_RAD,
    n_spatial: int = 60,
    rtol: float = 1e-5,
    atol: float = 1e-7,
    method: str = "LSODA",
) -> LuikovTinForward:
    """Solve the coupled Luikov system on ``x ∈ [0, L_m]`` with asymmetric BCs.

    Top (x=0): convective + radiative ↔ T_oven_K.
    Bottom (x=L): convective ↔ T_tin_K (tin contact).
    Moisture: Dirichlet u=0 at top, Neumann ∂u/∂x=0 at bottom.

    Implementation
    --------------
    Method of lines: ``N = n_spatial`` uniform grid, central-difference
    Laplacian with Robin (top, mixed convective+radiative) and Robin
    (bottom, convective-tin) ghost cells. State vector
    ``y = [T_0..T_{N-1}, u_0..u_{N-1}]`` integrated by ``LSODA``.

    The radiative term linearises about the current top-cell temperature;
    we use the discrete Robin form

        T_{−1} = T_0 + dx · q_top / k

    with

        q_top = h_top · (T_oven − T_0) + ε_rad · σ · (T_oven^4 − T_0^4).

    Translated to dimensionless Bi: ``h_top = Bi_top · k / L``.
    """
    if alpha_m2_s <= 0:
        raise ValueError(f"alpha_m2_s must be > 0, got {alpha_m2_s}")
    if Lu <= 0:
        raise ValueError(f"Lu must be > 0, got {Lu}")
    if Bi_top <= 0:
        raise ValueError(f"Bi_top must be > 0, got {Bi_top}")
    if Bi_bottom <= 0:
        raise ValueError(f"Bi_bottom must be > 0, got {Bi_bottom}")
    if L_m <= 0:
        raise ValueError(f"L_m must be > 0, got {L_m}")

    L = float(L_m)
    N = int(n_spatial)
    if N < 6:
        raise ValueError(f"n_spatial must be >= 6, got {N}")

    x_grid = np.linspace(0.0, L, N)
    dx = float(x_grid[1] - x_grid[0])
    dx2 = dx * dx

    # Convective coefficients from Bi: h = Bi · k / L.
    h_top_W_m2K = float(Bi_top) * K_DOUGH_W_MK / L
    h_bot_W_m2K = float(Bi_bottom) * K_DOUGH_W_MK / L

    # Phase-change coupling: the standard Luikov form puts ε · L_v / c
    # as the coefficient on ∂u/∂t in the heat equation. Kossovitch
    # number Ko = L_v · u_init / (c · ΔT_ref) is the dimensionless
    # version with ΔT_ref as the bake driving range. We treat Ko as a
    # free parameter (per the briefing) and recover the dimensional
    # coupling via:
    #     L_v / c = Ko · ΔT_ref / u_init
    # so the effective coefficient is ε · Ko · ΔT_ref / u_init.
    delta_T_ref = max(float(T_oven_K) - float(T_initial_K), 1.0)
    L_over_c_eff = float(Ko) * delta_T_ref / max(float(u_initial), 1e-6)
    coupling_eps_Lv_c = float(epsilon) * L_over_c_eff
    delta_soret = float(delta_posnov) * float(u_initial) / delta_T_ref

    alpha = float(alpha_m2_s)
    Lu_val = float(Lu)
    eps_rad = float(epsilon_rad)

    def _laplacian_T(T: np.ndarray) -> np.ndarray:
        Lap = np.empty(N, dtype=float)
        if N > 2:
            Lap[1:-1] = (T[:-2] - 2.0 * T[1:-1] + T[2:]) / dx2
        # Top BC at i=0: −k·dT/dx|_0 = q_top
        # Discrete: (T[0] - T_{-1}) / dx = -q_top / k
        # ⇒ T_{-1} = T[0] + dx · q_top / k
        T0 = T[0]
        q_top = h_top_W_m2K * (T_oven_K - T0) + eps_rad * SIGMA_SB * (
            T_oven_K ** 4 - T0 ** 4
        )
        ghost_top = T0 + dx * q_top / K_DOUGH_W_MK
        Lap[0] = (ghost_top - 2.0 * T0 + T[1]) / dx2

        # Bottom BC at i=N-1: +k·dT/dx|_L = h_bot · (T_tin − T)
        # Discrete: (T_N - T[N-1]) / dx = (h_bot/k) · (T_tin - T[N-1])
        # ⇒ T_N = T[N-1] + dx · (h_bot/k) · (T_tin - T[N-1])
        T_last = T[-1]
        ghost_bot = T_last + dx * (h_bot_W_m2K / K_DOUGH_W_MK) * (
            T_tin_K - T_last
        )
        Lap[-1] = (T[-2] - 2.0 * T_last + ghost_bot) / dx2
        return Lap

    def _laplacian_u(u: np.ndarray) -> np.ndarray:
        Lap = np.empty(N, dtype=float)
        if N > 2:
            Lap[1:-1] = (u[:-2] - 2.0 * u[1:-1] + u[2:]) / dx2
        # Dirichlet u=0 at i=0: ghost u_{-1} = -u[0]
        ghost_top = -u[0]
        Lap[0] = (ghost_top - 2.0 * u[0] + u[1]) / dx2
        # Neumann ∂u/∂x = 0 at i=N-1: ghost u_N = u[N-2]
        Lap[-1] = (u[-2] - 2.0 * u[-1] + u[-2]) / dx2
        return Lap

    # Stiff Dirichlet clamp on u[0] toward 0.
    tau_u = 0.05 * dx2 / max(alpha * Lu_val, 1e-12)

    n_state = 2 * N

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        T = y[:N]
        u = y[N:]
        d2T = _laplacian_T(T)
        d2u = _laplacian_u(u)
        du_dt = alpha * Lu_val * d2u + alpha * Lu_val * delta_soret * d2T
        dT_dt = alpha * d2T + coupling_eps_Lv_c * du_dt
        # Stiff Dirichlet clamp on u[0] (top, evaporation).
        du_dt[0] = (0.0 - u[0]) / tau_u
        out = np.empty(n_state, dtype=float)
        out[:N] = dT_dt
        out[N:] = du_dt
        return out

    y0 = np.empty(n_state, dtype=float)
    y0[:N] = float(T_initial_K)
    y0[N:] = float(u_initial)
    y0[N] = 0.0  # Dirichlet u(0) = 0 at t=0.

    t_grid = np.asarray(t_grid_s, dtype=float)
    if t_grid.size < 2:
        raise ValueError("t_grid_s must have at least 2 samples")
    t_span = (float(t_grid[0]), float(t_grid[-1]))

    sol = solve_ivp(
        rhs,
        t_span,
        y0,
        t_eval=t_grid,
        method=method,
        rtol=rtol,
        atol=atol,
    )

    converged = bool(sol.success)
    if not converged:
        T_xt = np.full((t_grid.size, N), float(T_initial_K), dtype=float)
        u_xt = np.full((t_grid.size, N), float(u_initial), dtype=float)
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
        T_sample = np.empty((t_grid.size, sample.size), dtype=float)
        u_sample = np.empty((t_grid.size, sample.size), dtype=float)
        for i in range(t_grid.size):
            T_sample[i, :] = np.interp(sample, x_grid, T_xt[i, :])
            u_sample[i, :] = np.interp(sample, x_grid, u_xt[i, :])

    return LuikovTinForward(
        T_field_K=T_sample,
        u_field=u_sample,
        t_grid_s=t_grid,
        x_grid_m=x_grid,
        T_full_K=T_xt,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Sensor mapping
# ---------------------------------------------------------------------------


def sensor_depths_mm_from_D(
    D_mm: float,
    sensor_positions_mm: tuple = SENSOR_POSITIONS_MM_FROM_TIP,
) -> np.ndarray:
    """Compute per-sensor depths below the top loaf surface.

    ``d_i = D − p_i`` where ``p_i`` is the probe-relative position from
    the tip (T1 is at the tip → ``p_1 = 0``).
    """
    p = np.asarray(sensor_positions_mm, dtype=float)
    return float(D_mm) - p


# ---------------------------------------------------------------------------
# Derived core depth
# ---------------------------------------------------------------------------


def infer_core_depth_from_forward(
    T_full_K: np.ndarray,
    x_grid_m: np.ndarray,
    t_grid_s: np.ndarray,
    sample_frac: float = 0.5,
) -> float:
    """Position (mm from top) of the temperature minimum at mid-bake.

    The "core" is the slowest-heating point: at the mid-time snapshot
    of the bake, this is the position where T is minimum. With asymmetric
    BCs this need not be at L/2; with symmetric BCs and matching target
    temperatures it should land near L/2.

    Note: we deliberately avoid argmin of dT/dt because the surface can
    plateau early (its rate dropping to ~0 once near T_oven) while the
    interior is still rising — argmin(rate) picks the surface in that
    case. The temperature minimum at mid-bake is more robust.
    """
    n_t = T_full_K.shape[0]
    i_mid = int(sample_frac * n_t)
    i_mid = max(0, min(i_mid, n_t - 1))
    T_snap = T_full_K[i_mid]
    j_min = int(np.argmin(T_snap))
    return float(x_grid_m[j_min] * 1000.0)


# ---------------------------------------------------------------------------
# Inverse fit
# ---------------------------------------------------------------------------


PARAM_NAMES = (
    "L_m", "D_m", "Lu", "Ko", "Bi_top", "Bi_bottom", "T_oven_K", "T_tin_K",
)


def _build_obs_matrix(
    df: pd.DataFrame,
    in_dough_sensors: list,
    downsample_factor: int,
) -> tuple[np.ndarray, np.ndarray]:
    t_full = df["Timestamp"].to_numpy(dtype=float)
    if downsample_factor < 1:
        downsample_factor = 1
    sl = slice(0, len(t_full), int(downsample_factor))
    t_obs = t_full[sl]
    T_cols = [df[s].to_numpy(dtype=float)[sl] for s in in_dough_sensors]
    T_obs_C = np.column_stack(T_cols)
    return t_obs, T_obs_C


def fit_luikov_tin_inverse(
    df: pd.DataFrame,
    in_dough_sensors: list,
    sensor_positions_mm: tuple = SENSOR_POSITIONS_MM_FROM_TIP,
    sensor_names: tuple = SENSOR_NAMES_DEFAULT,
    init: Optional[dict] = None,
    bounds: Optional[dict] = None,
    sample_period_s: float = 5.0,
    downsample_factor: int = 4,
    n_spatial: int = 60,
    startup_skip_frac: float = 0.20,
    max_iter: int = 1000,
    rtol: float = 1e-5,
    atol: float = 1e-7,
    method: str = "LSODA",
    soft_constraint_weight: float = 1e6,
) -> dict:
    """8-parameter Nelder-Mead joint fit of the asymmetric-BC Luikov inverse.

    Parameters
    ----------
    sensor_positions_mm
        Per-sensor probe-relative positions (mm from the tip). Defaults
        to ``(i-1) · 13.571 mm`` for i=1..8 — the Combustion probe
        geometry.

    Returns
    -------
    dict with keys:
        - ``L_m``, ``D_m``, ``Lu``, ``Ko``, ``Bi_top``, ``Bi_bottom``,
          ``T_oven_K``, ``T_tin_K`` and their ``*_se``
        - ``full_correlation_matrix`` (8×8), ``max_abs_off_diag``
        - ``sse``, ``rmse_per_sensor``, ``n_obs``, ``converged``,
          ``n_iter``
        - ``x_core_depth_inferred_mm`` — derived from forward profile
        - ``sensor_depths_mm`` — d_i = D − p_i
        - ``any_sensor_below_loaf`` — True if any d_i > L (sanity flag)
        - ``param_at_bound`` — dict mapping each param to True/False
    """
    init = init or {}
    bounds = bounds or {}

    # Defaults per the briefing.
    init_vals = {
        "L_m": float(init.get("L_m", 0.100)),
        "D_m": float(init.get("D_m", 0.070)),
        "Lu": float(init.get("Lu", 0.15)),
        "Ko": float(init.get("Ko", 4.0)),
        "Bi_top": float(init.get("Bi_top", 10.0)),
        "Bi_bottom": float(init.get("Bi_bottom", 2.0)),
        "T_oven_K": float(init.get("T_oven_K", 450.0)),
        "T_tin_K": float(init.get("T_tin_K", 410.0)),
    }
    bnd = {
        "L_m": bounds.get("L_m", (0.060, 0.150)),
        "D_m": bounds.get("D_m", (0.054, 0.095)),
        "Lu": bounds.get("Lu", (1e-4, 5.0)),
        "Ko": bounds.get("Ko", (0.05, 100.0)),
        "Bi_top": bounds.get("Bi_top", (0.5, 500.0)),
        "Bi_bottom": bounds.get("Bi_bottom", (0.05, 200.0)),
        "T_oven_K": bounds.get("T_oven_K", (350.0, 600.0)),
        "T_tin_K": bounds.get("T_tin_K", (340.0, 600.0)),
    }

    t_obs, T_obs_C = _build_obs_matrix(df, in_dough_sensors, downsample_factor)
    T_obs_K = T_obs_C + 273.15
    T_initial_K = float(np.mean(T_obs_K[0, :]))

    n_t_total = len(t_obs)
    n_skip = max(int(startup_skip_frac * n_t_total), 0)
    if n_skip >= n_t_total - 5:
        n_skip = max(n_t_total // 4, 0)

    # Sensor positions (probe-relative, from tip), m.
    p_m = np.asarray(sensor_positions_mm, dtype=float) / 1000.0
    # In-dough sensor mask via name lookup.
    pos_by_name = dict(zip(sensor_names, p_m))
    p_obs_m = np.array([pos_by_name[s] for s in in_dough_sensors], dtype=float)

    # Reparametrise: log on positive params, linear on others.
    # theta = (L_m, D_m, log Lu, log Ko, log Bi_top, log Bi_bot, T_oven, T_tin)
    def _theta_to_params(theta: np.ndarray) -> dict:
        return {
            "L_m": float(theta[0]),
            "D_m": float(theta[1]),
            "Lu": float(np.exp(theta[2])),
            "Ko": float(np.exp(theta[3])),
            "Bi_top": float(np.exp(theta[4])),
            "Bi_bottom": float(np.exp(theta[5])),
            "T_oven_K": float(theta[6]),
            "T_tin_K": float(theta[7]),
        }

    def _bounds_penalty(p: dict) -> float:
        for name, val in p.items():
            lo, hi = bnd[name]
            if not (lo <= val <= hi):
                return 1e10
        return 0.0

    def _soft_constraint(p: dict) -> float:
        # T_tin_K ≤ T_oven_K (soft).
        excess = p["T_tin_K"] - p["T_oven_K"]
        if excess <= 0:
            return 0.0
        return float(soft_constraint_weight) * (excess ** 2)

    def _loss(theta: np.ndarray) -> float:
        p = _theta_to_params(theta)
        pen = _bounds_penalty(p)
        if pen > 0:
            return pen
        # Sensor depths in loaf frame: d_i = D − p_i (m).
        d_obs_m = p["D_m"] - p_obs_m
        # If any sensor is above the loaf top (negative d) or below the
        # loaf bottom (d > L), the geometry is inconsistent — heavily
        # penalise but keep finite so the optimiser can move out.
        if np.any(d_obs_m < -1e-4):
            return 1e9
        if np.any(d_obs_m > p["L_m"] + 1e-4):
            return 1e9
        # Clip to [0, L] for the interpolation (small numerical slack).
        d_clipped = np.clip(d_obs_m, 0.0, p["L_m"])
        try:
            fwd = solve_luikov_tin_forward(
                L_m=p["L_m"],
                Lu=p["Lu"],
                Ko=p["Ko"],
                Bi_top=p["Bi_top"],
                Bi_bottom=p["Bi_bottom"],
                T_oven_K=p["T_oven_K"],
                T_tin_K=p["T_tin_K"],
                t_grid_s=t_obs,
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
        sse = float(np.sum(diff * diff))
        return sse + _soft_constraint(p)

    theta0 = np.array(
        [
            init_vals["L_m"],
            init_vals["D_m"],
            float(np.log(max(init_vals["Lu"], 1e-6))),
            float(np.log(max(init_vals["Ko"], 1e-6))),
            float(np.log(max(init_vals["Bi_top"], 1e-6))),
            float(np.log(max(init_vals["Bi_bottom"], 1e-6))),
            init_vals["T_oven_K"],
            init_vals["T_tin_K"],
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

    # Hessian → cov → corr.
    h_per = [
        2e-3,    # L_m (m)
        2e-3,    # D_m (m)
        0.05,    # log Lu
        0.05,    # log Ko
        0.05,    # log Bi_top
        0.05,    # log Bi_bottom
        1.0,     # T_oven_K
        1.0,     # T_tin_K
    ]
    try:
        H = _numerical_hessian(_loss, opt.x, h=h_per)
        dof = max(n_obs_fit - 8, 1)
        sigma2 = sse / dof
        cov_inflate = 1.4 ** 2
        Cov_theta = 2.0 * sigma2 * cov_inflate * np.linalg.pinv(H)
        # Delta-method jacobian:  param = J · theta.
        # For log parameters, var(p) = p² · var(log p).
        J = np.diag([
            1.0, 1.0,
            p_hat["Lu"], p_hat["Ko"], p_hat["Bi_top"], p_hat["Bi_bottom"],
            1.0, 1.0,
        ])
        Cov_param = J @ Cov_theta @ J.T
        diag_p = np.maximum(np.diag(Cov_param), 0.0)
        stderr = np.sqrt(diag_p)
        denom = np.outer(stderr, stderr)
        with np.errstate(divide="ignore", invalid="ignore"):
            corr = np.where(denom > 0, Cov_param / denom, np.nan)
        off = np.abs(corr.copy())
        for i in range(off.shape[0]):
            off[i, i] = 0.0
        max_off = (
            float(np.nanmax(off)) if np.any(np.isfinite(off)) else float("nan")
        )
    except Exception:
        stderr = np.full(8, np.nan)
        corr = np.full((8, 8), np.nan)
        max_off = float("nan")

    rmse = float(np.sqrt(sse / max(n_obs_fit, 1)))

    # Derived: re-run the forward at the fitted params over the full grid
    # (no sensor subset) to extract x_core_depth_inferred and to confirm
    # the in-sample fit.
    d_obs_m = p_hat["D_m"] - p_obs_m
    d_clipped = np.clip(d_obs_m, 0.0, p_hat["L_m"])
    try:
        fwd_full = solve_luikov_tin_forward(
            L_m=p_hat["L_m"],
            Lu=p_hat["Lu"],
            Ko=p_hat["Ko"],
            Bi_top=p_hat["Bi_top"],
            Bi_bottom=p_hat["Bi_bottom"],
            T_oven_K=p_hat["T_oven_K"],
            T_tin_K=p_hat["T_tin_K"],
            t_grid_s=t_obs,
            T_initial_K=T_initial_K,
            sample_x_m=d_clipped,
            n_spatial=n_spatial,
        )
        x_core_inferred_mm = infer_core_depth_from_forward(
            fwd_full.T_full_K, fwd_full.x_grid_m, fwd_full.t_grid_s
        )
    except Exception:
        x_core_inferred_mm = float("nan")

    # Sensor depths and below-loaf flag.
    sensor_depths_mm = p_hat["D_m"] * 1000.0 - np.asarray(
        sensor_positions_mm, dtype=float
    )
    any_below_loaf = bool(
        np.any(sensor_depths_mm > p_hat["L_m"] * 1000.0 + 0.1)
    )

    # Bound proximity (within 1% of the bound width or 1e-4 absolute).
    def _at_bound(name: str, val: float) -> str:
        lo, hi = bnd[name]
        width = max(hi - lo, 1e-9)
        if abs(val - lo) < max(0.01 * width, 1e-6):
            return "lo"
        if abs(val - hi) < max(0.01 * width, 1e-6):
            return "hi"
        return "interior"

    bound_status = {
        n: _at_bound(n, p_hat[n]) for n in PARAM_NAMES
    }
    n_interior = sum(1 for v in bound_status.values() if v == "interior")

    out = {
        **p_hat,
        "L_m_se": float(stderr[0]),
        "D_m_se": float(stderr[1]),
        "Lu_se": float(stderr[2]),
        "Ko_se": float(stderr[3]),
        "Bi_top_se": float(stderr[4]),
        "Bi_bottom_se": float(stderr[5]),
        "T_oven_K_se": float(stderr[6]),
        "T_tin_K_se": float(stderr[7]),
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
        "param_names": list(PARAM_NAMES),
    }
    return out
