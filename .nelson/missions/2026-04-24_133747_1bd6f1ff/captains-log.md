# Captain's Log — HMS Illustrious (M1 of flotilla `refactor/expected-bake-time`)

**Mission ID:** `2026-04-24_133747_1bd6f1ff`
**Branch:** `refactor/expected-bake-time`
**Risk tier:** LOW (Action Station 1)
**Mode:** single-session (admiral-executed; warrants no crew per `becalmed-fleet.md`: low complexity, heavy same-file editing)

## Sailing Orders

| | |
|---|---|
| Outcome | Extend fixture schema in `tests/fixtures/curve_boundary_cases.py` with per-curve `expected_durations_s: list[float] \| None` and `duration_tolerance_frac: float \| None`; annotate all real-source CSV fixtures. |
| Metric | Schema field present on case dict; all existing curve-boundary tests unchanged; new schema-shape test passes; git diff touches only `tests/fixtures/` and `tests/`. |
| Deadline | This session (M1 of 7-mission flotilla). |

## Decisions & Rationale

1. **Separate test file, not append-to-existing.** Added `tests/test_curve_boundary_fixture_schema.py` rather than extending `test_curve_boundary_detection.py`. Rationale: the detection-contract test file is already 30+ tests deep and growing with every mission (cliff, lidded, core-sensor, probe-removal, oven-entry); schema-shape tests are a different concern and will survive the full 7-mission flotilla unchanged. Small dedicated file = clearer fault isolation for future red-cell probes.

2. **Annotated five real cases, not just three.** Plan called out `100098DE_1351`, `BA3C_0946`, `BA3C_1759`. Exploration surfaced two more `"source": "real"` cases (`wonder_white_10k_lidded`, `post_wonder_meal_lidded`) both at 5 s sample period. Annotating all real cases keeps the contract uniform — M3/M4 refinement can trust that any `source == "real"` case carries either a populated list or an explicit `None` (only allowed when `truncated=True`).

3. **`None` reserved for truncated logs, nothing else.** `test_expected_durations_shape_matches_curve_count` refuses `None` unless `truncated=True`. This anchors the convention early: M3 refinement must short-circuit on `None` because duration is physically undefined for a log that ends mid-bake. Alternative (allow `None` for "unknown but complete") was rejected — it would leave the real-case contract ambiguous.

4. **One-sample-period agreement tolerance.** `test_expected_durations_agree_with_index_ground_truth` requires `|d - (end-start)×5s| ≤ 5 s`. Strict enough to catch off-by-one, loose enough to absorb a hypothetical future per-file sample-period variation. All current annotations are exact `(end - start) × 5.0`.

5. **BA3C_1759 gets a populated list despite `ambiguous=True`.** Case-level `ambiguous=True` is retained (bakes 2 & 3 have ambiguous starts). Per-bake durations are still computed and annotated because the M3/M4 tolerance band (`EXPECTED_DURATION_TOLERANCE_FRAC = 0.15`) is wider than the ±8-sample start uncertainty encoded in the case's `"tolerance": 8` field — so the hint remains useful and survives the existing ambiguity gate.

## Artifacts

| File | Change | Size |
|---|---|---|
| `tests/test_curve_boundary_fixture_schema.py` | **NEW** — 5 TDD-first schema tests | 122 lines |
| `tests/fixtures/curve_boundary_cases.py` | Schema comment + 5 real-case annotations | +~45 lines |

## Validation Evidence

**Red bar (pre-implementation):** `pytest tests/test_curve_boundary_fixture_schema.py` → 2 failed, 3 passed.
Assertion: `real_100098DE_1351: real-CSV case missing 'expected_durations_s' key`.

**Green bar (post-implementation):**
```
pytest tests/test_curve_boundary_fixture_schema.py tests/test_curve_boundary_detection.py
============================= 38 passed in 4.76s ==============================
```

**Regression check:** Full-suite failure count unchanged vs. baseline on main.
- With M1 changes:    `7 failed, 148 passed, 1 skipped` (3 viz + 2 sensor + 2 viz-edge)
- Without (git stash): `8 failed, 26 passed` on the same 4 failing files (includes `test_deep_insertion` flake)
- Baseline matches memory follow-up `(j)`: *pre-existing full-suite failures — test_deep_insertion flake + zone colors + surface sensor detection — 7-8 total depending on flake.*

**Conclusion:** 0 new failures introduced. 5 new tests added; all green.

## Open Risks / Follow-ups

- **Sample-period assumption** — `_SAMPLE_PERIOD_S = 5.0` is hardcoded in the schema test. All 5 real CSVs confirm `Sample Period: 5000` ms in header, but a future CSV at a different rate would silently pass the one-sample-period tolerance while actually disagreeing with its own index-based ground truth. Low priority — a follow-up mission can read sample period from each CSV's metadata and inject it into the test parametrisation.
- **No action required** for M2. The schema contract is stable and M2 (HMS Resolution — sigmoid module + config entries) does not touch these fixtures; it only consumes them at import time.

## Mentioned in Despatches

- The M1 exploration found 2 extra real cases beyond the plan's initial 3; annotating them uniformly has reduced the attack surface for M3/M4 to "real ⇒ populated or explicit None," eliminating a conditional branch those missions would otherwise need.

## Reusable Patterns

- **RED-then-GREEN on a dedicated schema file** — for any future schema extension of `CASES`, add a small `test_curve_boundary_fixture_schema.py::TestFixtureSchemaXxx` class with 4-5 assertions (presence, shape, value bounds, optionality). Keeps detection-contract tests uncluttered.
- **`duration_tolerance_frac` is defined optional via its *absence*, not a sentinel.** Case dicts omit the key when they want the config default; test only runs bound-checks when present. Avoids sentinel-vs-None confusion.

## Next Up

M2 HMS Resolution — config entries + pure `src/data/sigmoid_refinement.py` module.
Entry criteria for M2: met (M1 schema available for M2 to import in its own tests).
