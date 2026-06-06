# research/ — archived, non-runtime code

This directory holds code that is **not** part of the running application and is
**not** collected by `pytest tests/`. It is kept for reference, not for import.

## `spatial_reconstruction/temporal.py` (+ its tests)

`temporal.py` was the M23 per-snapshot temporal wrapper (`classify_temporal` /
`TemporalAssignment`): it re-ran the full spatial classifier on a causal window
at every stride. It produced a "walking core" artefact because the snapshot
classifier was designed for full-bake profiles, and it was **superseded by
`src/data/spatial_reconstruction/isothermal.py`** (M24 `track_isothermal`),
which computes the core/surface positions once and tracks only the isotherm
fronts over time.

Archived here (M27) so the runtime package surface stays minimal. The package
no longer exports `classify_temporal` / `TemporalAssignment`.

- `temporal.py` — the module (frozen; relative imports point at the package and
  will not resolve from this location).
- `test_temporal_classifier.py`, `_diagnose_temporal_BA3C.py` — its tests /
  diagnostic.

**Revival trigger:** a genuine need for *time-evolving role assignment* (as
opposed to fixed-position fronts). To revive: move `temporal.py` back to
`src/data/spatial_reconstruction/`, re-add the `classify_temporal` /
`TemporalAssignment` exports to that package's `__init__.py`, and move the test
back under `tests/`.

## The deleted inverse-problem modules (M27, not archived)

The 1D inverse heat/mass models (`heat_equation`, the `luikov_*` family, the
`stefan_inverse_*` trio, `zurcher`) and their tests/drivers/baselines were
**deleted**, not archived — they were research that reached a firm NO-GO. The
finding: the eight in-dough probe sensors lack the information to reconstruct
the deep interior or the moisture field, regardless of model class, boundary
condition, or parameter count (a structural ~5–6 °C RMSE floor with
structured residual). The verdicts live in the mission commit messages
(`M7`…`M22`) and `.nelson/missions/` archives; the code is recoverable from
git history if ever needed. The descriptive replacement that *did* work is
isotherm-front tracking (`isothermal.py`).
