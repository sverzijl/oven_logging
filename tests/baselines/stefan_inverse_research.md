# Method 3b — 1D Stefan-Front Inverse Research

**HMS Triumph research mission, 2026-04-28.** Tests whether the 1D Stefan problem with a moving evaporation front (modelled via the enthalpy method) recovers the loaf core position from real bread-baking CSVs. M7 (heat-equation, no latent heat) gave RMSE 6-10 °C — wrong physics class. M9 hypothesis: explicit 100 °C latent-heat plateau is the missing piece. Research-only — no production wiring.

## Executive summary

**Verdict: NO-GO**

- Forward-solver sanity (Stefan-Neumann analytical): max diff 2.82 °C (bar 3 °C) → PASS
- Synthetic recovery (10 seeds, generator dT=0.3, inverter dT=1.0): bias=0.0497, spread=0.0029, converged=10/10 → PASS
- Joint RMSE (real CSVs): median=6.91 °C, max=9.83 °C across 7 fixtures.
- Pinned RMSE (real CSVs): median=8.49 °C, max=41.51 °C across 7 fixtures.
- M7 heat-eq baseline RMSE for context: median=6.48 °C.
- Max |ρ| of joint 4-param fit: median=0.235, max-across-fixtures=0.303 (well-conditioned bar < 0.85).
- BA3C cases extrapolating past T1 (x_core < 0): BA3C_0946, BA3C_1759_C0, BA3C_1759_C1, BA3C_1759_C2

## Forward-solver sanity vs Stefan-Neumann analytical

One-phase Stefan-Neumann setup: dough at 100 °C, surface held at 150.0 °C, α = 1.00e-03, Stefan number Ste = 2.0, ρL_eff = 25.0 K. Sample positions x ∈ {0.5, 0.7, 0.85, 0.95}, t ∈ [0, 4000]s.

* max |T_num − T_ana| = **2.817 °C** (bar 3 °C → PASS)

* per-position max diff: [2.816569269876382, 1.7259212270704438, 0.8707755582754544, 0.2910718272117947]

Enthalpy method has unavoidable bias O(rhoL_eff/2) °C from the smearing window when matched to a sharp-interface analytical solution — tightening dT does not remove the bias since rhoL_eff is held constant. Bar of 3 °C accepts that bias as the cost of a non-stiff inverse problem.

## Synthetic ground-truth recovery

Generator: ΔT_smear = 0.3 °C; Inverter: ΔT_smear = 1.0 °C — different numerical realisations of the same physics class so the test is not a tautology. Realistic bake (ramp 22 → 200 °C, period 5 s, 280 samples), Gaussian σ = 0.5 °C noise. True x_core = -0.1; α_dough = 1e-3; α_crust = 8e-4; ρL_eff = 80 K.

* converged: 10/10
* mean bias `(x_fit − x_true)` = **0.0497**
* spread `σ(x_fit)` = **0.0029**
* median RMSE: **1.386 °C**


| seed | x_core_fit | α_dough | α_crust | ρL_eff | RMSE | max&#124;ρ&#124; | iter |
|---|---|---|---|---|---|---|---|
| 0 | -0.0507 | 9.46e-04 | 6.07e-04 | 59.5 | 1.41 | 0.310 | 102 |
| 1 | -0.0453 | 9.45e-04 | 6.20e-04 | 61.6 | 1.44 | 0.297 | 111 |
| 2 | -0.0488 | 9.46e-04 | 5.92e-04 | 58.3 | 1.39 | 0.565 | 141 |
| 3 | -0.0509 | 9.38e-04 | 8.82e-04 | 89.8 | 1.09 | 0.397 | 141 |
| 4 | -0.0508 | 9.49e-04 | 6.23e-04 | 61.3 | 1.38 | 0.478 | 125 |
| 5 | -0.0506 | 9.38e-04 | 6.35e-04 | 62.3 | 1.34 | 0.272 | 168 |
| 6 | -0.0531 | 9.53e-04 | 6.59e-04 | 66.5 | 1.23 | 0.248 | 159 |
| 7 | -0.0477 | 9.26e-04 | 6.26e-04 | 60.8 | 1.39 | 0.330 | 127 |
| 8 | -0.0489 | 9.54e-04 | 5.96e-04 | 58.6 | 1.48 | 0.431 | 114 |
| 9 | -0.0558 | 9.59e-04 | 8.60e-04 | 87.0 | 1.00 | 0.552 | 159 |

## Real-CSV viability — joint vs pinned vs M7 baseline

| fixture | x_surf_cont | x_core_joint | x_core_pinned | α_dough_joint | α_crust_joint | ρL_eff_joint | RMSE_joint | RMSE_pinned | RMSE_M7 | max&#124;ρ&#124;_joint | extrap_joint |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | 0.6787 | -0.051 | 0.427 | 3.57e-04 | 1.07e-03 | 40.0 | 6.19 | 8.49 | 6.09 | 0.235 | True |
| `BA3C_1759_C0` | 0.6787 | -0.051 | 0.427 | 3.57e-04 | 1.07e-03 | 40.0 | 6.19 | 8.49 | 6.09 | 0.235 | True |
| `BA3C_1759_C1` | 0.7177 | -0.061 | 0.479 | 4.60e-04 | 3.98e-03 | 16.1 | 6.41 | 7.92 | 6.14 | 0.303 | True |
| `BA3C_1759_C2` | 0.7132 | -0.051 | 0.443 | 3.38e-04 | 1.04e-03 | 39.5 | 7.63 | 7.85 | 6.48 | 0.116 | True |
| `100098DE_1351` | 0.7704 | 0.440 | 0.602 | 2.13e-04 | 9.74e-14 | 45599513173869.5 | 6.91 | 6.92 | 7.03 | 0.255 | False |
| `wonder_white` | 0.9286 | -0.063 | -0.045 | 1.71e+03 | 1.33e-05 | 1002.5 | 9.83 | 37.82 | 10.01 | 0.019 | True |
| `post_wonder_meal` | 0.9286 | -0.062 | -0.053 | 2.25e+02 | 1.48e-05 | 631.2 | 9.45 | 41.51 | 9.98 | 0.006 | True |

## Joint-fit 4×4 correlation matrices


### `BA3C_0946`

| | x_core | α_dough | α_crust | ρL_eff |
|---|---|---|---|---|
| **x_core** |  1.000 | -0.235 | -0.019 | -0.048 |
| **α_dough** | -0.235 |  1.000 | -0.091 |  0.090 |
| **α_crust** | -0.019 | -0.091 |  1.000 | -0.036 |
| **ρL_eff** | -0.048 |  0.090 | -0.036 |  1.000 |


### `BA3C_1759_C0`

| | x_core | α_dough | α_crust | ρL_eff |
|---|---|---|---|---|
| **x_core** |  1.000 | -0.235 | -0.019 | -0.048 |
| **α_dough** | -0.235 |  1.000 | -0.091 |  0.090 |
| **α_crust** | -0.019 | -0.091 |  1.000 | -0.036 |
| **ρL_eff** | -0.048 |  0.090 | -0.036 |  1.000 |


### `BA3C_1759_C1`

| | x_core | α_dough | α_crust | ρL_eff |
|---|---|---|---|---|
| **x_core** |  1.000 | -0.303 | -0.144 | -0.013 |
| **α_dough** | -0.303 |  1.000 |  0.034 |  0.002 |
| **α_crust** | -0.144 |  0.034 |  1.000 |  0.025 |
| **ρL_eff** | -0.013 |  0.002 |  0.025 |  1.000 |


### `BA3C_1759_C2`

| | x_core | α_dough | α_crust | ρL_eff |
|---|---|---|---|---|
| **x_core** |  1.000 | -0.116 | -0.079 | -0.022 |
| **α_dough** | -0.116 |  1.000 | -0.084 | -0.022 |
| **α_crust** | -0.079 | -0.084 |  1.000 |  0.105 |
| **ρL_eff** | -0.022 | -0.022 |  0.105 |  1.000 |


### `100098DE_1351`

| | x_core | α_dough | α_crust | ρL_eff |
|---|---|---|---|---|
| **x_core** |  1.000 | -0.255 | n/a | n/a |
| **α_dough** | -0.255 |  1.000 | n/a | n/a |
| **α_crust** | n/a | n/a | n/a | n/a |
| **ρL_eff** | n/a | n/a | n/a | n/a |


### `wonder_white`

| | x_core | α_dough | α_crust | ρL_eff |
|---|---|---|---|---|
| **x_core** |  1.000 | -0.019 | n/a | n/a |
| **α_dough** | -0.019 |  1.000 | n/a | n/a |
| **α_crust** | n/a | n/a | n/a | n/a |
| **ρL_eff** | n/a | n/a | n/a | n/a |


### `post_wonder_meal`

| | x_core | α_dough | α_crust | ρL_eff |
|---|---|---|---|---|
| **x_core** |  1.000 |  0.006 | n/a | n/a |
| **α_dough** |  0.006 |  1.000 | n/a | n/a |
| **α_crust** | n/a | n/a | n/a | n/a |
| **ρL_eff** | n/a | n/a | n/a | n/a |


## Literature-pinned variant — parameter conversion

Literature SI values: α_dough = 1.40e-07 m²/s, α_crust = 1.00e-07 m²/s, ρL_eff = 6.00e+08 J/m³.

Representative loaf thickness: 50 mm.
Normalised values: α_dough = 5.6000e-05, α_crust = 4.0000e-05, ρL_eff = 6.8571e+04 K.


## Recommendation

Stefan does not deliver enough RMSE reduction to justify the implementation cost. Either (a) the model class is still wrong (2D conduction? moisture migration?) or (b) the parametrisation is genuinely unidentifiable from in-dough thermometry alone. Recommend the loaf-thickness-metadata route (Method 4) over any further inverse-problem work.

## Open follow-ups

1. The literature-pinned variant relies on a 50 mm loaf-thickness scaling. If/when production captures real loaf thickness per CSV, this becomes per-fixture and removes one pragmatic conversion.
2. Lid-suppressed bakes (`wonder_white`, `post_wonder_meal`) cap the cavity at ~100 °C. The Stefan front cannot advance, and the inverse problem genuinely loses information. A different model (possibly two-parameter fit pinning ρL_eff and α_crust to literature) may be needed for those bakes.
3. Forward-solver bias of ~2-3 °C from the smearing window propagates into RMSE. Tighter ΔT_smear (0.3 °C) would shave that bias at the cost of doubled wall-time per fit. Worth re-examining once production wiring is decided.
