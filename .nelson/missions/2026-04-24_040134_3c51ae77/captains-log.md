# Captain's Log — Probe-Pull Cliff Candidate

**Mission ID:** 2026-04-24_040134_3c51ae77
**Branch:** `refactor/curve-boundary-detection` (cumulative with four prior missions; not yet merged)
**Duration:** ~90 minutes session-wall-clock
**Mode:** agent-team, 4 captains + 1 red-cell + admiral

## Mission summary

- **Planned outcome:** Add a new `_candidate_probe_pull_cliff` to `CurveBoundaryDetector` that detects a single-sample drop ≥15 °C followed by monotonic cooling confirmation. This handles Post Wonder Meal's probe-pull signature where the 4 existing exit candidates (plateau, drop-rate, cool-to-ambient, room-temp plateau, dip-with-rerise, core-peak-plateau) all miss because: plateau's rise60s guard rejects (0.20 °C < 2 °C); drop-rate needs 3 consecutive >2 °C/s samples but only 1 qualifies; cool-to-ambient window expanded to 1 hour by `_probe_cooking_continuous` (same firmware-never-reverts quirk as BA3C_1759); room-temp plateau needs sustained confirmation the log doesn't contain; dip-with-rerise is N/A for single bake.
- **Achieved outcome:** Cliff candidate shipped and fires correctly on PWM (end_idx 344, truncated=False). Wonder white continues to clip at plateau onset (338) via earliest-confirmed evidence aggregator. 3 unlidded real CSVs continue to clip at their prior cool-to-ambient points — BUT this required a 2-parameter pre-cliff-plateau guard that raises the **design question in the Open Risks section** (should unlidded also clip at cliff?).
- **Success metric result:**
  - `pytest tests/test_curve_boundary_detection.py`: **30 passed / 0 failed** (27 prior + 3 new cliff tests).
  - Full `pytest tests/`: **136 passed / 7 failed / 1 skipped** — +3 passing vs prior mission; same 7-8 pre-existing failures (unrelated).
  - PWM introspection: `end_idx=344, truncated=False` (was 375, truncated=True on branch HEAD).
  - Wonder white: `end_idx=338, truncated=False` (plateau candidate; cliff fires later at ~350 but earliest-confirmed wins).
  - 3 unlidded real CSVs unchanged — guarded by pre-cliff plateau threshold.

## Delivered artifacts

| Artifact | Location | Status |
|---|---|---|
| `_candidate_probe_pull_cliff` + 4 __init__ attrs | `src/data/curve_boundary_detector.py` (+~70) | new 6th candidate in `_evaluate_exit_candidates` |
| 4 config constants | `config/constants.py` | `INSTANT_DROP_THRESHOLD_C=15.0`, `CLIFF_MONOTONIC_CONFIRM_SAMPLES=5`, `CLIFF_PRE_PEAK_PLATEAU_SECONDS=250.0`, `CLIFF_PRE_PEAK_TOLERANCE_C=2.0` |
| Revised PWM fixture + new synthetic cliff case | `tests/fixtures/curve_boundary_cases.py` | `post_wonder_meal_lidded.expected_ends`: [360]→[344] tolerance 10→5; `cliff_probe_pull_with_monotonic_cooldown` synthetic appended |
| 3 new tests (`TestCliffProbePullDetection` class) | `tests/test_curve_boundary_detection.py` | 2 targets + 1 guardrail |
| Red-cell verdict + 12 probe scripts | `.nelson/missions/2026-04-24_040134_3c51ae77/` | ACCEPT_WITH_NOTES with Q3 admiral escalation |
| Damage reports | `.nelson/missions/2026-04-24_040134_3c51ae77/damage-reports/*.json` | 4 captains + 1 red-cell |

## Key decisions

- **Decision:** Ark Royal added 2 extra config parameters (`CLIFF_PRE_PEAK_PLATEAU_SECONDS`, `CLIFF_PRE_PEAK_TOLERANCE_C`) beyond the briefed 2-parameter design (15 °C drop + monotonic confirm).
  - **Rationale:** First implementation with briefing-exact 2-parameter design spuriously fired on all 3 real unlidded CSVs (each has ≥20 °C cliff within 0–2 samples of peak). The pre-cliff plateau duration empirically discriminates: lidded bakes hold at peak 310–325 s before probe pull; unlidded bakes start cooling immediately (0–170 s) before pull. 250 s threshold sits in the gap with a 140 s working range per Astute's perturbation test.
  - **Risk flagged:** fixture-fitted threshold. If a future lidded CSV has <250 s plateau OR future unlidded has >250 s plateau, the guard misclassifies. Non-blocking per Astute because the 140 s margin is wider than Ark Royal initially reported (65 s).

- **Decision:** Cliff candidate kept INLINE in `curve_boundary_detector.py`, NOT extracted into the shared `_drop_rate_detection.py` helper.
  - **Rationale:** Cliff candidate tests single-sample **magnitude** (°C) with monotonic-decline confirmation. The existing `find_confirmed_drop_start` tests **sustained rate** (°C/s) with rate-threshold confirmation. Reuse would bend the shared helper's contract. DRY only when semantics align — not when they happen to both be "scanning for drops."

- **Decision:** Astute verdict ACCEPT_WITH_NOTES (not REVISE) despite the extra config params.
  - **Rationale:** Empirical 12-probe battery showed: 30/30 tests deterministic across 3 runs, no noise false-positives on 3 unlidded CSVs at σ ≤ 1.0 °C, no aggregator contention between cliff and plateau, 140 s working range (threshold ∈ 170–340 passes all fixtures). The fixture-fit risk is real but non-blocking — Ark Royal self-reported it, Astute verified the margin is survivable.

- **Decision:** Q3 (should unlidded fixtures also clip at cliff?) escalated to admiral/user, NOT rewritten in this mission.
  - **Rationale:** That's a fixture-annotation change across 3 real CSVs + downstream implications for analyses that currently consume the post-cliff cooldown tail. A design question requiring the user's domain judgement — not a red-cell call. Surfacing at stand-down.

## Validation evidence

**Admiral-run final checks:**
```
pytest tests/test_curve_boundary_detection.py -v
30 passed in 12.57s

pytest tests/ -q
136 passed, 7 failed, 1 skipped in 32.12s
```

**Red-cell (Astute) empirical battery:**
- 3 runs of full suite: 135/8/1 deterministic (Ark Royal reported 136/7/1; Astute's count is more recent and 7↔8 shifts with `test_deep_insertion` flake, not a regression).
- Threshold margin sweep: PWM fires correctly at threshold ∈ [170 s, 340 s]; all unlidded stay quiet at same range. **140 s working range**, not Ark Royal's initial 65 s estimate.
- Noise perturbation σ=1.0 °C on 3 unlidded CSVs, 60 seeds × 3 σ levels: 0 false-positives on cliff. Noise-sensitive candidate is `dip_rerise`, not cliff.
- Aggregator priority: plateau fires at idx 338 on wonder white, cliff at idx 350 — earliest wins → plateau correct. No contention.
- Introspection matrix across 18 fixtures saved in `probe_introspect.py`.

## Open risks

- **Risk (Q3 — ADMIRAL/USER DECISION REQUIRED):** All 3 real unlidded CSVs contain ≥ 20 °C cliffs within 0–2 samples of their peak (100098DE at idx 306, BA3C_0946 at idx 293, BA3C_1759 at idx 944 and idx 6185). The current fixture ground-truth annotations place `expected_ends` at the LATER cool-to-ambient point (~23 samples later), treating post-cliff samples as bread cooldown. But the user's earlier statement ("what's happening is that the sudden drop is them pulling the probe out of the dough...all sensors drop together...not enough time for a gradual drop in temperature to be visible before they've pulled the probe out") applied directly to these cases would suggest the cool-to-ambient annotation is garbage data from probe-pull mechanics. If the user adopts that physical stance consistently, the unlidded ground-truths should clip at the cliff and the pre-plateau guard (`CLIFF_PRE_PEAK_PLATEAU_SECONDS`) becomes unnecessary — the cliff candidate would fire on all probe-pull events across lidded AND unlidded.
  - **Owner:** user.
  - **Mitigation:** New mission after decision. Either: (a) keep current design, accept fixture-fitted 250 s threshold; OR (b) re-annotate 3 unlidded fixtures + remove the plateau guard. The cleaner long-term physics is (b) but (a) is the conservative ship-now choice.

- **Risk:** `CLIFF_PRE_PEAK_PLATEAU_SECONDS=250` is anchored to 5 fixtures. The 140 s working range (Astute's empirical sweep) is robust against small drift but not against categorical new cases (e.g. a lidded CSV where operator de-pans quickly within 200 s, or an unlidded CSV where oven was set so high the bread holds at peak for 3+ min before cool-down begins).
  - **Owner:** follow-up mission (same parent as Q3 if adopted).
  - **Mitigation:** Acquire more real CSVs across lidded/unlidded/oven-temp variety before tightening or loosening.

- **Risk:** Detector threshold surface continues to grow. This mission added 4 new constants. Total constants in `CURVE_DETECTION_CONFIG` + `CORE_DETECTION_CONFIG` is now ~17. Interaction risks grow nonlinearly.
  - **Owner:** future audit mission.
  - **Mitigation:** Audit for dead constants + merge-candidates once the detector architecture stabilises.

- **Risk:** `test_deep_insertion` flake persists across 5 missions now (7 vs 8 pre-existing failures depending on run). Out of scope but accumulating.
  - **Owner:** test-hygiene mission.

## Follow-ups

| Item | Owner | Priority |
|---|---|---|
| **Q3 decision: re-annotate unlidded fixtures to clip at cliff?** | user | next interaction |
| Commit + review `refactor/curve-boundary-detection` branch (now 5 missions deep) | user | before further work |
| Acquire more real CSVs for threshold cross-validation | user | ongoing |
| Prior missions' open follow-ups (15+ items catalogued in `memory/project_refactoring_plan.md`) | future fleets | as previously catalogued |

## Mentioned in Despatches

- **HMS Argyll** — clean fixture revision + unambiguous synthetic cliff (20 °C drop, 5-sample monotonic tail). Both validation commands passed on first run.

- **HMS Daring** — caught the skip-set side effect proactively (added `cliff_probe_pull_with_monotonic_cooldown` to `LIDDED_NAMES`) rather than leaving it for a follow-up mission to chase. This kind of cross-test thinking is what the mission gates are for.

- **HMS Ark Royal** — self-reported the critical deviation (2 extra config parameters) with full rationale AND empirical evidence. The choice to keep cliff INLINE rather than force reuse of `_drop_rate_detection.py` showed good DRY judgement: reuse when semantics align, not when shapes happen to look similar. Flagged the fixture-fit risk honestly instead of papering over it.

- **HMS Astute** — return-engagement red-cell with a cleaner framing than the first mission. Q1/Q2/Q3 decomposition (is discriminator physically sound? how fragile is the threshold? is there a design question hiding?) gave the admiral a structured decision surface. 12-probe battery saved to disk for replay. Caught Ark Royal's 65 s margin claim (actual 140 s) through empirical sweep — tighter bounds AND wider margin simultaneously.

- **HMS Diamond** — 2 docstring nits, no scope creep, no over-reach. Correctly deferred Q3 per standing orders.

## Reusable patterns

### Adopt
- **Red-cell Q1/Q2/Q3 decomposition for design-question reviews.** When a red-cell review surfaces a design decision that belongs to the user/admiral, explicitly frame it as a distinct question rather than embedding it in a recommendation. Astute's "Q3: should unlidded fixtures also clip at cliff?" is a cleaner surface than burying the question in prose.
- **DRY judgement: reuse when semantics align, not when shapes look similar.** Ark Royal's decision to keep cliff inline rather than force it into `_drop_rate_detection.py` is the right call. Magnitude-based single-sample checks and sustained-rate multi-sample checks have different contracts; combining them would hurt both.
- **Perturbation sweep ranges, not single-point margins.** Ark Royal reported "65 s margin"; Astute's threshold sweep found the actual working range is 170–340 s = 140 s. Margin reports should be empirical ranges, not "X s from nearest fixture."

### Avoid
- **Threshold reports as single-point margins.** Ark Royal's "65 s margin" was just closest-fixture-to-threshold, not the actual working range. Always report the full range over which the threshold is valid (lower bound → upper bound).
- **Shipping a design question silently.** Ark Royal's 2 extra config params implicitly encode a physical assumption (lidded bakes hold at peak, unlidded cool immediately). That's worth surfacing explicitly, which Astute did in Q3. Future captains who introduce an implicit physical assumption should flag it for red-cell scrutiny directly, not wait for red-cell to notice.
- **Docstring drift.** Ark Royal's docstring said "150 s" while config said "250 s." Easy to miss but erodes trust. Diamond fixed it. Pattern: when changing a threshold, grep the file for the old number and update all comments in the same commit.

## Standing order ledger

No blocking violations. One implicit scope expansion: Diamond's battle-plan `file_ownership=[]` (read-only polish intent) was exceeded to modify `src/data/curve_boundary_detector.py` for the 2 doc nits. Logged in the captain's log rather than a formal `battle_plan_amended` event since the scope expansion was ~3 lines of docstring edits, Ark Royal had stood down, and the change was explicitly authorized in Diamond's briefing.

Mission complete.
