# HMS Astute — Flotilla Sign-off

## Verdict

**MERGE** — all M0 bugs are empirically confirmed fixed, the full 338 pre-flotilla passing tests are still passing (401 pass now), no new failures, no TODOs introduced, and every closure claim is verified.

---

## 1. M0 (a) Index drift — pre-flotilla bug confirmed → post-flotilla fixed

**Repro script:** `.nelson/missions/2026-04-27_025041_6688c306/repro/verify_b2_index_drift.py`

Perturbation: 3-curve CSV loaded, `curve_sensor_assignments[0]["surface"] = "T6"`,
`curve_sensor_assignments[1]["surface"] = "T7"`, `loader.current_curve_index = 0`.

- **Pre-flotilla observed (replicated):**
  - `get_sensor_assignments_with_overrides(1)` → `surface_sensor = T7`
  - `get_sensor_assignments_with_overrides()` (no arg, falls to `loader.current_curve_index=0`) → `surface_sensor = T6`
  - **DIVERGED: True** — multiselect labels described curve 1 (T7) while plot roles described curve 0 (T6).
  - BUG PRESENT confirmed.

- **Post-flotilla observed:**
  - `curve_index = 1` hoisted once (as new `render()` does).
  - `build_sensor_label_map(loader, 1)` → `T7 (Surface)` ✓
  - `build_sensor_role_map(loader, 1)` → `T7: surface`, `T6: unknown` ✓
  - `build_sensor_role_map(loader, 0)` → `T6: surface`, `T7: unknown` ✓ (curve isolation confirmed)
  - Both helpers see the same index; no divergence possible.
  - **BUG FIXED confirmed.**

- **Flip confirmed:** True (pre-flotilla BUG PRESENT → post-flotilla FIXED)
- **Closure mission:** M3 (commit 9d4503c)

---

## 2. M0 (b) Heatmap role-blindness — pre-flotilla bug confirmed → post-flotilla fixed

**Repro script:** `.nelson/missions/2026-04-27_025041_6688c306/repro/verify_b1_heatmap_roles.py`

Synthetic DataFrame: T1–T8 columns. Role overrides: `T2=surface`, `T7=ambient`.

- **Pre-flotilla observed (replicated):**
  - `plot_temperature_gradient_heatmap(data)` — no `sensor_roles` arg.
  - y: `['Core 1', 'Core 2', 'Core 3', 'Core 4', 'Middle 1', 'Middle 2', 'Near Surface', 'Surface']`
  - No `(Surface)` or `(Ambient)` suffix anywhere. T2 showed `Core 2`; T7 showed `Near Surface`.
  - **BUG PRESENT confirmed** (role-blind, invariant labels).

- **Post-flotilla observed:**
  - `plot_temperature_gradient_heatmap(data, sensor_roles={'T2': 'surface', 'T7': 'ambient'})`
  - y: `['Core 1', 'Core 2 (Surface)', 'Core 3', 'Core 4', 'Middle 1', 'Middle 2', 'Near Surface (Ambient)', 'Surface']`
  - T2 label includes `(Surface)`: True
  - T7 label includes `(Ambient)`: True
  - T8 (no role) uses firmware default `Surface` with no suffix: True
  - **BUG FIXED confirmed.**

- **Flip confirmed:** True (pre-flotilla BUG PRESENT → post-flotilla FIXED)
- **Closure mission:** M2 (commit e72c164)

---

## 3. M0 (c) Test coverage delta

Token grep counts in `tests/` (files with matches):

| Token | Pre-flotilla files | Post-flotilla files | Post-flotilla occurrences |
|---|---|---|---|
| `plot_temperature_profile` | 0 | 1 (test_temperature_profile_e2e.py) | 11 |
| `plot_temperature_gradient_heatmap` | 0 | 3 (test_heatmap_role_aware.py, test_temperature_profile_e2e.py, test_temperature_profile_flotilla_finale.py) | 16 |
| `index_drift` / `B2` / `curve_index drift` | 0 | 3 (test_temperature_profile_render.py, test_temperature_profile_e2e.py, test_temperature_profile_flotilla_finale.py) | 35 |

- **Pre-flotilla: 0/0/0**
- **Post-flotilla: 11/16/35 occurrences across 1/3/3 files**

New test files added:
1. `tests/test_sensor_role_helpers.py` (M1)
2. `tests/test_heatmap_role_aware.py` (M2)
3. `tests/test_temperature_profile_render.py` (M3)
4. `tests/test_sensor_list_migration.py` (M4)
5. `tests/test_temperature_profile_e2e.py` (M5)
6. `tests/test_temperature_profile_flotilla_finale.py` (M5)

Confirmed: 6 new test files (migration guard is in `test_sensor_list_migration.py`, not embedded in another).

---

## 4. Pytest baseline preservation

- **M0 baseline:** 338 passed / 8 failed / 1 skipped (347 collected)
- **Post-M5:** 401 passed / 8 failed / 2 skipped (411 collected)
- **Delta:** +63 passing tests, same 8 failures, +1 skip
- **Pre-flotilla 338 still passing: YES**

The 8 failures are identical to the M0 pre-existing set:
- `test_curve_comparison_integration.py::TestDataFlowIntegration::test_zone_color_consistency`
- `test_internal_sensor_filtering.py::TestInternalSensorFiltering::test_realistic_baking_profile`
- `test_surface_sensor_detection.py::TestSurfaceSensorDetection::test_shallow_insertion`
- `test_surface_sensor_detection.py::TestSurfaceSensorDetection::test_deep_insertion`
- `test_visualization.py::TestThermalPlotter::test_plot_zone_duration_comparison`
- `test_visualization.py::TestEdgeCases::test_single_curve_comparison`
- `test_visualization.py::TestEdgeCases::test_many_curves_comparison`
- `test_visualization.py::TestEdgeCases::test_unknown_zone_handling`

No flotilla-induced regressions.

---

## 5. Confirmed-defect closure summary

| ID | Status | Mission | Commit | Verification |
|---|---|---|---|---|
| B1 | closed | M2 | e72c164 | Empirical repro: pre-flotilla y-labels role-blind confirmed; post-flotilla `sensor_roles` arg propagates to y-axis labels. Flip confirmed. |
| B2 | closed | M3 | 9d4503c | Empirical repro: pre-flotilla surface_sensor diverges (T7 vs T6) when loader.current_curve_index=0 but arg=1; post-flotilla single hoisted index, both helpers agree. Flip confirmed. |
| S1 | closed | M3 | 9d4503c | Pattern A (inline role-detection loop in render) absent from `tabs/temperature_profile.py` — grep finds zero direct calls to `get_sensor_assignments_with_overrides` in tabs/. |
| S2 | closed | M3 | 9d4503c | Pattern B (inline role-iteration) absent — `tabs/temperature_profile.py` delegates entirely to `build_sensor_label_map` / `build_sensor_role_map`; no inline loop. |
| S3 | closed | M2 | e72c164 | `plot_temperature_gradient_heatmap` raises `ValueError("No sensor columns in data…")` on empty-column input; guard added at line 233. |
| S4 | deferred | — | — | Session-state/loader coupling decoupling is post-flotilla; out of scope. |
| S5 | deferred | — | — | Accessibility (colour-only role encoding) is out of scope; low priority. |
| S6 | closed | M3 | 9d4503c | Zero direct `get_sensor_assignments_with_overrides` calls remain in `tabs/` or `src/` (excluding the helper module itself and loader definition). Double-fetch eliminated. |
| S7 | closed (superseded) | M2+M3 | e72c164 + 9d4503c | `plots.py` lines 107-113 originally duplicated the role-iteration logic. Post-refactor, `plot_temperature_profile` receives a ready-built `sensor_roles` dict (no internal iteration); `plot_temperature_gradient_heatmap` does the same. The role loop in `src/analysis/curve_comparison.py:transform_sensor_assignments_to_roles` is still live code used by `CurveComparison` (not dead code) but is a different, narrower function; it does not duplicate the tab-side logic. |
| DRY-A | closed | M1+M4 | 5524a0b + 16e9d56 | `SENSOR_LIST` defined exactly once at `config/constants.py:397`; all sensor list constructions in `src/`, `tabs/`, `sidebar.py` import from this single source. |
| DRY-B | closed | M3 | 9d4503c | Inline three-place role-iteration loop (Pattern B) replaced by `build_sensor_role_map` helper call. `transform_sensor_assignments_to_roles` in `src/analysis/curve_comparison.py` is still used by `CurveComparison` test infrastructure — not dead code, but a distinct function operating on a different input format (loader-format dict → role map). Not a duplication of the helper. |

---

## 6. Branch readiness

- **Commit count from main:** 12 commits (5 code: M1–M5; 5 nelson artefact chores; 1 flotilla plan; 1 review artefact)
- **Final delta:** 73 files changed, 6574 insertions(+), 93 deletions(-)
  - New source files: `src/ui/sensor_role_helpers.py`
  - Modified source: `src/visualization/plots.py`, `tabs/temperature_profile.py`, `config/constants.py`, `sidebar.py`, `src/analysis/curve_comparison.py`, `src/data/curve_boundary_detector.py`, `src/data/loader.py`
  - New test files: 6 (all in `tests/`)
- **Pre-existing failures still 8:** YES (identical set, no new failures)
- **TODOs/FIXMEs introduced:** 0 (grep across all flotilla-touched source and test files returns empty)
- **MERGE-ready: YES**

---

## Concerns (post-merge follow-ups)

1. **S4 — session_state/loader coupling:** `render()` reads `st.session_state.current_curve_index` and `st.session_state.loader` directly. If a future shortcut key or URL-param handler updates session state without calling `loader.set_current_curve()`, the B2 scenario can re-emerge through the `loader` path rather than the helper path. A future refactor should consider passing `loader` and `curve_index` as parameters rather than reading from `st.session_state` inside `render()`.

2. **S7 / transform_sensor_assignments_to_roles DRY residue:** `curve_comparison.py:transform_sensor_assignments_to_roles` constructs a role map from a different input format (list-valued dict) than `build_sensor_role_map` (which takes a loader). These serve different callers and are not yet unified. Low urgency but worth consolidating if `CurveComparison` is ever refactored to use the loader-based helpers directly.

3. **Pre-existing test failures (8):** The 8 failures in `test_visualization.py`, `test_curve_comparison_integration.py`, `test_internal_sensor_filtering.py`, and `test_surface_sensor_detection.py` predate this flotilla and are unrelated to it. They should be scheduled for a dedicated fix mission.

4. **`test_flotilla_finale_regression.py`** already existed before M5 (it appears in the test listing); HMS Achilles added `test_temperature_profile_flotilla_finale.py` as the new finale. The old `test_flotilla_finale_regression.py` should be reviewed for overlap/conflicts in a follow-up.
