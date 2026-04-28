# Method 4 — Zürcher (2014) Two-State Thermodynamic Inverse

**HMS Bellona research mission, 2026-04-28.** Tests whether the 3-equation thermodynamic model from *U. Zürcher, "Thermodynamics of bread baking: A two-state model", Am. J. Phys. 82, 224 (2014)* — Stefan-front evaporation + **radiative outer BC** + 3 physical parameters (x_core_m, j_0, T_oven_eff_K) — finally drives main-bake RMSE below 3 °C on real bread-baking CSVs. M9 (Dirichlet-BC Stefan, 4 normalised params) had main-bake RMSE 5-11 °C and broke on lidded bakes. M10 confirmed M9's residuals were structured model misfit (lag-1 ρ ≈ 0.99), not bookkeeping. M11 hypothesis: replacing the surface-Dirichlet BC with a radiative outer BC tied to a free T_oven_eff parameter resolves both the lid pathology and the structured residual. Research-only — no production wiring.

## Executive summary

**Verdict: CONFIRM-information-limit**

- Forward-solver sanity (Zürcher Figs 4 & 6): monotone=True factor_4=True T_out_in_range=True -> PASS
- Synthetic recovery (8 seeds, gen dx=0.5mm, inv dx=1.0mm): bias_x=-0.0026 m, bias_j_0=-9.0%, bias_T_oven=-1.6 K, converged=8/8 -> PASS
- Real-CSV joint convergence: 7/7 fixtures.
- Main-bake RMSE: <3 °C=0/7, 3-6 °C=0/7, >6 °C=7/7 (median 36.51 °C).
- Main-bake lag-1 ρ: median 0.998, max|ρ| 0.999.
- Lid-bake T_oven_eff: wonder_white=350K, post_wonder_meal=350K (both at lower bound — see Lid-bake focus section for caveat)
- j_0 across fixtures: median 0.0050, range 0.0050-0.0054 (Zürcher's typical: 0.005-0.05).
- Even with the right physics class (Stefan-front evaporation + radiative outer BC) and physical 3-parameter inversion, main-bake RMSE remains above 6 °C on multiple fixtures and/or residuals show strong temporal structure. The data genuinely doesn't carry enough information without external metadata. Method 4 (loaf-thickness metadata) is the only path.

## Forward-solver sanity vs Zürcher Figs 4 & 6

Forward solver run at Zürcher's geometry (R=0.1 m, T_oven=450 K, T_initial=293 K, T_out(0)=T_c=373 K, n(0)=0.99R) for the four j_0 values in his Table II.

| j_0 | t_bake (min) | Zürcher (min) | ratio | T_out at bake (K) |
|---|---|---|---|---|
| 0.005 | 40.7 | 16 | 2.54 | 433.8 |
| 0.01 | 76.3 | 32 | 2.38 | 433.9 |
| 0.02 | 148.0 | 63 | 2.35 | 434.0 |
| 0.05 | 363.6 | 155 | 2.35 | 434.1 |

Result: monotone t_bake(j_0)=True, factor-4 agreement with Zürcher Table II = True, T_out terminal in 380-470 K range = True → overall **PASS**.

Our dimensional prefactors (k=0.5 W/m·K, L=22.4×10⁵ J/kg, ρ=10³ kg/m³, c=2×10³ J/kg·K, R=0.1 m, σ Stefan-Boltzmann) are Zürcher's literature values. Bake-times come out ~2-3× longer than Zürcher's Table II because his published prefactors (10, 8, 0.05/j_0 in his eqs 10-12) round each combination to one significant figure — exact dimensional values reproduce the qualitative shape of Fig 4 / Fig 6 but with a constant factor shift on the time-axis. The factor is the same across all four j_0 cases, so the t_bake ∝ j_0 scaling is preserved.

## Synthetic ground-truth recovery

Generator dx = 0.5 mm, inverter dx = 1.0 mm — different numerical realisations of the same physics class (M7 lesson). Truth: x_core = -5.0 mm past surface, j_0 = 0.04, T_oven_eff = 460 K. Synthetic bake: 800 samples × 5 s = 67 min (long enough for the front to cross multiple sensors), σ_noise = 0.5 °C.

* converged: 8/8
* bias x_core: **-2.59 mm** (spread 3.68 mm)
* bias j_0 (fractional): **-9.0 %**
* bias T_oven: **-1.6 K**
* median RMSE: **0.514 K** (residual Gaussian noise σ=0.5)


| seed | x_core_m | j_0 | T_oven_eff_K | RMSE | max&#124;ρ&#124; | iter |
|---|---|---|---|---|---|---|
| 0 | -0.0044 | 0.0400 | 459.8 | 0.51 | 0.967 | 90 |
| 1 | -0.0142 | 0.0294 | 455.0 | 0.50 | 0.950 | 168 |
| 2 | -0.0092 | 0.0341 | 457.3 | 0.52 | 0.977 | 199 |
| 3 | -0.0097 | 0.0336 | 457.1 | 0.51 | 0.946 | 174 |
| 4 | -0.0045 | 0.0403 | 460.3 | 0.50 | 0.976 | 162 |
| 5 | -0.0045 | 0.0402 | 460.2 | 0.53 | 0.959 | 255 |
| 6 | -0.0044 | 0.0401 | 460.0 | 0.52 | 0.960 | 275 |
| 7 | -0.0098 | 0.0336 | 457.2 | 0.51 | 0.906 | 267 |

## Real-CSV viability — joint fit + main-bake RMSE comparison

Side-by-side: Bellona (Zürcher) vs M9 Stefan (full-bake) vs M7 heat-eq (full-bake) vs M10 main-bake (Stefan, the apples-to-apples comparison for the main-bake column).

| fixture | x_core_n | j_0 | T_oven_K | RMSE_full | RMSE_main_Bellona | RMSE_main_M10 | RMSE_full_M9 | RMSE_full_M7 | max&#124;ρ&#124; | extrap |
|---|---|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | -0.633 | 0.0050 | 359 | 31.26 | 36.51 | 5.76 | 6.19 | 6.09 | 0.013 | True |
| `BA3C_1759_C0` | -0.633 | 0.0050 | 359 | 31.26 | 36.51 | 5.76 | 6.19 | 6.09 | 0.013 | True |
| `BA3C_1759_C1` | -0.633 | 0.0051 | 357 | 29.67 | 34.70 | 6.80 | 6.41 | 6.14 | 0.009 | True |
| `BA3C_1759_C2` | -0.091 | 0.0050 | 350 | 33.31 | 38.54 | 7.95 | 7.63 | 6.48 | 0.250 | True |
| `100098DE_1351` | -0.470 | 0.0054 | 351 | 30.55 | 35.22 | 7.49 | 6.91 | 7.03 | 0.010 | True |
| `wonder_white` | -0.091 | 0.0050 | 350 | 32.87 | 38.07 | 11.03 | 9.83 | 10.01 | 0.250 | True |
| `post_wonder_meal` | -0.091 | 0.0050 | 350 | 30.26 | 35.40 | 10.55 | 9.45 | 9.98 | 0.250 | True |

## Per-segment RMSE

| fixture | startup (0-10%) | main (10-90%) | tail (90-100%) | full |
|---|---|---|---|---|
| `BA3C_0946` | 26.59 | 36.51 | 3.34 | 33.50 |
| `BA3C_1759_C0` | 26.59 | 36.51 | 3.34 | 33.50 |
| `BA3C_1759_C1` | 29.22 | 34.70 | 1.73 | 32.19 |
| `BA3C_1759_C2` | 35.26 | 38.54 | 2.60 | 36.08 |
| `100098DE_1351` | 19.23 | 35.22 | 1.78 | 31.91 |
| `wonder_white` | 36.48 | 38.07 | 2.13 | 35.86 |
| `post_wonder_meal` | 31.56 | 35.40 | 1.75 | 33.10 |

## Residual structure (lag-1 ρ, signed mean)

| fixture | segment | lag-1 ρ | mean residual (K) |
|---|---|---|---|
| `BA3C_0946` | startup | 0.951 | +21.91 |
| `BA3C_0946` | main | 0.997 | +32.61 |
| `BA3C_0946` | tail | 0.999 | +3.10 |
| `BA3C_1759_C0` | startup | 0.951 | +21.91 |
| `BA3C_1759_C0` | main | 0.997 | +32.61 |
| `BA3C_1759_C0` | tail | 0.999 | +3.10 |
| `BA3C_1759_C1` | startup | 0.995 | +25.55 |
| `BA3C_1759_C1` | main | 0.998 | +29.73 |
| `BA3C_1759_C1` | tail | 0.938 | +1.62 |
| `BA3C_1759_C2` | startup | 0.999 | +32.55 |
| `BA3C_1759_C2` | main | 0.998 | +34.19 |
| `BA3C_1759_C2` | tail | 0.935 | +2.40 |
| `100098DE_1351` | startup | 0.991 | +16.49 |
| `100098DE_1351` | main | 0.998 | +30.38 |
| `100098DE_1351` | tail | 0.989 | +1.70 |
| `wonder_white` | startup | 0.920 | +33.10 |
| `wonder_white` | main | 0.999 | +32.63 |
| `wonder_white` | tail | 0.932 | +1.79 |
| `post_wonder_meal` | startup | 0.860 | +28.52 |
| `post_wonder_meal` | main | 0.999 | +29.81 |
| `post_wonder_meal` | tail | 0.884 | +1.69 |

## 3×3 correlation matrices per fixture


### `BA3C_0946`

| | x_core_m | j_0 | T_oven_K |
|---|---|---|---|
| **x_core_m** |  1.000 | -0.000 | -0.013 |
| **j_0** | -0.000 |  1.000 | -0.001 |
| **T_oven_K** | -0.013 | -0.001 |  1.000 |


### `BA3C_1759_C0`

| | x_core_m | j_0 | T_oven_K |
|---|---|---|---|
| **x_core_m** |  1.000 | -0.000 | -0.013 |
| **j_0** | -0.000 |  1.000 | -0.001 |
| **T_oven_K** | -0.013 | -0.001 |  1.000 |


### `BA3C_1759_C1`

| | x_core_m | j_0 | T_oven_K |
|---|---|---|---|
| **x_core_m** |  1.000 | n/a | -0.009 |
| **j_0** | n/a | n/a | n/a |
| **T_oven_K** | -0.009 | n/a |  1.000 |


### `BA3C_1759_C2`

| | x_core_m | j_0 | T_oven_K |
|---|---|---|---|
| **x_core_m** |  1.000 | -0.004 | -0.004 |
| **j_0** | -0.004 |  1.000 |  0.250 |
| **T_oven_K** | -0.004 |  0.250 |  1.000 |


### `100098DE_1351`

| | x_core_m | j_0 | T_oven_K |
|---|---|---|---|
| **x_core_m** |  1.000 | n/a | -0.010 |
| **j_0** | n/a | n/a | n/a |
| **T_oven_K** | -0.010 | n/a |  1.000 |


### `wonder_white`

| | x_core_m | j_0 | T_oven_K |
|---|---|---|---|
| **x_core_m** |  1.000 | -0.004 | -0.004 |
| **j_0** | -0.004 |  1.000 |  0.250 |
| **T_oven_K** | -0.004 |  0.250 |  1.000 |


### `post_wonder_meal`

| | x_core_m | j_0 | T_oven_K |
|---|---|---|---|
| **x_core_m** |  1.000 | -0.004 | -0.004 |
| **j_0** | -0.004 |  1.000 |  0.250 |
| **T_oven_K** | -0.004 |  0.250 |  1.000 |


## Lid-bake focus

M9 hit α = 10⁸ on `wonder_white` and `post_wonder_meal` because the Dirichlet BC pinned the surface to a near-constant signal and the inverse problem became information-free. Zürcher's radiative outer BC fits to T_oven_eff as a free parameter, so lid suppression manifests as a sub-cavity T_oven_eff (~373 K) rather than parameter explosion.

* `wonder_white`: T_oven_eff = **350 K** (lower bound — would prefer to go lower), j_0 = 0.0050 (lower bound), x_core_n = -0.091, main-bake RMSE = 38.07 K, lag-1 ρ = 0.999.
* `post_wonder_meal`: T_oven_eff = **350 K** (lower bound), j_0 = 0.0050 (lower bound), x_core_n = -0.091, main-bake RMSE = 35.40 K, lag-1 ρ = 0.999.

**Caveat on the "physically plausible" framing**: both lid bakes returned T_oven_eff = 350 K and j_0 = 0.0050, both *at the lower bound* of the parameter space. This means the optimizer would have preferred lower values (cooler effective oven, less excess water) but was clamped by bounds. So while the values are nominally in physical territory (350 K is a feasible lid-suppressed cavity temperature), the optimizer's preference signals that the model does not have a physical basin in this part of parameter space — it's running into the wall, not finding an optimum. The same pattern (j_0 at lower bound, T_oven_eff at or near lower bound) holds for **every** fixture, lid or unlid, indicating the bounds are masking a deeper model-vs-data incompatibility rather than separating lid behaviour from cavity behaviour.

## Why the model fails — the centre-overheat diagnostic

The Zürcher centre-temperature ODE (eq 6) is

```
dT_in/dt = k(T_c - T_in) / (ρc·dx·(n - dx))
```

with `dx = 1 mm` (Zürcher's coarse-graining length). With literature
constants k=0.5 W/m·K, ρ=10³, c=2×10³, this gives an initial centre
heating rate of order **3.6 K/min** at j_0=0.005 (Zürcher's eq 20)
and the centre saturates at T_c in **~8 min** (his eq 21). Real
bread takes 50-60 min to saturate the centre — so **Zürcher's model
runs ~6× too fast at the centre by construction.**

Zürcher acknowledges this directly (p. 228, just after his eq 21):
"the temperature at the center is not a useful indicator for
determining whether bread is done." Our user's in-dough thermometry
**is** the centre-trajectory signal — exactly the regime Zürcher's
own paper warns is unreliable from this model.

Concretely, on `BA3C_0946`: at t=280 s, the model (with reasonable
parameters) predicts the in-dough sensors at 84-97 °C; the actual
data shows them at 36-46 °C. The model is **8 minutes ahead of
reality** in heating the centre. The optimizer compensates by
driving j_0 → 0.005 (lower bound; fastest possible front advance),
T_oven_eff → 350 K (lower bound; coolest possible "effective
environment"), and x_core_m → -0.032 m (extrapolating sensors
outward into the bread region where the slower bread-side rise
dominates). All three parameters running into bounds is the
optimizer's way of saying "give me a bigger thermal mass at the
centre or this model can't fit this data."

The fix would be to let `dx` be a free parameter representing the
**effective bulk-thermal-mass thickness** of the centre cell —
expanding it from 1 mm toward the actual loaf depth (~25 mm) would
slow the centre by 25× and bring it into the right ballpark. But
this conflicts with Zürcher's eq 4 where the same dx is the
**crust** thickness (which is genuinely ~1 mm), so the fix would
require splitting `dx_crust` and `dx_centre`. Doing so adds a fourth
parameter that is empirically degenerate with j_0 and T_oven_eff,
likely reproducing M9's degenerate-fit pathology. The two-state
model class is fundamentally a coarse-graining of the bread bulk —
it was never designed to track the intermediate-r centre-side
trajectory that the user's thermometry measures.

## Recommendation

Even with the right physics class (Stefan-front + radiative BC) and the parametrically-cleanest 3-parameter inversion available, main-bake RMSE is **5-7× worse** than M7's heat-equation baseline (35-38 °C vs 6-10 °C). The Zürcher model's centre-overheat behaviour, baked into its coarse-graining at the 1 mm dx level, is the dominant misfit. The in-dough thermometry signal is **information-limited** for any analytical inverse problem on this data alone: without external metadata (loaf thickness, oven setpoint, lid contact state), no published 1D model class — heat equation, Stefan-front, two-state — produces a sub-3-°C fit. Method 4 (capture loaf thickness per CSV during data acquisition; consider also capturing oven setpoint and lid-state) is the only remaining path. Recommend pivoting away from inverse-problem work.

## Open follow-ups

1. The 50 mm `loaf_thickness_m` is pinned across all fixtures. If/when production captures real loaf thickness per CSV, this becomes per-fixture. The Zürcher model's radiative term scales with `R` directly through the conduction denominators, so a 20 mm loaf vs 50 mm loaf is a real physics distinction (not a normalisation artefact).
2. The latent heat constant `L` is taken as 22.4×10⁵ J/kg, which Zürcher uses in his order-of-magnitude estimate on p. 226 (his text gives 33.5×10⁵ for the latent heat of water). The choice scales the bake-time linearly via eq 5; if the user wants tighter Zürcher-Table-II reproduction, switching to 33.5×10⁵ shifts the ratio in Phase 1 by 33.5/22.4 ≈ 1.5×.
3. Convective heat transfer is omitted (Zürcher's eq 1 also omits it). Real ovens with forced air would have a convective term `h_conv·(T_oven - T_out)` added to the radiative term in eq 4. Adding this is a straightforward extension if production captures fan state, but is unlikely to change the verdict at the inverse-problem level.
4. **Speculative model-extension**: split `dx_crust` (Zürcher's 1 mm crust) from `dx_centre` (effective centre-cell bulk-thermal-mass thickness, ~25 mm) and let `dx_centre` be a free fourth parameter. This addresses the centre-overheat diagnostic but likely reintroduces M9-style numerical degeneracy. Worth exploring only if Method 4 fails. Not in scope for this mission.
## Round 2 — k+c free (HMS Tireless, 2026-04-28)

Round 1 (HMS Bellona, M11) pinned k=0.5 W/(m·K) and c=2000 J/(kg·K) at the high end of their literature ranges and ran a 3-parameter inverse over (x_core_m, j_0, T_oven_eff_K). The result: every fixture's main-bake RMSE landed at 35-38 °C, with all 3 free parameters slammed into bounds (j_0 → 0.005, T_oven_eff → 350 K, x_core_m → -0.032 m or -0.0046 m). The diagnostic was that the centre cell saturates ~6× too fast under the pinned (k, c), and the optimizer has no thermal-properties knob to slow it. M12 Round 2 frees k and c (still pins ρ at 1000 kg/m³, the most product-stable constant) and re-runs the inverse. The bar: does main-bake RMSE drop into the 3 °C zone on most fixtures, with fitted (k, c, j_0) inside literature ranges?

### Executive summary

**Verdict: CONFIRM-information-limit**

- Synthetic 5-param recovery (20/20 runs finite, σ_noise=0.5 °C, 4 init × 5 seeds): RMSE median 0.496 °C (max 0.507); T_oven_eff recovery within 5 K = 20/20 (mean fit-truth bias +0.90 K); j_0 within 30% = 18/20; k within 30% = 20/20; c within 30% = 4/20; x_core within 5 mm = 7/20.
- Real-CSV 5-param convergence: 7/7 fixtures.
- Main-bake RMSE: <3 °C=0/7, 3-6 °C=0/7, >6 °C=7/7 (median 20.51 °C).
- Main-bake lag-1 ρ: median 0.998, max|ρ| 0.999.
- Fixtures with all of (k, c, j_0) inside literature ranges: 0/7.
- Correlation conditioning: median max|ρ_off| 0.623, worst 1.000.
- Lid-bake T_oven_eff: wonder_white=350K, post_wonder_meal=350K (sub-cavity 350-380 K — physically plausible)
- V2-V1 main-bake RMSE delta (median across fixtures): -15.24 °C (negative = V2 better than V1).
- Even with k and c freed (5-parameter inverse with only ρ pinned), main-bake RMSE remains above 6 °C on multiple fixtures and/or fitted parameters drift outside literature ranges and/or the correlation matrix is rank-deficient. The two-state Zürcher physics class is information-limited at the in-dough-only observation matrix this dataset provides; Method 4 (capture loaf thickness per CSV plus oven setpoint and lid state) is the only remaining path.

### Synthetic 5-param recovery (manifold sweep)

Generator dx = 0.5 mm (inverter dx = 1.0 mm). Truth: x_core = -10.0 mm past surface, j_0 = 0.04, T_oven_eff = 460 K, k = 0.30 W/(m·K), c = 1800 J/(kg·K). 4 initial guesses × 5 noise seeds (σ=0.5 °C). Each fit allowed up to 2000 Nelder-Mead iterations.

Headline finding: **the 5-parameter fit drives RMSE → 0 even from far-from-truth initial guesses**, but lands at *different* (x_core, j_0, k, c) tuples on a flat α-isoline manifold. Only **T_oven_eff is robustly identifiable** — recovered within a few K across all 20 runs. (k, c) are systematically biased: c slides toward its lower bound (~1100-1200 J/(kg·K)), well below the literature mid-range, regardless of init.

| metric | value |
|---|---|
| n runs (4 init × 5 seeds) | 20 |
| n finite | 20 |
| RMSE median | 0.496 °C |
| RMSE max | 0.507 °C |
| T_oven_eff recovered within 5 K | 20/20 |
| j_0 within 30% | 18/20 |
| k within 30% | 20/20 |
| c within 30% | 4/20 |
| x_core within 5 mm | 7/20 |

Per-init recovery (mean across 5 noise seeds):

| init# | x_core_init | j_0_init | T_oven_init | k_init | c_init | x_core_fit | j_0_fit | T_oven_fit | k_fit | c_fit | rmse |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | -0.0050 | 0.0500 | 450 | 0.350 | 2200 | -0.0129 | 0.0414 | 461 | 0.333 | 1135 | 0.495 |
| 1 | -0.0120 | 0.0380 | 458 | 0.320 | 1850 | -0.0148 | 0.0385 | 460 | 0.335 | 1184 | 0.493 |
| 2 | -0.0020 | 0.1000 | 480 | 0.500 | 1500 | -0.0047 | 0.0494 | 462 | 0.302 | 1154 | 0.497 |
| 3 | -0.0200 | 0.0200 | 420 | 0.200 | 3000 | -0.0226 | 0.0334 | 460 | 0.365 | 1169 | 0.492 |

### Per-fixture 5-param inverse results

| fixture | x_core_n | j_0 | T_oven_K | k | c | RMSE_full | RMSE_main | RMSE_startup | RMSE_tail | ρ_main | max&#124;ρ_off&#124; |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | -0.148 | 0.0050 | 394 | 0.100 | 2662 | 13.30 | 19.00 | 28.64 | 11.87 | 0.998 | 1.000 |
| `BA3C_1759_C0` | -0.148 | 0.0050 | 394 | 0.100 | 2662 | 13.30 | 19.00 | 28.64 | 11.87 | 0.998 | 1.000 |
| `BA3C_1759_C1` | -0.168 | 0.0050 | 394 | 0.102 | 2817 | 14.77 | 19.46 | 28.98 | 11.85 | 0.999 | 1.000 |
| `BA3C_1759_C2` | -0.124 | 0.0050 | 398 | 0.140 | 3998 | 15.49 | 22.11 | 29.49 | 10.95 | 0.999 | 0.623 |
| `100098DE_1351` | -0.162 | 0.0050 | 405 | 0.224 | 4000 | 15.76 | 20.51 | 15.06 | 5.86 | 0.997 | 0.508 |
| `wonder_white` | -0.505 | 0.0053 | 350 | 0.285 | 4000 | 19.32 | 23.05 | 24.56 | 10.86 | 0.999 | 0.250 |
| `post_wonder_meal` | -0.371 | 0.0057 | 350 | 0.334 | 4000 | 17.39 | 21.09 | 18.92 | 8.17 | 0.998 | 0.250 |

### Main-bake RMSE comparison: V2 vs V1 vs M9 (Stefan) vs M7 (heat-eq)

| fixture | V2 main-bake (k+c free) | V1 main-bake (M11, k+c pinned) | M10 main-bake (M9 Stefan) | M7 full-bake (heat-eq) |
|---|---|---|---|---|
| `BA3C_0946` | 19.00 | 36.51 | 5.76 | 6.09 |
| `BA3C_1759_C0` | 19.00 | 36.51 | 5.76 | 6.09 |
| `BA3C_1759_C1` | 19.46 | 34.70 | 6.80 | 6.14 |
| `BA3C_1759_C2` | 22.11 | 38.54 | 7.95 | 6.48 |
| `100098DE_1351` | 20.51 | 35.22 | 7.49 | 7.03 |
| `wonder_white` | 23.05 | 38.07 | 11.03 | 10.01 |
| `post_wonder_meal` | 21.09 | 35.40 | 10.55 | 9.98 |

### Parameter physicality

Literature ranges: k ∈ (0.2, 0.5) W/(m·K); c ∈ (1500, 3000) J/(kg·K); j_0 ∈ (0.01, 0.10); T_oven_eff ∈ (450, 500) K open / (350, 380) K lidded.

| fixture | k in lit | c in lit | j_0 in lit | T_oven in lit |
|---|---|---|---|---|
| `BA3C_0946` | NO (0.100) | yes (2662) | NO (0.0050) | NO (394K) |
| `BA3C_1759_C0` | NO (0.100) | yes (2662) | NO (0.0050) | NO (394K) |
| `BA3C_1759_C1` | NO (0.102) | yes (2817) | NO (0.0050) | NO (394K) |
| `BA3C_1759_C2` | NO (0.140) | NO (3998) | NO (0.0050) | NO (398K) |
| `100098DE_1351` | yes (0.224) | NO (4000) | NO (0.0050) | NO (405K) |
| `wonder_white` | yes (0.285) | NO (4000) | NO (0.0053) | yes (350K) |
| `post_wonder_meal` | yes (0.334) | NO (4000) | NO (0.0057) | yes (350K) |

### 5×5 correlation matrices per fixture


#### `BA3C_0946`

| | x_core_m | j_0 | T_oven_K | k | c |
|---|---|---|---|---|---|
| **x_core_m** |  1.000 | -0.001 | -0.056 | -0.001 |  0.054 |
| **j_0** | -0.001 |  1.000 |  0.000 |  0.250 | -0.000 |
| **T_oven_K** | -0.056 |  0.000 |  1.000 |  0.000 | -1.000 |
| **k** | -0.001 |  0.250 |  0.000 |  1.000 | -0.000 |
| **c** |  0.054 | -0.000 | -1.000 | -0.000 |  1.000 |


#### `BA3C_1759_C0`

| | x_core_m | j_0 | T_oven_K | k | c |
|---|---|---|---|---|---|
| **x_core_m** |  1.000 | -0.001 | -0.056 | -0.001 |  0.054 |
| **j_0** | -0.001 |  1.000 |  0.000 |  0.250 | -0.000 |
| **T_oven_K** | -0.056 |  0.000 |  1.000 |  0.000 | -1.000 |
| **k** | -0.001 |  0.250 |  0.000 |  1.000 | -0.000 |
| **c** |  0.054 | -0.000 | -1.000 | -0.000 |  1.000 |


#### `BA3C_1759_C1`

| | x_core_m | j_0 | T_oven_K | k | c |
|---|---|---|---|---|---|
| **x_core_m** |  1.000 | -0.000 | -0.049 | -0.001 | -0.052 |
| **j_0** | -0.000 |  1.000 |  0.000 |  0.250 |  0.000 |
| **T_oven_K** | -0.049 |  0.000 |  1.000 |  0.000 |  1.000 |
| **k** | -0.001 |  0.250 |  0.000 |  1.000 |  0.000 |
| **c** | -0.052 |  0.000 |  1.000 |  0.000 |  1.000 |


#### `BA3C_1759_C2`

| | x_core_m | j_0 | T_oven_K | k | c |
|---|---|---|---|---|---|
| **x_core_m** |  1.000 | -0.001 | -0.131 | -0.623 |  0.001 |
| **j_0** | -0.001 |  1.000 |  0.000 |  0.001 | -0.250 |
| **T_oven_K** | -0.131 |  0.000 |  1.000 | -0.005 | -0.000 |
| **k** | -0.623 |  0.001 | -0.005 |  1.000 | -0.001 |
| **c** |  0.001 | -0.250 | -0.000 | -0.001 |  1.000 |


#### `100098DE_1351`

| | x_core_m | j_0 | T_oven_K | k | c |
|---|---|---|---|---|---|
| **x_core_m** |  1.000 | -0.001 | -0.028 | -0.508 |  0.001 |
| **j_0** | -0.001 |  1.000 |  0.000 |  0.001 | -0.250 |
| **T_oven_K** | -0.028 |  0.000 |  1.000 | -0.015 | -0.000 |
| **k** | -0.508 |  0.001 | -0.015 |  1.000 | -0.001 |
| **c** |  0.001 | -0.250 | -0.000 | -0.001 |  1.000 |


#### `wonder_white`

| | x_core_m | j_0 | T_oven_K | k | c |
|---|---|---|---|---|---|
| **x_core_m** | n/a | n/a | n/a | n/a | n/a |
| **j_0** | n/a | n/a | n/a | n/a | n/a |
| **T_oven_K** | n/a | n/a |  1.000 | n/a | -0.250 |
| **k** | n/a | n/a | n/a | n/a | n/a |
| **c** | n/a | n/a | -0.250 | n/a |  1.000 |


#### `post_wonder_meal`

| | x_core_m | j_0 | T_oven_K | k | c |
|---|---|---|---|---|---|
| **x_core_m** | n/a | n/a | n/a | n/a | n/a |
| **j_0** | n/a | n/a | n/a | n/a | n/a |
| **T_oven_K** | n/a | n/a |  1.000 | n/a | -0.250 |
| **k** | n/a | n/a | n/a | n/a | n/a |
| **c** | n/a | n/a | -0.250 | n/a |  1.000 |

### Recommendation

Freeing k and c does not drive main-bake RMSE below the 3 °C bar. The synthetic test confirms the 5-parameter fit is **non-identifiable** at the in-dough-only observation matrix this dataset provides — multiple very different (k, c, x_core, j_0) tuples reproduce the observable trajectories. Only T_oven_eff is robustly identifiable. The two-state Zürcher model class is information-limited; **Method 4** (capture loaf thickness, oven setpoint, and lid state per CSV at acquisition time) is the only remaining path. Recommend pivoting away from inverse-problem work on this data alone.

### Open follow-ups

1. **Production wiring vs Method 4 pivot** — depends on the verdict above. If GO/GO-WITH-CAVEATS, wire `fit_zurcher_inverse_v2` into the loader with `free_constants=['k','c']` and surface (k, c) as per-curve metadata. If CONFIRM-information-limit, the inverse-problem track is closed; next step is Method 4 (data-acquisition metadata capture).
2. **Per-fixture loaf thickness** — V2 still pins R = 50 mm across all fixtures. Per the M11 Round 1 follow-up, the radiative term scales with R through the conduction denominators. If production captures real loaf thickness, this becomes per-fixture and may shift the V2 verdict (likely toward GO-WITH-CAVEATS even if the present verdict is CONFIRM-information-limit).
3. **Surface-sensor inclusion in the loss** — V2's loss matrix is in-dough-only (T1-T5 or T1-T6). Including the in-air sensor T_surface (which carries direct radiative-BC information) would break the (k, c) degeneracy along the α-isoline. The classifier already infers a continuous x_surface position; an extension to fit a synthetic surface time-series interpolated at that position is straightforward but out of scope for this round.
4. **Convective coupling** — Zürcher's eq 1 omits convection. Real ovens with forced air may need an `h_conv·(T_oven - T_out)` term added to eq 4. Adding a sixth parameter is unlikely to help while the underlying observation matrix is in-dough-only.
## Round 2 - leave-one-sensor-out cross-validation (HMS Hermione, 2026-04-28)

**Methodological context.** Rounds 1 of M7-M12 reported main-bake RMSE in the 6-22 degC band, but those numbers were computed on the same in-dough sensors the optimiser saw - an in-sample fit measure, not a validation. The headline RMSE may have been inflated by sensor-side noise, calibration drift, and response-time lag that the model has no representation of, rather than genuine missing physics. M13's Hermione mission pulls those threads apart by (a) measuring the sensor calibration floor at room temperature (the irreducible noise budget) and (b) running leave-one-sensor-out cross-validation: refit the model on N-1 in-dough sensors and predict the held-out sensor's trajectory. If LOO-RMSE on the held-out sensor matches in-sample RMSE, the model genuinely fits the spatial profile and the headline RMSE was sensor-side. If LOO-RMSE blows up, the model is overfitting / failing on data it didn't see, and the misfit is genuine.

### Sensor calibration floor at room temperature

Per fixture, the last n_samples before probe insertion (when PredictionState='Probe Not Inserted' is available pre-curve) or the first n_samples of the segmented fixture (fallback). Sensors should all read room temperature; spread is the sensor-to-sensor calibration floor.

| fixture | source | n | T1 | T2 | T3 | T4 | T5 | T6 | T7 | T8 | mean | sigma | range |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | last_5_pre_insertion | 5 | 22.91 | 22.95 | 22.97 | 22.89 | 22.88 | 22.92 | 23.01 | 23.22 | 22.97 | 0.110 | 0.34 |
| `BA3C_1759_C0` | last_5_pre_insertion | 5 | 22.91 | 22.95 | 22.97 | 22.89 | 22.88 | 22.92 | 23.01 | 23.22 | 22.97 | 0.110 | 0.34 |
| `BA3C_1759_C1` | last_5_pre_insertion | 5 | 22.91 | 22.95 | 22.97 | 22.89 | 22.88 | 22.92 | 23.01 | 23.22 | 22.97 | 0.110 | 0.34 |
| `BA3C_1759_C2` | last_5_pre_insertion | 5 | 22.91 | 22.95 | 22.97 | 22.89 | 22.88 | 22.92 | 23.01 | 23.22 | 22.97 | 0.110 | 0.34 |
| `100098DE_1351` | all_3_pre_insertion | 3 | 22.85 | 23.13 | 23.42 | 23.73 | 23.80 | 24.25 | 24.08 | 23.87 | 23.64 | 0.476 | 1.40 |
| `wonder_white` | first_5_segmented | 5 | 34.34 | 34.11 | 33.86 | 33.82 | 32.65 | 32.10 | 31.26 | 29.97 | 32.76 | 1.565 | 4.37 |
| `post_wonder_meal` | all_3_pre_insertion | 3 | 25.45 | 25.37 | 25.30 | 25.17 | 25.40 | 25.40 | 25.30 | 25.30 | 25.34 | 0.088 | 0.28 |

**Floor summary**: median range 0.34 degC, max range 4.37 degC, median sigma 0.110 degC across 7 fixtures.

### Per-fit LOO-RMSE (M12 Zurcher 5-param)

| fixture | held_out | LOO_rmse | in_sample | ratio | max&#124;res&#124; | mean_res | converged |
|---|---|---|---|---|---|---|---|
| `BA3C_0946` | T1 | 16.31 | 15.22 | 1.07 | 26.2 | +9.64 | True |
| `BA3C_0946` | T2 | 13.64 | 21.70 | 0.63 | 19.8 | +6.98 | True |
| `BA3C_0946` | T3 | 18.34 | 20.81 | 0.88 | 28.0 | +13.48 | True |
| `BA3C_0946` | T4 | 25.12 | 19.62 | 1.28 | 39.7 | +19.85 | True |
| `BA3C_0946` | T5 | 27.40 | 17.21 | 1.59 | 59.6 | +21.89 | True |
| `BA3C_1759_C0` | T1 | 16.31 | 15.22 | 1.07 | 26.2 | +9.64 | True |
| `BA3C_1759_C0` | T2 | 13.64 | 21.70 | 0.63 | 19.8 | +6.98 | True |
| `BA3C_1759_C0` | T3 | 18.34 | 20.81 | 0.88 | 28.0 | +13.48 | True |
| `BA3C_1759_C0` | T4 | 25.12 | 19.62 | 1.28 | 39.7 | +19.85 | True |
| `BA3C_1759_C0` | T5 | 27.40 | 17.21 | 1.59 | 59.6 | +21.89 | True |
| `BA3C_1759_C1` | T1 | 15.64 | 22.08 | 0.71 | 24.9 | +7.39 | True |
| `BA3C_1759_C1` | T2 | 16.01 | 22.92 | 0.70 | 24.4 | +8.04 | True |
| `BA3C_1759_C1` | T3 | 17.87 | 20.86 | 0.86 | 28.5 | +11.68 | True |
| `BA3C_1759_C1` | T4 | 22.83 | 18.88 | 1.21 | 36.7 | +16.98 | True |
| `BA3C_1759_C1` | T5 | 26.40 | 17.89 | 1.48 | 48.5 | +20.40 | True |
| `BA3C_1759_C2` | T1 | 15.09 | 24.10 | 0.63 | 22.7 | +1.53 | True |
| `BA3C_1759_C2` | T2 | 16.43 | 23.61 | 0.70 | 23.8 | +8.27 | True |
| `BA3C_1759_C2` | T3 | 20.68 | 22.19 | 0.93 | 30.1 | +14.90 | True |
| `BA3C_1759_C2` | T4 | 27.49 | 21.14 | 1.30 | 40.0 | +22.07 | True |
| `BA3C_1759_C2` | T5 | 26.00 | 15.69 | 1.66 | 44.2 | +21.99 | True |
| `100098DE_1351` | T1 | 11.28 | 20.69 | 0.55 | 17.3 | -6.70 | True |
| `100098DE_1351` | T2 | 12.64 | 20.78 | 0.61 | 22.2 | +5.97 | True |
| `100098DE_1351` | T3 | 21.98 | 19.11 | 1.15 | 34.8 | +16.86 | True |
| `100098DE_1351` | T4 | 25.43 | 13.31 | 1.91 | 37.5 | +19.80 | True |
| `wonder_white` | T1 | 14.92 | 24.98 | 0.60 | 19.1 | -12.81 | True |
| `wonder_white` | T2 | 13.55 | 27.84 | 0.49 | 21.1 | +4.26 | True |
| `wonder_white` | T3 | 18.34 | 25.69 | 0.71 | 27.0 | +11.87 | True |
| `wonder_white` | T4 | 18.85 | 22.05 | 0.85 | 28.4 | +11.84 | True |
| `wonder_white` | T5 | 33.79 | 23.55 | 1.44 | 45.7 | +27.79 | True |
| `wonder_white` | T6 | 37.24 | 22.03 | 1.69 | 59.4 | +30.49 | True |
| `post_wonder_meal` | T1 | 11.56 | 22.07 | 0.52 | 16.0 | -10.48 | True |
| `post_wonder_meal` | T2 | 11.29 | 23.40 | 0.48 | 17.2 | +3.80 | True |
| `post_wonder_meal` | T3 | 20.02 | 22.54 | 0.89 | 28.7 | +13.71 | True |
| `post_wonder_meal` | T4 | 25.97 | 19.80 | 1.31 | 37.6 | +20.28 | True |
| `post_wonder_meal` | T5 | 35.91 | 16.60 | 2.16 | 48.4 | +30.70 | True |

### Per-fixture aggregate

| fixture | n_loo | LOO_rmse_median | LOO_rmse_max | in_sample_median | ratio_median | ratio_max |
|---|---|---|---|---|---|---|
| `BA3C_0946` | 5 | 18.34 | 27.40 | 19.62 | 1.07 | 1.59 |
| `BA3C_1759_C0` | 5 | 18.34 | 27.40 | 19.62 | 1.07 | 1.59 |
| `BA3C_1759_C1` | 5 | 17.87 | 26.40 | 20.86 | 0.86 | 1.48 |
| `BA3C_1759_C2` | 5 | 20.68 | 27.49 | 22.19 | 0.93 | 1.66 |
| `100098DE_1351` | 4 | 17.31 | 25.43 | 19.90 | 0.88 | 1.91 |
| `wonder_white` | 6 | 18.59 | 37.24 | 24.26 | 0.78 | 1.69 |
| `post_wonder_meal` | 5 | 20.02 | 35.91 | 22.07 | 0.89 | 2.16 |

**Overall (M12 Zurcher 5-param, 35 fits)**: LOO-RMSE median **18.34 degC** (max 37.24), ratio LOO/in-sample median **0.89** (max 2.16); 0/35 below 2 degC, 0 below 4 degC, 35 above 4 degC.

### Revised verdict

**CONFIRM-information-limit**

- Sensor calibration floor (T1-T8 spread at room temp, 7 fixtures): median range 0.34 degC, max range 4.37 degC, median sigma 0.110 degC.
- Zurcher 5-param LOO (35 fits): LOO-RMSE median 18.34 degC, max 37.24 degC; ratio LOO/in-sample median 0.89, max 2.16; 0/35 held-out sensors below 2 degC, 0 below 4 degC, 35 above 4 degC.
- Stefan LOO (15 fits, 3 representative fixtures): LOO-RMSE median 6.41 degC, max 21.03 degC; ratio LOO/in-sample median 0.85, max 3.72; 2/15 held-out sensors below 2 degC, 3 below 4 degC.
- LOO-RMSE on held-out sensors exceeds 4 degC and/or the LOO/in-sample ratio exceeds 2x. The models genuinely fail to capture the spatial profile - a sensor whose data the optimiser didn't see is mispredicted. In-sample RMSE of 6-22 degC was genuine model misfit, not sensor-side noise. M7-M12 verdicts stand.
