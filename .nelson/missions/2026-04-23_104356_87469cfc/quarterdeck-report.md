# Quarterdeck Checkpoint 2

**Mission:** Stabilise bread entry/exit detection in oven_logging
**Checkpoint:** 2 (after Victory + Astute completions)
**Branch:** refactor/curve-boundary-detection
**Timestamp:** 2026-04-23

## Progress

| Task | Ship | Status |
|---|---|---|
| 1. Fixture harness | HMS Forth | ✅ completed (stood down) |
| 2. Failing test ladder | HMS Medway | ✅ completed (stood down) |
| 3. CurveBoundaryDetector | HMS Victory | ✅ completed (awaiting stand-down) |
| 4. META review | HMS Astute | ✅ completed (awaiting stand-down) |
| 5. DRY sweep | HMS Kent | ⏭ dispatching now with expanded scope |

**4/5 tasks complete. Critical path length remaining: 1. Well ahead of schedule.**

## Detector outcome

- `tests/test_curve_boundary_detection.py`: 1→12 green (11 red tests flipped).
- `tests/` full suite: 117 passed, 8 failed, 1 skipped. The 8 failures are **pre-existing on main** (zone colours + surface sensor detection, unrelated to curve boundary detection). Confirmed independently by Astute via `git diff main` on the affected test files — no modifications. Victory's work introduces **zero new regressions** and fortuitously fixes one prior failure.
- All 10 plan findings addressed per Astute's matrix (curve_boundary_detector.py file:line evidence in verdict).
- Loader shrunk from 1,400+ to 916 lines; `_extract_baking_curve` deleted; CoreTemperature fallback consolidated into `column_helpers.resolve_core_temperature_series`.

## Red-cell verdict: ACCEPT_WITH_NOTES

Verdict document at `.nelson/missions/2026-04-23_104356_87469cfc/redcell-verdict.md`. No blocking defects. Six non-blocking items are folded into Kent's brief below. Three additional concerns flagged for a follow-up mission.

## Battle-plan amendment — Kent's scope expanded

**Original Kent scope (as registered in battle-plan.json):** DRY sweep of hardcoded T1-T8 sensor lists in `src/analysis/thermal_analysis.py`, `src/data/surface_sensor_detector.py`, `src/data/thermodynamic_sensor_classifier.py`.

**Amended scope** — Kent must also address Astute's 6 non-blocking items:

1. Remove `INSTANT_DROP_THRESHOLD_C` dead code (`config/constants.py`, `curve_boundary_detector.py` `__init__`); correct the docstring at `curve_boundary_detector.py:303-309`.
2. Remove or re-route `print()` debug statements in the `loader.py:739-751` adapter (leaks into Streamlit logs).
3. Add a rationale comment at `CURVE_DETECTION_CONFIG.MIN_CURVE_DURATION_SECONDS = 120` naming the fixture it is anchored to (or regenerate the fixture — Kent's call, but recommend commenting since the fixture is owned by Forth's deliverable).
4. Add a prominent comment at `_probe_cooking_continuous` + `_long_cool_window_samples` naming the 1759 CSV + firmware-reliability assumption + the two risks Astute documented.
5. Decide on `test_golden_master_real_csvs` — either delete as redundant with ground-truth, or re-purpose with a distinct contract.
6. Extract `'Probe Not Inserted'` + related PredictionState literals into a module-level constant.

**Amended file ownership for Kent:**
- `src/analysis/thermal_analysis.py`, `src/data/surface_sensor_detector.py`, `src/data/thermodynamic_sensor_classifier.py` (original)
- Added: `src/data/curve_boundary_detector.py`, `config/constants.py`, `src/data/loader.py` (adapter portion), `tests/test_curve_boundary_detection.py` (golden-master decision)

No conflict — Victory is stood down, so there is no concurrent ownership. This is sequential hand-off, which `split-keel.md` permits.

**Follow-up mission candidates** (flag in stand-down):
- Cross-CSV validation for `_probe_cooking_continuous` (≥ 3 more real CSVs required).
- `truncated` duration floor (currently unbounded).
- `_detect_start` inter-curve boundary assumption (implicit invariant).

## Squadron readiness

| Ship | Hull | Notes |
|---|---|---|
| HMS Forth | stood down | — |
| HMS Medway | stood down | — |
| HMS Victory | Green (idle) | shutdown after Kent completes |
| HMS Astute | Green (idle) | shutdown now |
| HMS Kent | Green 100% | dispatching with amended scope |
| HMS Admiralty | Green (plenty of headroom) | coordination only |

## Standing order scan

- admiral-at-the-helm: ✅ admiral has not implemented; coordinating only
- drifting-anchorage: ⚠️ Kent's scope was formally amended above — this is in-scope scope-expansion to absorb red-cell findings, not drift. Documented in this report as an amendment event.
- captain-at-the-capstan: ✅ all captains implemented directly with 0 crew
- pressed-crew / battalion-ashore / all-hands-on-deck: N/A no crew used
- press-ganged-navigator: ✅ Astute did not implement — critique-only
- wrong-ensign: ✅ agent-team tools used throughout

No violations.

## Budget

Rough estimate: ~15% of session tokens consumed. Comfortable headroom.

## Decision

**Continue with amended Kent brief.** Dispatching now.
