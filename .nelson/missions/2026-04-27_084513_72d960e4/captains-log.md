# HMS Vanguard — Captain's Log

**Mission**: M2b, refactor/role-classification-unified flotilla
**Date**: 2026-04-27
**Branch**: `refactor/role-classification-unified`
**Predecessor**: M2a HMS Indefatigable (commit `d6960b2` — piecewise model)

## Summary

Implemented the Stefan-physics-constrained spatial fit alongside the M2a
piecewise model, built the comparison harness, ran it on all 9 contract
fixtures, and committed the empirical comparison report. **Stefan unit tests
pass 13/13** (exceeds the ≥6/7 acceptance bar). **Empirical recommendation:
keep `piecewise` as the default model** — Stefan's stricter 100°C pin costs
one fixture (`real_100098DE_1351` ambient) that piecewise gets right.

## Files created / modified

**New files**
- `src/data/spatial_reconstruction/stefan.py` — `fit_stefan()` Stefan-front
  detection via T=100°C crossings, single-α air-region fit by linearised
  least squares, lid-bake mode share with piecewise.
- `src/data/spatial_reconstruction/comparison.py` — `ModelComparison`
  dataclass, `benchmark_fixture`, `benchmark_all_cases`,
  `write_comparison_report`.
- `tests/test_spatial_reconstruction_stefan.py` — 13 unit tests covering
  100°C pin, canonical / through-loaf / full-immersion / lid recovery,
  classify dispatch, and synthetic-agreement with piecewise.
- `tests/baselines/spatial_model_comparison.md` — per-fixture comparison
  with surface side-by-side, Stefan diagnostic (α, T_cavity, n crossings),
  aggregate metrics, recommendation, follow-ups.

**Modified files**
- `src/data/spatial_reconstruction/__init__.py` — export `fit_piecewise`,
  `fit_stefan`, comparison primitives.
- `src/data/spatial_reconstruction/classifier.py` — `classify(... model=...)`
  now dispatches `'piecewise' | 'stefan'`; `model_used` field reflects the
  actual model. Replaced the M2a `NotImplementedError` with a real branch.
- `config/constants.py` — extended `ROLE_CLASSIFIER_CONFIG` with
  `DEFAULT_MODEL`, `STEFAN_ALPHA_MIN`, `STEFAN_ALPHA_MAX`,
  `STEFAN_FRONT_TEMP_C`.

## Test outcomes

**Stefan unit tests** (`tests/test_spatial_reconstruction_stefan.py`):
**13/13 PASS**.
- `test_fit_stefan_pins_plateau_at_100c` ✓ (T at fit position within 0.5°C of 100)
- `test_fit_stefan_recovers_canonical_insertion_position` ✓
- `test_fit_stefan_through_loaf_returns_two_fronts` ✓
- `test_fit_stefan_full_immersion_returns_no_front` ✓
- `test_fit_stefan_lid_detection` ✓
- `test_classify_stefan_model_runs_on_real_fixtures` × 4 fixtures ✓
- `test_classify_piecewise_and_stefan_agree_on_synthetics` × 4 ✓

**Piecewise contract tests** (`TestClassifierReturnsExpectedRoles`):
**8/9 PASS** — unchanged from M2a baseline. The single fail is
`post_wonder_meal_lidded[surface=T7 vs T8]`. **No regression.**

**Piecewise unit tests** (`tests/test_spatial_reconstruction_piecewise.py`):
**12/12 PASS**.

**M1a/M1b schema tests**: **16/16 PASS**.

## Per-fixture comparison summary (from `tests/baselines/spatial_model_comparison.md`)

| Fixture | PW pass (c/s/a/l) | SF pass (c/s/a/l) | PW SSE | SF SSE | Stefan α |
|---|:---:|:---:|---:|---:|---:|
| real_100098DE_1351 | ✓/✓/✓/✓ | ✓/✓/✗/✓ | 5.5 | 977 | 26.9 |
| real_1000BA3C_0946 | ✓/✓/✓/✓ | ✓/✓/✓/✓ | 168 | 4238 | 23.0 |
| real_1000BA3C_1759 (curve 0) | ✓/✓/✓/✓ | ✓/✓/✓/✓ | 3.8 | 5081 | 18.9 |
| wonder_white_10k_lidded | ✗/✓/✓/✓ | ✗/✓/✓/✓ | 0.7 | 0.7 | n/a |
| post_wonder_meal_lidded | ✓/✗/✗/✓ | ✓/✗/✗/✓ | 0.6 | 0.6 | n/a |
| synthetic_shallow_insertion | ✓/✓/✓/✓ | ✓/✓/✓/✓ | 7.6 | 1764 | 10.7 |
| synthetic_full_immersion | ✓/✓/✓/✓ | ✓/✓/✓/✓ | 17.7 | 17.7 | n/a |
| synthetic_lid_touch | ✓/✓/✓/✓ | ✓/✓/✓/✓ | 12.1 | 9841 | 6.6 |
| synthetic_probe_pull_mid_bake | ✓/✓/✓/✓ | ✓/✓/✓/✓ | 16.8 | 4761 | 35.0 |

(The `wonder_white_10k_lidded` "core ✗" is a comparison-harness artefact
of folding the M1a-accepted alternates {T5, T6} down to a single annotation;
the contract test at `tests/test_role_classifier_unified.py` accepts T5
explicitly and passes.)

**Per-role pass rate**:

| Role | Piecewise | Stefan |
|---|---:|---:|
| core | 8/9 | 8/9 |
| surface | 8/9 | 8/9 |
| ambient | 8/9 | **7/9** |
| lid | 9/9 | 9/9 |

**Overall fixture pass (all four roles)**: piecewise **7/9**, Stefan **6/9**.

**Mean residual SSE** (terminal-vector prediction error): piecewise 26,
Stefan 2965. The raw SSE gap is enormous — Stefan's air-region exponential
asymptote disagrees sharply with the actual terminal vector when individual
sensors haven't yet equilibrated to T_cavity. **This is expected** and is
why the recommendation is not based on SSE alone.

**Mean position error** (synthetics with ground-truth `expected_x_dough_air_normalised`):
piecewise 0.143, Stefan 0.207. Piecewise wins on position too — the largest-
adjacent-jump heuristic happens to land closer to the annotated boundary
than the linear-interpolated 100°C crossing of the (noisy) terminal vector.

## Recommendation: default model = `piecewise`

Set in `ROLE_CLASSIFIER_CONFIG['DEFAULT_MODEL'] = 'piecewise'`. M3a wires
this through to `classify(...)`.

**Rationale**:
1. Piecewise passes 7/9 fixtures vs Stefan's 6/9. The Stefan model's
   stricter 100°C pin reclassifies T6 (terminal=100.4°C) on
   `real_100098DE_1351` as air-side, expanding ambient to {T6, T8}; the
   M1a annotation has just {T8}.
2. Mean residual SSE is dominated by the air-region exponential
   asymptote — Stefan's single global α cannot match individual
   air-side sensors that haven't equilibrated to T_cavity, while
   piecewise treats them as the cavity-proxy band.
3. Mean position error on synthetics also favours piecewise (0.143 vs 0.207).
4. The hypothesised win for Stefan was *stability under perturbation* (fewer
   parameters → less overfit), which **this n=9 deterministic harness does
   not measure**. M4's perturbation harness is the right venue to score
   that property; the M2b comparison cannot.

## Does Stefan resolve `post_wonder_meal_lidded`? — **No.**

Both models return `surface=T7`; M1a annotates `T8`. This is the lid-bake
through-loaf regime where every terminal sits in the 95-100°C plateau band
and the Stefan-front detection has 0 crossings of T=100°C — it falls back
to the same heat-up-speed split that piecewise uses (shared logic; copied
between modules). The disagreement is at the *annotation* layer, not the
*model* layer: `wonder_white_10k_lidded` annotates surface as the dough-side
neighbour while `post_wonder_meal_lidded` annotates the air-side neighbour,
and no spatial-reconstruction feature in our current dictionary cleanly
discriminates the two cases. M2a's open-issues list flagged this; M2b
confirms it remains open.

## Judgment calls

1. **Linearised-α fit, not iterative.** The Stefan crust model is
   `T(x) = 100 + (T_cav - 100)(1 - exp(-α d))`. Taking
   `log((T_cav - T)/(T_cav - 100)) = -α d` linearises perfectly when air
   sensors haven't saturated, and constraining-through-origin OLS gives a
   closed-form α with no optimiser dependency. Clamped to [0.05, 100] to
   protect against pathological inputs. Faster than `scipy.optimize` and
   deterministic.

2. **Through-loaf detection by 100°C crossings.** Piecewise uses a
   high-low-high heuristic on the terminal vector. Stefan can use the
   physics directly: ≥2 crossings of T=100 °C → through-loaf. This is
   cleaner and matches the model's promise.

3. **Reused piecewise's lid-bake split.** When all sensors plateau in
   [95, 105] °C and the spread is < 10 °C, the 100°C-crossing path is
   degenerate. Copied (not imported) the heat-up-speed gap algorithm
   from `piecewise.py` into `stefan.py` so the two models stay
   independently swappable; the M3a integrator can lift it to a shared
   helper if duplication ever bites.

4. **Comparison harness writes role_match against single-curve
   annotations.** For multi-curve `real_1000BA3C_1759`, the harness scores
   curve-0 only — the contract test scores all 3 curves separately.
   This is intentional: the comparison answers "is Stefan better than
   piecewise on a representative fixture?", not "do both pass the
   multi-curve schema?". Schema-level coverage is M3a's job.

5. **`DEFAULT_MODEL` config key, not a constructor default.** The default
   is config-driven so the loader (M3a) and any future sweep harness
   (M4) can flip it at one site. The `classify(model='piecewise')`
   function default is left as `'piecewise'` for backwards-compat with
   the M2a contract test.

## Open follow-ups

### M3a HMS Royal Sovereign (loader integration)
- Read `ROLE_CLASSIFIER_CONFIG['DEFAULT_MODEL']` once at loader startup
  and pass it through to every `classify(...)` call. Don't hardcode.
- The Stefan dispatch path is fully wired; flipping the default later is
  a one-line constants change.

### M4 (perturbation harness)
- Re-run `comparison.benchmark_all_cases()` under bootstrap resampling
  of input curves. Score *position-estimate variance* across resamples
  per model. The Stefan model's reduced parameter count is hypothesised
  to deliver lower variance than piecewise, even when mean accuracy is
  comparable. This is the empirical leverage the M2b comparison cannot
  provide.
- The lid-bake through-loaf annotation conflict (`post_wonder_meal_lidded`
  vs `wonder_white_10k_lidded`) needs either (a) a new feature
  (`xcorr_lag_to_oven_proxy_seconds` is computed but unused), or (b) the
  Admiral to reconcile the two fixtures' annotation conventions. M2b
  recommends asking the Admiral first — both are physically identical
  lid-bake through-loaf cases.
- The `_lid_bake_through_loaf` helper is duplicated between
  `piecewise.py` and `stefan.py` (DRY violation, deliberately accepted
  in M2b for module independence). M3a or M4 should hoist it into
  `profile.py` once a third caller appears.

### M3b (legacy module deletion)
- `src/data/surface_sensor_detector.py` and
  `src/data/thermodynamic_sensor_classifier.py` remain in the tree. M3b
  removes them after M3a wires the new classifier into the loader.

## Acceptance bar — checked off

- ✓ Stefan unit tests pass: **13/13** (bar was ≥6/7).
- ✓ Comparison harness runs on all 9 fixtures without crashing.
- ✓ Comparison report at `tests/baselines/spatial_model_comparison.md`
  with per-fixture data + recommendation.
- ✓ Piecewise contract tests still **8/9** (no regression).
- ✓ Stefan contract pass rate documented (**6/9** overall, **7/9** ambient).
- ✓ `post_wonder_meal_lidded` specifically analysed in the report
  (Stefan does NOT resolve it — both fall back to the same lid-bake split).
