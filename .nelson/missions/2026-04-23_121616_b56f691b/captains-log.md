# Captain's Log — Lidded-Bake Detection

**Mission ID:** 2026-04-23_121616_b56f691b
**Branch:** `refactor/curve-boundary-detection` (cumulative with the previous curve-detection mission; not yet merged)
**Duration:** ~90 minutes session-wall-clock
**Mode:** agent-team, 4 captains + 1 red-cell + admiral

## Mission summary

- **Planned outcome:** Add a core-peak-plateau end-detection candidate to `CurveBoundaryDetector` so lidded bakes — where the core's thermal mass under a metal lid prevents the sharp post-peak decline the other candidates rely on — terminate at oven-exit rather than at EOF or probe-removal.
- **Achieved outcome:** New `_candidate_core_peak_plateau` + rise-magnitude guardrail + `plateau_fired` flag + `_skip_plateau_tail` helper implemented. 3 new fixture cases (1 real from `wonder white 10k 13.01.2026.csv`, 2 synthetic) pin the contract. 3 new target tests flipped red→green; 11 original tests and 1 guardrail test all green. Full suite baseline stable at 120/8/1 across 3 runs. Red-cell verdict: ACCEPT_WITH_NOTES, 3 non-blocking polish items absorbed by Captain Spey.
- **Success metric result:**
  - `pytest tests/test_curve_boundary_detection.py`: **15 passed / 0 failed** (previous mission left 11; this mission added 4).
  - Full `pytest tests/`: **120 passed / 8 failed / 1 skipped** — the 8 failures are the same pre-existing set from the previous mission (zone colors + surface sensor detection), unrelated to curve detection.
  - Observed end_idx per lidded fixture: `wonder_white_10k_lidded` = 338 (target 340 ±5), `lidded_bake_plateau_classic` = 304 (target 300 ±5), `lidded_bake_plateau_truncated` = 304 (target 300 ±5). All within tolerance. `truncated=False` correctly set on all three — detector no longer falls through to EOF on lidded bakes.

## Delivered artifacts

| Artifact | Location | Status |
|---|---|---|
| `_candidate_core_peak_plateau` method | `src/data/curve_boundary_detector.py` | **added** (+ rise-magnitude guard, `_skip_plateau_tail` helper, `plateau_fired` flag threaded through `_detect_curve_end` and `_evaluate_exit_candidates`) |
| 3 new config constants + rationale comments | `config/constants.py` | `CORE_PEAK_PLATEAU_RATE_C_PER_SEC=0.01`, `CORE_PEAK_PLATEAU_CONFIRM_SECONDS=20` (deviated from briefed 60 — see Key Decisions), `CORE_PEAK_PLATEAU_RATE_WINDOW_SECONDS=30`. All three documented with mission-ID reference. |
| 3 new fixture cases | `tests/fixtures/curve_boundary_cases.py` | `wonder_white_10k_lidded` (real, 359 rows), `lidded_bake_plateau_classic` (synthetic, 601 samples with probe-removal distractor at idx 480), `lidded_bake_plateau_truncated` (synthetic, 360 samples ending mid-plateau) |
| 4 new tests | `tests/test_curve_boundary_detection.py` | `test_wonder_white_lidded_real_csv`, `test_synthetic_lidded_plateau_classic_ends_at_plateau_not_removal`, `test_synthetic_lidded_plateau_truncated_ends_at_plateau_not_eof`, `test_existing_unlidded_fixtures_unchanged` (guardrail) |
| Red-cell verdict | `.nelson/missions/2026-04-23_121616_b56f691b/redcell-verdict.md` | ACCEPT_WITH_NOTES |
| Ambush's empirical probe scripts | `.nelson/missions/2026-04-23_121616_b56f691b/probe_empirical.py`, `probe_edge.py`, `probe_edge2.py` | retained for replay by future fleets |
| Damage reports (Trent, Tamar, Warspite, Spey) | `.nelson/missions/2026-04-23_121616_b56f691b/damage-reports/*.json` | on disk |

Net change vs. previous mission's branch tip: `+33` lines in `config/constants.py`, `~120` lines added to `curve_boundary_detector.py`, `~140` lines of new fixtures, `~60` lines of new tests. No modifications to previously-shipped logic.

## Key decisions

- **Decision:** `CORE_PEAK_PLATEAU_CONFIRM_SECONDS` set to **20 s**, not the briefed 60 s.
  - **Rationale:** Captain Warspite profiled `wonder_white_10k_lidded` and found the real CSV has only ~4 samples (20 s at 5 s/sample) of sub-threshold plateau before the sharp post-oven-exit decline begins. A 60 s (12-sample) confirmation window would never fire and the wonder-white test could not pass. Reducing to 20 s required pairing with a second line of defence (rise-magnitude guardrail) to prevent misfires on unlidded bakes. Red-cell independently perturbed the fixtures with a 15 s plateau and confirmed the 20 s window does NOT spuriously fire.
- **Decision:** Add a **rise-magnitude guardrail** (plateau candidate only fires when core rose 2-10 °C in the 60 s before peak) that was not in the original brief.
  - **Rationale:** Required to keep the 20 s confirm safe. Empirically, lidded bakes sit in rise60s ∈ [3.05, 3.55] and non-lidded in [14.5, 30.2] or ≤ 1.0 — cleanly separable. Red-cell accepted the guard but flagged a theoretical vulnerability at rise60s ≈ 5-10 (no real CSV hits this band today; future mission to expand fixture coverage).
- **Decision:** Plateau candidate **scans from `peak_idx`**, not from `peak_idx + post_peak_grace` like the other candidates.
  - **Rationale:** The synthetic plateau boundaries need the confirmed run's first sample (`j - run + 1`) to land within tolerance of the true plateau onset, which is `peak_idx`. With `post_peak_grace=10`, scanning from `first_scan` puts the earliest confirmable run at `peak_idx + 10`, outside the ±5 tolerance. Kept `first_scan` in the signature for symmetry with sibling candidates (one-line comment explains).
- **Decision:** Added a `plateau_fired` flag to `_detect_curve_end`/`_evaluate_exit_candidates` return tuple + new `_skip_plateau_tail` helper.
  - **Rationale:** When the plateau candidate fires, the remaining ≥ bake-active samples (the post-plateau cooldown, which extends to EOF on the lidded fixtures) would otherwise be detected as a phantom second curve on the next outer-loop iteration. The flag gates the skip so it only activates on plateau exits, leaving other candidates' post-curve search behaviour unchanged. Red-cell verified no external callers are affected.
- **Decision:** Spey kept the unused `first_scan` parameter (Item B) rather than removing it.
  - **Rationale:** Removing would break call-site symmetry with sibling candidates in `_evaluate_exit_candidates` with no runtime benefit. Single-line comment explains; simpler than refactoring the call site.

## Validation evidence

**Admiral-run final checks:**
```
pytest tests/test_curve_boundary_detection.py -v
15 passed in 3.72s

pytest tests/ -q
120 passed, 8 failed, 1 skipped in 16.80s
```

**Red-cell empirical probes** (from `redcell-verdict.md`):
- 3 runs of full suite: 120/8/1 each time (stable).
- Short-plateau perturbation (15 s, 3 samples): plateau candidate did NOT fire — 20 s confirm window is safe.
- Which-candidate-fires matrix across all 14 fixtures: plateau fires on exactly the 3 lidded cases, nowhere else.
- Rise60s per fixture: lidded [3.05, 3.55], non-lidded [14.5, 30.2] or ≤ 1.0 — empirical separation verified.
- Pre-peak spurious fire probe: no misfire observed.
- Multi-curve lidded→unlidded + overlapping-bakes probe: `_skip_plateau_tail` does not swallow genuine second bakes.
- `grep` confirms no stray hardcoded plateau thresholds outside config.

## Open risks

- **Risk:** Rise-magnitude guardrail (2-10 °C over 60 s before peak) has theoretical fragility at rise60s ≈ 5-10 — a slow-rising unlidded bake with a quasi-plateau at peak could misfire.
  - **Owner:** follow-up mission.
  - **Mitigation:** No real CSV in the current fixture set hits this band (non-lidded are all ≥ 14.5 or ≤ 1.0, lidded are 3.05-3.55). Expand the real unlidded fixture set to cover the 5-10 rise60s band and re-validate. Rationale comment in `curve_boundary_detector.py` at the guard site flags this.

- **Risk:** `CORE_PEAK_PLATEAU_CONFIRM_SECONDS = 20 s` was chosen to fit one real CSV (`wonder_white_10k_lidded`). Same calibration-to-a-sample-of-one concern that the previous mission raised for `_probe_cooking_continuous` applies here, scaled down.
  - **Owner:** follow-up mission.
  - **Mitigation:** Acquire ≥ 2 more real lidded-bake CSVs (ideally with varying oven temperatures and lid-thickness) and verify the 20 s window holds. The in-code comment names the mission ID so the calibration provenance is traceable.

- **Risk:** At sample periods ≥ 10 s, `CONFIRMATION_WINDOW_SAMPLES` floor (default 3) dominates over the seconds-based confirm. Documented in `config/constants.py` as intentional (defensive against very sparse sampling), but future consumers sampling at ≥ 10 s should be aware.
  - **Owner:** (documentation only; no action)

- **Risk:** `test_deep_insertion` in `tests/test_surface_sensor_detection.py` is pre-existing flake (40% failure rate in isolation, order-dependent). Unrelated to this mission — Warspite touched no surface-sensor code.
  - **Owner:** separate test-hygiene mission.
  - **Mitigation:** flagged in Ambush's verdict (Note D) for follow-up; not addressed here.

## Follow-ups

| Item | Owner | Priority |
|---|---|---|
| Commit + review `refactor/curve-boundary-detection` branch (two missions' worth of diff now ready) | user | next session |
| Expand real unlidded fixture set to cover rise60s 5-10 band | future fleet | when more CSVs available |
| Acquire ≥ 2 more real lidded-bake CSVs for cross-validation of 20 s confirm window | future fleet | when more CSVs available |
| Resolve `test_deep_insertion` flake (pre-existing, unrelated) | separate mission | lower priority |
| Follow-up items still open from previous mission (cross-CSV `_probe_cooking_continuous`, `MIN_CURVE_DURATION_SECONDS` re-anchor, truncated duration floor, `_detect_start` inter-curve invariant, 8 pre-existing full-suite failures, `TransformationManager` disposition, `app.py` split, root-level script cleanup) | future fleets | as previously catalogued |

## Mentioned in Despatches

- **HMS Trent** — tight fixture discipline. Delivered 3 clean cases including the real CSV with its quirks (double-comma header, trailing NaN rows) handled without drama. Ground-truth methodology documentation carried forward from the previous mission's Forth convention.

- **HMS Tamar** — caught the subtle interaction between the new `wonder_white_10k_lidded` case (source='real') and the existing `test_ground_truth_real_csvs_tight` loop, and filtered appropriately rather than loosening the test. That kind of incidental-but-important catch is how regressions get prevented.

- **HMS Warspite** — self-reported all 3 deviations explicitly (confirm-window reduction, rise-magnitude guard, scan-from-peak_idx), giving Ambush a structured review surface. The rise-magnitude guardrail is the piece that makes the 20 s confirm safe; this is a genuinely good engineering move, not just a workaround.

- **HMS Ambush** — raised the bar for empirical red-cell review. Rise60s matrix across all 14 fixtures, short-plateau perturbation probe, multi-curve lidded→unlidded probe, overlapping-bakes probe — all saved to disk as runnable Python scripts for future replay. Previous mission's "Mentioned in Despatches" for Astute called this pattern adoptable; Ambush took it further.

- **HMS Spey** — comments-only discipline. Absorbed the 3 non-blocking items without touching logic, verified twice that baseline held, and correctly declined to action item D (unrelated flake) per standing orders.

## Reusable patterns

### Adopt
- **Self-reported deviations in handoff** (Warspite self-disclosing 3 departures from brief) + **empirical perturbation review** (Ambush running the detector against modified fixtures) is now a repeat-winner combination. Two missions in a row, both shipped clean with clear audit trails.
- **Saving red-cell probe scripts to disk** for future replay (Ambush dropped `probe_empirical.py`, `probe_edge.py`, `probe_edge2.py` in the mission dir). Cheap to do, preserves the exact perturbation set that was used to certify the code, and gives the next mission a starting point for regression testing.
- **Rise-magnitude guardrail as a "second line of defence"** pattern when tuning a primary threshold tightly. The 20 s confirm window was tuned aggressively to fit the real CSV; the 2-10 °C rise guard is the independent check that prevents the tight tuning from misfiring on unrelated curve shapes.
- **Pairing parameter changes with empirical separation data** — Ambush's rise60s matrix (lidded 3.05-3.55 vs non-lidded [14.5, 30.2] or ≤ 1.0) is exactly the evidence a future mission will need to decide whether to raise or lower the guard. Future briefs should ask captains to produce this kind of matrix on any parameter change.

### Avoid
- **Tuning parameters to a single real CSV.** Twice now (`_probe_cooking_continuous` in the previous mission, `CORE_PEAK_PLATEAU_CONFIRM_SECONDS` here), the implementation has been anchored to a sample-of-one real case. Both times the red-cell flagged it, both times it was accepted as non-blocking, both times the mitigation is "acquire more real CSVs." The pattern is becoming a recurring tech debt. A better approach going forward: require at least 2 real fixtures per novel product type before a new calibration ships.
- **Widening return-tuple signatures** to carry state through the call stack (`plateau_fired` flag). This worked cleanly here because there were no external callers, but a method that returns `(int, int, bool, bool)` is one flag away from being un-reviewable. If another flag needs threading, consider returning a small dataclass instead.

## Standing order ledger

No violations. One battle-plan amendment was required at formation (Spey's initial file_ownership was the same set as Warspite's, which the preflight hook correctly flagged as split-keel). Amended by narrowing Spey's ownership to read-only verification, then re-expanding after Warspite stood down (sequential handover, no concurrent write risk). Logged as a `battle_plan_amended` event.

Mission complete.
