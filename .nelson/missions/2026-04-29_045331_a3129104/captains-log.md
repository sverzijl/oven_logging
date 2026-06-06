# M21 HMS Onslaught — Captain's Log

**Mission**: extend M20 Stefan v2 with a distributed side-heat source
`S(x, t) = Q_side · w(x) · g_oven(t)` to test the hypothesis that 1D-from-top
conduction omits sidewall flux through the tin walls.

**Branch**: `refactor/role-classification-unified`.
**Date**: 2026-04-29.
**Token budget**: ~120k.

## Standing orders honoured

- *feedback_redcell_empirical_verification*: the decision gate IS the verdict.
  No autopolish if rmse_main remains > 4 °C.
- *feedback_tdd_dry*: failing tests written first
  (`test_forward_S_zero_reproduces_v2`, `test_forward_S_nonzero_warms_interior`,
  `test_inverse_recovers_synthetic_Q_side`,
  `test_single_fixture_BA3C_0946_decision_gate`); v3 module reuses M9
  forward helpers (`_alpha_eff_factory`), M9/M20 observation-matrix
  helpers (`_build_observation_matrix`), M20 bound-status helper
  (`_bound_status`), M20 bounds/init dicts (extended).

## Files added / modified

- `src/data/spatial_reconstruction/stefan_inverse_v3.py` — new module.
  - `solve_stefan_forward_v3` — M9 forward + side-source term.
    Reuses `_alpha_eff_factory` from `stefan_inverse.py`. Source enters
    the method-of-lines RHS as `S_norm · w(x) · g(t)` where
    `S_norm = Q_side / (ρ·c_p)`, `ρ·c_p = 2.0e6 J/(m³·K)`,
    `w(x) = 1 - 2|x_n - 0.5|` (tent at mid-depth),
    `g(t)` = normalised ambient-sensor profile.
  - `fit_stefan_inverse_v3` — 6-param Nelder-Mead fit (mirror of v2 +
    Q_side as 6th linear param).
  - `_build_g_oven_from_ambient` — picks the warmest sensor above the
    surface position as the oven-driving profile, normalises to [0,1].
- `tests/test_stefan_inverse_v3.py` — 4 tests (forward sanity ×2,
  synthetic recovery, decision gate).
- `tests/_driver_stefan_v3.py` — phased driver (sanity → synthetic
  recovery → BA3C_0946 gate → 5-fixture sweep).
- `tests/baselines/stefan_v3_research.{json,md}` — outputs.

## Verdict and rationale

(filled in by the driver after Phase 3 / 4 — see
`tests/baselines/stefan_v3_research.md`).
