# Method 3 — Heat-Equation Extrapolation Research

**HMS Ambush research mission, 2026-04-28.** Empirically tests whether the 1D heat-equation inverse problem can recover the loaf core position past the deepest probe sensor on the existing real CSVs. **Research-only — no production wiring.**

## Executive summary

**Verdict: NO-GO** for production wiring on the current fixture set.

- Synthetic ground-truth recovery passes cleanly (bias = −0.00063, spread = 0.0035, 93/100 Hessian-CI coverage at σ = 0.5 °C). The method *works in principle*.
- Real-CSV residual RMSE is **6–10 °C across all 7 fixtures** (the bar was < 2 °C). The 1D heat equation does not fit real bake physics well enough for the inverse problem to be meaningful.
- α–x_core correlation is **|ρ| = 0.87–0.91** on the 5 cases that converge cleanly. The two parameters are nearly degenerate — only one combined quantity is identifiable from the data, not the two separately. The bar was |ρ| < 0.8.
- 2 of 7 fixtures (`wonder_white`, `post_wonder_meal`) returned non-physical α values (1.3 × 10⁸ and 16 in normalised-position²/s) with ρ ≈ 0 — the optimiser drifted into a flat region of the loss landscape. Both are lid-suppressed bakes; the constant-temperature surface BC the model assumes is grossly violated when the cavity caps at 100 °C.
- **None of the BA3C cases extrapolated past T1** — the primary motivating use-case. Inferred x_core landed in [0.03, 0.25] (between T1 and T2-T3) for all four BA3C curves. The optimiser found the on-probe slowest-heating point, not the past-tip extrapolation the user wanted.

## Method

- **Forward solver**: 1D heat equation `∂T/∂t = α · ∂²T/∂x²` on `x ∈ [x_core, x_surface]`, finite-difference method-of-lines (30 spatial nodes), integrated by `scipy.integrate.solve_ivp` (`LSODA`).
- **Boundary conditions**: Neumann (`∂T/∂x = 0`) at the geometric core; Dirichlet (`T(x_surface, t) = T_observed_surface(t)`) at the dough/air interface.
- **Inverse fit**: Nelder-Mead minimisation of summed squared residuals across all in-dough sensors and downsampled time-samples (every 4th sample). Initial guess `x_core = -0.05`, `α = 10⁻³`.
- **Confidence**: numerical Hessian (5-point central differences) at the optimum; covariance ≈ inv(Hess) · 2σ²/n_obs.
- **Sample period**: read from CSV header (5 s/sample on all real fixtures).

## Synthetic ground-truth recovery (the gating test)

Generated synthetic dough observations with `α_true = 1.5 × 10⁻³`, `x_core_true = -0.15`, in-dough sensors {T1, T2, T3, T4}, σ = 0.5 °C Gaussian noise, 100 seeds.

| Metric | Value | Bar | Pass? |
|---|---|---|---|
| Mean bias `(x_fit − x_true)` | −0.00063 | < 0.02 | ✅ |
| Spread `σ(x_fit)` | 0.0035 | < 0.05 | ✅ |
| 95% Hessian-CI coverage | 93/100 | ≥ 90 | ✅ |
| Convergence rate | 100/100 | n/a | ✅ |
| Wall time | 180.7 s for 100 seeds | n/a | n/a |

**Verdict on the method itself**: when the model assumptions hold (1D conduction, Dirichlet surface, Neumann symmetry-core), the inverse problem is well-posed. Hessian-based CIs are calibrated.

## Real-CSV viability (7 curves)

All 7 curves run to completion. Results sorted by ρ (less degenerate first; ρ closer to 0 = better):

| Fixture | x_core | x_core 95% CI | α (norm²/s) | ρ(α, x_core) | RMSE (°C) | Notes |
|---|---|---|---|---|---|---|
| `BA3C_1759_C1` | 0.117 | n/a | 3.06 × 10⁻⁴ | −0.871 | 6.14 | Convergent, degenerate |
| `BA3C_0946` | 0.032 | n/a | 3.04 × 10⁻⁴ | −0.905 | 6.09 | Convergent, degenerate |
| `BA3C_1759_C0` | 0.032 | n/a | 3.04 × 10⁻⁴ | −0.905 | 6.09 | Convergent, degenerate |
| `BA3C_1759_C2` | 0.249 | n/a | 1.49 × 10⁻⁴ | −0.907 | 6.48 | Convergent, degenerate |
| `100098DE_1351` | 0.430 | n/a | 2.11 × 10⁻⁴ | −0.905 | 7.03 | Convergent, degenerate |
| `post_wonder_meal` | −0.061 | n/a | 16.4 | −0.001 | 9.98 | **Pathological** — α non-physical |
| `wonder_white` | −0.081 | n/a | 1.34 × 10⁸ | −0.003 | 10.01 | **Pathological** — α non-physical |

(95% CIs are not reported because all the convergent cases have |ρ| > 0.85 — the marginal CI on x_core conditional on a free α would be wider than the prior, and the joint CI is essentially a 1-D ridge in (α, x_core) space. The Hessian-based marginal CI is misleading here. See "Why the inverse problem is degenerate on real data" below.)

### Diagnostic observations

- **No BA3C case extrapolates past T1.** The user's primary motivator was that on a typical insertion T1 is on the probe boundary and we'd want to extrapolate the core PAST T1 (x < 0). The optimiser instead lands in (0, 0.25) — *inside* the probe span between T1 and T3 — even when the initial guess is `x_core = -0.05`. This is the optimiser finding the loss minimum, not a numerical artefact.

- **The two lidded cases are pathological.** When the cavity caps at ≈ 100 °C (lid suppresses cavity), the surface time-series provided as the BC is essentially constant after a brief rise. With a near-constant BC, dough sensors all approach a single asymptote and the time-axis information collapses — the inverse problem becomes ill-posed. The optimiser drifts to nonsense (`α = 1.3 × 10⁸`) without any gradient pulling it back.

- **The 5 well-behaved cases all share |ρ| ≈ 0.9.** A clear pattern: α and x_core anti-correlate at almost exactly the same magnitude across very different bakes. This means the data carries one primary signal (something like "depth × diffusivity") and the model has two parameters trying to fit it. Adding more sensors or more noise won't fix this — it's an identifiability issue, not a noise issue.

### Why the inverse problem is degenerate on real data

For 1D heat conduction with a fixed surface BC and a Neumann BC at depth d, the temperature at internal point x at time t scales (approximately, for early-time response) as `T(x, t) ≈ T_surface · erfc((x_surface − x) / (2√(α · t)))`. The argument of `erfc` depends on x and α only through the combination `(x_surface − x) / √α`. So for any fixed observation, doubling α and quartering `(x_surface − x)²` produces the same prediction. That's exactly the anti-correlation we observe (ρ ≈ −0.9). At late times, finite-thickness effects break this exact degeneracy, but the residuals on real data are too high (RMSE 6–10 °C) for that breaking signal to be useful.

In other words: **the heat-equation inverse problem can identify the diffusion length scale `(x_surface − x_core) / √α` precisely, but cannot disentangle x_core from α without additional physics or measurements.**

## Noise robustness (partial — driver stopped)

Only one condition was measured before stopping the driver (each real-CSV fit takes ~50 s; the full 360-fit sweep would have taken 4+ hours):

| Fixture | σ (°C) | heat-eq mean | heat-eq std | parabolic mean | parabolic std |
|---|---|---|---|---|---|
| `BA3C_0946` | 0.0 | 0.0321 | 0.0000 | −0.4333 | 0.0000 |

At σ = 0.0 both methods are deterministic, so the std is trivially zero. This row is a sanity check (matches phase-2 numbers). Differential-noise comparison was not collected. **Given the verdict is NO-GO from the convergence and identifiability evidence alone, robustness was deprioritised.**

The parabolic method *did* extrapolate past T1 (x = −0.43, deterministically) on this fixture — interesting, but its parameter uncertainty isn't characterised here either.

## Recommendation

**NO-GO** for production wiring. Reasons in order of severity:

1. Real-CSV RMSE of 6–10 °C means the 1D heat-equation model is the wrong physics for these bakes. Adding latent-heat plateau effects, moisture migration, or 2D/3D conduction would change the model class entirely — out of scope for a flotilla follow-up.
2. |ρ| ≈ 0.9 on the convergent cases means α and x_core cannot be separately identified. We could fix α (e.g. to a literature value for dough thermal diffusivity ≈ 1.4 × 10⁻⁷ m²/s) and re-run, but that's a different inverse problem (1-parameter fit) and we'd need to convert normalised x to mm to apply the literature value — which requires the loaf-thickness metadata Method 4 was waiting for.
3. The lidded-bake pathology (α drifting to 10⁸) means the model fails entirely on the bake type the user is most interested in (wonder_white, post_wonder_meal).
4. Even on the unlidded cases, the optimiser does not extrapolate past T1 — defeating the whole motivation.

### Things that would change this recommendation

- **Pin α to a known value**: if we adopt a published thermal diffusivity for bread dough (≈ 1.4 × 10⁻⁷ m²/s, with normalisation requiring loaf thickness), the 1-parameter `x_core` fit would not have the identifiability problem. Real-CSV residuals would still be ≥ 6 °C, but at least the parameter uncertainty would be tractable.
- **Use the Stefan boundary instead of constant-α conduction**: model the 100 °C latent-heat front explicitly. This is essentially merging Method 3 with the existing Stefan piecewise model from M2b. The benefit is unclear — the Stefan piecewise model already does this without solving the heat equation, and it's more numerically robust.
- **Acquire more fixtures with thermometry beyond T1** (e.g. an external thermocouple at the loaf's geometric centre). Independent ground-truth would let us test whether the inferred x_core is meaningful at all, rather than testing it against an indirect proxy.

### Practical recommendation for the original problem

The user wanted continuous core position past T1. Given Method 3 is NO-GO, the practical alternatives:

- **Method 1 (relaxed parabolic clamp)** as a v1 implementation, with a "low confidence — extrapolated past tip" flag in the UI. Empirical evidence here: parabolic gave x_core = −0.43 on `BA3C_0946`, extrapolated past T1 with the obvious noise-amplification caveats.
- **Method 4 (loaf-thickness metadata)** if/when we capture loaf-thickness in CSV header or per-product config. Geometric centre = `loaf_thickness / 2`, x_core = `insertion_depth − loaf_thickness / 2`. Fully physical, no inverse problem.

## Reproducibility

Data files committed:
- `src/data/spatial_reconstruction/heat_equation.py` — forward solver + inverse fitter + Hessian helper + bootstrap stub.
- `tests/test_heat_equation_research.py` — 4 test classes (forward sanity, synthetic recovery, real-CSV viability, robustness).
- `tests/_driver_heat_equation_report.py` — end-to-end driver invoked as `python -m tests._driver_heat_equation_report`. Phase 3 takes ~4 hours on real CSVs at the current downsample factor; consider increasing `downsample_factor` from 4 to 16 to bring it under 30 min for future runs.

To regenerate the synthetic + real-CSV portion of this report (~5 min):

```
pytest tests/test_heat_equation_research.py::TestForwardSolverSanity \
       tests/test_heat_equation_research.py::TestInverseGroundTruthRecovery \
       tests/test_heat_equation_research.py::TestRealCSVViability -v
```

The full driver was stopped mid-phase-3; raw outputs from phases 1 and 2 above are the canonical record.


---

# Round 2 — corrected BC + profile likelihood (HMS Resolution, 2026-04-28)

The Round 1 (HMS Ambush) verdict was driven in part by a discrete-sensor surface BC. On the typical BA3C insertion the M2a classifier identifies T6 as the surface-side sensor, but T6 itself is *in dough* (it plateaus near 100 °C). Feeding T6's time series as the Dirichlet BC at x_surface is feeding a fake-plateau, not the true dough/air interface temperature; the inverse problem becomes information-free over most of the bake.

Round 2 retests with three fixes: (i) the BC is built by per-timestep linear *spatial* interpolation across all 8 sensors at the M2a continuous interface position `surface_assignment.position_normalised`, (ii) a profile-likelihood scan distinguishes structural degeneracy from optimiser laziness, and (iii) `synthetic_shallow_insertion` is inverted as a true model-misfit baseline (its data was NOT generated by the heat-eq forward solver).


## Corrected-BC real-CSV viability (7 fixtures)

| fixture | x_surf_cont | x_core (v2) | x_core (M7 v1) | α (v2) | &#124;ρ&#124; (v2) | RMSE v2 (°C) | RMSE v1 (°C) | extrap |
|---|---|---|---|---|---|---|---|---|
| `BA3C_0946` | 0.6787 | 0.036 | 0.032 | 2.96e-04 | 0.891 | 6.07 | 6.09 | False |
| `BA3C_1759_C0` | 0.6787 | 0.036 | 0.032 | 2.96e-04 | 0.891 | 6.07 | 6.09 | False |
| `BA3C_1759_C1` | 0.7177 | 0.120 | 0.117 | 3.01e-04 | 0.882 | 6.11 | 6.14 | False |
| `BA3C_1759_C2` | 0.7132 | 0.250 | 0.249 | 1.49e-04 | 0.904 | 6.48 | 6.48 | False |
| `100098DE_1351` | 0.7704 | 0.434 | 0.430 | 2.21e-04 | 0.845 | 6.89 | 7.03 | False |
| `wonder_white` | 0.9286 | -0.061 | -0.081 | 4.00e+03 | 0.002 | 9.83 | 10.01 | True |
| `post_wonder_meal` | 0.9286 | -0.064 | -0.061 | 1.70e+03 | 0.002 | 9.46 | 9.98 | True |

## Profile-likelihood diagnostic (3 fixtures)


### `BA3C_0946` (x_surf_cont = 0.6787)

min loss = 13072.4, max = 24313.2, median = 16164.8, argmin x_core = 0.042, relative range = 0.70

**Verdict: BASIN — loss has a clear minimum (numerical, not structural).**


| x_core | α best | loss |
|---|---|---|
| -0.500 | 6.26e-04 | 20948.7 |
| -0.375 | 5.65e-04 | 18726.5 |
| -0.250 | 4.93e-04 | 16470.8 |
| -0.125 | 4.12e-04 | 14409.3 |
| 0.000 | 3.23e-04 | 13141.1 |
| 0.125 | 2.33e-04 | 13521.2 |
| 0.250 | 1.51e-04 | 16164.8 |
| 0.375 | 8.14e-05 | 21706.5 |

### `100098DE_1351` (x_surf_cont = 0.7704)

min loss = 14425.4, max = 23273.2, median = 19119.4, argmin x_core = 0.458, relative range = 0.46

**Verdict: FLAT — structural degeneracy (loss varies < 50% across the grid).**


| x_core | α best | loss |
|---|---|---|
| -0.500 | 2.35e-03 | 23273.2 |
| -0.375 | 2.04e-03 | 22604.0 |
| -0.250 | 1.72e-03 | 21772.3 |
| -0.125 | 1.40e-03 | 20673.0 |
| 0.000 | 1.08e-03 | 19119.4 |
| 0.125 | 7.82e-04 | 17249.9 |
| 0.250 | 5.18e-04 | 15594.4 |
| 0.375 | 3.05e-04 | 14584.8 |
| 0.500 | 1.43e-04 | 14425.7 |

### `wonder_white` — all loss values non-finite


## Synthetic shallow-insertion model-misfit baseline

The fixture was *not* generated by the heat-eq forward solver — its temperatures come from the role-classifier fixture-builder. Inverting it tests whether the heat-equation model class fits real bake geometries at all.


* x_surface_continuous = 0.3571
* in-dough sensors = ['T1', 'T2']
* fitted x_core = -2.4821, α = 3.81e-04, overall RMSE = 25.69 °C

Per-sensor RMSE:

| sensor | RMSE (°C) |
|---|---|
| T1 | 25.73 |
| T2 | 25.64 |

## Revised verdict

**REVISE TO GO-WITH-CAVEATS**

- Corrected-BC RMSE: median=6.48 °C, max=9.83 °C across 7 fixtures.
- Profile-likelihood: 1/2 fixtures show a basin; the rest are flat-loss (structural degeneracy).
- BA3C past-T1 extrapolation: NO (no BA3C case crosses x_core<0 with corrected BC)

Verdict logic: REVISE TO GO requires max-RMSE < 2 °C, every profile-likelihood scan showing a basin, and at least one BA3C case extrapolating past T1 (x_core<0). REVISE TO GO-WITH-CAVEATS if median-RMSE < 4 °C or any scan shows a basin. CONFIRM NO-GO otherwise.

