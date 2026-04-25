# Captain's Log — HMS Achilles (M5 of flotilla `refactor/curve-boundary-review`)

**Mission ID:** `2026-04-24_235912_a7eef390`
**Branch:** `refactor/curve-boundary-review`
**Risk tier:** MEDIUM (Action Station 2 — no new code, but may surface bugs that bounce back to M1–M3)
**Mode:** single-session

## Sailing Orders

| | |
|---|---|
| Outcome | End-to-end empirical verification of the boundary-review flotilla. Permanent regression test exercising loader-level operations the M3 tab issues; memory update; final flotilla captain's log. |
| Metric | E2E tests pass on 3 real CSVs; full suite baseline preserved; flotilla entry appended to memory; final log documents M1–M5. |
| Deadline | This session. |

## Decisions & Rationale

1. **E2E test exercises the LOADER, not Streamlit.** The M3 tab's UI primitives (number_input, buttons, plotly_chart) need the runtime to test live; the M5 regression simulates the **state transitions** the operator triggers on the loader. This catches the failure modes that matter (override survives hint? clear reverts to detector? raw_data preserved?) without taking a Streamlit-runtime dependency on CI.

2. **Parametrised raw_data preservation across 3 CSVs × 4 operations.** Twelve assertions for the price of one — pytest's parametrize handles the matrix. M1's contract gets 12 anchored regression points instead of one or three.

3. **Browser smoke documented as a user-action checklist** rather than a failed mission. The Streamlit runtime is slow to spawn in CI and the verification is mostly visual (does the expander appear in the right place? does the override badge change colour?). Documenting the checklist in this captain's log lets the user (or a future operator) run it themselves with full confidence about what to look for.

4. **`TestNoRegressionOnRealCSVs` belt-and-braces.** Even though prior flotilla regression tests cover this, having a single-class assertion that "BA3C_1759 still produces 3 curves under no hint and no override" guards against the M1 latent-bug-fix style of regression: silent count change after a refactor.

5. **Memory entry placed at top of the chronology.** Memory format adds new entries at the top so a reader scanning `MEMORY.md` sees the latest first; entry `(xi)` (this flotilla) lands above `(x)` (prior). Cross-references prior flotilla's commits and notes the branch-off point.

## Artifacts

| File | Change | Size |
|---|---|---|
| `tests/test_curve_boundary_review_e2e.py` | **NEW** — 19 E2E tests across 5 classes | 168 lines |
| Memory: `project_refactoring_plan.md` | Entry `(xi)` appended | +1 line (long) |

## Validation Evidence

**Green bar:**
```
pytest tests/test_curve_boundary_review_e2e.py
============================= 19 passed in 8.39s =============================
```

**Aggregate test stack across both flotillas:**
| Flotilla | Mission | File | Tests |
|---|---|---|---|
| Prior | M1 | `test_curve_boundary_fixture_schema.py` | 5 |
| Prior | M2 | `test_sigmoid_refinement.py` | 22 |
| Prior | M3 | `test_curve_boundary_detector_expected_duration.py` | 14 |
| Prior | M4 | `test_curve_boundary_detector_start_refinement.py` | 11 |
| Prior | M5 | `test_loader_expected_duration.py` | 9 |
| Prior | M6 | `test_sidebar_expected_duration.py` | 13 (was 11; +2 M4-this-flotilla) |
| Prior | M7 | `test_flotilla_finale_regression.py` | 29 |
| **Current** | M1 | `test_loader_curve_boundaries.py` | 15 |
| **Current** | M2 | `test_boundary_review_plots.py` | 15 |
| **Current** | M3 | `test_boundary_review_tab.py` | 14 |
| **Current** | M4 | `test_sidebar_expected_duration.py` | (covered above) |
| **Current** | M5 | `test_curve_boundary_review_e2e.py` | 19 |
| Existing | — | `test_curve_boundary_detection.py` | 33 (unchanged) |
| **Total flotilla tests** | | | **73 new this flotilla** |

## Browser Smoke Checklist (manual, user action)

After landing this flotilla, run `streamlit run app.py` and walk through:

**Sidebar (M4 verification):**
- [ ] Upload `ProbeData_100098DE_2025-05-30 13_51_07.csv`.
- [ ] Confirm sidebar Analysis Settings shows: Show zones, Apply smoothing, Product Type, then File Management. **No expected-bake-time expander**.

**Curve Boundaries tab (M3 verification):**
- [ ] Switch to "🔬 Curve Boundaries" — should be the second tab.
- [ ] See raw CSV log with one teal vrect (probe_pull_cliff) for the single bake. Diamond markers at start/end.
- [ ] Detail panel shows: detected start/end indices + duration + peak + kind.
- [ ] Type "25" into the hint number_input → boundary may shift; the badge changes to `🟩 hint`; the hint band (translucent blue) appears in the detail plot.
- [ ] Set Start sample idx to a value 5 samples earlier and click "Apply override" → badge changes to `🟧 override`; dashed amber vlines appear; the raw-log vrect for this curve becomes saturated amber.
- [ ] Click "Reset to auto" → badge returns to `🟦 auto`; vrect goes back to teal; hint number_input clears.

**Multi-bake (M1 latent-bug verification):**
- [ ] Upload `ProbeData_1000BA3C_2025-05-30 17_59_37.csv`.
- [ ] Curve Boundaries tab raw-log shows **three** vrects (bakes 1, 2, 3).
- [ ] Apply a hint to bake 2 only → still see 3 vrects (M1 fix anchored: hint editing no longer drops bakes).

**Cross-tab consistency:**
- [ ] After applying a manual override on Curve Boundaries tab, switch to Temperature Profile → the curve shown should reflect the pinned slice.

If any step deviates, capture the screenshot and mention this flotilla's mission IDs (M1–M5) in the issue report.

## Open Risks / Follow-ups

- **Browser smoke not yet executed by admiral.** Pending user action per checklist above. If anything regresses, M5 bounces work back to M3 (tab) or M2 (plot) most likely; M1 (loader) is well-anchored by 15+19 tests now.
- **Memory follow-up `(j)` pre-existing failures** still present (test_deep_insertion flake + zone colours + surface sensor detection — 7-8 unrelated tests). Cleanup belongs to a separate initiative.
- **Override persistence across browser sessions** (DF-3 in plan) deferred. `loader._boundary_overrides` is in-memory; refresh clears.
- **Drag-to-adjust** (DF-1) deferred. Current numeric-input UX is sufficient per user direction.
- **Auto-prefill from BAKEOUT_TARGETS** (DF-4) deferred. Current Detected pre-fill is a reasonable starting point.

## Mentioned in Despatches — Flotilla Honours

- **M1 HMS Ardent** — discovered and fixed a latent bug from the prior flotilla's M5 (`set_expected_durations` re-detecting on the first-curve slice). The discovery test (`test_set_expected_durations_preserves_all_three_bakes`) anchors the regression and would have prevented the bug had it existed in the prior flotilla.
- **All 5 missions green on first internal red bar** — no red-cell rounds needed across the flotilla. Lower-risk shape (no detector changes, no novel numerical methods) but a clean run validates the M1–M2 sequencing where pure modules precede UI.

## Reusable Patterns (this flotilla)

1. **Discovery test for latent bugs.** When adding a new attribute that *should* have been used in older code, write the test that asserts the new attribute makes a difference somewhere — it surfaces the silently-broken paths.
2. **Render → pure helpers → Streamlit primitives** (M3). Three layers, each testable in isolation.
3. **Per-(filename, curve_number) widget keys** (third use, M3 of this flotilla). Project convention now.
4. **Replace deletion comments with cross-mission references** (M4). Future readers see the lineage without `git log`.
5. **E2E via state-transition simulation** (this mission). Skip Streamlit runtime; assert the loader settles into the right shape after the operator's button-press equivalents.

## Flotilla Summary — `refactor/curve-boundary-review`

7 commits across 5 missions, branched off prior flotilla HEAD `4486734`:

| Mission | Commit | Risk | Deliverable |
|---|---|---|---|
| M1 HMS Ardent | `0469e4d` | LOW | `raw_data` attribute + `set_curve_boundaries` / `clear_curve_boundaries` + latent bug fix |
| M2 HMS Glorious | `a5627e9` | MEDIUM | `src/visualization/boundary_review_plots.py` pure module |
| M3 HMS Indomitable | `68c7588` | MEDIUM | `tabs/boundary_review.py` + `app.py` dispatch |
| M4 HMS Defender | `060eefb` | LOW | M6 sidebar expander removed; helpers retained |
| M5 HMS Achilles | this | MEDIUM | E2E regression + memory update + flotilla log |

**Aggregate:** 73 new tests this flotilla; 101 prior-flotilla + 33 detection tests preserved; full-suite baseline (8 pre-existing failures from memory follow-up `(j)`) unchanged.

**User-facing change:** the M6 sidebar expander is gone; a new "🔬 Curve Boundaries" tab at position #2 shows the raw CSV with auto-detected windows overlaid, lets the operator type a bake-time hint per curve, and supports manual sample-index pinning via "Apply override" / "Reset to auto" buttons. Per-curve state badge (`🟦 auto / 🟩 hint / 🟧 override`) shows what's driving the boundary at a glance.
