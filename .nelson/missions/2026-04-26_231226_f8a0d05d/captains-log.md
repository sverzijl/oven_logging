# Captain's Log — Temperature Profile Tab Review

**Admiral:** HMS Britannia (Opus)
**Date completed:** 2026-04-27
**Mission ID:** 2026-04-26_231226_f8a0d05d
**Duration:** 47 minutes
**Outcome:** **ACHIEVED**

---

## Mission summary

- **Planned outcome:** Detailed read-only review of the Temperature Profile tab — bugs, code smells, DRY violations — with empirical red-cell verification and a one-page synthesis.
- **Achieved outcome:** Three-captain read-only review completed. Two confirmed bugs (B1 heatmap role-blindness, B2 index drift) documented with file:line + empirical evidence. Seven code smells and two DRY groups catalogued. Hood signed off with **go** verdict and a 4-captain follow-up flotilla plan.
- **Success metric result:** Hood's 60-line sign-off lists confirmed defects, accepts all smells/DRY findings as-is, estimates ~150 LOC delta across ~8 files, recommends branch `refactor/temperature-profile-canonical-roles`. The user can launch the follow-up flotilla without re-reading Vanguard's full review.

---

## Delivered artifacts

| Artifact | Location |
|---|---|
| Empirical evidence pack (Astute) | `astute-evidence.md` |
| Repro scripts (Astute, optional persistence) | `repro/claim_a_index_drift.py` |
| Unified review report (Vanguard) | `vanguard-review.md` |
| Synthesis sign-off (Hood) | `hood-signoff.md` |
| Quarterdeck reports | `quarterdeck-report.md` (latest), `quarterdeck-report-0.md` (checkpoint 1) |
| Damage reports | `damage-reports/HMS-Astute.json`, `damage-reports/HMS-Vanguard.json`, `damage-reports/HMS-Hood.json` |
| Structured mission state | `sailing-orders.json`, `battle-plan.json`, `mission-log.json`, `fleet-status.json`, `stand-down.json` |

All paths relative to `.nelson/missions/2026-04-26_231226_f8a0d05d/` under the project workspace.

---

## Key decisions

1. **Astute fires first, not last.** The original red-cell convention is verify-after; here the admiral inverted the order so Vanguard's review report could cite Astute's empirical verdicts directly instead of speculating. This eliminated hedge language and bound the review to evidence.
   - **Rationale:** Astute's verdicts (PASS / CONDITIONAL PASS / ZERO) are load-bearing for severity ratings; sequencing them first removed an entire class of "Vanguard-says, Astute-counters" mid-mission churn.

2. **0 crew per captain.** All three captains implemented directly (no PWO, NO, MEO, etc.).
   - **Rationale:** Crew-or-Direct decision tree said "atomic single-deliverable → captain implements directly." Adding a PWO would have duplicated reads the captain was already doing — skeleton-crew anti-pattern. Confirmed by no captain reporting context exhaustion (lowest hull observed: Astute 78%, after delivery — informational only).

3. **B2 (index-drift) kept as confirmed bug despite narrow trigger.** Astute returned CONDITIONAL PASS (latent — sidebar.py:144-147 keeps indices synchronised under normal navigation). Hood was offered the option to demote it to a smell.
   - **Hood's call:** Reject the demotion. The reasoning: synchronisation between `loader.current_curve_index` and `st.session_state.current_curve_index` is a *coincidence of execution order*, not a structural guarantee. Any future caller (URL parameter reader, keyboard shortcut, programmatic test harness) that updates session state without calling `set_current_curve()` re-fires the bug. CLAUDE.md "Known Fragile Areas" documents exactly this class of latent fragility biting the project before. The dual-call architecture is a standing hazard, not a theoretical one.
   - **Admiral concurs.** This was the load-bearing adjudication call of the mission.

4. **No source code changes.** The mission charter was review-only. The canonical-helper API is genuinely undecided — Vanguard recommends `src/ui/sensor_role_helpers.py` with two functions (`build_sensor_role_map`, `build_sensor_label_map`), but Hood's go-verdict transitions the API decision into the follow-up flotilla, not this one.

---

## Validation evidence

- **Astute (B1 heatmap role-blindness, PASS):** Built a synthetic DataFrame and called `plot_temperature_gradient_heatmap()` directly. Observed `fig.data[0].y = ['Core 1', 'Core 2', 'Core 3', 'Core 4', 'Middle 1', 'Middle 2', 'Near Surface', 'Surface']` — invariant to perturbed role assignments. Z-rows = raw T1..T8 column data. Function signature at `src/visualization/plots.py:211` confirms only `data` is accepted; lines 214 and 226 confirm hardcoded sensor list and firmware-default labels. (`astute-evidence.md §(b)`.)
- **Astute (B2 index-drift, CONDITIONAL PASS):** Loaded `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` (3 curves, identical role assignments — divergence invisible without perturbation). Injected distinct surface assignments (T6 for curve 0, T7 for curve 1). Set `loader.current_curve_index = 0`. Compared `get_sensor_assignments_with_overrides(1)` (line-19 simulation) vs `get_sensor_assignments_with_overrides()` (line-53 simulation). Result: `surface_sensor` differed (T7 vs T6). Mechanism proven; trigger window confirmed narrow under current `sidebar.py:144-147` synchronous execution. (`astute-evidence.md §(a)`.)
- **Astute (test coverage, ZERO):** `pytest --collect-only -q` enumerated 347 tests. Grep on `tests/` for `plot_temperature_gradient_heatmap` and `plot_temperature_profile`: zero matches. Two files reference `tabs.temperature_profile` — `test_tab_modules_smoke.py` (import + callable check) and `test_widget_key_per_curve.py` (regex on f-string keys). Neither exercises runtime behaviour. Pre-existing pytest baseline: 8 fail / 338 pass / 1 skip — none in Temperature Profile scope. (`astute-evidence.md §(c)`.)
- **Vanguard report:** 291 lines covering all 5 required sections with file:line citations throughout. Reconciled both existing helpers (`sensor_naming.get_dynamic_sensor_names`, `curve_comparison.transform_sensor_assignments_to_roles`) explaining why neither is reusable as-is. (`vanguard-review.md`.)
- **Hood sign-off:** 60 lines, no new findings introduced, every adjudicated item traces to (Vanguard claim ↔ Astute verdict). (`hood-signoff.md`.)

---

## Open risks

- **Risk:** B2 (index drift) is preserved as a confirmed bug but is invisible in current normal navigation. A future contributor who tests B2's fix only against the live UI may believe the fix is unnecessary and revert it.
  - **Owner:** Follow-up flotilla Captain 3.
  - **Mitigation:** TDD test must cover the perturbed-fixture scenario (loader index ≠ session-state index). Test must fail before the fix lands.

- **Risk:** Pytest baseline showed 8 pre-existing failures unrelated to this tab. The follow-up flotilla's new tests will be added to a partially-broken suite, complicating green-baseline reasoning.
  - **Owner:** Follow-up flotilla Captain 1 (test infrastructure).
  - **Mitigation:** New tests should be in dedicated files; CI guard should track only the new tests' pass/fail until the pre-existing failures are addressed.

- **Risk:** The canonical helper API in `src/ui/sensor_role_helpers.py` is currently a recommendation, not a contract. The follow-up flotilla's Captain 1 will set the API; if Captains 2-4 disagree, the flotilla churns.
  - **Owner:** Follow-up flotilla admiral.
  - **Mitigation:** Captain 1's failing-test-first deliverable must include the canonical signature with at least three call sites stubbed. Subsequent captains either adopt or escalate before implementation.

---

## Follow-ups

| Item | Owner | Due |
|---|---|---|
| Launch follow-up refactor flotilla on branch `refactor/temperature-profile-canonical-roles` (4 captains: helper module + heatmap fix + tab refactor + sweep migration; optional Astute red-cell pass) | Next nelson mission | When user is ready |
| Address pre-existing 8-test pytest baseline failures (out of this mission's scope; flagged to memory) | Separate mission | Before next major refactor |
| Audit other tabs for the same Pattern A / Pattern B duplication and double-fetch-of-assignments smell — `curve_comparison.py` already has `transform_sensor_assignments_to_roles`; sweep should consolidate when canonical helper is in place | Captain 4 of follow-up flotilla | During the sweep migration |

---

## Mentioned in Despatches

- **HMS Astute** — Empirical verification was the load-bearing input to the entire mission. Used perturbed fixtures (the standing-order remedy) when the unperturbed CSV gave a false-negative on (a). Conditional verdict on (a) was nuanced and accurate. Identified narrow trigger window without overclaiming or underclaiming.
- **HMS Vanguard** — 291 lines covering 5 sections without padding; surfaced S6 (redundant double-fetch of assignments) and S7 (duplicate role-iteration in `plots.py:107-113`) — both genuinely new finds beyond the brief, sharpening the DRY map.
- **HMS Hood** — Made the load-bearing adjudication call (B2 demotion rejected) with one-paragraph structural reasoning grounded in CLAUDE.md "Known Fragile Areas." Held the line on "no new findings" and delivered an actionable one-pager the user can launch from.

---

## Reusable patterns

### Adopt
- **Astute-first ordering for review missions.** When the review captain's claims will be load-bearing for severity ratings, run the empirical verifier *before* the reviewer so the report cites verdicts instead of speculation. Removes mid-mission churn.
- **0-crew captains for read-only review work.** Per crew-or-direct decision tree: atomic single-deliverable tasks where the captain reads code → captain implements directly. Adding a PWO duplicates the captain's reads (skeleton-crew anti-pattern).
- **Hood's "no new findings" constraint for synthesis captains.** The synthesis captain's job is to adjudicate, not extend. This produced a 60-line one-pager from 350 lines of upstream artefacts and kept the deliverable directly usable as a launch document.
- **Perturbation-first red-cell.** Astute's CONDITIONAL PASS on (a) was unreachable without perturbing the fixture (3-curve CSV had identical role assignments per curve). Calibration-to-a-sample-of-one is invisible from the diff but obvious from a perturbation run — this codebase's standing red-cell pattern continues to pay off.

### Avoid
- **Quarterdeck-report rotation hygiene.** I overwrote checkpoint 1's `quarterdeck-report.md` with checkpoint 2's content before rotating the previous report to `quarterdeck-report-0.md`. Reconstructed from memory afterwards. The canonical procedure is: rotate FIRST (rename existing → `quarterdeck-report-N.md`), then write the new report. The skill prompt was clear; I was sloppy.
- **Don't drop the standing rotation step even when the previous report is short.** The on-disk report is the only recovery point if context compaction occurs mid-mission. A reconstructed report is better than none, but it loses the original timestamp and audit trail.

---

## Mission stats

| Metric | Value |
|---|---|
| Captains | 3 (HMS Astute, HMS Vanguard, HMS Hood) |
| Crew per ship | 0 |
| Marines deployed | 0 |
| Reliefs | 0 |
| Standing-order violations | 0 |
| Circuit-breaker fires | 1 (Astute hull 78% post-delivery — informational only, ship had paid off) |
| Damage reports filed | 3/3 |
| Structured artefacts | sailing-orders.json, battle-plan.json, mission-log.json, fleet-status.json, stand-down.json |
| Token budget | 70% consumed (admiral context) |
| Duration | 47 minutes |

---

**Mission complete.** Recommend launching the follow-up refactor flotilla per Hood's go-verdict.
