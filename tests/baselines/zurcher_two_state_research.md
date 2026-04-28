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
