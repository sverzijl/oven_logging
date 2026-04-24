# Captain's Log — Three-Bake 1759 Correction

**Mission ID:** 2026-04-24_090858_d46e235e
**Branch:** `refactor/curve-boundary-detection` (7 missions deep; not yet merged)
**Duration:** ~50 minutes session-wall-clock
**Mode:** agent-team, 4 captains + 1 red-cell + admiral

## Mission summary

- **Planned outcome:** Correct the `real_1000BA3C_1759` fixture from 2 bakes (as annotated since the first mission) to 3 bakes as actually present in the CSV, and remove the prior mission's `peak_idx+1` scan-start guard that had been papering over the misannotation.
- **Achieved outcome:** Fixture re-annotated to 3 bakes. Guard removed. New `_skip_probe_pull_tail` method added to prevent the next curve's start-detection from latching onto the cooldown tail immediately after a cliff exit. Detector now returns 3 clean curves for 1759: [13→293, 775→944, 6032→6185]. All other CSVs unchanged.
- **Success metric result:**
  - `pytest tests/test_curve_boundary_detection.py`: **30 passed / 0 failed** (1 previously-RED test flipped green; no regressions).
  - Full `pytest tests/`: **136 passed / 7 failed / 1 skipped** (same pre-existing failures; `test_deep_insertion` flake noise accounts for 135/136 variation).
  - 1759 introspection: 3 curves, correctly gapped, all `truncated=False`.

## Delivered artifacts

| Artifact | Location | Status |
|---|---|---|
| Fixture re-annotation: 1759 from 2 bakes to 3 bakes | `tests/fixtures/curve_boundary_cases.py` | `expected_n_curves` 2→3; `expected_starts` [13,5890]→[13,775,6032]; `expected_ends` [944,6185]→[293,944,6185] |
| `peak_idx+1` scan-start guard removed | `src/data/curve_boundary_detector.py::_candidate_probe_pull_cliff` | Dragon's prior-mission guard deleted |
| New `_skip_probe_pull_tail` method + `cliff_fired` flag threaded through pipeline | `src/data/curve_boundary_detector.py` | mirrors `_skip_plateau_tail` pattern; advances `search_from` past cooldown after a cliff exit |
| Two-layer-defense docstring note | `src/data/curve_boundary_detector.py::_candidate_probe_pull_cliff` | `CLIFF_MIN_START_TEMP_C=80` (Layer 1, unit) + `_skip_probe_pull_tail` (Layer 2, loop) each guard distinct failure modes |
| Noise-fragility docstring reworded from WARNING to NOTE | same | prior framing was partially annotation-driven; true fragility at production σ uncharacterised |
| Test-order fix in `test_ground_truth_real_csvs_tight` | `tests/test_curve_boundary_detection.py` | Portland reordered checks so ambiguous-1759 branch runs before tolerance-skip (previously a silent-green bug) |
| Red-cell verdict + probe scripts | `.nelson/missions/2026-04-24_090858_d46e235e/` | ACCEPT_WITH_NOTES |
| Damage reports | `.nelson/missions/2026-04-24_090858_d46e235e/damage-reports/*.json` | 4 captains + 1 red-cell |

## Key decisions

- **Decision:** Admiral's initial fixture estimates (bake-2 start 766, bake-3 start 6022) rejected in favour of detector-convention values (775 and 6032).
  - **Rationale:** Duncan discovered the 9-sample discrepancy for bake-2 during implementation — admiral had used "first sample where VCT rose above ROOM_TEMP_MAX=35" as the heuristic; detector uses `bake_active_c=40` as its convention across all CSVs. Artful's Q3 found the same 10-sample pattern on bake-3. Fixing the fixture to match the detector's principled convention is cleaner than retuning `bake_active_c` for one CSV.
  - **Standing order precedent set:** "When captain ground-truth estimates conflict with established detector convention, the fixture follows the detector unless there's a physical reason to recalibrate the detector."

- **Decision:** Both layers of probe-pull defence kept — `CLIFF_MIN_START_TEMP_C=80` AND `_skip_probe_pull_tail`.
  - **Rationale:** Artful's Q4 empirically confirmed each layer guards a distinct failure mode. Without Layer 1 the cliff candidate re-fires inside the post-cliff cooldown cascade (VCT 76 → 60 → 44... each single-sample drop exceeds 15 °C). Without Layer 2 the next curve's cold-start latches onto the cooldown tail. Defence-in-depth; low cost; kept both.

- **Decision:** Portland's test-order bug fix kept in-scope despite being a pre-existing issue.
  - **Rationale:** Portland discovered that `test_ground_truth_real_csvs_tight` was silently skipping 1759's bake-1 check because the tolerance-skip branch ran before the ambiguous-1759 branch. Fixing the order is necessary for the mission's TDD gate to be meaningful (otherwise the RED target test would never flip). Within file ownership, didn't expand scope.

- **Decision:** Mission explicitly reframed the prior mission's `peak_idx+1` guard rationale as "paper over a mis-annotated fixture."
  - **Rationale:** Prior Dragon (probe-pull-cliff mission) + Ambush's Q1 reframing ("first probe-pull of a multi-pull session") were both empirically correct descriptions of the j=293 event BUT the strategic conclusion (merge two bakes into one curve) was wrong. A multi-pull session with real cool-offs between bakes should produce multiple curves, not be suppressed into one. Documenting the reframe explicitly to prevent future captains from re-introducing a similar guard.

## Validation evidence

**Admiral-run final checks:**
```
pytest tests/test_curve_boundary_detection.py -v
30 passed in 12.27s

pytest tests/ -q
135 passed, 8 failed, 1 skipped (or 136/7/1 depending on test_deep_insertion flake)

1759 introspection: 3 curves
  curve 0: 13->293 (281 samples)
  curve 1: 775->944 (170 samples)
  curve 2: 6032->6185 (154 samples)
```

**Red-cell (Artful) empirical probes:**
- Q1 (skip side effects on single-curve CSVs): 100098DE / BA3C_0946 / PWM unaffected; wonder white doesn't trigger (fires plateau, not cliff). Clean.
- Q2 (over-skip): skip stops at idx 307 (VCT=30.40), cold-start scans from 307, correctly lands at 775 (VCT=40.00). 468-sample gap is real probe idle, not detector dead zone.
- Q3 (bake 3 annotation inconsistency): detector self-consistent at `bake_active_c=40`; fixture annotation 6022 was the 35 °C estimate, should be 6032 for consistency. Spey fixed.
- Q4 (CLIFF_MIN_START_TEMP_C necessity): unit-level probe confirmed — without the 80 °C gate, cliff fires at idx 294 inside the cooldown cascade. Keep it.
- Noise perturbation: σ=0.10/0.15/0.20/0.30 °C — 0/30 wrong curves across all fixtures. The prior mission's fragility concerns were partially annotation-driven.
- Two-cliff synthetic test: detector correctly produces 2 curves.

## Open risks

- **Risk:** Prior mission's cliff-noise-fragility claim was partially annotation-driven (when 1759 was 2-bake, a cliff firing at j=293 looked "spurious" because it split the merged curve). Now that ground truth is 3 bakes, the σ=0.05-0.15 °C fragility concern is softer but still uncharacterised against real Combustion probe noise.
  - **Owner:** follow-up mission.
  - **Mitigation:** Docstring on `_candidate_probe_pull_cliff` reworded from WARNING to NOTE. Four suggested mitigations retained. Real fix: static-temperature noise characterisation from a controlled dataset.

- **Risk:** `bake_active_c=40` threshold is now structurally embedded as "the" start convention. Any fixture whose annotated start point doesn't match this threshold (like admiral's initial 766/6022 estimates) will silently drift by ~10 samples unless caught. Future fixture annotators should either use the detector's convention OR flag the case as `ambiguous=True` with a wider tolerance.
  - **Owner:** documentation (covered in this mission's captain's log entry under "Key decisions" → standing order precedent).

- **Risk:** The `expected_core_sensor='T1'` annotation on 1759 was set when 1759 was a 2-bake fixture. Now that it's 3 bakes, T1 may not be the correct core for all 3 bakes. The core classifier runs per-curve, so each curve gets its own classification; but the fixture's single `expected_core_sensor` is now ambiguous.
  - **Owner:** follow-up mission.
  - **Mitigation:** No test currently iterates `expected_core_sensor` against per-curve classifications for 1759 (ambiguous branch suppresses), so no blocking issue. Future fixture schema could support `expected_core_sensor_per_curve: [...]`.

- **Risk:** `test_deep_insertion` flake continues through 7 missions. Unrelated but accumulating.
  - **Owner:** dedicated test-hygiene mission.

- **Risk:** Branch 7 missions deep, ~2500+ cumulative lines of change on top of `main`. Merge complexity growing nonlinearly.
  - **Owner:** user.

## Follow-ups

| Item | Owner | Priority |
|---|---|---|
| **Commit + review/merge** `refactor/curve-boundary-detection` branch (7 missions) | user | strongly recommended — getting long |
| Characterize real Combustion probe noise σ from static-temperature dataset → re-run cliff noise probes | future fleet | |
| Extend fixture schema to `expected_core_sensor_per_curve: list` for multi-bake CSVs | future fleet | |
| Resolve `test_deep_insertion` flake | separate mission | |
| All prior missions' open follow-ups — see `memory/project_refactoring_plan.md` | future fleets | |

## Mentioned in Despatches

- **HMS Lancaster** — executed the 1759 re-annotation cleanly with the bug-context in the description. Every future captain reading this fixture will understand the history of the 2→3 correction.

- **HMS Portland** — caught the hidden test-order bug (tolerance-skip running before ambiguous-1759 branch silently skipped the bake-1 check). Without Portland's diligence the mission's TDD gate would have been meaningless — the RED target would never have flipped. Scope-appropriate fix without over-reach.

- **HMS Duncan** — the scope expansion to detect the `bake_active_c=40 vs 35` discrepancy mid-implementation, flag it via SendMessage before unilaterally changing anything, and then execute the admiral-authorized fix cleanly is the right captain pattern. Also the `_skip_probe_pull_tail` mirror of `_skip_plateau_tail` shows good structural consistency — cliff exits now get the same post-exit housekeeping plateau exits do.

- **HMS Artful** — Q3 catching the same 10-sample shift on bake-3 that bake-2 had (hidden under `ambiguous=True`) and recommending the fixture alignment is the kind of finding that prevents hidden inconsistencies from calcifying. Q4's empirical confirmation that both defence layers are separately necessary provides a clear rationale for retaining both rather than paring down. Noise-regression re-analysis (the prior mission's fragility framing was partially annotation-driven) is a genuinely difficult conceptual reframing to make.

- **HMS Spey** — disciplined polish across items A (fixture alignment), B (two-layer-defence doc), C (noise-fragility reword). Items B and C are pure documentation — important for future captains to understand the system, but easy to skip if a polish captain cuts corners. Did not cut corners.

## Reusable patterns

### Adopt
- **"Detector convention wins over admiral estimate" for fixture alignment.** When a captain discovers the fixture's annotated value differs from the detector's principled convention by a small amount (here, 9-10 samples between `VCT>35` estimate and `bake_active_c=40` convention), default to aligning the fixture to the convention. Only retune the detector if there's a physical reason independent of any single fixture.
- **Test-order bugs as silent-green traps.** Portland's discovery — a tolerance-skip branch running before the ambiguous-case branch silently skipped the bake-1 assertion — is a pattern future captains should actively look for. When a target test should be RED but passes, check the order of branch guards in the test body.
- **Explicit reframing of prior-mission guards as "paper over" when a deeper bug is found.** Prior Dragon's `peak_idx+1` guard was empirically accurate ("first probe-pull of multi-pull session") but strategically wrong (a multi-pull session has multiple curves). Documenting this reframe in the captain's log prevents future captains from re-introducing the same guard under a different name.
- **Q3 as standing red-cell rubric: "what other inconsistencies does this fix expose?"** Artful's Q3 checked whether the bake-2 annotation refinement (766→775) also applied to bake-3 (6022→6032). Same pattern; hidden by `ambiguous=True`. Include a Q3-style "what siblings does this fix expose?" question in every red-cell prompt going forward.

### Avoid
- **Defending a fixture against a detector change by adding a guard.** Dragon's prior-mission `peak_idx+1` guard existed specifically to make the 2-bake annotation pass. When detector output disagrees with fixture annotation, the default should be to question the annotation first (is this really 2 bakes?) before adding detector guards.
- **Letting `ambiguous=True` flags silently suppress assertions that would catch related issues.** The bake-3 10-sample drift on 1759 was hidden for an entire mission because the ambiguous branch skipped the check. Ambiguous should mean "tolerance relaxed," not "assertion removed." Future fixture schema could encode per-bake tolerance instead of a global skip.
- **"Task 3 is complete, moving on" when the introspection matrix shows a visual defect.** Duncan's first handoff correctly flagged 30/30 tests green, but admiral's introspection revealed curve 1 = 294→944 (wrong — contains cooldown). Tests passing ≠ behaviour correct. Always verify the introspection matrix against the original user complaint, not just the test count.

## Standing order ledger

No blocking violations. Scope expansions:
1. Portland's test-order fix (within file ownership; necessary for mission's TDD gate).
2. Duncan's fixture tweak (admiral-authorized via SendMessage mid-mission; scope expanded from `src/data/curve_boundary_detector.py` to include `tests/fixtures/curve_boundary_cases.py` for the single-value update).
3. Spey's polish items A/B/C spanned both fixtures and detector file ownership; pre-authorized in briefing.

Mission complete.
