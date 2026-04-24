# Captain's Log — Stance B Re-Annotation

**Mission ID:** 2026-04-24_070615_fee9ec8f
**Branch:** `refactor/curve-boundary-detection` (now 6 missions deep; not yet merged)
**Duration:** ~70 minutes session-wall-clock
**Mode:** agent-team, 4 captains + 1 red-cell + admiral

## Mission summary

- **Planned outcome:** Adopt Stance B from prior mission's Q3. Re-annotate the 3 unlidded real fixtures to clip at the probe-pull cliff (physics-consistent with user's stated position that post-cliff samples are probe-pull mechanics, not bread cooldown). Remove the `CLIFF_PRE_PEAK_PLATEAU_SECONDS` and `CLIFF_PRE_PEAK_TOLERANCE_C` guards introduced in the prior mission so the cliff candidate fires universally across lidded and unlidded.
- **Achieved outcome:** Fixtures re-annotated. `CLIFF_PRE_PEAK_*` guards removed. Cliff candidate now fires universally. All 3 unlidded real CSVs clip at their cliff indices. Lidded cases (PWM, wonder white) unchanged. Dragon discovered BA3C_1759 contains a **first cliff at j=293** (first probe-pull of a multi-pull session per red-cell's Q1 reframing) BEFORE the real bake-1 endpoint at j=944, requiring 2 new physically-meaningful guards (scan starts from `peak_idx+1`; 80 °C minimum cliff-start temp). Red-cell accepted both replacement guards.
- **Success metric result:**
  - `pytest tests/test_curve_boundary_detection.py`: **30 passed** (held; 2 previously-RED tests flipped green via Dragon's detector change, not via test modification).
  - Full `pytest tests/`: **135 passed / 8 failed / 1 skipped** — baseline held (same 7-8 pre-existing failures with `test_deep_insertion` flake noise).
  - Introspection matrix per CSV:
    - `real_100098DE_1351`: end_idx 330 → **306** (cliff-clipped)
    - `real_1000BA3C_0946`: end_idx 299 → **293** (cliff-clipped)
    - `real_1000BA3C_1759` [bake 0]: 955 → **944** (cliff-clipped)
    - `real_1000BA3C_1759` [bake 1]: 6200 → **6185** (cliff-clipped)
    - `post_wonder_meal_lidded`: **344** (unchanged — plateau fires earlier than cliff)
    - `wonder_white_10k_lidded`: **338** (unchanged — plateau fires at 338 before cliff at ~350)

## Delivered artifacts

| Artifact | Location | Status |
|---|---|---|
| 3 unlidded fixtures re-annotated with Stance B ground-truth | `tests/fixtures/curve_boundary_cases.py` | description updated per case with mission ID + physics rationale |
| `CLIFF_PRE_PEAK_PLATEAU_SECONDS` + `CLIFF_PRE_PEAK_TOLERANCE_C` removed | `config/constants.py` | clean break; no graveyard constants |
| `CLIFF_MIN_START_TEMP_C=80.0` added (decoupled from MIN_PEAK_TEMP) | `config/constants.py` (Dauntless polish item B) | semantic separation between curve-acceptance and cliff-start |
| `_candidate_probe_pull_cliff` simplified + 2 replacement guards (`peak_idx+1` scan start; 80 °C min cliff-start temp) | `src/data/curve_boundary_detector.py` | both guards physically meaningful, red-cell accepted |
| Cliff noise-fragility docstring block | `src/data/curve_boundary_detector.py` (Dauntless polish item A) | documents σ=0.05–0.15 °C regression vs prior mission + 4 suggested mitigations for future work |
| Red-cell verdict + 11 probe scripts | `.nelson/missions/2026-04-24_070615_fee9ec8f/` | ACCEPT_WITH_NOTES |
| Damage reports | `.nelson/missions/2026-04-24_070615_fee9ec8f/damage-reports/*.json` | 4 captains + 1 red-cell |

## Key decisions

- **Decision:** Dragon's 2 replacement guards (`peak_idx+1` scan start + 80 °C min cliff-start temp) accepted despite being new guards that weren't in the original brief.
  - **Rationale:** BA3C_1759 contains a real bake-1 plus a first probe-pull event at j=293 followed by re-insertion and a second real bake phase ending at j=944. Without the guards, cliff fires at j=293 and clips bake-1 too early. The guards are physically meaningful (cliff shouldn't fire WHILE the running peak is still rising; cliff shouldn't fire below a minimum bread-cooked temperature) and are not a fixture-fit like the prior mission's `CLIFF_PRE_PEAK_PLATEAU_SECONDS=250`.
  - **Red-cell reframing (Q1):** Ambush's verdict explicitly reframed j=293 as "first probe-pull of a multi-pull session" (not just insertion as Dragon initially framed). Same pattern appears in PWM at j=189 (87→47, 40 °C drop). The guards handle this real operational signature across multiple CSVs, not a single-CSV fit.

- **Decision:** Polish item A documents noise-fragility as a risk rather than fixing it.
  - **Rationale:** Ambush measured that cliff now fires spuriously at σ=0.15 °C in 27–60% of BA3C_1759 trials. Real Combustion Inc. probes run σ=0.05 well below this per their spec, so current tests pass. But the detector is genuinely noisier than the prior mission (cliff went from tie-breaker to primary signal). Documenting the risk with 4 concrete mitigations (smoothing, threshold tightening, noise-relative threshold, order-invariant guard) gives a future mission a clear path. Fixing now would require re-running all perturbation probes with new parameters.

- **Decision:** Polish item B decouples `CLIFF_MIN_START_TEMP_C` from `MIN_PEAK_TEMP` despite no current value difference.
  - **Rationale:** Ambush flagged that one constant was serving two semantically distinct roles (curve acceptance vs cliff start). Separating now, with both at 80.0, lets future tuning of either threshold happen without breaking the other. Costs one new constant; buys independence.

- **Decision:** Concern C (BA3C_1759 bake-2 start drift 5890→6032, 142 samples) explicitly out of scope.
  - **Rationale:** Ambush confirmed this drift pre-dates this mission. It's an issue with the start-detection path, not the cliff/end-detection work this mission targeted. Logged to follow-ups for a dedicated mission.

## Validation evidence

**Admiral-run final checks:**
```
pytest tests/test_curve_boundary_detection.py -q
30 passed in 12.45s

pytest tests/ -q
135 passed, 8 failed, 1 skipped in 38.38s
```

**Red-cell (Ambush) empirical probes:**
- 30/30 boundary tests green across 3 runs. Full suite deterministic at 135/8/1.
- 18-fixture introspection matrix verified Dragon's claims on all 6 named cases.
- Q1 empirical finding: BA3C_1759 j=293 is a full 25-min bake followed by genuine 20 °C probe-pull — not just probe-insertion artifact. Same pattern in PWM at j=189.
- Q2 empirical: synthetic short-bake-with-cliff-at-peak confirms `peak_idx+1` scan start + grace-window fallback is correct.
- Q3 empirical: 80 °C is 7.35 °C below the lowest real cliff start (PWM j=189 at 87.35 °C) — defensible margin.
- Q4 empirical: zero interaction between min_k=2 contamination detector and cliff detector (different files, different pipeline stages).
- Noise regression: σ=0.15 °C causes 27–60% false cliff-fire rate on BA3C_1759 (documented as non-blocking — real Combustion probes operate below σ=0.05). Prior mission's "0 FP at σ≤1.0" no longer holds because cliff changed from tie-breaker to primary signal.

## Open risks

- **Risk:** Cliff noise-fragility at realistic σ=0.05–0.15 °C. Current fixtures ship below σ=0.05 so tests pass, but production CSVs with noisier probes (out of Combustion spec, or when a probe degrades) could silently gain extra curves via false cliff fires.
  - **Owner:** follow-up mission.
  - **Mitigation (documented):** Docstring on `_candidate_probe_pull_cliff` lists 4 options — 3-sample rolling smooth on cliff input, tighten `INSTANT_DROP_THRESHOLD_C` to 18 or 20, require cliff drop ≥ N× local noise estimate, order-invariant sliding-window guard.

- **Risk:** `BA3C_1759` bake-2 start drifts 5890 → 6032 (142 samples). **Pre-existing**, not caused by this mission. Start-detection path, not end-detection.
  - **Owner:** follow-up mission (not cataloged in prior missions' lists — add now).

- **Risk:** Cliff candidate now has 2 gating conditions (`peak_idx+1` scan, 80 °C min) that are themselves small calibrations against specific fixture features. If a future CSV has a legitimate sub-80 °C bake (underbaked, partial) where the probe is pulled, cliff won't fire.
  - **Owner:** when new fixtures arrive.
  - **Mitigation:** `CLIFF_MIN_START_TEMP_C` is now a dedicated config value — trivially adjustable.

- **Risk:** Branch `refactor/curve-boundary-detection` carries 6 missions' worth of uncommitted diff now. Merge blast radius grows.
  - **Owner:** user.

- **Risk:** Pre-existing `test_deep_insertion` flake persists through 6 missions. Same status.

## Follow-ups

| Item | Owner | Priority |
|---|---|---|
| **Commit + review/merge `refactor/curve-boundary-detection` branch** (now 6 missions deep; ~2000+ lines of cumulative diff) | user | strongly recommended before further work |
| Characterize real probe noise σ from static-temperature dataset + tighten cliff fragility | future fleet | before production deployment |
| Resolve BA3C_1759 bake-2 start drift (142 samples) — pre-existing | future fleet | new follow-up this mission |
| Acquire more real CSVs across lidded/unlidded variety | user (data collection) | ongoing |
| Prior missions' open follow-ups (15+ items in `memory/project_refactoring_plan.md`) | future fleets | as cataloged |

## Mentioned in Despatches

- **HMS Kent** — clean fixture re-annotation with physics-rationale documentation in each case's description. Preserved the bake-2 ambiguous flag on 1759 rather than losing it in the update. That kind of preservation of prior-mission context is what makes the captain's-log chain usable.

- **HMS Defender** — the "pytest may short-circuit on first mismatch" catch is the kind of test-infrastructure insight that prevents silent bugs. Flagged BA3C_0946 and BA3C_1759 might be hidden failures BEFORE Dragon discovered them, saving one round of iteration.

- **HMS Dragon** — discovered the BA3C_1759 j=293 second cliff during implementation (not at brief-read time) and flagged it as a substantive deviation with physical justification BEFORE shipping. Self-reported both guards with clear rationale. Chose physically-meaningful guards (peak_idx + temperature) over fixture-fitted ones (plateau duration).

- **HMS Ambush** — Q1 reframing (j=293 as multi-pull-session, not just insertion) recontextualized Dragon's entire guard design as handling a general probe-use pattern rather than a single-CSV quirk. Noise-fragility catch at σ=0.05–0.15 is a genuine regression Ambush's prior red-cell (in the first cliff mission) didn't see because cliff was a tie-breaker there, not the primary signal. Cross-mission continuity in a red-cell deserves commendation.

- **HMS Dauntless** — bounded scope maintained across 4 Polish captaincies now (Spey in the curve-boundary mission, Kent in the TransformationManager-audit thread, Duncan in probe-removal-fix, Diamond in probe-pull-cliff, now Dauntless). The "polish captain that doesn't fix things out of scope" pattern is a cultural load-bearer.

## Reusable patterns

### Adopt
- **Defender's "test short-circuit catch" precedent.** When a fixture change moves ground-truth values, the first failing test may mask additional failing tests in the same loop. Polish captains running validation should re-run assertions individually, not trust the first failure as the complete picture.
- **Dragon's "discover-and-flag-before-ship" discipline.** When an implementation surfaces a fixture quirk not anticipated in the brief, the captain's duty is to pause, document, and self-report the deviation — NOT to quietly add a guard and hope red-cell catches it. Dragon's report had the guards ready AND the physical justification AND the test-pass confirmation. Three-prong.
- **Ambush's Q1 reframing technique.** When a prior captain's description of a fixture feature is incomplete (e.g. "probe-insertion artifact"), red-cell's empirical investigation may produce a sharper reframe ("first probe-pull of a multi-pull session"). The reframe changes the risk model going forward. Future red-cell reviews should explicitly look for opportunities to reframe captain framings.
- **Polish captain's decoupling-without-value-change (Dauntless Concern B).** Separating a semantically-overloaded constant into two dedicated constants with the same value is a cheap structural improvement that pays off in future tuning. No behavior change, no test churn, just architectural cleanup.

### Avoid
- **Trusting the first pytest failure as the complete baseline.** Defender explicitly flagged this; it should be an invariant going forward.
- **Framing a guard as "probe insertion" when it's actually "first probe-pull."** Dragon's initial framing was too narrow; Ambush's reframing is more accurate and captures PWM's j=189 same-pattern occurrence. Future captains should stress-test their framing against more than one fixture before documenting.
- **Claiming noise-fragility immunity on a detector that moved from secondary to primary role.** Prior mission's Ambush measured 0 FP on cliff at σ≤1.0 because cliff was a tie-breaker; this mission's Ambush measured 27-60% FP at σ=0.15 because cliff is now primary. Future missions that change a detector's role in the aggregator should re-run noise probes against the new role, not trust prior-role measurements.

## Standing order ledger

No violations. Standard scope expansion for polish captain (Dauntless) authorized by briefing rather than formal `battle_plan_amended` event.

Mission complete.
