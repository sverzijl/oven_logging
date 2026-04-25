# Captain's Log — HMS Indomitable (M3 of flotilla `refactor/curve-boundary-review`)

**Mission ID:** `2026-04-24_235134_b68205bd`
**Branch:** `refactor/curve-boundary-review`
**Risk tier:** MEDIUM (Action Station 2 — Streamlit widget-key bleed is the prime hazard; precedent mission `2026-04-24_102020_af6532e1` closes the pattern)
**Mode:** single-session

## Sailing Orders

| | |
|---|---|
| Outcome | New `tabs/boundary_review.py` with raw-log + per-curve detail panel; dispatch from `app.py` in second tab position. |
| Metric | TDD-first pure-helper tests pass; smoke import verifies the tab + plot stack. |
| Deadline | This session. |

## Decisions & Rationale

1. **Tab position #2 (between Temperature Profile and S-Curve Analysis).** Operator-priority ordering: 1st tab = "look at the data", 2nd tab = "verify the detector did the right thing", everything else builds on a verified curve. Chose this over appending after Recommendations because the boundary-review screen is meant to be the *first thing* the operator opens after upload — moving it to #2 puts it right after the default landing tab.

2. **Pure helpers extracted (`compute_hint_window_seconds`, `boundary_state_label`, `manual_*_key`).** Streamlit-bound logic is hard to test. Extracting four pure helpers gave 14 unit tests covering: widget-key shape, hint-window calculation (with min-tolerance floor), and the override/hint/auto state ladder. The `render()` function itself is verified via M5 browser smoke.

3. **`compute_hint_window_seconds` mirrors detector tolerance band** — reads `EXPECTED_DURATION_TOLERANCE_FRAC` and `EXPECTED_DURATION_MIN_TOLERANCE_SECONDS` from the same `CURVE_DETECTION_CONFIG`. If a future mission re-tunes the detector's band, the plot's hint vrect updates automatically. Single source of truth.

4. **Two-column detail layout (3:2 plot:controls split).** Plot dominates so the operator can see the curve clearly; controls are dense but readable. The right column is laid out top-to-bottom: detected readout → hint input → manual override inputs → action buttons. The visual hierarchy matches the operator's mental model: "this is what was detected → here's how I'd fine-tune it → here's how I'd override it entirely".

5. **State badge `🟦 auto / 🟩 hint / 🟧 override`** in the detail header. One-glance status. Colour ladder mirrors the vrect colour for `manual_override` (saturated amber from M2's palette) so the badge and the curve band agree visually.

6. **Reset to auto clears BOTH hint AND override widgets.** Operator's mental model of "back to default" should not require two button presses. Implementation: `clear_curve_boundaries(curve_idx)` + delete the relevant session-state keys + recompute hint list + push to loader. Matches the M5/M6 set-and-rerun pattern.

7. **Apply override pre-validates `start < end` in the UI** before calling `loader.set_curve_boundaries`. The loader also raises `ValueError` (M1 contract) — defence in depth. UI validation produces a friendly `st.error`; loader validation produces a stack trace if somehow bypassed.

8. **Hint plumbing runs every render at the bottom of the panel.** Streamlit number_input edits set session state during the render; the loader's `expected_durations_s` only updates when this code runs. The change-detection guard (`loader.expected_durations_s != hint_list`) prevents Streamlit's rerun loop from firing infinitely.

## Artifacts

| File | Change | Size |
|---|---|---|
| `tabs/boundary_review.py` | **NEW** — render() + 4 pure helpers | 285 lines |
| `app.py` | Import `boundary_review`; insert tab spec at position 2 | +2 lines |
| `tests/test_boundary_review_tab.py` | **NEW** — 14 helper tests across 3 classes | 145 lines |

## Validation Evidence

**Red bar:** `ModuleNotFoundError: No module named 'tabs.boundary_review'`.

**Green bar:**
```
pytest tests/test_boundary_review_tab.py
============================= 14 passed in 3.92s =============================
```

**Integration smoke** (BA3C_1759 real CSV):
```
loader.raw_data.shape: (6214, 25)
loader.all_curves count: 3
raw-log fig: 4 traces, 3 shapes  (1 line + 3 boundary markers; 3 vrects)
detail fig: 1 traces, 5 shapes   (1 line; 2 detected vlines + 1 hint vrect + 2 override vlines)
```

**Tab module imports cleanly + render is callable** — verified via direct import; Streamlit-runtime smoke deferred to M5.

## Open Risks / Follow-ups

- **Browser smoke not yet executed.** The tab module compiles and integrates, but the live UX (radio switching, button responsiveness, expander layout) needs M5 verification. Two specific things to watch:
  - **Number input default-value drift** — Streamlit number_input's `value=` parameter behaves differently when the key is already in session state; if the operator types over a default and the session state has staled, M1's `set_curve_boundaries` may receive mismatched values. M5 should switch curves repeatedly and confirm the panel reflects each curve's actual state.
  - **Plot height on multi-bake CSVs** — the raw-log fig has 3 vrect annotations; on a narrow viewport they may overlap. M5 to verify.
- **State management complexity** — every render re-syncs hint state from session to loader. If a future feature adds a third mutator (e.g. M5 prior-flotilla's `set_sensor_override`), care needed to avoid rerun storms. Document.
- **Manual override clobbers hint refinement for the same curve.** This is by design (M1 contract: override has precedence over hint). The detail panel shows it as `🟧 override`; the operator sees a clear signal. But if they then type a new hint, nothing changes — the override still wins. Document in M5 captain's log if browser smoke surfaces operator confusion.

## Mentioned in Despatches

- The `compute_hint_window_seconds` helper is the right shape for centralising any future detector-aware UI calculation. Pattern: pure function consuming the same config keys the detector reads, so UI and detector stay in sync.

## Reusable Patterns

- **Render → pure helpers → Streamlit primitives.** Three layers: render() orchestrates, helpers compute, primitives render. Each layer testable in isolation.
- **Per-(filename, curve_number) widget keys** — third use of this pattern (M6, M3-current). Promote to a project convention.
- **Apply / Reset button pair** — symmetric controls, plain-language labels, validation in UI before the loader call.

## Next Up

M4 HMS Defender — remove the M6 sidebar widget now that the dedicated screen owns hint editing. LOW risk (deleting UI code; pure helpers in `src/ui/expected_duration_widgets.py` remain because M3 reuses them).
