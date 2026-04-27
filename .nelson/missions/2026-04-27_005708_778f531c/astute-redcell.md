# HMS Astute — M2 Red-cell Verification

## Verdict
GO

All 7 checks pass. B1 and S3 are empirically closed. Pytest delta is exactly +5. Pattern A/B untouched. One latent concern catalogued for M3-M5 (not a blocker).

---

## 1. B1 closure — y-axis reflects override

**Override scenarios tested (synthetic DataFrame, T1..T8, n=50 rows):**

**Scenario A — T2=surface, T7=ambient:**
```
Observed y-axis: ['Core 1 (Core)', 'Core 2 (Surface)', 'Core 3 (Internal)',
                  'Core 4 (Internal)', 'Middle 1 (Internal)', 'Middle 2 (Internal)',
                  'Near Surface (Ambient)', 'Surface']
```
T8 has role 'unknown' so its label has no suffix — correct per implementation.

**Scenario B — T5=surface, T6=ambient:**
```
Observed y-axis: ['Core 1 (Core)', 'Core 2 (Internal)', 'Core 3 (Internal)',
                  'Core 4 (Internal)', 'Middle 1 (Surface)', 'Middle 2 (Ambient)',
                  'Near Surface (Ambient)', 'Surface (Ambient)']
```

**M0 baseline (pre-fix):** `['Core 1','Core 2','Core 3','Core 4','Middle 1','Middle 2','Near Surface','Surface']` — identical for any override, role-blind.

**Verdict: PASS.** Override is now reflected. The heatmap y-axis is no longer hardcoded to firmware-default names; role suffixes appear exactly where the sensor_roles dict dictates.

---

## 2. Backwards compat (no roles)

**Call:** `plotter.plot_temperature_gradient_heatmap(data)` — no sensor_roles argument.

**Observed y-axis:**
```
['Core 1', 'Core 2', 'Core 3', 'Core 4', 'Middle 1', 'Middle 2', 'Near Surface', 'Surface']
```

**Matches M0 baseline:** YES. No role suffix appears in any label (confirmed by inspection and test).

---

## 3. Empty-input contract

**Call:** `plotter.plot_temperature_gradient_heatmap(pd.DataFrame({'TimeMinutes': [0, 1]}))`

**Observed exception:** `ValueError: No sensor columns in data; expected at least one of T1..T8.`

**Exception class:** `ValueError`

**Verdict: PASS.** Exact message matches the contract documented in test_heatmap_role_aware.py. Previously the function would silently return a broken/empty figure or raise an unhelpful KeyError.

---

## 4. End-to-end via build_sensor_role_map

**CSV used:** `ProbeData_1000F3C1_2025-05-23 09_11_59.csv` (single-curve file)

**Chain executed:**
1. `loader = ThermalProfileLoader(); loader.load_csv(csv_path)` — physics correction fires, surface corrected from T6 to T7.
2. `before_roles = build_sensor_role_map(loader, curve_idx)` — initial map: `{T1:internal, T2:core, T3:internal, T4:internal, T5:internal, T6:unknown, T7:surface, T8:ambient}`
3. **Override target chosen:** `T1` (role was 'internal'; not core, not surface — satisfies briefing requirement)
4. `loader.set_sensor_override(curve_idx, 'surface', 'T1')` applied.
5. `roles_with = build_sensor_role_map(loader, curve_idx)` — T1 role is now 'surface'. Confirmed.
6. `fig = plotter.plot_temperature_gradient_heatmap(data, sensor_roles=roles_with)` called.

**y-axis WITHOUT override:**
```
['Core 1 (Internal)', 'Core 2 (Core)', 'Core 3 (Internal)', 'Core 4 (Internal)',
 'Middle 1 (Internal)', 'Middle 2', 'Near Surface (Surface)', 'Surface (Ambient)']
```

**y-axis WITH override (T1=surface):**
```
['Core 1 (Surface)', 'Core 2 (Core)', 'Core 3 (Ambient)', 'Core 4 (Ambient)',
 'Middle 1 (Ambient)', 'Middle 2 (Ambient)', 'Near Surface (Ambient)', 'Surface (Ambient)']
```

T1 label is `'Core 1 (Surface)'` — override reflected correctly.

**tabs/temperature_profile.py call site (lines 82-86) confirmed:**
```python
heatmap_roles = build_sensor_role_map(st.session_state.loader, st.session_state.current_curve_index)
fig_heatmap = plotter.plot_temperature_gradient_heatmap(
    st.session_state.data,
    sensor_roles=heatmap_roles,
)
```
`build_sensor_role_map` is called with `loader` and `current_curve_index`. `sensor_roles=` keyword is passed.

**Verdict: PASS.**

---

## 5. Pytest delta

- **M0 baseline (before flotilla):** 338 passed, 8 failed, 1 skipped (347 collected)
- **M1 baseline (after M1):** 354 passed, 8 failed, 1 skipped
- **Observed (after M2):** `359 passed, 8 failed, 1 skipped` (295.61s run, all 8 pre-existing failures unchanged)
- **Delta M1→M2:** +5 new passing tests
- **8 pre-existing failures:** identical set to M0/M1 — no regressions, no new failures.

New tests from `tests/test_heatmap_role_aware.py`:
- `test_heatmap_y_axis_reflects_role_override`
- `test_heatmap_y_axis_default_no_roles`
- `test_heatmap_empty_input_raises_clear_error`
- `test_heatmap_partial_sensors`
- `test_heatmap_call_site_uses_helper`

**Verdict: PASS. Delta = exactly +5.**

---

## 6. Out-of-scope diff

**`git diff main..HEAD --stat` source/test files:**
```
config/constants.py                     |   6 +-   (M1: SENSOR_LIST constant)
src/ui/sensor_role_helpers.py           |  52 ++++  (M1)
src/visualization/plots.py             |  55 +++-  (M2: role-aware heatmap)
tabs/temperature_profile.py            |   7 +-   (M2: heatmap call site)
tests/test_heatmap_role_aware.py       | 257 +++++ (M2: 5 new tests)
tests/test_sensor_role_helpers.py      | 303 +++++ (M1: sensor_role_helpers tests)
```
All other changed paths are `.nelson/` mission artefacts and one flotilla plan `.md`. No unrelated source files modified.

**Verdict: PASS. Scope is clean.**

---

## 7. Pattern A/B preservation

**M2 commit diff hunks in `tabs/temperature_profile.py` (`git diff e72c164~1..e72c164 -- tabs/temperature_profile.py`):**
- Hunk 1: `@@ -3,6 +3,7 @@` — adds `from src.ui.sensor_role_helpers import build_sensor_role_map` import only.
- Hunk 2: `@@ -78,5 +79,9 @@` — replaces single heatmap call with `build_sensor_role_map` + role-aware call. Lines 79-87.

**Pattern A (lines 22-38):** Sensor-label loop for multiselect — NOT touched by M2 diff. Present and unmodified in file.

**Pattern B (lines 52-68):** Sensor-roles dict loop for line plot — NOT touched by M2 diff. Present and unmodified in file.

**Lines touched in tabs/temperature_profile.py:** line 6 (import) and lines 82-86 (heatmap call site only).

**Verdict: Pattern A/B preserved. YES.**

---

## Concerns for downstream M3-M5

### C1 — Surface-to-T1 override collapses internal_sensors to [] (expected behavior, latent confusion risk)

When `set_sensor_override(curve_idx, 'surface', 'T1')` is applied, `get_internal_sensors()` returns `[]` (and `ambient_sensors` absorbs all non-core sensors). Root cause: `get_internal_sensors` uses `range(1, surface_num)` where `surface_num = int('T1'[1]) = 1`, yielding an empty range. This is geometrically correct (no sensors are "below" T1) but produces a visually alarming heatmap where T3–T8 all show `(Ambient)`. No data loss — purely a labelling consequence. **Not a regression**, but M3-M5 UI work should document this edge case for operators.

### C2 — Index-drift (A1) still unresolved in tabs/temperature_profile.py line 54

`sensor_roles` for the line plot (lines 53-68) still uses `loader.get_sensor_assignments_with_overrides()` with **no explicit curve_index** argument (line 54), while the multiselect labels (line 20) pass `st.session_state.current_curve_index` explicitly. The latent divergence found in M0 §(a) is not closed by M2. The heatmap path now correctly passes `current_curve_index` via `build_sensor_role_map`, but the line-plot `sensor_roles` block at lines 53-68 retains the original fragility. This was out of M2's scope — catalogue for M3.

### C3 — `test_heatmap_role_aware.py` depends on real CSV fixture

`SINGLE_CURVE_CSV = REPO / 'ProbeData_1000F3C1_2025-05-23 09_11_59.csv'` is a committed binary fixture. If that file is removed or the path changes, `test_heatmap_y_axis_reflects_role_override` will fail at the fixture-load stage. Low probability but worth noting for test portability in M3-M5.
