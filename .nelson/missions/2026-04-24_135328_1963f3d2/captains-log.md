# Captain's Log — HMS Resolution (M2 of flotilla `refactor/expected-bake-time`)

**Mission ID:** `2026-04-24_135328_1963f3d2`
**Branch:** `refactor/expected-bake-time`
**Risk tier:** MEDIUM (Action Station 2 — new numerical-solver surface)
**Mode:** single-session (admiral-executed; per `becalmed-fleet.md`: sequential TDD work on a single new module)

## Sailing Orders

| | |
|---|---|
| Outcome | Introduce `src/data/sigmoid_refinement.py` (pure, no pandas/streamlit imports) with `fit_logistic`, `score_end_candidate`, `score_start_candidate`; wire six new keys into `CURVE_DETECTION_CONFIG`. |
| Metric | TDD-first test suite passes: clean sigmoid R² ≥ 0.999; σ=0.15 °C t₀ variance ≤ 1 sample; short-window short-circuit proven via monkeypatched `curve_fit`; non-sigmoid data scores < min_r2 gate; zero regression in existing suite. |
| Deadline | This session. |

## Decisions & Rationale

1. **Pure module, no pandas/streamlit coupling.** `sigmoid_refinement.py` imports only `numpy`, `scipy.optimize`, `math`, and `dataclasses`. Callers pass plain `np.ndarray` + `dict` config. This keeps the numerical-solver failure modes isolated from the detector's existing logic and makes the red-cell probe (σ sweep) trivially mockable.

2. **`LogisticFit` is a frozen dataclass with a `.failed()` classmethod.** NaN-filled sentinel rather than `None` because downstream call sites will read fields without guarding — a NaN contaminating arithmetic surfaces fast, whereas a `None` would raise `TypeError` far from the source. `r2 = 0.0` and `rmse = math.inf` on failure so bit comparisons work.

3. **Composite score formula: `w_r2 × r2_component + w_prox × proximity_component`.** Clean linear combination with a hard R² gate: if `fit.r2 < SIGMOID_FIT_MIN_R2`, `r2_component = 0` — no partial credit. Proximity uses linear falloff within the tolerance band and 0 outside. Final score clamped to `[0, 1]` so weights-summing-to-one-violations don't leak.

4. **Pre-solver short-circuit on `SIGMOID_FIT_MIN_SAMPLES`.** The hot-path test (`test_insufficient_samples_returns_zero_without_calling_curve_fit`) monkeypatches `curve_fit` to raise; the assertion that the score returns 0.0 without the mock firing proves the short-circuit holds. Protects M3's per-curve inner loop from paying ~10 ms × N-candidates solver cost on tiny windows.

5. **Time normalisation inside the scorer, not the fitter.** `fit_logistic` operates on whatever `t` is passed; `score_end_candidate` subtracts `t[start_idx]` before calling. Keeps the primitive general (can be called with absolute CSV timestamps OR relative ones) and avoids surprise when the detector uses different time bases per candidate.

6. **`score_start_candidate` delegates to `score_end_candidate` via `np.searchsorted`.** Instead of duplicating the fit + scoring logic, the start scorer infers the candidate end index from `proposed_start_time + expected_duration_s` and forwards. DRY: one code path, one bug surface. Test `test_start_in_middle_of_curve_scores_lower_than_start_at_zero` confirms the delegation produces the physically-correct ordering.

7. **Config-wiring tests pin the 6 new keys.** Four wiring tests prevent silent rename drift (`test_required_keys_present_in_curve_detection_config`, `test_composite_weights_sum_to_one`, `test_tolerance_frac_in_open_unit_interval`, `test_min_samples_is_positive_integer`). M3/M4 will consume these via `.get()` with defaults, so a silent rename would *not* raise — these tests close that gap.

8. **`curve_fit` bounds chosen to absorb numerical noise without strangling the optimiser.**
   - `L ∈ [L0 − 20, U0]` — lets the fit drop slightly below the observed min if the true asymptote is cooler.
   - `U ∈ [L0, U0 + 20]` — same, upward.
   - `k ∈ [0, 10]` — positive steepness only (rising sigmoid); 10/s upper bound is physically absurd for baking but keeps the optimiser from running away.
   - `t0 ∈ [t[0] − span, t[-1] + span]` — permits a wide inflection position, critical for windows that truncate before or after the true inflection.

   An alternative (unbounded `curve_fit`) was rejected: `scipy.optimize` without bounds can oscillate on noisy data and silently return `[1e10, 1e10, …]` with a misleading small RMSE if the residuals happen to align.

## Artifacts

| File | Change | Size |
|---|---|---|
| `src/data/sigmoid_refinement.py` | **NEW** — LogisticFit dataclass + 3 public functions + internal helpers | 247 lines |
| `tests/test_sigmoid_refinement.py` | **NEW** — 22 tests (7 fit + 6 end-score + 4 start-score + 1 dataclass + 4 config wiring) | 282 lines |
| `config/constants.py` | 6 new keys at bottom of `CURVE_DETECTION_CONFIG` | +26 lines |

## Validation Evidence

**Red bar (pre-implementation):** `pytest tests/test_sigmoid_refinement.py` → `ModuleNotFoundError: No module named 'src.data.sigmoid_refinement'` (collection error).

**Green bar (post-implementation):**
```
pytest tests/test_sigmoid_refinement.py tests/test_curve_boundary_fixture_schema.py tests/test_curve_boundary_detection.py
============================= 60 passed in 5.61s ==============================
```

**Red-cell probe (empirical, per memory feedback `feedback_redcell_empirical_verification`):**
`test_red_cell_t0_variance_low_at_sigma_015` — 20 seeds, σ=0.15 °C Gaussian noise, t₀ ground truth = 300.0 s.
- Mean drift: ≤ 1 sample period (5 s) of truth.
- Std dev: ≤ 1 sample period (5 s).

**Regression check:** `pytest tests/` → `8 failed, 169 passed, 1 skipped`.
Failure set matches pre-existing baseline from memory follow-up `(j)` (test_deep_insertion flake + zone colors + surface sensor detection). M2 added 22 new passing tests (+21 net vs. post-M1 baseline of 148 passed, accounting for the flake flipping).

## Open Risks / Follow-ups

- **`k` bound of 10/s is conservative but arbitrary.** A future mission may want to anchor it in measured probe thermal time constants. Current value comfortably exceeds real bake steepness (typical `k ≈ 0.006 1/s`) so it will not bind in practice.
- **R² gate is a hard threshold at 0.85.** Below this the sigmoid component contributes exactly 0 — no smooth transition. This was an intentional simplicity trade-off; if M7 red-cell surfaces cases where a 0.83 fit is rejected when it should weakly contribute, consider a smooth ramp in a future follow-up.
- **M4 will need `EXPECTED_DURATION_MAX_START_SHIFT_SECONDS`** per the flotilla plan. Deliberately not added in M2 — that key is owned by the mission that consumes it, to keep config entries coupled to their read sites.
- **`scipy` dependency now first-used in `src/data/`.** Previously `src/analysis/thermal_analysis.py` imported `scipy.signal`; this mission adds `scipy.optimize.curve_fit`. `requirements.txt` already pins scipy — no change needed.

## Mentioned in Despatches

- The short-circuit test (`test_insufficient_samples_returns_zero_without_calling_curve_fit`) via monkeypatch is a reusable pattern — any future hot-path optimisation in the detector can be anchored the same way: replace the expensive call with a raising sentinel and assert the fast path returns cleanly.

## Reusable Patterns

- **Pure numerical module + plain-dict config** pattern — keep scipy-dependent logic isolated in a module that takes `numpy` arrays and reads config via `.get()` with sensible defaults. The detector then wires it in with the production dict; tests pass a tighter test-dict without monkeypatching globals.
- **Monkeypatch-to-prove-short-circuit** idiom — if a function has a "don't bother calling the slow thing" path, assert it by replacing the slow thing with a raiser.

## Next Up

M3 HMS Agincourt — detector END refinement. HIGH risk tier (it edits the fragility surface). Will consume:
- `expected_durations_s` from fixtures (M1)
- `score_end_candidate` from this module (M2)
- `SIGMOID_FIT_MIN_R2`, `EXPECTED_DURATION_TOLERANCE_FRAC`, etc. from config (M2)

Entry criteria for M3: met.
