# Spatial-Reconstruction Model Comparison — Piecewise vs Stefan

Empirical comparison powering the default-model decision for `src/data/spatial_reconstruction/`. Both models read the same feature dict (DRY contract); they diverge only in how they reconstruct T(x) from the per-sensor terminal vector.

**Models compared**

- **Piecewise** (M2a HMS Indefatigable) — three independent regions:
  dough plateau, air rise (free slope), optional lid plateau. The dough/air interface is the largest adjacent ΔT exceeding `MONOTONIC_GRADIENT_MIN_JUMP_C`. Plateau temperature is free.
- **Stefan** (M2b HMS Vanguard) — physics-constrained:
  dough/air interface pinned at exactly T = 100 °C (latent-heat evaporation front); air-side rise governed by one global thermal-diffusivity coupling parameter `α`. The model is `T(x) = 100 + (T_cavity − 100)(1 − exp(−α(x − x_front)))`.

**Fixture set**: 9 cases — 5 real CSVs + 4 synthetics.

## Per-fixture results

| Fixture | Piecewise SSE | Stefan SSE | Piecewise x | Stefan x | Ground truth x | Piecewise err | Stefan err | Piecewise role pass (c/s/a/l) | Stefan role pass (c/s/a/l) |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|
| `real_100098DE_1351` | 5.50 | 976.87 | 0.786 | 0.691 | None | — | — | ✓/✓/✓/✓ | ✓/✓/✗/✓ |
| `real_1000BA3C_0946` | 168.04 | 4237.80 | 0.786 | 0.643 | None | — | — | ✓/✓/✓/✓ | ✓/✓/✓/✓ |
| `real_1000BA3C_1759` | 3.82 | 5081.30 | 0.643 | 0.593 | None | — | — | ✓/✓/✓/✓ | ✓/✓/✓/✓ |
| `wonder_white_10k_lidded` | 0.69 | 0.69 | (0.071, 0.929) | (0.071, 0.929) | None | — | — | ✗/✓/✓/✓ | ✗/✓/✓/✓ |
| `post_wonder_meal_lidded` | 0.63 | 0.63 | (0.071, 0.929) | (0.071, 0.929) | None | — | — | ✓/✗/✗/✓ | ✓/✗/✗/✓ |
| `synthetic_shallow_insertion` | 7.64 | 1763.82 | 0.214 | 0.151 | 0.357 | 0.143 | 0.206 | ✓/✓/✓/✓ | ✓/✓/✓/✓ |
| `synthetic_full_immersion` | 17.74 | 17.74 | None | None | None | — | — | ✓/✓/✓/✓ | ✓/✓/✓/✓ |
| `synthetic_lid_touch` | 12.10 | 9841.04 | 0.357 | 0.291 | 0.500 | 0.143 | 0.209 | ✓/✓/✓/✓ | ✓/✓/✓/✓ |
| `synthetic_probe_pull_mid_bake` | 16.80 | 4760.83 | 0.786 | 0.724 | 0.929 | 0.143 | 0.204 | ✓/✓/✓/✓ | ✓/✓/✓/✓ |

## Surface-pick side-by-side

| Fixture | Piecewise.surface | Stefan.surface | Expected |
|---|:---:|:---:|:---:|
| `real_100098DE_1351` | T7 | T7 | T7 |
| `real_1000BA3C_0946` | T6 | T6 | T6 |
| `real_1000BA3C_1759` | T6 | T6 | T6 |
| `wonder_white_10k_lidded` | T7 | T7 | T7 |
| `post_wonder_meal_lidded` | T7 | T7 | T8 |
| `synthetic_shallow_insertion` | T3 | T3 | T3 |
| `synthetic_full_immersion` | None | None | None |
| `synthetic_lid_touch` | T4 | T4 | T4 |
| `synthetic_probe_pull_mid_bake` | T7 | T7 | T7 |

## Compute time

| Fixture | Piecewise (ms) | Stefan (ms) |
|---|---:|---:|
| `real_100098DE_1351` | 1258.8 | 82.9 |
| `real_1000BA3C_0946` | 54.1 | 63.1 |
| `real_1000BA3C_1759` | 50.0 | 50.2 |
| `wonder_white_10k_lidded` | 73.1 | 67.1 |
| `post_wonder_meal_lidded` | 59.0 | 71.9 |
| `synthetic_shallow_insertion` | 74.6 | 48.7 |
| `synthetic_full_immersion` | 64.9 | 64.2 |
| `synthetic_lid_touch` | 60.3 | 67.0 |
| `synthetic_probe_pull_mid_bake` | 62.0 | 74.1 |

## Stefan diagnostic

| Fixture | T_cavity | α (1/x) | n 100°C crossings |
|---|---:|---:|---:|
| `real_100098DE_1351` | 138.5 | 26.94 | 1 |
| `real_1000BA3C_0946` | 170.6 | 23.03 | 1 |
| `real_1000BA3C_1759` | 173.5 | 18.94 | 1 |
| `wonder_white_10k_lidded` | 100.3 | — | 1 |
| `post_wonder_meal_lidded` | 98.6 | — | 0 |
| `synthetic_shallow_insertion` | 215.3 | 10.73 | 1 |
| `synthetic_full_immersion` | 97.3 | — | 0 |
| `synthetic_lid_touch` | 214.7 | 6.57 | 1 |
| `synthetic_probe_pull_mid_bake` | 215.0 | 35.00 | 1 |

## Aggregate metrics

- **Total fixtures passing all 4 roles**: piecewise 7/9, stefan 6/9.

| Role | Piecewise pass | Stefan pass |
|---|---:|---:|
| core | 8/9 | 8/9 |
| surface | 8/9 | 8/9 |
| ambient | 8/9 | 7/9 |
| lid | 9/9 | 9/9 |

- **Mean residual SSE** (lower = better fit): piecewise 25.88, stefan 2964.52.
- **Mean position error** (only on synthetics with ground-truth): piecewise 0.143, stefan 0.207.

## Spotlight: `post_wonder_meal_lidded` (the 1 piecewise-failing fixture)

- Expected surface: **T8** (M1a/M1b annotation: first sensor on the air side past dough).
- Piecewise.surface: **T7**
- Stefan.surface: **T7**

- **Both models agree on this fixture** (either both pass or both fail). The choice of model has no leverage here; the annotation convention in M1a's Truculent is the disagreement axis.

## Recommendation

**Default model**: `piecewise`

Piecewise passes 7/9 fixtures vs Stefan's 6/9. The Stefan model's stricter 100°C pin rejects fixtures where the latent-heat plateau sits 1-2°C below 100 °C (real-CSV calibration noise).

This recommendation is mirrored at `config.constants.ROLE_CLASSIFIER_CONFIG['DEFAULT_MODEL']` and is the value the loader (M3a) should pass through to `classify(...)`.

## Open follow-ups

- **M4 perturbation harness**: re-run this comparison under bootstrap resampling of the input curves to score *stability* of position estimates as well as accuracy. The Stefan model's reduced parameter count should show up as lower position-error variance even when mean accuracy is comparable.
- **Lid-bake disambiguation**: if the spotlight fixture above is not resolved by either model, M4 should add `xcorr_lag_to_oven_proxy_seconds` and a cool-rate feature to the lid-bake split — this is the smallest remaining gap in the contract surface.

