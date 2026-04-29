# HMS Kent — RCA synthesis (M19, Task 4)

## 1. Three reports' verdicts

- **Audacious (bake-time-to-physics audit):** alpha is the systematic bug. A 22-25 min bake requires alpha_eff in (4e-7, 3e-6) m^2/s; M9/M11/M12/M14/M15 used 1.0-1.4e-7 (5-7x too low); M17 freed alpha_pre and rail-pinned at the 5e-6 cap — empirical confirmation that literature alpha cannot reproduce the bake.
- **Active (M9 residual shape on BA3C_0946):** residuals are NOT noise (lag-1 rho=0.99) and NOT a uniform alpha bias (signs flip with depth: T1 over-heated by 14 deg C at 14 min, T2/T3 stuck on the 100 deg C plateau by +13/+10 deg C at ~21 min). Stefan-front propagation profile is wrong; constant-alpha + thin smear (delta_T_smear=1.0) cannot match both fast core warm-up and extended mid-depth plateau.
- **Diamond (bake-data sanity):** 4/7 fixtures (unlidded BA3C/100098DE, 23.3-25.3 min, surface_max 105-112 deg C) match user's 22-25 min band; 2/7 (lidded wonder_white/post_wonder_meal, 28.3-28.4 min, surface_max ~98 deg C) do not — they're a different boundary-condition cohort. Lumping them is a heterogeneous-data bug.

## 2. Cross-reference table

| Report | alpha | Boundary condition | Geometry / x_positions | Residual shape |
|---|---|---|---|---|
| Audacious | **5-7x too low** in M9/M14/M15; M17 rail-pinned at upper cap (smoking gun) | not in scope | L=50-65 mm one-sided slab; alpha quadratic in L (30% L error doubles alpha) | not analysed |
| Active | not a uniform bias (signs flip) — implies alpha needs T- or x-dependence, OR thin Stefan smear too narrow | surface BC fine (T4/T5 RMSE 1.7-4.2 deg C) | secondary suspicion of x-position mismatch | depth-dependent; rho=0.99; 5.4x RMSE spread T1->T5 |
| Diamond | not in scope | **two cohorts** (lidded vs unlidded); single BC cannot fit both | probe sensor picks differ per fixture (T1 vs T4 vs T5 as core) | not analysed |

## 3. Root cause

**Primary: effective alpha (and the latent-heat smear that controls front sharpness) is wrong.** Backed by Audacious (independent dimensional argument: bake time + slab geometry => alpha must be ~8e-7, not 1.4e-7) AND Active (M9 residuals on the cleanest fixture show a Stefan-front-shape failure that is exactly what a too-low alpha + too-narrow smear produces — slow front below T1, pinned plateau at T2/T3). M17 already freed alpha_pre and ran straight to the 5e-6 ceiling, empirically confirming the audit.

Secondary (Diamond, orthogonal): lidded cohort is a different BC regime. Real but lower-leverage — only 2/7 fixtures, and BA3C_0946 (the 5.76 deg C benchmark) is unlidded, so this is not the M9 main-bake bottleneck.

## 4. Concrete next mission

**M20 — re-run M9 on the unlidded cohort only with alpha_dough freed and smear widened.**

Specific changes (one config patch, one fit run):

1. In the M9 Stefan fitter config: free `alpha_dough` over (5e-7, 1e-5) m^2/s (NOT pinned at 1.4e-7, NOT capped at 5e-6); free `delta_T_smear` over (3.0, 10.0) deg C (currently 1.0, hard).
2. Restrict the fit cohort to the four unlidded fixtures: BA3C_0946, BA3C_1759_C0/C1/C2, plus 100098DE_1351 (5 curves). Defer wonder_white_10k and post_wonder_meal_20251017 to a separate lidded-BC mission.
3. Keep `rhoL_eff`, `x_core`, `x_surface`, `T_init` free as in current M9; do not re-parametrise.
4. Acceptance: BA3C_0946 main-bake RMSE < **4.0 deg C** (down from 5.76); per-sensor RMSE max/min ratio < 2.5 (down from 5.37); T1 peak |residual| < 7 deg C (down from 14.3).

## 5. Estimated impact

The two largest residual contributions on BA3C_0946 are T1 (-14.3 deg C peak, RMSE 9.05 main) and T2 (+12.7 peak, RMSE 6.79). Both are direct symptoms of front-propagation shape — exactly what freeing alpha + widening smear addresses. Halving each cuts overall RMSE roughly from 5.76 to 3.0-3.5 deg C. Plausible target: **3.0-4.0 deg C** on BA3C_0946. Audacious estimates alpha settling at 6e-7-3e-6 (fixture-specific) which independently supports this magnitude.

## 6. Stand-down condition

If M20 cannot get BA3C_0946 main-bake RMSE below **4.0 deg C** with both alpha and delta_T_smear free on the unlidded cohort, the physics inverse is unrecoverable at this level of model fidelity. Pivot to **Method 4 (metadata capture)**: log oven setpoint, lid state, loaf height, and probe insertion depth per bake, drop the inverse-fit physics, and ship a forward simulator parameterised by recorded metadata + a per-fixture residual correction. Do not commission M21+ on yet another physics reformulation.
