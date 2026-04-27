# Captain's Log — M3 Tab Refactor

**Admiral:** HMS Britannia (Opus)
**Mission ID:** 2026-04-27_013330_bbdd0d4d
**Branch:** refactor/temperature-profile-canonical-roles
**Outcome:** **ACHIEVED**

## Mission summary
- **Planned:** Close B2 (index drift), collapse S1 + S2 (Pattern A/B inline loops), close S6 (double-fetch). Adopt M1 helpers in tab.
- **Achieved:** Warspite commit `9d4503c`. All four defects closed. Astute verified GO across 8 checks.
- **Metric:** pytest 373 passed / 8 failed / 1 skipped (was 359/8/1; +14). File 88 → 56 lines (-32, -36%).

## Delivered artefacts
- `tabs/temperature_profile.py` — single hoisted `curve_index = st.session_state.current_curve_index`; both `build_sensor_label_map` and `build_sensor_role_map` called once each with explicit index; same `sensor_roles` dict feeds both line plot and heatmap; multiselect `options=list(SENSOR_LIST)`. 56 lines.
- `tests/test_temperature_profile_render.py` — 5 structural failing-first tests (B2 regression via ast/regex, Pattern A/B absence assertions, helper-call presence, double-fetch absence) + 9 already-green tests (golden contract sanity, AppTest smoke).

## Key decisions
- **Hoist `curve_index` once.** Captures session state at the top of `render()` and passes explicitly to both helpers. Closes B2 mechanism (proved gone via Astute's perturbed fixture: pre-fix T7 vs T6 divergence; post-fix T7 for both calls).
- **Single `sensor_roles` dict for both plots.** Closes S6 (double-fetch). Heatmap and line plot now consume identical role maps.
- **S4 (`render(state)` injection) deferred.** Touches `app.py` callers outside M3's file ownership. Flagged for post-flotilla follow-up — not M5 either, as the user-facing motivation was testability, which is partially delivered by AppTest smoke now passing.

## Validation evidence
- **B2 (Astute §1):** ast/regex shows zero direct `get_sensor_assignments_with_overrides` calls in render; helper calls each appear exactly once; `current_curve_index` hoisted into a single local. Empirical perturbation: pre-fix code diverged (T7 vs T6 for surface_sensor); post-fix code agrees (T7 for both).
- **Pattern absence (Astute §2):** zero regex hits for `for sensor in ['T1'`, `(Core)`, `(Surface)`, `(Internal)`, `(Ambient)` literals, or `sensor_roles[sensor] =` assignments. Imports correctly include `build_sensor_label_map`, `build_sensor_role_map`, `SENSOR_LIST`.
- **Backwards-compat (Astute §4):** all 16 tests in `TestHelpersMatchTemperatureProfileLoops` still green. M1's pinned contract holds.
- **Live render (Astute §3):** Streamlit AppTest smoke passes on the real F3C1 CSV; no exceptions.
- **Pytest delta:** stable +14 across two independent runs. The pre-existing flapper between 373/374 is not caused by M3.

## Open risks (carried to M4-M5)
1. **`test_deep_insertion` flapper.** Pre-existing order-dependent failure, oscillates between pass/fail. Not M3's fault. Out of scope for the flotilla.
2. **Widget key edge case.** Per Astute §C3, if `current_curve_index` is None at render time, widget keys become `temp_profile_show_all_None`. Recommend M5 add a defensive guard or test.
3. **No multi-file/multi-curve AppTest.** AppTest smoke covers single-CSV path only. M5 should consider an E2E test exercising the multi-file session state contract.
4. **Surface-to-T1 override edge case.** Carried from M2 — if user overrides surface to T1 (currently core), nothing happens because core priority wins. Cosmetic, not a regression.

## Follow-ups
- **M4 next:** sweep `['T1'..'T8']` literals across `sidebar.py`, `src/visualization/plots.py:91`, `src/data/loader.py:865, 1404`, `src/analysis/curve_comparison.py:31`, `sensor_naming.py:74, 107`, `src/data/curve_boundary_detector.py:36 _SENSOR_COLUMNS`. Replace with `from config.constants import SENSOR_LIST`.
- **M5 finale:** full regression + E2E + re-run all M0 perturbation scenarios.
- **Post-flotilla:** S4 `render(state)` injection, `test_deep_insertion` flapper investigation.

## Mentioned in Despatches
- **HMS Warspite** — exemplary atomic refactor. Removed both inline loops in one pass; structural tests guard against regression. File reduction 32 LOC matches the ~26-line two-loops budget plus housekeeping. AppTest smoke worked first try.
- **HMS Astute** — eight-check verification with empirical perturbation re-run. Proved B2 mechanism gone, not just claimed. Caught flapper count and surfaced four downstream concerns.

## Reusable patterns
- **Adopt:** Source-grep / ast structural tests for refactor completion (Pattern A/B absence). Functional tests prove behaviour; structural tests prove migration. Both needed.
- **Adopt:** Hoist call-once into a local at top of function before delegating to helpers; eliminates "called twice with different args" bug class.
- **Avoid:** Don't defer DRY across mission boundaries. Patterns A and B were both 13 lines of similar structure; collapsing them in one mission with a single helper module is cheaper than two missions.

## Mission stats
- Captains: 2 (HMS Warspite, HMS Astute)
- Crew per ship: 0
- Standing-order violations: 0
- Pytest delta: +14 passes
- Commit: 9d4503c
- File size delta: −32 lines (88 → 56)
