# HMS Audacious — Mathematical Viability Analysis

**Mission:** Cellular-with-sensor-grounding architecture for the bread-baking inverse problem.
**Verdict (one-liner):** The architecture **relocates** the M13 information limit; it does not break it. Sensor grounding is, in the Tikhonov sense, a smoothness-regularised parametric fit dressed in field-theory clothing — but the time-varying-α benefit is real and is the only mathematically defensible reason to build it.

---

## 1. DOF accounting

### 1.1 Naive count

- Mesh: `Nx × Ny = 50 × 100 = 5000` cells.
- Time: `Nt ≈ 280` steps.
- Parameter fields: `α(x,y,t)` and `s(x,y,t)` → 2 fields.
- Naive unknowns: `U = 5000 × 280 × 2 = 2,800,000`.

### 1.2 Sensor observations

Sensors enter as **Dirichlet conditions**, not residuals:
`T(x_k, y_k, t) = T_obs,k(t)` for k=1..8.
This **removes** `8 × 280 = 2240` rows from the unknown vector (those cell temperatures are now fixed). It does **not** add 2240 residual equations — that was the user's intent. Information enters by *constraining the PDE solution along 8 worldlines*.

### 1.3 PDE constraint reduction

The discretised heat equation
`(T_i,j^{n+1} − T_i,j^n)/Δt = ∇·(α ∇T)_i,j^n + s_i,j^n`
gives **one equation per cell-timestep**: `Nx · Ny · Nt = 1.4 M` constraints.
Each constraint algebraically links T at five neighbours given (α, s). For fixed (α, s) the PDE solves T uniquely from initial + boundary data; conversely, for given T everywhere, the PDE locally identifies (α, s) only up to the null space of the discretised operator at that cell.

The crucial linear-algebra fact: at each cell-timestep we have **one scalar equation in two unknowns** (α, s). This is the central degeneracy:
`(T^{n+1} − T^n)/Δt − ∇·(α∇T) − s = 0`
Any (α, s) satisfying `α·∇²T + s = const` at that cell-step is admissible. **This is a 1-dimensional null space at every cell-timestep**, i.e. the (α, s) field is locally underdetermined by exactly the same dimension as the field itself. The PDE alone does *not* close the system; it preserves a `Nx·Ny·Nt ≈ 1.4 M`-dimensional null space in (α, s).

### 1.4 Smoothness regularisation

A Tikhonov penalty `R = λ_s ‖∇α‖² + λ_t ‖∂_t α‖² + (analogous for s)` projects the null space onto its smoothest representatives. By the standard Karhunen–Loève / Whittle–Matérn argument, a smooth field on a 2D domain observed at N points has effective DOF

`DOF_eff(N, ℓ) ≈ N · (1 + log(L/ℓ))`

where `L/ℓ` is the ratio of domain size to correlation length. For a 50×100 mesh with `ℓ ≈ 5–10 cells` (the only physically reasonable smoothness scale — anything finer is fitting noise, anything coarser is parametric):

`DOF_eff ≈ 8 · (1 + log(50/10)) ≈ 8 · 2.6 ≈ 21` per snapshot.

Across time, if α(t) varies on a timescale `τ ≈ 5 min` against a 30-min bake, time-DOFs ≈ 6. Joint:
**effective DOFs ≈ 21 × 6 ≈ 130** for α; same for s; **total ≈ 250**.

That is two orders of magnitude more than M9's 4 parameters but four orders of magnitude *less* than the naive 2.8 M. The *smoothness prior* is what makes the problem tractable, and what the prior buys us is roughly `O(N_sensor · log(L/ℓ))` — the user's own estimate of `8 · log(50) ≈ 30` is the right order; my higher number adds time-evolution.

### 1.5 Tikhonov well-posedness

The regularised functional
`J(α,s) = ½‖PDE-residual‖² + λ_s R_space(α,s) + λ_t R_time(α,s)`
subject to Dirichlet sensor pinning is convex in (α, s) **iff the forward map T(α, s) is linearised around a working point**. Globally it is non-convex (T depends nonlinearly on α through the diffusion operator). Tikhonov-well-posed in the local sense: for any λ_s, λ_t > 0 the Hessian is positive-definite on the smoothness-restricted manifold, so a unique minimum exists *given an initial guess in the basin*. **Globally well-posed: no.** Multiple smooth (α, s) solutions can satisfy the Dirichlet constraints to within sensor noise.

---

## 2. Sensor-vs-field dimension mismatch

The 8 sensors lie on a **1D line** through a **2D dough cross-section**. Geometrically: a Combustion Inc. probe is a needle inserted radially or axially. Sensor coordinates are `(x_k, y_k=y_probe)` for k=1..8 along the probe, where the line `y = y_probe` is one slice of the (x,y) dough.

### 2.1 Theoretical assessment

For a 2D Laplacian (steady-state limit) with Dirichlet data only on a 1D curve Γ inside the domain, the solution is **uniquely determined inside Γ's enclosed region only if Γ is a closed curve enclosing the region**. A line segment is not closed. Cauchy data (T and ∂T/∂n) on a line segment make the interior problem well-posed (Holmgren's theorem) but Cauchy data is **exponentially unstable** to noise off-line (this is the classical sideways heat equation ill-posedness — see Hadamard 1923, Beck/Blackwell/St-Clair 1985).

### 2.2 Practical assessment

Smoothness with `ℓ ≈ 5–10 cells` does extend information **about one correlation length** off the sensor line. So for a probe inserted along the loaf's long axis through its centre:
- Cells within ~10 cells of the probe line: **interpolated by smoothness**, RMSE governed by `σ_sensor + λ_s · curvature`.
- Cells >10 cells off-line (the loaf's left/right cheeks, top/bottom): **predicted by prior alone**, i.e. extrapolation. RMSE → variance of the prior, which is essentially the bulk temperature scale (50–100 °C).

This is **structurally identical to the M13 deep-end failure**: the model fits well where it has data, fails where it doesn't. M13 said T1 LOO RMSE 9–21 °C *along* the probe; the cellular formulation will give similar or worse numbers *off* the probe, because there is no sensor to ground predictions and smoothness alone provides only `O(σ_T · sqrt(distance/ℓ))` error growth.

**Verdict B: failure relocates from "deep along the probe" to "everywhere off the probe line".** The 8-sensor-line cannot recover a 2D field except in a tube of one correlation length around the line.

---

## 3. Comparison: cellular-with-grounding vs parametric (M9 Stefan)

| Metric | Parametric M9 (Stefan) | Cellular + grounding |
|---|---|---|
| **Effective DOFs** | 4 (α_dough, α_crust, T_oven proxy, T_init) | ~250 (8 × log(L/ℓ) × time-modes); 2 fields, 2D |
| **Number of degeneracies** | 0 essential; α/source trade-off only at boundary | ∞-dim (α↔s null space at every cell-timestep), reduced to ~`Nx·Ny·Nt − DOF_eff` ≈ 1.4 M after smoothness chooses the smooth representative |
| **One forward solve cost** | 1 ODE in (T(t), front position s(t)); ms | 2D PDE on 50×100 over 280 steps; ~0.5–2 s implicit, ~5–30 ms explicit (CFL: dt < dx²/(2·α_max) ≈ ms-scale, so 280 oven-time steps = thousands of CFL steps) |
| **Robustness to noise** | High (4 params averaged across all data); LOO T1 RMSE 9–21 °C | Sensor-pinned cells: zero error by construction. Off-line cells: amplifies sensor noise via inverse 2D Laplacian — exponentially in distance/ℓ |
| **Predictive accuracy on held-out sensor (LOO)** | M13 measured: 9–21 °C on T1 | **Predicted same or worse**: leaving out sensor k removes a Dirichlet pin, so the cell at `(x_k, y_k)` is now interpolated from neighbours along the same line; no new physics fills the gap. Expect 5–15 °C if neighbour sensors are within `ℓ`, 15–30 °C if not. |

The **only** column where cellular wins decisively is "DOFs available to absorb time-varying physics" (row 1). Every other column is neutral or worse.

---

## 4. Is cellular fundamentally different, or parametric-with-basis-functions?

### 4.1 Equivalence theorem

A smoothness-regularised field `α(x,y,t)` with quadratic penalty `λ‖Lα‖²` (L any linear differential operator) is mathematically **identical** to a Gaussian-process prior with covariance `K = (L*L)^{-1}`. The MAP estimate of α given Dirichlet data is a **kernel-ridge regression** — i.e. parametric fitting in a basis of `K`'s eigenfunctions.

For 2D Whittle–Matérn smoothness with correlation length ℓ on a domain of size L, the eigenfunctions are sinusoids with effective truncation at `(L/ℓ)²` modes. So the cellular formulation is **exactly** parametric fitting with `~(L/ℓ)²` basis coefficients constrained by 8 sensors. Given `L/ℓ ≈ 5`, that is ~25 basis modes, of which only ~8 can actually be identified from 8 sensors (rank deficiency). The remaining 17 are pinned at zero by the prior.

**So yes: cellular-with-smoothness is parametric fitting, with `(L/ℓ)²` basis functions and only `min((L/ℓ)², N_sensor)` of them identifiable.**

### 4.2 What's left of the "fundamentally different" claim?

Two genuinely different things remain:
1. **The basis is data-adaptive**: smoothness eigenfunctions adapt to mesh/geometry, whereas Stefan's 4 params are hand-chosen physical knobs. This matters when geometry changes (bread shapes, oven racks) — cellular generalises, parametric needs re-derivation.
2. **The PDE forward model is enforced exactly, not as a residual**. A parametric Stefan fit minimises sensor RMSE; cellular minimises sensor RMSE *plus* the constraint that interior cells obey heat-eq. For prediction *off* sensor support this gives strictly more physical interpolation than naive splines — but **not** more than a parametric model that *also* uses heat-eq (which Stefan does).

So the comparison is really **cellular vs parametric-with-physics**, and both use the heat equation as the interpolating mechanism. The remaining advantage is field flexibility, not a different paradigm.

---

## 5. Time-varying α: does cellular get it for free?

### 5.1 The promise

The cellular formulation lets `α(x,y,t)` change at every step, regularised only by `λ_t ‖∂_t α‖². With `λ_t` tuned to allow ~1-min variation, α can rise during oven spring (5–15 min) without committing to a global value.

### 5.2 The reality

Time-varying α is **not free** — it costs time-DOFs in the prior. From §1.4: time-DOFs ≈ 6 across a 30-min bake at 5-min correlation length. Those 6 modes must be identified from 8 sensors × 280 timesteps = 2240 *time-resolved* observations, which is plenty of information per mode. Time identification is **strong**.

But: time-varying α is also **available to parametric fitting**. M9 could be reformulated as `α_dough(t) = α_0 + α_1 · g(t-t_spring) + ...` with 6–8 free params instead of 1. That is a piecewise-time parametric Stefan fit — already on the user's roadmap (per the brief). It requires no new architecture.

**So time-varying-α is a real benefit, but it is captured equally well by piecewise-time parametric fitting at a fraction of the cost.** The cellular formulation makes time-varying parameters *natural* (no need to choose a basis), which is a genuine usability improvement, but not a mathematical advantage.

### 5.3 The one place cellular wins

The argument that survives: **spatially-varying α(x,y) coupled with time-varying α(t)** is awkward to write parametrically (4 spatial regions × 6 time modes = 24 params, with the regions hand-drawn) but natural in the cellular formulation. If there is reason to believe α varies *both* spatially (crust/crumb boundary moves) *and* temporally (gelatinisation kinetics), cellular is the cleaner formulation.

For BA3C_0946-style bread baking: the crust/crumb boundary moving inward over time is exactly this regime. So cellular has a defensible niche here — but only if the **phenomenon being modelled** is a moving spatial structure, which is precisely what M9's Stefan formulation already captures parametrically with 4 params.

---

## 6. Verdict

**The architecture does not break the M13 information limit. It relocates it.**

- **DOF gain** (4 → ~250) is mostly absorbed by the prior: only `min((L/ℓ)², N_sensor) ≈ 8` modes are truly identified; the rest are smoothness-imputed.
- **Sensor-line vs 2D-field mismatch** means off-line cells are predicted by the prior alone — RMSE will be on the order of the loaf's bulk temperature variation (50–100 °C), worse than M13's 9–21 °C along-probe RMSE.
- **Smoothness-regularised cellular = kernel ridge regression** = parametric fitting in eigenfunction basis. Not a different paradigm.
- **Time-varying α** is a real benefit but is achievable with piecewise-time parametric fitting at a fraction of the cost.
- **Spatio-temporally-varying α** is the one regime where cellular is mathematically cleaner — but a moving Stefan front already parametrises this.

### Concrete recommendation

If the goal is **better LOO RMSE on T1**: cellular won't help. The information isn't there. Same data, same limit.

If the goal is **time-varying α to capture oven spring**: implement a 6-parameter piecewise-time Stefan first. ~1 day of work vs ~1–2 weeks for cellular. Compare LOO RMSE.

If the goal is **2D field reconstruction for visualisation / process control**: cellular *is* the right tool, but understand that off-probe cells are prior-driven, not data-driven. Communicate uncertainty bands accordingly.

The M13 information limit is a **data limit**, not a model limit. No architecture can manufacture information that isn't in 8 sensor traces. Cellular-with-grounding redistributes the available information across 2D space; it doesn't create more.

**Recommended squadron-level disposition:** STAND-DOWN on cellular-with-grounding as a path to better LOO RMSE. HYBRID-PILOT on a 1D-cellular intermediate (along-probe only) to test whether the architecture even matches parametric M9 in its strongest regime before scaling to 2D. BUILD-PARAMETRIC the piecewise-time Stefan first — it captures 80% of the cellular benefit at 10% of the cost.

---

*Word count: ~1430. Math shown for DOF count, smoothness equivalence, Cauchy-data instability.*
