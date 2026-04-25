# Captain's Log — HMS Ardent (M1 of flotilla `refactor/curve-boundary-review`)

**Mission ID:** `2026-04-24_233307_c5744e63`
**Branch:** `refactor/curve-boundary-review` (off `refactor/expected-bake-time` HEAD `4486734`)
**Risk tier:** LOW (Action Station 1 — pure plumbing; default behaviour byte-identical when no override applied)
**Mode:** single-session

## Sailing Orders

| | |
|---|---|
| Outcome | Loader exposes `raw_data` attribute (full pre-extraction DataFrame); new `set_curve_boundaries` / `clear_curve_boundaries` methods pin manual boundaries that override the detector. |
| Metric | 5+ TDD tests; default behaviour byte-identical when no override applied; 101+ existing tests unchanged. |
| Deadline | This session. |

## Decisions & Rationale

1. **Latent bug discovered while writing tests.** Before M1, `set_expected_durations` re-ran `_extract_all_baking_curves(self.data.copy())` — but `self.data` had been overwritten with the first curve's slice at line 87 of `load_csv`. Multi-bake CSVs (e.g. BA3C_1759, 3 bakes) silently lost bakes 2 and 3 on every hint update. The prior flotilla's tests didn't catch it because they invoked `_extract_all_baking_curves(df)` directly without going through `load_csv` → `set_expected_durations`. M1's `raw_data` attribute fixes this naturally — the new code path reads `self.raw_data` (full log) for re-detection. Added `TestSetExpectedDurationsUsesRawLog::test_set_expected_durations_preserves_all_three_bakes` to anchor the regression.

2. **Override application happens in `_extract_all_baking_curves`, not in a post-hoc layer.** The override is applied immediately AFTER detector returns, BEFORE per-curve sensor-role identification. This guarantees `_identify_sensor_roles_for_curve` runs on the pinned slice, so role detection and analytics see the same window the operator pinned. Alternative (post-hoc patching outside the extractor) was rejected — would have meant two code paths consuming "curve dicts" and risk drift.

3. **Override storage: `dict[curve_index, tuple[start, end]]`, not a list.** Sparse storage — most curves never get overridden. A list-of-tuples-or-None would force every entry to materialise; a dict naturally encodes "no override for this curve" by absence. Mirrors the `_sensor_overrides` pattern.

4. **`exit_candidate_kind = "manual_override"` on pinned curves.** Distinguishes operator decision from detector decision in logs, in tests, and in the upcoming Boundary Review tab UI. Adds a 7th value to the `_VALID_KINDS` vocabulary established in M3 of the prior flotilla; the M3 test suite uses an explicit set so the new kind needs no test update there (the kind is only set on overridden curves, not detector output).

5. **Validation in `set_curve_boundaries`, not silent clamping.** Inverted ranges, out-of-bounds indices, and unknown curve_index all raise. Streamlit widgets in M3 will pre-validate, but the loader API is also called from tests and could be called from future scripts — clear errors at the boundary surface beat mysterious slicing later.

6. **`_reapply_boundary_state` re-runs detection from `raw_data`** rather than caching detector output and patching it. Cleaner: any future detector improvement (e.g. M3-prior-flotilla refinement logic) automatically applies on every override change without `_reapply_boundary_state` knowing about the detector internals.

## Artifacts

| File | Change | Size |
|---|---|---|
| `src/data/loader.py` | New `raw_data` attribute; new `_boundary_overrides` dict; `set_curve_boundaries`, `clear_curve_boundaries`, `_reapply_boundary_state`, `_apply_boundary_overrides` methods; `set_expected_durations` re-detection now uses `raw_data` | +~95 lines |
| `tests/test_loader_curve_boundaries.py` | **NEW** — 15 tests across 5 classes | 240 lines |

## Validation Evidence

**Red bar:** 15 failed (attribute missing, methods missing, set_expected_durations bake count regression).

**Green bar:**
```
pytest tests/test_loader_curve_boundaries.py
============================= 15 passed in 13.26s =============================
```

**Detection-family regression:**
```
pytest tests/test_loader_curve_boundaries.py tests/test_loader_expected_duration.py \
       tests/test_curve_boundary_detector_expected_duration.py \
       tests/test_curve_boundary_detector_start_refinement.py \
       tests/test_curve_boundary_detection.py \
       tests/test_flotilla_finale_regression.py
======================= 111 passed in 321.78s (0:05:21) =======================
```

**Latent bug verified fixed empirically:**
```
real_1000BA3C_1759 with set_expected_durations([1400, 1465, 1485]):
  pre-M1 (regression):   1 curve  ← bakes 2 and 3 silently lost
  post-M1 (fix):         3 curves ← all bakes preserved
```

## Open Risks / Follow-ups

- **`raw_data` retention adds memory cost.** A 6,200-sample BA3C_1759 DataFrame is ~3 MB; trivial. If a session loads many large CSVs, total cost could grow. Not actionable now; document when M3 lands the multi-file UI.
- **Override invalidation when curve count changes.** If the user pins curve 2, then changes hints in a way that drops the detector's curve count to 2, the override at index 2 is silently dropped (with a stale-override skip in `_apply_boundary_overrides`). M3 should warn the user when this happens. Noted for M3 implementation.
- **Override persistence across browser sessions.** `_boundary_overrides` is in-memory only — a browser refresh clears them. DF-3 in the plan covers this if needed.

## Reusable Patterns

- **Discovery test catches latent bugs.** Writing `test_set_expected_durations_preserves_all_three_bakes` revealed the prior flotilla's bug. Pattern: when adding a new attribute that other code SHOULD have been using, write the test that asserts the new attribute makes a difference somewhere — it'll surface the silently-broken paths.
- **Validation at the loader boundary.** `set_curve_boundaries` raises on bad input. UI validates first for UX, but the loader is the trust boundary.

## Next Up

M2 HMS Glorious — pure plot helpers in `src/visualization/boundary_review_plots.py`. MEDIUM risk (new plot surface). Will consume `loader.raw_data` and curve dicts (now including `exit_candidate_kind == "manual_override"` for pinned curves).
