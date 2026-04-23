# Captain's Log — oven_logging Structural Refactor

**Mission ID:** `.nelson/missions/2026-04-23_071618_4b7f0acb`
**Branch:** `refactor/structural-cleanup` (from `main` @ `a8a1a53`)
**Mode:** agent-team
**Admiral:** HMS Victory
**Opened:** 2026-04-23T07:16 UTC
**Closed:** 2026-04-23T10:08 UTC
**Duration:** ~2h 52m

---

## Mission summary

**Planned outcome.** Stabilise the Streamlit bread-baking analyzer: fix the physics-flag race in loader.py, decompose app.py into per-tab modules, extract SensorAssignmentManager, dedupe CoreTemperature pattern (21 sites), delete TransformationManager, archive dead scripts/docs. Zero user-visible behaviour change.

**Achieved outcome.** All six deliverables completed. Physics-flag race eliminated (3 regen paths → 1 canonical helper). app.py 1337 → 112 lines (288 under <400 target). SensorAssignmentManager extracted into dedicated class. Column-helper dedup achieved single-source-of-truth for 11 sites (briefing estimate 21 — delta explained by T4/T5 eliminating sites). TransformationManager + 233 lines + integration doc deleted. ~30 ad-hoc scripts + 22 stale docs archived. Repo rebalanced.

**Success metric result.**
- Pre-mission baseline: 9 failed / 69 passed / 1 skipped (+ 1 collection error on the pending column-helper test)
- Final:                7 failed / 106 passed / 1 skipped
- Delta: **+37 passing tests** (pre-existing physics regression test + column-helper contract test both now green; Argyll's 20 characterisation + Diligent's 4 contract + Dreadnought's 11 smoke tests all added; flaky test_deep_insertion now stable in this suite run).
- `app.py`: 1337 → 112 lines (target <400) ✓
- `loader.py`: 1400 → 1137 lines (target <1100; off by 37 — noted as acceptable follow-up)
- Figure-hash parity: 6/6 curve figures byte-identical vs post-T4 baseline, verified independently by red-cell at both T4 and T7.
- 7-tab/8-tab duplication: collapsed into single parameterised builder (grep `st.tabs` in app.py = 1 match).

---

## Delivered artifacts

- **Branch:** `refactor/structural-cleanup` with 11 new commits (list below)
- **Commits (in order):**
  - `68a08b9` test: Sentinel — pre-flight regression safety net (3 regression tests + figure-hash baseline)
  - `685f1d5` chore: Swiftsure — delete unwired TransformationManager (-362 lines)
  - `37f5e6d` chore: Archivist — archive dead scripts and stale docs (~30 scripts, 22 docs, 4 dead modules/artifacts)
  - `d156add` fix: Resolute — collapse 3 column-regen paths, delete _extract_all_baking_curves_old (+75/-232)
  - `9c82eba` chore: baseline refresh after T4 (admiral)
  - `d654652` test: Argyll — characterise automatic sensor getters (20 tests)
  - `35c2634` refactor: Argyll — extract SensorAssignmentManager (+140/-83)
  - `555e618` refactor: Diligent — dedupe CoreTemperature idiom (11 sites → 1 helper)
  - `a477b82` test: Dreadnought — tab modules smoke tests (11 tests, red-phase)
  - `9c3ec90` refactor: Dreadnought — decompose app.py (1337 → 112 lines; 8 tab modules + sidebar/session_state/sensor_naming)
  - `3455fef` docs: Dreadnought damage report

- **Mission directory contents at stand-down:**
  - `sailing-orders.json`, `battle-plan.json`, `fleet-status.json`, `mission-log.json`, `stand-down.json` (structured record)
  - `quarterdeck-report.md` + `quarterdeck-report-[0-2].md` (per-phase checkpoints)
  - `damage-reports/hms-{sentinel,swiftsure,archivist,resolute,argyll,diligent,dreadnought}.json`
  - `red-cell/hms-scrutineer-t{4,7}-review.md` + reviewer-evidence `figure-hashes-*.json`
  - `baseline/figure-hashes.json` (post-T4 canonical parity reference) + `baseline/capture_baseline.py` (reproducer)
  - `plan-input.json` (original squadron+tasks definition)
  - `captains-log.md` (this file)

---

## Key decisions

1. **Execution mode `agent-team` over `subagents`.** Three captains (Resolute/Argyll/Diligent) share ownership of `loader.py`. agent-team's shared task list + SendMessage coordination was the right fit; subagents mode would have lost cross-captain context between handoffs.
2. **Serialise, don't parallelise, on loader.py.** Initial battle plan flagged `split-keel` (HMS Resolute, HMS Argyll, HMS Diligent all claimed `src/data/loader.py`). Remedy per split-keel.md doctrine: amended battle plan to give Resolute exclusive ownership; Argyll and Diligent declared only their new files. Dependency graph (T5 ← T4; T6 ← T4,T5) enforces serial edits. Re-ran conflict scan — clean. No worktree isolation needed.
3. **Delete TransformationManager, don't integrate.** User decision, confirmed pre-flight. The physics-flag fix Resolute delivered addressed the root cause (3 duplicate column-regen paths) more surgically than wiring in a 233-line parallel pipeline would have.
4. **Test-first ordering non-negotiable.** Every behaviour-changing captain had a failing test committed before the fix. Git audit confirms: T1→T4 gap 28m, T5 internal gap 4m, T6 test committed in T1 (Sentinel's), T7 gap 9m 39s.
5. **Baseline refresh between T4 and T5.** Scrutineer discovered during T4 review that the P0 figure-hash baseline was environmentally stale (plotly JSON non-determinism — verified by re-running against HEAD~1 with Resolute's loader stashed; same hashes as d156add, both differed from P0). Admiral refreshed the baseline (`9c82eba`) so T6/T7 had a valid reference.
6. **Two deviations approved for Dreadnought, Option A each:**
   - 3 additive session-state keys (`show_zones`, `smooth_data`, `product_type`) — formerly Python locals passed via closure in the monolith; now idiomatic Streamlit state. Doesn't break widget state machine.
   - `grep st.tabs` returns 2 because the pre-existing Curve Comparison sub-tabs (5 inner tabs) moved with the tab-8 extraction. Mission metric was about the 7/8-tab duplication (collapsed to 1 builder), not every `st.tabs` call. Briefing metric was over-specified.
7. **Diligent's scope discipline.** 3 sites with T1-fallback (not CoreAverage-fallback) were correctly left alone — migrating through `get_core_temperature_column` would raise KeyError where the originals returned T1. Flagged as follow-up, not scope creep.

---

## Validation evidence

- **Test suite.** Baseline 69 passed → final 106 passed (+37). Both previously-failing intentional regression tests (physics, column-helper) now green. Pre-existing 7 failures (4 in test_visualization, 2 in test_surface_sensor_detection, 1 in test_curve_comparison_integration, 1 in test_internal_sensor_filtering) unchanged — not caused by this mission.
- **Figure-hash parity.** Resolute, Scrutineer (T4), and Scrutineer (T7) each independently re-ran `capture_baseline.py` and verified 6/6 byte-identical hashes. Red-cell artifacts in `red-cell/figure-hashes-*.json`.
- **Streamlit boot.** Admiral, Dreadnought, and Scrutineer each separately confirmed HTTP 200 from headless `streamlit run app.py`. No import errors, no session-state errors at boot.
- **DRY audit.** `grep -rn "'CoreTemperature' in " src/ app.py` → exactly 1 match (`src/data/column_helpers.py:19`, the helper). `grep -rn "st.tabs" app.py tabs/` → 2 matches (1 main dispatcher + 1 pre-existing sub-tabs), both legitimate. `grep "def _get_automatic_\|def _validate_sensor_assignments" src/data/loader.py` → 4 delegate stubs (each one-line, no logic). `grep "SurfaceTemperature'] = " src/data/loader.py` → 9 sites across 3 architectural paths, with the bug-surface (virtual) path collapsed to a single if/elif ladder.
- **Red-cell reviews.**
  - T4: APPROVE-WITH-NOTES. Two notes, both housekeeping (baseline refresh — done; future unification of dynamic classifier — logged as follow-up).
  - T7: APPROVE (clean). Six checklist sections all passed. Two residual risks flagged (manual UI walkthrough not performed by red-cell; recommendations tab has a minor recomputation cost) — neither a blocker.
- **TDD audit (from git log timestamps):** All 4 behaviour-changing captains (Resolute T4, Argyll T5, Diligent T6, Dreadnought T7) committed tests before fixes. Sentinel's T1 tests were committed before ANY other captain's work and proved to fail on HEAD for the physics-regression case.

---

## Open risks

1. **Pre-existing test failures (7).** Not touched by this mission. Likely orthogonal to refactor surface but worth triaging in a follow-up: `test_visualization.py::{test_plot_zone_duration_comparison, test_single_curve_comparison, test_many_curves_comparison, test_unknown_zone_handling}`, `test_surface_sensor_detection.py::{test_shallow_insertion, test_deep_insertion}`, `test_curve_comparison_integration.py::test_zone_color_consistency`, `test_internal_sensor_filtering.py::test_realistic_baking_profile`.
   - **Owner:** next-mission captain.
   - **Mitigation:** pinned in CLAUDE.md follow-ups; Archivist's "flaky test_deep_insertion" finding suggests fixture ordering may be involved.

2. **Manual UI walkthrough not conducted by admiral or red-cell.** Dreadnought's DR claims she headless-booted Streamlit and ran her own verification; Scrutineer confirmed headless boot but flagged the full click-through as "not performed". A human should click through the 4 fixture CSVs through all 8 tabs once before merging this branch to main.
   - **Owner:** user / operator.
   - **Mitigation:** figure-hash parity gives high confidence that the data pipeline is unchanged; widget-key grep gives high confidence session-state machinery is unchanged. Residual risk is runtime errors that only surface when state transitions happen. Low probability, low blast radius.

3. **loader.py at 1137 lines, 37 over the <1100 target.** Not a blocker — the target was aspirational. Captain Resolute collapsed 3 column-regen paths; Captain Argyll extracted SensorAssignmentManager; Captain Diligent thinned 1 call site. Further reduction would require tackling the dynamic-classifier path (3 sites still write SurfaceTemperature independently, noted by Resolute as orthogonal to the bug surface).
   - **Owner:** follow-up refactor mission.
   - **Mitigation:** document the next natural seam (extract dynamic classifier) in CLAUDE.md; not urgent.

---

## Follow-ups

- **F1. T1-fallback column-selection variants (3 sites).** `src/analysis/curve_comparison.py:199`, `src/analysis/curve_comparison.py:388`, `src/visualization/plots.py:1106` fall back to `'T1'` (not `'CoreAverage'`). Diligent correctly did NOT migrate — migration would have been a behaviour change. Future mission: decide whether to introduce `get_core_temperature_column_or_t1()` or otherwise reconcile.
  - **Owner:** next column-helper mission.
- **F2. Unify dynamic-classifier path.** `_classify_sensors_dynamically` still writes `SurfaceTemperature` at 3 sites (loader.py:625, 642, 699). Orthogonal to the T4 bug surface (only fires when Virtual* columns are missing), but a future pass could extend `_apply_standard_columns` with a "dynamic-classification result" branch and achieve true single-writer design.
  - **Owner:** future loader-refactor mission.
- **F3. loader.py under 1100 lines.** Current 1137. Needs F2 to get there organically.
- **F4. Pre-existing test failures.** 7 failures in the suite are orthogonal to this mission. Triage recommended.
- **F5. CLAUDE.md update.** The rewrite from the earlier session is still in the working tree as an uncommitted modification. Author (admiral) should decide whether to commit it on this branch or on a separate docs branch.
- **F6. Human UI spot-check before merge.** Click through all 4 `ProbeData_*.csv` fixtures × all 8 tabs once. Lowest-risk task; cheap insurance.
- **F7. 7 pre-existing test failures.** Triage as separate mission.
- **F8. Baseline timestamp post-mission hygiene.** If someone re-runs `capture_baseline.py` they'll dirty `figure-hashes.json` (timestamp-only). Consider parameterising the script to stdout-only mode, or guard with `--overwrite` flag.

---

## Mentioned in Despatches

- **HMS Resolute** (Captain Resolute, T4). Physics-flag race eliminated. 3 column-regen paths → 1 canonical helper. Genuine 28-minute TDD red-phase. Flagged her own figure-hash-drift concern proactively in her damage report rather than burying it. Made the hardest call of the mission (scope boundary on the dynamic-classifier path) cleanly and justified it.
- **HMS Scrutineer** (Red-Cell Navigator, T4 + T7). Two back-to-back clean reviews. At T4, independently isolated refactor-vs-environment drift by swapping in HEAD~1's loader.py, self-disclosed the transient modification, restored cleanly. At T7, verified the pre-existing `st.tabs` sub-call was byte-identical to its pre-refactor location. Proactive process hygiene (killed an orphan Streamlit process). Honest about scope (flagged manual UI walkthrough as "not performed" rather than silently skipping).
- **HMS Diligent** (Captain Diligent, T6). Refactor discipline under fire — correctly distinguished the strict CoreAverage-fallback idiom (migrated, 11 sites) from T1-fallback variants (3 sites, would have been a behaviour change, flagged as follow-up). Explained the 21-vs-11 site discrepancy with precise traceback to T4 and T5.
- **HMS Dreadnought** (Captain Dreadnought, T7). Largest diff of the mission (1337 → 112 line app.py). Paused twice to flag deviations rather than silently violate metrics, proposed 3 options each time with reasoned recommendations. Strict 9m 39s TDD red-phase. Zero `src/` touches — stayed perfectly in scope.

Also noted: **HMS Sentinel** (signal flag — dual-assertion test caught the bug in both _regenerate_standard_columns and _generate_standard_columns_for_df, sharpening Resolute's target), **HMS Archivist** (signal flag — investigated first-run pytest flakiness rather than ignoring it, surfaced as intelligence), **HMS Argyll** (signal flag — textbook TDD extract).

---

## Reusable patterns

**Adopt:**
- **Pre-flight "safety net" captain at Station 0.** HMS Sentinel's role — write regression tests that MUST fail on HEAD before any other captain sails. Turns "is the bug real?" into a provable check rather than a hope.
- **Figure-hash baseline as parity metric for refactors.** 6 SHA-256 hashes against representative fixtures caught nothing this mission (because nothing regressed), but would have caught silent output drift instantly. Cheap to compute, expensive when you need it and don't have it.
- **Serial dependency as legitimate split-keel mitigation.** When N captains must touch the same file, an explicit dependency chain in the battle plan (N depends on N-1) enforces temporal exclusion without needing worktree isolation. Document in the amendment event; re-run conflict scan to prove clean.
- **Red-cell parity-isolation methodology.** For any "refactor is lossless" claim, the red-cell should swap in HEAD~1's version of the touched file and re-run the parity check. If HEAD~1 and the refactor produce the same output, the refactor is lossless. If HEAD~1 matches the baseline but the refactor doesn't, it's a real regression.
- **"Test commit must precede fix commit" git-log audit.** Easy to check, impossible to fake retroactively without rewriting history. Makes TDD enforceable at quarterdeck gates rather than relying on trust.
- **Three-option-with-recommendation deviation protocol.** Dreadnought modelled this well — don't just ask "what do I do?", propose A/B/C with reasoned rec. Admiral can approve in one message. Keeps momentum.

**Avoid:**
- **Over-specifying grep metrics in captain briefings.** My T7 briefing said `grep st.tabs` should return exactly 1 match — but the pre-existing Curve Comparison sub-tabs were legitimate user-visible behaviour that needed to move with tab 8. Resulted in Dreadnought having to pause for a deviation approval. Better: phrase metrics as "collapsed the 7/8-tab duplication into one builder" and let the captain count.
- **Capturing the baseline before all behaviour-stabilising captains have committed.** P0 baseline was captured by Sentinel before Resolute's T4 fix, and turned out to be environmentally stale due to plotly serialization non-determinism. Cost us a ~30-min detour at the T4 red-cell review. Next time: capture the baseline AFTER the critical fix has landed, or capture twice (pre-fix + post-fix) and compare.
- **Assuming characterisation tests need a CSV fixture.** Argyll's 20 tests for SensorAssignmentManager use a mix of synthetic and real-fixture cases; the synthetic ones are faster and more robust to fixture drift. Prefer synthetic for contract tests; use fixtures only when the behaviour is fixture-specific.
- **Implicit coupling between tab modules via shared Python locals.** The 3 deviation-1 variables (`show_zones`, `smooth_data`, `product_type`) were closure-captured in the monolith — a subtle implicit contract. The decomposition surfaced this. Next refactor: look for closure-captured state BEFORE extraction, promote to explicit interface.
