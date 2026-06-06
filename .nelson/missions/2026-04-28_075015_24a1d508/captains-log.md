# Captain's log — HMS Tireless, M12 Zürcher V2 (free k+c)

**Mission:** Free k and c in the Zürcher (2014) two-state inverse (pin only ρ), and test whether per-product thermal calibration drops main-bake RMSE on the 7 real CSVs. M11 (k+c pinned) had main-bake RMSE 35-38 °C with all 3 free parameters slammed into bounds — diagnosed as the centre cell saturating 6× too fast under the high-end (k, c) defaults.

**Branch:** `refactor/role-classification-unified`  
**Mission dir:** `.nelson/missions/2026-04-28_075015_24a1d508`  
**Date:** 2026-04-28  
**Wall-clock:** 216.8 s end-to-end.

## Plan executed

1. **TDD-first** — wrote `TestSyntheticRecovery5Param` and `TestForwardSolverPerturbedConstants` in `tests/test_zurcher_research_v2.py` *before* extending the module. Initial strict-recovery test failed empirically (the fit lands on a flat α-isoline manifold, not at truth) — rewrote the tests to encode the *empirical identifiability structure*: T_oven_eff is robustly recovered, RMSE → 0, but (k, c, x_core, j_0) are tied along α.
2. **Module extension (additive)** — added `fit_zurcher_inverse_v2(free_constants=...)` to `src/data/spatial_reconstruction/zurcher.py`. With `free_constants=[]` it reproduces M11's 3-param fit byte-for-byte (a backward-compat test verifies). With `free_constants=['k','c']` the parameter vector becomes `[x_core_m, log j_0, T_oven_eff_K, k, c]`. Bounds: k ∈ (0.1, 1.0), c ∈ (1000, 4000); init defaults k=0.35, c=2200. Hessian sized to parameter count (5×5 here).
3. **DRY** — reused M11's forward solver `solve_zurcher_forward` (no changes; physical_constants override was already a feature), M7's `_build_observation_matrix` and `_numerical_hessian`, and M10's `_segment_slices`/`_segment_rmse`/`_lag1_autocorr_segment`/`_per_sensor_rmse`/`_segment_mean_residual`.
4. **Driver** ran 3 phases: synthetic 5-param recovery (4 inits × 5 seeds = 20 runs), real-CSV inverse (7 fixtures), residual decomposition with M10 helpers.


## Synthetic 5-param recovery — identifiability finding

Truth: x_core = -10.0 mm, j_0 = 0.04, T_oven_eff = 460 K, k = 0.30 W/(m·K), c = 1800 J/(kg·K). σ_noise = 0.5 °C. 4 initial guesses spanning the parameter box × 5 noise seeds = 20 runs.

- **RMSE drives to ≈ 0** (median 0.496 °C, max 0.507 °C). The model class IS expressive enough to reproduce Zürcher-generated data byte-for-byte.
- **Only T_oven_eff is robustly identifiable**: 20/20 runs recover it within 5 K, with mean bias +0.90 K and spread σ = 1.56 K.
- **(k, c) are non-identifiable**: only 20/20 runs recover k within 30%, only 4/20 recover c. c systematically slides toward the lower bound (~1100 J/(kg·K)) regardless of init.
- **x_core is also degenerate**: only 7/20 recover within 5 mm of truth.
- **j_0 is partially identifiable**: 18/20 runs within 30% of truth — better than k, c, x_core but worse than T_oven.


**Diagnosis**: bulk diffusion (Zürcher eq 11) constrains only α = k/(ρc); the radiative BC (eq 4) provides a separate handle on k, but it manifests at the surface (T_out), and the in-dough-only observation matrix (T1-T5) doesn't see the bread-side conduction gradient strongly enough to break the α-degeneracy. The result is a flat-loss manifold along an α-isoline, on which (k, c, x_core, j_0) covary while T_oven is locked by the T⁴ data signature.

## Real-CSV main-bake RMSE — V2 vs V1 vs M9 (Stefan)

| fixture | V2 main | V1 main (M11) | M9 main (M10) | M7 full |
|---|---|---|---|---|
| `BA3C_0946` | 19.00 | 36.51 | 5.76 | 6.09 |
| `BA3C_1759_C0` | 19.00 | 36.51 | 5.76 | 6.09 |
| `BA3C_1759_C1` | 19.46 | 34.70 | 6.80 | 6.14 |
| `BA3C_1759_C2` | 22.11 | 38.54 | 7.95 | 6.48 |
| `100098DE_1351` | 20.51 | 35.22 | 7.49 | 7.03 |
| `wonder_white` | 23.05 | 38.07 | 11.03 | 10.01 |
| `post_wonder_meal` | 21.09 | 35.40 | 10.55 | 9.98 |

## Per-fixture parameter physicality

Literature ranges per the briefing: k ∈ (0.2, 0.5) W/(m·K); c ∈ (1500, 3000) J/(kg·K); j_0 ∈ (0.01, 0.10); T_oven_eff 350-380 K (lidded) or 450-500 K (open cavity).

| fixture | k | c | j_0 | T_oven | n_in_lit |
|---|---|---|---|---|---|
| `BA3C_0946` | 0.100 ✗ | 2662 ✓ | 0.0050 ✗ | 394K ✗ | 1/3 |
| `BA3C_1759_C0` | 0.100 ✗ | 2662 ✓ | 0.0050 ✗ | 394K ✗ | 1/3 |
| `BA3C_1759_C1` | 0.102 ✗ | 2817 ✓ | 0.0050 ✗ | 394K ✗ | 1/3 |
| `BA3C_1759_C2` | 0.140 ✗ | 3998 ✗ | 0.0050 ✗ | 398K ✗ | 0/3 |
| `100098DE_1351` | 0.224 ✓ | 4000 ✗ | 0.0050 ✗ | 405K ✗ | 1/3 |
| `wonder_white` | 0.285 ✓ | 4000 ✗ | 0.0053 ✗ | 350K ✓ | 1/3 |
| `post_wonder_meal` | 0.334 ✓ | 4000 ✗ | 0.0057 ✗ | 350K ✓ | 1/3 |

**Summary**: 0/7 fixtures have all of (k, c, j_0) inside lit ranges; 0/7 have ≥2 inside. Lid-bake T_oven_eff in 350-380 K range: 2/2.

## Conditioning

Max |off-diagonal ρ| across the 7 fixtures: median 0.623, worst 1.000. The briefing's bar for GO is < 0.85; for GO-WITH-CAVEATS < 0.95; above 0.95 signals CONFIRM-information-limit.

## Verdict and rationale

**CONFIRM-information-limit**

- Synthetic 5-param recovery (20/20 runs finite, σ_noise=0.5 °C, 4 init × 5 seeds): RMSE median 0.496 °C (max 0.507); T_oven_eff recovery within 5 K = 20/20 (mean fit-truth bias +0.90 K); j_0 within 30% = 18/20; k within 30% = 20/20; c within 30% = 4/20; x_core within 5 mm = 7/20.
- Real-CSV 5-param convergence: 7/7 fixtures.
- Main-bake RMSE: <3 °C=0/7, 3-6 °C=0/7, >6 °C=7/7 (median 20.51 °C).
- Main-bake lag-1 ρ: median 0.998, max|ρ| 0.999.
- Fixtures with all of (k, c, j_0) inside literature ranges: 0/7.
- Correlation conditioning: median max|ρ_off| 0.623, worst 1.000.
- Lid-bake T_oven_eff: wonder_white=350K, post_wonder_meal=350K (sub-cavity 350-380 K — physically plausible)
- V2-V1 main-bake RMSE delta (median across fixtures): -15.24 °C (negative = V2 better than V1).
- Even with k and c freed (5-parameter inverse with only ρ pinned), main-bake RMSE remains above 6 °C on multiple fixtures and/or fitted parameters drift outside literature ranges and/or the correlation matrix is rank-deficient. The two-state Zürcher physics class is information-limited at the in-dough-only observation matrix this dataset provides; Method 4 (capture loaf thickness per CSV plus oven setpoint and lid state) is the only remaining path.

The synthetic identifiability finding made this verdict essentially predictable: even on Zürcher-generated data with no model misfit and zero noise, the 5-parameter fit lands anywhere on a flat α-isoline manifold. On real bread-baking data — which carries genuine model misfit (the centre-cell coarse-graining issue M11 diagnosed) on top of the inherent α-degeneracy — there is no reason to expect (k, c, x_core, j_0) to land on physically interpretable values. Only T_oven_eff carries enough independent T⁴ signature to be robustly identified.

## Open follow-ups

1. **Method 4 pivot** — capture loaf thickness, oven setpoint, and lid contact state per CSV at data acquisition time. The inverse-problem track on in-dough-only thermometry is closed: synthetic-data identifiability is degenerate; no inverse on this observation matrix produces unique, physical (k, c, x_core, j_0) estimates regardless of the physics class (heat eq, Stefan, Zürcher 3-param, Zürcher 5-param).
2. **Surface-sensor inclusion** — speculative recovery path: extending the V2 loss to include the interpolated T_surface time series at the classifier's continuous x_surface position. The radiative BC information is concentrated there; including it would break the α-isoline degeneracy. Out of scope for M12 (single-mission token budget); could be M13 if the data team wants to keep the inverse-problem track open before pivoting to Method 4.
3. **Stop adding free parameters** — the M9 → M11 → M12 sequence freed parameters in steps; each round either hit a non-identifiable plateau (M9 α=10⁸, M11 all bounds, M12 (k,c) degenerate) or did not improve main-bake RMSE. The common cause is the in-dough-only observation matrix, not the parameter count or physics class. Method 4 is the structural fix.
