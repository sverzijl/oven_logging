# HMS Defender — Practical complexity assessment

**Mission:** M22 task 3. Engineering scoping for a cellular-with-sensor-grounding (data-assimilation) inverse architecture against the existing M9 Stefan baseline.

**Baseline anchor:** `src/data/spatial_reconstruction/heat_equation.py` (830 LOC) + `stefan_inverse_v3.py` (623 LOC) currently solve a 1D method-of-lines grid (`N=30` spatial × ~280 timesteps ≈ 8.4k ODE vars) via `scipy.integrate.solve_ivp(method='LSODA')` with a 6-param Nelder-Mead outer loop. Single-fit wall-time ≈ 75 s on `BA3C_0946`.

---

## 1. Implementation options ranking

| # | Stack | Install (Win) | Forward LOC | Inverse LOC | Total LOC | Dev-days | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | **scipy.sparse + handwritten FDM** | trivial (already in `requirements.txt`) | 250–350 | 200–300 | **500–650** | 4–6 | **RECOMMENDED** |
| 2 | **JAX (FDM + autodiff)** | medium — `pip install jax jaxlib` works on Win/CPU since 0.4.x but no GPU; `jaxopt` for L-BFGS | 200–300 | 100–150 | **350–500** | 6–9 | Strong if we want gradient-based fits |
| 3 | **PyTorch + custom FDM layer** | easy — wheels are first-class on Windows | 250–350 | 150–200 | **500–700** | 6–9 | Overkill (no GPU need at this size) |
| 4 | **FEniCS / dolfin** | painful — no native Windows wheel; needs WSL2 or conda-forge `fenics-dolfinx`; CI pain | 150–250 | 200–300 | 500–700 | 10–15 | Reject for now |
| 5 | **Firedrake** | worse than FEniCS — no Windows support, Linux/macOS only | n/a | n/a | n/a | n/a | Reject |

**Why option 1 wins:** the existing M9 stack is already FDM-with-`solve_ivp`. A 1D-cellular variant with sensor grounding is a 100–200 LOC delta on `heat_equation.solve_heat_equation_forward`, not a rewrite. Anchor sensors become additional Dirichlet/penalty terms in the same RHS function. Win-compat is a non-issue — we already ship scipy/numpy.

**Why JAX is the strong second:** Nelder-Mead on a 6-param fit takes ~200–400 forward solves (75 s / fit ≈ 0.2–0.4 s/solve in M9). At 50×100 cells the per-solve cost goes up >100×; gradient-based optimization buys a real ~5–10× factor by replacing 200+ derivative-free evaluations with ~20 L-BFGS steps, each costing 1 fwd + 1 reverse-AD pass. But the rewrite cost is real, and JAX-on-Windows still has rough edges around `lax.scan` debugging.

---

## 2. Computational cost estimate

**Single forward solve, 50×100 cells × 280 timesteps × coupled (T, u, α) ≈ 15k state vars:**

- LSODA on 15k stiff ODEs with banded Jacobian: **6–25 s/solve** (M9 at 8.4k = 0.2–0.4 s/solve; cost scales as ~N·log N for sparse stiff systems but Jacobian-vector cost dominates → ~30–60× M9). Bottom of the band assumes we provide a banded Jacobian; top assumes finite-difference Jacobian.
- Memory: 15k × 280 × 8 bytes ≈ 33 MB output, fine. Internal LSODA workspace ~5–10× that.

**Single inverse fit (Nelder-Mead, 5–6 params):** 200–400 forward solves × 6–25 s = **20–170 min/fit**. Realistic central estimate **≈ 60 min/fit**.

**Versus M9 (75 s):** **~50× slower per fit.** Not 1000×. The 100× claim in the brief is the upper end and only hits if we run cold-start LSODA per evaluation with finite-diff Jacobian.

**7-fixture sweep:** 7 × 60 min ≈ **7 h** central; 2.3 h best-case, 20 h worst-case. Overnight is the operating mode.

**With JAX + L-BFGS:** ~20 outer steps × 2 forward-equivalent passes × 8 s ≈ **5–10 min/fit**, 35–70 min for 7-fixture sweep. This is the only path that makes parameter-field inversion (α(x,y,t), source(x,y,t)) tractable; once params become fields with O(100–1000) DOFs Nelder-Mead simply will not converge.

**Critical:** scaling parameter inversion from 6 scalars to a smoothness-prior-regularised α-field on a 5000-cell mesh is the real cost cliff. Pure scipy + Nelder-Mead does not reach there. **Field-level inversion forces JAX (or a custom adjoint).**

---

## 3. Reuse from existing codebase

Verified against the tree (`src/data/spatial_reconstruction/`, 3,559 LOC total across stefan/heat_equation/profile/inverse modules):

- `src/data/spatial_reconstruction/profile.py::interpolate_temperature_series_at` — direct reuse for sensor-grounding boundary interpolation. Already used by all four inverse modules (`stefan_inverse{,_v2,_v3}.py`, `heat_equation.py`).
- `tests/test_heat_equation_research.py::_segmented_real_fixture` — fixture loader with main-bake segmentation. Direct reuse.
- `src/data/spatial_reconstruction/heat_equation.py::solve_heat_equation_forward` — partial reuse: extract its LSODA wrapper, banded-Jacobian construction, and Dirichlet projection. The cellular variant adds (i) a 2nd spatial dim, (ii) interior sensor-anchor Dirichlet/penalty terms, (iii) cell-wise α field. ~60% of the time-integration scaffolding survives.
- `src/data/spatial_reconstruction/stefan_inverse_v3.py::fit_stefan_inverse_v3` — reuse the Hessian/CI machinery (`_numerical_hessian`, parameter-correlation matrix). Drop the 6-param Nelder-Mead outer loop.
- `src/data/spatial_reconstruction/profile.py::ProfileFit, extract_features` — reuse for initial-condition seeding (T(x,0) profile from the M2a piecewise reconstruction).
- `src/data/spatial_reconstruction/classifier.py::SpatialAssignment` — provides per-curve `position_normalised` for each sensor → exactly the (x,y) grounding coordinates the cellular formulation needs. **This is the missing piece M9 doesn't use; the cellular formulation finally does.**
- M10 residual decomposition (per `.nelson/missions/2026-04-28_*` archives) — reuse for the diagnostic phase to localise where the cellular fit is failing in space×time.

**No reuse:** the Stefan-front tracking machinery (`stefan.py::fit_stefan`, `STEFAN_FRONT_TEMP_C` clamp) — the cellular formulation does not need an explicit moving boundary; phase change becomes a smooth α(T) feature.

---

## 4. Smaller-scope pilot recommendation

**Recommend: Pilot option 1 (1D cellular with sensor grounding, ~500 LOC, 3–10 min/fit).**

Justification:

- **Tests the load-bearing hypothesis directly** — the user's claim is that grounding the PDE at sensor positions improves identifiability. A 1D mesh with multiple interior Dirichlet anchors is the minimal experiment that exercises this. The 8 sensors already lie on a single probe axis; 2D adds geometry without adding information.
- **LOO falsification is built-in** — drop sensor T_k from the grounding set, predict T_k(t) from the grounded model, compare against M9's LOO (T1=9.45, T2=7.40). If 1D cellular LOO ≥ M9 LOO, the architecture is not earning its complexity, and we stop before sinking effort into 2D and field inversion.
- **Cost is bounded** — 100 cells × 280 timesteps ≈ 28k DOF, ~1 s forward, ~5 min Nelder-Mead fit. Within one engineer-day per sweep iteration.
- **Pilot 2 (2D pinned-α) is the wrong test** — pinned α with no inversion is just interpolation; it cannot fail informatively. We already know the forward problem is well-posed when α is known (that's M9's premise).
- **Pilot 3 (1D piecewise-time α) is a useful side experiment** but is a parametric refinement of M9, not a test of cellular-grounding. It belongs in a separate mission if the user wants to isolate "is time-varying α the win?"

**Decision rule after pilot 1:**
- LOO RMSE ≥ M9 LOO across all 7 fixtures → **STAND-DOWN** the cellular architecture.
- LOO RMSE < M9 LOO on ≥4/7 fixtures → **proceed to 2D + field inversion** (now justifying JAX).
- Mixed → **HYBRID**: keep 1D-cellular as the production path, document the failure modes.

---

## 5. Success metric definition

**Primary metric:** main-bake RMSE on `BA3C_0946` (the single-curve canonical fixture).

| Method | Main-bake RMSE | Status |
|---|---|---|
| M9 Stefan v3 (6-param) | **5.76 °C** | baseline |
| Method 4 stub (geometric core) | n/a (metadata-driven, not fit-based) | baseline |
| **Pilot 1 target** | **< 4.0 °C** (≥30% reduction) | required to justify build |
| Pilot 1 minimum-viable | ≤ 5.5 °C **and** LOO improvement | weak pass |
| Pilot 1 failure | ≥ 5.76 °C **or** LOO regression | stand-down |

**Failure-mode signal (held-out sensor LOO):** drop each interior sensor in turn, rebuild the grounded fit on the remaining 7, predict the dropped sensor's full series. The architecture is **only earning its keep** if:

- LOO RMSE at T1 < 9.45 °C (M9 baseline)
- LOO RMSE at T2 < 7.40 °C (M9 baseline)
- LOO improvement holds on ≥ 4/7 fixtures in the sweep, not just `BA3C_0946`

**Why this is the right gate:** in-sample fit improvement is cheap with extra DOFs; sensor grounding adds 5–7 effective DOFs (one Dirichlet per anchor). A naive PDE with 7 interior anchors will *always* fit the training sensors near-perfectly. The honest test is whether information at anchor k generalises to held-out sensor j — which is exactly what a well-posed forward model with correctly-inferred α(x,t) should give us, and is exactly what a misspecified model cannot fake.

**Sweep RMSE budget:** 7-fixture mean RMSE < 4.5 °C (M9 sweep mean is currently ~6.2 °C per the M21 turnover) is the headline number to report up to the flagship.

---

## Bottom line

- **Build path:** scipy+sparse 1D-cellular pilot (Pilot 1), 500 LOC, ~5 days dev, ~5 min/fit. Falsifiable in one mission via LOO.
- **Defer:** 2D, parameter fields, smoothness priors, JAX. All conditional on Pilot 1 passing the LOO gate.
- **Reject:** FEniCS/Firedrake (Windows install pain not worth it at this scale).
- **Total cost to a verdict:** ≈ 1 engineer-week. Worst-case downside is one stand-down mission and a documented null result.
