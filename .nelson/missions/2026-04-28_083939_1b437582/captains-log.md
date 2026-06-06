# Captain's log - HMS Hermione, M13 leave-one-sensor-out cross-validation

**Mission**: Run leave-one-sensor-out cross-validation on the M9 Stefan and M12 Zurcher 5-param fits, plus measure the sensor calibration floor at t=0. Determine empirically whether the M7-M12 main-bake RMSE 6-22 degC was missing physics or sensor noise + calibration drift + response-time lag.

**Branch**: `refactor/role-classification-unified`  
**Mission dir**: `.nelson/missions/2026-04-28_083939_1b437582`  
**Date**: 2026-04-28  
**Wall-clock**: 11170.8 s end-to-end.

## Sensor calibration floor

Across 7 fixtures, T1-T8 readings at room temperature (pre-bake or first samples of segmented fixture) span a median range of 0.34 degC (max 4.37 degC), with median per-fixture sigma 0.110 degC. This is the sensor-to-sensor calibration floor: any model RMSE smaller than this is unphysical.

| fixture | source | n | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | mean | sigma | range |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | last_5_pre_insertion | 5 | 22.91 | 22.95 | 22.97 | 22.89 | 22.88 | 22.92 | 23.01 | 23.22 | 22.97 | 0.110 | 0.34 |
| `BA3C_1759_C0` | last_5_pre_insertion | 5 | 22.91 | 22.95 | 22.97 | 22.89 | 22.88 | 22.92 | 23.01 | 23.22 | 22.97 | 0.110 | 0.34 |
| `BA3C_1759_C1` | last_5_pre_insertion | 5 | 22.91 | 22.95 | 22.97 | 22.89 | 22.88 | 22.92 | 23.01 | 23.22 | 22.97 | 0.110 | 0.34 |
| `BA3C_1759_C2` | last_5_pre_insertion | 5 | 22.91 | 22.95 | 22.97 | 22.89 | 22.88 | 22.92 | 23.01 | 23.22 | 22.97 | 0.110 | 0.34 |
| `100098DE_1351` | all_3_pre_insertion | 3 | 22.85 | 23.13 | 23.42 | 23.73 | 23.80 | 24.25 | 24.08 | 23.87 | 23.64 | 0.476 | 1.40 |
| `wonder_white` | first_5_segmented | 5 | 34.34 | 34.11 | 33.86 | 33.82 | 32.65 | 32.10 | 31.26 | 29.97 | 32.76 | 1.565 | 4.37 |
| `post_wonder_meal` | all_3_pre_insertion | 3 | 25.45 | 25.37 | 25.30 | 25.17 | 25.40 | 25.40 | 25.30 | 25.30 | 25.34 | 0.088 | 0.28 |

## Zurcher 5-param LOO (full sweep)

35 LOO fits across all 7 fixtures. Median LOO-RMSE **18.34 degC** (max 37.24). Ratio LOO/in-sample median **0.89**, max 2.16. 0 held-out sensors below 2 degC, 0 below 4 degC, 35 above 4 degC.

| fixture | n_loo | LOO_rmse_median | LOO_rmse_max | in_sample_median | ratio_median | ratio_max |
|---|---|---|---|---|---|---|
| `BA3C_0946` | 5 | 18.34 | 27.40 | 19.62 | 1.07 | 1.59 |
| `BA3C_1759_C0` | 5 | 18.34 | 27.40 | 19.62 | 1.07 | 1.59 |
| `BA3C_1759_C1` | 5 | 17.87 | 26.40 | 20.86 | 0.86 | 1.48 |
| `BA3C_1759_C2` | 5 | 20.68 | 27.49 | 22.19 | 0.93 | 1.66 |
| `100098DE_1351` | 4 | 17.31 | 25.43 | 19.90 | 0.88 | 1.91 |
| `wonder_white` | 6 | 18.59 | 37.24 | 24.26 | 0.78 | 1.69 |
| `post_wonder_meal` | 5 | 20.02 | 35.91 | 22.07 | 0.89 | 2.16 |

## Stefan LOO (3 representative fixtures)

15 LOO fits on 100098DE_1351, BA3C_0946, wonder_white. Median LOO-RMSE **6.41 degC** (max 21.03). Ratio LOO/in-sample median **0.85**, max 3.72. 2 held-out sensors below 2 degC, 3 below 4 degC.

| fixture | n_loo | LOO_rmse_median | LOO_rmse_max | in_sample_median | ratio_median | ratio_max |
|---|---|---|---|---|---|---|
| `BA3C_0946` | 5 | 5.60 | 9.45 | 6.41 | 0.87 | 1.83 |
| `100098DE_1351` | 4 | 8.78 | 12.99 | 7.52 | 1.28 | 1.64 |
| `wonder_white` | 6 | 5.88 | 21.03 | 10.64 | 0.55 | 3.72 |

## Verdict and rationale

**CONFIRM-information-limit**

- Sensor calibration floor (T1-T8 spread at room temp, 7 fixtures): median range 0.34 degC, max range 4.37 degC, median sigma 0.110 degC.
- Zurcher 5-param LOO (35 fits): LOO-RMSE median 18.34 degC, max 37.24 degC; ratio LOO/in-sample median 0.89, max 2.16; 0/35 held-out sensors below 2 degC, 0 below 4 degC, 35 above 4 degC.
- Stefan LOO (15 fits, 3 representative fixtures): LOO-RMSE median 6.41 degC, max 21.03 degC; ratio LOO/in-sample median 0.85, max 3.72; 2/15 held-out sensors below 2 degC, 3 below 4 degC.
- LOO-RMSE on held-out sensors exceeds 4 degC and/or the LOO/in-sample ratio exceeds 2x. The models genuinely fail to capture the spatial profile - a sensor whose data the optimiser didn't see is mispredicted. In-sample RMSE of 6-22 degC was genuine model misfit, not sensor-side noise. M7-M12 verdicts stand.

## Production wiring recommendation

LOO-RMSE on held-out sensors confirms the in-sample RMSE was genuine model misfit. Either the physics class is wrong (2D conduction, moisture migration, convective coupling) or the parametrisation is genuinely non-identifiable from in-dough-only thermometry. **Pivot to Method 4** (per-CSV loaf-thickness, oven-setpoint, and lid-state metadata capture). The inverse-problem track on the present observation matrix is closed.
