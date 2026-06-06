# HMS Diamond — bake-data sanity check (M19 task 3)

Mission: confirm whether the 7 real-CSV fixtures used for inverse physics
fitting are 22–25 min sandwich-bread bakes as the user states, or something
else. If something else, M19 has been tuning a model for the wrong process.

## Per-fixture characterisation

| fixture | duration (min) | surface_max (°C) | core_max (°C) | core_at_end (°C) | peak_to_end (min) | core_sensor | surface_sensor |
|---|---:|---:|---:|---:|---:|---|---|
| BA3C_0946 | 23.33 | 107.35 | 96.75 | 96.75 | 0.00 | T1 | T6 |
| BA3C_1759_C0 | 23.33 | 107.35 | 96.75 | 96.75 | 0.00 | T1 | T6 |
| BA3C_1759_C1 | 24.42 | 105.25 | 98.15 | 97.80 | 0.08 | T1 | T6 |
| BA3C_1759_C2 | 24.75 | 111.35 | 97.25 | 97.10 | 0.08 | T1 | T6 |
| 100098DE_1351 | 25.25 | 112.35 | 97.85 | 93.95 | 0.17 | T4 | T7 |
| wonder_white_10k | 28.33 | 98.15 | 97.55 | 97.55 | 0.00 | T5 | T7 |
| post_wonder_meal_20251017 | 28.42 | 97.90 | 97.60 | 97.35 | 0.83 | T5 | T7 |

Notes
- Sample period 5.0 s for every fixture (CSV header `Sample Period: 5000` ms).
- `expected_start` / `expected_end` taken verbatim from
  `tests/fixtures/curve_boundary_cases.py` (M2a curve-detector ground truth);
  not re-derived in this task.
- `core_sensor` / `surface_sensor` are the per-curve picks from
  `ThermalProfileLoader`'s spatial-reconstruction classifier; readings are
  from those raw sensor columns (T1..T8) over the bake window.
- `peak_to_end_min` = (expected_end − argmax(core)) × period — i.e. the
  detector-defined cool-down window. Values ≈ 0 reflect the M1 "Stance B"
  re-annotation that clips at the probe-pull cliff (peak ≈ end), NOT a
  missing cool-down phase in the underlying physics.

## Annotated trace

`diamond-bake-trace.png` — BA3C_0946, all 8 raw sensors, vertical lines at
expected_start (idx 13) and expected_end (idx 293), horizontal references at
100 °C and 95 °C, duration annotation 23.33 min.

## Verdict

**Mixed: 4 of 7 fixtures are inside the user-stated 22–25 min band; 3 are
not, and they fall on either side.**

- Mean bake_duration = 25.40 min (σ = 1.99, range 23.33–28.42 min).
- In-band (22–25 min): BA3C_0946 (23.33), BA3C_1759_C0 (23.33),
  BA3C_1759_C1 (24.42), BA3C_1759_C2 (24.75).
- Above band (≥ 28 min, both lidded): wonder_white_10k (28.33),
  post_wonder_meal_20251017 (28.42).
- At/just above the upper edge: 100098DE_1351 (25.25 min — within rounding
  of 25 min).

Two clusters are visible in the duration distribution:

1. Unlidded BA3C / 100098DE bakes — 23.3–25.3 min, surface_max 105–112 °C
   (T6/T7 free-rises above the 100 °C plateau because the air-side sensor
   sees oven-cavity radiation). These are consistent with the user's
   22–25 min sandwich-loaf description.
2. Lidded wonder_white / post_wonder_meal bakes — 28.3–28.4 min,
   surface_max ≈ 98 °C (every sensor pinned to the saturated-vapour
   plateau under the lid; nothing free-rises). These are ~3 min longer
   than the user's stated band and represent a different oven boundary
   condition (lidded tin vs. open).

**Did the dough ever finish?** core_at_end ranges 93.95–97.80 °C, mean
96.75 °C. Six of seven fixtures crossed the 95 °C target core; only
100098DE_1351 ends at 93.95 °C — and core_max for that fixture was 97.85 °C
at idx 304, so the loaf did reach 95 °C internally; the end annotation
clips at the probe-pull cliff (idx 306) where the reading has already
started to fall. **No fixture is an aborted/incomplete bake.** The Stefan
front reached the core in every case; the inverse-fit failure is not
explained by "we were modelling pre-95 °C kinetics on a bake that never
reached 95".

**Implication for M19 inverse-fit failure**: lumping the lidded fixtures
(28.4 min, surface_max ≈ 98 °C, no air-side free-rise) with unlidded
fixtures (23.3 min, surface_max 105–112 °C, T6/T7 free-rises) into a
single boundary-condition fit is a heterogeneous-data bug. A model with a
single oven-side BC can't simultaneously match a sensor that sits at
98 °C under a lid and a sensor that climbs to 112 °C in cavity radiation.
This is M19's most likely "wrong-regime" lever — recommend separating the
two cohorts before re-fitting, and re-running comparison harness with a
lid-aware boundary condition for the wonder_white / post_wonder_meal
group.

The user-stated 22–25 min target is **largely accurate for the unlidded
BA3C / 100098DE cohort** (4 of 7 fixtures), and **about 3 min short for
the lidded cohort** (2 of 7 fixtures), consistent with lidded bakes
trapping latent heat and extending the bread-internal hold near 100 °C.
