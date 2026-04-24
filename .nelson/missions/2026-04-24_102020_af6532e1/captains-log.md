# Captain's Log — Per-Curve Widget Key Fix

**Mission ID:** 2026-04-24_102020_af6532e1
**Branch:** `refactor/curve-boundary-detection` (8 missions deep)
**Duration:** ~15 minutes wall-clock
**Mode:** agent-team, 1 captain, no red-cell (scope too narrow)

## Mission summary

- **Planned outcome:** Fix the curve-switch sensor-multiselect persistence bug in `tabs/temperature_profile.py`. Streamlit widgets with fixed `key` parameters persist state across reruns, so sensor selections made on one curve bled into other curves when the user rotated.
- **Achieved outcome:** 2 widget keys changed to f-strings embedding `st.session_state.current_curve_index`. Each curve now tracks its own selection state. User's original complaint ("the curve looks different when I return") resolved.
- **Success metric:**
  - `pytest tests/test_widget_key_per_curve.py`: **4 passed** (RED→GREEN).
  - Full suite: **139 passed / 8 failed / 1 skipped** (+4 passing vs prior baseline, no regressions).

## Delivered artifacts

| Artifact | Location | Status |
|---|---|---|
| Per-curve widget keys | `tabs/temperature_profile.py` (2 line changes) | `key=f"temp_profile_show_all_{idx}"` and `key=f"temp_profile_sensor_select_{idx}"` |
| Regression test (4 cases) | `tests/test_widget_key_per_curve.py` (NEW) | asserts f-string pattern present and old hardcoded keys removed via `inspect.getsource` |

## Open risks / follow-ups

- **Audit other tabs for similar bugs.** Tamar's recce flag: other tabs under `tabs/` were not inspected for fixed-key widgets that would leak state across curve rotations. Likely none have the specific bug (the problematic widgets were unique to the sensor-selection UI), but worth a grep pass in a future mission.
- 8-mission branch still uncommitted.

## Mentioned in Despatches

- **HMS Tamar** — single-captain TDD mission executed without deviation. Test-first discipline, exactly 2 line changes, no scope creep. The `inspect.getsource` + regex assertion pattern for testing Streamlit widget properties (without AppTest) is a reusable technique for future UI contract tests.

## Reusable patterns

### Adopt
- **`inspect.getsource` + regex-style assertions for Streamlit widget contracts.** Without AppTest, you can still pin widget-level contracts (key format, argument shape) by inspecting the source code of render functions.
- **Single-captain mission for narrow, atomic bug fixes.** When scope is truly atomic (2 line changes with a regression test), skipping the full F→T→A→META→polish chain saves time without sacrificing TDD.

### Avoid
- **Streamlit widgets with constant `key` inside a view that's re-rendered with different data.** If the data backing a view (e.g. "which sensors are available") varies per session-state selection, the widget's `key` should also vary so the persisted state is scoped correctly.

Mission complete.
