"""HMS Bellona — M11 Zürcher (2014) two-state thermodynamic bread-baking model.

Implements the 3-coupled-ODE forward model from
*U. Zürcher, "Thermodynamics of bread baking: A two-state model",*
Am. J. Phys. 82, 224 (2014). The state variables are the crust surface
temperature ``T_out``, the centre temperature ``T_in``, and the front
position ``n`` separating the "done" (baked) phase from the "undone"
(dough) phase.

Why this model when M9's 1D Stefan inverse failed:

* M9 used a Dirichlet BC pinned to a single sensor's measured temperature;
  on lidded bakes that BC is near-constant (cavity caps at 100 °C) and the
  inverse problem becomes information-free — α grew to 10⁸ on
  ``wonder_white``/``post_wonder_meal``.
* Zürcher uses a **radiative outer BC** with a single effective oven
  temperature ``T_oven_eff`` as a free parameter. The crust surface
  temperature is part of the model state, not driven by an observed
  sensor — naturally accommodates lid suppression because the inverse
  fits to the *effective* environmental temperature.
* M9's joint fit had four numerically-coupled parameters in normalised
  position² / s units (no literature comparison possible). Zürcher's
  three parameters are physical: ``x_core`` (m), ``j_0`` (dimensionless
  excess water mass fraction, ~0.05), ``T_oven_eff`` (K). Literature
  priors and "is this physical?" sanity checks become meaningful.

Equations (Zürcher §III, eqs 4-6 in dimensional form):

.. math::

    \\frac{dT_{out}}{dt} = \\frac{1}{\\rho c\\, dx}\\left[
        \\sigma\\left(T_{oven}^4 - T_{out}^4\\right)
        - k\\,\\frac{T_{out} - T_c}{R - dx - n}
    \\right]                                                        \\tag{4}

    \\frac{dn}{dt} = -\\frac{k}{j_0 L \\rho}\\left[
        \\frac{T_{out} - T_c}{R - dx - n}
        - \\frac{T_c - T_{in}}{n - dx}
    \\right]                                                        \\tag{5}

    \\frac{dT_{in}}{dt} = \\frac{k}{\\rho c\\, dx}\\,
        \\frac{T_c - T_{in}}{n - dx}                                \\tag{6}

with ``T_c`` = 373 K (water boiling), ``L`` = 22.4×10⁵ J/kg (per the
order-of-magnitude estimate Zürcher uses on p. 226), ``k`` = 0.5 W/m·K,
``rho`` = 10³ kg/m³, ``c`` = 2×10³ J/kg·K, ``sigma`` = Stefan-Boltzmann.

The full spatial temperature profile is **piecewise linear** (Zürcher
Fig 3): linear from ``T_in`` at the centre to ``T_c`` at the front,
then linear from ``T_c`` at the front to ``T_out`` at the surface.

Free inverse parameters: ``x_core_m`` (metres from surface; can be
negative meaning past probe tip), ``j_0`` (dimensionless), ``T_oven_eff_K``
(Kelvin). All other constants are pinned to Zürcher's literature values.

Coordinate convention
---------------------

The user's CSVs use a normalised probe position ``x ∈ [0, 1]`` with
sensors at ``i/7``. For the Zürcher model we work in **physical metres
from the surface**, then convert back. We pin a representative
``loaf_thickness_m = 0.05`` so the radiative term has correct units
(unit conversion of ``k/(R - dx - n)`` requires SI lengths).

The Zürcher coordinate system places centre at ``x = 0``, surface at
``x = R``. Our normalised system places surface at ``x = 1``, with
sensor ``T1`` at ``x = 0``. We map a normalised position ``x_n`` to
physical centre-distance ``r = x_n · loaf_thickness_m`` (with
``R = loaf_thickness_m`` representing the half-loaf depth).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import minimize

# Re-use the M7/M9 helpers (DRY).
from .heat_equation import _build_observation_matrix, _numerical_hessian


# ---------------------------------------------------------------------------
# Physical constants (Zürcher 2014, §I and §II)
# ---------------------------------------------------------------------------

K_DOUGH = 0.5            # thermal conductivity, W/(m·K)
RHO_DOUGH = 1.0e3        # density, kg/m³
C_DOUGH = 2.0e3          # specific heat, J/(kg·K)
L_LATENT = 22.4e5        # latent heat of evaporation, J/kg (Zürcher's
                         # j_0·L estimate uses this — the prefactor 0.05/j_0
                         # in scaled eq 12 is consistent with this value).
SIGMA_SB = 5.670374419e-8  # Stefan-Boltzmann, W/(m²·K⁴)
T_C_K = 373.0            # crossover (water boiling) temperature, K
DX_DEFAULT_M = 1.0e-3    # spatial coarse-graining length, m (Zürcher §II)
EMISSIVITY = 1.0         # Zürcher assumes blackbody (eq 1)


# Default loaf "radius" (half-loaf thickness). Zürcher uses 0.1 m for a
# round loaf; sandwich-bread half-thickness is closer to 0.05 m.
LOAF_THICKNESS_M_DEFAULT = 0.05


# ---------------------------------------------------------------------------
# Forward solver
# ---------------------------------------------------------------------------


@dataclass
class ZurcherForward:
    """Output of :func:`solve_zurcher_forward`."""

    T_out_t: np.ndarray        # crust surface temperature vs time, K
    T_in_t: np.ndarray         # centre temperature vs time, K
    n_t: np.ndarray            # front position vs time, m (from centre)
    t_grid_s: np.ndarray       # time grid actually returned, s
    T_predicted_K: np.ndarray  # piecewise-linear T(x_sample, t), shape (n_t, n_x)
    converged: bool
    bake_complete_at_s: Optional[float]  # time when n hit dx, or None

    def asdict(self) -> dict:
        return {
            "T_out_t": self.T_out_t,
            "T_in_t": self.T_in_t,
            "n_t": self.n_t,
            "t_grid_s": self.t_grid_s,
            "T_predicted_K": self.T_predicted_K,
            "converged": self.converged,
            "bake_complete_at_s": self.bake_complete_at_s,
        }


def _piecewise_linear_T(
    r: np.ndarray,
    T_in: float,
    T_out: float,
    n_front: float,
    R: float,
    dx: float,
    T_c: float = T_C_K,
) -> np.ndarray:
    """Evaluate Zürcher's piecewise-linear T(r) profile (Fig 3).

    Parameters
    ----------
    r : (n_x,) array_like
        Radii (metres from centre) at which to evaluate T.
    T_in, T_out : float
        Centre and crust temperatures (K).
    n_front : float
        Front position (m from centre). For r < n: dough side
        (linear T_in → T_c). For r > n: bread side (linear T_c → T_out).
    R, dx : float
        Loaf radius and coarse-graining length (m).
    T_c : float
        Crossover temperature.
    """
    r = np.asarray(r, dtype=float)
    out = np.empty_like(r)

    # Inner cell: r ∈ [0, dx] holds T_in by Zürcher's coarse-graining.
    inner = r <= dx
    out[inner] = T_in

    # Outer cell: r ∈ [R - dx, R] holds T_out.
    outer = r >= (R - dx)
    out[outer] = T_out

    # Dough side: dx < r < n  → linear T_in → T_c.
    dough = (~inner) & (r < n_front)
    if np.any(dough):
        denom = max(n_front - dx, 1e-12)
        frac = (r[dough] - dx) / denom
        out[dough] = T_in + frac * (T_c - T_in)

    # Bread side: n < r < R - dx  → linear T_c → T_out.
    bread = (~outer) & (r > n_front) & (r >= dx)
    if np.any(bread):
        denom = max(R - dx - n_front, 1e-12)
        frac = (r[bread] - n_front) / denom
        out[bread] = T_c + frac * (T_out - T_c)

    # At r == n exactly, both bread and dough miss — fix with T_c.
    on_front = (r == n_front) & (~inner) & (~outer)
    if np.any(on_front):
        out[on_front] = T_c

    return out


def solve_zurcher_forward(
    x_core_m: float,
    j_0: float,
    T_oven_eff_K: float,
    t_grid_s: np.ndarray,
    T_initial_K: float = 295.0,
    T_in_initial_K: Optional[float] = None,
    T_out_initial_K: Optional[float] = None,
    loaf_thickness_m: float = LOAF_THICKNESS_M_DEFAULT,
    R_m: Optional[float] = None,
    dx_m: float = DX_DEFAULT_M,
    n_init_frac: float = 0.99,
    sample_x_normalised: Optional[np.ndarray] = None,
    sample_x_m: Optional[np.ndarray] = None,
    physical_constants: Optional[dict] = None,
    rtol: float = 1e-6,
    atol: float = 1e-3,
    method: str = "LSODA",
    floor_factor: float = 0.5,
) -> ZurcherForward:
    """Solve Zürcher's three-ODE system on ``t_grid_s``.

    Parameters
    ----------
    x_core_m : float
        Core position **in metres from the loaf surface** (positive going
        inward, matches the user's ``x_core_normalised`` after scaling).
        Used only for converting normalised sample positions to physical
        radii; if you pass ``sample_x_m`` directly this is informational.
    j_0 : float
        Excess-water mass fraction (dimensionless). Zürcher's typical
        range: 0.005-0.05.
    T_oven_eff_K : float
        Effective environmental (oven) temperature. Free parameter.
    t_grid_s : array_like
        Times (seconds) at which to return the state.
    T_initial_K : float
        Initial centre temperature (Zürcher: room temp 293-295 K).
    T_in_initial_K, T_out_initial_K : float, optional
        Override individual initial temperatures. Zürcher's IC: T_out(0)=T_c,
        T_in(0)=room temp.
    loaf_thickness_m : float
        Half-loaf physical thickness, sets ``R``. Pinned per fixture (the
        user's CSVs lack metadata).
    R_m : float, optional
        Override loaf radius. Defaults to ``loaf_thickness_m``.
    dx_m : float
        Coarse-graining length (Zürcher: 1 mm).
    n_init_frac : float
        Initial front position as fraction of R (Zürcher's eq init: 0.98-0.99).
    sample_x_normalised : (n_x,) array_like, optional
        Normalised sensor positions (∈ [0, 1]; 0 = T1 deepest, 1 = surface).
        Each is converted via ``r = (1 - x_n) · R + x_n · 0`` — wait, no:
        we need to map probe coordinates to centre-distance. The convention
        is **surface at r = R**, so sensor at normalised position x_n
        (where x_n = 1 is the surface) sits at ``r = x_n · R``. Sensor T1
        at x_n = 0 is at the centre (r = 0).
    sample_x_m : (n_x,) array_like, optional
        Direct override (metres from centre). Used by the residual
        decomposition tests.
    physical_constants : dict, optional
        Override ``k``, ``rho``, ``c``, ``L``, ``sigma``. Defaults to
        Zürcher's values.
    rtol, atol : float
        Integrator tolerances. Defaults are tight because the radiative
        term scales with T⁴ and gives fast initial growth.
    method : str
        ``solve_ivp`` method. ``"LSODA"`` handles the stiff regime when n
        approaches the boundaries; ``"RK45"`` is fine for synthetic tests.
    floor_factor : float
        Multiplier of ``dx`` used as a floor for the denominators
        ``(R - dx - n)`` and ``(n - dx)`` to prevent blow-up near the
        boundaries. ``0.5`` is conservative.
    """
    pc = physical_constants or {}
    k = float(pc.get("k", K_DOUGH))
    rho = float(pc.get("rho", RHO_DOUGH))
    c = float(pc.get("c", C_DOUGH))
    L = float(pc.get("L", L_LATENT))
    sigma = float(pc.get("sigma", SIGMA_SB))
    T_c = float(pc.get("T_c", T_C_K))
    eps = float(pc.get("emissivity", EMISSIVITY))

    R = float(R_m) if R_m is not None else float(loaf_thickness_m)
    dx = float(dx_m)
    if R <= 2.0 * dx:
        raise ValueError(f"R={R} too small for dx={dx}; need R > 2*dx")

    # Initial conditions — Zürcher's defaults.
    if T_in_initial_K is None:
        T_in0 = float(T_initial_K)
    else:
        T_in0 = float(T_in_initial_K)
    if T_out_initial_K is None:
        T_out0 = float(T_c)
    else:
        T_out0 = float(T_out_initial_K)
    n0 = float(n_init_frac) * R
    # Clamp n0 just inside (dx, R-dx) — the boundary is reached when
    # n_init_frac == 0.99 and R == 0.1, dx == 1e-3 (R-dx = 0.099 = n0
    # exactly). Slightly inside is fine.
    if n0 >= R - dx:
        n0 = R - 2.0 * dx
    if n0 <= dx:
        n0 = 2.0 * dx
    if not (dx < n0 < R - dx):
        raise ValueError(
            f"Initial front n0={n0:.4f} outside (dx={dx:.4f}, R-dx={R-dx:.4f})"
        )

    floor = floor_factor * dx
    j_0_safe = max(float(j_0), 1e-6)

    def rhs(t: float, y: np.ndarray) -> np.ndarray:
        T_out, T_in, n = y
        # Apply non-negative floor to denominators to prevent runaway near
        # the boundaries. The model is undefined outside (dx, R-dx); the
        # event handler stops integration when n hits dx.
        denom_outer = max(R - dx - n, floor)
        denom_inner = max(n - dx, floor)
        # Crust energy balance (eq 4)
        net_rad = sigma * eps * (T_oven_eff_K ** 4 - T_out ** 4)
        cond_outer = k * (T_out - T_c) / denom_outer
        dT_out_dt = (net_rad - cond_outer) / (rho * c * dx)
        # Front velocity (eq 5) — sign: front advances inward (n decreases).
        cond_inner = k * (T_c - T_in) / denom_inner
        dn_dt = -(1.0 / (j_0_safe * L * rho)) * (cond_outer - cond_inner)
        # Centre energy balance (eq 6)
        dT_in_dt = cond_inner / (rho * c * dx)
        return np.array([dT_out_dt, dT_in_dt, dn_dt])

    # Stop integration when front reaches dx (bake done).
    def front_event(t: float, y: np.ndarray) -> float:
        return y[2] - dx

    front_event.terminal = True
    front_event.direction = -1.0

    t_grid = np.asarray(t_grid_s, dtype=float)
    if t_grid.size < 2:
        raise ValueError("t_grid_s must have at least 2 samples")
    t_span = (float(t_grid[0]), float(t_grid[-1]))
    y0 = np.array([T_out0, T_in0, n0], dtype=float)

    sol = solve_ivp(
        rhs,
        t_span,
        y0,
        t_eval=t_grid,
        method=method,
        rtol=rtol,
        atol=atol,
        events=front_event,
    )

    converged = bool(sol.success)
    bake_complete_at_s: Optional[float] = None
    if sol.t_events is not None and len(sol.t_events) > 0 and len(sol.t_events[0]) > 0:
        bake_complete_at_s = float(sol.t_events[0][0])

    # If integration stopped early because the front reached dx, extend
    # the state past the event by holding final values constant — the bake
    # is "done", T_out continues to follow the radiative balance with n=dx
    # (degenerate; we just clamp).
    T_out_t = np.full(t_grid.size, T_out0, dtype=float)
    T_in_t = np.full(t_grid.size, T_in0, dtype=float)
    n_t = np.full(t_grid.size, n0, dtype=float)
    n_used = sol.y.shape[1]
    T_out_t[:n_used] = sol.y[0, :]
    T_in_t[:n_used] = sol.y[1, :]
    n_t[:n_used] = sol.y[2, :]
    if n_used < t_grid.size:
        T_out_t[n_used:] = sol.y[0, -1]
        T_in_t[n_used:] = sol.y[1, -1]
        n_t[n_used:] = sol.y[2, -1]

    # Sample-position predictions (piecewise-linear).
    if sample_x_m is None and sample_x_normalised is not None:
        x_n = np.asarray(sample_x_normalised, dtype=float)
        # Probe convention: x_n = 0 is T1 (deepest into loaf) — the user's
        # mapping puts T1 toward the *centre*, T8 at the surface. So r = x_n · R.
        sample_x_m = x_n * R
    if sample_x_m is None:
        T_predicted = np.zeros((t_grid.size, 0))
    else:
        sample_x_m_arr = np.asarray(sample_x_m, dtype=float)
        T_predicted = np.empty((t_grid.size, sample_x_m_arr.size), dtype=float)
        for i in range(t_grid.size):
            T_predicted[i, :] = _piecewise_linear_T(
                r=sample_x_m_arr,
                T_in=T_in_t[i],
                T_out=T_out_t[i],
                n_front=n_t[i],
                R=R,
                dx=dx,
                T_c=T_c,
            )

    return ZurcherForward(
        T_out_t=T_out_t,
        T_in_t=T_in_t,
        n_t=n_t,
        t_grid_s=t_grid,
        T_predicted_K=T_predicted,
        converged=converged,
        bake_complete_at_s=bake_complete_at_s,
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

    The user's normalised x runs along the probe with ``x_n = 0`` at T1
    (deepest into the loaf) and ``x_n = 1`` at T8 (deepest into the air).
    The classifier identifies a continuous ``x_surface_normalised`` where
    the dough/air interface lies; sensors with ``x_n < x_surface_norm``
    are in-dough.

    We fix the surface at physical centre-distance ``r = R``, and place
    T1 at ``r = x_core_m`` (a free inverse parameter — when negative,
    means the inferred loaf centre is past the probe tip). Linear
    interpolation between gives sensor i at::

        r_i = x_core_m + (x_n_i / x_surface_norm) * (R - x_core_m)

    so r_i = x_core_m at x_n=0 (T1) and r_i = R at x_n = x_surface_norm.
    """
    x_n = np.asarray(x_normalised, dtype=float)
    x_core = float(x_core_m)
    x_surf = float(x_surface_normalised)
    R = float(loaf_thickness_m)
    if x_surf <= 0:
        raise ValueError(f"x_surface_normalised must be > 0, got {x_surf}")
    return x_core + (x_n / x_surf) * (R - x_core)


def fit_zurcher_inverse(
    df: pd.DataFrame,
    in_dough_sensors: list[str],
    x_surface_normalised: float,
    sensor_positions_normalised: tuple = SENSOR_POSITIONS_DEFAULT,
    sensor_names: tuple = SENSOR_NAMES_DEFAULT,
    init: Optional[dict] = None,
    sample_period_s: float = 5.0,
    downsample_factor: int = 4,
    loaf_thickness_m: float = LOAF_THICKNESS_M_DEFAULT,
    dx_m: float = DX_DEFAULT_M,
    n_init_frac: float = 0.99,
    bounds: Optional[dict] = None,
    max_iter: int = 400,
    rtol: float = 1e-6,
    atol: float = 1e-3,
    method: str = "LSODA",
    startup_skip_frac: float = 0.20,
) -> dict:
    """Three-parameter Nelder-Mead fit of the Zürcher model.

    Free parameters
    ---------------
    * ``x_core_m`` — core position in metres from the surface. Negative
      means the inferred core is past the deepest sensor (T1 at r=0). The
      result is converted back to normalised probe coords via
      ``x_core_normalised = x_core_m / loaf_thickness_m`` for direct
      comparison with M7/M9 numbers.
    * ``j_0`` — excess-water mass fraction (dimensionless).
    * ``T_oven_eff_K`` — effective oven temperature.

    Returns
    -------
    dict with keys::

        x_core_m, x_core_normalised,
        j_0, T_oven_eff_K,
        x_core_m_se, j_0_se, T_oven_eff_K_se,
        full_correlation_matrix,           # 3×3
        max_abs_off_diag_correlation,
        sse, rmse_per_sensor, n_obs,
        converged, n_iter, T_initial_K,
        loaf_thickness_m, dx_m, in_dough.
    """
    init = init or {}
    bounds = bounds or {}
    # Defaults: x_core_m is the physical centre-distance of T1.
    # Negative ⇒ inferred loaf centre is past T1 (probe didn't reach
    # centre); positive ⇒ T1 is interior to the loaf centre (unusual).
    x_core_m_init = float(init.get("x_core_m", -0.005))
    j_0_init = float(init.get("j_0", 0.05))
    T_oven_init = float(init.get("T_oven_eff_K", 450.0))
    x_core_lo, x_core_hi = bounds.get("x_core_m", (-0.04, 0.04))
    j_0_lo, j_0_hi = bounds.get("j_0", (0.005, 0.20))
    T_oven_lo, T_oven_hi = bounds.get("T_oven_eff_K", (350.0, 600.0))

    t_obs, T_obs_C, x_obs_n = _build_observation_matrix(
        df=df,
        in_dough_sensors=in_dough_sensors,
        sensor_names=sensor_names,
        sensor_positions_normalised=sensor_positions_normalised,
        downsample_factor=downsample_factor,
    )
    # Convert °C observations → K. The model speaks Kelvin (T_c=373, T⁴).
    T_obs_K = T_obs_C + 273.15

    # Initial centre temperature: average across deepest sensor's first sample
    # — but most reliably, average the first row across in-dough sensors and
    # convert to K (matches M9's pattern).
    T_initial_K = float(np.mean(T_obs_K[0, :]))

    # Startup skip: Zürcher's piecewise-linear profile assumes the dough has
    # already developed a quasi-steady temperature gradient. Real bread starts
    # uniformly cold; the first ~20% of samples show large mismatch. We
    # compute the loss only over the warmup-excluded window, but the forward
    # solver still runs from t=0 (so the integration starts from the right
    # initial state).
    n_t_total = len(t_obs)
    n_skip = max(int(startup_skip_frac * n_t_total), 0)
    if n_skip >= n_t_total - 5:
        n_skip = max(n_t_total // 4, 0)

    # Optimise in unconstrained reals via squashing transforms:
    #   x_core_m: linear (we'll just clamp inside _loss)
    #   j_0: log
    #   T_oven_eff_K: linear
    # Bounds enforced via penalty (Nelder-Mead has no native bounds).
    def _theta_to_params(theta: np.ndarray) -> tuple[float, float, float]:
        x_core = float(theta[0])
        j0 = float(np.exp(theta[1]))
        T_oven = float(theta[2])
        return x_core, j0, T_oven

    def _bounds_penalty(x_core: float, j0: float, T_oven: float) -> float:
        if not (x_core_lo <= x_core <= x_core_hi):
            return 1e10
        if not (j_0_lo <= j0 <= j_0_hi):
            return 1e10
        if not (T_oven_lo <= T_oven <= T_oven_hi):
            return 1e10
        return 0.0

    def _loss(theta: np.ndarray) -> float:
        x_core, j0, T_oven = _theta_to_params(theta)
        pen = _bounds_penalty(x_core, j0, T_oven)
        if pen > 0:
            return pen
        # Map normalised sensor positions to physical centre-distance via
        # the current x_core_m. This is what makes x_core_m a real free
        # parameter (vs M7/M9 where it shifts the spatial domain). With
        # sample_x_m derived from x_core_m, shifting x_core_m moves all
        # the in-dough sensors radially.
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
            fwd = solve_zurcher_forward(
                x_core_m=x_core,
                j_0=j0,
                T_oven_eff_K=T_oven,
                t_grid_s=t_obs,
                T_initial_K=T_initial_K,
                T_in_initial_K=T_initial_K,
                # Start crust at room temp like the data, NOT Zürcher's
                # idealised T_c IC. The piecewise-linear assumption then
                # only holds after the warmup-skip window.
                T_out_initial_K=T_initial_K,
                loaf_thickness_m=loaf_thickness_m,
                dx_m=dx_m,
                n_init_frac=n_init_frac,
                sample_x_m=sample_x_m,
                rtol=rtol,
                atol=atol,
                method=method,
            )
        except Exception:
            return 1e10
        if not fwd.converged:
            return 1e10
        # Loss computed only on the warmup-excluded window.
        diff = (fwd.T_predicted_K[n_skip:] - T_obs_K[n_skip:]).ravel()
        if not np.all(np.isfinite(diff)):
            return 1e10
        return float(np.sum(diff * diff))

    theta0 = np.array(
        [
            x_core_m_init,
            float(np.log(max(j_0_init, 1e-4))),
            T_oven_init,
        ],
        dtype=float,
    )
    opt = minimize(
        _loss,
        theta0,
        method="Nelder-Mead",
        options={
            "xatol": 1e-5,
            "fatol": 1e-2,
            "maxiter": max_iter,
            "adaptive": True,
        },
    )

    x_core_hat, j0_hat, T_oven_hat = _theta_to_params(opt.x)
    sse = float(opt.fun)
    n_obs_fit = int(T_obs_K[n_skip:].size)
    n_obs_total = int(T_obs_K.size)

    # 3×3 Hessian → covariance → correlation. Steps tuned per parameter.
    try:
        H_sse = _numerical_hessian(
            _loss, opt.x, h=[1e-3, 1e-2, 1e-2]
        )
        p_params = 3
        dof = max(n_obs_fit - p_params, 1)
        sigma2 = sse / dof
        cov_inflate = 1.4 ** 2  # match M7/M9 calibration
        Cov_theta = 2.0 * sigma2 * cov_inflate * np.linalg.pinv(H_sse)
        # Delta method: theta = (x_core, log j0, T_oven); param = (x_core, j0, T_oven).
        J = np.diag([1.0, j0_hat, 1.0])
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
        stderr_param = np.full(3, np.nan)
        corr_param = np.full((3, 3), np.nan)
        max_off = float("nan")

    rmse = float(np.sqrt(sse / max(n_obs_fit, 1)))
    x_core_normalised = x_core_hat / float(loaf_thickness_m)

    return {
        "x_core_m": x_core_hat,
        "x_core_normalised": x_core_normalised,
        "j_0": j0_hat,
        "T_oven_eff_K": T_oven_hat,
        "x_core_m_se": float(stderr_param[0]),
        "j_0_se": float(stderr_param[1]),
        "T_oven_eff_K_se": float(stderr_param[2]),
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
        "dx_m": float(dx_m),
        "x_surface_normalised": float(x_surface_normalised),
        "in_dough": list(in_dough_sensors),
        "sensor_positions_normalised": list(sensor_positions_normalised),
    }
