# Captain's Log — HMS Inspector (M7 of flotilla `refactor/curve-boundary-review`)

**Mission ID:** `2026-04-25_092326_ec2fbd6e`
**Branch:** `refactor/curve-boundary-review`
**Risk tier:** LOW (snapshot + display addition; no detector / loader-API contract changes)
**Mode:** single-session

## Sailing Orders

User feedback: *"Other than changing the shaded area, expected baketime doesn't seem to do anything"*. The hint WAS reaching the detector but for well-detected bakes the optimisation result agreed with the existing decision — boundary unchanged, hence invisible to the operator.

| | |
|---|---|
| Outcome | Snapshot the no-hint, no-override decision at load_csv time as `loader.baseline_curves`; the Boundary Review tab compares against it to show what auto-optimisation moved (or explain that nothing needed to move). |
| Metric | 7 loader baseline tests + 2 plot baseline-overlay tests pass; live readout shows Δ samples or "no change needed" message. |
| Deadline | This session. |

## Decisions & Rationale

1. **Snapshot at load, not on-demand.** Computing the baseline by re-running detection with `expected_durations_s=None` every time the tab renders would cost ~100–500 ms per render on BA3C_1759 (full detector pass over 6,200 samples). Taking the snapshot ONCE at load is essentially free — the detector already ran with no hint, no override at that moment, so `all_curves` IS the baseline. Just copy.

2. **`_copy_curve_dict` static method on the loader.** The curve dict's `data` field holds a DataFrame slice; if a tab mutates it (e.g. an analyzer adds a derived column), the mutation must not bleed into `baseline_curves`. The helper duplicates the data slice and shallow-copies primitives. Safer than `copy.deepcopy` (which deep-copies the whole DataFrame object including index machinery).

3. **`baseline_curves` is a public attribute, not a method.** Streamlit reads it directly. No need for getters; simpler to inspect in tests.

4. **Three explicit UX states:**
   - **Boundary shifted** → render the diff with absolute baseline + current numbers AND deltas in samples.
   - **Hint active but no shift** → `st.info` reassurance: "Hint accepted; detector's decision is already inside the hint's tolerance band — no boundary change needed."
   - **Override pinned** → `st.info` clarification: "Manual override pinned the boundary; detector input ignored."
   No state collapses to silent "nothing to show" because the user feedback proved that's the failure mode.

5. **Baseline vlines on the detail plot** are dotted grey, drawn BEFORE the solid blue current vlines so the painter algorithm leaves the current vlines visually dominant. Skipped entirely when baseline matches detected (visually redundant).

6. **Baseline overlay only renders when there's a meaningful diff** (`boundary_shifted` boolean). For normal "auto" curves with no hint, no override, baseline_curves[i] equals all_curves[i] exactly, so `boundary_shifted = False` and no extra noise on the plot.

## Artifacts

| File | Change |
|---|---|
| `src/data/loader.py` | New `self.baseline_curves: list = []` attribute; `_copy_curve_dict` static method; snapshot at end of `load_csv` |
| `src/visualization/boundary_review_plots.py` | New `_BASELINE_BOUNDARY_COLOR`; `plot_curve_detail` accepts `baseline_indices` kwarg drawing dotted vlines when differing from current |
| `tabs/boundary_review.py` | `_render_detail_panel` reads `loader.baseline_curves[curve_index]`, computes `boundary_shifted`, threads `baseline_indices` to the detail plot, renders the diff readout or `st.info` reassurance |
| `tests/test_loader_baseline_curves.py` | **NEW** — 7 tests across 2 classes |
| `tests/test_boundary_review_plots.py` | +2 tests for baseline overlay |

## Validation Evidence

**Empirical smoke** confirming hint actually shifts boundaries on BA3C_1759 with extreme hint:
```
baseline_curves count: 3
after extreme hint (10 min on 24-min bakes):
  bake 1: baseline=(13,293) now=(19,293) delta=(+6, 0) kind: probe_pull_cliff -> probe_pull_cliff
  bake 2: baseline=(651,944) now=(657,944) delta=(+6, 0) kind: probe_pull_cliff -> probe_pull_cliff
  bake 3: baseline=(5888,6185) now=(5894,6185) delta=(+6, 0) kind: probe_pull_cliff -> probe_pull_cliff
```
M4 start refinement caps shift at 6 samples (`EXPECTED_DURATION_MAX_START_SHIFT_SECONDS = 30 s` ÷ `dt = 5 s`); the auto-optimisation IS working and the diff readout will now make it visible to the operator.

**Green bar:** `pytest tests/test_loader_baseline_curves.py tests/test_boundary_review_plots.py tests/test_boundary_review_tab.py tests/test_curve_boundary_review_e2e.py → 65 passed`.

## Next Up

M8 HMS Mercury (this session) — replace the two number_input widgets with a single range slider for faster manual-override editing.
