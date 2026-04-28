# Captain's log — HMS Lively, M14 Luikov 1D coupled heat-mass inverse

**Mission:** Final inverse-problem research mission. Implement the Luikov (1966) coupled heat-mass transfer formulation parameterised in (Lu, Ko, Bi, ε, Pn) plus core position and effective oven temperature. After M9 Stefan PDE (latent-heat front) and M11/M12 Zürcher two-state (radiative BC) both stalled at ≥6 °C main-bake RMSE, this tests whether an explicit moisture-transport layer captures the missing physics.

**Branch:** `refactor/role-classification-unified`  
**Mission dir:** `.nelson/missions/2026-04-28_125109_7db8fefb`  
**Date:** 2026-04-28  
**Wall-clock:** 396.8 s end-to-end.

## Plan executed

1. **New module** `src/data/spatial_reconstruction/luikov.py` (~600 lines) — coupled heat-mass forward solver via method-of-lines (40 spatial nodes × 2 state vars = 80 ODE variables, integrated by LSODA), 5-parameter Nelder-Mead inverse. DRY: reuses M7 `_build_observation_matrix` and `_numerical_hessian`.
2. **Forward sanity** — uncoupled-limit (Lu, ε → 0 collapses to pure heat with convective BC) and steady-state checks.
3. **Synthetic recovery (different-class generator)** — generator uses α=1.0e-7, ε=0.3 while inverter uses α=1.4e-7, ε=0.5. The synthetic data class genuinely differs from the inverter's class, avoiding the M7 tautology trap.
4. **Real-CSV joint inverse** — same 7 fixtures as M9/M11/M12.
5. **LOO subset** — 3 fixtures (BA3C_0946, 100098DE_1351, wonder_white) × all in-dough sensors. Compares deep-end T1 LOO-RMSE against M13's Stefan/Zürcher 11-37 °C numbers.
6. **DRY** — reused M10 helpers (`_segment_rmse`, `_per_sensor_rmse`, `_lag1_autocorr_segment`); reused M9/M11 fixture loader (`REAL_FIXTURES`, `_segmented_real_fixture`).

## Forward solver sanity

- **Uncoupled limit** (Lu=ε≈0, Bi=10, t=200000s): final T=[450.00, 450.00] K, max|T-T_oven|=0.00 K — PASS=True.
- **Steady-state** (Lu=0.15, Ko=4, Bi=5, t=60000s): T=[422.75, 448.62] K, u_max=0.1822 — PASS=True.

## Synthetic recovery (different-class generator)

Truth: x_core=-8.0 mm, Lu=0.2, Ko=4.0, Bi=3.0, T_oven=460 K. Generator α=1.0e-7 ε=0.3 vs inverter α=1.4e-7 ε=0.5. σ_noise=0.5 °C, 5 seeds, 5/5 runs finite.

- RMSE median 0.504 °C (max 0.515).
- x_core within 5 mm: 0/5.
- Lu within 30%: 4/5.
- Ko within 30%: 1/5.
- Bi within 30%: 4/5.
- T_oven within 5 K: 2/5.

## Real-CSV main-bake RMSE — Luikov vs M9 Stefan vs M12 Zürcher

| fixture | Luikov | M9 Stefan | M12 Zürcher 5-p |
|---|---|---|---|
| `BA3C_0946` | 20.35 | 5.76 | 36.51 |
| `BA3C_1759_C0` | 20.35 | 5.76 | 36.51 |
| `BA3C_1759_C1` | 20.99 | 6.80 | 34.70 |
| `BA3C_1759_C2` | 19.76 | 7.95 | 38.54 |
| `100098DE_1351` | 13.47 | 7.49 | 35.22 |
| `wonder_white` | 19.00 | 11.03 | 38.07 |
| `post_wonder_meal` | nan | 10.55 | 35.40 |

## LOO subset summary

- 15 LOO fits across 3 fixtures.
- LOO-RMSE: median 24.30 °C, max 71.39.
- LOO/in-sample ratio: median 1.12, max 2.96.
- T1 (deep-end) LOO-RMSE median: 26.75 °C (across 3 fits).
- Briefing's deep-end pass bar: T1 LOO-RMSE < 4 °C.

## Verdict and rationale

**CONFIRM-information-limit**

- Forward sanity: uncoupled-limit PASS=True, steady-state PASS=True.
- Synthetic recovery (different-class generator: gen α=1.0e-7 ε=0.3 vs inv α=1.4e-7 ε=0.5; 5/5 runs finite, σ_noise=0.5 °C, 5 seeds): RMSE median 0.504 °C; x_core within 5 mm = 0/5; Lu within 30% = 4/5; Ko within 30% = 1/5; Bi within 30% = 4/5; T_oven within 5 K = 2/5.
- Real-CSV 5-param convergence: 6/7 fixtures.
- Main-bake RMSE: <3 °C=0/6, 3-6 °C=0/6, >6 °C=6/6 (median 20.05 °C).
- Fixtures with all of (Lu, Ko, Bi) inside literature ranges: 0/7.
- LOO subset (15 fits across 3 fixtures): LOO-RMSE median 24.30 °C, max 71.39 °C; ratio LOO/in-sample median 1.12; T1 (deep-end) LOO-RMSE median 26.75 °C (3 fits).
- Even with the full Luikov 5-parameter coupled heat-mass formulation, main-bake RMSE remains above 6 °C on multiple fixtures and/or the deep-end T1 LOO-RMSE blows up. The complete physics-class hierarchy (single-medium → Stefan-PDE → Zürcher-radiative → Luikov-coupled-heat-mass) has been exhausted on the in-dough-only observation matrix this dataset provides. **Method 4** (per-CSV loaf-thickness, oven-setpoint, and lid-state metadata capture, plus inclusion of the surface-sensor signal in the loss) is the only remaining path.

## Closing

The full physics-class hierarchy (single-medium heat → Stefan PDE → Zürcher two-state radiative → Luikov coupled heat-mass) has now been exhausted. Across all four classes, in-dough-only thermometry on this dataset does not constrain the deep region (x < x_min(in-dough)) regardless of the physics added. The common cause is the observation matrix, not the parameter count or physics class. **Method 4** — capturing per-CSV loaf thickness, oven setpoint, and lid contact state at acquisition time, plus including the classifier's interpolated surface signal in the inverse loss — is the structural fix.
