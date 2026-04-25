# Captain's Log — HMS Refit (M6 of flotilla `refactor/curve-boundary-review`)

**Mission ID:** `2026-04-25_090608_ef2514d4`
**Branch:** `refactor/curve-boundary-review`
**Risk tier:** LOW (Action Station 1 — UX changes only; no detector / loader contract changes)
**Mode:** single-session

## Sailing Orders

User feedback after live-testing the M3 tab:
1. *"The tab for the manual adjustments should be first."*
2. *"The graphs on the manual adjustments have weird numbers that are over 10,000."* — referring to seconds-based x-axis on a multi-hour log
3. *"The manual adjustment is in terms of IDX, but the graph doesn't help you choose the values."*

| | |
|---|---|
| Outcome | Tab → position #1; plot x-axis in MINUTES; manual override accepts time-in-minutes (searchsorted to idx); live-preview vlines while typing. |
| Metric | Existing tests updated; new helper `time_minutes_to_idx` covered by 5 unit tests; full plot+tab+E2E suite green. |
| Deadline | This session. |

## Decisions & Rationale

1. **Public APIs unchanged; conversions at draw/apply time.** The plot helpers' public signatures still take `Timestamp`-based DataFrames and `hint_window_s` in seconds. The loader's `set_curve_boundaries` still takes idx values. The minutes axis is achieved by dividing inside the figure-builders; the time-input widgets are converted to idx via `time_minutes_to_idx` inside the tab module. No consumer of the loader or plot helpers needs to change.

2. **`time_minutes_to_idx` does nearest-neighbour search.** `np.searchsorted(side="left")` gives the left insertion point; we then check whether the previous neighbour is closer in absolute time and pick the smaller-distance idx. This matters at sample boundaries: a user typing "16.65 min" between idx 199 (16.583 min) and idx 200 (16.667 min) gets idx 200 (closer), not 199 (clamped left). Five tests cover zero/exact/between/beyond/empty cases.

3. **Live preview vlines before Apply.** Before this mission, override vlines only appeared AFTER the operator hit Apply (when `state_label == "override"`). The new gate `show_override_overlay = (state_label == "override") or preview_start_idx != detected_start or preview_end_idx != detected_end` shows the dashed amber vlines AS the operator types. Critical for the user feedback: the graph now actively helps choose values because the operator can type a number and see immediately where on the curve the boundary will land.

4. **Annotations now include idx values.** Vline labels read `Detected start (idx 651)` instead of just `Detected start`. Operator can quickly read off the idx for any boundary they're inspecting; cross-references the loader's idx-based contract from the UI.

5. **Hover tooltips show time + idx + temp.** Plotly `customdata` carries the original raw_data row index; the `hovertemplate` displays `t=X.XX min`, `idx=N`, `T=Y.YY°C`. So the operator can hover anywhere on the curve to find the idx of any sample — eliminates the "I have to count grid lines to find idx" friction the user flagged.

6. **`detected_start_min` / `detected_end_min` shown in the readout.** "Start: 54.25 min (idx 651)" — both representations side by side. Operator's mental model maps cleanly between time (what they read off the graph) and idx (what the loader stores).

7. **Tab moved to position #1.** It's the operator's workflow gate: load CSV → verify detection → drill into other tabs. Putting it first matches that flow and reduces clicks.

## Artifacts

| File | Change | Size |
|---|---|---|
| `app.py` | Swap TAB_SPECS — Curve Boundaries first, Temperature Profile second | 2 lines moved |
| `src/visualization/boundary_review_plots.py` | Both plotters convert seconds→minutes at draw time; vrects/vlines/markers use `/60.0`; hover templates show min + idx + °C; vline annotations include idx; xaxis title "Time (min)" | ~30 lines changed |
| `tabs/boundary_review.py` | New `time_minutes_to_idx` helper; manual override widgets in minutes (Start time / End time, max=log_max_minutes); live preview gate; readout shows both min and idx; numpy import added | ~60 lines changed |
| `tests/test_boundary_review_plots.py` | New tests: x-axis title in minutes (raw + detail); vrects in minute coordinates | +14 lines |
| `tests/test_boundary_review_tab.py` | New `TestTimeMinutesToIdx` class with 5 tests | +33 lines |

## Validation Evidence

**Green bar:**
```
pytest tests/test_boundary_review_plots.py tests/test_boundary_review_tab.py tests/test_curve_boundary_review_e2e.py
============================= 56 passed in 18.71s =============================
```

**Live smoke** on BA3C_1759 bake-2:
```
detail fig x-axis title: Time (min)
detail fig x-range: (49.37, 83.55)   ← was 2962.0–5013.0 (seconds) pre-fix
```

## Open Risks / Follow-ups

- **Manual override snap is silent.** Operator types "16.65 min"; on Apply we round to idx 200 (16.667 min). The readout caption shows the snapped idx live ("idx 651 → 944 (293 samples)") so it's not invisible, but a future polish could echo the snapped time too.
- **Live preview overlay always renders when widget value differs from detector decision.** This means even after a Reset, the widgets still hold the LAST entered values until they're cleared. The Reset code DOES delete the widget keys from session state, so the next render reverts. Verified by the existing E2E `test_reset_after_override_reverts_to_detector_decision`.
- **Multi-curve hint plumbing path** unchanged — only the manual override widgets switched to minutes. Hint already accepts minutes (M6 prior flotilla).

## Mentioned in Despatches

- The `time_minutes_to_idx` helper with nearest-neighbour bias is the kind of tiny utility worth promoting to `src/ui/expected_duration_widgets.py` if a second tab ever needs it. Left in the tab module for now (YAGNI).

## Reusable Patterns

- **Internal-conversion-at-draw-time pattern** keeps public APIs stable while reshaping rendered output. Future plot helpers can apply the same trick for any unit conversion.
- **Live-preview-on-divergence gate** — when widget values differ from the underlying state, render the preview overlay even before Apply. Reusable for any "stage then commit" form pattern.
- **Hover customdata with idx + time** — the Streamlit-Plotly idiom for surfacing internal sample indices in a time-axis plot. Could be standardised in `VisualizationConfig.HOVER_TEMPLATES`.
