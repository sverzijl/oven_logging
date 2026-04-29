# HMS Foxhound — Captain's log (M24, isothermal-tracking)

Mission dir: `.nelson/missions/2026-04-29_092737_9b83d7ba`.
Branch: `refactor/role-classification-unified`.

## Mission

Replace the M23 per-snapshot-classify-then-smooth approach (which produced a
walking-core artefact and Stefan-front-vs-surface ordering inversion on
BA3C_0946) with **isothermal tracking**: at each timestep, find where the
spatial temperature field crosses target values (60, 80, 100, 110 C), and
trace those positions over time. The core/surface position is computed
**once** from the full bake.

## Files created

- `src/data/spatial_reconstruction/isothermal.py` — `IsothermalAssignment`
  dataclass + `track_isothermal()` + `_find_isotherm_position()`.
- `tests/test_isothermal_tracker.py` — 9 tests (3 unit on
  `_find_isotherm_position`, 2 synthetic on the tracker, 4 empirical on
  BA3C_0946).
- `tests/_diagnose_isothermal_BA3C.py` — standalone diagnostic that
  generates `isothermal-traces-BA3C_0946.png` + `isothermal-data-BA3C_0946.json`.

## Algorithm

`track_isothermal(df, ...)`:

1. Run `classify(df, ...)` once on the full bake → fixed core_x, surface_x
   (clamped to [0, 1]; original confidence label preserved on the
   `SpatialAssignment`).
2. Build a stride grid every `stride_seconds` (default 30 s) up to
   `(n_rows-1)*period_s`.
3. For each stride centre, look up the corresponding df row.
4. For each target T, walk the eight sensors from surface (high x) to core
   (low x), find the first adjacent pair bracketing T, and linear-interp
   between them. Boundary cases:
   - max(temps) < target → NaN (front not in probe yet).
   - min(temps) > target → 0.0 (front past T1, advanced past probe tip).
5. Apply Savitzky-Golay smoothing per-isotherm on contiguous finite runs;
   clamp smoothed values to [0, 1] to suppress polynomial-fit edge ringing
   when the raw signal saturates at the probe tip.
6. Compute `T_at_fixed_core_t` and `T_at_fixed_surface_t` by per-stride
   spatial interpolation of the eight sensors at the fixed positions
   (reuses `interpolate_temperature_series_at` — DRY with the per-curve
   path).

DRY: reuses `classify()` for the one-time core/surface determination only;
isotherm tracking itself does NOT call `classify()` per stride.

## Test results

`pytest tests/test_isothermal_tracker.py -v` → **9 passed in 3.54 s**:
- TestFindIsothermPositionUnit: 3 cases (below all → NaN, above all → 0,
  middle → linear interp).
- TestIsothermalSynthetic: 2 cases (static profile → constant position;
  advancing front → q1>q4 inward drift).
- TestIsothermalBA3C0946: 4 cases (smoke, ordering 60>80>100>110 by
  position-deepest-to-surface inverted as x_60 < x_80 < x_100 < x_110,
  100 C front monotone-inward, fixed core/surface scalars).

Sibling regression: `pytest tests/test_temporal_classifier.py
tests/test_role_classifier_unified.py -q` → **30 passed**, M1-M23 untouched.

## BA3C_0946 result (from diagnostic)

```
bake duration       : 23.00 min
fixed core_x        : 0.0000  (clamped from extrapolated -0.041; conf=low)
fixed surface_x     : 0.6787  (conf=high)
T_at_fixed_core final : 96.50 C   (target ~95 — within 1.5 C)

isotherm | first   | last     | position range
---------+---------+----------+---------------------
  60.0 C |  0.50   | 23.00 m  | x=0.000 .. 0.868
  80.0 C |  0.50   | 23.00 m  | x=0.000 .. 0.971
 100.0 C |  2.50   | 23.00 m  | x=0.592 .. 0.988
 110.0 C |  3.00   | 23.00 m  | x=0.730 .. 0.984

100 C front: head=0.898  tail=0.614  monotone-inward=True
```

All four physical sanity criteria from sailing orders satisfied:
1. 100 C front advances monotone-inward (0.898 → 0.614).
2. Isotherm ordering holds (110 stays nearest surface; 60 reaches deepest).
3. Core position is a **single scalar** (no walking).
4. T_at_fixed_core climbs smoothly to ~95 C plateau.

## Verdict

The walking-core artefact and the Stefan-front-vs-surface inversion in M23
are both eliminated by:
- Computing core position **once** from the full bake (no per-stride
  classifier reentry).
- Tracking the 100 C front by direct **isothermal interpolation** of T(x)
  rather than re-deriving it from snapshot heuristics.

The diagnostic PNG (`isothermal-traces-BA3C_0946.png`) shows clean
front-progression curves: 60 C reaches T1 at ~17 min; 80 C arrives at ~22 min;
100 C still ~0.6 at end of bake (centre is below boiling, consistent with
final core T = 96.5 C). 110 C front moves only modestly — only the outer
~30% of the dough ever exceeds 110 C, as expected.

## Recommendation for M24 production wiring

1. Surface this in `app.py` as a new "Moisture-front timeline" plot in the
   profile-analysis tabs. The four bread-chemistry isotherms (60 C
   yeast-kill, 80 C starch-gelatinisation, 100 C boiling/Stefan, 110 C
   crust onset) are physically interpretable and map cleanly onto the
   bread-chemistry zones already in `config.constants.S_CURVE_ZONES`.
2. Keep `classify_temporal` (M23) for diagnostic comparison only — do
   not delete; flag it deprecated for production use.
3. The fixed-core confidence-`low` label on BA3C_0946 should propagate to
   the UI (already in the PositionalAssignment; just needs sidebar
   wiring).
