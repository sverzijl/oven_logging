# Captain's Log — HMS Penelope (M6 hot-fix)

**Mission:** Deliver real continuous-position interpolation for the core and
surface roles in both the piecewise and Stefan models, and surface the
result in the UI.

**Branch:** `refactor/role-classification-unified`
**Mission dir:** `.nelson/missions/2026-04-27_131601_97d63fea`

## Substantive win

Before this mission, every fixture returned `position_normalised` exactly
equal to `i/7` for some integer `i` (a sensor's position) and
`df['CoreTemperature']` was byte-identical to `df[nearest_sensor]`. The
classifier paid lip-service to a continuous-position contract while
shipping discrete sensor picks.

After this mission:

- **All 5 real CSVs / 7 curves** show off-sensor surface positions.
- **4 of 7 curves** show off-sensor core positions (the remaining 3 are
  curves where the slowest in-dough sensor is T1 — at the boundary of the
  probe, parabolic vertex interpolation correctly degrades to the
  discrete sensor pick).
- **`SurfaceTemperature` deviates from its nearest-sensor anchor by up to
  13.3 °C** on real fixtures (per-timestep linear blend of two adjacent
  sensors).
- **`CoreTemperature` deviates from its nearest-sensor anchor by up to
  0.75 °C** on real fixtures — small because the core sensors are all in
  the latent-heat plateau (similar values), which is exactly what the
  physics predicts.

## What changed

### `src/data/spatial_reconstruction/piecewise.py`
- New `_parabolic_vertex(x_arr, y_arr, anchor_idx)` — 3-point parabolic
  vertex interpolation with documented limitations (boundary anchor →
  exact sensor; collinear → exact sensor; offset clamped to ±1 to bound
  ill-conditioned parabolas).
- New `_crossing_position(positions, temps, target_temp)` — linear
  interpolation along the spatial axis; returns the first upward
  crossing of `target_temp` or `None` when no bracket exists.
- `fit_piecewise` now applies parabolic vertex interpolation around the
  argmax-`time_to_60c` anchor when both immediate neighbours are also
  in-dough. Boundary anchors degrade to the discrete sensor pick.
- `_interface_position` now returns a continuous crossing of the
  plateau-band temperature (`PLATEAU_NEAR_100_UPPER_C` ≈ 105 °C) instead
  of the midpoint between adjacent sensors. The fallback path
  (largest-jump-anywhere) interpolates at the half-jump temperature.

### `src/data/spatial_reconstruction/stefan.py`
- `fit_stefan` applies parabolic vertex interpolation around the slowest
  in-dough sensor (same logic as piecewise). Stefan-front positions
  already used continuous 100 °C crossings via `_find_100c_crossings`.
- Imports `_parabolic_vertex` from `piecewise.py` (single source of truth).

### `src/data/spatial_reconstruction/profile.py`
- New public helper
  `interpolate_temperature_series_at(df, positions, x_target, sensors)`
  — vectorised per-timestep linear spatial interpolation. Boundary
  clamping to first/last sensor. Returns `df[s].copy()` when `x_target`
  lands exactly on a sensor.

### `src/data/spatial_reconstruction/classifier.py`
- `_build_assignment` now calls `interpolate_temperature_series_at` to
  produce the role's `temperature_series` from the **continuous**
  `position`, not from `df[nearest]`.
- New `nearest_sensor_override` parameter on `_build_assignment` — lets
  callers (e.g. the surface picker) anchor the override-UI sensor to a
  specific sensor while still surfacing the continuous interface
  position in `position_normalised`.
- Surface assignment now sets `position_normalised = float(x_surface)`
  (the continuous `fit.x_dough_air`) and `nearest_sensor` to the
  sensor-pick result. Core assignment passes `fit.x_core` (continuous)
  directly.

### `sidebar.py`
- New "Inferred Continuous Positions (read-only)" panel inside the
  override expander, showing `core` / `surface` / `lid` continuous
  positions with a clear interpolation flag (`x=0.390 (interpolated;
  nearest sensor T4)` vs. `x=0.286 (at sensor T3)`).

### Tests
- New `tests/test_spatial_reconstruction_interpolation.py` (12 tests):
  - `_parabolic_vertex` recovers off-sensor minimum within 0.005;
    boundary and collinear anchors degrade gracefully.
  - `interpolate_temperature_series_at` returns sensor-aligned series
    for on-sensor `x_target`; linear blend between adjacent sensors;
    clamps below first / above last sensor.
  - `_crossing_position` finds first-upward crossing; returns None on
    no-bracket inputs.
  - End-to-end: classifier `temperature_series` is a TRUE per-timestep
    spatial blend (not a copy of the nearest sensor) on synthetic
    profiles with engineered off-sensor cores.
  - Real-CSV regression: at least one of the 7 fixtures (across the 5
    real CSVs) has off-sensor positions.
  - Stefan model: front position is a continuous off-sensor crossing.
- Strengthened `tests/test_spatial_reconstruction_piecewise.py` —
  `test_classify_returns_position_between_sensors` now asserts the
  surface position is STRICTLY between T3 and T4 (off-sensor by
  > 0.005), not just "nearest sensor in {T3, T4}".
- Updated `tests/test_role_classifier_assignments.py` — assertions
  switched from byte-identical-to-Tn to "tracks the nearest-sensor
  anchor closely" (the new contract).
- Updated `tests/test_loader_role_classifier_integration.py` — same.
- Updated `tests/test_per_curve_sensor_identification.py` — same.

## Key judgment calls

1. **Surface position uses the dough/air interface, not the sensor's
   position.** I changed surface assignment so
   `position_normalised = fit.x_dough_air` (continuous interface) while
   `nearest_sensor` retains the discrete sensor pick used by the override
   UI. This is the architecturally correct choice — the surface IS the
   interface; the sensor anchor is just the override target.

2. **Core uses parabolic vertex interpolation.** For the slowest in-dough
   sensor, I fit a 3-point parabola through (position, time_to_60c) on
   the immediate neighbours. Boundary anchors (no left or right
   neighbour) and collinear samples degrade to the discrete sensor. This
   matches the brief's guidance — accept the 3-point method's known
   limitations rather than introduce a new fitting routine.

3. **Stefan front already used continuous interpolation.** The existing
   `_find_100c_crossings` in stefan.py already performed linear-
   interpolation at T = 100 °C. I only had to add parabolic vertex for
   the core; the Stefan front itself was already correct.

4. **Backward-compat-test updates.** Tests that asserted
   `CoreTemperature == df['T4']` byte-for-byte are now incorrect under
   the new contract. I weakened those assertions to "tracks the nearest
   sensor closely" (max diff bound) — preserving the intent
   (standardised columns reflect the right physical sensor) without
   regressing the substantive interpolation contract.

## Test counts

- `test_spatial_reconstruction_piecewise.py`: 12 passed
- `test_spatial_reconstruction_stefan.py`: 13 passed
- `test_spatial_reconstruction_interpolation.py`: 12 passed (new)
- `test_role_classifier_unified.py`: 25 passed
- `test_role_classifier_assignments.py`: 10 passed
- `test_role_classifier_perturbation.py`: 40 passed
- `test_flotilla_finale_role_classification.py`: 22 passed
- `test_flotilla_finale_regression.py`: 29 passed
- `test_loader_role_classifier_integration.py`: 13 passed
- `test_per_curve_sensor_identification.py`: 5 passed
- ... and a wider sweep of 269 tests passes.

5 failures observed in `test_visualization.py` /
`test_curve_comparison_integration.py` are PRE-EXISTING and unrelated
(zone-color regressions). 1 failure in
`test_internal_sensor_filtering.py::test_realistic_baking_profile` is
also pre-existing.

## Open issues / follow-ups

- **`get_internal_sensors` is still position-blind.** It uses raw
  `data[Tn].max() <= 103°C` instead of the inferred continuous core /
  surface positions. CLAUDE.md already flags this as a future
  follow-up.
- **Sidebar uses `lid_position_normalised` from the loader dict.** That
  key was already populated; I only added the read-only display.
- **No animation / heatmap update.** The temperature-profile heatmap
  could be enhanced to render the inferred continuous positions as
  vertical lines; out of scope for this hot-fix.
- **Stefan core at boundary.** When the slowest in-dough sensor is at
  index 0 or N-1, Stefan still falls back to the discrete sensor (same
  as piecewise). A future improvement could fit a one-sided Stefan curve
  to extrapolate beyond the probe, but the brief was explicit:
  "Don't bloat the parabolic interpolation — accept the 3-point method's
  known limitations."

## Acceptance bar verification

- [x] All affected tests pass (focused-pack, finale, sidebar, detector).
- [x] At least one real-CSV fixture has off-sensor position (7/7 surface
      positions are off-sensor; 4/7 core positions are off-sensor —
      vastly exceeds the ≥3/6 expectation).
- [x] Sidebar shows continuous positions for the current curve.
- [x] Captain's log written.
