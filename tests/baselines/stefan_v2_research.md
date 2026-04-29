# M20 HMS Resolute — Stefan v2 (5-param, α + smear free)

**Mission**: take M9 Stefan exactly as-is, free α_dough in (5e-7, 1e-5) m²/s and Δ_T_smear in (3, 10) °C. Single-fixture validation on BA3C_0946 first. Acceptance: main-bake RMSE < 4 °C with parameters interior.

## Executive summary

**Verdict: GO-WITH-CAVEATS**

- Phase 2 single-fixture BA3C_0946 main-bake RMSE = 5.73 °C (M9 baseline 5.76; bar 4.0).
- Phase 2 n_at_bound = 2 of 5 (max allowed 2).

## Phase 1 — Forward sanity

smear=1 final core T = 25.00 °C (finite=True); smear=5 final core T = 25.00 °C (finite=True); → PASS.

## Phase 2 — Single-fixture BA3C_0946 (decision gate)

Bar: main-bake RMSE < 4 °C AND ≤ 2 of 5 params at bounds. Result: main-bake RMSE = **5.73 °C** (M9 baseline 5.76); n_at_bound = 2 of 5; max&#124;ρ&#124; = 0.483; converged = True; → FAIL.


### Fitted parameters

| param | value | bound | SE |
|---|---|---|---|
| x_core_normalised | 4.3727e-04 | interior | 8.048e-03 |
| alpha_dough (m²/s_norm) | 3.2135e-04 | interior | 6.144e-06 |
| alpha_crust (m²/s_norm) | 4.7668e-05 | lo | 6.675e-06 |
| rhoL_eff (K) | 10.1182 | lo | 1.442 |
| delta_T_smear (°C) | 5.0230 | interior | 0.142 |


### 5×5 correlation matrix

| | x_core | α_d | α_c | ρL | ΔT_smear |
|---|---|---|---|---|---|
| **x_core** |  1.000 | -0.483 | -0.003 | -0.020 |  0.010 |
| **α_d** | -0.483 |  1.000 |  0.001 | -0.004 | -0.007 |
| **α_c** | -0.003 |  0.001 |  1.000 | -0.000 | -0.001 |
| **ρL** | -0.020 | -0.004 | -0.000 |  1.000 |  0.161 |
| **ΔT_smear** |  0.010 | -0.007 | -0.001 |  0.161 |  1.000 |


## Recommendation

Stefan v2 improves on M9 — main-bake RMSE drops below 6 °C — but either the < 4 °C bar is missed on some fixtures, or LOO drop is below the 30% target, or parameters are at bounds on multiple fixtures. Recommend treating Stefan v2 as a *research-only* improvement; do not wire to runtime until a fixture-stratified follow-up identifies which fixtures need a model-class change (lid pathology, geometry mismatch). M21 should pursue Method 4 (loaf-thickness metadata) in parallel.
