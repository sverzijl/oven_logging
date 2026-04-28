# HMS Ambush — Captain's Log

**Mission**: Empirically test whether Method 3 (1D heat-equation inverse problem) can extrapolate the loaf core position past the deepest probe sensor on the existing real CSVs. Research-only — no production wiring.

**Branch**: `refactor/role-classification-unified`
**Mission dir**: `.nelson/missions/2026-04-28_011739_e9776158`
**Status**: COMPLETE — verdict NO-GO.

## Outcome

Built the forward solver + inverse fitter + Hessian-based confidence; ran phases 1 (synthetic) and 2 (real CSVs) end-to-end; phase 3 (noise robustness) was started but stopped before completion when per-fit time on real CSVs proved to be ~50 s (vs ~1.8 s on synthetics) — the full 360-fit sweep would have taken 4+ hours. The verdict was clear from phases 1-2 alone, so the robustness sweep was deprioritised.

## Key findings (canonical record at `tests/baselines/heat_equation_extrapolation_research.md`)

1. **Synthetic recovery passes cleanly.** Bias = −0.00063, spread = 0.0035, 93/100 Hessian-CI coverage at σ = 0.5 °C. The method works in principle — when the model assumptions hold.

2. **Real-CSV RMSE is 6–10 °C across all 7 curves.** The acceptance bar was < 2 °C. The 1D heat equation is the wrong physics class for real bakes (latent-heat plateau, moisture, 2D/3D effects, non-Dirichlet BC under a lid).

3. **|ρ(α, x_core)| ≈ 0.9** on the 5 convergent cases. This is the core problem: the inverse problem identifies the diffusion length scale `(x_surface − x_core) / √α` but cannot separate x_core from α without an external constraint. Adding fixtures or seeds will not help.

4. **2 of 7 cases entirely degenerate** (lidded). When the cavity caps at ≈ 100 °C, the surface BC becomes near-constant and the inverse problem becomes ill-posed. α drifts to 10⁸ in `wonder_white` and 16 in `post_wonder_meal` with ρ ≈ 0 — a flat region of the loss landscape.

5. **No BA3C case extrapolated past T1** — the user's primary motivator. All 4 BA3C `x_core` estimates landed in (0, 0.25); the optimiser found the on-probe slowest-heating point, not a past-tip extrapolation.

## Recommendation

**NO-GO** for Method 3 in production. The recommendation in the report points the user to:

- **Method 1 (relaxed parabolic clamp)** for an immediate v1 — accepts noise amplification with a "low confidence — extrapolated past tip" UI flag. Cheap to ship, adequate to demonstrate the concept.
- **Method 4 (loaf-thickness metadata)** for a fully physical solution if/when we capture loaf thickness.
- **Pin α to a literature value** if the user insists on the heat-equation approach — converts the 2-parameter degenerate fit into a 1-parameter well-posed fit. Real-CSV RMSE would still be ≥ 6 °C, but at least the parameter uncertainty would be tractable. Requires the same loaf-geometry metadata Method 4 wants.

## Files delivered

- `src/data/spatial_reconstruction/heat_equation.py` — forward solver + inverse fit + Hessian.
- `tests/test_heat_equation_research.py` — 4 test classes (forward sanity, synthetic, real-CSV, robustness).
- `tests/_driver_heat_equation_report.py` — driver script (phase 3 too slow on real CSVs at current downsample_factor=4; recommend raising to 16 if rerun).
- `tests/baselines/heat_equation_extrapolation_research.md` — canonical research report with the verdict.

## Validation

- Forward solver sanity: 2/2 pass.
- Synthetic ground-truth recovery: 1/1 pass (no noise) + bias/spread/coverage figures from phase-1 driver run.
- Real-CSV viability: 7/7 fits ran to optimiser convergence (with degenerate ρ on 5 cases and pathological α on 2).
- Existing flotilla tests untouched (heat_equation.py is research-only; not wired into the classifier).

## Reusable patterns

**Adopt**: Document an inverse problem's *identifiability* (parameter correlation matrix) before trusting its CIs. The Hessian-based marginal CI on x_core looks reasonable until you check ρ; |ρ| ≈ 0.9 means the marginal CI is misleading and the true uncertainty is along a 1-D ridge in (α, x_core) space. Always report ρ alongside CIs for 2-parameter inverse problems.

**Avoid**: Tuning a synthetic-recovery harness's runtime to be acceptable, then assuming the same speed scales to real data. Phase-1 ran at 1.8 s/fit on synthetic time-grids; phase-3 ran at ~50 s/fit on real time-grids — a 27× slowdown driven by sample-count differences. Always size the slow path's runtime budget on real data, not synthetic.

## Mission paid off

Verdict delivered with empirical evidence; report committed; no production wiring.
