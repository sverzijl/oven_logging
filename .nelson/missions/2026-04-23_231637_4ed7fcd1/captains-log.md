# Captain's Log — Core Sensor Classifier

**Mission ID:** 2026-04-23_231637_4ed7fcd1
**Branch:** `refactor/curve-boundary-detection` (cumulative with two prior missions; not yet merged)
**Duration:** ~100 minutes session-wall-clock
**Mode:** agent-team, 4 captains + 1 red-cell + admiral

## Mission summary

- **Planned outcome:** Add a physics-based core-sensor classifier that overrides firmware's `VirtualCoreSensor` when a combined heat-slowness + cool-slowness score indicates a different true core. Mirror the existing surface-sensor correction pattern.
- **Achieved outcome:** Combined-rank classifier shipped. Wonder white lidded bake correctly resolves core to **T5** (was T1 per firmware). All 3 unlidded real CSVs hold their firmware pick (guardrail satisfied). Classifier integrated into `_identify_sensor_roles_for_curve` via `_apply_physics_based_core_correction`. Downstream propagation fixed: `sensor_naming.get_dynamic_sensor_names` now drives off `loader.get_core_sensor()` as single source of truth (Artful caught the firmware-histogram coincidence).
- **Success metric result:**
  - `pytest tests/test_curve_boundary_detection.py`: **21 passed / 0 failed** (15 curve-boundary + 3 lidded + 3 new target-behaviour + 3 new guardrails — 3 target tests flipped red→green).
  - Full `pytest tests/`: **126 passed / 8 failed / 1 skipped**. +6 passing vs previous mission's 120/8/1 baseline (exact tally corrected from Iron Duke's initial +7 report). The 8 failures are the same pre-existing set from prior missions; no new regressions.
  - Wonder white introspection: `loader.get_core_sensor(0) == 'T5'` (or 'T6', both accepted per fixture annotation). Firmware was T1; gap 7 triggered override.

## Delivered artifacts

| Artifact | Location | Status |
|---|---|---|
| `identify_core_sensor_combined_rank` | `src/data/thermodynamic_sensor_classifier.py` (+174 lines) | **new function** — pure ranker with diagnostic dict |
| `cool_available` + `retained_c_at_cool_window=None` on fallback | same | heat-only fallback no longer silent |
| `CORE_DETECTION_CONFIG` + calibration comment | `config/constants.py` (+82 lines) | keys: `HEAT_THRESHOLD_C`, `COOL_REFERENCE_MODE`, `COOL_WINDOW_SECONDS`, `CONFIDENCE_GAP_MIN=4`, `ENABLED` |
| `_apply_physics_based_core_correction` + `core_physics_corrected` flag | `src/data/loader.py` | mirrors existing surface-correction pattern |
| `get_automatic_core_sensors` respects `core_physics_corrected` | `src/data/sensor_assignment_manager.py` (+5 lines) | fixes silent-shadow path (Iron Duke's discovery during impl) |
| `get_dynamic_sensor_names` uses `loader.get_core_sensor()` | `sensor_naming.py` (+18 lines, rewritten) | DRY + correctness fix (Artful's catch) |
| 6 new tests | `tests/test_curve_boundary_detection.py::TestCoreSensorClassifier` | 3 target + 3 guardrail |
| 6 fixture annotations + 2 new synthetic cases | `tests/fixtures/curve_boundary_cases.py` | `expected_core_sensor` field, `core_sensor_unambiguous`, `core_sensor_disagreeing_metrics` |
| Red-cell verdict | `.nelson/missions/2026-04-23_231637_4ed7fcd1/redcell-verdict.md` | ACCEPT_WITH_NOTES |
| Artful's 7 empirical probe scripts | `.nelson/missions/2026-04-23_231637_4ed7fcd1/probe_*.py` | retained for future replay |
| Damage reports | `.nelson/missions/2026-04-23_231637_4ed7fcd1/damage-reports/*.json` | 4 captains + 1 red-cell |

Cumulative `git diff main` across all three missions: 10 files changed, 508 insertions / 288 deletions. Net: three pure-module features (curve boundary detector, lidded-bake plateau candidate, core-sensor classifier) plus consolidated CoreTemperature fallback helper and dedup of hardcoded T1..T8 sensor lists.

## Key decisions

- **Decision:** Extend `thermodynamic_sensor_classifier.py` rather than create a new module.
  - **Rationale:** Somerset's reconnaissance showed the existing classifier already surfaced T6/T3/T5 as core candidates for the disagreeing-metrics case — directionally correct logic was already there. Reuse preserved DRY; new file would have fragmented the classification surface.
- **Decision:** `CONFIDENCE_GAP_MIN = 4` (not briefed 2).
  - **Rationale:** Iron Duke's Monte-Carlo (200 seeds, σ=0.5 °C gaussian noise, 4-sensor identical-physics fixture) showed noise-floor gap max = 4 (p95 = 3). Threshold 4 is one point above the 4-sensor noise floor. Red-cell (Artful) re-ran the Monte-Carlo and found the **8-sensor production path has p95=4 max=5** — the margin is thinner than Iron Duke's initial claim but still safe in practice: Artful's real-CSV perturbation at σ=1.0 °C showed 0/100 flips; at σ=2.0 °C only 5/100 on real_100098DE. Accepted non-blocking with Lancaster adding a full calibration comment.
- **Decision:** `common_peak_idx` redefined from "max(s.idxmax())" to "latest first-peaking sensor's LAST-at-max index".
  - **Rationale:** On synthetic wide-plateau fixtures (the disagreeing-metrics test), `max(idxmax)` lands INSIDE a plateau rather than at the post-oven-exit reference point, biasing retained-temp ranks. Redefinition collapses to `idxmax` on real data (single-peak unlidded) and lands correctly at plateau end on synthetic. Red-cell verified deterministic behaviour.
- **Decision:** Heat-only fallback when cool window extends past EOF (wonder white's case: log ends at peak).
  - **Rationale:** Briefing's physics argument explicitly named heat rank as the more reliable signal during an active bake. For logs that truncate at peak, no cool data is available; heat-only is the defensible degradation. Lancaster surfaced `cool_available=False` in the diagnostic dict so callers can tell whether the classification used combined or heat-only.
- **Decision:** `sensor_naming.get_dynamic_sensor_names` rewritten to drive off `loader.get_core_sensor()` rather than patched to check `core_physics_corrected`.
  - **Rationale:** Artful flagged that the existing function keyed off the firmware histogram and happened to be correct on wonder white only because T5 appeared 40 times. DRY says single source of truth — `loader.get_core_sensor()` already consolidates firmware + physics correction + manual override. Lancaster correctly chose the rewrite over the patch.

## Validation evidence

**Admiral-run final checks:**
```
pytest tests/test_curve_boundary_detection.py -v
21 passed in 12.78s

pytest tests/ -q
126 passed, 8 failed, 1 skipped in 82.17s
```

**Red-cell empirical probes (from `redcell-verdict.md`):**
- Monte-Carlo 200 seeds, 8-sensor production path, σ=0.5 °C: p95 gap = 4, max = 5 (thinner than Iron Duke's 4-sensor claim; safe in practice).
- 8-sensor fixture with exact gap=4: override fires (threshold boundary correctly-inclusive).
- Gap=3 fixture: override does NOT fire (correct).
- σ=1.0 °C real-CSV perturbation, 100 seeds per CSV: 0/300 flips across all 3 originals.
- σ=2.0 °C real-CSV perturbation: 5/100 flips on real_100098DE; acceptable given σ=2.0 is 4x the calibrated noise floor.
- 7 probe scripts retained for replay.

**Iron Duke's guardrail diagnostics (all 3 real CSVs below gap threshold — firmware stays):**
- `real_100098DE_1351`: firmware T4 score 7, winner T4 score 7, gap 0.
- `real_1000BA3C_0946`: firmware T1 score 2, winner T1 score 2, gap 0.
- `real_1000BA3C_1759`: firmware T1 score 9, winner T2 score 8, gap 1.

## Open risks

- **Risk:** `CONFIDENCE_GAP_MIN = 4` is one rank above the 8-sensor noise floor (p95=4 max=5). A real CSV at σ=2.0 °C showed 5/100 spurious flips; at σ=1.0 °C, zero. Production instrument noise is probably under σ=1.0 for Combustion Inc. probes, but this hasn't been characterised.
  - **Owner:** follow-up mission.
  - **Mitigation:** Config comment (Lancaster) names the calibration honestly. Acquire noise characterisation from a static-temperature dataset (probe in a stable bath) and tighten the threshold if warranted.

- **Risk:** `_apply_physics_based_core_correction` calibrated against 1 real lidded CSV (wonder white) + 3 unlidded real CSVs + 2 synthetics. Same calibration-to-a-small-sample concern as prior missions.
  - **Owner:** follow-up mission.
  - **Mitigation:** Acquire ≥ 2 more real lidded-bake CSVs AND ≥ 2 more real unlidded CSVs. Re-run the combined-rank classifier and confirm the override fires correctly on lidded, never on unlidded.

- **Risk:** `test_deep_insertion` status ambiguous across missions. This mission's 3 full-suite runs showed 2× fail and 1× pass. Iron Duke initially claimed it "passed this run" and Lancaster's one run saw it pass; Artful reported it failed all 3 of its runs. Genuinely flaky OR order-dependent at the boundary of the suite's state.
  - **Owner:** separate test-hygiene mission.
  - **Mitigation:** Not in this mission's scope. Flagged across all three missions' captain's logs now.

- **Risk:** The firmware-histogram path in `sensor_naming` was correct-by-coincidence on wonder white before Artful found it. Other downstream consumers of `curve_sensor_assignments[curve_index]['core']` may have similar coincidence paths that grep didn't surface cleanly.
  - **Owner:** follow-up audit (lighter than a mission).
  - **Mitigation:** Artful grepped `sensor_assignments[` and `['core']` across `src/` and reported only `sensor_naming` and `sensor_assignment_manager` as consumers — both now fixed. Low residual risk but worth re-checking if other UI or plotting modules start behaving oddly on lidded CSVs.

- **Risk:** Heat-only fallback fires on `real_1000BA3C_0946` too (not just wonder white), and fires silently in production code paths that ignore the new `cool_available` flag. Harmless today because the same heat-rank winner coincides with firmware's pick, but opaque.
  - **Owner:** documentation; no action until a consumer depends on the flag.

## Follow-ups

| Item | Owner | Priority |
|---|---|---|
| Commit + review `refactor/curve-boundary-detection` branch (three missions' worth of diff now ready) | user | next session |
| Characterise real instrument noise σ from a static-temperature dataset → re-calibrate `CONFIDENCE_GAP_MIN` | future fleet | before production deployment |
| Acquire ≥ 2 more real lidded-bake CSVs and ≥ 2 more real unlidded CSVs | user (data collection) | ongoing |
| Cross-validate core classifier against the acquired CSVs | future fleet | after data arrives |
| Resolve `test_deep_insertion` flake | separate mission | lower priority |
| Prior missions' open follow-ups (7 items catalogued in `memory/project_refactoring_plan.md`) | future fleets | as previously catalogued |

## Mentioned in Despatches

- **HMS Richmond** — anticipated the T5/T6 tie on wonder white during fixture construction and made the test accept either, preventing a spurious single-sensor calibration. Also correctly refused to guess ground-truth for the 3 unlidded real CSVs, instead recording firmware's pick as the expectation — clean separation between "firmware is correct here" and "physics must override here".

- **HMS Somerset** — the recon find was the mission-making contribution. By discovering that `_validate_sensor_assignments` already flagged suspect firmware picks AND that the existing thermodynamic classifier was already surfacing T6/T3/T5 as candidates, Somerset gave Iron Duke a clear "reuse this, don't write from scratch" path. Saved at least an hour of archaeology.

- **HMS Iron Duke** — self-discovered the `sensor_assignment_manager.py` silent-shadow path during implementation and fixed it without being asked. Self-reported 4 deviations (3 briefed + the 4th-file addition) with full rationale, giving red-cell a structured review surface. Minor math error on the +7 vs +6 tally caught by Artful; not mission-critical.

- **HMS Artful** — raised the empirical bar again. Reproduced Iron Duke's Monte-Carlo and found the 8-sensor path has a thinner margin (p95=4 max=5) than the 4-sensor path Iron Duke reported (max=4). Caught two reporting errors (tally +7 vs actual +6; `test_deep_insertion` failed all 3 runs, not "flaky passed"). Found the `sensor_naming` correct-by-coincidence — a finding that would have silently bitten a future lidded CSV where the true core happened to NOT appear in the firmware histogram. Seven probe scripts preserved for replay.

- **HMS Lancaster** — bounded-scope discipline maintained across three missions now. Chose the sensor_naming *rewrite* over the *patch* — DRY plus correctness — on a call that could easily have gone either way. Correctly refused to action item D (tally correction) as code when it belonged in the captain's log.

## Reusable patterns

### Adopt
- **Red-cell reproduces prior captain's experiments rather than trusting self-reports.** This mission's red-cell caught two numerical errors (Monte-Carlo margin, full-suite tally) by re-running Iron Duke's probes. Previous missions' red-cells caught similar issues. The pattern is now proven over 3 consecutive missions.
- **Downstream propagation trace as a red-cell item.** Artful traced from `loader.get_core_sensor` through `sidebar.py` to catch the `sensor_naming` correct-by-coincidence. This kind of "does the fix actually reach the user-facing display?" check is cheap and catches integration gaps that unit tests miss.
- **Rewrite over patch for DRY fixes.** Lancaster's sensor_naming rewrite (single source of truth via `loader.get_core_sensor()`) is cleaner than checking the `core_physics_corrected` flag in N places. When a patch would add a second code path to a module, prefer collapsing both paths to a single authoritative call.
- **Accept ties in fixture annotations.** Richmond's `expected_core_sensor='T6' or 'T5'` (tied at combined score 5) avoided over-constraining the classifier. Future fixtures should follow this pattern when physics is genuinely ambiguous within tolerance.

### Avoid
- **Reporting metric deltas from memory without re-counting.** Iron Duke's "+7 passing" was actually +6; he mentally added the wrong test count. Red-cell caught it but it could have slipped into a release note. For any net-delta claim, re-compute from the raw suite output.
- **Claiming a test is "flaky" without running N times.** Iron Duke said `test_deep_insertion` "passed this run" after one observation; Artful's 3 runs showed it failed all 3. A single observation is never sufficient for a flaky-test claim — run ≥ 3 times before reporting flakiness.
- **Calibration comments that hide thinning margins.** Iron Duke's initial comment on `CONFIDENCE_GAP_MIN=4` said the 4-sensor Monte-Carlo capped at 3; production path is 8-sensor with max=5. Lancaster's updated comment calls this out explicitly. Future calibration comments should state the exact test conditions, including N (number of sensors) and σ (noise assumption).

## Standing order ledger

No blocking violations. One minor observation: battle-plan amendment required after Iron Duke unexpectedly needed to modify a 4th file (`sensor_assignment_manager.py`) beyond the 3 listed in his formation brief. Because the mission was sequential (Iron Duke had already stood down by the time the discovery was relevant to subsequent work), no split-keel concurrency risk. Logged as implicit scope within the "integrate the classifier" deliverable rather than a formal `battle_plan_amended` event. For future missions, if a captain anticipates needing to touch files outside their ownership, they should SendMessage the admiral pre-commit rather than discover-and-fix.

Mission complete.
