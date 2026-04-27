# HMS Foudroyant — Captain's Log

Mission: M5 finale of flotilla `refactor/role-classification-unified`.
Date: 2026-04-27.
Commits anchored to flotilla: b14211c..fcebc86 (M1a..M4) + this M5 commit.

## Mission scope

Documentation, cleanup, and a permanent regression test that pins the new
spatial-reconstruction architecture so the flotilla cannot silently regress.
NO classifier code touched (`src/data/spatial_reconstruction/*`,
`src/data/loader.py`, `src/data/sensor_assignment_manager.py`, `sidebar.py`
all read-only this mission).

## Items completed

### 1. CLAUDE.md updates (surgical)

Sections rewritten:

- **Per-curve sensor identification** — replaced firmware-mode-pick +
  physics-correction prose with the spatial_reconstruction.classify
  contract, role list (core/surface/ambient/lid), `SpatialAssignment` /
  `PositionalAssignment` dataclass description, manual-override
  precedence, and `_validate_override_topology` with through-loaf note.
- **Data transformation pipeline** — pruned the legacy 3-step layering
  (Virtual columns → physics correction → manual override) and replaced
  with the new 3-tier (manual override > classifier > legacy fallback).
  Deleted reference to `surface_sensor_detector.py`,
  `physics_corrected` flag, and `TransformationManager`.  Documented
  `LidTemperature` lifecycle.
- **Known Fragile Areas** — dropped the `physics_corrected` flag warning;
  added `LidTemperature` column lifecycle and override-topology
  through-loaf exception.
- **Config as source of truth** — replaced legacy classifier tunables
  with `ROLE_CLASSIFIER_CONFIG` pointer and clarified
  `INTERNAL_SENSOR_CONFIG` is a legacy retained for `get_internal_sensors`.
- **Architecture** — added the spatial-reconstruction module layout
  pointer (geometry / profile / piecewise / stefan / classifier /
  comparison) and baseline-report locations.
- **Repo Hygiene Notes** — updated to reflect the now-clean root.

### 2. config/constants.py audit

Grep evidence — `SURFACE_DETECTION_CONFIG` keys (4): all unused in src/
and tests/.  Block deleted.  `CORE_DETECTION_CONFIG` audit:

| Key                                       | Status     | Action |
|-------------------------------------------|------------|--------|
| `HEAT_THRESHOLD_C`                         | used       | keep   |
| `COOL_REFERENCE_MODE`                      | dead       | DELETE |
| `COOL_WINDOW_SECONDS`                      | used       | keep   |
| `CONFIDENCE_GAP_MIN`                       | dead       | DELETE |
| `ENABLED`                                  | dead       | DELETE |
| `PROBE_REMOVAL_RATE_C_PER_SEC`             | used       | keep   |
| `PROBE_REMOVAL_CONFIRM_SAMPLES`            | used       | keep   |
| `PROBE_REMOVAL_MIN_SIMULTANEOUS_SENSORS`   | used       | keep   |

Used keys are consumed by `identify_core_sensor_combined_rank` in
`src/data/thermodynamic_sensor_classifier.py` (which is itself still used
by `tests/test_curve_boundary_detection.py`, the curve-boundary
contamination path).  Block header rewrote to reflect that the
combined-rank function survives but the class around it is gone.

`INTERNAL_SENSOR_CONFIG`: all 4 keys (`TEMP_THRESHOLD`, `TIME_THRESHOLD`,
`USE_TIME_BASED_FILTERING`, `ALWAYS_INCLUDE_CORE`) read by
`loader.get_internal_sensors`.  Block header amended to note it is a
legacy retained surface and a position-based replacement is a future
follow-up.

`ROLE_CLASSIFIER_CONFIG`: untouched (added by M2a/M2b; new authority).

`CURVE_DETECTION_CONFIG`: untouched (curve-boundary detector tunables).

Constants module imports cleanly post-edit; no removed key has a reader
anywhere.

### 3. Root-level historical artefacts

Inventory: `*.md` at root was `CLAUDE.md`, `CODE_REVIEW_SUMMARY.md`,
`REFACTORING_ANALYSIS.md`.

- `CODE_REVIEW_SUMMARY.md` — first paragraph documents
  "Physics-based corrections persist", `physics_corrected` flag,
  `surface_sensor_detector` corrections.  Matches "*_SUMMARY.md
  describing superseded state".  **DELETED.**
- `REFACTORING_ANALYSIS.md` — first section describes
  `physics-based correction`, `surface-temperature overwrite bug`,
  `TransformationManager` (dead branch).  Matches "*_ANALYSIS.md for a
  now-completed initiative".  **DELETED.**
- `CLAUDE.md` — kept; updated in step 1.

Root-level `*.py`: only `app.py`, `sidebar.py`, `session_state.py`,
`sensor_naming.py` — none are legacy investigation scripts; none import
deleted modules; none deleted.

(The `~25 *_PLAN.md / *_SUMMARY.md / *_ANALYSIS.md files` mentioned in
the previous CLAUDE.md text appear to have been pruned across earlier
flotillas — only the two surviving root markdowns matched the deletion
criteria and have been removed.)

### 4. Permanent finale regression test

Created `tests/test_flotilla_finale_role_classification.py` — 22 tests,
modelled on the existing `test_flotilla_finale_regression.py`:

- 4 tests: public API surface (`classify`, `SpatialAssignment`,
  `PositionalAssignment`, `ProfileFit`, `extract_features`,
  `compute_oven_proxy`, `PROBE_GEOMETRIES`, `lookup_geometry`).
- 3 tests: legacy modules deleted (`surface_sensor_detector` import
  raises; `ThermodynamicSensorClassifier` class absent;
  `identify_core_sensor_combined_rank` survives).
- 2 tests: override topology (lid override accepted; core/surface
  inversion rejected with ValueError).
- 5 parametrized tests + 2 lifecycle tests: real-CSV per-role contract
  via `ThermalProfileLoader` (5 fixtures × {core, surface, ambient, lid}
  with multi-curve handling for `real_1000BA3C_1759`; through-loaf cases
  honour the `topology_note` lid-or-list expectation; wonder_white
  acceptable cores set {T5, T6}).
- 4 parametrized tests: synthetic per-role contract via direct
  `classify` (synthetic_lid_touch lid pick accepts T7 or T8 per the
  fixture's documented alternate).
- 2 tests: baseline reports (`tests/baselines/spatial_model_comparison.md`,
  `tests/baselines/role_classifier_flip_rates.md`) exist in-tree.

All 22 tests green.  This is the flotilla's permanent guardrail.

### 5. Memory update

Appended section (y) to `project_refactoring_plan.md` recording flotilla
landing date, mission roster, commit range, key architecture outcome,
and 5 + 2 carried-forward follow-ups (M4 #1..#5; M1a `1000F3C1_0911`
fixture gap; pre-existing j).

## Validation

- `pytest tests/test_flotilla_finale_role_classification.py -v`:
  **22 passed in 2.13 s.**
- Focused regression pack (M2a-M4 tests + finale):
  **159 passed in 76.65 s.**
- Full suite `pytest tests/ -q --tb=no`:
  **564 passed, 6 failed, 2 skipped in 258.93 s.**  Failures match the
  pre-existing baseline exactly (test_zone_color_consistency,
  test_realistic_baking_profile, four test_visualization.*) — no new
  regressions, no fixed regressions.

## Recommendation

The flotilla is structurally complete and the finale regression gate
holds.  Recommend merge to `main` after a final read-only diff review
(no captain on this mission has modified classifier code; the diff is
strictly documentation + cleanup + test).  M4's red-cell follow-ups
(#1..#5) are noted in memory and can be picked up in a separate
flotilla; none block merge.

— Captain, HMS Foudroyant
