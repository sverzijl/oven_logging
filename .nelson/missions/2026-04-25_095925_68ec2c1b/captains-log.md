# Captain's Log — HMS Vanguard (M10 of flotilla `refactor/curve-boundary-review`)

**Mission ID:** `2026-04-25_095925_68ec2c1b`
**Branch:** `refactor/curve-boundary-review`
**Risk tier:** LOW (UI simplification; loader + plot APIs untouched)
**Mode:** single-session

## Sailing Orders

User feedback after M9 landed: *"Perfect, I don't think if the dragging works we need the text/entry boxes on the right of the graph."*

| | |
|---|---|
| Outcome | Strip the entry widgets in the detail panel right column. Box-select on the plot is now the sole input mechanism. |
| Metric | tabs/boundary_review.py simplified; 90/90 review-tab + plots + baseline + E2E + loader + sidebar tests pass. |
| Deadline | This session. |

## Decisions & Rationale

1. **Removed: hint number_input.** The hint feature still exists in the loader API (`set_expected_durations`) but is no longer reachable from this tab. Tradeoff: operators can't trigger auto-optimisation refinement from the UI anymore. Acceptable because (a) the user explicitly asked, (b) box-select gives more direct control, (c) the prior flotilla's regression suite still covers the hint pathway end-to-end at the loader level (`tests/test_curve_boundary_detector_expected_duration.py`, `test_flotilla_finale_regression.py`).

2. **Removed: manual range slider + Apply button.** Box-select pins on drag-release with zero clicks. The slider was a fine-tuning fallback that, given the user's feedback, isn't needed. If pixel-precision becomes important, the modebar's "Box Select" tool already supports very fine drags (Plotly internally maps mouse pixels to axis coordinates).

3. **Removed: helpers `manual_start_key`, `manual_end_key`, `manual_range_key`, `compute_hint_window_seconds`.** They were public-but-internal utility shims that no longer have callers. Their tests (`TestWidgetKeyShapes`, `TestManualRangeKey`, `TestComputeHintWindowSeconds`) went with them. Sidebar tests in `tests/test_sidebar_expected_duration.py` still cover the helpers in `src/ui/expected_duration_widgets.py` which remain in use by external code.

4. **Removed: bottom-of-panel hint plumbing.** The block that synced widget state to `loader.expected_durations_s` on every render is gone. Without the hint widget there's nothing to sync.

5. **Kept: `boundary_state_label` (simplified).** Was a 4-state machine (auto / hint / override / fallback). With hint gone, it's now binary: `override` or `auto`. Updated 4 tests → 3 tests.

6. **Kept: `time_minutes_to_idx`.** Used by the box-select handler to convert dragged x-range minutes into raw_data indices for `loader.set_curve_boundaries`.

7. **Kept: `extract_x_range_from_selection`.** Box-select event parser. 8 unit tests intact.

8. **Kept: Reset to auto button (standalone).** One-click recovery from a manual override. Was previously inside a 2-column `st.columns` row alongside Apply; now full-width.

9. **Kept: readout (Detected + Boundary shift / override info).** Read-only text that helps the operator verify state — these aren't entry widgets, they're displays. Important context as the operator works.

10. **Override vline overlay simplified.** Previously: `show_override_overlay = state_label == "override" or preview_start != detected or preview_end != detected` (live preview from slider). Now: just `state_label == "override"`. The box-select itself provides Plotly's native rectangle drag-feedback during the drag — no separate vline preview needed.

## Artifacts

| File | Change |
|---|---|
| `tabs/boundary_review.py` | Stripped from 515 → 245 lines; 4 deprecated helpers removed; `render()` and `_render_detail_panel` simplified; imports reduced |
| `tests/test_boundary_review_tab.py` | Removed 14 obsolete tests across 3 classes; 16 tests retained covering the 3 surviving helpers |

## Validation Evidence

**Green bar:**
```
pytest tests/test_boundary_review_tab.py tests/test_boundary_review_plots.py
       tests/test_loader_baseline_curves.py tests/test_curve_boundary_review_e2e.py
       tests/test_loader_curve_boundaries.py tests/test_sidebar_expected_duration.py
============================= 90 passed in 14.23s =============================
```

**Module-surface inspection:**
```
helpers: [boundary_state_label, extract_x_range_from_selection,
          plot_curve_detail, plot_raw_log_with_curves, render,
          time_minutes_to_idx]
```
Down from 11 public names to 6.

## Open Risks / Follow-ups

- **Hint pathway only reachable via direct loader API now.** If a future tab wants to surface the hint feature, `loader.set_expected_durations` is still there. The pure helpers in `src/ui/expected_duration_widgets.py` (minutes_to_seconds, etc.) remain available for that future tab.
- **No keyboard shortcut to reset.** Single button-click. Acceptable.
- **Override vline overlay drops live preview.** Drag-feedback is now Plotly's box rectangle, which disappears after release. The pinned vlines render on the next rerun. Brief visual gap of one round-trip — acceptable.

## Next Up

User testing of the simplified UI. If responsive, consider raw-log box-select as a future polish.
