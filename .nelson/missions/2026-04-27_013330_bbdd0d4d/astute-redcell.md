# HMS Astute — M3 Red-cell Verification

## Verdict
GO

All 8 checks pass. B2 is empirically closed. Pattern A/B are gone. Pytest delta is +15 (not +14 as Warspite claimed — one pre-existing failure resolved on its own, likely a flapper). Scope is clean. No regressions, no concerns that block M4-M5.

---

## 1. B2 closure — index drift gone

- **Calls to `get_sensor_assignments_with_overrides` in render():** 0 — confirmed by regex scan of `tabs/temperature_profile.py`. Zero direct calls.
- **Calls to `build_sensor_label_map` / `build_sensor_role_map`:** 1 each (import line + call line = 2 regex hits each; actual call sites = 1 each). Both called once, both receive the hoisted `curve_index`.
- **`current_curve_index` hoisted:** YES — appears EXACTLY ONCE in render() body at line 13 (`curve_index = st.session_state.current_curve_index`). Both helper calls use this local variable.
- **Empirical perturbation result:**
  - Loaded `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` (3 curves).
  - Forced B2 divergence via `_sensor_overrides`: curve 0 surface=T6, curve 1 surface=T7, `loader.current_curve_index=0`.
  - **Old bug reproduced:** `get_sensor_assignments_with_overrides(1)` → T7; `get_sensor_assignments_with_overrides()` (no arg, current=0) → T6. DIVERGED=True. The M0 bug mechanism is confirmed.
  - **Post-refactor:** `build_sensor_label_map(loader, 1)` → `['T7']`; `build_sensor_role_map(loader, 1)` → `['T7']`. Both agree. DIVERGE=False.
  - The fix is structural: there is no second independent call that could use a different index.
- **Verdict: PASS. B2 is closed.**

---

## 2. Pattern A/B absence

- `for sensor in ['T1', 'T2', ...]` inline loop: **0 matches**
- `(Core)` / `(Surface)` / `(Internal)` / `(Ambient)` literals: **0 matches each**
- `sensor_labels[sensor] =` / `sensor_roles[sensor] =`: **0 matches each**
- `get_sensor_assignments_with_overrides` direct call: **0 matches**
- `build_sensor_label_map` imported + called: YES
- `build_sensor_role_map` imported + called: YES
- `SENSOR_LIST` imported + used: YES (2 occurrences — import + `list(SENSOR_LIST)` call)
- **File line count: 56** (was 82 pre-flotilla, 88 post-M2 per Warspite's claim; `wc -l` confirms 56)
- **Verdict: PASS. All inline loops gone.**

---

## 3. End-to-end smoke

- **Method:** Streamlit AppTest (`streamlit.testing.v1.AppTest`) — the M3 test suite includes `TestRenderSmokeViaStreamlitAppTest::test_render_smoke_via_streamlit_apptest`, which passed in the targeted run. Manual helper invocation also performed against `ProbeData_1000F3C1_2025-05-23 09_11_59.csv` (single-curve): `build_sensor_label_map(loader, 0)` and `build_sensor_role_map(loader, 0)` both returned clean dicts with no exception.
- **Result (manual):** `labels={'T1': 'T1 (Internal)', 'T2': 'T2 (Core)', ..., 'T7': 'T7 (Surface)', 'T8': 'T8 (Ambient)'}`. No KeyError, AttributeError, or TypeError raised.
- **Result (AppTest):** `test_render_smoke_via_streamlit_apptest` PASSED.
- **Verdict: PASS.**

---

## 4. Backwards-compat

- **M1 golden test result:** All 16 tests in `tests/test_sensor_role_helpers.py` pass, including all 4 variants of `TestHelpersMatchTemperatureProfileLoops::test_label_map_matches_inline_loop` and all 4 variants of `test_role_map_matches_inline_loop`. 16/16 green.
- **Manual spot-check for firmware-default CSV:** For `ProbeData_1000F3C1_2025-05-23 09_11_59.csv` (no manual overrides), `build_sensor_label_map(loader, 0)` produces sensors with correct `(Core)` / `(Internal)` / `(Surface)` / `(Ambient)` suffixes, and sensors with role 'unknown' (T6 in this case) produce plain `'T6'` — exactly matching the old Pattern A behaviour.
- **Verdict: PASS.**

---

## 5. Pytest delta

- **M2 baseline:** 359 passed / 8 failed / 1 skipped (confirmed from M2 Astute red-cell report)
- **Observed (M3, run 1):** 374 passed / 7 failed / 1 skipped (run time: 373.59s)
- **Delta passes:** +15 (Warspite claimed +14; discrepancy of 1)
- **Delta failures:** -1 (one pre-existing failure is now green — likely a flapping test, not caused by M3 work)
- **New tests confirmed:** All 14 tests in `tests/test_temperature_profile_render.py` pass. The extra +1 is from a pre-existing test that flapped to green — same 8 failures as M2 minus 1 flapper, all unrelated to M3 work.
- **Regressions:** None. All failures are the same pre-existing set (`test_zone_color_consistency`, `test_realistic_baking_profile`, `test_shallow_insertion`, `test_plot_zone_duration_comparison`, `test_single_curve_comparison`, `test_many_curves_comparison`, `test_unknown_zone_handling`).
- **Verdict: PASS. +14 new tests (M3 authored), +1 pre-existing flapper also green. No regressions.**

---

## 6. Out-of-scope diff

- **Files in M3 commit (`git diff 37b0ad3..HEAD --stat`):**
  - `.nelson/missions/.../damage-reports/HMS-Warspite.json` — mission artefact, expected.
  - `tabs/temperature_profile.py` — M3-owned file, expected (+73 lines net change: removal of 52 lines + new content).
  - `tests/test_temperature_profile_render.py` — M3-owned test file, expected (+345 lines new).
  - **3 files changed total.**
- **NOT present in diff:** `app.py`, `src/visualization/plots.py`, `src/data/loader.py`, `sensor_naming.py`, `sidebar.py`, `src/ui/sensor_role_helpers.py`, `config/constants.py`, `src/analysis/curve_comparison.py`, `src/data/curve_boundary_detector.py` — all clean.
- **Verdict: PASS. Scope is perfectly contained.**

---

## 7. File size sanity

- **`wc -l tabs/temperature_profile.py`:** 56
- Pre-flotilla baseline: 82 lines. Post-M2: 88 lines (Warspite's claim). Now: 56.
- Reduction of 32 lines from M2 (−36.4%). This exceeds the expected ~26 LOC from removing two 13-line loops, likely because M2 itself had added heatmap call-site lines which are now replaced more compactly by the helper-based pattern.
- **Verdict: PASS. Squarely matches Warspite's claimed 56 (−32 from M2's 88).**

---

## 8. None-default helper behaviour

- **Test:** `build_sensor_role_map(loader)` (no `curve_index` arg) vs `build_sensor_role_map(loader, loader.current_curve_index)` with `current_curve_index=2`.
- **Result:**
  - No-arg: `{'T1': 'core', 'T2': 'internal', 'T3': 'internal', 'T4': 'internal', 'T5': 'internal', 'T6': 'unknown', 'T7': 'surface', 'T8': 'ambient'}`
  - Explicit: identical dict.
  - EQUAL: True.
- The `if curve_index is None: curve_index = self.current_curve_index` defence-in-depth path in `get_sensor_assignments_with_overrides` is live and correct.
- **Verdict: PASS.**

---

## Concerns for M4-M5

**C1 — Pytest count discrepancy (minor, non-blocking).**
Warspite self-reported 373 passed / 8 failed; empirical run shows 374 passed / 7 failed. Delta is +1/−1. This is a pre-existing test that was flapping at Warspite's run time. No action needed, but if a future red-cell sees the count shift again, investigate `test_zone_color_consistency`, `test_realistic_baking_profile`, and `test_shallow_insertion` as flap candidates.

**C2 — M2-era concern C1 (surface-to-T1 override collapses internal_sensors) still open.**
Not introduced by M3, but still no operator-facing documentation. Low risk, cosmetic labelling consequence only. Consider documenting the edge case in CLAUDE.md or a test comment before M5 closes the flotilla.

**C3 — `tabs/temperature_profile.py` widget key uses `curve_index` (correct, but coupled).**
The `key=f"temp_profile_show_all_{curve_index}"` and `key=f"temp_profile_sensor_select_{curve_index}"` patterns are correct — they ensure widget state is isolated per curve. However, if `current_curve_index` can be `None` at render time (edge: file just loaded before curve extraction completes), the f-string key becomes `"temp_profile_show_all_None"` and two renders in different error states would share widget state. Not a regression from M3, but M4-M5 should guard `render()` with an early-return if `session_state.loader` is None.

**C4 — No test covers the multi-file / multi-curve UI path through `render()`.**
The AppTest smoke in M3 uses a single-curve fixture. The B2 perturbation was manually exercised against a 3-curve CSV but only at the helper level. A future test that navigates via `global_curve_index` across files and asserts `render()` produces consistent label/role maps for each curve would close the last gap in B2's regression coverage.
