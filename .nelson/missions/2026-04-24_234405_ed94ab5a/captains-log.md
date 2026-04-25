# Captain's Log — HMS Glorious (M2 of flotilla `refactor/curve-boundary-review`)

**Mission ID:** `2026-04-24_234405_ed94ab5a`
**Branch:** `refactor/curve-boundary-review`
**Risk tier:** MEDIUM (Action Station 2 — new plot surface; visual regressions are subtle)
**Mode:** single-session

## Sailing Orders

| | |
|---|---|
| Outcome | Pure plot-builder module `src/visualization/boundary_review_plots.py` consumed by the M3 tab. Two figures + one helper. |
| Metric | 6+ TDD tests pass; reuses VisualizationConfig palette; no Streamlit imports. |
| Deadline | This session. |

## Decisions & Rationale

1. **Per-kind vrect colour mapping in module-level dict.** `_KIND_FILLCOLOR` is a flat dict keyed by `exit_candidate_kind` strings. Manual override gets the most saturated amber so the operator immediately sees pinned curves; detector kinds use translucent teal/blue/orange/grey by candidate type. The mapping lives next to the figure-builders, not in `VisualizationConfig`, because it's specific to this screen and would clutter the shared config.

2. **Detected vs override boundaries use different visual languages.** Detected: solid blue vlines. Override: dashed amber vlines. Hint window: translucent blue vrect. Three visual primitives → three operator-readable concepts. No legend needed because each annotation carries its own text label (top-left for detected start, top-right for detected end, bottom edges for override).

3. **`downsample_for_plot` preserves first AND last samples.** Stride downsampling drops the last samples when `n % stride != 0`, producing a Plotly figure visually clipped on the right. Concat the last row back when missing — minor extra cost, prevents a category of "where did my data go?" UX bugs.

4. **Detail plot reads from `raw_df`, not `curve["data"]`.** Why: `curve["data"]` is the slice from `start_idx` to `end_idx`, but the detail plot adds ±20% padding on either side so the operator can see what's just before and just after the bake. Indexing the raw_df by Timestamp range gives the padding for free; using `curve["data"]` would require re-fetching neighbours.

5. **`hint_window_s` parameter is in absolute log seconds, not (lo_idx, hi_idx).** The hint band sits at `[end_time - expected*(1+tol), end_time - expected*(1-tol)]` from the operator's perspective — i.e. "where would the bake end if it took the hinted duration?" Caller computes the band; the plot draws it. Decouples plot from detector internals.

6. **No `streamlit_plotly_events` integration.** Pure Plotly figures. Drag-to-adjust deferred to DF-1; manual numeric override (M3) is sufficient for the operator's needs.

## Artifacts

| File | Change | Size |
|---|---|---|
| `src/visualization/boundary_review_plots.py` | **NEW** — 3 public functions, ~280 lines | 280 lines |
| `tests/test_boundary_review_plots.py` | **NEW** — 15 tests across 3 classes | 240 lines |

## Validation Evidence

**Red bar:** `ModuleNotFoundError: No module named 'src.visualization.boundary_review_plots'`.

**Green bar:**
```
pytest tests/test_boundary_review_plots.py
============================= 15 passed in 4.97s ==============================
```

**Adjacent tests unaffected** (M1 + sigmoid + sidebar helpers + finale regression family — confirmed via partial regression run; only the pre-existing `test_zone_color_consistency` flake from memory `(j)` triggered, unrelated to M2).

## Open Risks / Follow-ups

- **Performance on 6,200-sample BA3C_1759 with default `downsample_to=5000`** — at the threshold, only every 2nd sample is kept; the bake windows lose 1-sample resolution. The detail plot does NOT downsample (it operates on `±20% padding` window which is ~2,000 samples max), so the operator zoomed-in view is faithful. Acceptable trade-off; document in M3 if any visual regression surfaces.
- **vrect colours may clash on future themes** — hardcoded RGBA strings. If the project adds a dark-mode toggle in a future flotilla, these need to move to `VisualizationConfig`. Noted.
- **Annotation text density on multi-bake CSVs** — BA3C_1759 has 3 vrects, each with `Bake N (kind)` annotation. Top-left positioning may overlap on narrow viewports. M5 browser smoke will verify.

## Mentioned in Despatches

- The module's structural-property test pattern (assert vrect count + vline count + scatter trace presence rather than pixel output) is reusable for any future Plotly figure tests.

## Reusable Patterns

- **Stride-with-endpoint-preservation** — `downsample_for_plot` is generic; could promote to `VisualizationConfig.helpers` if other plots ever face the same problem.
- **Per-kind colour dict** — `_KIND_FILLCOLOR` is the right size to live in the module that uses it; resist the urge to lift to a global config until a second consumer materialises.

## Next Up

M3 HMS Indomitable — new tab module `tabs/boundary_review.py` consuming both M1 (loader.raw_data, set_curve_boundaries) and M2 (plot helpers). MEDIUM risk (Streamlit widget-key bleed).
