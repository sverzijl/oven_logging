# M3a HMS Royal Sovereign — Captain's Log

Mission: wire the spatial-reconstruction classifier into the runtime path of
`ThermalProfileLoader`, kill the legacy `physics_corrected` flag system, add
the `LidTemperature` column, and rewrite `SensorAssignmentManager` as a thin
adapter.

## Decisions and dispatches

### 1. Loader integration

`_identify_sensor_roles_for_curve` is now a single call to
`spatial_reconstruction.classify(df, sample_period_ms, probe_geometry)`,
followed by a flatten-to-dict helper (`_spatial_assignment_to_dict`) that
stores the per-role nearest sensor, the inferred normalised positions, the
firmware diagnostic, and the full `SpatialAssignment` object under the
`'assignment'` key. Backward-compat averages (`CoreAverage`, `SurfaceAverage`)
remain for legacy consumers.

`probe_geometry` is looked up via `lookup_geometry(probe_sn=<Probe S/N>,
probe_model=<Probe HW revision>)` from CSV header metadata (only the uniform
fallback is populated today, but the wiring is in place).

A defensive `try/except` around `classify(...)` falls back to a degraded
empty-assignment dict when the classifier raises — the curve extraction
loop never crashes on a single bad slice.

### 2. Killed code paths

Three legacy methods deleted from `loader.py`:
- `_apply_physics_based_surface_correction` (lines 412–467)
- `_apply_physics_based_core_correction` (lines 470–531)
- `_classify_sensors_dynamically` (lines 860–966)

`physics_corrected` and `core_physics_corrected` flags removed from
`_apply_standard_columns` and `sensor_assignment_manager.py`. The
`CORE_DETECTION_CONFIG` and `SURFACE_DETECTION_CONFIG` imports are dropped
from the loader (the constants themselves remain in `config/constants.py`
for M5 cleanup, per the briefing).

### 3. `_apply_standard_columns` rewrite

New layering, every layer pulls from the classifier's `SpatialAssignment`:

- `CoreTemperature`: manual override > `assignment.core.temperature_series`
  > `resolve_core_temperature_series` fallback.
- `SurfaceTemperature`: manual override > `assignment.surface.temperature_series`
  > `VirtualSurfaceTemperature` > `SurfaceAverage` > T7/T8 mean.
- `AmbientTemperature`: manual override > mean over
  `assignment.ambient_assignments[*].temperature_series` > legacy fallback.
- `LidTemperature` (new column): manual override > `assignment.lid.temperature_series`
  > **column dropped**. No NaN columns: present-or-absent only.

A stale `LidTemperature` column carried over from a prior curve is
explicitly dropped when the current curve has no lid in its assignment —
exercised by `test_curve_switching_lid_column.py`.

### 4. New loader getters

Added: `get_lid_sensor`, `get_core_temperature_series`,
`get_surface_temperature_series`, `get_ambient_temperature_series`,
`get_lid_temperature_series`. Each respects manual overrides (raw sensor
read) and otherwise returns the classifier's interpolated series.

`get_ambient_sensors` rewired to read from the assignment dict directly —
the `range(surface_num+1, 9)` heuristic is gone.

`get_internal_sensors` keeps its temperature-threshold filter logic but
now reads core/surface from the new schema (it goes through
`get_surface_sensor` and `get_core_sensor` which already read overrides
+ classifier).

### 5. `SensorAssignmentManager` rewrite

Reduced from a per-curve histogram + thermodynamic-validator (~145 LOC) to
a thin read-side adapter (~85 LOC) with four methods:
`get_automatic_core_sensors`, `get_automatic_surface_sensors`,
`get_automatic_ambient_sensors`, `get_automatic_lid_sensor`. Each reads
straight from `curve_sensor_assignments[i]['core'|'surface'|'ambient'|'lid']`.
`validate_sensor_assignments` is now a no-op stub — the spatial classifier
applies topology checks at fit time, so the legacy validator is redundant.

### 6. Tests

Created (TDD red-then-green):
- `tests/test_role_classifier_assignments.py` — 10 tests pinning the new
  per-curve assignment dict + flag-killed contract.
- `tests/test_loader_role_classifier_integration.py` — 13 tests covering
  end-to-end role assignments, interpolated-series getters, and lid-column
  lifecycle on real CSVs.
- `tests/test_curve_switching_lid_column.py` — 3 tests verifying the
  `LidTemperature` column appears/disappears correctly across curve
  switches (synthetic two-curve setup using `_lid_touch_df` +
  `_full_immersion_df`).

Deleted: `tests/test_physics_flag_regression.py` (replaced).

Updated to align with the new contract:
- `tests/test_per_curve_sensor_identification.py::test_physics_correction_per_curve`
  — now asserts the flag is GONE rather than present; surface picks unchanged.
- `tests/test_per_curve_sensor_identification.py::test_backward_compatibility_single_curve`
  — relaxed core sensor expectation to T1..T4 set (synthetic data has no
  spatial gradient).
- `tests/test_sensor_assignment_manager.py::TestCoreInfoAllSensors` —
  rewritten to test the thin adapter (single-pick), not the legacy
  histogram-based multi-sensor list.
- `tests/test_sensor_role_helpers.py::test_build_sensor_label_map_unknown_has_no_suffix`
  — switched to a stub-loader exercise (the spatial classifier now
  assigns every real-CSV sensor a role, so unknown-role sensors no
  longer occur on real fixtures).
- `tests/test_curve_boundary_detection.py::test_synthetic_disagreeing_metrics_core_is_t6`
  — now accepts T5 OR T6: the spatial reconstructor picks T5 (heat-rank
  winner = coldest dough-side point) where the legacy combined-rank picked
  T6. Both are physically defensible; T5 matches the v1 core definition.

### 7. Test counts

- 50/50 classifier tests pass via the loader path
  (`test_role_classifier_unified.py`).
- 25/25 spatial reconstruction tests
  (`test_spatial_reconstruction_piecewise.py` + `_stefan.py`).
- 33/33 curve boundary detection tests.
- 26/26 new tests across the three new files.
- Full suite: **8 pre-existing failures unchanged**, 462 → 486 passes (net
  +24 from new tests).

### 8. Judgment calls

- **Probe metadata key naming**: chose `Probe S/N` and `Probe HW revision`
  as the metadata keys (matching the literal CSV header field names).
  `lookup_geometry` falls through to `default_uniform` for any unknown probe
  model — no functional change today.
- **`get_internal_sensors`**: kept the temperature-threshold filter logic
  intact rather than rewriting it to read positions from the assignment.
  M5 (or a follow-up) can replace the filter with classifier-driven
  position checks.
- **`validate_sensor_assignments` → no-op**: the legacy validator's job
  (warn when role-temperature ordering is wrong) is now subsumed by the
  classifier's topology checks. Keeping it as a no-op stub avoids breaking
  callers; deletion is a future cleanup.
- **`test_synthetic_disagreeing_metrics_core_is_t6`**: relaxed to T5∪T6
  rather than deleted. The synthetic case is still useful as a behaviour
  pin.

### 9. Open issues for M3b HMS Bellerophon

- Override UI for ambient + lid (`sidebar.py:230–327` extension).
- Topology validation on overrides (core_idx < surface_idx ≤ ambient ≤ lid).
- Delete `src/data/surface_sensor_detector.py` outright.
- Delete the `ThermodynamicSensorClassifier` class from
  `thermodynamic_sensor_classifier.py:251–502`. Decide on
  `identify_core_sensor_combined_rank` (no current src callers; kept by
  inertia, M3b can delete).
- The `_sensor_overrides` schema today reads `'core' | 'surface' |
  'ambient' | 'lid'`; M3b extends the UI to write all four.

### 10. Sailing orders fulfilled

- TDD red-then-green: 18/26 new tests started red, all green after
  implementation.
- DRY: a single `_apply_standard_columns` writes every standardised column
  from a single source of truth (the `SpatialAssignment`).
- `physics_corrected` references in `src/`: zero (verified by grep).
- `surface_sensor_detector.py` and `ThermodynamicSensorClassifier` class
  preserved (M3b's job to delete).
