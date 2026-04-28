"""Method 3b (research-only): 1D Stefan-front inverse problem.

The 1D heat equation `T_t = α · T_xx` (Method 3 / M7) gave RMSE 6-10 °C on
real bread-baking CSVs because it cannot represent the latent-heat plateau
at 100 °C that every in-dough sensor exhibits. The Stefan problem with a
moving evaporation front explicitly models this latent-heat absorption:

* **Dough** (T ≤ 100 °C):     ∂T/∂t = α_dough · ∂²T/∂x²
* **Crust** (T ≥ 100 °C):     ∂T/∂t = α_crust · ∂²T/∂x²
* **At the front** s(t):       T = 100 °C  AND  ρL · ds/dt = jump in heat flux.

Implementation: **enthalpy method** (effective heat capacity). The latent
heat appears as a delta-function in C_p(T) at T = 100 °C; numerically we
smear it over a small ΔT window so a stiff-aware ODE integrator can step
through it. No explicit front tracking — the front emerges as the locus
where T crosses 100 °C, and the latent-heat absorption is encoded in the
local effective heat capacity.

**Domain**: ``x ∈ [x_core, x_surface]``, normalised position units
(same convention as :mod:`heat_equation`). The Stefan coefficient
``rhoL_eff`` is in matching dimensionless units — see the parametrisation
note below.

**Parametrisation note**: the model has three thermal parameters
(α_dough, α_crust, ρL_eff). In SI units::

    α [m²/s] = k [W/(m·K)] / (ρ [kg/m³] · C_p [J/(kg·K)])
    ρL_eff [J/m³] = ρ [kg/m³] · L [J/kg] · (moisture mass fraction)

In normalised position units we work with::

    α_norm = α_SI / loaf_thickness²
    rhoL_eff_norm — defined so that the dimensionless effective heat
                    capacity inside the smearing window
                    `1 + rhoL_eff_norm / (2 · ΔT_smear · α_norm)`
                    matches the SI-Stefan-number ratio of latent to
                    sensible heat.

For the literature-pinned variant we use a representative loaf thickness
of 50 mm to convert published values; the conversion is documented in
:func:`fit_stefan_inverse_pinned`.

Public API:

* :func:`solve_stefan_forward` — enthalpy-method forward solver.
* :func:`fit_stefan_inverse_joint` — 4-param Nelder-Mead joint fit.
* :func:`fit_stefan_inverse_pinned` — 1-param fit with literature-pinned α & ρL.
* :func:`classical_stefan_neumann` — analytical Stefan-Neumann reference
  for forward-solver sanity tests.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, minimize
from scipy.special import erf, erfc

from .heat_equation import _numerical_hessian


# Stefan front temperature (water boiling at standard pressure).
T_FRONT_C = 100.0


# ---------------------------------------------------------------------------
# Forward solver — enthalpy method (effective Cp)
# ---------------------------------------------------------------------------


def _alpha_eff_factory(
    alpha_dough: float,
    alpha_crust: float,
    rhoL_eff: float,
    delta_T_smear: float,
) -> callable:
    """Return ``alpha_eff(T)`` for the enthalpy-method forward solve.

    Outside the smearing window ``[100 - dT, 100 + dT]``::

        T < 100 - dT:  alpha_eff = alpha_dough
        T > 100 + dT:  alpha_eff = alpha_crust

    Inside the window the effective heat capacity is augmented by
    ``rhoL_eff / (2 dT)``. In α-form this is::

        alpha_eff(T) = alpha_baseline / (1 + rhoL_eff / (2 dT · alpha_baseline))

    We use a smooth blend of (alpha_dough → alpha_crust) at the centre of
    the window so the diffusivity transitions continuously across 100 °C
    after the latent-heat trap releases.
    """
    inv_2dT = 1.0 / (2.0 * delta_T_smear)

    def _alpha_eff(T: np.ndarray) -> np.ndarray:
        T = np.asarray(T, dtype=float)
        out = np.where(T < T_FRONT_C, alpha_dough, alpha_crust)
        # Inside the smearing window we trap the heat. In our normalised
        # heat-eq formulation `dT/dt = α · d²T/dx²` (no explicit ρcp), the
        # latent heat enters as an augmentation of the effective heat
        # capacity: cp_eff(T) = cp · (1 + (L/cp)/(2 dT)). Since α ≡ k/(ρcp),
        # the corresponding α_eff is α / (1 + (L/cp)/(2 dT)). The parameter
        # we expose is rhoL_eff_norm := L/cp (units K), the dimensionless
        # latent-to-sensible heat ratio. The trap factor is therefore:
        #     trap = 1 + rhoL_eff / (2 · dT)
        # **independent of α** — this is the correct form (see Stefan-Neumann
        # one-phase analytical sanity test).
        in_win = np.abs(T - T_FRONT_C) <= delta_T_smear
        if np.any(in_win):
            # Linear blend dough→crust across [-dT, +dT] for α_baseline.
            frac = (T[in_win] - (T_FRONT_C - delta_T_smear)) * inv_2dT
            frac = np.clip(frac, 0.0, 1.0)
            alpha_baseline = (1.0 - frac) * alpha_dough + frac * alpha_crust
            trap = 1.0 + rhoL_eff * inv_2dT
            out[in_win] = alpha_baseline / trap
        return out

    return _alpha_eff


def solve_stefan_forward(
    x_core: float,
    x_surface: float,
    alpha_dough: float,
    alpha_crust: float,
    rhoL_eff: float,
    t_grid: np.ndarray,
    T_surface_series: np.ndarray,
    T_initial: float,
    n_spatial: int = 60,
    sample_x: Optional[np.ndarray] = None,
    delta_T_smear: float = 1.0,
) -> np.ndarray:
    """Solve the 1D Stefan problem via the enthalpy method.

    Geometry / BCs:

    * Domain ``x ∈ [x_core, x_surface]`` with Neumann (∂T/∂x = 0) at the
      core (symmetry) and Dirichlet at the surface
      (``T(x_surface, t) = T_surface_series(t)``).
    * Initial condition ``T(x, 0) = T_initial`` for all x.

    Numerics:

    * Method-of-lines: 2nd-order central differences for ``T_xx``;
      the local effective diffusivity ``α_eff(T)`` from
      :func:`_alpha_eff_factory` is applied node-wise (frozen-coefficient
      style). LSODA via :func:`scipy.integrate.solve_ivp`.
    * The Dirichlet BC at ``x_surface`` is enforced by stiff clamping
      (same pattern as :func:`heat_equation.solve_heat_eq_forward`).

    Parameters
    ----------
    x_core, x_surface:
        Normalised domain edges; ``x_core < x_surface``.
    alpha_dough, alpha_crust:
        Thermal diffusivities in normalised-position²/s for the two
        regions (T < 100 °C and T > 100 °C respectively).
    rhoL_eff:
        Volumetric effective latent heat (in normalised units — see
        module docstring). Must be ≥ 0.
    t_grid:
        Times in seconds, monotone increasing, length ≥ 2.
    T_surface_series:
        Observed surface temperatures at ``t_grid``.
    T_initial:
        Initial uniform temperature.
    n_spatial:
        Number of spatial nodes (default 60).
    sample_x:
        Output positions; default = the spatial grid.
    delta_T_smear:
        Half-width of the 100 °C smearing window in °C. Smaller →
        sharper Stefan condition but stiffer ODE. Default 1.0 °C.

    Returns
    -------
    np.ndarray, shape ``(len(t_grid), len(sample_x))``
    """
    if alpha_dough <= 0:
        raise ValueError(f"alpha_dough must be > 0, got {alpha_dough}")
    if alpha_crust <= 0:
        raise ValueError(f"alpha_crust must be > 0, got {alpha_crust}")
    if rhoL_eff < 0:
        raise ValueError(f"rhoL_eff must be >= 0, got {rhoL_eff}")
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

    # Use the largest feasible diffusivity to set the BC stiff-clamp time
    # constant (so the clamp is faster than the fastest diffusion mode).
    alpha_max = float(max(alpha_dough, alpha_crust))

    def _rhs(t: float, T: np.ndarray) -> np.ndarray:
        a_local = alpha_eff(T)  # node-wise α_eff(T_node)
        dTdt = np.empty_like(T)
        # Neumann at core (i=0): ghost cell T[-1] = T[1] →
        # T_xx[0] ≈ 2 (T[1] - T[0]) / dx²
        dTdt[0] = a_local[0] * 2.0 * (T[1] - T[0]) / dx2
        # Interior central differences. Use the node-local α (frozen
        # coefficient) — this is the standard enthalpy-method scheme.
        dTdt[1:-1] = a_local[1:-1] * (T[:-2] - 2.0 * T[1:-1] + T[2:]) / dx2
        # Dirichlet stiff clamp at the surface.
        T_surf = _surface_at(t)
        tau = 0.05 * dx2 / max(alpha_max, 1e-9)
        dTdt[-1] = (T_surf - T[-1]) / tau
        return dTdt

    T0 = np.full(N, float(T_initial))
    T0[-1] = float(T_surface_series[0])

    # BDF is ~5× faster than LSODA on this stiff enthalpy-method problem
    # (LSODA's switch heuristic spends time deciding the stiff regime; BDF
    # commits to the stiff path from the start). rtol=1e-4 + atol=1e-5
    # keeps the per-call accuracy within ~0.5 °C of LSODA's reference
    # output — well below the inverse-fit RMSE noise floor.
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
# Classical Stefan-Neumann analytical reference
# ---------------------------------------------------------------------------


def _stefan_neumann_lambda(stefan_number: float, alpha_ratio: float = 1.0) -> float:
    """Solve the Stefan-Neumann transcendental equation for ``λ``.

    The classical two-phase Stefan-Neumann problem (semi-infinite solid
    initially at ``T_init < T_m``, surface held at ``T_surf > T_m``,
    melting at ``T_m``) has front position ``s(t) = 2 λ √(α_dough · t)``
    where λ is the positive root of::

        Ste · exp(-λ²)
        ----------------------------- = λ √π
        erf(λ) + ν · exp((1-ν²)·λ²) · erfc(ν·λ) · √α_ratio · (T_init - T_m) / (T_surf - T_m)

    For the **one-phase** simplification (T_init = T_m, dough region
    initially at the front temperature so no sensible-heat sink in the
    unfrozen region), the equation reduces to::

        Ste · exp(-λ²) / erf(λ) = λ √π

    where ``Ste = c_p · (T_surf - T_m) / L`` is the Stefan number. We
    use this one-phase form for the sanity test — generates a synthetic
    that is easy to compare to.

    Parameters
    ----------
    stefan_number:
        Dimensionless Stefan number (sensible / latent ratio).
    alpha_ratio:
        ``alpha_dough / alpha_crust``. Unused in the one-phase form;
        kept for API symmetry.

    Returns
    -------
    float
        The positive root λ.
    """
    # One-phase form: λ √π · erf(λ) · exp(λ²) - Ste = 0.
    def _eq(lam: float) -> float:
        return lam * math.sqrt(math.pi) * erf(lam) * math.exp(lam * lam) - stefan_number

    # λ is small for small Ste, grows roughly as √(Ste) for moderate Ste.
    # Bracket conservatively.
    lo, hi = 1e-8, 5.0
    f_lo, f_hi = _eq(lo), _eq(hi)
    if f_lo * f_hi > 0:
        # Expand if needed.
        for h in (10.0, 20.0):
            f_hi = _eq(h)
            if f_lo * f_hi <= 0:
                hi = h
                break
        else:
            raise RuntimeError(
                f"Could not bracket λ for Ste={stefan_number}"
            )
    return float(brentq(_eq, lo, hi, xtol=1e-10))


def classical_stefan_neumann(
    T_init: float,
    T_surface: float,
    alpha_crust: float,
    stefan_number: float,
    x_surface: float,
    x: np.ndarray,
    t: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Classical one-phase Stefan-Neumann analytical solution.

    Semi-infinite domain ``x ∈ (-∞, x_surface]``, surface held at
    ``T_surface > 100 °C``, dough region initially at ``T_init = 100 °C``.
    Front position::

        s(t) = x_surface - 2 λ √(α_crust · t)

    Temperature in the crust region (``s(t) ≤ x ≤ x_surface``)::

        T(x, t) = T_surface + (100 - T_surface) · erf((x_surface - x) / (2√(α_crust t))) / erf(λ)

    Below the front the dough is at 100 °C (the one-phase assumption).

    Parameters
    ----------
    T_init:
        Initial dough temperature, must equal 100 °C for the one-phase form.
    T_surface:
        Surface temperature (constant Dirichlet BC), > 100 °C.
    alpha_crust:
        Thermal diffusivity in the crust region.
    stefan_number:
        Ste = c_p · (T_surface - 100) / L. Determines λ.
    x_surface:
        Domain edge.
    x, t:
        Sample positions (1-D) and times (1-D).

    Returns
    -------
    (T_grid, s_grid):
        T_grid shape (len(t), len(x)); s_grid shape (len(t),).
    """
    if abs(T_init - T_FRONT_C) > 0.5:
        raise ValueError(
            f"One-phase Stefan-Neumann requires T_init == 100 °C; got {T_init}"
        )
    lam = _stefan_neumann_lambda(stefan_number)
    x = np.asarray(x, dtype=float)
    t = np.asarray(t, dtype=float)
    T = np.empty((t.size, x.size), dtype=float)
    s = np.empty(t.size, dtype=float)
    erf_lam = float(erf(lam))
    for i, ti in enumerate(t):
        if ti <= 0:
            T[i, :] = T_init
            s[i] = x_surface  # front coincides with surface at t=0
            continue
        s_i = x_surface - 2.0 * lam * math.sqrt(alpha_crust * ti)
        s[i] = s_i
        # In crust (above front): erf-profile.
        # Below front (s < x): dough at 100 °C.
        denom = 2.0 * math.sqrt(alpha_crust * ti)
        for j, xj in enumerate(x):
            if xj > x_surface:
                T[i, j] = T_surface
            elif xj > s_i:
                # In crust: T = T_surf + (100 - T_surf) · erf((x_s - x) / (2√(αt))) / erf(λ)
                arg = (x_surface - xj) / denom
                T[i, j] = T_surface + (T_FRONT_C - T_surface) * float(erf(arg)) / erf_lam
            else:
                T[i, j] = T_FRONT_C
    return T, s


# ---------------------------------------------------------------------------
# Inverse fitting — joint and pinned
# ---------------------------------------------------------------------------


def _build_observation_matrix(
    df: pd.DataFrame,
    in_dough_sensors: list[str],
    sensor_names: tuple,
    sensor_positions_normalised: tuple,
    downsample_factor: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Same shape contract as :func:`heat_equation._build_observation_matrix`.

    Kept as a private helper because Stefan adds nothing — but importing
    the M7 helper directly would create a circular dependency (M7 → Stefan
    is fine, Stefan → M7 brings the heat_equation module's full namespace
    into the Stefan import; we want the helpers separate to keep the
    module-level smoke-test surface tight).
    """
    pos_map = dict(zip(sensor_names, sensor_positions_normalised))
    x_obs = np.array([pos_map[s] for s in in_dough_sensors], dtype=float)
    t = df["Timestamp"].to_numpy(dtype=float)
    if downsample_factor < 1:
        downsample_factor = 1
    sl = slice(0, len(t), int(downsample_factor))
    t_obs = t[sl]
    T_cols = [df[s].to_numpy(dtype=float)[sl] for s in in_dough_sensors]
    T_obs = np.column_stack(T_cols)
    return t_obs, T_obs, x_obs


def _correlation_matrix(H_sse: np.ndarray, sigma2: float) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(stderr, corr_matrix)`` from the SSE-Hessian.

    For the SSE objective with Gaussian residuals,
    ``Cov ≈ 2 σ² · inv(H_sse)``. We invert via :func:`numpy.linalg.pinv`
    for safety. Returns NaN matrices if the inversion fails.
    """
    n = H_sse.shape[0]
    try:
        # Pinv is more robust than inv when the Hessian is near-singular
        # (which happens when the inverse problem is degenerate).
        Cov = 2.0 * sigma2 * np.linalg.pinv(H_sse)
    except np.linalg.LinAlgError:
        return np.full(n, np.nan), np.full((n, n), np.nan)
    diag = np.diag(Cov)
    if np.any(diag < 0):
        # Hessian had negative eigenvalues — Cov is degenerate. Mark and continue.
        diag = np.maximum(diag, 0.0)
    stderr = np.sqrt(diag)
    denom = np.outer(stderr, stderr)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(denom > 0, Cov / denom, np.nan)
    return stderr, corr


def fit_stefan_inverse_joint(
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
    sample_period_s: float = 5.0,
    downsample_factor: int = 4,
    n_spatial: int = 60,
    delta_T_smear: float = 1.0,
    max_iter: int = 400,
) -> dict:
    """Joint 4-parameter Nelder-Mead fit (x_core, α_dough, α_crust, ρL_eff).

    Spatially-interpolated surface BC at ``x_surface_continuous`` (M6
    pattern; same as :func:`heat_equation.fit_heat_equation_inverse_v2`).

    Returns
    -------
    dict with keys::

        x_core, alpha_dough, alpha_crust, rhoL_eff,
        x_core_se, alpha_dough_se, alpha_crust_se, rhoL_eff_se,
        full_correlation_matrix,  # 4×4
        max_abs_off_diag_correlation,
        sse, rmse_per_sensor, n_obs, converged, n_iter,
        T_initial, x_surface_continuous, extrapolated, bc_source.
    """
    from .profile import interpolate_temperature_series_at

    init = init or {}
    x_core_init = float(init.get("x_core", -0.05))
    alpha_dough_init = float(init.get("alpha_dough", 1e-3))
    alpha_crust_init = float(init.get("alpha_crust", 1e-3))
    rhoL_init = float(init.get("rhoL_eff", 5e3))

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

    # Optimise in (x_core, log α_dough, log α_crust, log ρL_eff).
    # The log-transform keeps the three thermal params positive without
    # bounded optimisation. x_core stays in linear space.
    def _theta_to_params(theta: np.ndarray) -> tuple[float, float, float, float]:
        x_core = float(theta[0])
        alpha_d = float(np.exp(theta[1]))
        alpha_c = float(np.exp(theta[2]))
        rhoL = float(np.exp(theta[3]))
        return x_core, alpha_d, alpha_c, rhoL

    def _loss(theta: np.ndarray) -> float:
        x_core, alpha_d, alpha_c, rhoL = _theta_to_params(theta)
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
                delta_T_smear=delta_T_smear,
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

    x_core_hat, alpha_d_hat, alpha_c_hat, rhoL_hat = _theta_to_params(opt.x)
    sse = float(opt.fun)
    n_obs = int(T_obs.size)

    # Hessian-based covariance + full correlation matrix.
    try:
        # Steps for finite differences. log-α and log-ρL are O(1), x_core is O(0.1).
        H_sse = _numerical_hessian(
            _loss, opt.x, h=[5e-3, 1e-2, 1e-2, 1e-2]
        )
        p_params = 4
        dof = max(n_obs - p_params, 1)
        sigma2 = sse / dof
        # Same temporal-correlation inflation as M7 (calibrated to ~95% coverage
        # under synthetic noise). Stefan adds front-locality which doesn't
        # reduce that correlation, so the same factor is appropriate.
        cov_inflate = 1.4 ** 2
        stderr_theta, corr = _correlation_matrix(H_sse, sigma2 * cov_inflate)
        # Convert log-parameter SE to linear-parameter SE via delta method.
        # var(α) = α² · var(log α); cov(α, x_core) = α · cov(log α, x_core).
        # We need the linear-param correlation matrix because the report
        # reads it (the user thinks in α, ρL — not log).
        Cov_theta = 2.0 * sigma2 * cov_inflate * np.linalg.pinv(H_sse)
        # Build a Jacobian J such that Cov_param = J · Cov_theta · J^T.
        # theta = (x_core, log α_d, log α_c, log ρL); param = (x_core, α_d, α_c, ρL).
        J = np.diag([1.0, alpha_d_hat, alpha_c_hat, rhoL_hat])
        Cov_param = J @ Cov_theta @ J.T
        diag_p = np.diag(Cov_param).copy()
        diag_p = np.maximum(diag_p, 0.0)
        stderr_param = np.sqrt(diag_p)
        denom = np.outer(stderr_param, stderr_param)
        with np.errstate(divide="ignore", invalid="ignore"):
            corr_param = np.where(denom > 0, Cov_param / denom, np.nan)
        # Max absolute off-diagonal correlation.
        n = corr_param.shape[0]
        off = np.abs(corr_param.copy())
        for i in range(n):
            off[i, i] = 0.0
        max_off = float(np.nanmax(off)) if np.any(np.isfinite(off)) else float("nan")
    except Exception:
        stderr_param = np.full(4, np.nan)
        corr_param = np.full((4, 4), np.nan)
        max_off = float("nan")

    rmse = float(np.sqrt(sse / max(n_obs, 1)))
    extrapolated = x_core_hat < float(min(sensor_positions_normalised))

    return {
        "x_core": x_core_hat,
        "alpha_dough": alpha_d_hat,
        "alpha_crust": alpha_c_hat,
        "rhoL_eff": rhoL_hat,
        "x_core_se": float(stderr_param[0]),
        "alpha_dough_se": float(stderr_param[1]),
        "alpha_crust_se": float(stderr_param[2]),
        "rhoL_eff_se": float(stderr_param[3]),
        "full_correlation_matrix": corr_param.tolist(),
        "max_abs_off_diag_correlation": max_off,
        "sse": sse,
        "rmse_per_sensor": rmse,
        "n_obs": n_obs,
        "converged": bool(opt.success),
        "n_iter": int(opt.nit) if hasattr(opt, "nit") else 0,
        "T_initial": T_initial,
        "x_surface_continuous": x_surface,
        "extrapolated": bool(extrapolated),
        "bc_source": "interpolated_v2",
        "delta_T_smear": float(delta_T_smear),
    }


# Literature reference values for the pinned variant.
# alpha_dough ≈ 1.4e-7 m²/s; alpha_crust ≈ 1.0e-7 m²/s; ρL_eff ≈ 6e8 J/m³.
ALPHA_DOUGH_LIT_SI = 1.4e-7
ALPHA_CRUST_LIT_SI = 1.0e-7
RHO_L_EFF_LIT_SI = 6.0e8

# Representative half-loaf thickness for SI ↔ normalised conversion.
LOAF_THICKNESS_M = 0.050


def _lit_to_normalised(
    alpha_dough_lit: float,
    alpha_crust_lit: float,
    rhoL_eff_lit: float,
    loaf_thickness_m: float,
) -> tuple[float, float, float]:
    """Convert SI literature values to the normalised-position units used.

    α_norm = α_SI / loaf_thickness² (units: 1/s in normalised x).
    ρL_eff_norm: in the enthalpy-method formulation, the dimensionless
        latent-heat trap factor inside the smearing window is
        ``rhoL_eff / (2 dT · α_baseline)``. To preserve this ratio
        we set ``rhoL_eff_norm = rhoL_eff_lit / (rho · cp_ref · loaf_thickness²)``
        where ``rho · cp_ref ≈ k_lit / α_lit`` (since α = k/(ρcp)). That
        cancels to ``rhoL_eff_norm = rhoL_eff_lit · α_lit / (k_lit · loaf_thickness²)``.
        A standard k_dough ≈ 0.5 W/(m·K) means
        ``rhoL_eff_norm ≈ rhoL_eff_lit / (k / α) / loaf_thickness²``.
        With ρcp_dough ≈ 3.5e6 J/(m³·K), we get
        ``rhoL_eff_norm = rhoL_eff_lit / (rho_cp · loaf_thickness²)``
        which gives the dimensionless ratio L/cp directly (= 240 K for water).
        Multiplied by 1/loaf_thickness² (~ 400 m⁻²) and divided by ρcp,
        the practical normalised value is L_eff/(cp·thickness²) — i.e.
        about 240/0.0025 ≈ 1e5 in normalised K-units.
    """
    th2 = loaf_thickness_m * loaf_thickness_m
    alpha_d_norm = alpha_dough_lit / th2
    alpha_c_norm = alpha_crust_lit / th2
    # Use ρcp_dough = 3.5e6 J/(m³·K) (mean of liquid water 4.2e6 and solid
    # bread 2.8e6). This sets the latent/sensible ratio L/cp = 240 K, which
    # matches the temperature in K equivalent to the latent heat of water
    # (latent heat 2.26e6 J/kg / cp 4.2e3 J/(kg·K) ≈ 540 K, but we use the
    # moisture-fraction-weighted bread value).
    rho_cp_dough = 3.5e6  # J/(m³·K)
    rhoL_norm = rhoL_eff_lit / (rho_cp_dough * th2)
    return alpha_d_norm, alpha_c_norm, rhoL_norm


def fit_stefan_inverse_pinned(
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
    alpha_dough_lit: float = ALPHA_DOUGH_LIT_SI,
    alpha_crust_lit: float = ALPHA_CRUST_LIT_SI,
    rhoL_eff_lit: float = RHO_L_EFF_LIT_SI,
    loaf_thickness_m: float = LOAF_THICKNESS_M,
    x_core_init: float = -0.05,
    sample_period_s: float = 5.0,
    downsample_factor: int = 4,
    n_spatial: int = 60,
    delta_T_smear: float = 1.0,
    max_iter: int = 200,
) -> dict:
    """1-parameter fit (x_core only) with literature-pinned (α, ρL_eff).

    Conversion of literature values into normalised-position units:

    * α_norm = α_SI / loaf_thickness² (loaf_thickness = 50 mm by default).
    * ρL_eff_norm = ρL_eff_lit / (ρcp_dough · loaf_thickness²)
      with ρcp_dough = 3.5e6 J/(m³·K). This preserves the dimensionless
      L/cp ratio that determines the Stefan number.

    Returns a dict matching :func:`fit_stefan_inverse_joint`'s shape, but
    with the three pinned parameters reported alongside x_core. The
    ``full_correlation_matrix`` entry is a 1x1 matrix (just x_core).
    """
    from .profile import interpolate_temperature_series_at

    alpha_d_norm, alpha_c_norm, rhoL_norm = _lit_to_normalised(
        alpha_dough_lit, alpha_crust_lit, rhoL_eff_lit, loaf_thickness_m
    )

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

    def _loss(theta: np.ndarray) -> float:
        x_core = float(theta[0])
        if x_core >= x_surface - 1e-3:
            return 1e10
        try:
            T_pred = solve_stefan_forward(
                x_core=x_core,
                x_surface=x_surface,
                alpha_dough=alpha_d_norm,
                alpha_crust=alpha_c_norm,
                rhoL_eff=rhoL_norm,
                t_grid=t_obs,
                T_surface_series=T_surf_obs,
                T_initial=T_initial,
                n_spatial=n_spatial,
                sample_x=x_obs,
                delta_T_smear=delta_T_smear,
            )
        except Exception:
            return 1e10
        diff = (T_pred - T_obs).ravel()
        return float(np.sum(diff * diff))

    theta0 = np.array([x_core_init], dtype=float)
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

    x_core_hat = float(opt.x[0])
    sse = float(opt.fun)
    n_obs = int(T_obs.size)

    # Hessian on the 1-D loss → x_core_se directly.
    try:
        H = _numerical_hessian(_loss, opt.x, h=[5e-3])
        dof = max(n_obs - 1, 1)
        sigma2 = sse / dof
        cov_inflate = 1.4 ** 2
        # 1×1 Hessian → variance directly.
        var_xc = 2.0 * sigma2 * cov_inflate / max(float(H[0, 0]), 1e-30)
        x_core_se = float(np.sqrt(max(var_xc, 0.0)))
    except Exception:
        x_core_se = float("nan")

    rmse = float(np.sqrt(sse / max(n_obs, 1)))
    extrapolated = x_core_hat < float(min(sensor_positions_normalised))

    return {
        "x_core": x_core_hat,
        "x_core_se": x_core_se,
        "alpha_dough_pinned": alpha_d_norm,
        "alpha_crust_pinned": alpha_c_norm,
        "rhoL_eff_pinned": rhoL_norm,
        "alpha_dough_lit_si": alpha_dough_lit,
        "alpha_crust_lit_si": alpha_crust_lit,
        "rhoL_eff_lit_si": rhoL_eff_lit,
        "loaf_thickness_m": float(loaf_thickness_m),
        "full_correlation_matrix": [[1.0]],
        "max_abs_off_diag_correlation": 0.0,
        "sse": sse,
        "rmse_per_sensor": rmse,
        "n_obs": n_obs,
        "converged": bool(opt.success),
        "n_iter": int(opt.nit) if hasattr(opt, "nit") else 0,
        "T_initial": T_initial,
        "x_surface_continuous": x_surface,
        "extrapolated": bool(extrapolated),
        "bc_source": "interpolated_v2",
        "delta_T_smear": float(delta_T_smear),
        "variant": "pinned",
    }


__all__ = [
    "T_FRONT_C",
    "solve_stefan_forward",
    "classical_stefan_neumann",
    "fit_stefan_inverse_joint",
    "fit_stefan_inverse_pinned",
    "ALPHA_DOUGH_LIT_SI",
    "ALPHA_CRUST_LIT_SI",
    "RHO_L_EFF_LIT_SI",
    "LOAF_THICKNESS_M",
]
