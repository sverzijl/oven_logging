# Captain's Log — M1a HMS Truculent

**Flotilla:** `refactor/role-classification-unified`
**Mission:** M1a — annotation tooling + ground-truth surface and lid annotations
**Branch:** `refactor/role-classification-unified` (off main)
**Mission dir:** `.nelson/missions/2026-04-27_050308_c614d9eb`
**Status:** COMPLETE — outcome achieved.

## Outcome

Annotation tooling, plot artefacts for all real CSVs in the fixture file, ground-truth `expected_surface_sensor` and (where applicable) `expected_lid_sensor` populated on the 5 real-CSV cases in `tests/fixtures/curve_boundary_cases.py`, and a parametrized presence test (`tests/test_role_classifier_unified.py`) that pins the schema and passes.

## Decisions

1. **Scope corrected from 6 to 5 real CSVs.** The brief listed 6 real CSVs but `tests/fixtures/curve_boundary_cases.py` contains only 5 real-CSV cases (`real_100098DE_1351`, `real_1000BA3C_0946`, `real_1000BA3C_1759`, `wonder_white_10k_lidded`, `post_wonder_meal_lidded`). `1000F3C1_0911` has no fixture entry — annotating it requires adding a new case, which is beyond M1a scope. Truculent correctly limited the pass to the 5 existing cases. The missing CSV is captured as a follow-up in the flotilla plan.

2. **`real_1000BA3C_1759` has 3 curves.** The brief listed it as 2-bake; the actual log spans 3 bakes (per the existing `expected_core_sensor` annotation note in the file). Truculent correctly used a per-curve list `["T6", "T6", "T6"]` for `expected_surface_sensor` since the same probe insertion holds across all three.

3. **Both lidded fixtures are `expected_lid_sensor=None`.** Neither `wonder_white_10k_lidded` nor `post_wonder_meal_lidded` shows a sensor sitting 20-60 °C below the cavity proxy `max(T1..T8)`. The lid is in the oven but not in measurable thermal contact with any of the 8 sensors in these particular bakes. Explicit `None` is required by the test contract.

4. **Surface picks under lidded suppression are weak but defensible.** On both lidded fixtures, the standard surface signature (free-rise above 100 °C) is suppressed because the lid prevents the cavity from rising above ~100 °C. Truculent picked the first sensor on the air side past core (T7 for wonder_white, T8 for post_wonder_meal) using heat-up ordering and adjacent-sensor jump. Astute concurred but flagged the picks as weaker than the unlidded cases.

## Astute red-cell verdict

**Verdict: REVISE** — flagged one cosmetic discrepancy in `annotations/manifest.json` (curve 3 of BA3C_1759 had `expected_surface_sensor: "T7"` and `expected_core_sensor: "T6"` in the JSON record, contradicting both its own reasoning text ("Surface = T6 in this curve too") and the fixture file (`["T6", "T6", "T6"]`). Astute's independent picks were T6 across all three curves of BA3C_1759 and aligned with the fixture.

**Resolution applied:** Manifest record corrected to `expected_surface_sensor: "T6"`, `expected_core_sensor: "T1"` for curve 3 — matching the fixture and reasoning. The fixture itself was always correct; only the annotation provenance JSON had the typo. Tests re-run after fix: 7/7 pass.

**Final verdict after fix:** PASS. All 7 of Astute's independent picks now align with both Truculent's fixture and the corrected manifest.

## Diffs / artefacts

- `tests/fixtures/_role_annotator.py` — NEW (annotator helper module).
- `tests/test_role_classifier_unified.py` — NEW (parametrized presence tests).
- `tests/fixtures/curve_boundary_cases.py` — surgical edits adding `expected_surface_sensor` to all 5 real-CSV entries and `expected_lid_sensor` to the 2 lidded entries. No other changes.
- `.nelson/missions/2026-04-27_050308_c614d9eb/annotations/*.png` — 7 plot artefacts (one per detected curve).
- `.nelson/missions/2026-04-27_050308_c614d9eb/annotations/manifest.json` — provenance JSON with per-curve picks and reasoning. Cosmetic typo on curve 3 of BA3C_1759 corrected after Astute red-cell.
- `.nelson/missions/2026-04-27_050308_c614d9eb/damage-reports/HMS-Astute.json` — independent verification report.

## Validation

- `pytest tests/test_role_classifier_unified.py -v` → 7/7 pass.
- `pytest tests/` → 419 passed, 8 failed, 2 skipped. The 8 failures (`test_deep_insertion`, `test_shallow_insertion`, `test_zone_color_consistency`, `test_realistic_baking_profile`, four `test_visualization.*`) match the pre-existing-failure baseline already noted as flotilla follow-up (j) in `project_refactoring_plan.md`. None of them touched by Truculent's additive-only edits.

## Open risks / follow-ups

- **`1000F3C1_0911` not annotated.** That CSV exists at the repo root but has no fixture entry. Either add a fixture case in a separate mission, or accept the 5-fixture coverage as sufficient for the flotilla.
- **Lidded surface picks (T7 wonder_white, T8 post_wonder_meal) are physically the weakest annotations.** When M2 spatial reconstruction runs, these are the most likely to surface as low-confidence picks. Should be flagged in the M4 perturbation harness output.
- **Pre-existing 8 pytest failures remain.** Tracked separately as flotilla follow-up (j); not in M1a scope.

## Mentioned in Despatches

- **HMS Truculent** — disciplined annotation pass with explicit physics reasoning per pick. Caught the 6→5 real-CSV scope mismatch and the 2→3 BA3C_1759 curve count without prompting. Picks matched Astute's independent pass on all 7 curves.
- **HMS Astute** — caught the manifest/fixture inconsistency on BA3C_1759 curve 3 that would have created confusion in later missions reading the manifest as authoritative. Independent cold-read pass executed cleanly under read-only Explore constraints.

## Reusable patterns

- **Adopt:** Annotator-as-pure-helper-module pattern. Keeps plot generation reusable across missions without coupling to test assertions.
- **Adopt:** Manifest JSON next to plot PNGs is a useful provenance pattern — but red-cell must verify manifest consistency against the fixture file (this would have been missed without Astute).
- **Avoid:** Hand-typing role assignments into a manifest after writing reasoning text. Reasoning-then-pick is reliable; pick-without-reading-back-the-reasoning produces typos like the curve-3 bug.

## Mission paid off

Both ships idle, work verified on disk, captain's log written, manifest reconciled with fixture. Mission ready to stand down.
