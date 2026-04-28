"""HMS Lively — M14 Luikov 1D coupled heat-mass transfer inverse problem.

Luikov (1966) model for capillary-porous media with explicit moisture and
vapour transport. After the M9 Stefan PDE (latent-heat front, 4-param) and
M11/M12 Zürcher two-state (radiative BC + crust front, 5-param) inverses
both stalled at 6+ °C main-bake RMSE on real bread CSVs, this module tries
the next class up the hierarchy: a coupled heat-mass system in which the
moisture field provides an *additional* observable constraint via the
phase-change source term, even though we only observe temperature.

Model
-----

State variables: ``T(x, t)`` (temperature, K) and ``u(x, t)`` (local
moisture content, mass fraction).

.. math::

    \\frac{\\partial T}{\\partial t}
        &= \\alpha \\frac{\\partial^2 T}{\\partial x^2}
           + \\frac{\\varepsilon L}{c} \\frac{\\partial u}{\\partial t}
                                                                 \\qquad (1) \\\\
    \\frac{\\partial u}{\\partial t}
        &= \\alpha \\mathrm{Lu} \\frac{\\partial^2 u}{\\partial x^2}
           + \\alpha \\mathrm{Lu} \\delta
             \\frac{\\partial^2 T}{\\partial x^2}                  \\qquad (2)

Substituting (2) into (1) eliminates ``∂u/∂t`` from the RHS, giving a
clean explicit 80-variable ODE system after method-of-lines spatial
discretisation.

Free parameters (5)
-------------------

* ``x_core_m`` — core position in metres from the loaf surface; negative
  means the inferred centre lies past the deepest probe sensor (T1 at
  r = 0). Same convention as the Zürcher inverse.
* ``Lu`` — Luikov number = ``D_m / α`` (mass-vs-heat diffusivity).
  Typical bread range: 0.05-0.5 (mass diffuses slower than heat).
* ``Ko`` — Kossovitch number = ``L · u_initial / (c · ΔT_ref)``.
  Typical bread range: 1-10 (latent heat dominates over sensible).
* ``Bi`` — surface Biot number = ``h · R / k`` (convective-to-conductive
  heat transfer at the surface). Typical range: 0.5-10.
* ``T_oven_eff_K`` — effective environmental temperature driving the
  surface convection BC. Free as in M11/M12 because the user's CSVs
  lack oven-setpoint metadata.

Pinned constants (3)
--------------------

* ``alpha_m2_s = 1.4e-7 m²/s`` — thermal diffusivity (literature
  bread value, within ±30%).
* ``epsilon = 0.5`` — phase-change criterion (typical mid-bake value).
* ``u_initial = 0.4`` — initial moisture mass fraction (standard
  sandwich-bread).

Avoiding the M7 tautology trap
------------------------------

The synthetic-recovery harness (see ``tests/_driver_luikov.py``)
generates data with **different ε and α** than the inverter uses, so
the synthetic data class genuinely differs from the inverter's
interpretation — recovering (Lu, Ko, Bi, x_core) within 30% becomes a
real test of partial identifiability, not a tautology.

Numerical care
--------------

The coupled system can be stiff when Lu << 1 (moisture evolves slowly
while T evolves fast). We use ``scipy.integrate.solve_ivp`` with method
``LSODA`` (auto-switching stiff/non-stiff) and the state vector
``(T_0, …, T_{N-1}, u_0, …, u_{N-1})`` of size ``2N``.

Boundary conditions
-------------------

* **Surface (x = x_surface)** — convective heat transfer:
  ``-k·∂T/∂x = h·(T_surface - T_oven_eff_K)``, dimensionless form
  ``∂T/∂x = -Bi/R · (T - T_oven_eff_K)`` at x = x_surface.
* **Surface moisture (x = x_surface)** — Dirichlet ``u = 0`` (dries out;
  bread crust is essentially anhydrous after the bake).
* **Core (x = x_core)** — Neumann symmetry: ``∂T/∂x = 0`` and
  ``∂u/∂x = 0``.
* **Initial condition** — ``T(x, 0) = T_initial_K``, ``u(x, 0) = u_initial``
  uniform.

Coordinate convention
---------------------

Same as M11/M12: surface at physical centre-distance ``r = R``,
sensor T1 at ``r = x_core_m``. The convective Biot BC requires SI
lengths so ``loaf_thickness_m`` (default 50 mm) becomes ``R``.

Public API
----------

* :func:`solve_luikov_forward` — coupled-PDE forward solver (LSODA,
  method-of-lines).
* :func:`fit_luikov_inverse` — 5-parameter Nelder-Mead joint fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import minimize

# Re-use the M7/M9/M11 helpers (DRY).
from .heat_equation import _build_observation_matrix, _numerical_hessian


# ---------------------------------------------------------------------------
# Physical defaults (all SI). Most are pinned in the inverse fit; the user
# can override via the ``physical_constants`` dict on the forward solver.
# ---------------------------------------------------------------------------

ALPHA_DEFAULT_M2_S = 1.4e-7    # thermal diffusivity, m²/s
EPSILON_DEFAULT = 0.5          # phase-change criterion (vapour fraction)
U_INITIAL_DEFAULT = 0.4        # initial moisture mass fraction
PN_DEFAULT = 0.0               # Posnov number (Soret) — pinned 0 by default
LATENT_J_KG = 22.4e5           # latent heat of evaporation, J/kg
C_DOUGH_J_KGK = 2.0e3          # specific heat, J/(kg·K)
RHO_DOUGH_KG_M3 = 1.0e3        # density, kg/m³
K_DOUGH_W_MK = 0.5             # thermal conductivity, W/(m·K)
LOAF_THICKNESS_M_DEFAULT = 0.05  # half-loaf physical thickness, m


# ---------------------------------------------------------------------------
# Forward solver
# ---------------------------------------------------------------------------


@dataclass
class LuikovForward:
    """Output of :func:`solve_luikov_forward`."""

    T_field_K: np.ndarray   # (n_t, n_sample) — temperature at sample positions
    u_field: np.ndarray     # (n_t, n_sample) — moisture at sample positions
    t_grid_s: np.ndarray    # times actually returned
    converged: bool

    def asdict(self) -> dict:
        return {
            "T_field": self.T_field_K,
            "u_field": self.u_field,
            "t_grid": self.t_grid_s,
            "converged": self.converged,
        }


def solve_luikov_forward(
    x_core_m: float,
    Lu: float,
    Ko: float,
    Bi: float,
    T_oven_eff_K: float,
    t_grid_s: np.ndarray,
    T_initial_K: float,
    u_initial: float = U_INITIAL_DEFAULT,
    epsilon: float = EPSILON_DEFAULT,
    alpha_m2_s: float = ALPHA_DEFAULT_M2_S,
    Pn: float = PN_DEFAULT,
    loaf_thickness_m: float = LOAF_THICKNESS_M_DEFAULT,
    n_spatial: int = 40,
    sample_x_m: Optional[np.ndarray] = None,
    rtol: float = 1e-5,
    atol: float = 1e-7,
    method: str = "LSODA",
) -> LuikovForward:
    """Solve the coupled Luikov 1D PDE system on ``t_grid_s``.

    Spatial domain: ``r ∈ [x_core_m, R]`` with ``R = loaf_thickness_m``.

    Method of lines: ``N = n_spatial`` uniform grid points, second
    derivatives via central differences (Neumann ghost cell at the core,
    convective ghost at the surface). State vector
    ``y = [T_0, …, T_{N-1}, u_0, …, u_{N-1}]`` integrated by
    :func:`scipy.integrate.solve_ivp` with method ``LSODA``.

    Parameters
    ----------
    x_core_m, Lu, Ko, Bi, T_oven_eff_K
        Free fit parameters. See module docstring.
    t_grid_s
        Times (seconds) at which to return the solution.
    T_initial_K
        Initial uniform temperature (Kelvin).
    u_initial
        Initial uniform moisture mass fraction.
    epsilon
        Phase-change fraction. Pin 0.5 for typical bread mid-bake.
    alpha_m2_s
        Thermal diffusivity. Pin literature 1.4e-7.
    Pn
        Posnov number (dimensionless thermo-gradient coupling on the
        moisture equation). Pin 0 by default — published Luikov inverse
        solutions in the bread/wood-drying literature commonly omit
        Soret coupling. The forward solver supports Pn != 0 for
        synthetic-recovery experiments.
    loaf_thickness_m
        Half-loaf physical thickness ``R``.
    n_spatial
        Number of spatial grid points (default 40).
    sample_x_m
        Positions (metres from centre) at which to return ``(T, u)``.
        Default: the spatial grid itself.
    rtol, atol, method
        Integrator tunables.
    """
    if alpha_m2_s <= 0:
        raise ValueError(f"alpha_m2_s must be > 0, got {alpha_m2_s}")
    if Lu <= 0:
        raise ValueError(f"Lu must be > 0, got {Lu}")
    if Bi <= 0:
        raise ValueError(f"Bi must be > 0, got {Bi}")

    R = float(loaf_thickness_m)
    x_core = float(x_core_m)
    if R - x_core <= 1e-4:
        raise ValueError(
            f"Domain too thin: R={R}, x_core={x_core}; need R - x_core > 1e-4"
        )

    N = int(n_spatial)
    if N < 6:
        raise ValueError(f"n_spatial must be >= 6, got {N}")

    x_grid = np.linspace(x_core, R, N)
    dx = float(x_grid[1] - x_grid[0])
    dx2 = dx * dx

    # The Kossovitch number provides ε·L/c implicitly: Ko = L·u_init/(c·ΔT)
    # ⇒ L/c = Ko · ΔT / u_init. Use ΔT = (T_oven_eff_K - T_initial_K) as the
    # canonical reference. The phase-change coupling coefficient is then
    # ε · Ko · ΔT / u_init.
    delta_T_ref = max(float(T_oven_eff_K) - float(T_initial_K), 1.0)
    L_over_c = float(Ko) * delta_T_ref / max(float(u_initial), 1e-6)
    coupling_eps_L_c = float(epsilon) * L_over_c

    # Pn = δ · ΔT / u_init  ⇒  δ = Pn · u_init / ΔT.
    delta_soret = float(Pn) * float(u_initial) / delta_T_ref

    # Surface convective BC (heat): the discrete Robin form uses the ghost
    # node T_{N} = T_{N-1} - dx · h/k · (T_{N-1} - T_oven_eff). With Bi =
    # h·R/k we get h/k = Bi/R, so:
    #     (T_{N} - T_{N-1}) / dx = -(Bi/R) · (T_{N-1} - T_oven_eff)
    # ⇒  T_{N} = T_{N-1} - (Bi · dx / R) · (T_{N-1} - T_oven_eff).
    bc_factor = float(Bi) * dx / R

    # Mass surface BC: Dirichlet u = 0 at x = R.
    # We enforce by clamping u[N-1] via a stiff source term in the RHS.
    u_surface_value = 0.0

    alpha = float(alpha_m2_s)
    Lu_val = float(Lu)

    n_state = 2 * N

    def _laplacian_T(T: np.ndarray) -> np.ndarray:
        """Compute d²T/dx² on the grid with Neumann at i=0 and convective Robin at i=N-1."""
        L = np.empty(N, dtype=float)
        # Interior: central difference.
        if N > 2:
            L[1:-1] = (T[:-2] - 2.0 * T[1:-1] + T[2:]) / dx2
        # Neumann at x_core (i=0): ghost T_{-1} = T_1.
        # ⇒ d²T/dx²[0] ≈ 2·(T[1] - T[0]) / dx²
        L[0] = 2.0 * (T[1] - T[0]) / dx2
        # Robin (convective) at surface (i=N-1):
        # ghost T_N = T[N-1] - bc_factor · (T[N-1] - T_oven_eff)
        ghost = T[-1] - bc_factor * (T[-1] - T_oven_eff_K)
        L[-1] = (T[-2] - 2.0 * T[-1] + ghost) / dx2
        return L

    def _laplacian_u(u: np.ndarray) -> np.ndarray:
        """Compute d²u/dx² with Neumann at i=0 and Dirichlet u=0 at i=N-1."""
        L = np.empty(N, dtype=float)
        if N > 2:
            L[1:-1] = (u[:-2] - 2.0 * u[1:-1] + u[2:]) / dx2
        L[0] = 2.0 * (u[1] - u[0]) / dx2
        # Dirichlet u_surface_value at i=N-1: ghost u_N = 2·u_surface_value - u[N-1].
        ghost = 2.0 * u_surface_value - u[-1]
        L[-1] = (u[-2] - 2.0 * u[-1] + ghost) / dx2
        return L

    # Tau for the Dirichlet-clamp on u[N-1]: pull u[N-1] toward 0 fast
    # relative to the moisture diffusion timescale.
    tau_u = 0.05 * dx2 / max(alpha * Lu_val, 1e-12)

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        T = y[:N]
        u = y[N:]
        d2T = _laplacian_T(T)
        d2u = _laplacian_u(u)

        # Compute du/dt first (the moisture equation has no implicit term
        # in the standard Luikov formulation we're using).
        du_dt = alpha * Lu_val * d2u + alpha * Lu_val * delta_soret * d2T

        # Substitute du/dt into the heat equation:
        # ∂T/∂t = α·∂²T/∂x² + (ε·L/c)·∂u/∂t
        dT_dt = alpha * d2T + coupling_eps_L_c * du_dt

        # Stiff Dirichlet-clamp on u[N-1] toward 0 (override diffusion).
        # The Lapl-based contribution we already wrote in is mostly fine
        # (ghost u_N = -u[N-1] pulls it down), but adding an explicit
        # relaxation makes the BC robust under integrator tolerances.
        du_dt[-1] = (u_surface_value - u[-1]) / tau_u

        out = np.empty(n_state, dtype=float)
        out[:N] = dT_dt
        out[N:] = du_dt
        return out

    # Initial state.
    y0 = np.empty(n_state, dtype=float)
    y0[:N] = float(T_initial_K)
    y0[N:] = float(u_initial)
    # Surface-T initial: the convective BC won't be enforced exactly at t=0;
    # it builds up via dynamics. Same convention as the M7/M11 solvers.
    # Surface u initial: clamp to 0 to avoid a t=0 BC discontinuity shock.
    y0[-1] = u_surface_value

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
        # Return what we have, padded.
        T_xt = np.full((t_grid.size, N), float(T_initial_K), dtype=float)
        u_xt = np.full((t_grid.size, N), float(u_initial), dtype=float)
        n_used = sol.y.shape[1] if sol.y.size else 0
        if n_used > 0:
            T_xt[:n_used] = sol.y[:N, :].T
            u_xt[:n_used] = sol.y[N:, :].T
            T_xt[n_used:] = T_xt[n_used - 1]
            u_xt[n_used:] = u_xt[n_used - 1]
    else:
        T_xt = sol.y[:N, :].T  # (n_t, N)
        u_xt = sol.y[N:, :].T

    # Sample at requested positions.
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

    return LuikovForward(
        T_field_K=T_sample,
        u_field=u_sample,
        t_grid_s=t_grid,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Inverse fitter
# ---------------------------------------------------------------------------


SENSOR_NAMES_DEFAULT: tuple = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")
SENSOR_POSITIONS_DEFAULT: tuple = tuple(i / 7 for i in range(8))


def _normalised_to_metres_with_core(
    x_normalised: np.ndarray,
    x_core_m: float,
    x_surface_normalised: float,
    loaf_thickness_m: float,
) -> np.ndarray:
    """Map normalised probe coordinates to physical centre-distance.

    Same convention as the M11 Zürcher inverse: surface at r = R, T1 at
    r = x_core_m. Linear interpolation:

        r_i = x_core_m + (x_n_i / x_surface_norm) · (R - x_core_m).
    """
    x_n = np.asarray(x_normalised, dtype=float)
    x_core = float(x_core_m)
    x_surf = float(x_surface_normalised)
    R = float(loaf_thickness_m)
    if x_surf <= 0:
        raise ValueError(f"x_surface_normalised must be > 0, got {x_surf}")
    return x_core + (x_n / x_surf) * (R - x_core)


def fit_luikov_inverse(
    df: pd.DataFrame,
    in_dough_sensors: list,
    x_surface_normalised: float,
    sensor_positions_normalised: tuple = SENSOR_POSITIONS_DEFAULT,
    sensor_names: tuple = SENSOR_NAMES_DEFAULT,
    init: Optional[dict] = None,
    bounds: Optional[dict] = None,
    sample_period_s: float = 5.0,
    downsample_factor: int = 4,
    loaf_thickness_m: float = LOAF_THICKNESS_M_DEFAULT,
    alpha_m2_s: float = ALPHA_DEFAULT_M2_S,
    epsilon: float = EPSILON_DEFAULT,
    u_initial: float = U_INITIAL_DEFAULT,
    Pn: float = PN_DEFAULT,
    n_spatial: int = 40,
    max_iter: int = 800,
    rtol: float = 1e-5,
    atol: float = 1e-7,
    method: str = "LSODA",
    startup_skip_frac: float = 0.20,
) -> dict:
    """5-parameter Nelder-Mead fit of the Luikov coupled inverse problem.

    Free parameters
    ---------------
    * ``x_core_m`` — core position in metres from the surface.
    * ``Lu`` — Luikov number (mass-vs-heat diffusivity ratio).
    * ``Ko`` — Kossovitch number (latent vs sensible heat).
    * ``Bi`` — surface Biot number.
    * ``T_oven_eff_K`` — effective oven temperature.

    Returns
    -------
    dict with keys mirroring the M11 Zürcher inverse plus the Luikov
    params: ``x_core_m``, ``x_core_normalised``, ``Lu``, ``Ko``, ``Bi``,
    ``T_oven_eff_K``, their ``*_se``, ``full_correlation_matrix``,
    ``max_abs_off_diag_correlation``, ``sse``, ``rmse_per_sensor``,
    ``n_obs``, ``converged``, ``T_initial_K``, ``loaf_thickness_m``,
    ``in_dough``, ``sensor_positions_normalised``.
    """
    init = init or {}
    bounds = bounds or {}

    # Defaults — chosen near the centre of the literature ranges in the
    # briefing: Lu 0.05-0.5, Ko 1-10, Bi 0.5-10.
    x_core_m_init = float(init.get("x_core_m", -0.005))
    Lu_init = float(init.get("Lu", 0.15))
    Ko_init = float(init.get("Ko", 4.0))
    Bi_init = float(init.get("Bi", 3.0))
    T_oven_init = float(init.get("T_oven_eff_K", 450.0))

    x_core_lo, x_core_hi = bounds.get("x_core_m", (-0.04, 0.04))
    Lu_lo, Lu_hi = bounds.get("Lu", (0.01, 2.0))
    Ko_lo, Ko_hi = bounds.get("Ko", (0.1, 30.0))
    Bi_lo, Bi_hi = bounds.get("Bi", (0.1, 50.0))
    T_oven_lo, T_oven_hi = bounds.get("T_oven_eff_K", (350.0, 600.0))

    t_obs, T_obs_C, x_obs_n = _build_observation_matrix(
        df=df,
        in_dough_sensors=in_dough_sensors,
        sensor_names=sensor_names,
        sensor_positions_normalised=sensor_positions_normalised,
        downsample_factor=downsample_factor,
    )
    T_obs_K = T_obs_C + 273.15
    T_initial_K = float(np.mean(T_obs_K[0, :]))

    n_t_total = len(t_obs)
    n_skip = max(int(startup_skip_frac * n_t_total), 0)
    if n_skip >= n_t_total - 5:
        n_skip = max(n_t_total // 4, 0)

    # Optimise in unconstrained reals via squashing transforms:
    #   x_core_m: linear (clamped via penalty)
    #   Lu, Ko, Bi: log
    #   T_oven_eff_K: linear
    def _theta_to_params(theta: np.ndarray) -> tuple:
        x_core = float(theta[0])
        Lu_v = float(np.exp(theta[1]))
        Ko_v = float(np.exp(theta[2]))
        Bi_v = float(np.exp(theta[3]))
        T_oven_v = float(theta[4])
        return x_core, Lu_v, Ko_v, Bi_v, T_oven_v

    def _bounds_penalty(x_core, Lu_v, Ko_v, Bi_v, T_oven_v) -> float:
        if not (x_core_lo <= x_core <= x_core_hi):
            return 1e10
        if not (Lu_lo <= Lu_v <= Lu_hi):
            return 1e10
        if not (Ko_lo <= Ko_v <= Ko_hi):
            return 1e10
        if not (Bi_lo <= Bi_v <= Bi_hi):
            return 1e10
        if not (T_oven_lo <= T_oven_v <= T_oven_hi):
            return 1e10
        return 0.0

    def _loss(theta: np.ndarray) -> float:
        x_core, Lu_v, Ko_v, Bi_v, T_oven_v = _theta_to_params(theta)
        pen = _bounds_penalty(x_core, Lu_v, Ko_v, Bi_v, T_oven_v)
        if pen > 0:
            return pen
        try:
            sample_x_m = _normalised_to_metres_with_core(
                x_normalised=x_obs_n,
                x_core_m=x_core,
                x_surface_normalised=x_surface_normalised,
                loaf_thickness_m=loaf_thickness_m,
            )
        except ValueError:
            return 1e10
        try:
            fwd = solve_luikov_forward(
                x_core_m=x_core,
                Lu=Lu_v,
                Ko=Ko_v,
                Bi=Bi_v,
                T_oven_eff_K=T_oven_v,
                t_grid_s=t_obs,
                T_initial_K=T_initial_K,
                u_initial=u_initial,
                epsilon=epsilon,
                alpha_m2_s=alpha_m2_s,
                Pn=Pn,
                loaf_thickness_m=loaf_thickness_m,
                n_spatial=n_spatial,
                sample_x_m=sample_x_m,
                rtol=rtol,
                atol=atol,
                method=method,
            )
        except Exception:
            return 1e10
        if not fwd.converged:
            return 1e10
        diff = (fwd.T_field_K[n_skip:] - T_obs_K[n_skip:]).ravel()
        if not np.all(np.isfinite(diff)):
            return 1e10
        return float(np.sum(diff * diff))

    theta0 = np.array(
        [
            x_core_m_init,
            float(np.log(max(Lu_init, 1e-3))),
            float(np.log(max(Ko_init, 1e-2))),
            float(np.log(max(Bi_init, 1e-2))),
            T_oven_init,
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
            "maxiter": max_iter,
            "adaptive": True,
        },
    )

    x_core_hat, Lu_hat, Ko_hat, Bi_hat, T_oven_hat = _theta_to_params(opt.x)
    sse = float(opt.fun)
    n_obs_fit = int(T_obs_K[n_skip:].size)
    n_obs_total = int(T_obs_K.size)

    # 5×5 Hessian → covariance → correlation. Step sizes per parameter:
    #   x_core (m, ~0.01): 1e-3 m
    #   log Lu (~ln 0.15 = -1.9): 0.05 (~5% multiplicative)
    #   log Ko (~ln 4 = 1.4):     0.05
    #   log Bi (~ln 3 = 1.1):     0.05
    #   T_oven (K, ~450):         1.0
    h_per_param = [1e-3, 0.05, 0.05, 0.05, 1.0]
    try:
        H_sse = _numerical_hessian(_loss, opt.x, h=h_per_param)
        p_count = 5
        dof = max(n_obs_fit - p_count, 1)
        sigma2 = sse / dof
        cov_inflate = 1.4 ** 2
        Cov_theta = 2.0 * sigma2 * cov_inflate * np.linalg.pinv(H_sse)
        # Delta method jacobian: theta = (x_core, log Lu, log Ko, log Bi, T_oven)
        # → param = (x_core, Lu, Ko, Bi, T_oven). var(Lu) = Lu² · var(log Lu).
        J = np.diag([1.0, Lu_hat, Ko_hat, Bi_hat, 1.0])
        Cov_param = J @ Cov_theta @ J.T
        diag_p = np.maximum(np.diag(Cov_param), 0.0)
        stderr_param = np.sqrt(diag_p)
        denom = np.outer(stderr_param, stderr_param)
        with np.errstate(divide="ignore", invalid="ignore"):
            corr_param = np.where(denom > 0, Cov_param / denom, np.nan)
        n = corr_param.shape[0]
        off = np.abs(corr_param.copy())
        for i in range(n):
            off[i, i] = 0.0
        max_off = (
            float(np.nanmax(off)) if np.any(np.isfinite(off)) else float("nan")
        )
    except Exception:
        stderr_param = np.full(5, np.nan)
        corr_param = np.full((5, 5), np.nan)
        max_off = float("nan")

    rmse = float(np.sqrt(sse / max(n_obs_fit, 1)))
    x_core_normalised = x_core_hat / float(loaf_thickness_m)

    return {
        "x_core_m": x_core_hat,
        "x_core_normalised": x_core_normalised,
        "Lu": Lu_hat,
        "Ko": Ko_hat,
        "Bi": Bi_hat,
        "T_oven_eff_K": T_oven_hat,
        "x_core_m_se": float(stderr_param[0]),
        "Lu_se": float(stderr_param[1]),
        "Ko_se": float(stderr_param[2]),
        "Bi_se": float(stderr_param[3]),
        "T_oven_eff_K_se": float(stderr_param[4]),
        "full_correlation_matrix": corr_param.tolist(),
        "max_abs_off_diag_correlation": max_off,
        "sse": sse,
        "rmse_per_sensor": rmse,
        "n_obs": n_obs_fit,
        "n_obs_total": n_obs_total,
        "startup_skip_frac": float(startup_skip_frac),
        "n_skip": int(n_skip),
        "converged": bool(opt.success),
        "n_iter": int(opt.nit) if hasattr(opt, "nit") else 0,
        "T_initial_K": T_initial_K,
        "loaf_thickness_m": float(loaf_thickness_m),
        "alpha_m2_s": float(alpha_m2_s),
        "epsilon": float(epsilon),
        "u_initial": float(u_initial),
        "Pn": float(Pn),
        "n_spatial": int(n_spatial),
        "x_surface_normalised": float(x_surface_normalised),
        "in_dough": list(in_dough_sensors),
        "sensor_positions_normalised": list(sensor_positions_normalised),
        "param_names": ["x_core_m", "Lu", "Ko", "Bi", "T_oven_eff_K"],
    }
