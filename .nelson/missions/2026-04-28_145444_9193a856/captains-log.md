# Captain's log — HMS Daring, M16 Luikov OBSERVED-BC inverse

**Mission:** Reformulate M15 with observed T_air(t) and h_eff(t) (replacing fitted T_oven_eff and Bi_top), add α(T) piecewise profile, and halve the parameter count (4-5 free params vs M15's 8).

**Branch:** `refactor/role-classification-unified`  
**Mission dir:** `.nelson/missions/2026-04-28_145444_9193a856`  
**Date:** 2026-04-28 (M16)  
**Wall-clock:** 1583.7 s end-to-end.

## Verdict: **CONFIRM-information-limit**

- Forward sanity: 8-test pytest sub-suite PASS (returncode=0).
- Synthetic recovery (different α_pre: gen 1.0e-7 vs inv 1.4e-7; 3/3 runs finite, σ_noise=0.5 °C, 3 seeds): RMSE median 0.551 °C; L_m within 30%=3/3; D_m within 30%=3/3; Lu within 30%=2/3; q_bot within 30%=3/3; α_ratio within 30%=3/3.
- Real-CSV 4-5 param convergence: 5/7.
- Main-bake RMSE: <4 °C=0/5, 4-6 °C=0/5, >6 °C=5/5 (median 37.28 °C).
- Fixtures with ≥4/5 interior params: 1/5.
- x_core_depth_inferred in [30, 80] mm: 2/5 fixtures (range 19.5-65.9 mm).
- LOO subset (T1, T2 on 3 fixtures): T1 LOO-RMSE median 46.69 °C (3 fits), T2 LOO-RMSE median 40.73 °C (3 fits). Compare M9 Stefan 9.0-21.0 °C; M15 11.74 °C.
- Even with observed top BC and free α(T), the in-dough observation matrix does not constrain the model class. Method 4 (oven-setpoint metadata + tin/lid state at acquisition) is the unambiguous next step.

## Phase 1 observables diagnostic

| fixture | steam? | spring_window | T_air range | h_eff median |
|---|---|---|---|---|
| `BA3C_0946` | no | 535-815s | 23-154°C | 9.1 |
| `BA3C_1759_C0` | no | 535-815s | 23-154°C | 9.1 |
| `BA3C_1759_C1` | no | 550-780s | 36-144°C | 7.9 |
| `BA3C_1759_C2` | no | 650-890s | 41-156°C | 13.0 |
| `100098DE_1351` | no | 655-850s | 26-139°C | 9.3 |
| `wonder_white` | no | 625-1000s | 29-99°C | 20.1 |
| `post_wonder_meal` | no | 550-950s | 26-99°C | 12.2 |

## Per-fixture x_core_depth_inferred

| fixture | x_core_inferred (mm) | L_m fitted (mm) | D_m fitted (mm) | α_ratio fitted |
|---|---|---|---|---|
| `BA3C_0946` | (no fit) | | | |
| `BA3C_1759_C0` | (no fit) | | | |
| `BA3C_1759_C1` | 24.0 | 101.3 | 54.2 | 0.98 |
| `BA3C_1759_C2` | 30.5 | 60.0 | 54.2 | 0.72 |
| `100098DE_1351` | 65.9 | 65.9 | 54.0 | 0.53 |
| `wonder_white` | 19.5 | 67.8 | 67.8 | 0.23 |
| `post_wonder_meal` | 20.0 | 107.0 | 92.7 | 0.20 |

## Did observed-BC reformulation help vs M15?

| fixture | Daring (M16) | Sirius (M15) | M9 Stefan |
|---|---|---|---|
| `BA3C_0946` | nan | 5.98 | 5.76 |
| `BA3C_1759_C0` | nan | 5.98 | 5.76 |
| `BA3C_1759_C1` | 30.94 | 6.23 | 6.80 |
| `BA3C_1759_C2` | 26.77 | 6.43 | 7.95 |
| `100098DE_1351` | 38.30 | nan | 7.49 |
| `wonder_white` | 37.28 | nan | 11.03 |
| `post_wonder_meal` | 41.96 | nan | 10.55 |

## LOO T1 deep-end test

T1 LOO-RMSE (M16): median 46.69 °C, max 52.22 °C, n=3.  Compare M9 Stefan 9.0-21.0 °C; M15 11.74 °C.

## Open follow-ups

- Information limit reaffirmed at half the parameter count of M15. The hierarchy single-medium → Stefan → Zürcher → Luikov-symmetric → Luikov-asymmetric-tin (M15) → Luikov-observed-BC (M16) has been exhausted on the in-dough-only observation matrix.
- **Method 4** is now the only remaining structural lever: capture per-CSV loaf thickness, oven setpoint, tin/lid contact state at acquisition time; include surface-sensor signal in inverse loss. Pivot away from inverse-problem research on this data alone.
