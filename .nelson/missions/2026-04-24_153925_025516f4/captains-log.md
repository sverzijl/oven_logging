# Captain's Log — HMS Victory (M7 of flotilla `refactor/expected-bake-time`)

**Mission ID:** `2026-04-24_153925_025516f4`
**Branch:** `refactor/expected-bake-time`
**Risk tier:** MEDIUM (Action Station 2 — no new code, but may bounce work back to M3/M4)
**Mode:** single-session (admiral ran the battery directly after HMS Red Cell agent hit per-session rate limit)

## Sailing Orders

| | |
|---|---|
| Outcome | Final empirical verification of the flotilla: 36-run red-cell battery (σ ∈ {0.15, 0.5, 1.0} × 3 real CSVs × 4 hint modes × 8 seeds = 288 detector calls); permanent pytest regression guard; memory updates; flotilla-level captain's log. |
| Metric | 216/216 seed-runs produce correct curve count; no cliff FP amplification beyond +3 ceiling; permanent regression test suite added; project memory updated. |
| Deadline | This session. |

## Decisions & Rationale

1. **Admiral ran the battery, not a sub-agent.** HMS Red Cell subagent was dispatched for the 36-run battery but returned rate-limited. Admiral had full flotilla context from writing M3 and M4 already, so switched to direct execution: scripted the matrix inline, ran it in one go, captured the numbers. Faster than re-spawning. Per `admiral-at-the-helm.md`: the admiral runs the probe; the **analysis/verdict** work (scoring, test design) remained admiral-level (which it would be anyway).

2. **Cliff-amplification ceiling at +3, not 0.** Naive reading would say "any cliff increase with hint = regression". Empirical evidence disagrees: on BA3C_1759 σ=0.5 the correct hint converts 2 plateau → cliff decisions. Those are *correct* physical events (probe pull is the real end), not amplifications. +3 cap leaves headroom for legitimate refinement while still catching pathological cases.

3. **Permanent regression test at `tests/test_flotilla_finale_regression.py`, not as part of existing files.** Four properties deserve isolation:
   - Curve count preservation (9 parametrised cases)
   - No cliff FP amplification (18 parametrised cases)
   - End-idx stdev reduction at σ=1.0 (1 strongest-signal test)
   - Graceful degradation on truncated fixture + spurious hint (1 test)

   Total: 29 tests, ~3 min runtime. Separate file so the finale's tests can be bisected independently of per-mission suites when a future refactor breaks one.

4. **Runtime ~3 min is acceptable for CI.** Alternative (reducing N_SEEDS from 8 to 4) was rejected: 4 seeds make stdev assertions noisy; 8 is the same choice M3/M4 red-cells made. If CI budget tightens later, `@pytest.mark.slow` and a CI skip is the right mitigation, not cutting seed count.

5. **Memory updated with full mission index and commit hashes.** Entry `(x)` appended to `project_refactoring_plan.md` with all 7 mission IDs and the 6 commit hashes landed so far. A future session with no conversation context can reconstruct the whole flotilla from the memory entry + `git log`.

6. **Browser smoke deferred, not skipped.** Manual Streamlit smoke-test ( `streamlit run app.py`, upload each CSV, verify expander appears, entering hint re-runs detection ) is a meaningful gate before merging to main but doesn't belong in the pytest battery. Documented below in the **Next-steps** section so the user can action it before merge.

## Artifacts

| File | Change | Size |
|---|---|---|
| `tests/test_flotilla_finale_regression.py` | **NEW** — permanent regression guard | 208 lines |
| `.nelson/missions/2026-04-24_153925_025516f4/` | Mission artefacts + this log | ~150 lines |
| Memory: `project_refactoring_plan.md` | Entry `(x)` appended | +1 line (long) |

## Red-Cell Battery Verdicts (numeric)

**216/216 seed-runs produced correct curve count.**

### End-idx stdev (lower = better)

| CSV | σ | none | correct | +30% | -30% |
|---|---|---|---|---|---|
| 100098DE | 0.15 | 0.00 | 0.00 | 0.00 | 0.00 |
| 100098DE | 0.50 | 105.63 | **10.39** | 105.63 | 105.63 |
| 100098DE | 1.00 | 244.49 | **11.82** | 244.49 | 244.49 |
| BA3C_1759 | 0.15 | 0.00 | 0.00 | 0.00 | 0.00 |
| BA3C_1759 | 0.50 | 0.00 | 0.00 | 29.10 | 0.00 |
| BA3C_1759 | 1.00 | 169.66 | 169.66 | 167.96 | 169.66 |
| BA3C_0946 | 0.15–1.0 | 0–1.98 | (truncated, n/a) | | |

**Finding:** correct hint dramatically stabilises end-idx on 100098DE (~21× reduction at σ=1.0). On BA3C_1759 +30% mildly worsens (29.10 vs 0.00) — fallback path triggers; expected. ±30% never crashes.

### Cliff-kind deltas (hint count − none count, across 8 seeds)

| CSV | σ | correct | +30% | -30% |
|---|---|---|---|---|
| 100098DE | 0.15 | +0 | +0 | +0 |
| 100098DE | 0.50 | +1 | +0 | +0 |
| 100098DE | 1.00 | +0 | +0 | +0 |
| BA3C_1759 | 0.15 | +0 | +0 | +0 |
| BA3C_1759 | 0.50 | **+2** | −2 | +0 |
| BA3C_1759 | 1.00 | +0 | −1 | +0 |

**Finding:** max Δ is +2 on BA3C_1759 σ=0.5 with correct hint. Inspection shows these are 2 plateau decisions converting to cliff (the actual probe-pull event) — a **legitimate refinement**, not amplification. Well inside the +3 test ceiling.

### Start-idx stdev

All rows ≤ 2.90 samples. Zero on the vast majority. Hint never inflates start variance.

### Graceful ±30 %

All 72 rows (3 CSV × 3 σ × 2 signed-30% modes × 4 mode-replicates) produce correct curve count. Detector falls back to earliest-wins baseline + emits `logger.warning` when no candidate lands in the band. No crashes. No silent decision corruption.

## Validation Evidence

**Permanent regression test suite:**
```
pytest tests/test_flotilla_finale_regression.py
============================= 29 passed in 218.33s =============================
```

**Full flotilla test stack (aggregate):**
| Mission | File | Tests |
|---|---|---|
| M1 | `test_curve_boundary_fixture_schema.py` | 5 |
| M2 | `test_sigmoid_refinement.py` | 22 |
| M3 | `test_curve_boundary_detector_expected_duration.py` | 14 |
| M4 | `test_curve_boundary_detector_start_refinement.py` | 11 |
| M5 | `test_loader_expected_duration.py` | 9 |
| M6 | `test_sidebar_expected_duration.py` | 11 |
| M7 | `test_flotilla_finale_regression.py` | 29 |
| **Total new** | | **101 tests** |
| Existing detection | `test_curve_boundary_detection.py` | 33 (unchanged) |

**Full-suite:** 8 failed, 243 passed, 1 skipped — failures match pre-existing baseline (memory follow-up `(j)`: test_deep_insertion flake + zone colors + surface sensor detection).

## Open Risks / Follow-ups

- **Browser smoke NOT yet executed.** Before merge to main, run `streamlit run app.py`, upload each real CSV, verify (i) expander `⏱️ Expected bake time (optional)` appears after upload, (ii) each curve has a number_input pre-filled with detected duration, (iii) editing a value triggers re-detection and visible window adjustment, (iv) clearing the value returns to detector's native decision. User-level verification, not pytest.
- **M3 A2 caveat preserved**: `wonder_white_10k_lidded` with M1-annotated hint selects cliff@350 over plateau@338 (operator-time vs detector-time semantic mismatch). Documented in code via `_HINT_DRIFT_CAVEAT` set in `TestHintMatchesGroundTruth`; should be resolved by a future mission that either re-annotates the hint as "time from detector's detected start" or pre-fills the UI from the detected duration (M6 already does the latter).
- **Tolerance band (±15 %) is intuitive, not empirically calibrated.** The red-cell battery used it as-is; all tests pass. A follow-up calibration from real operator-entered hints would tighten or widen it with evidence.
- **Deferred from flotilla plan (DF-1 through DF-5):** noise σ-driven calibration of tolerance, auto-prefill from `BAKEOUT_TARGETS`, sigmoid diagnostics surfaced in UI, refined window feeding back to `_identify_sensor_roles_for_curve`, removing `ambiguous=True` from BA3C_1759 bake-2. All of these are non-blocking; none belong in M7.
- **`post_wonder_meal_lidded` σ=1.0 seed 7 anomaly** (noted during M3 red-cell): no-hint splits the bake into 2 curves via `dip_with_rerise` false positive. With hint it correctly stays 1 curve. M7 battery confirms this is an *improvement* from M3/M4. Document: hint rescues this fixture.

## Mentioned in Despatches — Flotilla Honours

- **HMS Red Cell (M3)** — caught the `peak_idx` staleness bug (A1) via 240-run σ sweep. Without that probe, the merged bake-3 curve on BA3C_1759 σ=0.5 seed 7 would have silently dropped in production.
- **HMS Red Cell (M4)** — monkey-patched `_refine_start_with_hint` to empirically exercise all 4 guards in a single synthetic probe. Saved a test-authorship cycle.
- **HMS Red Cell (M7)** — started the 36-run battery but rate-limited; admiral picked up the script and finished the probe. Partial credit; the matrix design carried through.
- **All 7 missions green on first red-cell pass** (after M3's A1 fix) — rare for a flotilla of this tier. Suggests the TDD+DRY+red-cell discipline scales: each mission landed with its own unit + integration + empirical coverage before calling green.

## Reusable Patterns — Flotilla Summary

1. **Baseline-then-refine in all logic-adding missions.** M3 kept the baseline earliest-wins scan verbatim and added a gated refinement. M4 did the same for start. No-hint path byte-identical; hint path is a layer, not a rewrite.
2. **Peak re-derivation after any boundary shift.** Bit M3 (A1) once. M4 inherited the pattern from the start. Promoted to convention in the flotilla's reusable-patterns log.
3. **Guard stack, cheapest-first.** M4's 5-guard stack (in-window → horizon → max-shift → PredictionState → R²) is the template for any future refinement that can *move* a decision.
4. **Pure module + thin Streamlit wrapper** (M2, M6). Unit tests without the runtime.
5. **Change-detection equality guard against Streamlit infinite reruns** (M6). Any `st.rerun()` path needs it.
6. **Monkey-patched spy** for "did the wrapper forward the kwarg?" tests (M5).
7. **Red-cell empirical probes with numeric tables** (M3/M4/M7). "Did the diff introduce a bug?" is unanswerable; "at σ=0.5 seed=7 did peak_temp equal 36.6°C?" is trivially answerable.

## Next Up (Post-Flotilla)

The flotilla is complete. Remaining work belongs to a separate initiative:

1. **Manual browser smoke** on the 3 primary real CSVs (user action before merge).
2. **Merge `refactor/expected-bake-time` into `main`** once smoke passes.
3. **Follow-up mission (single-ship)**: resolve the M3 A2 caveat by either re-annotating `wonder_white_10k_lidded` or threading the detected-duration pre-fill through more robustly.
4. **DF-1 through DF-5** from the original plan file — open as separate missions as priority dictates.
