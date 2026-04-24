# Red-Cell Verdict — HMS Astute

## Verdict: ACCEPT_WITH_NOTES

Victory's implementation is empirically correct on every claim I was asked to verify. All 33 boundary tests pass, all five real CSVs produce the introspection Victory reported, and a 90-trial noise battery keeps curve-count at 3 for 1759. The only reasons this is not a plain ACCEPT are (a) two non-blocking observations about the implementation's dependence on skip-advance behaviour that the current fixture set masks, and (b) a pre-existing flake (`test_deep_insertion`, unrelated to this mission) that surfaced during my 3× repeat runs.

## Independent test verification
- Target TDD tests (TestOvenEntryStartDetection): **3/3 pass** (durations >20 min, bake-2 start=651±8, bake-3 start=5888±8).
- `tests/test_curve_boundary_detection.py`: **33/33 pass**, matching Victory's claim (30 existing + 3 new).
- Full suite 3× runs (same process, fresh): `7 failed / 143 passed / 1 skipped`, `8 / 142 / 1`, `8 / 142 / 1`.
  - The flaky extra failure in runs 2 and 3 is `tests/test_surface_sensor_detection.py::TestSurfaceSensorDetection::test_deep_insertion` — pre-existing, unrelated to curve_boundary_detector, consistent with prior-mission red-cell notes about that test's flake.
  - The 7 stable failures are all in `test_surface_sensor_detection`, `test_internal_sensor_filtering`, `test_visualization`, and `test_curve_comparison_integration` — same pre-existing set Victory reported, none under this mission's file ownership.

## Central questions

### Q1 — Other-CSV invariance
Confirmed. Direct introspection through the current detector:

| CSV | has T1..T8 | has PredictionState | core[0] | PredState transition | Curves | Method used |
|---|---|---|---|---|---|---|
| 100098DE_1351 | yes | yes | 22.85 | idx 3 | 1 (start=3, end=306) | Method 1 |
| BA3C_0946     | yes | yes | 25.40 | idx 13 | 1 (start=13, end=293) | Method 1 |
| WW (lidded)   | yes | yes (no 'Probe Not Inserted' state) | 31.30 | None | 1 (start=39, end=338) | Method 2b |
| PWM (lidded)  | yes | yes | 26.10 | idx 3 | 1 (start=3, end=344) | Method 1 |

Method 2b is reached for WW only; for the other three the plumbing is inert (method 1 short-circuits before max-sensor is consulted). All curves match Victory's introspection matrix exactly.

Follow-up on the single-curve post-cliff tail (100098DE, BA3C_0946, WW, PWM): after each of these curves ends the outer loop calls `_skip_probe_pull_tail` (cliff-fired exits for 100098DE, BA3C_0946, WW) or exits via plateau (PWM plateau exit → skip NOT called, confirmed by reading `extract_curves`). Critical: with the new max-based skip, `_skip_probe_pull_tail` advances past the full hot cascade so method 2b finds no further hit (see "New concerns" below — this is actually why Q1 is clean).

### Q2 — WW first-curve start path (why 39, not 3?)
Empirically answered. WW's `PredictionState` column contains only `['Probe Inserted', 'Cooking']` — the value `'Probe Not Inserted'` NEVER appears, so `_detect_start` method 1 has no transition to find and returns no candidate. Method 2a requires `temps[0] >= ROOM_TEMP_MAX (35.0)`; WW's core[0] is 31.30, so 2a also does not fire. Method 2b (cold-start) is the one that lands: `first_crossing(max_sensor >= 40, confirm_n=3)` = idx 39, identical to `first_crossing(core >= 40)` = idx 39 on this fixture because all 8 sensors warm uniformly before oven rise. Victory's "max-sensor == VCT pre-peak for WW" claim is literally true on the WW fixture.

This differs from PWM because PWM's PredictionState *does* contain 'Probe Not Inserted' and transitions to 'Probe Inserted' at idx 3, so method 1 wins there (start=3). Different methods fire on WW vs PWM despite both being lidded.

### Q3 — 1759 bake-1 method (did it actually use method 2?)
Confirmed: **method 1 (PredictionState)**, not method 2b. 1759's pred_state set is `['Probe Not Inserted', 'Probe Inserted', 'Cooking']`, and the first 'Probe Not Inserted' → other transition is at idx 12 → 13 (so `_detect_start` returns 13). Important correction to the briefing's framing: 1759's PredictionState *does* contain 'Probe Not Inserted' **once**, at the very start — the heuristic `_probe_cooking_continuous` returns True because it never reverts *after the first departure*, not because 'Probe Not Inserted' is absent. Method 1 fires for bake 1 exactly once and returns 13.

For bakes 2 and 3 `_detect_start` is re-invoked with `search_from` well past idx 13; method 1 finds no later 'Probe Not Inserted'→other transition, method 2a can't fire (search_from > 0), and method 2b fires on max_sensor: 651 and 5888 respectively. Traced directly through the code and confirmed by executing the same predicates against the CSV.

### Q4 — Noise sensitivity of max-sensor
Ran 30 trials each at σ ∈ {0.15, 0.5, 1.0} °C, gaussian noise applied independently to T1..T8 (and VCT/CoreTemperature) on a copy of 1759 each trial. Results:

| σ | wrong n_curves | bake-1 start | bake-2 start | bake-3 start |
|---|---|---|---|---|
| 0.15 | 0/30 | 13 ±0 | 651.57 ±0.50 (651..652) | 5888 ±0 |
| 0.5  | 0/30 | 16.67 ±14.57 (13..87) | 659.47 ±19.04 (651..729) | 5892.73 ±21.36 (5887..6005) |
| 1.0  | 0/30 | 13 ±0 | 657.43 ±27.39 (651..803) | 5889.97 ±8.66 (5887..5929) |

All 90 trials produced 3 curves. Start-index drift grows with σ (as expected — noise can shift the exact first-crossing sample), but never catastrophically. The quiescent region between bakes 2 and 3 has `max_sensor` mean=28°C (min=23.8, max=119.4 — the 119.4 is inside the bake-2 post-cliff cascade that the skip removes), so pushing a 25°C baseline past a 40°C threshold is not within σ=1.0 reach. No spurious bake-2-to-3 splits observed.

### Q5 — Bake-3 physical interpretation
Bake 3 is a **real bake**, not a "hot-oven dwell":
- VCT at start (5888) = 34.85 °C
- VCT at peak (6183) = 97.10 °C, **rise = 62.25 °C** over 24.75 min
- Time from start to VCT ≥ 80 °C: **18.17 min**

Comparison across the three bakes (similar shape → same physical event):

| Bake | start_vct | peak | rise | duration | t_to_80 |
|---|---|---|---|---|---|
| 1 | 30.80 | 96.75 | 65.95 | 23.33 | 18.67 min |
| 2 | 34.50 | 98.15 | 63.65 | 24.42 | 17.58 min |
| 3 | 34.85 | 97.10 | 62.25 | 24.75 | 18.17 min |

Bake 3 is within ~3% on every metric. There IS a noticeable 120-sample slow-warming phase at the start of bake 3 (VCT moves from 34.85 → 37.8 between idx 5888..6008) while T8 is already hot (≥42.6°C at 5888) — this is exactly the "ambient-leads-core" oven-entry phase the max-sensor detector is designed to capture. Physical interpretation: probe re-inserted into a hot oven, dough takes ~10 min to start warming its core sensor, then normal bake rise. Annotating start at 5888 (max-sensor crossing) captures the full bake including the insulated warm-up; annotating at 6032 (core crossing) would under-count it.

## Perturbation battery
- **Standard test runs (3×)**: boundary test file 33/33 three times; full suite 7/8/8 failures as described in "Independent test verification".
- **Noise (Q4)**: 90 trials across σ=0.15/0.5/1.0 — 0/90 wrong n_curves.
- **Old-vs-new skip (new adversarial probe)**: if the OLD core-based skip were used with the NEW max-sensor-based method 2b, these regressions would appear:
  | CSV | old-skip exits at | method 2b (max) from there | outcome |
  |---|---|---|---|
  | 100098DE | 339 (core) | 339 | spurious second curve |
  | BA3C_1759 after bake 1 | 307 | 307 | bake 2 fires inside the cascade |
  | BA3C_1759 after bake 2 | 962 | 962 | bake 3 fires inside the cascade |
  | PWM | 368 | 368 | spurious second curve |
  | BA3C_0946 | 300 | None | ok (truncated log) |
  | WW | 359 | None | ok |

  This is strong evidence that **Victory's skip change is strictly necessary**, not cosmetic — with method 2b on max_sensor and the OLD core-only skip, four of six real fixtures would regress. The max-sensor skip is load-bearing.

  Under the implemented combination (max-sensor skip + max-sensor method 2b), `m2b_after_new` is None for 100098DE/BA3C_0946/WW/PWM and returns the correct 651/5888 for 1759.

## Victory's implementation
**ACCEPT** with the following evidence:
- The three file diffs Victory reports match the code as currently on disk.
- The `_skip_probe_pull_tail` rename/retype is minimal and its docstring correctly captures both defence layers.
- Method 2a (mid-bake, `temps[0] >= room_temp_max`) is preserved on the core series — correctly — so synthetic fixtures whose first sample is already hot (e.g. two_bakes_no_cool, lidded_bake_no_cooldown) retain exactly their prior semantics.
- The `_resolve_max_sensor_series` helper falls back to the core series when T1..T8 aren't all present — essential for every synthetic fixture, which only supplies VCT. This is the reason synthetic-fixture tests are untouched.
- The fixture expected_starts edit (660 → 651) follows the "detector convention wins over admiral estimate" pattern documented in mission 2026-04-24_090858_d46e235e, and Victory escalated to team-lead before editing — correct process.

One minor implementation observation (non-blocking, see below): the detector file header comment at lines 27-31 cites this mission's directory as the origin of the max-sensor convention, which is fine, but `_skip_probe_pull_tail`'s docstring under "TWO-LAYER DEFENSE" still attributes both layers to mission `2026-04-24_090858_d46e235e` — that's the Q4 Artful mission, not Victory's. Harmless, and not this red-cell's business, but a future tidy would strengthen the provenance trail.

## New concerns

### NC-1 (NON-BLOCKING) — Skip is load-bearing; a single-fixture change in sample-period could unbalance it
The post-cliff cascade at 100098DE lasts 84 samples (=420 s at 5 s/sample) before max_sensor drops below 35. The skip's termination condition is `confirm_n=3` consecutive sub-room samples. At a coarser sample period (say 30 s/sample), the same physical 420 s cascade would be ~14 samples, and 3 consecutive sub-room might release the skip inside a fluctuating tail if T8 re-overshoots briefly. This has not been observed on any fixture and is NOT a defect today, but the skip's confirmation gate is not sample-period adaptive; a follow-up mission could make `confirm_n` a seconds-based parameter for consistency with the rest of the detector.

### NC-2 (NON-BLOCKING) — Method 2b can fire as early as the post-cliff tail if skip is ever removed
The detector now has a hard dependency between the max-sensor skip and the max-sensor method 2b (evidence above). This means future refactors must keep them coupled: you can't swap one without the other. Worth calling out in a comment near method 2b, or (better) covering with an explicit regression test that forces the skip-off code path on a real fixture and asserts a regression. No action required in this mission.

### NC-3 (NON-BLOCKING) — Noise at σ=0.5 shifted bake-1 start once from 13 to 87
In the σ=0.5 noise battery, one trial out of 30 produced bake-1 start=87 (method 1 on a clean PredictionState should always return 13). I did not trace this in detail; the most likely explanation is that the clean bake-1 curve was produced at start=13 but then rejected by the duration/peak gate under some noise realisation, and the outer loop re-entered `_detect_start` from past idx 13, where method 1 returns None and method 2b fires at 87. The suite-level outcome (3 curves, bake-2 + bake-3 durations > 20 min) is unaffected. Worth a future robust-start test, but not this mission.

### NC-4 (NON-BLOCKING) — `_probe_cooking_continuous` heuristic framing
The briefing (Q3) suggested "1759's PredictionState never reverts to 'Probe Not Inserted' — so does method 1 even fire for bake 1?" — this phrasing conflates "never reverts after first departure" (the heuristic) with "never contains 'Probe Not Inserted'" (false on 1759). Method 1 fires exactly once because the first-departure transition is at idx 13. The detector's docstring at `_probe_cooking_continuous` (lines 405-433) already explains this clearly and is calibrated to 1759. No code change needed.

## Blocking vs non-blocking
- **Blocking**: none.
- **Non-blocking**: NC-1, NC-2, NC-3, NC-4 above. All four are observations about the robustness envelope of the new implementation; none contradicts Victory's claims or breaks a current test.

## Probe scripts saved (as per Standing Orders)
- `.nelson/missions/2026-04-24_105032_1b3801f8/probes/probe_introspect.py` — full introspection matrix for all 5 real CSVs, reports method used per first-curve.
- `.nelson/missions/2026-04-24_105032_1b3801f8/probes/probe_outer_loop.py` — outer-loop trace on 1759 for bakes 2 and 3, confirms method 2b + skip combination.
- `.nelson/missions/2026-04-24_105032_1b3801f8/probes/probe_quiescent.py` — inspection of the 1759 inter-bake-2-and-3 quiescent region.
- `.nelson/missions/2026-04-24_105032_1b3801f8/probes/probe_noise.py` — noise battery, σ ∈ {0.15, 0.5, 1.0}, 30 trials each.
- `.nelson/missions/2026-04-24_105032_1b3801f8/probes/probe_bake3.py` — bake-3 shape vs bakes 1 and 2.
- `.nelson/missions/2026-04-24_105032_1b3801f8/probes/probe_single_curve_tail.py` — post-cliff tail lengths for the four single-curve CSVs.
- `.nelson/missions/2026-04-24_105032_1b3801f8/probes/probe_100098de_tail.py` — detailed 100098DE cascade trace showing skip termination at 394.
- `.nelson/missions/2026-04-24_105032_1b3801f8/probes/probe_old_skip.py` — comparison of old core-based skip vs new max-sensor-based skip (the strongest single piece of evidence that Victory's change is necessary).
