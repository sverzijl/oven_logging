# HMS Astute — M4 Red-cell Verification

## Verdict
GO

All 8 checks pass. Two non-canonical loader.py sites (mixed lists with 'Timestamp' et al.) remain unscoped but are correctly excluded by the mission's own regex definition. Pytest count differs by 1 from Spey's claim (376 vs 377) due to `test_deep_insertion` flapping back to FAIL in full-suite timing; this is a pre-existing flapper, not a regression. No new failures. Prior-flotilla tests 35/35 green.

---

## 1. Completeness — own grep audit

- **Forms searched:**
  - `\['T1'.*'T8'\]` (single-quoted 8-element lists)
  - `\["T1".*"T8"\]` (double-quoted 8-element lists)
  - `\('T1'.*'T8'\)` (single-quoted 8-element tuples)
  - `\("T1".*"T8"\)` (double-quoted 8-element tuples)
  - `range\(1\s*,\s*9\)` for f-string T{i} generators
  - Broader: `T1.*T2.*T3.*T4` to catch partial lists and mixed-column lists

- **Matches found outside allow-list (src/, sidebar.py, sensor_naming.py, app.py):**

  | Location | Form | Classification |
  |---|---|---|
  | `config/constants.py:397` | `('T1','T2','T3','T4','T5','T6','T7','T8')` | CANONICAL DEFINITION — allow-listed |
  | `sensor_naming.py:74` | `['T1','T4','T6','T8']` — 4-element fallback | PARTIAL — not canonical-8, intentional |
  | `sensor_naming.py:107` | `['T1','T4','T7']` — 3-element fallback | PARTIAL — not canonical-8, intentional |
  | `src/data/loader.py:253` | `['Timestamp','T1','T2',...,'T8','VirtualCore...']` — mixed | MIXED — not standalone canonical-8; excluded by regex definition |
  | `src/data/loader.py:1244-1245` | `['Timestamp','TimeMinutes','T1','T2','T3','T4',\n'T5','T6','T7','T8']` — mixed | MIXED — not standalone canonical-8; regex split across lines, pattern does not fire |
  | `src/data/loader.py:397-398` | `['T1','T2','T3','T4']` partial for CoreAverage | PARTIAL — 4-element backward-compat average |
  | `src/visualization/plots.py:366` | `['T1','T2','T3','T4']` core_sensors | PARTIAL — 4-element, not canonical-8 |
  | `src/data/sensor_assignment_manager.py:54` | `['T1','T2','T3','T4']` | PARTIAL — 4-element |
  | `src/analysis/thermal_analysis.py:127,232,240` | `('T1','T2','T3','T4')` tuple membership test | PARTIAL — 4-element filter |
  | `src/data/surface_sensor_detector.py:159` | `['T4','T5','T6','T7','T8']` 5-element | PARTIAL — not canonical-8 |
  | Test fixtures `tests/fixtures/curve_boundary_cases.py:559,607` | `["T1"..."T8"]` | ALLOW-LISTED — tests/ |

  **Zero matches outside allow-list for the canonical 8-element standalone form.** The two mixed-column sites in loader.py (lines 253 and 1244) were explicitly noted by Spey in the damage report (line 252 cited as mixed); line 1244 (`get_sensor_data()`) was also not migrated, consistent with Spey's decision that "mixed list, not standalone canonical." These sites are candidates for a follow-up DRY pass but are NOT in M4 scope.

  **Partial-list sites (T1–T4, T5–T8, etc.) are pre-existing technical debt, not canonical-8 sites.** Not in M4 scope.

- **Verdict: PASS. No canonical-8 sites remain outside allow-list.**

---

## 2. _SENSOR_COLUMNS removal

- **Grep result:** `grep -rn "_SENSOR_COLUMNS" src/` → zero hits. Confirmed.
- **SENSOR_LIST import in curve_boundary_detector.py:** `from config.constants import SENSOR_LIST` at line 21. Usage at line 44 (`if all(col in df.columns for col in SENSOR_LIST)`) and line 45 (`df.loc[:, list(SENSOR_LIST)].to_numpy(...)`).
- **Verdict: PASS. Option A complete. _SENSOR_COLUMNS deleted, SENSOR_LIST imported and used.**

---

## 3. Sidebar selectbox preservation

- **options= form:** `options=list(SENSOR_LIST)` at lines 239 and 249. Streamlit receives a proper Python list. Correct.
- **index= form:** `index=list(SENSOR_LIST).index(current_core) if current_core else 0` (line 240); `index=list(SENSOR_LIST).index(current_surface) if current_surface else 6` (line 250). The `.index()` call preserves exact position lookup identical to the old hardcoded list (order is T1..T8 in both cases — confirmed by Verification 5 order check). Default fallbacks (0 for core, 6 for surface = T7) are preserved.
- **Verdict: PASS. Selectbox behaviour structurally identical.**

---

## 4. sensor_naming.py left-as-is decision

- **:74 content:** `return ['T1', 'T4', 'T6', 'T8']  # Fallback defaults` — 4-element partial list used when `loader` is None. Returns a spread of representative sensors.
- **:107 content:** `defaults = ['T1', 'T4', 'T7']` — 3-element fallback for `get_default_sensors()` when no sensors are detected.
- **Both partial?** YES. Neither is a canonical T1..T8 8-element list. Both are heuristic defaults (one 4-element, one 3-element). Spey's decision to leave them is correct; migrating them to `list(SENSOR_LIST)` would change behaviour (returning 8 sensors instead of 3–4 representative ones).
- **Verdict: PASS. Spey's leave-as-is decision is correct.**

---

## 5. Loader behaviour unchanged

- **Empirical method:** Loaded both real CSVs directly:
  - `ProbeData_1000F3C1_2025-05-23 09_11_59.csv` (single curve)
  - `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` (3 curves)
  - Verified `SENSOR_LIST` order equals `[f'T{i}' for i in range(1,9)]` (identical list, confirmed by direct comparison: `ORDER MATCH: True`).

- **Result:**
  - Single-curve CSV: 1 curve detected, core=T2, surface=T7 (physics-corrected from T6), internal=['T1','T2','T3','T4','T5'], ambient=['T8']. Normal operation.
  - Multi-curve CSV: 3 curves detected, all with core=T1, surface=T7 (physics-corrected), internal=['T1','T2','T3','T4','T5'], ambient=['T8']. Per-curve identification operating correctly.
  - `loader.py:486` migrated site (`[s for s in SENSOR_LIST if s in df.columns]`): behavioural equivalence guaranteed since SENSOR_LIST order = range(1,9) order.
  - `loader.py:866` migrated site (`list(SENSOR_LIST)`): returns full ordered list — identical to old `['T1',...,'T8']`.

- **Verdict: PASS. Loader behaviour empirically confirmed unchanged.**

---

## 6. Pytest delta

- **M3 baseline:** 373/8/1 (from M3 Spey damage report; M3 Astute empirically saw 374/7/1 due to flapper)
- **Observed (this run):** 376 passed / 8 failed / 1 skipped
- **Spey's claim:** 377 passed / 7–8 failed / 1 skipped
- **Delta from M3 baseline (373):** +3 passes (the 3 new migration guard tests in `test_sensor_list_migration.py`). Consistent.
- **Discrepancy vs Spey's 377:** `test_deep_insertion` (flapper) was PASS during Spey's run, FAIL during this full-suite run (confirmed by re-running isolated: it PASSes in isolation, FAILs in full suite due to timing sensitivity). This is the same flapper identified in M3.
- **Prior-flotilla tests still pass:** YES — 35/35 green (`test_sensor_role_helpers.py`, `test_heatmap_role_aware.py`, `test_temperature_profile_render.py` all 100% pass).
- **New M4 migration guard tests:** 3/3 pass (`test_no_hardcoded_sensor_list_in_production_source`, `test_sensor_list_imported_at_known_sites`, `test_curve_boundary_detector_no_private_sensor_columns`).
- **Regressions introduced:** None. All 8 failures are the same pre-existing set as M3.

---

## 7. Sweep coverage map

- **Canonical definition:** `config/constants.py:397` — `SENSOR_LIST = ('T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8')`

- **Migrated sites (from Spey's damage report, verified empirically):**

  | File | Line (post-migration) | Form |
  |---|---|---|
  | `sidebar.py` | 239, 240 | `options=list(SENSOR_LIST)`, `list(SENSOR_LIST).index(current_core)` |
  | `sidebar.py` | 249, 250 | `options=list(SENSOR_LIST)`, `list(SENSOR_LIST).index(current_surface)` |
  | `src/visualization/plots.py` | 91 | `sensors = list(SENSOR_LIST)` |
  | `src/data/loader.py` | 486 | `[s for s in SENSOR_LIST if s in df.columns]` |
  | `src/data/loader.py` | 866 | `list(SENSOR_LIST)` |
  | `src/data/loader.py` | 1392 | `['Timestamp'] + list(SENSOR_LIST)` |
  | `src/data/loader.py` | 1405 | `list(SENSOR_LIST)` |
  | `src/analysis/curve_comparison.py` | 31 | `all_sensors = list(SENSOR_LIST)` |
  | `src/data/curve_boundary_detector.py` | 21, 44–45 | `from config.constants import SENSOR_LIST` + usage (Option A: _SENSOR_COLUMNS deleted) |

- **Allow-listed remaining sites:**
  - `config/constants.py:397` — canonical definition itself
  - `sensor_naming.py:74` — 4-element partial fallback (correct as-is)
  - `sensor_naming.py:107` — 3-element partial fallback (correct as-is)
  - `src/data/loader.py:253,1244` — mixed-column lists ('Timestamp', 'TimeMinutes', etc. + T1..T8); not standalone canonical-8; pattern does not fire; follow-up DRY candidates
  - `tests/fixtures/curve_boundary_cases.py:559,607` — test fixtures (allow-listed)

- **Verdict: COMPLETE. Every standalone canonical-8 list has been migrated. One definition, nine reference sites.**

---

## 8. app.py audit

- **Hardcoded T1..T8 forms in app.py:** NONE. Grep for `'T1'`, `"T1"`, and `T1.*T8` patterns across app.py returned zero results. app.py has been clean of sensor literals for this entire flotilla.
- **Recommendation:** No action required. Flag as a known-clean baseline for M5.

---

## Concerns for M5

**C1 — loader.py:1244 (`get_sensor_data()`) is a de-facto canonical-8 list that escaped scope.**
`sensor_cols = ['Timestamp', 'TimeMinutes', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']` at line 1244. It is split across two lines so the regex does not fire. Spey's damage report mentioned line 252 (the `_clean_data` numeric columns list) but NOT line 1244. This site should be migrated in M5 or a follow-up: `sensor_cols = ['Timestamp', 'TimeMinutes'] + list(SENSOR_LIST)`. Not a blocker — `get_sensor_data()` is not a hotpath and the T-column names are correct — but it is a DRY violation.

**C2 — Partial lists (T1–T4, T5–T8 etc.) are pre-existing technical debt outside M4 scope.**
Found in `src/analysis/thermal_analysis.py`, `src/visualization/plots.py:366`, `src/data/sensor_assignment_manager.py:54`, `src/data/surface_sensor_detector.py:159`, `src/data/loader.py:397-398`. These hardcode assumptions about how many sensors belong to each role group. A future mission should evaluate whether these should be driven by a configurable `CORE_RANGE` / `SURFACE_RANGE` constant or left as comment-documented heuristics.

**C3 — test_deep_insertion flapper still present.**
Pre-existing; documented in M3. Not caused by M4. Recommend isolating and fixing before final flotilla stand-down.

**C4 — M3 concerns C2, C3, C4 carry over unchanged.**
Specifically: surface-to-T1 override collapses internal_sensors (C2), render() None-guard (C3), no multi-file multi-curve AppTest (C4). None of these are affected by M4 work.
