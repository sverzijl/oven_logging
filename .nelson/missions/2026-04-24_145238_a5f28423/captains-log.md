# Captain's Log — HMS Hood (M4 of flotilla `refactor/expected-bake-time`)

**Mission ID:** `2026-04-24_145238_a5f28423`
**Branch:** `refactor/expected-bake-time`
**Risk tier:** HIGH (Action Station 3 — disturbs Method 2b max-sensor start + NC-1/NC-2 coupling with `_skip_probe_pull_tail`)
**Mode:** single-session + red-cell navigator (HMS Red Cell)
**Mentioned in Despatches:** HMS Red Cell — monkey-patched trace hooks to empirically verify all four start-refinement guards in one probe.

## Sailing Orders

| | |
|---|---|
| Outcome | Plumb optional per-curve start refinement through `extract_curves` when a hint is supplied; shift native start toward the expected-start window subject to max-shift cap + R² gate + PredictionState horizon guard + search_from horizon guard. Preserve Method 2b max-sensor start and NC-1/NC-2 coupling when hint is absent. |
| Metric | 5+ new TDD tests pass; 33/33 existing detection tests unchanged; M3's 14 tests unchanged; red-cell verifies no start drift under σ ∈ {0.15, 0.5, 1.0}. |
| Deadline | This session. |

## Decisions & Rationale

1. **Refinement, not replacement.** Method 1 / 2a / 2b still fire independently in `_detect_start`; M4 only runs AFTER `_detect_curve_end` returns, in the outer loop at the `extract_curves` level. The `_refine_start_with_hint` helper proposes at most one shift, and that shift is bounded by four gates. When any gate fails, the native start is retained verbatim. This keeps Method 2b (mission `2026-04-24_105032_1b3801f8`) as the primary source of truth and M4 as a refinement layer.

2. **Short-circuit on truncated curves.** A truncated log's `end_time` is the log's EOF, not an actual bake end — applying `end_time - expected_duration` as the window anchor would produce a nonsense window. M4 explicitly skips refinement when `truncated=True`. Real-world impact: `real_1000BA3C_0946` is the only truncated real fixture, and it also carries `expected_durations_s=None` (M1 convention), so the hint never reaches M4 for it anyway — but the `truncated` guard is the second line of defence.

3. **Four guard stack** (evaluated in order):
   - **In-window no-op** — if `t_native_start ∈ [t_start_lo, t_start_hi]`, return immediately.
   - **Horizon guard** — shifts bounded below by `search_from` (outer loop's next-curve pointer); prevents crossing a previous curve's post-exit tail and re-including its cooldown as "in the bake".
   - **Max-shift cap** — `EXPECTED_DURATION_MAX_START_SHIFT_SECONDS = 30.0` (6 samples @ 5 s). Deliberately tight to protect Method 2b's empirical tuning; can be widened in a future mission once M7's red-cell calibrates against a larger real-CSV corpus.
   - **PredictionState guard** — aborts if the proposed shift would cross a `'Probe Not Inserted'` marker. NC-1/NC-2 coupling: `_skip_probe_pull_tail` assumes the bake's start is in the current insertion session; crossing the marker would break that invariant.
   - **Sigmoid R² gate** — shift is only adopted when `fit_logistic(temps[shifted:end_idx+1])` yields R² ≥ `SIGMOID_FIT_MIN_R2`. Pure shape quality, NO proximity term.

4. **Direct R² gate, not composite `score_start_candidate`.** First attempt wired through `score_start_candidate` and was rejected empirically: the composite's proximity term penalises short bakes twice (once in the end path, once in the start path). Case in point: a synthetic where native start was correct and shift moved to a known-clean earlier start scored 0.599 — blocked despite R²=0.99. Switched to `fit_logistic(t, T).r2` directly. Rationale for end-refinement to keep composite: there we want to *locate* the end, so "how close is it to the expected time" matters. For start-refinement the end is already known; we only ask "is the window shape-clean?"

5. **Peak re-derivation after start shift** (inherited pattern from M3 A1 fix). A start shift earlier can extend the curve range; if the running-max `peak_idx` was computed from `start_idx` forward during baseline end-detection, the extended range can now contain a new true max. Re-derive `peak_idx = shifted + argmax(temps[shifted : end_idx + 1])` to ensure the outer `MIN_PEAK_TEMP` gate sees the correct peak.

6. **Log at `INFO` on successful shift, `WARNING` on abort.** Operational visibility: a production user running the app can grep `INFO Start refined` to see how often hints are actually shifting detector decisions (current expectation from red-cell Q3: nearly never on real fixtures — native starts sit at band centre). A shift going through silently would make it hard to diagnose if a mis-hinted bake produced an unexpected window.

## Artifacts

| File | Change | Size |
|---|---|---|
| `src/data/curve_boundary_detector.py` | Import `fit_logistic`; new `_duration_max_start_shift_s`; outer-loop refinement call; `_refine_start_with_hint` method | +~160 lines |
| `config/constants.py` | `EXPECTED_DURATION_MAX_START_SHIFT_SECONDS = 30.0` | +12 lines |
| `tests/test_curve_boundary_detector_start_refinement.py` | **NEW** — 11 tests across 6 classes | 325 lines |

## Validation Evidence

**Red bar (pre-implementation):** 4 failed: `test_max_start_shift_key_present`, `test_max_start_shift_is_positive_float`, `test_start_shifts_earlier_when_hint_suggests_longer_bake`, `test_shift_bounded_by_max_start_shift_seconds`.

**Green bar (post-implementation):**
```
pytest tests/test_curve_boundary_detector_start_refinement.py tests/test_curve_boundary_detector_expected_duration.py tests/test_curve_boundary_detection.py tests/test_sigmoid_refinement.py tests/test_curve_boundary_fixture_schema.py
======================== 85 passed in 61.22s (0:01:01) ========================
```

**HMS Red Cell final verdict: GO**
- **Q1 REGRESSION (byte-identity at hint=None):** PASS — 7/7 real curves unchanged vs. pre-M4 commit `16be76e`.
- **Q2 START VARIANCE UNDER NOISE:** PASS — start-idx stdev = 0.000 in **every** (CSV × σ × mode) combination. Hint never increases start variance.
- **Q3 METHOD 2b PRESERVATION:** PASS — bake-2 start remains 651 and bake-3 start remains 5888 on BA3C_1759, both under no-hint AND with hint=[1400, 1465, 1485]. Both hit the in-window no-op early return.
- **Q4 NC-1/NC-2 COUPLING:** PASS — all 4 guards empirically triggered via monkey-patched trace:
  - In-window no-op → return unchanged
  - max_shift cap → 6-sample shift applied, R²=0.890 passed
  - PredictionState guard → shift aborted with warning `"...would cross PredictionState='Probe Not Inserted' at idx [0,1,2,3,4,5]"`
  - R² gate → shifts rejected with R²∈{0.665, 0.606}, start preserved

**Regression check:** `pytest tests/` → `8 failed, 194 passed, 1 skipped`. Failures match pre-existing baseline (memory follow-up `(j)`). M4 added 11 tests; all detection/M3/M2/M1 tests still pass.

## Open Risks / Follow-ups

- **M4 is a latent capability on current real fixtures.** All native starts sit at or near the centre of their expected-start windows, so the in-window no-op fires and no shift occurs. This is by design — Method 2b is already good. The defensive value activates when (a) M7 tightens the tolerance band, (b) a future mid-bake-start fixture lands with a genuinely mis-aligned native start, or (c) operator-entered hints disagree sharply with detector-frame durations (the A2 caveat from M3).
- **`max_shift = 30 s` may be too tight for logs where the detector's Method 2b fires late on very slow rises** (e.g. `post_wonder_meal_lidded`-like future logs). Not a blocker today; document for M7 calibration.
- **R² gate uses `fit_logistic` directly**, bypassing `score_start_candidate`. If future work wants to extend scoring (e.g. add inflection-position plausibility), the helper needs a third scoring variant. Deliberately deferred — YAGNI.
- **Horizon guard is currently dominated by max_shift** — HMS Red Cell flagged this as defensive-layering-worth-keeping because raising max_shift in the future would make horizon critical. Noted in the detector comment at `_refine_start_with_hint`.

## Mentioned in Despatches

- **HMS Red Cell** — discovered that every guard could be exercised in-band via a single synthetic DataFrame with trace hooks, giving a 4-guards-in-one-probe empirical verification. The trace pattern (monkey-patch to capture intermediate tuple) is worth keeping in the pattern library for future multi-guard reviews.

## Reusable Patterns

- **Guard-stack pattern for refinement logic.** When adding a refinement that can *move* a decision: order guards from cheapest/most-restrictive to most-expensive (no-op → horizon/max-shift → PredictionState → numerical quality). Each guard aborts, preserving the native decision.
- **Direct primitive over composite wrapper when the composite's proximity term doesn't apply.** The composite `score_end_candidate` has `proximity_score` as a load-bearing term; for start-refinement where we already trust the end, skip the composite and call the primitive `fit_logistic` directly. Saves a class of double-penalisation bugs.
- **Peak re-derivation pattern (M3 A1, now M4).** Any refinement that moves curve boundaries must re-derive derived state (peak index) over the refined range. Third time this pattern surfaces — promote to convention.

## Next Up

M5 HMS Dauntless — loader plumbing. LOW risk, pure pass-through. Consumes the `expected_durations_s: list[float | None] | None` kwarg in `ThermalProfileLoader._extract_all_baking_curves` and exposes `set_expected_durations` on the loader with cache-invalidation semantics.

Entry criteria for M5: met. No red-cell required (LOW tier).
