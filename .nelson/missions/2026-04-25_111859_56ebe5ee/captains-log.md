# Captain's Log — HMS Endeavour (M11 of flotilla `refactor/curve-boundary-review`)

**Mission ID:** `2026-04-25_111859_56ebe5ee`
**Branch:** `refactor/curve-boundary-review`
**Risk tier:** MEDIUM (loader API growth + new dispatch logic; orthogonal storage to existing override system)
**Mode:** single-session

## Sailing Orders

User feedback: *"What if the curve isn't identified, make it so I can identify a curve that hasn't been identified. On selection, the code will try to identify the the curves boundaries which can then be fine tuned by the user."*

| | |
|---|---|
| Outcome | Drag-box on the raw-log plot claims a missed bake region. New `loader.add_manual_curve(s, e)` auto-refines via detector; falls back to BAKE_ACTIVE_C trim. New `loader.remove_manual_curve`. `set_curve_boundaries` dispatches by curve type. |
| Metric | 15 TDD loader tests pass; raw-log box-select wired; existing 78 review/loader/E2E tests still pass. |
| Deadline | This session. |

## Decisions & Rationale

1. **Two orthogonal storages.** `_boundary_overrides: dict[int, tuple]` keyed by **detector position** (not all_curves position), and `_added_curves: list[tuple]` for user-claimed regions. Keeping them separate means user-add and override operations don't interfere — overrides survive user-add insertions because their key is stable in detector-position space.

2. **Detector-position translation in `set_curve_boundaries`.** When the operator overrides a detector curve at all_curves position N, we count how many earlier user-added curves push N's detector position lower. This count gives the stable detector key. Tested via `test_box_select_on_detector_curve_updates_boundary_overrides`.

3. **Auto-refinement strategy: detector first, BAKE_ACTIVE_C trim fallback, user-range last.** Most operator drags will be wider than the actual bake — running the detector on the sub-slice pulls boundaries in. If the region has no clear bake (low peak, short, contaminated), the detector returns nothing; the BAKE_ACTIVE_C trim removes leading/trailing ambient samples. Final fallback: accept the user's range verbatim (they know what they're claiming).

4. **`exit_candidate_kind = "user_added"` and `_user_added_idx`.** The kind string is what the UI consumes for display (badge colour, info text). The `_user_added_idx` is the position in `_added_curves` — used by `set_curve_boundaries` to dispatch updates to the right storage. Both pieces of metadata travel on the curve dict.

5. **Sort + renumber after merge.** Detector curves come back sorted by start_idx; user-added curves go on the end; one final sort across the merged list keeps chronological order. `curve_number` is reassigned 1..N after sort so the radio selector reads sensibly.

6. **Reset/Remove button dispatches based on state.** When the selected curve is `user_added`, the button reads "Remove this bake" and calls `remove_manual_curve`. Otherwise it reads "Reset to auto" and calls `clear_curve_boundaries`. Single button, label-driven — no mode confusion.

7. **Raw-log box-select uses the same `extract_x_range_from_selection` helper as the detail plot.** Single helper, two callers. The consumed-signature gate (per-file for the raw plot, per-file-per-curve for the detail plot) prevents double-firing.

8. **Auto-refinement test for "no curve in region" had to be lenient.** The fallback branch returns the user's range; testing it strictly is brittle because the detector's behaviour at sub-slice scale depends on whether MIN_PEAK_TEMP and MIN_CURVE_DURATION_SECONDS gates trigger. The test asserts only that the range is non-empty and bounded by the user input — trims may or may not happen.

## Artifacts

| File | Change |
|---|---|
| `src/data/loader.py` | New `_added_curves` attribute; `add_manual_curve`, `remove_manual_curve`, `_build_user_added_curve_dict`, `_refine_user_added_region` methods; `_extract_all_baking_curves` appends + sorts + renumbers; `set_curve_boundaries` dispatches |
| `src/visualization/boundary_review_plots.py` | New `user_added` kind colour (purple); `dragmode="select"` + `selectdirection="h"` on raw-log layout |
| `tabs/boundary_review.py` | Raw-log plot wired with `on_select="rerun"` + add_manual_curve handler; `boundary_state_label` extended to `user_added`; badge colour map; Reset/Remove dispatch button |
| `tests/test_loader_user_added_curves.py` | **NEW** — 15 tests across 5 classes |
| `tests/test_boundary_review_tab.py` | +1 test for `user_added` state label |

## Validation Evidence

**Green bar:**
```
pytest tests/test_loader_user_added_curves.py tests/test_loader_curve_boundaries.py
       tests/test_loader_baseline_curves.py tests/test_curve_boundary_review_e2e.py
       tests/test_boundary_review_plots.py tests/test_boundary_review_tab.py
============================= 93 passed in 15.47s =============================
```

**Live smoke** on BA3C_1759:
```
initial curves: 3
after add_manual_curve(2000, 3000) → idx 2, total 4
  bake 1: idx 13-293   kind=probe_pull_cliff _user_added_idx=None
  bake 2: idx 651-944  kind=probe_pull_cliff _user_added_idx=None
  bake 3: idx 2000-3000 kind=user_added     _user_added_idx=0   ← inserted in chrono order
  bake 4: idx 5888-6185 kind=probe_pull_cliff _user_added_idx=None
```

## Open Risks / Follow-ups

- **Refinement on a region containing a bake near MIN_CURVE_DURATION_SECONDS** may fail the detector's gate and fall back to BAKE_ACTIVE_C trim. Acceptable: the user's drag is the source of truth in that case.
- **Removing a user-added curve doesn't touch `_boundary_overrides`** — overrides are detector-keyed and unaffected by user-add insert/remove cycles. Verified by `test_user_added_survives_subsequent_detector_override`.
- **Sensor role identification runs on the user-added slice** so analyzer downstream tabs see the user's range with proper sensor roles.
- **Browser smoke pending.** Live UI verification by the operator.
