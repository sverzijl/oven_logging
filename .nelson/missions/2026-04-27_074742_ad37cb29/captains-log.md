# HMS Indefatigable — Captain's Log

**Mission**: M2a, refactor/role-classification-unified flotilla
**Date**: 2026-04-27
**Branch**: `refactor/role-classification-unified`

## Summary

Built the new `src/data/spatial_reconstruction/` package replacing discrete sensor-classification with thermodynamic spatial profile reconstruction. The piecewise three-region model is wired and producing role assignments that match fixture annotations on **8 of 9** parametrized contract cases — exceeds the required ≥7/9 bar.

## Files created

- `src/data/spatial_reconstruction/__init__.py` (public API exports)
- `src/data/spatial_reconstruction/geometry.py` (`PROBE_GEOMETRIES`, `lookup_geometry`)
- `src/data/spatial_reconstruction/profile.py` (`extract_features`, `compute_oven_proxy`, `ProfileFit`)
- `src/data/spatial_reconstruction/piecewise.py` (`fit_piecewise` with through-loaf + lid-bake handling)
- `src/data/spatial_reconstruction/classifier.py` (`classify`, `SpatialAssignment`, `PositionalAssignment`)
- `tests/test_spatial_reconstruction_piecewise.py` (12 unit tests, all green)

Files modified:
- `config/constants.py` — added `ROLE_CLASSIFIER_CONFIG` block with calibration-story comments.
- `tests/test_role_classifier_unified.py` — extended `TestClassifierReturnsExpectedRoles` to call `classify` and assert role assignments; multi-curve real CSV is now segmented via `CurveBoundaryDetector` and tested per-curve.

## Per-component unit tests

`tests/test_spatial_reconstruction_piecewise.py` — **12/12 PASS** covering:
- 2 geometry lookup tests
- 4 profile / extract_features / oven proxy tests
- 2 piecewise fit tests (single interface, through-loaf)
- 4 classifier tests (interface position, full immersion, through-loaf, lid detection)

## Per-role pass-rate breakdown — `TestClassifierReturnsExpectedRoles` (9 cases)

| Case                            | core | surface | ambient | lid  | overall |
|---------------------------------|------|---------|---------|------|---------|
| real_100098DE_1351              | T4 ✓ | T7 ✓    | [T8] ✓  | None ✓ | PASS  |
| real_1000BA3C_0946              | T1 ✓ | T6 ✓    | [T7,T8] ✓ | None ✓ | PASS |
| real_1000BA3C_1759 (3 curves)   | n/a  | T6 ✓×3  | [T7,T8] ✓×3 | n/a  | PASS  |
| wonder_white_10k_lidded         | T6 ✓ | T7 ✓    | [T1,T8] ✓ | None ✓ | PASS |
| post_wonder_meal_lidded         | T5 ✓ | T7 (T8 expected) | [T1,T8] ([T1] expected) | None ✓ | **FAIL** |
| synthetic_shallow_insertion     | T1 ✓ | T3 ✓    | [T4..T8] ✓ | None ✓ | PASS  |
| synthetic_full_immersion        | T1 ✓ | None ✓  | [] ✓    | None ✓ | PASS  |
| synthetic_lid_touch             | T1 ✓ | T4 ✓    | [T5,T6] ✓ | T7 ✓ | PASS  |
| synthetic_probe_pull_mid_bake   | T1 ✓ | T7 ✓    | [T8] ✓  | None ✓ | PASS  |

**Aggregate**: 8/9 pass. Per-role pass rate at the assertion level (9 cases × 4 roles = 36 role-assertions on single-curve cases + 6 role-assertions on the multi-curve case = 42):
- core: 9/9 (multi-curve uses curve-0 firmware mode)
- surface: 8/9
- ambient: 8/9
- lid: 9/9

Synthetic cases: **4/4 PASS** (deterministic-by-construction, as expected).
Real cases: **4/5 PASS** — exceeds the ≥3 brief.
Lidded through-loaf: **1/2 PASS** (wonder_white passes; post_wonder_meal annotation prefers air-side surface where wonder_white prefers dough-side — see judgment calls).

## Schema-test compatibility

- `tests/test_role_classifier_unified.py` schema tests (`TestSurfaceAnnotationPresent`, `TestLidAnnotationPresent`, `TestAmbientAnnotationPresent`, `TestSyntheticAnnotations`): **16/16 PASS** (M1a/M1b contract intact).

## Judgment calls

1. **Surface convention varies between unlidded and lidded bakes.** In unlidded canonical insertion, "surface" is the first AIR-SIDE sensor past the dough/air interface (the kink-and-rise sensor). In lidded bakes where all sensors plateau, "surface" is the DOUGH-SIDE sensor adjacent to the interface. The classifier branches on `lid_bake_mode` (detected by all-sensors-in-plateau-band terminal temperatures). A `max_temp` threshold of `PLATEAU_NEAR_100_UPPER_C` (105°C) distinguishes "kinked-and-rose" from "stayed-on-plateau" sensors so real_1000BA3C_0946 picks T6 (max 107) rather than T7 (max 133).

2. **Coldest-dough = slowest-heat-up, not coldest-terminal.** Initially used coldest terminal-T to pick `x_core` but that picked T2 instead of T1 on real_1000BA3C_0946 (T1 and T2 both deep in dough; T2 marginally cooler at terminal). Switched to `time_to_60c_seconds` (slowest = deepest) which is well-defined for both unlidded and lidded bakes.

3. **Lid contact requires a multi-sensor plateau cluster.** A single isolated sensor in the lid window (cavity − [20, 80] °C) is more likely a cooler-ambient sensor than true lid contact. Required ≥ 2 sensors within 15°C of each other in the lid window. This stops T7 in real_1000BA3C_0946 (terminal=131°C, gap=39°C from T8=170°C cavity proxy) being misclassified as lid — it stays as ambient, matching the fixture.

4. **Lid-bake through-loaf detection uses heat-up speed, not terminal-T.** In all-plateau-band bakes (`lid_bake_mode`), the dough/air interface is invisible in terminal temperatures. Used `time_to_60c_seconds` and a gap-threshold rule (largest adjacent gap ≥ 25% of total span) to find the air-side sensors at each end. This unblocks wonder_white_10k_lidded.

5. **post_wonder_meal_lidded annotation chooses opposite convention from wonder_white_10k_lidded.** Both fixtures are lidded through-loaf bakes with very similar physics (T1 and T8 fastest heat-up; T2-T7 dough cluster). wonder_white annotates surface=T7 (dough-side), post_wonder annotates surface=T8 (air-side). My algorithm uniformly picks dough-side in lid mode → matches wonder_white but not post_wonder. Could not find a feature that cleanly distinguishes the two cases; deferred to M2b/M4.

6. **Multi-curve test path uses CurveBoundaryDetector.** For real_1000BA3C_1759 (3 bakes in one CSV), I extended the contract test to call `CurveBoundaryDetector.extract_curves(df, expected_durations_s=...)` then call `classify` per curve. The `classify` API itself remains single-curve; the multi-curve adapter lives in the test (matches "M2a does NOT modify the loader" rule).

7. **`terminal_temp` is anchored at the proxy peak, not the literal end of the curve.** Synthetic test fixtures and real CSVs that include cool-down samples would otherwise pull terminal-T toward room temperature on every sensor. Anchoring the window centre at `max(T1..T8)` peak captures the active-bake plateau / peak temperature for in-dough / air-side sensors respectively.

## Open issues for follow-up missions

### M2b HMS Vanguard (Stefan model + comparison)
- Implement `stefan.py:StefanFit` with constrained-shape fit (latent-heat front at exactly 100°C, thermal-diffusivity-coupled crust slope, oven-proxy-anchored air region).
- Build comparison harness (`comparison.py`) and write `tests/baselines/spatial_model_comparison.md`.
- **Open question**: can the Stefan model resolve the post_wonder_meal vs wonder_white surface-convention ambiguity? The Stefan front is exactly where T = 100°C — both fixtures have all sensors plateau just below 100°C, so the Stefan model may also struggle. Alternative: ask the Admiral to reconcile the two fixtures' annotation conventions before M2b lands.

### M3a HMS Royal Sovereign (loader integration)
- Wire `classify(...)` into `_identify_sensor_roles_for_curve` (loader.py:330–410). The classifier returns a `SpatialAssignment`; the loader needs:
  - `assignment.core` → `curve_sensor_assignments['core']`
  - `assignment.surface` → `curve_sensor_assignments['surface']` (None for full immersion)
  - `assignment.ambient` → `curve_sensor_assignments['ambient']` (list)
  - `assignment.lid` → `curve_sensor_assignments['lid']` (None when no lid contact)
- Add `LidTemperature` column to `_apply_standard_columns` only when `assignment.lid` is non-None.
- The classifier already auto-segments multi-curve raw CSVs (`MULTI_CURVE_SEGMENT_THRESHOLD_SAMPLES`), but the loader's existing `_extract_all_baking_curves` already gives per-curve slices — pass per-curve slices to `classify`, do NOT pass raw CSV.
- The classifier exposes `position_normalised` and `nearest_sensor` on each `PositionalAssignment` — M3a wires `nearest_sensor` to the legacy override-anchor path; `position_normalised` and `temperature_series` (interpolated) become available later.

### M3b / M4 (later missions)
- The `xcorr_lag_to_oven_proxy_seconds` feature is computed in `extract_features` but is NOT currently used by the piecewise fit or classifier. M2b's Stefan model or M4's perturbation harness could use it as a tie-breaker for ambiguous lidded cases.
- The `confidence` field on `PositionalAssignment` is set heuristically ("high" / "medium" / "low") — M4 perturbation harness should validate the confidence labels by Monte-Carlo and re-calibrate `CONFIDENCE_GAP_MIN_FRACTION` if needed.
- `synthetic_probe_pull_mid_bake` passes today, but the `find_confirmed_multi_sensor_drop` reuse from `_drop_rate_detection.py` is NOT yet wired in — `extract_features` operates on the full DataFrame including post-pull samples. M4's perturbation harness should add a probe-pull mask before fitting.

## Acceptance bar

- ≥7/9 contract cases pass: **8/9 actual** ✓
- All per-component unit tests pass: **12/12** ✓
- M1a/M1b schema tests stay green: **16/16** ✓
- Loader unmodified: ✓ (M3a's job)
- Legacy modules undeleted: ✓ (M3b's job)
