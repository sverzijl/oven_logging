# Captain's Log — HMS Dauntless (M5 of flotilla `refactor/expected-bake-time`)

**Mission ID:** `2026-04-24_152808_3bb51e80`
**Branch:** `refactor/expected-bake-time`
**Risk tier:** LOW (Action Station 1 — pure plumbing; default preserves byte-identical behaviour)
**Mode:** single-session (admiral-executed; per `becalmed-fleet.md`: low complexity, sequential)

## Sailing Orders

| | |
|---|---|
| Outcome | Plumb optional `expected_durations_s: list[float \| None] \| None` through `ThermalProfileLoader` into `_extract_all_baking_curves`; expose `set_expected_durations` with cache-invalidation; pad/truncate/warn on length mismatch. |
| Metric | 3+ new tests pass; M4/M3/M2/M1 tests unchanged; no-hint default preserves loader behaviour. |
| Deadline | This session. |

## Decisions & Rationale

1. **Attribute on the loader, not a kwarg on `_extract_all_baking_curves`.** Two reasons:
   - **Cache-invalidation semantics free.** `set_expected_durations` mirrors the `set_sensor_override` pattern — mutate state, re-run detection. Callers (M6 Spartan sidebar) can set the attribute and trigger a rerun without knowing the detection internals.
   - **`_extract_all_baking_curves` already takes `df` only.** Threading the hint as a kwarg would change every caller; keeping it as instance state keeps the change surface minimal (9 lines in `_extract_all_baking_curves`, 1 line in `__init__`).

2. **Length mismatches WARN, not RAISE.** The detector consumes hints positionally (`expected_durations_s[curve_slot]` with a bounds check) — extras are harmlessly ignored, missing entries fall through to no-hint refinement. Raising on mismatch would break the UI flow where (i) user uploads CSV, (ii) detection runs with N=2 curves, (iii) user enters 2 hints, (iv) user edits upstream parameters that shift detection to N=3 curves. The warning surfaces the drift without blocking the session.

3. **`set_expected_durations` preserves `current_curve_index` when valid.** If the user is currently viewing curve 2 of 3 and sets hints that re-detect still produces 3 curves, they stay on curve 2. If the hint causes curve count to shrink to 1, fall back to index 0. Alternative (always reset to 0) was rejected — it would disrupt UI context for the common case where hints are refining, not reshaping, the detection output.

4. **`self.data` is the cache.** `set_expected_durations` runs detection on `self.data.copy()`, which the loader already populates after CSV load (line 69 / 75). This makes the cache-invalidation trivial: "the cached DataFrame" is just `self.data`. No new cache fields needed.

5. **Kept the method signature symmetric with detector.** Loader stores `list[float | None] | None`; detector kwarg is `list[float | None] | None`; UI (M6) will store `list[float | None] | None` in session state. No type conversion anywhere in the chain.

## Artifacts

| File | Change | Size |
|---|---|---|
| `src/data/loader.py` | 1 new instance attribute; hint forwarded in `_extract_all_baking_curves`; length-mismatch warning; new `set_expected_durations` method | +~40 lines |
| `tests/test_loader_expected_duration.py` | **NEW** — 9 tests across 5 classes | 217 lines |

## Validation Evidence

**Red bar:** 7 failed (attribute missing, method missing, plumbing absent, warning not emitted).

**Green bar:**
```
pytest tests/test_loader_expected_duration.py
============================== 9 passed in 4.56s ==============================
```

**Detection-family regression:**
```
pytest tests/test_loader_expected_duration.py \
       tests/test_curve_boundary_detector_start_refinement.py \
       tests/test_curve_boundary_detector_expected_duration.py \
       tests/test_curve_boundary_detection.py \
       tests/test_sigmoid_refinement.py \
       tests/test_curve_boundary_fixture_schema.py
======================== 94 passed
```

**Full-suite:** `8 failed, 203 passed, 1 skipped` — failures match pre-existing baseline (memory follow-up `(j)`).

## Open Risks / Follow-ups

- **`_extract_all_baking_curves` returns-then-warns order.** The warning fires AFTER the detector has already consumed the hint — if the detector silently mis-assigned hints due to a count mismatch, the user sees both the wrong curves AND the warning. Considered pre-check before detector call but rejected: the "detected curve count" doesn't exist until the detector has run. Not a bug, just a slight UX quirk.
- **No test covers concurrent calls to `set_expected_durations`.** Streamlit isn't concurrent, so this isn't relevant to the current UI. If the loader ever lands in a threaded context a follow-up mission will need cache-locking.
- **Multi-file session state.** `app.py` stores `st.session_state.files = {filename: {loader, metadata, curves}}` — each file has its own loader instance, so M5's attribute is naturally per-file. No cross-file interference by construction.

## Mentioned in Despatches

- None specific to M5 — straightforward plumbing that took the pattern from M3 A1 (peak re-derivation) and M4 (refinement gates). The test file's `TestPlumbingReachesDetector` with monkey-patched `extract_curves` is reusable for any future loader-level forwarding test.

## Reusable Patterns

- **State-attribute + setter pattern for optional plumbing.** When adding an optional kwarg that needs to survive across method calls AND trigger a fresh run on change, use an instance attribute + a setter that mutates + re-runs. Keeps the signature of deeply-called methods stable.
- **Spy via `monkeypatch.setattr`** to verify "did the parent method forward the kwarg?" — lightweight, no mock library needed.

## Next Up

M6 HMS Spartan — two-pass sidebar UI. MEDIUM risk (Streamlit widget-key bleed is the hazard; precedent = mission `2026-04-24_102020_af6532e1`). Will consume:
- `loader.set_expected_durations(...)` from this mission
- `st.session_state.expected_durations_s` per-file keyed
- Per-curve widget keys by `curve_number` (1-indexed), NOT by `current_curve_index`

Entry criteria for M6: met.
