# M20 HMS Resolute — Captain's Log

## Mission

Take M9 Stefan exactly as-is, free **α_dough** in (5×10⁻⁷, 1×10⁻⁵) m²/s SI
(equivalent to (2×10⁻⁴, 4×10⁻³) in M9 normalised units, since
α_norm = α_SI / loaf_thickness² with thickness = 50 mm) and **delta_T_smear**
in (3, 10) °C. Single-fixture validation on BA3C_0946 first.
Acceptance: main-bake RMSE < 4 °C with parameters interior.

## Context

M19 RCA flotilla identified two pinned-too-low parameters as the systematic
cause of why no physics model fit below ~6 °C across 17 missions:

1. α_dough was effectively pinned at literature SI 1.4e-7 m²/s → 5-7× too
   low for a 22-25 min bake at 50-65 mm slab thickness.
2. delta_T_smear=1 °C produced a too-narrow Stefan front, causing M9's
   depth-dependent residual sign-flip on BA3C_0946 (T1 -14 °C vs T2/T3
   +12-13 °C, lag-1 ρ=0.99).

M17 already empirically confirmed (1) by hitting 4.91e-6 m²/s at the 5e-6
upper bound when α was freed.

## Implementation summary

* `src/data/spatial_reconstruction/stefan_inverse_v2.py`
  - 5-param Nelder-Mead joint fit: (x_core, alpha_dough, alpha_crust,
    rhoL_eff, delta_T_smear).
  - Reuses M9's `solve_stefan_forward` (no solver code change — solver
    already accepts `delta_T_smear` as kwarg).
  - Reuses M9's `_build_observation_matrix`, `_correlation_matrix` and
    `_numerical_hessian` helpers (DRY).
  - Log-space transform on the three positive thermal parameters; linear
    on x_core and smear. Bound enforcement via penalty inside the loss
    (Nelder-Mead doesn't take bounds).
  - Delta-method Jacobian to convert log-param SE → linear-param SE for
    the reported correlation matrix (5×5 on the linear params).
  - SI-bound conversion: bounds entered in SI in BOUNDS_V2_SI, multiplied
    by 1/loaf_thickness² to get the normalised-unit bounds the forward
    solver actually sees.

* `tests/test_stefan_inverse_v2.py` — three tests as briefed:
  1. forward solver with wider smear (smoke test on the solver kwarg)
  2. inverse fits synthetic with freed alpha (correctness test)
  3. single-fixture BA3C_0946 main-bake RMSE < 4 °C (acceptance gate)

* `tests/_driver_stefan_v2.py` — 4-phase driver:
  1. forward sanity
  2. single-fixture BA3C_0946 (decision gate)
  3. 5-fixture sweep (skipped on gate fail)
  4. LOO subset on BA3C_0946 holding T1, T2 (skipped on gate fail)

* `tests/baselines/stefan_v2_research.{json,md}` — outputs.

## Decision gate — phase 2

Bar: main-bake RMSE < 4.0 °C AND ≤ 2 of 5 parameters at bounds.

Result: see `tests/baselines/stefan_v2_research.md` executive summary.

## Verdict + recommendation

See `tests/baselines/stefan_v2_research.md` final sections.
