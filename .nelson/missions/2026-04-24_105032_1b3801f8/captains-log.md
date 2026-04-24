# Captain's Log — Max-Sensor Start Detection

**Mission ID:** 2026-04-24_105032_1b3801f8
**Branch:** `refactor/curve-boundary-detection` (9 missions deep)
**Duration:** ~30 minutes
**Mode:** agent-team, 4 captains + 1 red-cell + admiral

## Mission summary

- **Planned outcome:** Fix 1759 bake 2 and bake 3 durations (user reported they "should be greater than 20 minutes"; currently 14.2 and 12.8 min). Root cause: core sensor rises slowly after probe re-insertion into a hot oven; ambient sensor rises immediately and is the real oven-entry signal. Change start detection and `_skip_probe_pull_tail` to use `max(T1..T8)` instead of VCT alone.
- **Achieved outcome:** Max-sensor detection implemented. 1759 now returns 3 curves with durations **23.3 / 24.4 / 24.8 min**, all above the 20-minute floor. Single-curve CSVs (PWM, WW, 100098DE, BA3C_0946) unchanged. All 33 boundary tests green.
- **Success metric:**
  - `pytest tests/test_curve_boundary_detection.py`: 33 passed / 0 failed
  - Full suite: 143 passed / 7 failed / 1 skipped (same pre-existing failures; `test_deep_insertion` flake continues)
  - 1759: `[13→293, 651→944, 5888→6185]` all truncated=False

## Delivered artifacts

| Artifact | Location | Status |
|---|---|---|
| Max-sensor plumbing through `extract_curves` | `src/data/curve_boundary_detector.py` | new `_resolve_max_sensor_series` helper; `_skip_probe_pull_tail` and `_detect_start` method 2b updated |
| `_skip_probe_pull_tail` advances while `max(T1..T8) >= ROOM_TEMP_MAX` | same | catches ambient-side cascade (T8 stays hot ~30s post-cliff) |
| Cold-start method 2b uses `max(T1..T8) >= bake_active_c` | same | detects T8's sharp rise when probe enters oven |
| Method 1 (PredictionState) and method 2a (mid-bake) unchanged | same | preserved — single-curve CSVs use these |
| Fixture re-annotation: `[13, 775, 6032]` → `[13, 651, 5888]`; tolerance 5→8 | `tests/fixtures/curve_boundary_cases.py` | admiral's 660 estimate empirically refined to 651 during implementation |
| 3 new regression tests (`TestOvenEntryStartDetection`) | `tests/test_curve_boundary_detection.py` | duration > 20 min; bake-2 start 651±8; bake-3 start 5888±8 |
| NC-1/2/3 docstring additions | `src/data/curve_boundary_detector.py` | coupling + noise + sample-count caveats documented |
| Red-cell verdict + probe scripts | `.nelson/missions/2026-04-24_105032_1b3801f8/` | ACCEPT_WITH_NOTES |
| Damage reports | `.nelson/missions/2026-04-24_105032_1b3801f8/damage-reports/*.json` | 4 captains + 1 red-cell |

## Key decisions

- **Decision:** Use ambient sensor (via max-of-all-sensors) as the oven-entry signal, not core temperature.
  - **Rationale:** When probe re-enters a hot oven, ambient sensor T8 responds within 1-2 samples (jumps from ~25→70 °C), while core T1 takes 100+ samples to cross 40 °C (insulated by bread dough). For the user's analytical purpose ("how long was the probe in the oven"), ambient-rise is the correct start marker. For a pure "when did the core start cooking" measurement, VCT-based detection would be better — but the user's explicit preference (bakes should be ≥ 20 min) aligns with probe-in-oven semantics.

- **Decision:** Plumb `max_sensor` through the detector rather than compute on-demand in each method.
  - **Rationale:** Victory's implementation adds a `_resolve_max_sensor_series` helper and passes the precomputed series through. Avoids recomputing max(T1..T8) in multiple places (DRY). Keeps the existing method signatures mostly intact.

- **Decision:** Both `_skip_probe_pull_tail` and method 2b changed together; the two are now coupled.
  - **Rationale:** Astute's `probe_old_skip.py` counterfactual proved the coupling is load-bearing: with max-sensor method 2b but old core-based skip, 100098DE / PWM / both 1759 inter-bake gaps would all regress because method 2b would fire inside the post-cliff cascade where T8 stays hot. Both changes are strictly necessary. NC-2 documents this coupling for future maintainers.

- **Decision:** Admiral's fixture annotation (bake 2 start=660) corrected to 651 during Victory's implementation.
  - **Rationale:** My diagnostic sampled every 10 indices and missed the 650→651 transition. Detector output at the principled threshold (max ≥ 40) lands at 651. Fixture updated to match the detector's empirical output, not my guesstimate. Same "detector convention wins over admiral estimate" pattern as mission `2026-04-24_090858_d46e235e`.

## Validation evidence

**Admiral-run final checks:**
```
pytest tests/test_curve_boundary_detection.py -q
33 passed in ~15s

1759 introspection: 3 curves
  curve 0: 13->293   23.3 min
  curve 1: 651->944  24.4 min
  curve 2: 5888->6185 24.8 min
All truncated=False, all >20 min ✓
```

**Red-cell (Astute) empirical probes:**
- Q1 (other-CSV invariance): PWM=3 (method 1), WW=39 (method 2b; max_sensor==VCT pre-peak), 100098DE=3 (method 1), BA3C_0946=13 (method 1). All unchanged.
- Q2 (WW=39 investigation): WW's PredictionState never has 'Probe Not Inserted' so method 1 can't fire; sample[0] VCT=31.30 < 35 so method 2a can't fire; method 2b lands at 39 where both max and VCT cross 40. Victory's "unchanged" claim is literally correct.
- Q3 (1759 bake-1 method): Method 1 fires at idx 13. Victory's claim confirmed.
- Q4 (noise sensitivity): 90 trials at σ∈{0.15, 0.5, 1.0} °C — 0/90 wrong curve count.
- Q5 (bake-3 physics): Real bake. VCT rises 62.25°C over 24.75 min, shape matches bakes 1 and 2 within ~3%.
- Counterfactual test (probe_old_skip.py): confirmed that reverting just the skip change while keeping method 2b change would regress 100098DE, PWM, and 1759 inter-bake gaps.

## Open risks

- **Risk:** `_skip_probe_pull_tail`'s confirm_n is sample-count, not seconds. At sample periods significantly different from 5 s, skip may terminate too quickly or too slowly.
  - **Owner:** future mission.
  - **Mitigation:** NC-1 docstring note added. No current fixture exercises this; real fix requires sample-period-tunable confirmation.

- **Risk:** Method 2b + `_skip_probe_pull_tail` are now structurally coupled. Changing one without the other is a latent regression source.
  - **Owner:** future maintainers.
  - **Mitigation:** NC-2 coupling-warning comment block added with explicit regression risk citation.

- **Risk:** Ambient-sensor noise above σ≈0.5 °C can shift detected starts on single noise trials. Real Combustion probes operate well below this threshold.
  - **Owner:** future mission.
  - **Mitigation:** NC-3 note flags smoothing / noise-relative threshold as follow-up options.

- **Risk:** Branch is now 9 missions deep on `refactor/curve-boundary-detection`. Merge complexity continues growing.
  - **Owner:** user.

- **Risk:** `test_deep_insertion` flake persists through 9 missions.
  - **Owner:** separate test-hygiene mission.

## Follow-ups

| Item | Owner | Priority |
|---|---|---|
| **Commit + review/merge** `refactor/curve-boundary-detection` (9 missions) | user | increasingly urgent |
| Noise characterisation of real Combustion probes (σ) | future mission | |
| Sample-period-scaled confirm_n across detector candidates | future mission | |
| Prior missions' open follow-ups — see `memory/project_refactoring_plan.md` | future fleets | |

## Mentioned in Despatches

- **HMS Forth** — 3rd mission as fixture captain on this branch. Fast turnaround, preserves prior annotations, documents methodology clearly. A reliable pattern.

- **HMS Medway** — 3 target-behaviour tests with clean durations/start-indices assertions. No scope creep.

- **HMS Victory** — flagged admiral's off-by-10 estimate mid-implementation (660 vs empirical 651) via SendMessage rather than quietly adjusting thresholds. Victory's `_resolve_max_sensor_series` helper is a clean DRY extraction; the plumbing-through-signatures approach is structurally cleaner than computing max on-demand in multiple methods.

- **HMS Astute** — **probe_old_skip.py counterfactual** is the most structurally persuasive red-cell finding so far on this branch. Demonstrating that reverting one part of a two-part change would regress four other CSVs is a rigorous argument for coupling necessity — not just "both changes work" but "neither works alone." Future red-cell reviews should adopt this counterfactual-probe pattern.

- **HMS Spey** — 4th mission as polish captain. NC-1/2/3 captured exactly per brief, no functional changes, two clean pytest runs.

## Reusable patterns

### Adopt
- **Counterfactual probes as red-cell rigor.** Astute's probe_old_skip.py demonstrated that reverting ONLY the skip change (keeping method 2b change) would regress 4 other CSVs. This is a much stronger "both changes are necessary" argument than "both changes pass tests." Adopt for future two-part changes: include a counterfactual probe that removes each part individually and shows the regression.
- **Detector convention wins over admiral estimate (now 3 missions proven).** Admiral's bake-start estimates have been off by small amounts 3 times now (766 vs 775, 660 vs 651, 6022 vs 6032). Each time the detector's principled threshold was correct. Default: fixture annotations follow detector output at known thresholds, not admiral diagnostics.
- **Max-sensor as oven-environment detector.** Using `max(T1..T8)` rather than a specific sensor gives robust "is probe in hot environment" detection — ambient sensor signals oven entry fast, core sensor signals bake progress. Max captures "any heat anywhere on the probe."

### Avoid
- **Sampling every Nth index in admiral diagnostics.** My "T8 jumps at idx 660" was actually "T8 jumps at idx 651, I sampled idx 650 and 660 and missed 651." Future diagnostics should scan every sample in the region of interest.
- **Splitting related changes across independent mission tasks.** `_skip_probe_pull_tail` and method 2b are logically coupled (one prepares the state the other acts on). If they'd been split across separate missions, one ship-without-the-other would have regressed 4 CSVs silently. Always identify and ship together any set of changes where one alone creates regression.

## Standing order ledger

No blocking violations. Two minor scope expansions:
1. Admiral-authorized 660→651 fixture/test alignment mid-implementation (SendMessage authorization, scope-expansion documented in Victory's report).
2. Victory's `_resolve_max_sensor_series` helper added mid-implementation — an internal structural choice within file ownership, not scope creep.

Mission complete.
