# HMS Active M19/T2 - M9 residual shape on BA3C_0946

- Fixture: BA3C_0946 (cleanest unlidded; M9 main-bake RMSE 5.76 deg C).
- M9 cached params: alpha_dough=3.570e-04 m^2/s, alpha_crust=1.065e-03 m^2/s, rhoL_eff=40.0, x_core=-0.0513, x_surface=0.6787, T_init=29.3 deg C.
- Residual sign convention: r = T_observed - T_predicted (positive = model under-predicts).
- Total n_t=71, in-dough sensors=['T1', 'T2', 'T3', 'T4', 'T5'] (5 in-dough out of 8).
- Recomputed full RMSE = 6.19 deg C (M9 cache reports 6.19 for sanity check).

## Per-sensor residual statistics

| sensor | RMSE (full) | RMSE (main 10-90%) | mean | std | peak |r| | lag-1 rho | t_peak (min) | T_obs@peak | T_pred@peak |
|---|---|---|---|---|---|---|---|---|---|
| T1 | 9.30 | 9.05 | +0.13 | 9.30 | -14.32 | 0.994 | 14.0 | 45.6 | 59.9 |
| T2 | 7.35 | 6.79 | +1.17 | 7.26 | +12.69 | 0.993 | 21.0 | 93.8 | 81.1 |
| T3 | 5.48 | 4.91 | +1.39 | 5.30 | +9.71 | 0.990 | 20.7 | 94.0 | 84.2 |
| T4 | 4.24 | 4.20 | -0.18 | 4.23 | -8.31 | 0.984 | 7.7 | 46.5 | 54.8 |
| T5 | 1.73 | 1.63 | -0.43 | 1.68 | +4.65 | 0.788 | 0.3 | 34.0 | 29.4 |

## Aggregate diagnostics

- |mean|/std ratio (mean across sensors): **0.15** (>0.5 = bias-dominated, structured; <0.2 = approx zero-mean noise).
- lag-1 autocorr median across sensors: **0.990**, max |rho|: **0.994** (>0.6 = strong temporal structure; <0.3 = noise-like).
- Per-sensor RMSE spread: min=1.73, max=9.30, max/min ratio=5.37 (>2 = depth-dependent shape mismatch).
- Mean residual signs: 3 sensors positive, 2 negative (all-positive => model systematically under-predicts; mixed => spatial pattern).

## Residual signature

**(c) Different per-sensor residual shapes** -- per-sensor mean residuals: T1=+0.13, T2=+1.17, T3=+1.39, T4=-0.18, T5=-0.43. Per-sensor RMSE ranges 1.73 to 9.30 deg C, a 5.4x spread. lag-1 autocorr median=0.990 (strong temporal structure). The residual is NOT zero-mean noise; its shape depends on sensor depth, indicating a spatial-profile bug (wrong x positions, wrong alpha, or missing 1D->multi-D physics).

## Actionable finding (one)

The residual is **not** noise. lag-1 autocorr=0.99 across all sensors, RMSE spreads 5.4x with depth (T1=9.3 deg C deepest, T5=1.7 deg C near-surface), and the SIGN of the deviation flips between depth bins:

- **Deep sensor T1** (x ~ 0.0, near core): worst residual **-14.3 deg C at 14 min** (T_obs=45.6, T_pred=59.9). The model **heats T1 too fast** during the rise.
- **Mid sensors T2, T3** (x ~ 0.14, 0.29; the latent-plateau zone): worst residuals **+13 / +10 deg C at ~21 min** (T_obs ~ 94, T_pred ~ 81-84). Once the front passes T1, the model **stays stuck on the 100 deg C plateau too long** at T2/T3 -- the smear is too wide / front motion is too slow there.
- **Near-surface T4, T5**: small residuals; surface BC and crust diffusivity are fine.

This is **NOT a uniform alpha bias** (signs flip) and **NOT noise** (rho=0.99). It is the **Stefan-front propagation profile** that is wrong. Concretely: M9's single-alpha_dough + single rhoL_eff cannot simultaneously match (i) fast core warm-up and (ii) extended mid-depth plateau. Either alpha effectively varies with x (or with T), or the latent-heat smear delta_T_smear=1.0 is too narrow and the front propagates too fast through the deep dough.

**One specific change** -- replace the constant alpha_dough with a temperature-dependent alpha(T) that drops sharply at T -> 100 deg C (i.e. fold the latent-heat sink into an effective-diffusivity dip rather than a thin Stefan front), or equivalently widen delta_T_smear from 1.0 deg C to ~5-10 deg C. This will (a) slow the front below T1 (cuts the -14 deg C T1 residual), and (b) allow T2/T3 to climb past 100 deg C earlier instead of being pinned (cuts the +13 / +10 deg C mid-depth residuals). Both biases are the dominant share of each sensor's RMSE; closing them more than halves the 6.2 deg C overall.

Secondary: re-derive sensor x-positions thermodynamically (the |residual| pattern with depth also leaves room for nominal-vs-actual probe-geometry mismatch), but the temperature-direction bias above is the bigger lever.

## Worst-residual time windows per sensor

| sensor | t at peak |r| (min) | T_obs (deg C) | T_pred (deg C) | residual (deg C) |
|---|---|---|---|---|
| T1 | 14.0 | 45.6 | 59.9 | -14.32 |
| T2 | 21.0 | 93.8 | 81.1 | +12.69 |
| T3 | 20.7 | 94.0 | 84.2 | +9.71 |
| T4 | 7.7 | 46.5 | 54.8 | -8.31 |
| T5 | 0.3 | 34.0 | 29.4 | +4.65 |
