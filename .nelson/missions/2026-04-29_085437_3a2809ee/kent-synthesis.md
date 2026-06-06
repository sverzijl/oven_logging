# HMS Kent — M22 Task 4: Synthesis

**Mission:** Reconcile Astute (literature), Audacious (viability), Defender (complexity) against the user's clarified goal — **derived field quantities (moisture-front position, surface position, core position over time)**, not training-sensor RMSE.

**Verdict (one-liner): STAND-DOWN on a dedicated cellular pilot. Land M2a + per-snapshot Stefan as a time-evolving derived-quantity tracker.** The cellular architecture's only mathematically defensible output — a smooth 1D-along-probe time-evolving moisture-front trace — is recovered for ~5% of the cost by running the existing Stefan classifier per snapshot and post-smoothing.

---

## 1. Three-report verdict summary

**Astute (literature).** No published paper inverts both α(x,y,t) and source(x,y,t) from interior sensors; no paper reconstructs a 2D field from a 1D sensor line. The closest cousins (Bakhshaei 2024, Reddy 2024, Li 2025) use 25–100+ sensors and invert *boundary* fluxes, not distributed internal fields. Identifiability theorems (Beck/Blackwell 1985, Alifanov 1994) are unanimous: a co-linear sensor line cannot identify transverse variation; smoothness only fills the null space with the prior's mean. Astute's recommendation: **reduce to 1D T(s,t) along the probe axis** with thermodynamic interpolation transverse.

**Audacious (viability).** The cellular architecture relocates rather than breaks the M13 information limit. Naive 2.8 M unknowns are reduced by smoothness regularisation to ~250 effective DOFs, of which only ~8 are truly identified from the 8 sensors — the other ~242 are smoothness-imputed. The smoothness-equals-parametric equivalence theorem holds: cellular-with-smoothness is mathematically identical to kernel-ridge regression in `(L/ℓ)²` basis modes, with `min((L/ℓ)², N_sensor)` rank. Time-varying α is real but is captured equally by piecewise-time parametric fitting. **STAND-DOWN on 2D, HYBRID-PILOT on 1D-cellular, BUILD-PARAMETRIC piecewise-time first.**

**Defender (complexity).** A 1D-cellular pilot is feasible: ~500 LOC delta on the existing `heat_equation.py` + `stefan_inverse_v3.py` scaffolding, scipy.sparse + handwritten FDM, ~5 min/fit, ~5 dev-days. JAX is only required if we scale to field inversion. FEniCS rejected for Windows install pain. Pilot success metric (as written): main-bake RMSE < 4.0 °C and LOO improvement on ≥4/7 fixtures.

---

## 2. Re-framing through the user's clarified goal

The user is asking for **time-evolving derived quantities along the probe axis** — moisture-front position s_front(t), surface position s_surface(t), core position s_core(t) — not better training-sensor RMSE.

This is consequential for each report:

- **Astute** explicitly recommended reducing to 1D-along-probe — exactly the geometry the user's derived quantities live on. The 2D-from-1D-line objection evaporates because the user is not asking for 2D output.
- **Audacious's** equivalence theorem becomes less damaging: yes, cellular = kernel ridge regression in a basis, but the **derived quantities** (positions of isothermal surfaces, latent-heat fronts) can still be physically meaningful outputs of a smoothed field, even if the underlying field is just basis-function smoothing of 8 sensor traces.
- **Defender's** success metric (main-bake RMSE < 4.0 °C) is the **wrong gate** for the reframed goal. The right gate is whether the derived-quantity traces are smooth, physically plausible, and consistent with M2a's per-snapshot Stefan estimates.

The pivotal question: **does a 1D cellular pilot give us derived quantities that the existing M2a + Stefan classifier doesn't already provide?**

---

## 3. Empirical answer: M2a + per-snapshot Stefan already produces all three derived traces

The existing pipeline in `src/data/spatial_reconstruction/` already exposes:

- `ProfileFit.x_stefan_front` (from `stefan.py`) — the position along the probe where T(x) crosses 100 °C, i.e. the **moisture/evaporation front**.
- `SpatialAssignment.core_assignment.position_normalised` — inferred core position in [0,1].
- `SpatialAssignment.surface_assignment.position_normalised` — inferred dough/air interface position.
- `SpatialAssignment.lid_assignment.position_normalised` — inferred lid position.

These are computed per-snapshot today (one classification per curve). Running the classifier **per timestep** (or every k-th timestep) immediately yields time-series s_front(t), s_surface(t), s_core(t) without any new physics, PDE, or inversion machinery. A simple Savitzky–Golay or spline post-smooth across t enforces the temporal continuity the user wants.

**This is not hypothetical — it is a ~50 LOC wrapper over `classify()`.** The total cost is one mission of order 1–2 days, vs Defender's 5 dev-days for a 1D cellular pilot that would, by Audacious's equivalence theorem, produce the *same smoothed traces* up to a different smoothing prior.

The cellular architecture's marginal contribution over per-snapshot-Stefan-plus-temporal-smoothing is:

1. **Joint space-time smoothness coupling.** Cellular enforces ∂_t α and ∇α together; per-snapshot-Stefan + post-smooth treats them independently. This is a real but second-order benefit.
2. **PDE-consistent interpolation between snapshots.** Cellular's heat equation provides physical interpolation; per-snapshot-Stefan's spline interpolation is not physics-aware. Again real, second-order.
3. **Built-in uncertainty propagation.** Cellular's Hessian gives joint CI on (s_front, s_surface, s_core); per-snapshot-Stefan gives independent per-snapshot CIs.

None of these three benefits justifies 5 dev-days plus a 50× per-fit cost increase plus the Audacious-flagged risk that the underlying field is smoothness-imputed fiction.

---

## 4. Verdict: STAND-DOWN on cellular pilot. Build M23 = "Stefan-per-snapshot temporal tracker."

**M23 scope (1–2 days):**

1. Add `classify_temporal(df, sample_period_ms, stride_s=10)` to `src/data/spatial_reconstruction/classifier.py` — runs `classify()` on rolling windows, returns `TemporalAssignment` with arrays s_front(t), s_surface(t), s_core(t), confidence(t).
2. Post-smooth with Savitzky–Golay (window ~30 s) to suppress per-snapshot jitter; flag windows where Stefan fit fails to converge.
3. Validate on `BA3C_0946`: produce time-evolving traces; visually check monotonicity (front moves inward), continuity, agreement with the M2a single-snapshot estimate at the snapshot time.
4. Compare to M2a + Method 4 stub: confirm M23 is a strict superset (gives temporal evolution that the static estimate can't).
5. Write up as the user-facing "moisture-front tracker" deliverable.

**Pilot success metric** (in user's terms):

- s_front(t) is monotone decreasing (front moves inward) on ≥6/7 fixtures.
- s_core(t) at the canonical evaluation snapshot agrees with M2a's static estimate to within 0.05 normalised position.
- s_surface(t) is continuous (no jumps > 0.1 normalised position between adjacent windows).
- Total runtime < 30 s per fixture.

**Affirmation of M18 production landing:** the M18 production path (M2a piecewise classifier + Stefan opt-in + Method 4 geometric stub) is the right production architecture. M23 adds the temporal-tracking wrapper on top without disturbing it.

---

## 5. Key risk

**The user may interpret "stand-down" as "we gave up."** Frame M23 as the *positive* deliverable that actually answers their clarified question — the cellular architecture was a candidate solution; the simpler per-snapshot-temporal wrapper is a better solution to the same problem. The 5.7 °C RMSE floor is irrelevant; M23 produces derived quantities, not predictions.

Secondary risk: per-snapshot Stefan may fail to converge in early-bake (T < 100 °C everywhere, no front) or late-bake (front off the probe). Mitigation: report confidence(t) and gracefully degrade to piecewise-only when no 100 °C crossing exists.

---

*Word count: ~780.*
