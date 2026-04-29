# M21 HMS Onslaught — Stefan v3 (6-param, side-source freed)

**Mission**: extend M20 Stefan v2 with a distributed side-heat source `S(x,t) = Q_side · w(x) · g_oven(t)` representing tin-wall heat flux. Test the hypothesis that 1D-from-top can't explain deep-sensor heating because the model omits sidewall conduction.

## Executive summary

**Verdict: GO-WITH-CAVEATS**

- Phase 3 single-fixture BA3C_0946 main-bake RMSE = 5.66 °C (M9 5.76, M20 5.73; bar 4.0). n_interior = 5/6 (min 4).
- Phase 2 synthetic recovery: 1/5 seeds recovered Q_side within 30% (gate 3).

## Phase 1 — Forward sanity

(a) `Q_side=0` reproduces M20 forward: max|Δ| = 0.00000 K → PASS.

(b) `Q_side=1e5` warms interior: max ΔT = 34.34 K → PASS.

## Phase 2 — Synthetic recovery

Recovery target: Q_side within 30% on at least 3/5 seeds. Result: **1/5** seeds recovered. → FAIL


| seed | Q_true | Q_fit | rel_err | RMSE | n_at_bound | recovered |
|---|---|---|---|---|---|---|
| 11 | 2.80e+04 | 1.09e+04 | 61.0% | 0.84 | 0 | no |
| 23 | 1.07e+05 | 1.09e+04 | 89.8% | 1.68 | 0 | no |
| 37 | 1.09e+05 | 1.06e+04 | 90.2% | 4.01 | 0 | no |
| 53 | 1.16e+04 | 1.01e+04 | 12.6% | 0.56 | 0 | yes |
| 71 | 4.55e+04 | 1.01e+04 | 77.8% | 1.46 | 0 | no |

## Phase 3 — Single-fixture decision gate (BA3C_0946)

Bar: main-bake RMSE < 4 °C AND ≥ 4/6 params interior. Result: main-bake RMSE = **5.66 °C** (M9=5.76, M20=5.73); n_interior = 5/6; max&#124;ρ&#124; = 0.452; converged = True; → FAIL.


### Fitted parameters

| param | value | bound | SE |
|---|---|---|---|
| x_core_normalised | 4.2654e-04 | interior | 9.109e-03 |
| alpha_dough (norm) | 3.0343e-04 | interior | 5.005e-06 |
| alpha_crust (norm) | 1.3243e-04 | interior | 0.000e+00 |
| rhoL_eff (K) | 10.3383 | lo | 0.297 |
| delta_T_smear (°C) | 4.8174 | interior | 0.031 |
| Q_side (W/m³) | 1.3299e+04 | interior | 345.073 |


### 6×6 correlation matrix

| | x_core | α_d | α_c | ρL | ΔT_smear | Q_side |
|---|---|---|---|---|---|---|
| **x_core** |  1.000 | -0.452 | n/a | -0.115 |  0.135 |  0.021 |
| **α_d** | -0.452 |  1.000 | n/a |  0.389 | -0.343 |  0.025 |
| **α_c** | n/a | n/a | n/a | n/a | n/a | n/a |
| **ρL** | -0.115 |  0.389 | n/a |  1.000 | -0.051 |  0.051 |
| **ΔT_smear** |  0.135 | -0.343 | n/a | -0.051 |  1.000 | -0.103 |
| **Q_side** |  0.021 |  0.025 | n/a |  0.051 | -0.103 |  1.000 |


### Comparison vs prior missions

| mission | params | main-bake RMSE | Δ vs M9 |
|---|---|---|---|
| M9 (4-param baseline) | 4 | 5.76 | — |
| M20 (5-param: +α_d, +Δ_T_smear) | 5 | 5.73 | -0.03 |
| M21 (6-param: +Q_side) | 6 | 5.66 | -0.10 |


## Recommendation

v3 helps on the single-fixture gate but either misses the < 4 °C bar slightly or has multiple parameters at bounds. Treat v3 as a research curiosity; do not wire to runtime until either the synthetic recovery floor is solid OR the production-landing Method 1+4 metadata path is in place. Recommend M22 land Method 1 + Method 4 stub in parallel with any further v3 polish.
