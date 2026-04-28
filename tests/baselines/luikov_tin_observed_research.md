# Luikov OBSERVED-BC inverse — research report (HMS Daring / M16)

**Mission:** Reformulate the M15 asymmetric-tin Luikov inverse with OBSERVED top-BC inputs (T_air(t) from M2a-flagged ambient sensor, h_eff(t) from surface energy balance) and a piecewise α(T) profile for oven-spring property change. 4-5 free parameters (down from M15's 8). Per-fixture diagnostics extracted upfront.

**Branch:** `refactor/role-classification-unified`  
**Mission dir:** `.nelson/missions/2026-04-28_145444_9193a856`  
**Date:** 2026-04-28 (M16)  

## Executive summary

**Verdict: CONFIRM-information-limit**

- Forward sanity: 8-test pytest sub-suite PASS (returncode=0).
- Synthetic recovery (different α_pre: gen 1.0e-7 vs inv 1.4e-7; 3/3 runs finite, σ_noise=0.5 °C, 3 seeds): RMSE median 0.551 °C; L_m within 30%=3/3; D_m within 30%=3/3; Lu within 30%=2/3; q_bot within 30%=3/3; α_ratio within 30%=3/3.
- Real-CSV 4-5 param convergence: 5/7.
- Main-bake RMSE: <4 °C=0/5, 4-6 °C=0/5, >6 °C=5/5 (median 37.28 °C).
- Fixtures with ≥4/5 interior params: 1/5.
- x_core_depth_inferred in [30, 80] mm: 2/5 fixtures (range 19.5-65.9 mm).
- LOO subset (T1, T2 on 3 fixtures): T1 LOO-RMSE median 46.69 °C (3 fits), T2 LOO-RMSE median 40.73 °C (3 fits). Compare M9 Stefan 9.0-21.0 °C; M15 11.74 °C.
- Even with observed top BC and free α(T), the in-dough observation matrix does not constrain the model class. Method 4 (oven-setpoint metadata + tin/lid state at acquisition) is the unambiguous next step.

## Method

M15 → M16 reformulation: T_oven_eff (was a free parameter) is now extracted as T_air(t) directly from the M2a-flagged ambient sensor; Bi_top (was free) is replaced by h_eff(t) extracted from the surface energy balance `q ≈ -k_dough · ∂T/∂x` between surface and next-deeper sensor. α(T) is added as a piecewise function: α_pre at T<50°C, α_pre·alpha_ratio at T>65°C, linear in between. Pinned: k_dough=0.5 W/(m·K), Ko=4.0, ε=0.5, δ=2.0, α_pre=1.4×10⁻⁷ m²/s. Free parameters (5): L_m, D_m, Lu, q_bottom_eff, alpha_ratio.

## Phase 1 — Per-fixture observables diagnostic

| fixture | steam_dur(s) | spring_start(s) | spring_end(s) | T_air_min(°C) | T_air_max(°C) | h_eff_med(W/m²·K) |
|---|---|---|---|---|---|---|
| `BA3C_0946` | 0 | 535 | 815 | 23 | 154 | 9.1 |
| `BA3C_1759_C0` | 0 | 535 | 815 | 23 | 154 | 9.1 |
| `BA3C_1759_C1` | 0 | 550 | 780 | 36 | 144 | 7.9 |
| `BA3C_1759_C2` | 0 | 650 | 890 | 41 | 156 | 13.0 |
| `100098DE_1351` | 0 | 655 | 850 | 26 | 139 | 9.3 |
| `wonder_white` | 0 | 625 | 1000 | 29 | 99 | 20.1 |
| `post_wonder_meal` | 0 | 550 | 950 | 26 | 99 | 12.2 |

## Forward solver sanity

8-test pytest sub-suite (`tests/test_luikov_tin_observed_research.py`): **PASS** (returncode=0). Tests: alpha(T) profile (low/high/midband), constant-input baseline, alpha(T) evolution speed, steady-state convergence, time-varying input tracking, core-depth inference.

## Synthetic recovery (different α_pre generator)

Truth: L=95 mm, D=65 mm, Lu=0.1, q_bot=20.0, α_ratio=0.4. Generator α_pre=1.0e-7 m²/s; inverter α_pre=1.4e-7 m²/s. σ_noise=0.5 °C, 3 seeds. T_air(t) and h_eff(t) patterns sourced from BA3C_0946 observed.

| metric | value |
|---|---|
| n_runs | 3 |
| n_finite | 3 |
| RMSE median | 0.551 |
| RMSE max | 0.569 |
| L_m within 30% | 3/3 |
| D_m within 30% | 3/3 |
| Lu within 30% | 2/3 |
| q_bottom_eff within 30% | 3/3 |
| alpha_ratio within 30% | 3/3 |

Per-seed table:

| seed | L (mm) | D (mm) | Lu | q_bot | α_ratio | rmse | interior | s |
|---|---|---|---|---|---|---|---|---|
| 0 | 97.0 | 68.6 | 0.119 | 20.4 | 0.39 | 0.546 | 5/5 | 19.7 |
| 1 | 99.9 | 68.5 | 0.132 | 20.6 | 0.41 | 0.569 | 5/5 | 14.5 |
| 2 | 93.3 | 69.2 | 0.095 | 21.5 | 0.33 | 0.551 | 5/5 | 19.6 |

## Per-fixture real-CSV inverse results

| fixture | L (mm) | D (mm) | Lu | q_bot | α_ratio | x_core (mm) | RMSE_full | interior |
|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | ERR/no-conv | | | | | | | |
| `BA3C_1759_C0` | ERR/no-conv | | | | | | | |
| `BA3C_1759_C1` | 101.3 | 54.2 | 0.245 | 0.4 | 0.98 | 24.0 | 36.32 | 3/5 |
| `BA3C_1759_C2` | 60.0 | 54.2 | 0.165 | 22.8 | 0.72 | 30.5 | 32.68 | 3/5 |
| `100098DE_1351` | 65.9 | 54.0 | 0.003 | 0.2 | 0.53 | 65.9 | 44.54 | 2/5 |
| `wonder_white` | 67.8 | 67.8 | 0.028 | 29.6 | 0.23 | 19.5 | 43.19 | 4/5 |
| `post_wonder_meal` | 107.0 | 92.7 | 0.016 | 0.0 | 0.20 | 20.0 | 48.26 | 2/5 |

## Per-fixture residual decomposition (M10 helpers)

| fixture | RMSE_full | RMSE_main | RMSE_startup | RMSE_tail | ρ_main |
|---|---|---|---|---|---|
| `BA3C_0946` | (skipped) | | | | |
| `BA3C_1759_C0` | (skipped) | | | | |
| `BA3C_1759_C1` | 32.96 | 30.94 | 9.15 | 55.01 | 1.000 |
| `BA3C_1759_C2` | 29.42 | 26.77 | 7.35 | 52.68 | 1.000 |
| `100098DE_1351` | 40.03 | 38.30 | 6.19 | 64.67 | 0.999 |
| `wonder_white` | 38.81 | 37.28 | 4.90 | 62.21 | 1.000 |
| `post_wonder_meal` | 43.40 | 41.96 | 6.28 | 68.26 | 1.000 |

## Main-bake RMSE: Daring (M16) vs Sirius (M15) vs M9 Stefan

| fixture | Daring (M16) | Sirius (M15) | M9 Stefan |
|---|---|---|---|
| `BA3C_0946` | nan | 5.98 | 5.76 |
| `BA3C_1759_C0` | nan | 5.98 | 5.76 |
| `BA3C_1759_C1` | 30.94 | 6.23 | 6.80 |
| `BA3C_1759_C2` | 26.77 | 6.43 | 7.95 |
| `100098DE_1351` | 38.30 | nan | 7.49 |
| `wonder_white` | 37.28 | nan | 11.03 |
| `post_wonder_meal` | 41.96 | nan | 10.55 |

## Bound-hitting (per-parameter, per-fixture)

| fixture | L_m | D_m | Lu | q_bottom_eff | alpha_ratio |
|---|---|---|---|---|---|
| `BA3C_0946` | interior | interior | hi | interior | interior |
| `BA3C_1759_C0` | interior | interior | hi | interior | interior |
| `BA3C_1759_C1` | interior | lo | interior | lo | interior |
| `BA3C_1759_C2` | lo | lo | interior | interior | interior |
| `100098DE_1351` | interior | lo | lo | lo | interior |
| `wonder_white` | interior | interior | lo | interior | interior |
| `post_wonder_meal` | interior | interior | lo | lo | lo |

## LOO subset (deep-end T1, T2 on 3 representative fixtures)

M15 T1 LOO median: 11.74 °C. M9 Stefan range: 9.0-21.0 °C.

| fixture | held_out | LOO_rmse | in_sample | ratio | max&#124;res&#124; | mean_res | x_core (mm) | interior | s |
|---|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | T1 | 28.98 | 29.74 | 0.97 | 59.4 | -22.02 | 107.5 | 4/5 | 281.9 |
| `BA3C_0946` | T2 | 29.64 | 29.45 | 1.01 | 57.1 | -23.77 | 108.9 | 3/5 | 299.6 |
| `100098DE_1351` | T1 | 46.69 | 42.29 | 1.10 | 68.6 | -40.04 | 62.1 | 3/5 | 29.9 |
| `100098DE_1351` | T2 | 40.73 | 43.80 | 0.93 | 67.1 | -32.76 | 61.7 | 2/5 | 38.9 |
| `wonder_white` | T1 | 52.22 | 39.70 | 1.32 | 69.9 | -47.59 | 17.3 | 3/5 | 78.2 |
| `wonder_white` | T2 | 43.74 | 42.15 | 1.04 | 67.8 | -37.39 | 14.8 | 3/5 | 27.7 |

## Recommendation for production

Even with observed top BC and a free α(T) profile, the in-dough-only observation matrix does not pin the deep-end response or the full parameter space. The information limit confirmed by M15 is now reaffirmed at half the parameter count. Method 4 — per-CSV loaf-thickness, oven-setpoint, tin/lid metadata — is the only remaining structural lever.
