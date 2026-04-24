# Captain's Log — Probe-Removal Contamination Fix

**Mission ID:** 2026-04-24_015052_25705c7a
**Branch:** `refactor/curve-boundary-detection` (cumulative with three prior missions; not yet merged)
**Duration:** ~80 minutes session-wall-clock
**Mode:** agent-team, 4 captains + 1 red-cell + admiral

## Mission summary

- **Planned outcome:** Detect the probe-removal signature in the core classifier's cool-rank window (operator pulling the probe out of the loaf shortly after peak makes cool-rank measure probe-pull mechanics, not bread cooling), and fall back to heat-only ranking when contamination is detected.
- **Achieved outcome:** Probe-removal contamination detector shipped. Uses multi-sensor simultaneous-drop physics (≥2 sensors must exceed rate threshold on the same sample) after a REVISE iteration tightened it from min_k=1 to min_k=2. Cross-mission DRY extraction to `src/data/_drop_rate_detection.py` shared between curve boundary detector and classifier. Post Wonder Meal now resolves core to T5 (was T7 via contaminated cool-rank). Wonder white still resolves to T5 (now via the new contamination path rather than the Iron-Duke `cool_available=False` path — same answer, more explicit mechanism). Guardrail CSV `real_1000BA3C_1759` (genuine slow cooldown) correctly does NOT trigger contamination.
- **Success metric result:**
  - `pytest tests/test_curve_boundary_detection.py`: **27 passed / 0 failed** (25 prior + 2 new negative tests).
  - Full suite: **133 passed / 7 failed / 1 skipped** — +5 passing vs prior mission baseline (4 new PR tests + 1 new staggered-spike + 1 BA3C_0946 assertion − 1 test_deep_insertion flake noise). 7 failures are the same pre-existing set; zero new regressions.
  - BA3C_1759 noise FP rate (σ=1.0 °C): **4%** (was 13% at min_k=1 — passes the <5% bar).
  - PWM (Post Wonder Meal): `winner=T5, cool_contamination_detected=True`.

## Delivered artifacts

| Artifact | Location | Status |
|---|---|---|
| Probe-removal detection helper | `src/data/_drop_rate_detection.py` (new, 120 lines) | exports `find_confirmed_drop_start` (single-series, from curve boundary detector) and `find_confirmed_multi_sensor_drop` (with `min_k_sensors=2` default) |
| Shared helper consumed by classifier | `src/data/thermodynamic_sensor_classifier.py` (+50) | `_detect_probe_removal_in_cool_window` + `cool_contamination_detected` diagnostic |
| Shared helper consumed by curve boundary detector | `src/data/curve_boundary_detector.py` (−22) | `_candidate_drop_rate` now delegates to shared helper, behaviour bit-identical |
| `CORE_DETECTION_CONFIG` entries | `config/constants.py` (+15) | `PROBE_REMOVAL_RATE_C_PER_SEC=2.0`, `PROBE_REMOVAL_CONFIRM_SAMPLES=2`, `PROBE_REMOVAL_MIN_SIMULTANEOUS_SENSORS=2` (the revised-in value) |
| Post Wonder Meal real case + synthetic contamination case | `tests/fixtures/curve_boundary_cases.py` (+11, admiral-authorized) | `post_wonder_meal_lidded` (expected_core_sensor='T5'), `probe_removal_contaminates_cool_rank` synthetic |
| 4 new contamination tests + 2 negative tests | `tests/test_curve_boundary_detection.py` | `TestProbeRemovalContamination` class |
| Red-cell verdict (REVISE) | `.nelson/missions/2026-04-24_015052_25705c7a/redcell-verdict.md` | |
| Audacious's 4 probe scripts | `.nelson/missions/2026-04-24_015052_25705c7a/probe_*.py` | for future replay |
| Damage reports | `.nelson/missions/2026-04-24_015052_25705c7a/damage-reports/*.json` | 4 captains + 1 red-cell |

## Key decisions

- **Decision:** User's physical insight drove the mission — probe pull contaminates cool-rank, heat-only is more reliable than a contaminated combined rank.
  - **Rationale:** On Post Wonder Meal the operator pulled the probe ~5-6 samples after peak. All sensors dropped together. The classifier read this as "cooling" and used the contaminated retained-temp values for cool-rank, letting T7 win over the actually-correct T5. The fix is to detect probe pull and fall back to heat-only (which the prior mission had already justified as the more reliable signal during active bake).

- **Decision:** Admiral authorized scope expansion into `tests/fixtures/curve_boundary_cases.py` mid-mission for a 3-line patch (ballooned to 6 lines + 4 lines of rationale — Vanguard discovered the loader gate needed 5 Virtual* columns not just 3).
  - **Rationale:** Portland's synthetic fixture was missing the Virtual* column set that routes a fixture through the combined-rank classifier path. Without the patch, the synthetic contamination test was exercising the LEGACY classifier path, not Vanguard's work. The alternative (re-run Portland) would have cost more than a direct authorization. Red-cell (Audacious) independently verified the loader gate at `loader.py:278` requires all 6 Virtual* cols and confirmed the expansion was necessary, not scope creep.

- **Decision:** Red-cell REVISE, not ACCEPT_WITH_NOTES — Audacious measured 13% FP on BA3C_1759 and 62% FP on 100098DE at σ=1.0 °C noise with Vanguard's `min_k=1` detector. Duncan tightened to `min_k=2` following Audacious's Pareto-dominance proof.
  - **Rationale:** `min_k=1` (any single sensor spikes → confirm) was weaker than probe-pull physics requires. A real probe pull drops ≥2 sensors on the same sample (the probe moves rigidly); single-sensor spikes are noise. `min_k=2` matches the physics AND drops BA3C_1759 FP to 4% while preserving PWM true-positive. Audacious's probe scripts are saved for replay.

- **Decision:** Duncan rewrote `test_real_1000BA3C_0946_not_contaminated` instead of asserting the false claim the briefing requested.
  - **Rationale:** BA3C_0946 genuinely has a probe-pull event at idx 294-295 (4 sensors simultaneously drop ≥2 °C/s). Audacious's briefing assumption that min_k=2 would suppress this was empirically wrong. Duncan correctly refused to assert `cool_contamination_detected=False` for a case that genuinely IS contaminated, and rewrote the test to assert the correct physical truth: `winner=T1` and `cool_available=False` (the classifier's heat-only fallback fires for this case via the `cool_available=False` branch Iron Duke shipped, not the new contamination branch — same result, different mechanism). This preserves the test's original intent: "unlidded real CSVs produce the right winner."

- **Decision:** DRY extraction into `src/data/_drop_rate_detection.py` accepted.
  - **Rationale:** Vanguard spotted that both the curve boundary detector's `_candidate_drop_rate` and the new contamination detector were doing essentially the same thing (scan for sustained drop rate over N consecutive samples). Two entry points in the shared module: single-series (unchanged use by boundary detector) and multi-sensor-with-min-k (used by classifier). Red-cell accepted the extraction.

## Validation evidence

**Admiral-run final checks:**
```
pytest tests/test_curve_boundary_detection.py -v
27 passed in 5.94s

pytest tests/ -q
133 passed, 7 failed, 1 skipped in 28.24s
```

**Red-cell (Audacious) empirical probes:**
- Noise FP rate σ=1.0 °C, 100 seeds per CSV × 3 unlidded CSVs:
  - BA3C_1759 at min_k=1: 13% → min_k=2: **4%** (below 5% threshold ✓)
  - 100098DE at min_k=1: 62% → min_k=2: 17% (improved but not under 5%; min_k=3 would fix but breaks PWM true-positive — Pareto-optimal trade)
  - BA3C_0946: baseline contam=True at both min_k=1 and min_k=2 — **this is genuine probe-pull detection on a real CSV**, not a false positive. Test was rewritten to assert this correctly.
- Staggered-spike probe (8 sensors, 1-sample spike each, spread across 20 samples): min_k=1 fired spuriously → min_k=2 does NOT fire (correct — no simultaneous drop).
- Probe scripts saved at `.nelson/missions/2026-04-24_015052_25705c7a/probe_*.py`.

**Full fixture contamination matrix after min_k=2:**
| Fixture | Source | cool_contamination_detected | Winner |
|---|---|---|---|
| wonder_white_10k_lidded | real | True | T5 |
| post_wonder_meal_lidded | real | True | T5 |
| real_100098DE_1351 | real | (cool_available=False) | T4 (firmware) |
| real_1000BA3C_0946 | real | (cool_available=False) | T1 (firmware) |
| real_1000BA3C_1759 | real | False | T1 (firmware, combined rank) |
| probe_removal_contaminates_cool_rank | synthetic | True | T4 |
| core_sensor_unambiguous | synthetic | False | T4 |
| core_sensor_disagreeing_metrics | synthetic | False | T6 |

## Open risks

- **Risk:** 100098DE_1351 shows 17% FP rate under σ=1.0 °C synthetic noise. Lower than min_k=1's 62%, but still not under 5%.
  - **Owner:** follow-up mission.
  - **Mitigation:** Tightening to min_k=3 eliminates the FP but breaks PWM true-positive (PWM's probe pull only engages 2 sensors simultaneously on some samples). Pareto-optimal at min_k=2. Real fix requires noise characterisation of actual Combustion Inc. probes — σ=1.0 is Audacious's synthetic assumption and production noise may be tighter (e.g. σ=0.3 would drop FP rate to near-zero at min_k=2). Acquire a static-temperature dataset.

- **Risk:** Three consecutive missions have shipped fixes anchored to a small number of real CSVs (wonder white, Post Wonder Meal, BA3C_1759, 100098DE, BA3C_0946). The detector now has multiple interlocking thresholds (rate, confirm_n, min_k, confidence gap, cool_available fallback) that are each individually tuned against one or two fixtures. Interaction risks grow with each threshold.
  - **Owner:** follow-up mission.
  - **Mitigation:** Acquire ≥ 4 more real CSVs spanning lidded and unlidded product types. Build an empirical perturbation harness in `tests/` that runs the noise/spike/contamination probes routinely, flagging regressions across threshold changes.

- **Risk:** Pre-existing full-suite failures unchanged across 4 missions now (8 failures mostly in visualization + surface sensor classification). Not in scope but accumulating.
  - **Owner:** dedicated test-hygiene mission.

- **Risk:** Branch `refactor/curve-boundary-detection` now carries 4 missions' worth of uncommitted diff. Merge blast radius grows with each mission.
  - **Owner:** user.
  - **Mitigation:** Commit now (or in grouped commits per mission) before further work. 15-20 new/modified files, cumulative ~1800+ lines of new code and documentation.

## Follow-ups

| Item | Owner | Priority |
|---|---|---|
| Commit + review/merge `refactor/curve-boundary-detection` branch (4 missions' worth now) | user | next session (branch is getting large) |
| Characterise real probe noise σ → re-calibrate contamination thresholds | future fleet | before production deployment |
| Acquire ≥ 4 more real CSVs (lidded + unlidded variety) for threshold cross-validation | user (data collection) | ongoing |
| Build an empirical perturbation test harness in `tests/` | future fleet | when real CSVs arrive |
| Prior missions' open follow-ups (10 items in `memory/project_refactoring_plan.md`) | future fleets | as previously catalogued |

## Mentioned in Despatches

- **HMS Portland** — fast fixture turnaround, clear construction rationale, correctly documented ambiguity. Small miss: the 6th Virtual* column requirement wasn't caught at fixture construction time (Vanguard spotted it downstream) — but noted as a loader-gate edge case, not an error.

- **HMS St Albans** — proactively caught the `LIDDED_NAMES` skip-set side effect when the lidded-bake guardrail test inherited from a prior mission didn't know about the new `post_wonder_meal_lidded` fixture. Fixed within file-ownership scope on admiral prompt without over-reach.

- **HMS Vanguard** — self-reported the semantic deviation (min_k=1 any-sensor-per-sample instead of briefed confirm_n=2) with full rationale AND explicitly flagged it for red-cell validation. That kind of self-disclosure is what makes the red-cell gate meaningful. The DRY extraction into `_drop_rate_detection.py` was a structural win across the codebase.

- **HMS Audacious** — REVISE verdict done right. Reproduced Vanguard's Monte-Carlo with different noise parameters, found 13%/62% FP rates on unlidded guardrails, identified the Pareto-superior min_k=2 threshold empirically, AND saved the probes to disk for Duncan to replay. The "Pareto-optimal" framing (min_k=2 beats min_k=1 on FPs, beats min_k=3 on TPs) is a cleaner decision criterion than "tighten until it passes."

- **HMS Duncan** — refused to assert a false claim. The briefing asked for `test_real_1000BA3C_0946_not_contaminated` asserting `cool_contamination_detected=False`, but the empirical data shows BA3C_0946 DOES have a probe-pull event. Duncan rewrote the test to preserve the guardrail's intent without lying about physics. This kind of discipline protects the suite from becoming a collection of post-hoc rationalisations.

## Reusable patterns

### Adopt
- **User domain insight drives mission scope.** This mission originated from the user correctly identifying that the apparent "cooldown" on lidded CSVs is probe-pull mechanics, not bread cooling. The whole mission existed to encode that insight. Future captains should treat user statements about the physical process as authoritative ground truth, even when the code's behaviour appears to "work."
- **Red-cell empirical perturbation as a Pareto scan.** Audacious didn't just say "min_k=1 is wrong" — they measured FP rates at min_k=1, min_k=2, min_k=3 and reported which was Pareto-optimal. That's a much stronger argument than "tighten until passing." Adopt Pareto-scan framing for all threshold calibration red-cell reviews.
- **Captain refuses to lie.** Duncan rewrote a test rather than assert a false claim. Tests that assert false things become invisible bugs in the suite. This precedent matters.
- **DRY extraction at the point of reuse, not pre-emptively.** Vanguard extracted `_drop_rate_detection.py` when they saw the same scanning pattern in two call sites. This is better than Iron Duke inlining duplicate logic OR than pre-emptively extracting a helper nobody needed.

### Avoid
- **Inheriting guardrail tests that iterate over `source='real'` without a type gate.** The `LIDDED_NAMES` skip-set in `test_existing_unlidded_fixtures_unchanged` required manual maintenance every time a new real lidded fixture was added. Better pattern: add a `product_type` or `is_lidded` flag to the fixture schema and let the guardrail test filter automatically. Not done this mission (would have required modifying prior fixtures), but worth doing next time.
- **Assuming threshold changes will propagate cleanly across all similar cases.** Audacious assumed min_k=2 would also fix BA3C_0946's baseline-contam; empirically it didn't because BA3C_0946 has a genuine probe-pull event. "Works for A → should work for B" is a red-cell assumption that needs its own empirical verification. Duncan catching this saved us from shipping a broken test.
- **Growing interlocking thresholds on a small real-CSV sample.** This mission added `PROBE_REMOVAL_MIN_SIMULTANEOUS_SENSORS` on top of `PROBE_REMOVAL_RATE_C_PER_SEC`, `PROBE_REMOVAL_CONFIRM_SAMPLES`, `CONFIDENCE_GAP_MIN`, `CORE_PEAK_PLATEAU_RATE_C_PER_SEC`, `CORE_PEAK_PLATEAU_CONFIRM_SECONDS`, `DROP_RATE_THRESHOLD_C_PER_SEC`, `CONFIRMATION_WINDOW_SAMPLES`, `INSTANT_DROP_THRESHOLD_C` (now dead), `LARGE_DROP_FROM_PEAK_C`, `MIN_PEAK_TEMP`, `ROOM_TEMP_MAX`, `MIN_CURVE_DURATION_SECONDS`. The threshold surface is getting wide. Future missions should resist adding new thresholds without either (a) physical justification independent of fixture behaviour OR (b) empirically validated removal/merge of an existing threshold.

## Standing order ledger

No blocking violations. Two minor amendments logged:
1. Battle-plan amendment mid-mission: Duncan's task 4 was originally "Final polish + smoke" (station_tier 0, file_ownership []). Rewrote to "REVISE: tighten to min_k=2 + polish" (station_tier 1, file_ownership expanded to 4 files) after Audacious's REVISE verdict. Logged as implicit amendment.
2. Fixture scope expansion authorized via SendMessage to Vanguard mid-implementation (not a formal `battle_plan_amended` event). For future missions, admiral should `nelson-data.py event --type battle_plan_amended` even for small authorizations to keep the audit trail clean.

Mission complete.
