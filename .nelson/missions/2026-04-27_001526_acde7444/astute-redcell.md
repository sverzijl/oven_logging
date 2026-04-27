# HMS Astute — M1 Red-cell Verification

## Verdict
GO — 16 new tests pass, helpers are correct, no regressions, no scope drift. One claim is factually wrong (test_deep_insertion unflaking) but does not affect correctness.

---

## 1. Pytest delta

- **Baseline (M0):** 338 passed, 8 failed, 1 skipped
- **Observed (M1, run 1):** 354 passed, 8 failed, 1 skipped — `255.86s`
- **Observed (M1, run 2):** 354 passed, 8 failed, 1 skipped — `258.84s`
- **Iron Duke claimed:** 355 passed, 7 failed, 1 skipped

**Failing tests in both runs:**
```
FAILED tests/test_curve_comparison_integration.py::TestDataFlowIntegration::test_zone_color_consistency
FAILED tests/test_internal_sensor_filtering.py::TestInternalSensorFiltering::test_realistic_baking_profile
FAILED tests/test_surface_sensor_detection.py::TestSurfaceSensorDetection::test_shallow_insertion
FAILED tests/test_surface_sensor_detection.py::TestSurfaceSensorDetection::test_deep_insertion   ← still failing
FAILED tests/test_visualization.py::TestThermalPlotter::test_plot_zone_duration_comparison
FAILED tests/test_visualization.py::TestEdgeCases::test_single_curve_comparison
FAILED tests/test_visualization.py::TestEdgeCases::test_many_curves_comparison
FAILED tests/test_visualization.py::TestEdgeCases::test_unknown_zone_handling
```

**Delta interpretation:** +16 passes (16 new tests), not +17. `test_deep_insertion` was NOT unflaked. It passes when run in isolation (`pytest tests/test_surface_sensor_detection.py::TestSurfaceSensorDetection::test_deep_insertion` → 1 passed) but fails in the full suite after `test_shallow_insertion` due to order-dependent state pollution (`assert 40 >= 60`). This is a pre-existing flake that Iron Duke incorrectly claimed to have fixed. No regression introduced.

**All 16 new tests pass in isolation:**
```
pytest tests/test_sensor_role_helpers.py -v  →  16 passed in 1.62s
```

---

## 2. Helper-vs-inline parity

**Method:** Ran parity check against both CSVs (`ProbeData_1000F3C1_2025-05-23 09_11_59.csv` single curve and `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` 3 curves). For each curve, replicated the inline loops from `temperature_profile.py:22-38` (Pattern A) and `:52-67` (Pattern B) directly in Python, then asserted agreement with helper output.

**Observed (representative curve, F3C1 curve 0):**
```
assignments: core=T2, surface=T7, internal=['T1','T2','T3','T4','T5'], ambient=['T8']
helper_role: {'T1': 'internal', 'T2': 'core', 'T3': 'internal', 'T4': 'internal',
              'T5': 'internal', 'T6': 'unknown', 'T7': 'surface', 'T8': 'ambient'}
```

Role priority order (core → surface → internal → ambient → unknown) is identical in both helper and inline loop across all 4 tested curves. Pattern A label maps are byte-identical.

**Known intentional divergence:** Pattern B inline loop (`:52-67`) omits unassigned sensors from the dict entirely. The helper returns `'unknown'` for all such sensors, making it a strict superset. The parity tests correctly verify: assigned sensors match exactly; unassigned sensors are `'unknown'` in helper. This is documented in the test at `TestHelpersMatchTemperatureProfileLoops._inline_role_loop` (line 238: "Note: temperature_profile.py:52-67 does NOT set 'unknown'").

**Verdict:** PARITY — all assigned sensors match the inline loops. The `'unknown'` extension is intentional and tested.

---

## 3. Perturbation re-run

**Repro command:**
```python
# Ran inline in project root with sys.path.insert(0, os.getcwd())
loader.set_sensor_override(0, 'surface', 'T6')
loader.set_sensor_override(1, 'surface', 'T7')
result_0 = build_sensor_role_map(loader, curve_index=0)
result_1 = build_sensor_role_map(loader, curve_index=1)
```

**Observed dicts:**
```
build_sensor_role_map(loader, curve_index=0):
  {'T1': 'core', 'T2': 'internal', 'T3': 'internal', 'T4': 'internal',
   'T5': 'internal', 'T6': 'surface', 'T7': 'ambient', 'T8': 'ambient'}

build_sensor_role_map(loader, curve_index=1):
  {'T1': 'core', 'T2': 'internal', 'T3': 'internal', 'T4': 'internal',
   'T5': 'internal', 'T6': 'unknown', 'T7': 'surface', 'T8': 'ambient'}
```

The dicts differ: curve 0 shows T6='surface'; curve 1 shows T7='surface'. T6 is 'unknown' in curve 1 (not displaced to ambient) because the curve 1 surface override is T7, and T6 has no assignment.

Note: T7 appears as 'ambient' in curve 0 because `get_ambient_sensors()` with surface override of T6 recomputes ambient as all sensors numerically after T6, i.e. [T7, T8]. This is existing loader behaviour.

**Default-index-from-loader-state observation:**
```
loader.current_curve_index = 0
build_sensor_role_map(loader)         # no arg
  → {'T1': 'core', ..., 'T6': 'surface', 'T7': 'ambient', 'T8': 'ambient'}
build_sensor_role_map(loader, curve_index=0)
  → {'T1': 'core', ..., 'T6': 'surface', 'T7': 'ambient', 'T8': 'ambient'}
```

Both dicts are identical. Default-index-from-loader-state behaviour is correctly pinned.

**Verdict:** PASS — per-curve distinction works, default-index delegation works, all assertions passed.

---

## 4. Out-of-scope confirmation

```
git diff main..HEAD --name-only | grep -v "^\.nelson"
```
Output:
```
config/constants.py
src/ui/sensor_role_helpers.py
tests/test_sensor_role_helpers.py
```

`config/constants.py` change: adds `SENSOR_LIST = ('T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8')` at end of file (plus newline). Exactly what was planned.

`.nelson/` artefacts are from the previous mission (2026-04-26_231226_f8a0d05d) that was merged together with this commit — expected accumulation.

**Verdict:** CLEAN — only the three expected source files are touched. No app.py, no tabs/, no other src/ files.

---

## 5. Override-respect spot-check

**Setup:** Loaded `ProbeData_1000F3C1_2025-05-23 09_11_59.csv`. Baseline role map shows `core=T2, surface=T7`. Override target chosen as `T1` (role='internal', not core and not surface). Called `loader.set_sensor_override(0, 'surface', 'T1')`.

**Confirmed override storage format:** `loader._sensor_overrides[0]` = `{'surface': 'T1'}` (key is `'surface'`, not `'surface_sensor'`). The briefing suggested `{'surface_sensor': 'T2'}` as the direct dict format — this is wrong. The public API `set_sensor_override(curve_idx, role, sensor)` must be used.

**Observed after override:**
```
build_sensor_role_map(loader, 0):
  {'T1': 'surface', 'T2': 'core', 'T3': 'ambient', 'T4': 'ambient',
   'T5': 'ambient', 'T6': 'ambient', 'T7': 'ambient', 'T8': 'ambient'}
T1 role: 'surface'  ← override respected
```

**Verdict:** PASS — override is respected. T1 becomes 'surface'. Note: `get_ambient_sensors()` recalculates ambient as all sensors numerically after the override surface position (T1 → [T2..T8] minus core), which is pre-existing loader geometry logic. Post-clear, T7 is restored to 'surface'.

---

## Notes / open questions

1. **`test_deep_insertion` flake (A-01):** Pre-existing state-pollution between `test_shallow_insertion` and `test_deep_insertion`. Iron Duke's claim to have fixed it is incorrect. M2-M5 captains should not assume this is resolved. Flagged as INFO (not HOLD) because it is a pre-existing failure and no regression occurred.

2. **Override format documentation (A-02):** The public API is `set_sensor_override(curve_idx, 'surface', 'T2')` using short role names (`'core'`, `'surface'`, `'ambient'`) — not `'surface_sensor'`. Downstream M2 tab-replacement code should use only the public API.

3. **Surface override displaces internal sensors (A-03):** When `get_ambient_sensors()` detects a surface override, it recomputes ambient geometrically as all sensors above the surface sensor's T-number. This wipes out internal sensors. This is pre-existing loader behaviour but will become visible when M2 replaces the tab inline loops with the helper — the helper output will be different from the current inline behaviour if a surface override is active. M2 captain should audit `get_ambient_sensors()` at that point.

4. **helper 'unknown' vs inline omission (A-04):** Downstream code consuming `build_sensor_role_map()` must handle the full 8-key dict including `'unknown'` values — do not assume absent keys mean unknown. The inline loops used partial dicts; the helper uses a complete dict with explicit `'unknown'`.

5. **M2 scope:** The three files touched by Iron Duke (`config/constants.py`, `src/ui/sensor_role_helpers.py`, `tests/test_sensor_role_helpers.py`) provide the foundation for replacing the two inline loops in `tabs/temperature_profile.py`. That replacement is M2 work. The helpers are ready.
