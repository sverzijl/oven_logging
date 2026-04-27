# HMS Bellerophon — Captain's Log (M3b)

**Branch**: `refactor/role-classification-unified`
**Mission dir**: `.nelson/missions/2026-04-27_113942_cfc3d87f`
**Sail date**: 2026-04-27

## Mission

Land the user-facing surface of the role-classification refactor and remove
the legacy classifier modules.

1. Extend `ThermalProfileLoader.set_sensor_override` to accept `'ambient'`
   (list-of-sensor) and `'lid'` (str-or-None).
2. Add a `_validate_override_topology` helper that enforces probe geometry
   (`core_idx < surface_idx <= min(ambient) <= max(ambient) <= lid_idx`)
   with a through-loaf exception for split ambient groups.
3. Extend the sidebar's "Override Sensor Assignments" expander with Ambient
   (multiselect) and Lid (single, optional) widgets; route validation through
   the loader.
4. Delete `src/data/surface_sensor_detector.py` and the
   `ThermodynamicSensorClassifier` class.
5. Audit existing tests for `set(...columns) ==` assertions that hard-code a
   non-`LidTemperature` column set.

## Outcome

All goals met. Net test count change: **+24 passes** (502 vs 478 in baseline
non-deleted scope), zero regressions, six pre-existing failures unchanged.

## Files modified

| File | Δ | Notes |
|---|---|---|
| `src/data/loader.py` | +148 / -8 | Added `_validate_override_topology`, `_sensor_index`, extended `set_sensor_override` to validate before mutating; `_apply_standard_columns` now honours explicit `lid=None` (clears column even when classifier reports a lid). |
| `sidebar.py` | +66 / -36 | Added Ambient (multiselect) and Lid (selectbox with "None") widgets to the override expander; on Apply, validation calls `ThermalProfileLoader._validate_override_topology` directly so error text is identical to the loader's. |
| `src/data/surface_sensor_detector.py` | DELETED (-209) | Last consumers were the legacy thermodynamic classifier and its test file. |
| `src/data/thermodynamic_sensor_classifier.py` | -252 (class removed; doc rewritten) | Kept `_detect_probe_removal_in_cool_window` and `identify_core_sensor_combined_rank` — the latter is still imported by `tests/test_curve_boundary_detection.py`. Updated module docstring to note the class deletion lineage. |
| `tests/test_surface_sensor_detection.py` | DELETED | Tested only the deleted module. |

## New tests

| File | Tests | Verdict |
|---|---|---|
| `tests/test_topology_validation_rejects_invalid_overrides.py` | 11 | All pass |
| `tests/test_sidebar_lid_override.py` | 6 | All pass |
| `tests/test_legacy_modules_removed.py` | 3 | All pass |

Combined with the pre-existing `tests/test_curve_boundary_detection.py` 33/33,
the M3b focused-tests pack runs **53 / 53 green**.

## Topology validator — how it reads

**Rule**: when all roles are present:

```
core_idx < surface_idx <= min(ambient_idx) <= max(ambient_idx) <= lid_idx
```

Partial-override calls only validate the constraints the supplied keys touch
(so the operator can apply `core` first, then `surface` etc.).

**Through-loaf exception**: when ambient sensors lie on BOTH ends of the probe
and surface is between them, the strict `surface <= min(ambient)` rule is
relaxed *iff*

  * the lower ambient group is a contiguous prefix starting at T1, and
  * the upper ambient group is contiguous on the far side, and
  * the surface index lies strictly between the two groups.

Examples:

| Scenario | core | surface | ambient | lid | result |
|---|---|---|---|---|---|
| Standard 1-side insertion | T1 | T5 | [T6,T7,T8] | T8 | accept |
| Through-loaf | T2 | T4 | [T1, T8] | – | accept |
| Lid below ambient | T1 | T5 | [T6,T7] | T5 | reject (lid < ambient) |
| Ambient straddling but lower group not anchored at T1 | T1 | T6 | [T2,T3,T7,T8] | – | reject |
| Core >= surface | T5 | T2 | – | – | reject |

Validation lives **only** in `loader._validate_override_topology` — sidebar.py
calls the same `@classmethod`, so the error messages stay identical (DRY).

## Standardised-column-set audit

`grep -rn "set\(.*\.columns" tests/` returned zero hits.
`grep -rn "columns) ==" tests/`, `grep -rn ".columns ==" tests/` likewise empty.
The test suite never asserted exact equality on a column set, so no edits
were required. Adjacent tests like
`tests/test_curve_switching_lid_column.py` already use membership checks
(`'LidTemperature' in df.columns`).

## M3a focused-test re-run

Ran the full suite: 502 passed, 6 failed, 2 skipped. The 6 failures are the
pre-existing baseline (pre-M3b run was 8 failed; the delta of -2 is the two
intentionally deleted `test_surface_sensor_detection.py` cases). No
regressions introduced. `test_curve_boundary_detection.py` still 33/33.

Pre-existing failures (NOT introduced by this mission):
- `tests/test_curve_comparison_integration.py::test_zone_color_consistency`
- `tests/test_internal_sensor_filtering.py::test_realistic_baking_profile`
- `tests/test_visualization.py` (4 cases)

## Smoke-test confirmation

```
$ python -c 'import src.data.surface_sensor_detector'
ModuleNotFoundError: No module named 'src.data.surface_sensor_detector'

$ python -c 'from src.data import thermodynamic_sensor_classifier as m;
              print(hasattr(m, "ThermodynamicSensorClassifier"),
                    hasattr(m, "identify_core_sensor_combined_rank"))'
False True
```

## Open issues / follow-ups for M4

1. **Through-loaf inference**: the validator *accepts* through-loaf overrides
   but the spatial classifier still has no first-class through-loaf detection.
   When the operator hand-sets `ambient=[T1, T8], surface=T4`, the resulting
   `AmbientTemperature` is a unweighted mean across both ends — fine for the
   present "average ambient" consumer, but the perturbation harness should
   exercise the asymmetric case where lower vs upper ambient drift apart.

2. **Sidebar smoke tests**: the M3b new-tests skip Streamlit (per standing
   orders) and pin behaviour at the loader level. A real headless-streamlit
   smoke test (e.g. via `streamlit.testing.AppTest`) would catch widget-key
   collisions. Logged for the M4 perturbation harness.

3. **Docstrings in `spatial_reconstruction`**: `__init__.py` and
   `classifier.py` still reference `surface_sensor_detector.py` by file name
   in their docstrings. Cosmetic — left as-is to preserve provenance, but
   they could be updated to past-tense ("the now-deleted classifiers").

4. **Backward-compat bare `'core'`/`'surface'` overrides as lists**: the old
   `set_sensor_override(0, 'core', sensor)` always took a string; nothing
   forced list-vs-string typing on the caller. The new validator silently
   accepts a stringy `'ambient'` for back-compat (mirrors the existing
   `get_ambient_sensors` path). M4 may want to tighten this.

## Standing orders satisfied

- TDD: failing tests written first (7 red on first run), then loader code
  greened them.
- DRY: validation lives only in `loader._validate_override_topology`; sidebar
  calls the same classmethod.
- No streamlit mocking; tests drive the loader directly.
- Token budget: well under 80 k.
