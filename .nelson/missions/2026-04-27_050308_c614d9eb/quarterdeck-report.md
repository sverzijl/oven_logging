# Quarterdeck Report — Checkpoint 1

**Mission:** M1a HMS Truculent (refactor/role-classification-unified flotilla)
**Phase:** UNDERWAY
**Time:** 2026-04-27 (mid-session)

## Progress

- Task 1 (HMS Truculent): **completed**
- Task 2 (HMS Astute red-cell): pending — dispatching now

## Truculent's deliverables (verified on disk)

- `tests/fixtures/_role_annotator.py` — annotator module (NEW).
- `tests/test_role_classifier_unified.py` — parametrized presence tests (NEW). All 7 tests pass.
- `tests/fixtures/curve_boundary_cases.py` — surgical edits adding `expected_surface_sensor` to all 5 real-CSV cases (BA3C_1759 as 3-curve list since the case spans 3 bakes) and `expected_lid_sensor` to the 2 lidded cases.
- `.nelson/missions/2026-04-27_050308_c614d9eb/annotations/` — 7 PNG plot artefacts + `manifest.json` with full reasoning per case.

## Per-fixture picks (from manifest)

| Fixture | Curves | core (existing) | surface (M1a) | lid (M1a) |
|---|---|---|---|---|
| `real_100098DE_1351` | 1 | T4 | T7 | n/a |
| `real_1000BA3C_0946` | 1 | T1 | T6 | n/a |
| `real_1000BA3C_1759` | 3 | T1 | [T6, T6, T6] | n/a |
| `wonder_white_10k_lidded` | 1 | T6 | T7 | None |
| `post_wonder_meal_lidded` | 1 | T5 | T8 | None |

Note: `1000F3C1_0911` has no fixture entry in `curve_boundary_cases.py` — Truculent correctly limited the pass to the 5 real-CSV cases that exist there.

## Test results

- `tests/test_role_classifier_unified.py`: **7/7 pass** in 2.57s.
- Full `tests/`: 419 passed, 8 failed, 2 skipped. The 8 failures match the pre-existing-failure baseline noted in memory `project_refactoring_plan.md` follow-up (j) — none touched by Truculent's additive-only edits.

## Hull integrity

- Truculent: Green.
- Admiral: Green.

## Decision

Continue. Dispatch HMS Astute for independent red-cell pass.
