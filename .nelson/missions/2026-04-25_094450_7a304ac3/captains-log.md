# Captain's Log — HMS Lookout (M9 of flotilla `refactor/curve-boundary-review`)

**Mission ID:** `2026-04-25_094450_7a304ac3`
**Branch:** `refactor/curve-boundary-review`
**Risk tier:** LOW (Streamlit-Plotly native event API; Streamlit 1.34+ feature; verified locally on 1.56)
**Mode:** single-session

## Sailing Orders

User feedback: *"Is there someway we can do it so I'm able to start with the graph with multiple bake curves, and then zoom in and select the start and end points (or move them)"* — slider was step-improvement but the user wants direct interaction with the plot.

| | |
|---|---|
| Outcome | Drag a horizontal box on the detail plot to set the boundary directly. Plotly handles the visual feedback; Streamlit's `on_select="rerun"` propagates the box back to Python where we convert minutes → idx and pin via `loader.set_curve_boundaries`. |
| Metric | New `extract_x_range_from_selection` helper unit-tested across 8 cases; live drag updates boundary; slider still works for fine-tuning. |
| Deadline | This session. |

## Decisions & Rationale

1. **Native Streamlit `on_select`, no third-party dependency.** Streamlit added Plotly selection events in 1.34 (May 2024); the project's installed version is 1.56. Adding `streamlit_plotly_events` would have given us drag-handles-on-vlines (more granular than box select) but at the cost of a new dependency. Box-select via native API gets us most of the way and keeps `requirements.txt` clean.

2. **`dragmode="select"`, `selectdirection="h"`.** Setting `dragmode="select"` on the detail plot's layout makes click-and-drag a box-select by default — no toolbar interaction needed. `selectdirection="h"` constrains the box to horizontal because y-extent is irrelevant for time-bounded boundaries (we don't care which temperatures the operator drags through). Pan and zoom remain available via the modebar (top-right of every Plotly chart).

3. **`extract_x_range_from_selection` is defensive across event shapes.** Streamlit's plotly state object is dict-like in 1.56 but the exact type may shift; the helper supports both `dict[str, ...]` and attribute-access via `getattr`. Returns `None` for any malformed payload (empty dict, missing `selection`, empty box list, missing `x`, zero-width box). Eight unit tests cover each shape.

4. **Reverse-drag normalised to `(lo, hi)`.** Operator dragging right-to-left produces `x = [25.0, 10.0]` in some Plotly versions; the helper takes `min/max` so direction is irrelevant.

5. **Consumed-signature guard against double-apply.** Streamlit may keep the selection state across reruns triggered by other widgets (e.g. switching curves via radio). Without a guard, the box would re-apply on every rerun. Solution: stash the selection's rounded `(lo, hi)` tuple under `f"detail_box_consumed__{file}__c{N}"` after applying; only act when the current selection's signature differs.

6. **Box-select clears the slider's stored range.** When a box pins the boundary, the curve dict's start/end values change; the slider's session state still holds the old range. Deleting `range_key` from session state forces the slider to read its default from the (now updated) detected start/end on next render — keeping the slider visually aligned with the override.

7. **Caption above the plot, not toolbar tooltip.** Plotly's modebar has a "Box Select" tool but the icon is non-obvious. A 1-line caption ("💡 Drag a horizontal box on the plot to set start/end directly...") makes the gesture discoverable without burying it in tooltips.

## Artifacts

| File | Change |
|---|---|
| `src/visualization/boundary_review_plots.py` | `plot_curve_detail` adds `dragmode="select"` and `selectdirection="h"` to layout |
| `tabs/boundary_review.py` | New `extract_x_range_from_selection` helper; detail-plot chart uses `on_select="rerun"`, `selection_mode="box"`; consumed-signature gate; slider auto-clears on box-apply; caption added |
| `tests/test_boundary_review_tab.py` | New `TestExtractXRangeFromSelection` class with 8 unit tests |

## Validation Evidence

**Green bar:**
```
pytest tests/test_boundary_review_tab.py tests/test_boundary_review_plots.py
       tests/test_loader_baseline_curves.py tests/test_curve_boundary_review_e2e.py
============================= 77 passed in 12.33s =============================
```

**Live smoke** confirms `dragmode="select"` and `selectdirection="h"` are set on the detail plot.

## Open Risks / Follow-ups

- **Plotly modebar still shows zoom as default.** When the user clicks "Zoom" on the toolbar, dragmode flips to "zoom" and box-select stops working until they click "Box Select" again. This is Plotly's native UX — not fixable without a custom modebar config. Acceptable: caption explains the default mode.
- **Box-select affects ONLY the detail plot, not the multi-curve raw-log overview.** The user's mental model in the feedback was "start with multi-curve, zoom, select" — currently they: (a) pick a curve via radio, (b) drag a box on the detail plot. The radio acts as the "which curve" selector. A future polish could add box-select to the raw-log plot too, with the radio determining the target curve. Deferred — current flow is functional.
- **Drag-handle-on-existing-vline** (literal "move them" interaction) requires either `streamlit_plotly_events` or Plotly's editable-shapes feature; box-select is a coarser tool that REPLACES rather than MOVES the boundary. Adequate for current use case.
- **Selection persists across radio switches** if the user box-selects on bake 1, then switches to bake 2. The consumed-signature key is per-(file, curve_number) so the prior selection won't bleed; on the new curve the slider takes over until a new box is drawn.

## Next Up

User testing of the live UI. If responsive, consider raw-log box-select as a future polish.
