# Luikov 1D coupled heat-mass inverse — research report

**Mission:** HMS Lively (M14) — final inverse-problem research mission across the full physics-class hierarchy. Implements the Luikov (1966) coupled heat-mass transfer formulation parameterised in the four Luikov dimensionless numbers (Lu, Ko, Bi, ε, Pn) plus core position and effective oven temperature, with explicit moisture transport via the phase-change source term.

**Branch:** `refactor/role-classification-unified`  
**Mission dir:** `.nelson/missions/2026-04-28_125109_7db8fefb`  
**Date:** 2026-04-28  

## Executive summary

**Verdict: CONFIRM-information-limit**

- Forward sanity: uncoupled-limit PASS=True, steady-state PASS=True.
- Synthetic recovery (different-class generator: gen α=1.0e-7 ε=0.3 vs inv α=1.4e-7 ε=0.5; 5/5 runs finite, σ_noise=0.5 °C, 5 seeds): RMSE median 0.504 °C; x_core within 5 mm = 0/5; Lu within 30% = 4/5; Ko within 30% = 1/5; Bi within 30% = 4/5; T_oven within 5 K = 2/5.
- Real-CSV 5-param convergence: 6/7 fixtures.
- Main-bake RMSE: <3 °C=0/6, 3-6 °C=0/6, >6 °C=6/6 (median 20.05 °C).
- Fixtures with all of (Lu, Ko, Bi) inside literature ranges: 0/7.
- LOO subset (15 fits across 3 fixtures): LOO-RMSE median 24.30 °C, max 71.39 °C; ratio LOO/in-sample median 1.12; T1 (deep-end) LOO-RMSE median 26.75 °C (3 fits).
- Even with the full Luikov 5-parameter coupled heat-mass formulation, main-bake RMSE remains above 6 °C on multiple fixtures and/or the deep-end T1 LOO-RMSE blows up. The complete physics-class hierarchy (single-medium → Stefan-PDE → Zürcher-radiative → Luikov-coupled-heat-mass) has been exhausted on the in-dough-only observation matrix this dataset provides. **Method 4** (per-CSV loaf-thickness, oven-setpoint, and lid-state metadata capture, plus inclusion of the surface-sensor signal in the loss) is the only remaining path.

## Forward solver sanity

**Uncoupled limit** (Lu=ε=Ko≈0, Bi=10, t=200000s): final T_min=450.00 K, T_max=450.00 K, max|T-T_oven|=0.00 K — PASS=True.

**Steady-state** (full coupling, Lu=0.15, Ko=4, Bi=5, t=60000s): T=[422.75, 448.62] K, u_max=0.1822, u_min=0.0000 — PASS=True.

Overall forward sanity: PASS.

## Synthetic recovery (different-class generator)

To avoid the M7 tautology trap, the generator used α=1.0e-07 m²/s, ε=0.3 while the inverter used α=1.4e-07 m²/s, ε=0.5. Synthetic data class genuinely differs from the inverter's class — recovery within 30% becomes a real identifiability test, not a tautology.

Truth: x_core = -8.0 mm, Lu = 0.2, Ko = 4.0, Bi = 3.0, T_oven_eff = 460 K. σ_noise = 0.5 °C, 5 seeds.

| metric | value |
|---|---|
| n_runs | 5 |
| n_finite | 5 |
| RMSE median | 0.504 °C |
| RMSE max | 0.515 °C |
| x_core within 5 mm | 0/5 |
| Lu within 30% | 4/5 |
| Ko within 30% | 1/5 |
| Bi within 30% | 4/5 |
| T_oven within 5 K | 2/5 |

Per-seed table:

| seed | x_core_m | Lu | Ko | Bi | T_oven | rmse | n_iter | converged | fit_s |
|---|---|---|---|---|---|---|---|---|---|
| 0 | -0.0176 | 0.203 | 2.499 | 2.628 | 455.2 | 0.489 | 497 | True | 17.2 |
| 1 | -0.0175 | 0.214 | 2.289 | 2.478 | 457.9 | 0.492 | 436 | True | 15.5 |
| 2 | -0.0184 | 0.209 | 2.045 | 2.266 | 465.5 | 0.515 | 427 | True | 14.7 |
| 3 | -0.0186 | 0.172 | 3.334 | 3.089 | 454.3 | 0.504 | 599 | True | 18.2 |
| 4 | -0.0186 | 0.274 | 0.931 | 1.342 | 514.0 | 0.510 | 480 | True | 15.4 |

## Per-fixture real-CSV inverse results

| fixture | x_core_n | Lu | Ko | Bi | T_oven | RMSE_full | RMSE_main | RMSE_startup | RMSE_tail | ρ_main | max&#124;ρ_off&#124; |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | +0.208 | 0.010 | 0.101 | 50.000 | 433 | 24.98 | 20.35 | 5.53 | 40.40 | 0.993 | 0.333 |
| `BA3C_1759_C0` | +0.208 | 0.010 | 0.101 | 50.000 | 433 | 24.98 | 20.35 | 5.53 | 40.40 | 0.993 | 0.333 |
| `BA3C_1759_C1` | +0.253 | 0.010 | 29.999 | 50.000 | 445 | 24.05 | 20.99 | 3.95 | 35.16 | 0.998 | 0.333 |
| `BA3C_1759_C2` | +0.214 | 0.010 | 29.997 | 49.243 | 440 | 23.58 | 19.76 | 2.34 | 36.77 | 0.998 | 0.333 |
| `100098DE_1351` | +0.643 | 0.039 | 3.611 | 42.949 | 394 | 13.53 | 13.47 | 5.27 | 8.38 | 0.995 | 0.755 |
| `wonder_white` | +0.736 | 0.010 | 10.459 | 39.909 | 359 | 19.28 | 19.00 | 9.17 | 18.71 | 0.999 | 0.855 |
| `post_wonder_meal` | +0.063 | 0.021 | 29.969 | 47.123 | 584 | 36.85 | nan | nan | nan | nan | 0.906 |

## Main-bake RMSE comparison: Luikov vs M9 Stefan vs M12 Zürcher

| fixture | Luikov main-bake (M14) | M9 Stefan main-bake (M10) | M12 Zürcher 5-param main-bake |
|---|---|---|---|
| `BA3C_0946` | 20.35 | 5.76 | 36.51 |
| `BA3C_1759_C0` | 20.35 | 5.76 | 36.51 |
| `BA3C_1759_C1` | 20.99 | 6.80 | 34.70 |
| `BA3C_1759_C2` | 19.76 | 7.95 | 38.54 |
| `100098DE_1351` | 13.47 | 7.49 | 35.22 |
| `wonder_white` | 19.00 | 11.03 | 38.07 |
| `post_wonder_meal` | nan | 10.55 | 35.40 |

## Parameter physicality

Literature ranges per the briefing: Lu ∈ (0.05, 0.50); Ko ∈ (1.0, 10.0); Bi ∈ (0.5, 10.0); T_oven_eff ∈ (450, 500) K open / (350, 380) K lidded.

| fixture | Lu in lit | Ko in lit | Bi in lit | T_oven in lit |
|---|---|---|---|---|
| `BA3C_0946` | 0.010 ✗ | 0.101 ✗ | 50.000 ✗ | 433 ✗ |
| `BA3C_1759_C0` | 0.010 ✗ | 0.101 ✗ | 50.000 ✗ | 433 ✗ |
| `BA3C_1759_C1` | 0.010 ✗ | 29.999 ✗ | 50.000 ✗ | 445 ✗ |
| `BA3C_1759_C2` | 0.010 ✗ | 29.997 ✗ | 49.243 ✗ | 440 ✗ |
| `100098DE_1351` | 0.039 ✗ | 3.611 ✓ | 42.949 ✗ | 394 ✗ |
| `wonder_white` | 0.010 ✗ | 10.459 ✗ | 39.909 ✗ | 359 ✓ |
| `post_wonder_meal` | (no fit) | | | |

## LOO subset (3 representative fixtures)

Held-out sensor predicted from a refit on the remaining N-1 in-dough sensors. Question: does T1 (deep-end) LOO-RMSE improve under Luikov's moisture-transport physics vs M13's Stefan/Zürcher 11-37 °C?

| fixture | held_out | LOO_rmse | in_sample | ratio | max&#124;res&#124; | mean_res | converged | fit_s |
|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | T1 | 26.75 | 21.16 | 1.26 | 53.3 | -20.17 | True | 9.6 |
| `BA3C_0946` | T2 | 27.18 | 21.82 | 1.25 | 50.6 | -21.58 | True | 12.0 |
| `BA3C_0946` | T3 | 23.01 | 23.28 | 0.99 | 39.3 | -19.16 | True | 7.2 |
| `BA3C_0946` | T4 | 12.43 | 27.15 | 0.46 | 19.8 | -10.32 | False | 14.9 |
| `BA3C_0946` | T5 | 71.39 | 24.11 | 2.96 | 94.6 | +66.19 | True | 14.9 |
| `100098DE_1351` | T1 | 20.24 | 13.26 | 1.53 | 29.3 | -18.62 | True | 17.9 |
| `100098DE_1351` | T2 | 33.19 | 30.14 | 1.10 | 52.2 | -27.50 | True | 6.7 |
| `100098DE_1351` | T3 | 21.29 | 34.57 | 0.62 | 36.4 | -17.47 | True | 6.4 |
| `100098DE_1351` | T4 | 23.90 | 10.45 | 2.29 | 38.1 | +20.48 | True | 17.5 |
| `wonder_white` | T1 | 48.65 | 30.33 | 1.60 | 60.9 | -44.72 | True | 12.4 |
| `wonder_white` | T2 | 24.30 | 26.13 | 0.93 | 35.4 | -21.68 | True | 20.1 |
| `wonder_white` | T3 | 24.73 | 33.01 | 0.75 | 41.6 | -20.15 | True | 10.9 |
| `wonder_white` | T4 | 10.49 | 15.18 | 0.69 | 18.1 | +5.22 | True | 18.9 |
| `wonder_white` | T5 | 15.55 | 13.86 | 1.12 | 26.8 | +11.56 | False | 33.5 |
| `wonder_white` | T6 | 65.66 | 36.60 | 1.79 | 87.0 | +61.51 | True | 6.7 |

## Correlation matrices per fixture


### `BA3C_0946`

| | x_core_m | Lu | Ko | Bi | T_oven_K |
|---|---|---|---|---|---|
| **x_core_m** | n/a | n/a | n/a | n/a | n/a |
| **Lu** | n/a |  1.000 |  0.333 | -0.333 |  0.004 |
| **Ko** | n/a |  0.333 |  1.000 | -0.333 |  0.004 |
| **Bi** | n/a | -0.333 | -0.333 |  1.000 | -0.004 |
| **T_oven_K** | n/a |  0.004 |  0.004 | -0.004 |  1.000 |


### `BA3C_1759_C0`

| | x_core_m | Lu | Ko | Bi | T_oven_K |
|---|---|---|---|---|---|
| **x_core_m** | n/a | n/a | n/a | n/a | n/a |
| **Lu** | n/a |  1.000 |  0.333 | -0.333 |  0.004 |
| **Ko** | n/a |  0.333 |  1.000 | -0.333 |  0.004 |
| **Bi** | n/a | -0.333 | -0.333 |  1.000 | -0.004 |
| **T_oven_K** | n/a |  0.004 |  0.004 | -0.004 |  1.000 |


### `BA3C_1759_C1`

| | x_core_m | Lu | Ko | Bi | T_oven_K |
|---|---|---|---|---|---|
| **x_core_m** | n/a | n/a | n/a | n/a | n/a |
| **Lu** | n/a |  1.000 | -0.333 | -0.333 |  0.004 |
| **Ko** | n/a | -0.333 |  1.000 |  0.333 | -0.004 |
| **Bi** | n/a | -0.333 |  0.333 |  1.000 | -0.004 |
| **T_oven_K** | n/a |  0.004 | -0.004 | -0.004 |  1.000 |


### `BA3C_1759_C2`

| | x_core_m | Lu | Ko | Bi | T_oven_K |
|---|---|---|---|---|---|
| **x_core_m** | n/a | n/a | n/a | n/a | n/a |
| **Lu** | n/a |  1.000 | -0.333 | -0.333 |  0.004 |
| **Ko** | n/a | -0.333 |  1.000 |  0.333 | -0.004 |
| **Bi** | n/a | -0.333 |  0.333 |  1.000 | -0.004 |
| **T_oven_K** | n/a |  0.004 | -0.004 | -0.004 |  1.000 |


### `100098DE_1351`

| | x_core_m | Lu | Ko | Bi | T_oven_K |
|---|---|---|---|---|---|
| **x_core_m** |  1.000 |  0.079 |  0.065 | n/a | -0.425 |
| **Lu** |  0.079 |  1.000 | -0.038 | n/a |  0.488 |
| **Ko** |  0.065 | -0.038 |  1.000 | n/a |  0.755 |
| **Bi** | n/a | n/a | n/a | n/a | n/a |
| **T_oven_K** | -0.425 |  0.488 |  0.755 | n/a |  1.000 |


### `wonder_white`

| | x_core_m | Lu | Ko | Bi | T_oven_K |
|---|---|---|---|---|---|
| **x_core_m** |  1.000 | -0.000 |  0.022 | n/a | -0.512 |
| **Lu** | -0.000 |  1.000 | -0.000 | n/a | -0.000 |
| **Ko** |  0.022 | -0.000 |  1.000 | n/a |  0.855 |
| **Bi** | n/a | n/a | n/a | n/a | n/a |
| **T_oven_K** | -0.512 | -0.000 |  0.855 | n/a |  1.000 |


### `post_wonder_meal`

| | x_core_m | Lu | Ko | Bi | T_oven_K |
|---|---|---|---|---|---|
| **x_core_m** | n/a | n/a | n/a | n/a | n/a |
| **Lu** | n/a |  1.000 |  0.000 |  0.657 |  0.906 |
| **Ko** | n/a |  0.000 |  1.000 | -0.000 | -0.000 |
| **Bi** | n/a |  0.657 | -0.000 |  1.000 |  0.304 |
| **T_oven_K** | n/a |  0.906 | -0.000 |  0.304 |  1.000 |

## Recommendation for production

The full hierarchy (single-medium → Stefan-PDE → Zürcher-radiative → Luikov-coupled-heat-mass) has been exhausted. Even with explicit moisture transport and convective Biot BC, the in-dough-only observation matrix does not constrain the deep region. **Method 4** (per-CSV loaf-thickness, oven-setpoint, lid-state metadata; or inclusion of the spatially-interpolated surface signal in the loss) is the only remaining path. Recommend pivoting away from inverse-problem work on this data alone.
