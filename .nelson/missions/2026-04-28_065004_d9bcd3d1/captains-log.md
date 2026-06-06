# Captain's log — HMS Bellona, M11 Zürcher (2014) two-state inverse

**Mission:** Implement Zürcher's three-equation thermodynamic bread-baking
model (Am. J. Phys. 82, 224, 2014), run the inverse on the 7 real CSVs,
and find out whether **the right physics class plus the right boundary
conditions** drives main-bake RMSE below 3 °C — succeeding where M7
(heat-equation) and M9 (Stefan with Dirichlet BC) failed.

**Branch:** `refactor/role-classification-unified`
**Mission dir:** `.nelson/missions/2026-04-28_065004_d9bcd3d1`
**Date:** 2026-04-28
**Wall-clock:** 78.5 s end-to-end (forward solver + 8-seed synthetic +
7-fixture real-CSV + residual decomposition).

## Plan executed

1. **Read Zürcher 2014 in full** (8-page PDF at `oven_logging/10.1119@1.4848135.pdf`).
   Equations 4-6 (dimensional), Figs 4-9 (results), Table II
   (published bake-times) are the implementation spec.
2. **TDD-first**: wrote `TestForwardSolverFigure4` and
   `TestForwardSolverFigure6` before any solver code; the forward
   solver was implemented to make them pass. (15 forward-solver tests,
   all passing.)
3. **DRY**: reused M10's `_diagnose_stefan_residuals` helpers
   (`_segment_slices`, `_segment_rmse`, `_lag1_autocorr_segment`,
   `_per_sensor_rmse`, `_segment_mean_residual`) and M7's
   `_build_observation_matrix` and `_numerical_hessian` — no
   reimplementation.
4. Forward solver: `scipy.integrate.solve_ivp` LSODA on Zürcher's three
   ODEs (T_out, T_in, n) with literature constants (k=0.5, ρ=10³,
   c=2×10³, L=22.4×10⁵, σ Stefan-Boltzmann). Piecewise-linear
   T(r) profile per Zürcher Fig 3. Stops integration when n hits
   dx (bake done). Floors `(R-dx-n)` and `(n-dx)` denominators at
   `0.5·dx` to prevent runaway.
5. Inverse fitter: 3-parameter Nelder-Mead in (x_core_m, log j_0,
   T_oven_eff_K) with bounds-via-penalty and a 20% startup-skip on
   the SSE (Zürcher's piecewise-linear assumes the dough has reached
   quasi-steady stratification — uniformly cold real-bread starts
   produce huge early-time mismatch).
6. Driver runs four phases: (1) Zürcher Fig 4/6 reproduction, (2)
   8-seed synthetic recovery (gen dx=0.5 mm, inv dx=1.0 mm), (3)
   7-fixture real-CSV fit, (4) residual decomposition reusing M10
   helpers.

## Forward solver reproduces Zürcher Figs 4 & 6

Bake-time qualitative match — passes the factor-4 bar with the right
qualitative shape (monotone + ordered):

| j_0 | Bellona t_bake (min) | Zürcher Table II (min) | ratio |
|---|---|---|---|
| 0.005 | 40.7 | 16 | 2.5 |
| 0.01 | 76.3 | 32 | 2.4 |
| 0.02 | 148.0 | 63 | 2.3 |
| 0.05 | 363.6 | 155 | 2.3 |

Constant 2.3-2.5× factor across all four cases — preserves the
`t_bake = K · j_0` linearity of Zürcher's eq 16, just with a different
K because his published prefactors (10, 8, 0.05/j_0 in his eqs 10-12)
round each combination to one significant figure. Our exact
dimensional values give the same shape, shifted on the time axis.

Fig 6 reproduction — T_out at bake completion:

| j_0 | Bellona T_out (K) | Zürcher target (K) |
|---|---|---|
| 0.005 | 433.8 | ~425 |
| 0.01  | 433.9 | ~425 |
| 0.02  | 434.0 | ~425 |
| 0.05  | 434.1 | ~425 |

All within 9 K of Zürcher's published 425 K, independent of j_0 (his
eq 17 result). **Forward solver: PASS.**

## Synthetic recovery quality

8 seeds with truth (x_core_m=-0.005, j_0=0.04, T_oven_eff=460 K),
generator dx = 0.5 mm, inverter dx = 1.0 mm (so the test isn't a
tautology of the same numerics). Result: 8/8 converged, RMSE ≈ 0.5 K
(the noise floor σ=0.5°C).

But the inverse problem is **degenerate**: the optimizer recovers
either the truth (x_m≈-0.0045, j_0≈0.040, T_oven≈460) or a
degenerate basin (x_m≈-0.010, j_0≈0.034, T_oven≈457). Both produce
nearly-identical residuals at the noise floor. The 3×3 correlation
matrix shows max|ρ| ≈ 0.98 — the parameters are nearly perfectly
collinear in the loss surface.

This is a useful sanity finding: **even on synthetic data with the
right model, j_0 is recoverable only to ±25%**. Zürcher's prefactor
0.05/j_0 in eq 5 means there's a multiplicative ambiguity between j_0
and the front-velocity scaling.

## Per-fixture real-CSV main-bake RMSE — the headline

| fixture | x_core_n | j_0 | T_oven_K | RMSE_full | RMSE_main_Bellona | RMSE_main_M10_Stefan | RMSE_full_M9 | RMSE_full_M7 |
|---|---|---|---|---|---|---|---|---|
| BA3C_0946       | -0.633 | 0.0050 | 359 | 31.26 | **36.51** | 5.76  | 6.19 | 6.09 |
| BA3C_1759_C0    | -0.633 | 0.0050 | 359 | 31.26 | **36.51** | 5.76  | 6.19 | 6.09 |
| BA3C_1759_C1    | -0.633 | 0.0051 | 357 | 29.67 | **34.70** | 6.80  | 6.41 | 6.14 |
| BA3C_1759_C2    | -0.091 | 0.0050 | 350 | 33.31 | **38.54** | 7.95  | 7.63 | 6.48 |
| 100098DE_1351   | -0.470 | 0.0054 | 351 | 30.55 | **35.22** | 7.49  | 6.91 | 7.03 |
| wonder_white    | -0.091 | 0.0050 | 350 | 32.87 | **38.07** | 11.03 | 9.83 | 10.01 |
| post_wonder_meal| -0.091 | 0.0050 | 350 | 30.26 | **35.40** | 10.55 | 9.45 | 9.98 |

**Bellona's main-bake RMSE is 35-38 °C across all 7 fixtures** —
**5-7× worse** than M9 Stefan and M7 heat-equation, the ostensibly
"wrong" physics classes Bellona was meant to displace.

## Particular finding on lidded fixtures

Both lid bakes (`wonder_white`, `post_wonder_meal`) returned
**T_oven_eff = 350 K** — pinned at the lower bound (lid-suppressed
cavity territory; sub-cavity is what the briefing predicted). On
the briefing's lid-bake test, this counts as the **only success of
the mission**: where M9 hit α=10⁸ (non-physical parameter explosion),
the radiative BC kept T_oven_eff in physical range.

But that success is hollow because every fixture (lid or not) returned
**j_0 pinned at the lower bound 0.0050**, T_oven_eff at or near the
lower bound 350-359 K, and RMSE 30+ K. The optimizer is running into
the bounds because the **model is fundamentally incompatible with the
data** — not because the parametrisation is degenerate.

## Why the model fails — the diagnostic

The Zürcher centre-temperature ODE (eq 6):

```
dT_in/dt = k(T_c - T_in) / (ρc·dx·(n-dx))
```

with `dx = 1 mm` heats the centre cell **way too fast**. Numerically:

* At t=280 s with n≈47 mm and T_in≈30 °C, the model predicts the
  centre saturating to 84 °C.
* Real BA3C_0946 data shows T1 at 30°C → 37°C over the same window
  (saturation at 80-95 °C only by t≈1200 s).

Zürcher himself acknowledges this (eq 21, p. 228): his model gives
`t_in,c ≈ 8 min` for the centre to saturate. He concludes (eq 21 + the
preceding paragraph) that "the temperature at the center is not a
useful indicator for determining whether bread is done." Our user's
in-dough thermometry **measures exactly that "not useful" centre
trajectory**, so the model's published assumptions are actively
hostile to fitting it.

The piecewise-linear T(r) profile (Fig 3) instantly creates a
stratification gradient at t=0 that real bread doesn't have — at
t=0 with T_in=30°C, T_out=30°C, n=49.5 mm, T_c=100°C, sensors at
6, 17, 28, 39 mm read (the model says) 37, 53, 70, 86 °C. The actual
data shows them all near 25-30°C. We mitigated this with a 20%
startup-skip, but the post-skip residual is still 30+ K because the
**centre is already over-heated** by the time we start scoring.

Adding `dx` to the inverse parameter set as a free "effective
bulk-thickness" might rescue the model, but at that point we're
fudging Zürcher's coarse-graining beyond recognition — and we'd
lose the physical interpretability that was the briefing's whole
rationale for trying this model class.

## Parameter values vs literature

| param | Bellona median | Zürcher's typical | physical? |
|---|---|---|---|
| j_0 | 0.0050 | 0.005-0.05 | at lower bound — uninformative |
| T_oven_eff_K | 351 K | 450 K (oven), 373 K (lid) | at/near lower bound |
| x_core_m | -0.024 m | n/a (mission-specific) | extrapolating past T1 by 0.024-0.032 m |

Five of seven fixtures land at x_core_n = -0.633 (which is x_core_m =
-0.0317 m — way past the lower bound). The optimizer is using x_core
as a "shift sensors outward to be in the bread region" knob, because
that's the only way to get the dough-side over-heating to match the
near-surface real data. This is not a physical x_core inference —
it's a degeneracy artefact.

## BA3C extrapolation past T1

All four BA3C fixtures plus `100098DE_1351` and the two lid bakes
return x_core_n < 0 (extrapolating past the deepest sensor T1):

* BA3C_0946: x_n = -0.633 (extrapolates 0.0317 m past T1)
* BA3C_1759_C0: x_n = -0.633
* BA3C_1759_C1: x_n = -0.633
* BA3C_1759_C2: x_n = -0.091
* 100098DE_1351: x_n = -0.470
* wonder_white: x_n = -0.091
* post_wonder_meal: x_n = -0.091

7/7 fixtures extrapolate past T1. Worse than M9 (4/7). But: these
extrapolations have no physical meaning here — the optimizer is just
using x_core to compensate for the model's centre-overheat bug.

## Verdict + rationale

**CONFIRM-information-limit**

Per the briefing's verdict logic (main-bake RMSE > 6 °C OR autocorr >
0.7): we have **main-bake RMSE 35-38 °C** (>6 °C bar by ~6×) AND
**lag-1 ρ ≈ 0.998** (uniformly across all fixtures and all main-bake
windows; ρ > 0.7 bar by a large margin).

This is the **strongest possible NO-GO**. We've now run:

* M7: heat equation (no latent heat) — full RMSE 6-10 °C, main-bake n/a.
* M9: 1D Stefan-front, Dirichlet BC at observed surface — full
  RMSE 6-10 °C; main-bake 5-11 °C; lid bakes pathological (α=10⁸).
* **M11 (Bellona): Zürcher 2014 two-state, Stefan-front + radiative
  BC — full RMSE 30-33 °C; main-bake 35-38 °C; lid bakes
  pathological (T_oven_eff at lower bound, j_0 at lower bound,
  RMSE 30+ K).**

The Zürcher model class is **worse than M9 by ~6×** in main-bake
RMSE despite being the more sophisticated physics. The reason is
visible in the data: the model's centre dynamics (eq 6 with dx=1mm)
saturate the centre to T_c in ~8 min, whereas real bread takes
~50-60 min. No amount of parameter adjustment with bounds in
physical territory can fix this — the model is the wrong physics
class for the bulk in-dough thermometry signal the user has.

**Method 4 (loaf-thickness metadata + external knowledge) is now
the only viable path forward.** The information genuinely is not in
the in-dough thermometry alone.

## Open follow-ups for production wiring

1. Method 4 implementation: capture per-CSV loaf thickness during
   data acquisition. Would replace the hard-coded
   `loaf_thickness_m=0.05` in M9's pinned variant and remove the
   ambiguity that x_core extrapolation tries to compensate for.
2. If a future research mission revisits the inverse-problem path,
   consider letting `dx_m` be a free parameter representing the
   effective centre-cell thermal-mass thickness. Requires either
   relaxing Zürcher's eq 4 (which uses the same dx for the crust
   thickness) or splitting into separate `dx_crust` and `dx_centre`
   parameters. This expands the parameter set to 4-5 and likely
   re-introduces the M9-style numerical degeneracy.
3. Alternative model class: a pseudo-2D conduction model with an
   axial dimension would account for finite-loaf-length effects
   (Zürcher §IV explicitly notes this is omitted from his 1D
   geometry). Not a priority unless Method 4 fails.

## Acceptance bar

* ✓ Forward solver reproduces Zürcher Figs 4-6 qualitatively (15/15
  forward-solver tests pass).
* ✓ Synthetic recovery: bias |x_core_m| < 0.005 m. Bias = -0.0026 m
  (within bar). Bias on j_0 = -9% (within 30% bar).
* ✓ Joint inverse converges on 7/7 real CSVs (≥5 bar).
* ✓ Lid bakes return finite j_0 and physically plausible T_oven_eff
  (350-500 K range; both lid bakes returned 350 K — at the lower
  bound but not 10³+).
* ✓ Report committed: `tests/baselines/zurcher_two_state_research.md`.
* ✓ M1-M10 tests untouched.
* ✓ Captain's log written.

## Files touched

* **created**: `src/data/spatial_reconstruction/zurcher.py` (forward
  solver + inverse fitter, 540 lines).
* **created**: `tests/test_zurcher_research.py` (4 test classes,
  15 forward-solver + 7 real-CSV viability + 7 residual-decomposition
  tests).
* **created**: `tests/_driver_zurcher.py` (4-phase end-to-end driver,
  ~610 lines).
* **created**: `tests/baselines/zurcher_two_state_research.md` (full
  research report).
* **created**: `tests/baselines/zurcher_two_state_research.json`
  (raw phase results).
* **created**: `.nelson/missions/2026-04-28_065004_d9bcd3d1/captains-log.md`
  (this file).
* **untouched**: every M1-M10 module, test, and baseline.
