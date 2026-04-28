# Luikov asymmetric-tin BC inverse — research report (HMS Sirius / M15)

**Mission:** Reformulate the M14 Luikov inverse with corrected geometry (95 mm probe span / 13.571 mm sensor pitch / decoupled loaf thickness) and asymmetric BCs (radiative-convective top to oven, conductive bottom through the tin). 8 free parameters; x_core depth becomes a *derived* quantity from the fitted profile.

**Branch:** `refactor/role-classification-unified`  
**Mission dir:** `.nelson/missions/2026-04-28_135827_d3177ebb`  
**Date:** 2026-04-29 (M15)  

## Executive summary

**Verdict: CONFIRM-information-limit**

- Forward sanity: 4-test pytest sub-suite PASS (returncode=0).
- Synthetic recovery (different-class generator: gen ε=0.3 δ=2.5 vs inv ε=0.5 δ=2.0; 5/5 runs finite, σ_noise=0.5 °C, 5 seeds): RMSE median 0.493 °C; L_m within 30%=5/5; D_m within 30%=5/5; Lu within 30%=5/5; Ko within 30%=2/5; Bi_top within 30%=3/5; Bi_bot within 30%=5/5; T_oven within 30%=5/5; T_tin within 30%=5/5.
- Real-CSV 8-param convergence: 4/7.
- Main-bake RMSE: <4 °C=0/4, 4-6 °C=2/4, >6 °C=2/4 (median 6.10 °C).
- Fixtures with ≥6/8 interior params: 0/4.
- x_core_depth_inferred in [30, 80] mm: 0/4 fixtures (range 81.0-88.0 mm).
- LOO subset (held-out T1, T2 on 3 fixtures): T1 LOO-RMSE median 11.74 °C (3 fits), T2 LOO-RMSE median 5.11 °C (3 fits). Compare M9 Stefan T1 LOO 9.0-21.0 °C; M14 Luikov T1 LOO 26.75 °C.
- Even with full asymmetric-tin BCs, correct probe geometry, and a free loaf thickness, main-bake RMSE remains above 4 °C on multiple fixtures and/or the deep-end T1 LOO blows up. The data fundamentally underdetermines the model class. Method 4 (per-CSV metadata capture: actual loaf thickness, oven setpoint, lid/tin state, plus inclusion of the surface-sensor signal in the loss) is the unambiguously remaining path.

## Method

Coupled heat + moisture transport on `x ∈ [0, L]` with `x=0` at the oven-facing top and `x=L` at the tin-contacting bottom. Convective-radiative top BC and convective tin bottom BC. Pinned constants: α=1.4×10⁻⁷ m²/s, c=2000 J/(kg·K), L_v=2.26×10⁶ J/kg, u_init=0.4, ε=0.5, δ=2.0, ε_rad=0.85, k=0.5 W/(m·K). 8 free parameters (L_m, D_m, Lu, Ko, Bi_top, Bi_bottom, T_oven_K, T_tin_K) optimised via Nelder-Mead with the soft constraint T_tin_K ≤ T_oven_K. Sensor positions are mapped from probe-relative (13.571 mm spacing from the tip) into loaf coordinates via d_i = D − (i−1)·13.571 mm — so probe geometry is decoupled from L.

## Forward solver sanity

4-test pytest sub-suite (`tests/test_luikov_tin_forward.py`): **PASS** (returncode=0). Tests: top-only-heated → descending profile, bottom-only-heated → ascending, symmetric BCs (with ε_rad=0, Ko≈0) → symmetric profile + core at L/2, long-time steady state → T → T_oven.

## Synthetic recovery (different-class generator)

Truth: L=95 mm, D=65 mm, Lu=0.1, Ko=5.0, Bi_top=8.0, Bi_bottom=2.0, T_oven=470.0 K, T_tin=410.0 K. Generator ε=0.3, δ=2.5; inverter ε=0.5, δ=2.0. σ_noise=0.5 °C, 5 seeds.

| metric | value |
|---|---|
| n_runs | 5 |
| n_finite | 5 |
| RMSE median | 0.493 |
| RMSE max | 0.508 |
| L_m within 30% | 5/5 |
| D_m within 30% | 5/5 |
| Lu within 30% | 5/5 |
| Ko within 30% | 2/5 |
| Bi_top within 30% | 3/5 |
| Bi_bottom within 30% | 5/5 |
| T_oven_K within 30% | 5/5 |
| T_tin_K within 30% | 5/5 |
| interior count median | 7.0/8 |
| x_core_inferred median (mm) | 55.8 |

Per-seed table:

| seed | L_m (mm) | D_m (mm) | Lu | Ko | Bi_top | Bi_bot | T_oven (K) | T_tin (K) | x_core_inf (mm) | rmse | interior | fit_s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 96.7 | 65.6 | 0.101 | 3.70 | 10.13 | 1.94 | 472 | 423 | 55.7 | 0.486 | 7/8 | 24.8 |
| 1 | 96.3 | 66.3 | 0.117 | 3.15 | 12.24 | 2.05 | 472 | 408 | 57.1 | 0.487 | 8/8 | 29.4 |
| 2 | 93.5 | 64.6 | 0.087 | 4.39 | 7.44 | 1.78 | 474 | 413 | 53.9 | 0.508 | 7/8 | 24.2 |
| 3 | 95.3 | 65.7 | 0.111 | 3.44 | 10.48 | 2.11 | 472 | 403 | 56.5 | 0.501 | 8/8 | 25.1 |
| 4 | 94.0 | 65.5 | 0.107 | 3.48 | 9.74 | 2.00 | 472 | 400 | 55.8 | 0.493 | 7/8 | 25.4 |

## Per-fixture real-CSV inverse results

| fixture | L_m (mm) | D_m (mm) | Lu | Ko | Bi_top | Bi_bot | T_oven (K) | T_tin (K) | x_core_inf (mm) | RMSE_full | interior |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | 136.6 | 94.9 | 3.496 | 3.64 | 6.72 | 0.68 | 600 | 600 | 88.0 | 6.45 | 4/8 |
| `BA3C_1759_C0` | 136.6 | 94.9 | 3.496 | 3.64 | 6.72 | 0.68 | 600 | 600 | 88.0 | 6.45 | 4/8 |
| `BA3C_1759_C1` | 150.0 | 95.0 | 1.132 | 11.58 | 0.99 | 1.50 | 581 | 581 | 81.4 | 6.47 | 4/8 |
| `BA3C_1759_C2` | 149.4 | 95.0 | 1.644 | 5.70 | 5.07 | 2.13 | 600 | 600 | 81.0 | 6.76 | 3/8 |
| `100098DE_1351` | ERROR/no-conv | | | | | | | | | | |
| `wonder_white` | ERROR/no-conv | | | | | | | | | | |
| `post_wonder_meal` | ERROR/no-conv | | | | | | | | | | |

## Per-fixture residual decomposition (M10 helpers)

| fixture | RMSE_full | RMSE_main | RMSE_startup | RMSE_tail | ρ_main | max&#124;ρ_off&#124; |
|---|---|---|---|---|---|---|
| `BA3C_0946` | 6.26 | 5.98 | 6.01 | 8.10 | 0.988 | 0.944 |
| `BA3C_1759_C0` | 6.26 | 5.98 | 6.01 | 8.10 | 0.988 | 0.944 |
| `BA3C_1759_C1` | 5.86 | 6.23 | 1.32 | 5.86 | 0.993 | 0.562 |
| `BA3C_1759_C2` | 6.09 | 6.43 | 1.85 | 6.25 | 0.994 | 0.937 |
| `100098DE_1351` | (skipped) | | | | | |
| `wonder_white` | (skipped) | | | | | |
| `post_wonder_meal` | (skipped) | | | | | |

## Main-bake RMSE comparison: Sirius vs M9 Stefan vs M14 Luikov

| fixture | Sirius (M15) | M9 Stefan | M14 Luikov (50mm/symmetric) |
|---|---|---|---|
| `BA3C_0946` | 5.98 | 5.76 | 20.35 |
| `BA3C_1759_C0` | 5.98 | 5.76 | 20.35 |
| `BA3C_1759_C1` | 6.23 | 6.80 | 20.99 |
| `BA3C_1759_C2` | 6.43 | 7.95 | 19.76 |
| `100098DE_1351` | nan | 7.49 | 13.47 |
| `wonder_white` | nan | 11.03 | 19.00 |
| `post_wonder_meal` | nan | 10.55 | nan |

## Bound-hitting (per-parameter, per-fixture)

Each cell shows where the parameter landed: `interior`, `lo` (at lower bound), or `hi` (at upper bound).

| fixture | L_m | D_m | Lu | Ko | Bi_top | Bi_bot | T_oven | T_tin |
|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | interior | hi | interior | interior | interior | lo | hi | hi |
| `BA3C_1759_C0` | interior | hi | interior | interior | interior | lo | hi | hi |
| `BA3C_1759_C1` | hi | hi | interior | interior | lo | lo | interior | interior |
| `BA3C_1759_C2` | hi | hi | interior | interior | lo | interior | hi | hi |
| `100098DE_1351` | interior | interior | interior | hi | lo | lo | interior | interior |
| `wonder_white` | interior | hi | hi | interior | lo | interior | interior | interior |
| `post_wonder_meal` | interior | interior | hi | lo | lo | interior | interior | interior |

## LOO subset (deep-end T1, T2 on 3 representative fixtures)

M13 Stefan/Zürcher T1 LOO range: 9.0-21.0 °C. M14 Luikov T1 LOO: 26.75 °C. Question for M15: does asymmetric BC + correct geometry recover the deep end?

| fixture | held_out | LOO_rmse | in_sample | ratio | max&#124;res&#124; | mean_res | x_core_inf (mm) | interior | fit_s |
|---|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | T1 | 11.74 | 4.93 | 2.38 | 20.8 | +6.63 | 79.5 | 6/8 | 39.4 |
| `BA3C_0946` | T2 | 6.37 | 5.77 | 1.10 | 11.3 | -2.15 | 83.9 | 5/8 | 49.1 |
| `100098DE_1351` | T1 | 8.85 | 5.52 | 1.60 | 24.2 | +4.51 | 63.8 | 4/8 | 35.7 |
| `100098DE_1351` | T2 | 5.01 | 6.10 | 0.82 | 8.7 | -2.34 | 68.4 | 5/8 | 36.9 |
| `wonder_white` | T1 | 12.07 | 8.33 | 1.45 | 26.0 | +7.26 | 50.3 | 6/8 | 39.9 |
| `wonder_white` | T2 | 5.11 | 11.46 | 0.45 | 8.1 | +0.50 | 52.6 | 6/8 | 44.7 |

## 8x8 correlation matrices per fixture


### `BA3C_0946`

max |off-diag|: 0.944

| | L_m | D_m | Lu | Ko | Bi_top | Bi_bot | T_oven_K | T_tin_K |
|---|---|---|---|---|---|---|---|---|
| **L_m** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **D_m** | n/a |  1.000 | -0.000 | -0.000 |  0.001 | n/a |  0.333 |  0.333 |
| **Lu** | n/a | -0.000 |  1.000 | -0.944 |  0.321 | n/a |  0.000 |  0.000 |
| **Ko** | n/a | -0.000 | -0.944 |  1.000 | -0.583 | n/a | -0.000 | -0.000 |
| **Bi_top** | n/a |  0.001 |  0.321 | -0.583 |  1.000 | n/a |  0.001 |  0.001 |
| **Bi_bot** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **T_oven_K** | n/a |  0.333 |  0.000 | -0.000 |  0.001 | n/a |  1.000 |  0.333 |
| **T_tin_K** | n/a |  0.333 |  0.000 | -0.000 |  0.001 | n/a |  0.333 |  1.000 |


### `BA3C_1759_C0`

max |off-diag|: 0.944

| | L_m | D_m | Lu | Ko | Bi_top | Bi_bot | T_oven_K | T_tin_K |
|---|---|---|---|---|---|---|---|---|
| **L_m** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **D_m** | n/a |  1.000 | -0.000 | -0.000 |  0.001 | n/a |  0.333 |  0.333 |
| **Lu** | n/a | -0.000 |  1.000 | -0.944 |  0.321 | n/a |  0.000 |  0.000 |
| **Ko** | n/a | -0.000 | -0.944 |  1.000 | -0.583 | n/a | -0.000 | -0.000 |
| **Bi_top** | n/a |  0.001 |  0.321 | -0.583 |  1.000 | n/a |  0.001 |  0.001 |
| **Bi_bot** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **T_oven_K** | n/a |  0.333 |  0.000 | -0.000 |  0.001 | n/a |  1.000 |  0.333 |
| **T_tin_K** | n/a |  0.333 |  0.000 | -0.000 |  0.001 | n/a |  0.333 |  1.000 |


### `BA3C_1759_C1`

max |off-diag|: 0.562

| | L_m | D_m | Lu | Ko | Bi_top | Bi_bot | T_oven_K | T_tin_K |
|---|---|---|---|---|---|---|---|---|
| **L_m** |  1.000 |  0.250 | n/a | n/a | -0.000 | -0.000 | n/a | n/a |
| **D_m** |  0.250 |  1.000 | n/a | n/a | -0.000 | -0.000 | n/a | n/a |
| **Lu** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **Ko** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **Bi_top** | -0.000 | -0.000 | n/a | n/a |  1.000 |  0.562 | n/a | n/a |
| **Bi_bot** | -0.000 | -0.000 | n/a | n/a |  0.562 |  1.000 | n/a | n/a |
| **T_oven_K** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **T_tin_K** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |


### `BA3C_1759_C2`

max |off-diag|: 0.937

| | L_m | D_m | Lu | Ko | Bi_top | Bi_bot | T_oven_K | T_tin_K |
|---|---|---|---|---|---|---|---|---|
| **L_m** |  1.000 |  0.500 | n/a | n/a | -0.000 | -0.000 |  0.500 |  0.500 |
| **D_m** |  0.500 |  1.000 | n/a | n/a |  0.000 | -0.000 |  0.500 |  0.500 |
| **Lu** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **Ko** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **Bi_top** | -0.000 |  0.000 | n/a | n/a |  1.000 |  0.937 | -0.000 | -0.000 |
| **Bi_bot** | -0.000 | -0.000 | n/a | n/a |  0.937 |  1.000 | -0.000 | -0.000 |
| **T_oven_K** |  0.500 |  0.500 | n/a | n/a | -0.000 | -0.000 |  1.000 |  0.500 |
| **T_tin_K** |  0.500 |  0.500 | n/a | n/a | -0.000 | -0.000 |  0.500 |  1.000 |


### `100098DE_1351`

max |off-diag|: 0.250

| | L_m | D_m | Lu | Ko | Bi_top | Bi_bot | T_oven_K | T_tin_K |
|---|---|---|---|---|---|---|---|---|
| **L_m** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **D_m** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **Lu** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **Ko** | n/a | n/a | n/a |  1.000 | -0.250 |  0.000 | n/a | n/a |
| **Bi_top** | n/a | n/a | n/a | -0.250 |  1.000 | -0.000 | n/a | n/a |
| **Bi_bot** | n/a | n/a | n/a |  0.000 | -0.000 |  1.000 | n/a | n/a |
| **T_oven_K** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| **T_tin_K** | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |


### `wonder_white`

max |off-diag|: 0.969

| | L_m | D_m | Lu | Ko | Bi_top | Bi_bot | T_oven_K | T_tin_K |
|---|---|---|---|---|---|---|---|---|
| **L_m** |  1.000 | -0.000 | -0.000 | -0.031 |  0.149 |  0.902 | -0.294 |  0.807 |
| **D_m** | -0.000 |  1.000 |  0.250 | -0.000 |  0.001 | -0.000 |  0.001 |  0.000 |
| **Lu** | -0.000 |  0.250 |  1.000 | -0.000 |  0.001 | -0.000 |  0.001 |  0.000 |
| **Ko** | -0.031 | -0.000 | -0.000 |  1.000 | -0.839 | -0.431 | -0.646 | -0.600 |
| **Bi_top** |  0.149 |  0.001 |  0.001 | -0.839 |  1.000 |  0.431 |  0.870 |  0.640 |
| **Bi_bot** |  0.902 | -0.000 | -0.000 | -0.431 |  0.431 |  1.000 | -0.063 |  0.969 |
| **T_oven_K** | -0.294 |  0.001 |  0.001 | -0.646 |  0.870 | -0.063 |  1.000 |  0.183 |
| **T_tin_K** |  0.807 |  0.000 |  0.000 | -0.600 |  0.640 |  0.969 |  0.183 |  1.000 |


### `post_wonder_meal`

max |off-diag|: 0.814

| | L_m | D_m | Lu | Ko | Bi_top | Bi_bot | T_oven_K | T_tin_K |
|---|---|---|---|---|---|---|---|---|
| **L_m** |  1.000 |  0.489 | -0.000 | -0.187 |  0.202 |  0.613 |  0.386 |  0.038 |
| **D_m** |  0.489 |  1.000 | -0.000 | -0.398 |  0.264 |  0.110 |  0.814 | -0.102 |
| **Lu** | -0.000 | -0.000 |  1.000 | -0.000 |  0.000 | -0.000 | -0.000 |  0.000 |
| **Ko** | -0.187 | -0.398 | -0.000 |  1.000 | -0.408 | -0.437 | -0.683 | -0.023 |
| **Bi_top** |  0.202 |  0.264 |  0.000 | -0.408 |  1.000 |  0.169 |  0.050 |  0.059 |
| **Bi_bot** |  0.613 |  0.110 | -0.000 | -0.437 |  0.169 |  1.000 |  0.246 | -0.506 |
| **T_oven_K** |  0.386 |  0.814 | -0.000 | -0.683 |  0.050 |  0.246 |  1.000 | -0.080 |
| **T_tin_K** |  0.038 | -0.102 |  0.000 | -0.023 |  0.059 | -0.506 | -0.080 |  1.000 |

## Recommendation for production

Even with the corrected geometry and asymmetric tin BCs, the in-dough-only observation matrix does not constrain the deep region or the full 8-parameter space. The complete physics-class hierarchy plus geometric correction has been exhausted on this data alone. **Method 4** — per-CSV loaf-thickness, oven-setpoint, lid/tin-state metadata capture, plus inclusion of the spatially-interpolated surface-sensor signal in the loss — is the only remaining structural path.
